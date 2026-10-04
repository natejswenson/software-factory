"""Real Git readiness observations must leave every source/evidence byte untouched."""

import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from software_factory import engine, preflight
from software_factory.errors import FactoryError
from software_factory.git import git, repository
from software_factory.store import atomic_json, read_json, runs_root
from tests.support import FactoryCase


class PreflightTests(FactoryCase):
    def report(self, fixture, **options):
        return preflight.inspect(str(fixture.repo), str(fixture.root / "absent parents/worktrees"), **options)

    def checks(self, report):
        return {item["name"]: item for item in report["checks"]}

    def files_snapshot(self, root):
        return {
            str(path.relative_to(root)): os.readlink(path) if path.is_symlink() else path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() or path.is_symlink()
        }

    def test_ready_with_unrelated_dirt_is_read_only_including_saved_receipts(self):
        f = self.fixture()
        saved = engine.start(f.options)
        (f.repo / "value.txt").write_text("unrelated user dirt")
        (f.repo / "unrelated.md").write_text("new user note")
        before = self.files_snapshot(f.root)
        inventory = git(f.repo, ["worktree", "list", "--porcelain"])
        git_module = importlib.import_module("software_factory.git")
        original = git_module.command
        observed = []

        def command(argv, *args, **kwargs):
            observed.append(list(argv))
            self.assertEqual(argv[0], "git")
            self.assertFalse(
                set(argv) & {"fetch", "push", "ls-remote", "auth", "add", "write-tree", "read-tree", "commit"}
            )
            return original(argv, *args, **kwargs)

        with (
            patch.object(git_module, "command", command),
            patch.object(engine, "start", side_effect=AssertionError("no allocation")),
        ):
            result = self.report(f)
        self.assertTrue(result["ready"], result)
        self.assertTrue(result["deliveryReady"])
        self.assertEqual(preflight.exit_code(result), 0)
        self.assertEqual(self.files_snapshot(f.root), before)
        self.assertEqual(git(f.repo, ["worktree", "list", "--porcelain"]), inventory)
        self.assertTrue(Path(saved["run"]).is_dir())
        self.assertFalse((f.root / "absent parents").exists())
        self.assertIn("Working tree contains changes", self.checks(result)["source-dirt"]["message"])
        self.assertTrue(any("--no-optional-locks" in argv and "status" in argv for argv in observed))

    def test_defaults_legacy_stack_and_absent_allocation_never_created(self):
        f = self.fixture()
        allocation = runs_root(repository(f.repo).common)
        self.assertFalse(allocation.exists())
        result = self.report(f)
        self.assertEqual(result["baseRef"], "main")
        self.assertEqual(result["base"], git(f.repo, ["rev-parse", "main"]).strip())
        self.assertEqual(result["endpoint"], "local")
        self.assertFalse(allocation.exists())
        git(f.repo, ["branch", "feature/lower"])
        result = self.report(f, base="feature/lower", branch="feature/new")
        self.assertTrue(result["ready"], result)
        self.assertEqual(result["baseRef"], "feature/lower")
        git(f.repo, ["branch", "-m", "main", "feature/original"])
        self.assertEqual(self.report(f)["baseRef"], "HEAD")
        self.assertTrue(self.report(f)["ready"])

    def test_independent_blockers_and_dependent_unknowns(self):
        f = self.fixture()
        bad_root = f.root / "not a directory"
        bad_root.write_text("user content")
        config = read_json(f.repo / ".factory.json")
        config["checks"] = [
            {"name": "missing", "argv": ["synthetic_missing_factory_tool"], "timeoutMs": 2000},
            {"name": "absolute", "argv": [sys.executable], "timeoutMs": 2000},
            {"name": "relative", "argv": ["./check-tool"], "timeoutMs": 2000},
        ]
        atomic_json(f.repo / ".factory.json", config)
        git(f.repo, ["commit", "-am", "synthetic missing tool"])
        result = preflight.inspect(str(f.repo), str(bad_root), base="missing-base", branch="bad-branch")
        checks = self.checks(result)
        for name in ("base", "branch", "worktree-root"):
            self.assertEqual(checks[name]["status"], "fail")
            self.assertTrue(checks[name]["remedy"])
        self.assertEqual(checks["configuration"]["status"], "pass")
        self.assertEqual(checks["committed-settings"]["status"], "unknown")
        self.assertEqual(checks["executable:missing"]["status"], "fail")
        self.assertEqual(checks["executable:absolute"]["status"], "pass")
        self.assertEqual(checks["executable:relative"]["status"], "unknown")
        self.assertEqual(preflight.exit_code(result), 2)
        result = self.report(f)
        self.assertEqual(self.checks(result)["executable:missing"]["status"], "fail")
        self.assertEqual(bad_root.read_text(), "user content")

    def test_settings_dirt_unsafe_rules_and_branch_collision_still_block_start(self):
        f = self.fixture()
        self.rule(f.repo, "instructions.md", "uncommitted rule")
        result = self.report(f, branch="feature/new")
        self.assertEqual(self.checks(result)["committed-settings"]["status"], "fail")
        with self.assertRaisesRegex(FactoryError, "committed"):
            engine.start(f.options)
        (f.repo / ".rules/instructions.md").unlink()
        git(f.repo, ["branch", "feature/taken"])
        result = self.report(f, branch="feature/taken")
        self.assertEqual(self.checks(result)["branch"]["status"], "fail")
        (f.repo / ".rules/unsafe.md").symlink_to(f.root / "missing")
        result = self.report(f)
        self.assertEqual(self.checks(result)["configuration"]["status"], "fail")
        self.assertEqual(self.checks(result)["committed-settings"]["status"], "unknown")

    def test_private_allocation_parent_shapes_are_known_blockers_with_no_writes(self):
        for part in ("factory", "factory/runs"):
            with self.subTest(part=part):
                f = self.fixture()
                target = Path(repository(f.repo).common) / part
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(b"retained evidence placeholder")
                before = self.files_snapshot(f.root)
                result = self.report(f)
                self.assertEqual(self.checks(result)["allocation-path"]["status"], "fail")
                self.assertEqual(preflight.exit_code(result), 2)
                self.assertEqual(self.files_snapshot(f.root), before)
                self.assertFalse((f.root / "absent parents").exists())

    def test_git_conflicts_and_submodule_entries_are_rejected(self):
        for kind in ("conflict", "submodule"):
            with self.subTest(kind=kind):
                f = self.fixture()
                if kind == "submodule":
                    head = git(f.repo, ["rev-parse", "HEAD"]).strip()
                    git(f.repo, ["update-index", "--add", "--cacheinfo", f"160000,{head},module"])
                else:
                    git(f.repo, ["checkout", "-b", "feature/other"])
                    (f.repo / "value.txt").write_text("other")
                    git(f.repo, ["commit", "-am", "synthetic other side"])
                    git(f.repo, ["checkout", "main"])
                    (f.repo / "value.txt").write_text("main side")
                    git(f.repo, ["commit", "-am", "synthetic main side"])
                    with self.assertRaises(FactoryError):
                        git(f.repo, ["merge", "feature/other"])
                before = self.files_snapshot(f.root)
                result = self.report(f)
                self.assertEqual(self.checks(result)["git-state"]["status"], "fail")
                self.assertEqual(self.files_snapshot(f.root), before)

    def test_absolute_and_selected_base_relative_executables_ignore_source_dirt(self):
        f = self.fixture()
        config = read_json(f.repo / ".factory.json")
        executable = f.repo / "check-tool"
        executable.write_text("#!/bin/sh\nexit 9\n")
        executable.chmod(0o755)
        config["checks"][0]["argv"] = ["./check-tool"]
        atomic_json(f.repo / ".factory.json", config)
        git(f.repo, ["add", "check-tool", ".factory.json"])
        git(f.repo, ["commit", "-m", "synthetic relative executable"])
        executable.unlink()
        self.assertTrue(self.report(f)["ready"])
        self.assertEqual(self.checks(self.report(f))["executable:behavior"]["status"], "pass")
        config["checks"][0]["argv"] = [str(f.root / "missing absolute")]
        atomic_json(f.repo / ".factory.json", config)
        git(f.repo, ["commit", "-am", "synthetic unavailable absolute executable"])
        self.assertEqual(self.checks(self.report(f))["executable:behavior"]["status"], "fail")

    def test_external_relative_tool_is_uncertain_and_original_start_accepts_it(self):
        f = self.fixture()
        config = read_json(f.repo / ".factory.json")
        config["checks"][0]["argv"] = ["../external-tool"]
        atomic_json(f.repo / ".factory.json", config)
        git(f.repo, ["commit", "-am", "synthetic external relative tool"])
        parent = Path(f.options.worktree_root)
        parent.mkdir(parents=True, exist_ok=True)
        tool = parent / "external-tool"
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(0o755)
        before = self.files_snapshot(f.root)
        result = preflight.inspect(str(f.repo), str(parent))
        self.assertEqual(self.checks(result)["executable:behavior"]["status"], "unknown")
        self.assertEqual(preflight.exit_code(result), 3)
        self.assertEqual(self.files_snapshot(f.root), before)
        started = engine.start(f.options)
        self.assertEqual(started["phase"], "plan")
        self.assertTrue((Path(started["worktree"]) / "../external-tool").is_file())

    def test_draft_delivery_prerequisites_do_not_block_otherwise_ready_start_or_leak_url(self):
        f = self.fixture("draft-pr")
        missing = self.report(f)
        self.assertTrue(missing["ready"])
        self.assertIs(missing["deliveryReady"], False)
        self.assertEqual(preflight.exit_code(missing), 0)
        git(f.repo, ["remote", "add", "origin", "https://synthetic-user:synthetic-secret@example.invalid/demo.git"])
        with patch.object(preflight.shutil, "which", return_value="/synthetic/bin/gh"):
            result = self.report(f)
        self.assertTrue(result["ready"])
        self.assertIsNone(result["deliveryReady"])
        self.assertNotIn("synthetic-secret", json.dumps(result))
        self.assertNotIn("synthetic-user", preflight.format_report(result))
        head = git(f.repo, ["rev-parse", "HEAD"]).strip()
        self.assertIs(self.report(f, base=head)["deliveryReady"], False)
        self.assertIs(self.report(f, base="HEAD")["deliveryReady"], False)
        with patch.object(preflight.shutil, "which", return_value=None):
            result = self.report(f)
        self.assertEqual(self.checks(result)["delivery-gh"]["status"], "fail")

    def test_access_and_infrastructure_unknown_reports_exit_three_not_success(self):
        f = self.fixture()
        with patch.object(preflight, "_path", side_effect=PermissionError("synthetic observation denied")):
            result = self.report(f)
        self.assertEqual(self.checks(result)["worktree-root"]["status"], "unknown")
        self.assertEqual(preflight.exit_code(result), 3)
        with patch.object(preflight.os, "access", return_value=False):
            result = self.report(f)
        self.assertEqual(self.checks(result)["worktree-root"]["status"], "fail")
        self.assertEqual(preflight.exit_code(result), 2)
        with patch.object(preflight, "read_project", side_effect=OSError("synthetic settings access error")):
            result = self.report(f)
        self.assertEqual(self.checks(result)["configuration"]["status"], "unknown")
        self.assertEqual(preflight.exit_code(result), 3)

    def test_cli_exact_contract_human_output_exit_and_no_tracebacks(self):
        f = self.fixture()
        args = ["preflight", "--repo", f.repo, "--worktree-root", f.root / "new worktrees"]
        output = self.cli(*args, "--json")
        self.assertEqual(output.returncode, 0, output.stderr)
        result = json.loads(output.stdout)
        self.assertEqual(
            set(result),
            {"version", "repo", "baseRef", "base", "endpoint", "ready", "deliveryReady", "checks", "limitations"},
        )
        for check in result["checks"]:
            self.assertEqual(set(check), {"name", "scope", "status", "message", "remedy"})
        self.assertIn("Start ready: True", self.cli(*args).stdout)
        blocked = self.cli(*args, "--branch", "invalid", "--json")
        self.assertEqual(blocked.returncode, 2)
        self.assertFalse(json.loads(blocked.stdout)["ready"])
        for args in (("preflight",), ("preflight", "--repo", f.root, "--worktree-root", f.root / "new")):
            output = self.cli(*args, "--json")
            self.assertEqual(output.returncode, 2)
            self.assertNotIn("Traceback", output.stderr)
        self.assertIn("preflight", self.cli("--help").stdout)

    def test_cyclic_root_is_invalid_without_traceback_on_supported_python_versions(self):
        f = self.fixture()
        first, second = f.root / "loop one", f.root / "loop two"
        first.symlink_to(second)
        second.symlink_to(first)
        output = self.cli("preflight", "--repo", f.repo, "--worktree-root", first, "--json")
        self.assertEqual(output.returncode, 2, output.stderr)
        self.assertEqual(self.checks(json.loads(output.stdout))["worktree-root"]["status"], "fail")
        self.assertNotIn("Traceback", output.stderr)
