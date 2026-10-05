"""Plugin ownership, deterministic adapters and loaded-root execution regressions."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import check_layout, plugin_metadata
from software_factory.errors import FactoryError
from software_factory.resources import skill_path
from software_factory.store import runs_root

ROOT = Path(__file__).resolve().parents[1]


def copy_plugin(destination: Path) -> Path:
    destination.mkdir()
    for folder in ("software_factory", "skills", ".codex-plugin", ".agents", ".claude-plugin"):
        shutil.copytree(ROOT / folder, destination / folder,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_version.py"))
    (destination / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/factory.py", destination / "scripts/factory.py")
    return destination


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in root.rglob("*")}


class PluginStructureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="factory plugin tests ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.plugin = copy_plugin(self.root / "copied plugin")

    def test_metadata_generation_is_deterministic_and_check_is_read_only(self):
        before = snapshot(self.plugin)
        plugin_metadata.sync(self.plugin, check=True)
        self.assertEqual(snapshot(self.plugin), before)
        plugin_metadata.sync(self.plugin)
        self.assertEqual(snapshot(self.plugin), before)
        codex = json.loads((self.plugin / ".codex-plugin/plugin.json").read_text())
        claude = json.loads((self.plugin / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(codex["name"], claude["name"])
        self.assertNotIn("version", codex)
        self.assertNotIn("version", claude)
        (self.plugin / ".claude-plugin/plugin.json").write_text('{}\n')
        stale = snapshot(self.plugin)
        with self.assertRaisesRegex(ValueError, "drift"):
            plugin_metadata.sync(self.plugin, check=True)
        self.assertEqual(snapshot(self.plugin), stale)

    def test_metadata_rejects_unsupported_components_types_and_duplicate_keys(self):
        path = self.plugin / ".codex-plugin/plugin.json"
        original = path.read_text()
        for change in ({"mcpServers": "./.mcp.json"}, {"version": "1.0.0"},
                       {"skills": "../escape"}, {"name": 123}, {"interface": {"defaultPrompt": "text"}}):
            value = json.loads(original) | change
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                plugin_metadata.sync(self.plugin)
        path.write_text(original.replace('"name": "software-factory"', '"name": "software-factory", "name": "other"'))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            plugin_metadata.sync(self.plugin)

    def test_catalog_cannot_escape_root_or_add_plugins(self):
        path = self.plugin / ".agents/plugins/marketplace.json"
        original = json.loads(path.read_text())
        for source in ("../", "/tmp", "./plugins/software-factory"):
            value = json.loads(json.dumps(original))
            value["plugins"][0]["source"]["path"] = source
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "exactly one"):
                plugin_metadata.sync(self.plugin)
        original["plugins"].append(original["plugins"][0])
        path.write_text(json.dumps(original))
        with self.assertRaises(ValueError):
            plugin_metadata.sync(self.plugin)

    def test_metadata_refuses_skill_and_output_directory_aliases(self):
        outside = self.root / "outside"
        shutil.move(self.plugin / "skills", outside)
        (self.plugin / "skills").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            plugin_metadata.sync(self.plugin)
        (self.plugin / "skills").unlink()
        shutil.move(outside, self.plugin / "skills")
        shutil.rmtree(self.plugin / ".claude-plugin")
        (self.plugin / ".claude-plugin").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            plugin_metadata.sync(self.plugin)
        self.assertFalse(outside.exists())

    def test_layout_checks_untracked_source_and_does_not_follow_cycles_or_generated_data(self):
        subprocess.run(["git", "init", "-q", self.plugin], check=True)
        (self.plugin / ".gitignore").write_text("build/\n__pycache__/\n")
        (self.plugin / "build").mkdir()
        (self.plugin / "build/skills").symlink_to(self.plugin / "build")
        before = snapshot(self.plugin / "skills")
        check_layout.check(self.plugin)
        self.assertEqual(snapshot(self.plugin / "skills"), before)
        alias = self.plugin / "skills/cycle"
        alias.symlink_to(self.plugin / "skills", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "alias|link"):
            check_layout.check(self.plugin)
        alias.unlink()
        empty = self.plugin / "skills/empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "Empty"):
            check_layout.check(self.plugin)
        empty.rmdir()
        (self.plugin / "skills/.gitkeep").touch()
        with self.assertRaisesRegex(ValueError, "Placeholder"):
            check_layout.check(self.plugin)

    def test_layout_rejects_duplicate_skill_and_nested_wrapper(self):
        subprocess.run(["git", "init", "-q", self.plugin], check=True)
        wrapper = self.plugin / "plugins/software-factory"
        wrapper.mkdir(parents=True)
        (wrapper / "README.md").write_text("nested wrapper")
        with self.assertRaisesRegex(ValueError, "nested"):
            check_layout.check(self.plugin)
        shutil.rmtree(self.plugin / "plugins")
        (self.plugin / "software_factory/SKILL.md").write_text("duplicate")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            check_layout.check(self.plugin)

    def test_launcher_uses_loaded_root_with_literal_arguments_and_unrelated_cwd(self):
        sentinel = self.root / "factory"
        sentinel.write_text("#!/bin/sh\nexit 99\n")
        sentinel.chmod(0o755)
        env = {**os.environ, "PATH": str(self.root), "PYTHONPATH": str(ROOT)}
        before = snapshot(self.plugin)
        result = subprocess.run([sys.executable, self.plugin / "scripts/factory.py", "skill-path", "--json"],
                                cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)), self.plugin / "skills/software-factory")
        literal = subprocess.run([sys.executable, self.plugin / "scripts/factory.py", "unknown $(touch unwanted)", "--json"],
                                 cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(literal.returncode, 2)
        self.assertIn("unknown $(touch unwanted)", json.loads(literal.stderr)["error"])
        self.assertFalse((self.root / "unwanted").exists())
        self.assertEqual(snapshot(self.plugin), before)

    def test_missing_plugin_resources_fail_without_global_fallback(self):
        for relative in ("skills/software-factory/protocol.md", "software_factory/cli.py",
                         "software_factory/templates/prd/_template.md", ".codex-plugin/plugin.json"):
            path = self.plugin / relative
            content = path.read_bytes()
            path.unlink()
            result = subprocess.run([sys.executable, self.plugin / "scripts/factory.py", "skill-path", "--json"],
                                    cwd=self.root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)["code"], "resources")
            self.assertNotIn("Traceback", result.stderr)
            path.write_bytes(content)

    def test_unsafe_engine_alias_fails_before_outside_import_side_effects(self):
        marker = self.root / "outside-imported"
        outside = self.root / "outside.py"
        outside.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
        module = self.plugin / "software_factory/__init__.py"
        module.unlink()
        module.symlink_to(outside)
        result = subprocess.run([sys.executable, self.plugin / "scripts/factory.py", "skill-path", "--json"],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["code"], "resources")
        self.assertFalse(marker.exists())

    def test_source_marker_never_falls_back_to_generated_wheel_resources(self):
        package = self.root / "wheel/software_factory"
        destination = package / "skills/software-factory"
        shutil.copytree(self.plugin / "skills/software-factory", destination)
        self.assertEqual(skill_path(package), destination)
        (package.parent / ".codex-plugin").mkdir()
        with self.assertRaisesRegex(FactoryError, "Missing"):
            skill_path(package)

    def test_copied_read_only_plugin_completes_local_lifecycle_without_root_writes(self):
        before = snapshot(self.plugin)
        for path in self.plugin.rglob("*"):
            path.chmod(0o555 if path.is_dir() else 0o444)
        self.plugin.chmod(0o555)
        def restore():
            self.plugin.chmod(0o755)
            for path in self.plugin.rglob("*"):
                path.chmod(0o755 if path.is_dir() else 0o644)
        self.addCleanup(restore)
        result = subprocess.run([sys.executable, ROOT / "scripts/smoke_install.py", "--plugin-root", self.plugin],
                                cwd=self.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["pluginLifecycle"], "passed")
        self.assertEqual(snapshot(self.plugin), before)

    def test_maintained_document_links_resolve(self):
        paths = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *(p for p in ROOT.rglob("docs/**/*.md") if "history" not in p.parts),
                 *ROOT.glob("skills/software-factory/*.md")]
        for path in paths:
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
                if ":" in target or target.startswith("#"):
                    continue
                self.assertTrue((path.parent / target.split("#")[0]).exists(), f"{path.name}: {target}")

    def test_moved_usage_preserves_run_location_and_numeric_limits_as_prose(self):
        usage = '\n'.join((ROOT / p).read_text() for p in ('docs/user-guide/project-setup.md', 'docs/user-guide/tasks-and-recovery.md', 'docs/reference/commands.md'))
        common = Path("synthetic-common")
        recorded_location = runs_root(common).relative_to(common).as_posix()
        self.assertIn(f"Git common-dir (`{recorded_location}`)", usage)
        self.assertIn("`timeoutMs` (100–600000)", usage)
        self.assertIn("checks (name/scope/status/message/remedy)", usage)
        self.assertIn("limit (1–1000)", usage)
        self.assertNotIn("(user-guide/", usage)
