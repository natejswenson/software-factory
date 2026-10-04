"""Bundles capture exact inputs, never produce reviews or mutate the task."""

import io
import json
import os
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from software_factory import cli, engine, review_context
from software_factory.errors import FactoryError
from software_factory.git import git, git_bytes
from software_factory.store import atomic_json, fingerprint, locked, read_run
from tests.support import FactoryCase


class ReviewContextTests(FactoryCase):
    def bundle(self, run, stage="code", **options):
        return review_context.collect(read_run(run["run"]), stage=stage, **options)

    def test_plan_full_exact_values_and_explicit_attributed_inputs(self):
        f = self.fixture()
        (f.repo / "AGENTS.md").write_text("Root guidance ✓\n")
        self.rule(f.repo, "project.md", "Current rule with full content")
        git(f.repo, ["add", "."])
        git(f.repo, ["commit", "-m", "synthetic bundle guidance"])
        run = self.planned(f)
        host = f.root / "host.md"
        host.write_text("Explicit session data `$(literal)` ✓\n")
        supplement = f.root / "proof.md"
        supplement.write_text("Synthetic supplemental observation\n")
        state = read_run(run["run"])
        before = (Path(run["run"]) / "state.json").read_bytes()
        bundle = self.bundle(run, "plan", instructions_files=[str(host)], supplements=[str(supplement)])
        self.assertEqual(
            set(bundle),
            {
                "version",
                "id",
                "stage",
                "worktree",
                "task",
                "criteria",
                "plan",
                "config",
                "rules",
                "instructions",
                "supplements",
                "context",
                "evidence",
                "verification",
                "diff",
                "limitations",
                "complete",
            },
        )
        self.assertTrue(bundle["complete"])
        self.assertIsNone(bundle["evidence"])
        self.assertIsNone(bundle["verification"])
        self.assertIsNone(bundle["diff"])
        self.assertEqual(bundle["task"], state["task"])
        self.assertEqual(bundle["criteria"], state["criteria"])
        self.assertEqual(bundle["context"], engine.context(state))
        self.assertEqual(bundle["rules"], engine.task_rules(state))
        self.assertEqual(bundle["config"], state["config"])
        raw = (Path(run["run"]) / "plan.md").read_bytes()
        self.assertEqual(
            bundle["plan"],
            {"path": str(Path(run["run"]) / "plan.md"), "content": raw.decode(), "hash": fingerprint(raw)},
        )
        self.assertEqual([x["kind"] for x in bundle["instructions"]], ["repository", "explicit-instructions"])
        self.assertEqual(bundle["instructions"][1]["content"], host.read_text())
        self.assertEqual(bundle["instructions"][1]["sha256"], fingerprint(host.read_bytes()))
        self.assertEqual(bundle["supplements"][0]["path"], str(supplement))
        self.assertEqual(bundle["supplements"][0]["content"], supplement.read_text())
        self.assertTrue(any("conversation" in x for x in bundle["limitations"]))
        self.assertTrue(any("independence" in x for x in bundle["limitations"]))
        self.assertEqual(before, (Path(run["run"]) / "state.json").read_bytes())
        self.assertNotIn("verdict", bundle)
        self.assertFalse((Path(run["run"]) / "review-context.json").exists())

    def test_code_complete_binary_diff_scopes_and_frozen_checks(self):
        f = self.fixture()
        for directory in ("", "nested", "nested/deep", "unrelated"):
            p = f.repo / directory
            p.mkdir(exist_ok=True, parents=True)
            (p / "AGENTS.md").write_text(f"Scoped {directory or 'root'}\n")
        git(f.repo, ["add", "."])
        git(f.repo, ["commit", "-m", "synthetic scopes"])
        run = self.planned(f)
        root = Path(run["worktree"])
        (root / "value.txt").write_text("new\n")
        (root / "nested/deep/new.bin").write_bytes(bytes(range(256)))
        (root / "nested/deep/link").symlink_to("../../value.txt")
        (root / "nested/tool").write_text("#!/bin/sh\nexit 0\n")
        (root / "nested/tool").chmod(0o755)
        (root / "ignored-not-in-bundle").write_text("untracked ignored")
        config = json.loads((root / ".factory.json").read_text())
        config["checks"][0]["argv"] = ["synthetic-do-not-execute"]
        atomic_json(root / ".factory.json", config)
        run = engine.verify(run["run"])
        self.assertTrue(run["verification"]["passed"])
        b = self.bundle(run)
        state = read_run(run["run"])
        e = engine.check_verified(state)
        self.assertEqual(b["evidence"], e)
        self.assertEqual(b["context"], engine.context(state))
        self.assertEqual(b["verification"], state["verification"])
        self.assertEqual(b["config"], state["config"])
        self.assertNotEqual(b["config"], config)
        expected = git_bytes(
            root,
            [
                "diff",
                "--binary",
                "--full-index",
                "--no-renames",
                "--no-ext-diff",
                "--no-textconv",
                state["base"],
                e["tree"],
                "--",
            ],
        ).decode("utf-8", "surrogateescape")
        self.assertEqual(b["diff"]["patch"], expected)
        self.assertEqual(b["diff"]["paths"], e["paths"])
        self.assertTrue(b["diff"]["binary"])
        self.assertEqual(
            [Path(x["path"]).relative_to(root).as_posix() for x in b["instructions"]],
            ["AGENTS.md", "nested/AGENTS.md", "nested/deep/AGENTS.md"],
        )
        self.assertNotIn("ignored-not-in-bundle", b["diff"]["paths"])
        self.assertEqual(
            [Path(x["path"]).relative_to(root).as_posix() for x in self.bundle(run, "plan")["instructions"]],
            ["AGENTS.md"],
        )

    def test_missing_empty_plan_failed_stale_and_blocked_runs_refuse(self):
        f = self.fixture()
        run = engine.start(f.options)
        with self.assertRaises(FactoryError):
            self.bundle(run, "plan")
        (Path(run["run"]) / "plan.md").write_text("   \n")
        with self.assertRaises(FactoryError):
            self.bundle(run, "plan")
        run = self.planned(f)
        engine.verify(run["run"])
        with self.assertRaisesRegex(FactoryError, "verification"):
            self.bundle(run)
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        run = engine.verify(run["run"])
        self.bundle(run)
        (Path(run["worktree"]) / "extra").write_text("drift")
        with self.assertRaisesRegex(FactoryError, "verification"):
            self.bundle(run)
        state = read_run(run["run"])
        state["phase"] = "blocked"
        atomic_json(Path(run["run"]) / "state.json", state)
        with self.assertRaisesRegex(FactoryError, "Repair limit"):
            self.bundle(run, "plan")

    def test_unsafe_missing_encoding_and_product_limits_never_emit_partial(self):
        f = self.fixture()
        run = self.planned(f)
        file = f.root / "input.md"
        for value in ("missing", "directory", "symlink", "utf8", "oversized"):
            with self.subTest(value=value):
                file.unlink(missing_ok=True)
                if value == "directory":
                    file.mkdir()
                elif value == "symlink":
                    file.symlink_to(Path(run["run"]) / "plan.md")
                elif value == "utf8":
                    file.write_bytes(b"\xff")
                elif value == "oversized":
                    file.write_bytes(b"a" * (review_context.MAX_FILE_BYTES + 1))
                with self.assertRaises(FactoryError):
                    self.bundle(run, "plan", supplements=[str(file)])
                if value == "directory":
                    file.rmdir()
        file.unlink(missing_ok=True)
        file.write_text("regular")
        files = []
        for i in range(9):
            p = f.root / f"input-{i}.md"
            p.write_bytes(b"a" * review_context.MAX_FILE_BYTES)
            files.append(str(p))
        with self.assertRaisesRegex(FactoryError, "aggregate"):
            self.bundle(run, "plan", supplements=files)
        with patch.object(review_context, "MAX_BUNDLE_BYTES", 100), self.assertRaisesRegex(FactoryError, "bundle"):
            self.bundle(run, "plan")
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        engine.verify(run["run"])
        with patch.object(review_context, "MAX_DIFF_BYTES", 16), self.assertRaisesRegex(FactoryError, "diff"):
            self.bundle(run)
        self.assertEqual(read_run(run["run"])["failures"], 0)

    def test_live_or_foreign_owner_prevents_any_capture(self):
        run = self.checked(self.fixture())
        with locked(run["run"]):
            owner = Path(run["run"]) / "lock/owner.json"
            raw = json.loads(owner.read_text())
            atomic_json(owner, {**raw, "host": "synthetic-other-host", "pid": os.getpid()})
            with (
                patch.object(engine, "context", side_effect=AssertionError("locked")),
                patch.object(engine, "check_verified", side_effect=AssertionError("locked")),
            ):
                with self.assertRaisesRegex(FactoryError, "owns"):
                    self.bundle(run)
            atomic_json(owner, raw)
            output = self.cli("review-context", "--run", run["run"], "--stage", "code", "--json")
            self.assertEqual(output.returncode, 2)
            self.assertIn("locked", output.stderr)

    def test_input_edit_and_new_automatic_instruction_during_capture_reject(self):
        f = self.fixture()
        run = self.checked(f)
        root = Path(run["worktree"])
        explicit = f.root / "host.md"
        explicit.write_text("Before")
        original = review_context.read_input
        changed = False

        def moving(path, kind, *, required=True):
            nonlocal changed
            value = original(path, kind, required=required)
            if Path(path) == explicit and not changed:
                explicit.write_text("After")
                changed = True
            return value

        with patch.object(review_context, "read_input", moving), self.assertRaisesRegex(FactoryError, "changed"):
            self.bundle(run, instructions_files=[str(explicit)])
        original_git = review_context.git_bytes

        def new_instruction(*args, **kwargs):
            output = original_git(*args, **kwargs)
            (root / "AGENTS.md").write_text("New guidance during capture")
            return output

        with (
            patch.object(review_context, "git_bytes", new_instruction),
            self.assertRaisesRegex(FactoryError, "changed"),
        ):
            self.bundle(run)

    def test_run_handoff_drift_and_missing_objects_are_explicit(self):
        run = self.checked(self.fixture())
        state = read_run(run["run"])
        new = {**state, "failures": 1}
        atomic_json(Path(run["run"]) / "state.json", new)
        with self.assertRaisesRegex(FactoryError, "changed"):
            review_context.collect(state, stage="code")
        with patch.object(
            review_context, "git_bytes", side_effect=FactoryError("Synthetic missing object", "infrastructure")
        ):
            output = self.bundle_error(run)
            self.assertEqual(output.code, "infrastructure")

    def bundle_error(self, run):
        try:
            self.bundle(run)
        except FactoryError as error:
            return error
        self.fail("Missing object must not yield a complete bundle")

    def test_legacy_exact_context_readonly_and_stale_review_submission(self):
        run = self.checked(self.fixture())
        state = read_run(run["run"])
        state.pop("rules")
        state["planReview"]["context"].pop("rules")
        state["verification"]["evidence"].pop("rules")
        atomic_json(Path(run["run"]) / "state.json", state)
        before = (Path(run["run"]) / "state.json").read_bytes()
        index = git(run["worktree"], ["write-tree"])
        head = git(run["worktree"], ["rev-parse", "HEAD"])
        status = git(run["worktree"], ["status", "--porcelain"])
        b = self.bundle(run)
        self.assertEqual(b["rules"], {"enabled": False, "files": [], "hash": None, "snapshot": None})
        self.assertNotIn("rules", b["context"])
        self.assertNotIn("rules", b["evidence"])
        self.assertEqual(before, (Path(run["run"]) / "state.json").read_bytes())
        self.assertEqual(index, git(run["worktree"], ["write-tree"]))
        self.assertEqual(head, git(run["worktree"], ["rev-parse", "HEAD"]))
        self.assertEqual(status, git(run["worktree"], ["status", "--porcelain"]))
        (Path(run["worktree"]) / "extra").write_text("later edit")
        review = {
            "reviewer": "synthetic fixture",
            "verdict": "pass",
            "findings": [],
            "evidence": b["evidence"],
            "criteria": [{"id": "AC1", "passed": True, "evidence": "synthetic fixture"}],
        }
        with self.assertRaises(FactoryError):
            engine.submit_review(run["run"], self.json_file(run["run"], "synthetic-stale.json", review))
        self.assertEqual(before, (Path(run["run"]) / "state.json").read_bytes())

    def test_non_utf8_patch_bytes_are_lossless_in_json_and_readable_as_escapes(self):
        run = self.planned(self.fixture())
        root = Path(run["worktree"])
        (root / "value.txt").write_text("new\n")
        (root / "non-utf8.txt").write_bytes(b"synthetic byte: \xff\n")
        engine.verify(run["run"])
        bundle = self.bundle(run)
        raw = git_bytes(
            root,
            [
                "diff",
                "--binary",
                "--full-index",
                "--no-renames",
                "--no-ext-diff",
                "--no-textconv",
                bundle["diff"]["base"],
                bundle["diff"]["tree"],
                "--",
            ],
        )
        restored = json.loads(json.dumps(bundle, ensure_ascii=True))["diff"]["patch"].encode("utf-8", "surrogateescape")
        self.assertEqual(restored, raw)
        output = self.cli("review-context", "--run", run["run"], "--stage", "code")
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn(r"\udcff", output.stdout)
        with patch.object(review_context, "MAX_BUNDLE_BYTES", 100), self.assertRaises(FactoryError):
            review_context.format_bundle(bundle)

    def test_unavailable_input_metadata_is_infrastructure_without_partial_output(self):
        f = self.fixture()
        run = self.checked(f)
        explicit = f.root / "session.md"
        explicit.write_text("Synthetic directions")
        original = Path.lstat

        def denied(path, *args, **kwargs):
            if path == explicit:
                raise PermissionError("Synthetic metadata access denied")
            return original(path, *args, **kwargs)

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(Path, "lstat", denied), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(
                [
                    "review-context",
                    "--run",
                    run["run"],
                    "--stage",
                    "code",
                    "--instructions-file",
                    str(explicit),
                    "--json",
                ]
            )
        self.assertEqual(code, 3)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(json.loads(stderr.getvalue())["code"], "infrastructure")
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_automatic_ancestry_never_imports_outside_instructions_but_explicit_paths_work(self):
        f = self.fixture()
        nested = f.repo / "nested"
        nested.mkdir()
        (nested / "file.txt").write_text("Tracked old scope")
        git(f.repo, ["add", "."])
        git(f.repo, ["commit", "-m", "synthetic tracked nested scope"])
        run = self.planned(f)
        root = Path(run["worktree"])
        outside = f.root / "outside"
        outside.mkdir()
        (outside / "AGENTS.md").write_text("Synthetic external private guidance")
        shutil.rmtree(root / "nested")
        (root / "nested").symlink_to(outside, target_is_directory=True)
        (root / "value.txt").write_text("new\n")
        engine.verify(run["run"])
        original = review_context._from_descriptor

        def forbid_external(descriptor, path, kind):
            if kind == "repository" and path == root / "nested/AGENTS.md":
                os.close(descriptor)
                raise AssertionError("Outside automatic input was opened")
            return original(descriptor, path, kind)

        with patch.object(review_context, "_from_descriptor", forbid_external):
            with self.assertRaisesRegex(FactoryError, "ancestry"):
                self.bundle(run)
        explicit = review_context.read_input(root / "nested/AGENTS.md", "explicit-instructions")
        self.assertEqual(explicit["content"], (outside / "AGENTS.md").read_text())
        self.assertEqual(explicit["kind"], "explicit-instructions")

    def test_automatic_ancestor_change_after_capture_rejects_even_for_ignored_paths(self):
        f = self.fixture()
        nested = f.repo / "nested"
        nested.mkdir()
        (nested / "file.txt").write_text("Tracked scoped file")
        (f.repo / ".gitignore").write_text("AGENTS.md\n")
        git(f.repo, ["add", "."])
        git(f.repo, ["commit", "-m", "synthetic ignored guidance scope"])
        run = self.planned(f)
        root = Path(run["worktree"])
        (root / "value.txt").write_text("new\n")
        (root / "nested/file.txt").unlink()
        engine.verify(run["run"])
        outside = f.root / "outside"
        outside.mkdir()
        (outside / "AGENTS.md").write_text("Synthetic outside instruction")
        original = review_context.git_bytes

        def replace_after_capture(*args, **kwargs):
            result = original(*args, **kwargs)
            (root / "nested").rmdir()
            (root / "nested").symlink_to(outside, target_is_directory=True)
            return result

        with patch.object(review_context, "git_bytes", replace_after_capture):
            with self.assertRaisesRegex(FactoryError, "changed"):
                self.bundle(run)

    def test_directory_swap_between_metadata_and_open_cannot_read_outside_scope(self):
        f = self.fixture()
        (f.repo / "nested").mkdir()
        (f.repo / "nested/file.txt").write_text("Tracked scope")
        git(f.repo, ["add", "."])
        git(f.repo, ["commit", "-m", "synthetic directory race scope"])
        run = self.planned(f)
        root = Path(run["worktree"])
        (root / "value.txt").write_text("new\n")
        (root / "nested/file.txt").unlink()
        engine.verify(run["run"])
        outside = f.root / "outside"
        outside.mkdir()
        (outside / "AGENTS.md").write_text("Synthetic outside guidance")
        original = os.open
        changed = False

        def swap(path, flags, *args, **kwargs):
            nonlocal changed
            if path == "nested" and flags & os.O_DIRECTORY and not changed:
                (root / "nested").rmdir()
                (root / "nested").symlink_to(outside, target_is_directory=True)
                changed = True
            return original(path, flags, *args, **kwargs)

        with patch.object(os, "open", swap):
            with self.assertRaisesRegex(FactoryError, "ancestry"):
                self.bundle(run)
        self.assertTrue(changed)

    def test_cli_json_human_help_and_invalid_stage(self):
        run = self.checked(self.fixture())
        out = self.cli("review-context", "--run", run["run"], "--stage", "code", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(json.loads(out.stdout)["complete"])
        out = self.cli("review-context", "--run", run["run"], "--stage", "plan")
        self.assertIn("## Task", out.stdout)
        self.assertIn("## Plan", out.stdout)
        for stage in ("", "unknown"):
            out = self.cli("review-context", "--run", run["run"], "--stage", stage, "--json")
            self.assertEqual(out.returncode, 2)
            self.assertNotIn("Traceback", out.stderr)
        self.assertIn("review-context", self.cli("--help").stdout)
