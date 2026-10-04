"""Real-repository scaffold behavior; synthetic faults never alter production receipts."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

from software_factory import engine, prd
from software_factory.errors import FactoryError
from software_factory.git import git, repository
from software_factory.store import runs_root
from tests.support import FactoryCase


class PrdTests(FactoryCase):
    def invariant(self, repo):
        return (
            git(repo, ["rev-parse", "HEAD"]),
            git(repo, ["write-tree"]),
            git(repo, ["branch", "--list"]),
            git(repo, ["worktree", "list", "--porcelain"]),
            (repo / ".factory.json").read_bytes() if (repo / ".factory.json").exists() else None,
            runs_root(repository(repo).common).exists(),
        )

    def test_cli_setup_root_nested_repeat_and_custom_bytes(self):
        f = self.fixture()
        nested = f.repo / "nested folder"
        nested.mkdir()
        before = self.invariant(f.repo)
        output = self.cli("prd-init", "--repo", nested, "--json")
        self.assertEqual(output.returncode, 0, output.stderr)
        result = json.loads(output.stdout)
        self.assertEqual(set(result), {"repo", "prd", "created", "skipped", "next"})
        self.assertEqual(result["repo"], str(f.repo))
        self.assertEqual(result["created"], ["prd/README.md", "prd/_template.md"])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(self.invariant(f.repo), before)
        index = f.repo / "prd/README.md"
        index.write_bytes(b"custom bytes\xff\n")
        (f.repo / "prd/unrelated.md").write_text("user requirements")
        status = git(f.repo, ["status", "--porcelain"])
        human = self.cli("prd-init", "--repo", f.repo)
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("Skipped: prd/README.md", human.stdout)
        self.assertNotIn("Created:", human.stdout)
        self.assertEqual(index.read_bytes(), b"custom bytes\xff\n")
        self.assertEqual((f.repo / "prd/unrelated.md").read_text(), "user requirements")
        self.assertEqual(git(f.repo, ["status", "--porcelain"]), status)
        self.assertEqual(self.invariant(f.repo), before)
        result = engine.prd_init(str(f.repo))
        self.assertEqual(result["created"], [])
        self.assertEqual(result["skipped"], ["prd/README.md", "prd/_template.md"])

    def test_standalone_linked_worktree_only_changes_selected_root(self):
        f = self.fixture()
        linked = f.root / "linked worktree"
        git(f.repo, ["worktree", "add", "-b", "feature/prd", str(linked)])
        before = self.invariant(f.repo)
        result = engine.prd_init(str(linked))
        self.assertEqual(result["repo"], str(linked))
        self.assertFalse((f.repo / "prd").exists())
        self.assertEqual(self.invariant(f.repo), before)
        self.assertEqual(git(linked, ["status", "--porcelain"]).strip(), "?? prd/")
        (linked / ".factory.json").unlink()
        self.assertEqual(engine.prd_init(str(linked))["created"], [])
        self.assertFalse((linked / ".factory.json").exists())
        self.assertFalse((linked / ".rules").exists())

    def test_partial_setup_preserves_customized_file(self):
        f = self.fixture()
        directory = f.repo / "prd"
        directory.mkdir()
        (directory / "_template.md").write_text("custom template")
        result = engine.prd_init(str(f.repo))
        self.assertEqual(result["created"], ["prd/README.md"])
        self.assertEqual(result["skipped"], ["prd/_template.md"])
        self.assertEqual((directory / "_template.md").read_text(), "custom template")

    def test_unsafe_paths_and_invalid_resources_never_write_peers_or_config(self):
        for kind in ("directory-symlink", "directory-file", "file-symlink", "file-directory"):
            with self.subTest(kind=kind):
                f = self.fixture()
                (f.repo / ".factory.json").unlink()
                directory = f.repo / "prd"
                if kind == "directory-symlink":
                    directory.symlink_to(f.root)
                elif kind == "directory-file":
                    directory.write_text("user file")
                else:
                    directory.mkdir()
                    bad = directory / "_template.md"
                    if kind == "file-symlink":
                        bad.symlink_to(f.root / "absent")
                    else:
                        bad.mkdir()
                before = git(f.repo, ["status", "--porcelain"])
                with self.assertRaises(FactoryError) as failure:
                    engine.init(str(f.repo), [{"name": "test", "argv": [sys.executable], "timeoutMs": 100}])
                self.assertEqual(failure.exception.code, "invalid")
                self.assertFalse((f.repo / ".rules").exists())
                self.assertEqual(git(f.repo, ["status", "--porcelain"]), before)
                with self.assertRaises(FactoryError):
                    engine.prd_init(str(f.repo))
        f = self.fixture()
        (f.repo / ".factory.json").unlink()
        with patch.object(prd, "files", side_effect=FileNotFoundError("synthetic missing resource")):
            with self.assertRaises(FactoryError) as failure:
                engine.init(str(f.repo), [{"name": "test", "argv": [sys.executable], "timeoutMs": 100}])
        self.assertEqual(failure.exception.code, "infrastructure")
        self.assertFalse((f.repo / ".rules").exists())
        self.assertFalse((f.repo / "prd").exists())

    def test_init_refusal_and_invalid_checks_precede_all_writes(self):
        f = self.fixture()
        with self.assertRaisesRegex(FactoryError, "already exists"):
            engine.init(str(f.repo), [])
        self.assertFalse((f.repo / "prd").exists())
        (f.repo / ".factory.json").unlink()
        with self.assertRaisesRegex(FactoryError, "at least one"):
            engine.init(str(f.repo), [])
        self.assertFalse((f.repo / "prd").exists())
        self.assertFalse((f.repo / ".rules").exists())
        self.rule(f.repo, "factory.md", "custom instructions without config")
        with self.assertRaisesRegex(FactoryError, "already exists"):
            engine.init(str(f.repo), [{"name": "test", "argv": [sys.executable], "timeoutMs": 100}])
        self.assertFalse((f.repo / "prd").exists())
        self.assertEqual((f.repo / ".rules/factory.md").read_text(), "custom instructions without config")

    def test_exclusive_create_collision_preserves_regular_and_rejects_unsafe(self):
        original = Path.open
        for unsafe in (False, True):
            with self.subTest(unsafe=unsafe):
                f = self.fixture()
                target = f.repo / "prd/README.md"

                def collide(path, mode="r", *args, **kwargs):
                    if path == target and mode == "x":
                        if unsafe:
                            path.symlink_to(f.root / "missing")
                        else:
                            path.write_bytes(b"concurrent custom")
                    return original(path, mode, *args, **kwargs)

                with patch.object(Path, "open", collide):
                    if unsafe:
                        with self.assertRaises(FactoryError) as failure:
                            engine.prd_init(str(f.repo))
                        self.assertEqual(failure.exception.code, "invalid")
                        self.assertFalse((f.repo / "prd/_template.md").exists())
                    else:
                        result = engine.prd_init(str(f.repo))
                        self.assertEqual(result["skipped"], ["prd/README.md"])
                        self.assertEqual(result["created"], ["prd/_template.md"])
                        self.assertEqual(target.read_bytes(), b"concurrent custom")

    def test_unsafe_final_path_appearing_after_validation_is_not_reported_skipped(self):
        for kind in ("symlink", "directory"):
            with self.subTest(kind=kind):
                f = self.fixture()
                scaffold = prd.prepare(f.repo)
                original = prd.validate_paths
                target = f.repo / "prd/_template.md"

                def change_after_validation(root):
                    original(root)
                    # Simulate a local race at the validation/creation boundary.
                    if (root / "prd/README.md").exists() and not target.exists():
                        if kind == "symlink":
                            target.symlink_to(f.root / "missing")
                        else:
                            target.mkdir()

                with patch.object(prd, "validate_paths", change_after_validation):
                    with self.assertRaises(FactoryError) as failure:
                        prd.create(scaffold)
                self.assertEqual(failure.exception.code, "invalid")
                self.assertIn("prd/_template.md", str(failure.exception))
                self.assertIn("prd/README.md", str(failure.exception))
                self.assertTrue(target.is_symlink() if kind == "symlink" else target.is_dir())

    def test_open_failure_reports_prior_config_and_created_files_then_fills_missing(self):
        f = self.fixture()
        (f.repo / ".factory.json").unlink()
        original = Path.open

        def fail(path, mode="r", *args, **kwargs):
            if path.name == "_template.md" and mode == "x":
                raise PermissionError("synthetic denied write")
            return original(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail):
            with self.assertRaises(FactoryError) as failure:
                engine.init(str(f.repo), [{"name": "test", "argv": [sys.executable], "timeoutMs": 100}])
        self.assertEqual(failure.exception.code, "infrastructure")
        self.assertIn(".rules/factory.md", str(failure.exception))
        self.assertIn("prd/README.md", str(failure.exception))
        preserved = (f.repo / "prd/README.md").read_bytes()
        result = engine.prd_init(str(f.repo))
        self.assertEqual(result["created"], ["prd/_template.md"])
        self.assertEqual((f.repo / "prd/README.md").read_bytes(), preserved)

    def test_write_and_close_failures_report_created_incomplete_and_preserve_bytes(self):
        original = Path.open
        for destination in ("prd/README.md", ".rules/factory.md"):
            for failure_kind in ("write", "close"):
                with self.subTest(destination=destination, failure=failure_kind):
                    f = self.fixture()
                    (f.repo / ".factory.json").unlink()
                    target = f.repo / destination

                    class BrokenStream:
                        def __init__(self, stream):
                            self.stream = stream

                        def __enter__(self):
                            return self

                        def write(self, content):
                            self.stream.write("partial")
                            if failure_kind == "write":
                                raise OSError("synthetic write failure")

                        def __exit__(self, *args):
                            self.stream.close()
                            if failure_kind == "close":
                                raise OSError("synthetic close failure")

                    def fail(path, mode="r", *args, **kwargs):
                        stream = original(path, mode, *args, **kwargs)
                        return BrokenStream(stream) if path == target and mode == "x" else stream

                    with patch.object(Path, "open", fail):
                        with self.assertRaises(FactoryError) as failure:
                            engine.init(str(f.repo), [{"name": "test", "argv": [sys.executable], "timeoutMs": 100}])
                    self.assertEqual(failure.exception.code, "infrastructure")
                    self.assertIn(destination, str(failure.exception))
                    self.assertIn("may be incomplete", str(failure.exception))
                    self.assertEqual(target.read_text(), "partial")
                    engine.prd_init(str(f.repo))
                    self.assertEqual(target.read_text(), "partial")
                    self.assertTrue((f.repo / "prd/_template.md").is_file())

    def test_resources_complete_and_cli_errors_are_structured(self):
        f = self.fixture()
        result = engine.prd_init(str(f.repo))
        template = (f.repo / "prd/_template.md").read_text()
        for heading in ("Problem and users", "Desired outcome", "Scope", "Non-goals", "User workflow", "Requirements", "Acceptance criteria", "Constraints and compatibility", "Dependencies", "Verification", "Risks and open questions", "Delivery and follow-up"):
            self.assertIn(f"## {heading}", template)
        self.assertIn("Status: draft", template)
        guidance = (f.repo / "prd/README.md").read_text()
        for text in ("draft", "ready", "in-progress", "delivered", "--task-file", "--criterion", "self-contained", "not recursively loaded", "reviewed private plan"):
            self.assertIn(text, guidance)
        self.assertEqual(result["created"], ["prd/README.md", "prd/_template.md"])
        self.assertIn("prd-init", self.cli("--help").stdout)
        for args in (("prd-init",), ("prd-init", "--repo", f.root)):
            output = self.cli(*args, "--json")
            self.assertEqual(output.returncode, 2 if len(args) == 1 else 3, output.stderr)
            self.assertIn(json.loads(output.stderr)["code"], ("invalid", "infrastructure"))
            self.assertNotIn("Traceback", output.stderr)
