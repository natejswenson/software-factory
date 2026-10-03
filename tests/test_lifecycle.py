"""Behavioral parity for intake, evidence gates and interruption recovery."""

import os
import shutil
import socket
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from software_factory import engine
from software_factory.checks import validate_config
from software_factory.delivery import deliver
from software_factory.errors import FactoryError
from software_factory.git import git, snapshot
from software_factory.store import atomic_json, list_runs, locked, read_json, read_run
from tests.support import FactoryCase


class LifecycleTests(FactoryCase):
    def test_file_type_transitions_stage_exact_reviewed_tree(self):
        for kind in ("directory-symlink", "file-directory"):
            for already_staged in (False, True):
                with self.subTest(kind=kind, already_staged=already_staged):
                    f = self.fixture()
                    original = f.repo / "replacement"
                    if kind == "directory-symlink":
                        original.mkdir()
                        (original / "child.md").write_text("synthetic old skill")
                    else:
                        original.write_text("old file")
                    git(f.repo, ["add", "--", "replacement"])
                    git(f.repo, ["commit", "-m", "file type baseline"])
                    run = self.planned(f)
                    root = Path(run["worktree"])
                    (root / "value.txt").write_text("new\n")
                    replacement = root / "replacement"
                    if kind == "directory-symlink":
                        shutil.rmtree(replacement)
                        replacement.symlink_to("value.txt")
                    else:
                        replacement.unlink()
                        replacement.mkdir()
                        (replacement / "child.md").write_text("new file")
                    if already_staged:
                        git(root, ["add", "-A", "--", "."])
                    checked = engine.verify(run["run"])
                    self.review(checked)
                    result = deliver(run["run"])
                    self.assertEqual(result["phase"], "done")
                    self.assertEqual(result["delivery"]["tree"], checked["next"]["evidence"]["tree"])
                    self.assertEqual(git(root, ["status", "--porcelain"]).strip(), "")

    def test_dirty_source_idempotent_local_lifecycle(self):
        f = self.fixture()
        (f.repo / "value.txt").write_text("user dirty change\n")
        initial = engine.start(f.options)
        self.assertEqual(initial["next"]["action"], "plan")
        self.assertEqual(engine.start(f.options)["id"], initial["id"])
        self.assertEqual(engine.resume(initial["run"])["id"], initial["id"])
        run = self.reviewed(f)
        result = deliver(run["run"])
        self.assertEqual(result["phase"], "done")
        self.assertEqual(result["delivery"]["endpoint"], "local")
        self.assertEqual(git(result["worktree"], ["rev-parse", "HEAD^{tree}"]).strip(), result["delivery"]["tree"])
        self.assertEqual(git(result["worktree"], ["status", "--porcelain"]).strip(), "")
        self.assertEqual((f.repo / "value.txt").read_text(), "user dirty change\n")
        self.assertEqual(deliver(run["run"])["delivery"]["commit"], result["delivery"]["commit"])
        self.assertEqual(len(list_runs(read_run(run["run"])["common"])), 1)

    def test_missing_criteria_checks_and_uncommitted_config(self):
        f = self.fixture()
        with self.assertRaisesRegex(FactoryError, "criterion"):
            engine.start(replace(f.options, criteria=[]))
        with self.assertRaisesRegex(FactoryError, "at least one"):
            validate_config({"version": 1, "endpoint": "local", "checks": []})
        config = read_json(f.repo / ".factory.json")
        config["checks"][0]["timeoutMs"] = 1500
        atomic_json(f.repo / ".factory.json", config)
        with self.assertRaisesRegex(FactoryError, "committed"):
            engine.start(f.options)
        (f.repo / ".factory.json").write_text("{}")
        with self.assertRaisesRegex(FactoryError, "version 1"):
            engine.start(f.options)

    def test_default_draft_and_stack_base(self):
        f = self.fixture("draft-pr")
        git(f.repo, ["branch", "feature/lower"])
        run = engine.start(replace(f.options, base="feature/lower"))
        self.assertEqual(run["endpoint"], "draft-pr")
        self.assertEqual(run["base"], "feature/lower")
        main = engine.start(f.options)
        self.assertNotEqual(run["id"], main["id"])
        self.assertEqual(main["base"], "main")

    def test_plan_rejection_stale_and_key_order(self):
        run = self.planned(self.fixture())
        (Path(run["run"]) / "plan.md").write_text("# Revised plan\nDifferent scope\n")
        with self.assertRaisesRegex(FactoryError, "plan review"):
            engine.verify(run["run"])
        status = engine.describe(read_run(run["run"]))
        self.assertEqual(status["next"]["action"], "plan-review")
        ctx = dict(reversed(list(status["next"]["context"].items())))
        rejected = engine.submit_plan_review(
            run["run"],
            self.json_file(
                run["run"],
                "reject.json",
                {
                    "reviewer": "synthetic fixture",
                    "context": ctx,
                    "verdict": "fail",
                    "findings": [{"severity": "major", "location": "plan", "issue": "Missing acceptance coverage"}],
                },
            ),
        )
        self.assertEqual(rejected["next"]["action"], "plan")
        self.assertEqual(rejected["failures"], 1)

    def test_failed_check_recorded_then_repaired(self):
        run = self.planned(self.fixture())
        failed = engine.verify(run["run"])
        self.assertFalse(failed["verification"]["passed"])
        self.assertEqual(failed["failures"], 1)
        self.assertTrue((Path(run["run"]) / "verification-1.json").exists())
        with self.assertRaisesRegex(FactoryError, "current verification"):
            deliver(run["run"])
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        self.assertEqual(engine.verify(run["run"])["next"]["action"], "review")
        self.assertTrue((Path(run["run"]) / "verification-1.json").exists())

    def test_three_failures_and_explicit_extension(self):
        run = self.planned(self.fixture())
        engine.verify(run["run"])
        engine.verify(run["run"])
        self.assertEqual(engine.verify(run["run"])["phase"], "blocked")
        with self.assertRaisesRegex(FactoryError, "Repair limit"):
            engine.verify(run["run"])
        with self.assertRaisesRegex(FactoryError, "reason"):
            engine.extend(run["run"], 1, "")
        self.assertEqual(engine.extend(run["run"], 1, "Synthetic user direction")["phase"], "implement")

    def test_tracked_ignored_modes_symlinks_and_untracked_drift(self):
        f = self.fixture()
        (f.repo / "ignored-tracked").write_text("one")
        git(f.repo, ["add", "-f", "--", "ignored-tracked"])
        git(f.repo, ["commit", "-m", "tracked ignore"])
        run = self.checked(f)
        worktree = Path(run["worktree"])
        base = read_run(run["run"])["base"]
        original = run["next"]["evidence"]["tree"]
        (worktree / "ignored-tracked").write_text("two")
        self.assertNotEqual(snapshot(worktree, base)["tree"], original)
        self.assertEqual(engine.describe(read_run(run["run"]))["next"]["action"], "verify")
        with self.assertRaisesRegex(FactoryError, "verification"):
            self.review(run)
        (worktree / "ignored-tracked").write_text("one")
        (worktree / "check.py").chmod(0o755)
        self.assertNotEqual(snapshot(worktree, base)["tree"], original)
        (worktree / "check.py").chmod(0o644)
        (worktree / "link").symlink_to("value.txt")
        self.assertNotEqual(snapshot(worktree, base)["tree"], original)
        (worktree / "link").unlink()
        (worktree / ":untracked").write_text("new")
        self.assertNotEqual(snapshot(worktree, base)["tree"], original)

    def test_config_edits_do_not_weaken_frozen_checks(self):
        run = self.planned(self.fixture())
        atomic_json(Path(run["worktree"]) / ".factory.json", {"version": 1, "endpoint": "local", "checks": []})
        result = engine.verify(run["run"])
        self.assertFalse(result["verification"]["passed"])
        self.assertEqual(result["verification"]["results"][0]["name"], "behavior")

    def test_check_cannot_certify_self_edits(self):
        run = self.planned(self.fixture())
        (Path(run["worktree"]) / "check.py").write_text(
            "from pathlib import Path\nPath('value.txt').write_text('new')\n"
        )
        result = engine.verify(run["run"])
        self.assertTrue(result["verification"]["results"][0]["passed"])
        self.assertFalse(result["verification"]["passed"])
        self.assertFalse(result["verification"]["unchanged"])

    def test_review_covers_every_criterion_and_no_major_findings(self):
        run = self.checked(self.fixture())
        with self.assertRaisesRegex(FactoryError, "every acceptance"):
            self.review(run, criteria=[])
        with self.assertRaisesRegex(FactoryError, "unresolved"):
            self.review(run, findings=[{"severity": "major", "location": "value.txt", "issue": "Wrong behavior"}])
        result = self.review(
            run, verdict="fail", criteria=[{"id": "AC1", "passed": False, "evidence": "Missing coverage"}]
        )
        self.assertEqual(result["next"]["action"], "implement")
        self.assertEqual(result["failures"], 1)

    def test_reviewed_tree_and_head_drift_prevent_delivery(self):
        run = self.reviewed(self.fixture())
        extra = Path(run["worktree"]) / "extra"
        extra.write_text("drift")
        with self.assertRaisesRegex(FactoryError, "current verification"):
            deliver(run["run"])
        extra.unlink()
        git(run["worktree"], ["commit", "--allow-empty", "-m", "unexpected commit"])
        with self.assertRaisesRegex(FactoryError, "current verification"):
            deliver(run["run"])

    def test_altered_missing_worktree_and_index_conflicts(self):
        run = self.planned(self.fixture())
        git(run["worktree"], ["checkout", "--detach"])
        with self.assertRaisesRegex(FactoryError, "ownership"):
            engine.resume(run["run"])
        git(run["worktree"], ["checkout", run["branch"]])
        # Real conflict, in addition to the original ownership tests.
        base = read_run(run["run"])["base"]
        git(run["worktree"], ["checkout", "-b", "conflict-fixture", base])
        (Path(run["worktree"]) / "value.txt").write_text("side")
        git(run["worktree"], ["commit", "-am", "side"])
        git(run["worktree"], ["checkout", run["branch"]])
        (Path(run["worktree"]) / "value.txt").write_text("ours")
        git(run["worktree"], ["commit", "-am", "ours"])
        with self.assertRaises(FactoryError):
            git(run["worktree"], ["merge", "conflict-fixture"])
        with self.assertRaisesRegex(FactoryError, "index conflicts"):
            snapshot(run["worktree"], base)
        shutil.rmtree(run["worktree"])
        with self.assertRaisesRegex(FactoryError, "missing"):
            engine.resume(run["run"])

    def test_live_locks_refuse_and_dead_same_host_recover(self):
        run = engine.start(self.fixture().options)
        with locked(run["run"]):
            with self.assertRaisesRegex(FactoryError, "owns this run"):
                engine.resume(run["run"])
            with self.assertRaisesRegex(FactoryError, "still alive"):
                engine.recover(run["run"])
        lock = Path(run["run"]) / "lock"
        lock.mkdir()
        atomic_json(lock / "owner.json", {"pid": 2147483647, "host": socket.gethostname()})
        self.assertTrue(engine.recover(run["run"])["operation"]["recovered"])
        self.assertEqual(engine.resume(run["run"])["phase"], "plan")

    def test_interrupted_commit_reconciles_without_duplicate(self):
        run = self.reviewed(self.fixture())
        state = read_run(run["run"])
        snap = snapshot(run["worktree"], state["base"])
        state["commitIntent"] = {"parent": snap["head"], "tree": snap["tree"], "paths": snap["paths"]}
        atomic_json(Path(run["run"]) / "state.json", state)
        git(run["worktree"], ["add", "--", *snap["paths"]])
        git(run["worktree"], ["commit", "-m", "synthetic interrupted delivery"])
        head = git(run["worktree"], ["rev-parse", "HEAD"]).strip()
        result = deliver(run["run"])
        self.assertEqual(result["delivery"]["commit"], head)
        self.assertEqual(result["phase"], "done")

    def test_interrupted_start_resumes_owned_worktree(self):
        f = self.fixture()
        run = engine.start(f.options)
        state = read_run(run["run"])
        state["phase"] = "preparing"
        atomic_json(Path(run["run"]) / "state.json", state)
        self.assertEqual(engine.start(f.options)["phase"], "plan")

    def test_cli_json_roundtrip_and_process_deduplication(self):
        f = self.fixture()
        args = [
            "start",
            "--repo",
            f.repo,
            "--task",
            f.options.task,
            "--criterion",
            f.options.criteria[0],
            "--worktree-root",
            f.options.worktree_root,
            "--json",
        ]
        import json

        first, second = self.cli(*args), self.cli(*args)
        self.assertEqual(first.returncode, 0, first.stderr)
        a, b = json.loads(first.stdout), json.loads(second.stdout)
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(json.loads(self.cli("next", "--run", a["run"], "--json").stdout)["next"]["action"], "plan")
        missing = self.cli(
            "start", "--repo", f.repo, "--task", "No criteria", "--worktree-root", f.options.worktree_root, "--json"
        )
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(json.loads(missing.stderr)["code"], "invalid")

    def test_issue_snapshot_frozen_and_identity_reused(self):
        f = self.fixture()
        self.github(f)
        options = replace(f.options, task=None, issue="42")
        run = engine.start(options)
        self.assertIn("Frozen issue", run["task"])
        self.assertEqual(engine.start(options)["id"], run["id"])
        self.assertEqual(read_run(run["run"])["source"]["snapshot"]["number"], 42)

    def test_draft_remote_head_and_uncertain_create_recovery(self):
        f = self.fixture("draft-pr")
        file = self.github(f)
        run = self.reviewed(f)
        with patch.dict(os.environ, {"MOCK_FAIL": "1"}):
            with self.assertRaisesRegex(FactoryError, "gh pr"):
                deliver(run["run"])
        self.assertTrue(file.exists())
        self.assertEqual(read_run(run["run"])["operation"]["kind"], "pr-create")
        self.assertEqual(engine.describe(read_run(run["run"]))["next"]["action"], "deliver")
        created = read_json(file)
        result = deliver(run["run"])
        self.assertEqual(result["phase"], "done")
        self.assertEqual(result["delivery"]["pr"], created["url"])
        self.assertEqual(result["delivery"]["commit"], created["headRefOid"])
        self.assertEqual(
            git(run["worktree"], ["ls-remote", "origin", f"refs/heads/{run['branch']}"]).split()[0],
            created["headRefOid"],
        )

    def test_closed_ready_wrong_head_wrong_base_cannot_complete(self):
        f = self.fixture("draft-pr")
        file = self.github(f)
        run = self.reviewed(f)
        with patch.dict(os.environ, {"MOCK_FAIL": "1"}), self.assertRaises(FactoryError):
            deliver(run["run"])
        original = read_json(file)
        for change in ({"isDraft": False}, {"state": "CLOSED"}, {"headRefOid": "wrong"}, {"baseRefName": "wrong"}):
            atomic_json(file, {**original, **change})
            with self.assertRaisesRegex(FactoryError, "not an open draft"):
                deliver(run["run"])
            self.assertNotEqual(read_run(run["run"])["phase"], "done")
        atomic_json(file, original)
        self.assertEqual(deliver(run["run"])["phase"], "done")

    def test_missing_remote_does_not_downgrade_endpoint(self):
        f = self.fixture("draft-pr")
        run = self.reviewed(f)
        mock = f.root / "offline"
        mock.mkdir()
        script = mock / "gh"
        script.write_text("#!/bin/sh\nexit 1\n")
        script.chmod(0o755)
        with (
            patch.dict(os.environ, {"PATH": str(mock) + os.pathsep + os.environ["PATH"]}),
            self.assertRaisesRegex(FactoryError, "gh repo"),
        ):
            deliver(run["run"])
        state = read_run(run["run"])
        self.assertEqual(state["endpoint"], "draft-pr")
        self.assertNotEqual(state["phase"], "done")
        self.assertTrue(state["delivery"]["commit"])

    def test_repair_supersedes_interrupted_commit_intent(self):
        f = self.fixture("draft-pr")
        file = self.github(f)
        run = self.reviewed(f)
        with patch.dict(os.environ, {"MOCK_FAIL": "1"}), self.assertRaises(FactoryError):
            deliver(run["run"])
        old = read_run(run["run"])["delivery"]["commit"]
        (Path(run["worktree"]) / "new-file").write_text("reviewed repair")
        verified = engine.verify(run["run"])
        self.assertIsNone(read_run(run["run"])["commitIntent"])
        self.review(verified)
        file.unlink()
        result = deliver(run["run"])
        self.assertEqual(result["phase"], "done")
        self.assertNotEqual(result["delivery"]["commit"], old)

    def test_renames_and_committed_deletions_exact_tree(self):
        f = self.fixture()
        (f.repo / "original.txt").write_text("rename content")
        (f.repo / "delete.txt").write_text("delete content")
        git(f.repo, ["add", "--", "original.txt", "delete.txt"])
        git(f.repo, ["commit", "-m", "rename baseline"])
        run = self.planned(f)
        root = Path(run["worktree"])
        (root / "value.txt").write_text("new\n")
        (root / "delete.txt").unlink()
        git(root, ["add", "--", "delete.txt"])
        git(root, ["commit", "-m", "delete before verification"])
        (root / "original.txt").rename(root / "renamed.txt")
        checked = engine.verify(run["run"])
        self.assertIn("original.txt", checked["next"]["evidence"]["paths"])
        self.assertIn("renamed.txt", checked["next"]["evidence"]["paths"])
        self.review(checked)
        result = deliver(run["run"])
        self.assertEqual(result["phase"], "done")
        self.assertEqual(git(root, ["rev-parse", "HEAD^{tree}"]).strip(), checked["next"]["evidence"]["tree"])

    def test_dead_allocation_lock_recovered(self):
        f = self.fixture()
        run = engine.start(f.options)
        allocation = Path(read_run(run["run"])["common"]) / "factory" / "runs"
        (allocation / "lock").mkdir()
        atomic_json(allocation / "lock" / "owner.json", {"pid": 2147483647, "host": socket.gethostname()})
        self.assertTrue(engine.recover(run["run"])["allocation"]["recovered"])
        self.assertNotEqual(engine.start(replace(f.options, task="Another task"))["id"], run["id"])
