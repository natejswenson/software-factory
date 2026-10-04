"""Real snapshots exercise explanations without granting or changing any gate."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from software_factory import diagnostics, engine
from software_factory.delivery import deliver
from software_factory.errors import FactoryError
from software_factory.git import git
from software_factory.store import atomic_json, locked, read_run
from tests.support import FactoryCase


class DiagnosticTests(FactoryCase):
    def state(self, run, **changes):
        state = read_run(run["run"])
        state.update(changes)
        atomic_json(Path(run["run"]) / "state.json", state)
        return state

    def preserved(self, run):
        state = read_run(run["run"])
        root = Path(state["worktree"])
        files = {
            str(p): os.readlink(p) if p.is_symlink() else p.read_bytes()
            for parent in (root, Path(state["dir"]))
            for p in parent.rglob("*")
            if (p.is_file() or p.is_symlink()) and ".git" not in p.parts
        }
        index = git(root, ["write-tree"])
        head = git(root, ["rev-parse", "HEAD"])
        report = diagnostics.explain(state)
        after = {
            str(p): os.readlink(p) if p.is_symlink() else p.read_bytes()
            for parent in (root, Path(state["dir"]))
            for p in parent.rglob("*")
            if (p.is_file() or p.is_symlink()) and ".git" not in p.parts
        }
        self.assertEqual(files, after)
        self.assertEqual(index, git(root, ["write-tree"]))
        self.assertEqual(head, git(root, ["rev-parse", "HEAD"]))
        return report

    def test_missing_current_and_failed_proofs_match_authoritative_next(self):
        f = self.fixture()
        run = engine.start(f.options)
        r = self.preserved(run)
        self.assertEqual({v["status"] for v in r["gates"].values()}, {"missing"})
        self.assertEqual(r["next"], engine.next_action(read_run(run["run"])))
        self.assertFalse(r["changedPaths"]["available"])
        run = self.planned(f)
        failed = engine.verify(run["run"])
        r = self.preserved(failed)
        self.assertEqual(r["gates"]["planReview"]["status"], "current")
        self.assertEqual(r["gates"]["verification"]["status"], "failed")
        self.assertFalse(r["gates"]["verification"]["passed"])
        (Path(run["worktree"]) / "extra").write_text("changed since failed check")
        r = self.preserved(failed)
        self.assertEqual(r["gates"]["verification"]["status"], "failed")
        self.assertIn("tree", {d["key"] for d in r["gates"]["verification"]["differences"]})
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        reviewed = self.review(engine.verify(run["run"]))
        r = self.preserved(reviewed)
        self.assertEqual({v["status"] for v in r["gates"].values()}, {"current"})
        self.assertEqual(r["next"], reviewed["next"])
        self.assertEqual(r["changedPaths"]["paths"], [])
        self.assertEqual(diagnostics.exit_code(r), 0)

    def test_each_fingerprint_dimension_and_failed_review_historical_fact(self):
        run = self.reviewed(self.fixture())
        original = read_run(run["run"])
        for key in engine.EVIDENCE_KEYS:
            with self.subTest(key=key):
                changed = {**original["codeReview"]["evidence"], key: "synthetic-old-hash"}
                self.state(run, codeReview={**original["codeReview"], "evidence": changed})
                r = self.preserved(run)
                self.assertEqual(r["gates"]["codeReview"]["status"], "stale")
                self.assertEqual([d["key"] for d in r["gates"]["codeReview"]["differences"]], [key])
                self.assertEqual(r["next"]["action"], "review")
        self.state(run, codeReview={**original["codeReview"], "verdict": "fail", "evidence": changed})
        r = self.preserved(run)
        self.assertEqual(r["gates"]["codeReview"]["status"], "failed")
        self.assertEqual(r["gates"]["codeReview"]["verdict"], "fail")
        self.assertTrue(r["gates"]["codeReview"]["differences"])
        self.state(run, codeReview=original["codeReview"])
        (Path(run["run"]) / "plan.md").write_text("Different complete plan\n")
        r = self.preserved(run)
        self.assertEqual(r["gates"]["planReview"]["status"], "stale")
        self.assertEqual(r["next"]["action"], "plan-review")
        self.assertIn("plan", {d["key"] for d in r["gates"]["planReview"]["differences"]})

    def test_proof_tree_changes_cover_ignored_tracked_modes_links_delete_and_rename(self):
        f = self.fixture()
        for name in ("ignored-tracked", "old-name", "delete-me", "mode-tool"):
            (f.repo / name).write_text("baseline")
        git(f.repo, ["add", "-f", "ignored-tracked", "old-name", "delete-me", "mode-tool"])
        git(f.repo, ["commit", "-m", "synthetic baseline paths"])
        run = self.checked(f)
        root = Path(run["worktree"])
        (root / "ignored-tracked").write_text("changed")
        (root / "old-name").rename(root / "new-name")
        (root / "delete-me").unlink()
        (root / "mode-tool").chmod(0o755)
        (root / "value.txt").unlink()
        (root / "value.txt").symlink_to("check.py")
        (root / "ignored-untracked").write_text("excluded")
        r = self.preserved(run)
        self.assertEqual(r["changedPaths"]["baseline"], "verification")
        self.assertEqual(
            r["changedPaths"]["paths"],
            ["delete-me", "ignored-tracked", "mode-tool", "new-name", "old-name", "value.txt"],
        )
        self.assertEqual(r["changedPaths"]["recordedTree"], run["verification"]["evidence"]["tree"])
        self.assertEqual(r["gates"]["verification"]["status"], "stale")
        self.assertEqual(r["next"]["action"], "verify")
        saved = read_run(run["run"])
        self.state(
            run, verification=None, codeReview={"verdict": "pass", "evidence": saved["verification"]["evidence"]}
        )
        self.assertEqual(self.preserved(run)["changedPaths"]["baseline"], "codeReview")

    def test_rules_drift_is_initial_detail_and_malformed_rules_are_unknown(self):
        f = self.fixture()
        self.rule(f.repo, "instructions.md", "Original rule")
        git(f.repo, ["add", ".rules"])
        git(f.repo, ["commit", "-m", "synthetic initial rule"])
        run = self.reviewed(f)
        root = Path(run["worktree"])
        self.rule(root, "next.md", "New rule")
        r = self.preserved(run)
        self.assertEqual(r["rulesDetail"]["baseline"], "initial")
        self.assertEqual(r["rulesDetail"]["initialPaths"], [".rules/instructions.md"])
        self.assertEqual(r["rulesDetail"]["currentPaths"], [".rules/instructions.md", ".rules/next.md"])
        self.assertEqual(r["gates"]["planReview"]["status"], "stale")
        self.assertIn("rules", {d["key"] for d in r["gates"]["planReview"]["differences"]})
        self.rule(root, "unsafe.md", '```factory-config\n{"endpoint":"invalid"}\n```')
        r = self.preserved(run)
        self.assertIsNone(r["next"])
        self.assertEqual(r["gates"]["verification"]["status"], "unknown")
        self.assertTrue(r["errors"])
        self.assertEqual(diagnostics.exit_code(r), 3)

    def test_unavailable_tree_and_invalid_worktree_never_guess_unchanged(self):
        run = self.checked(self.fixture())
        saved = read_run(run["run"])
        evidence = {**saved["verification"]["evidence"], "tree": "0" * 40}
        self.state(run, verification={**saved["verification"], "evidence": evidence})
        r = self.preserved(run)
        self.assertFalse(r["changedPaths"]["available"])
        self.assertEqual(r["changedPaths"]["paths"], [])
        self.assertTrue(r["errors"])
        self.assertEqual(diagnostics.exit_code(r), 3)
        state = self.state(run, worktree=str(Path(run["worktree"]) / "absent"))
        before = (Path(run["run"]) / "state.json").read_bytes()
        r = diagnostics.explain(state)
        self.assertIsNone(r["next"])
        self.assertEqual(r["gates"]["verification"]["status"], "unknown")
        self.assertEqual(before, (Path(run["run"]) / "state.json").read_bytes())
        self.assertEqual(diagnostics.exit_code(r), 3)

    def test_live_owner_missing_receipt_and_moving_inspection_are_safe(self):
        run = self.checked(self.fixture())
        with locked(run["run"]):
            with (
                patch.object(diagnostics.os, "getpid", return_value=-1),
                patch.object(engine, "evidence", side_effect=AssertionError("no Git under another owner")),
            ):
                r = diagnostics.explain(read_run(run["run"]))
            self.assertEqual(r["next"]["action"], "wait")
            self.assertEqual(r["gates"]["verification"]["status"], "unknown")
            self.assertEqual(diagnostics.exit_code(r), 3)
            owner = Path(run["run"]) / "lock/owner.json"
            raw = owner.read_bytes()
            owner.unlink()
            r = diagnostics.explain(read_run(run["run"]))
            self.assertIsNone(r["next"])
            self.assertTrue(r["errors"])
            owner.write_bytes(raw)
        original = engine.evidence
        calls = 0

        def moving(state):
            nonlocal calls
            current = original(state)
            calls += 1
            if calls == 1:
                (Path(run["worktree"]) / "extra").write_text("concurrent edit")
            return current

        with patch.object(engine, "evidence", moving):
            r = diagnostics.explain(read_run(run["run"]))
        self.assertIsNone(r["next"])
        self.assertEqual(r["gates"]["verification"]["status"], "unknown")
        self.assertIn("snapshot-changed", [e["code"] for e in r["errors"]])

    def test_legacy_blocked_done_and_owned_delivery_recovery(self):
        f = self.fixture("draft-pr")
        self.github(f)
        run = self.reviewed(f)
        with patch.dict(os.environ, {"MOCK_FAIL": "1"}), self.assertRaises(FactoryError):
            deliver(run["run"])
        r = self.preserved(run)
        self.assertTrue(r["deliveryRecoveryAllowed"])
        self.assertEqual(r["gates"]["codeReview"]["status"], "stale")
        self.assertIn("head", {d["key"] for d in r["gates"]["codeReview"]["differences"]})
        self.assertEqual(r["next"]["action"], "deliver")
        done = deliver(run["run"])
        r = self.preserved(done)
        self.assertEqual(r["next"], done["next"])
        self.assertEqual(r["delivery"], done["delivery"])
        self.assertTrue(any("historical" in x.lower() for x in r["limitations"]))
        state = self.state(run, phase="blocked")
        r = diagnostics.explain(state)
        self.assertEqual(r["next"]["action"], "blocked")
        self.assertEqual(diagnostics.exit_code(r), 2)
        state = self.state(run, phase="done", worktree=str(f.root / "absent"))
        r = diagnostics.explain(state)
        self.assertEqual(r["next"]["action"], "done")
        self.assertEqual(diagnostics.exit_code(r), 3)
        other = self.reviewed(self.fixture())
        state = read_run(other["run"])
        state.pop("rules")
        for record, field in [("planReview", "context"), ("verification", "evidence"), ("codeReview", "evidence")]:
            state[record][field].pop("rules", None)
        atomic_json(Path(other["run"]) / "state.json", state)
        self.assertEqual({v["status"] for v in self.preserved(other)["gates"].values()}, {"current"})

    def test_malformed_proofs_and_inspection_failure_after_next_remain_partial(self):
        run = self.checked(self.fixture())
        saved = read_run(run["run"])
        for bad in (["malformed"], {"passed": True, "evidence": {"tree": ["not a hash"]}}):
            self.state(run, verification=bad)
            output = self.cli("explain", "--run", run["run"], "--json")
            self.assertEqual(output.returncode, 3, output.stderr)
            self.assertEqual(json.loads(output.stdout)["gates"]["verification"]["status"], "unknown")
            self.assertNotIn("Traceback", output.stderr)
        self.state(
            run,
            verification={
                **saved["verification"],
                "evidence": {**saved["verification"]["evidence"], "tree": "--output=forbidden-write"},
            },
        )
        r = self.preserved(run)
        self.assertFalse(r["changedPaths"]["available"])
        self.assertFalse((Path(run["worktree"]) / "forbidden-write").exists())
        self.state(run, verification=saved["verification"])
        original = engine.evidence
        count = 0

        def unavailable(state):
            nonlocal count
            count += 1
            if count == 3:
                raise FactoryError("Synthetic observation failure", "infrastructure")
            return original(state)

        with patch.object(engine, "evidence", unavailable):
            r = diagnostics.explain(read_run(run["run"]))
        self.assertIsNone(r["next"])
        self.assertEqual(r["gates"]["verification"]["status"], "unknown")
        self.assertEqual(diagnostics.exit_code(r), 3)

        def late_unavailable(state):
            nonlocal count
            count += 1
            if count == 4:
                raise FactoryError("Synthetic late rules failure", "invalid")
            return original(state)

        count = 0
        with patch.object(engine, "evidence", late_unavailable):
            r = diagnostics.explain(read_run(run["run"]))
        self.assertIsNone(r["next"])
        self.assertEqual(r["gates"]["verification"]["status"], "unknown")
        self.assertEqual(r["gates"]["codeReview"]["status"], "missing")
        self.assertFalse(r["changedPaths"]["available"])
        with locked(run["run"]):
            before = (Path(run["run"]) / "state.json").read_bytes()
            output = self.cli("explain", "--run", run["run"], "--json")
            self.assertEqual(output.returncode, 3)
            self.assertEqual(json.loads(output.stdout)["next"]["action"], "wait")
            self.assertEqual(before, (Path(run["run"]) / "state.json").read_bytes())

    def test_run_change_between_initial_read_and_capture_is_not_current(self):
        run = self.checked(self.fixture())
        earlier = read_run(run["run"])
        newer = self.state(run, failures=earlier["failures"] + 1)
        before = (Path(run["run"]) / "state.json").read_bytes()
        with patch.object(engine, "evidence", side_effect=AssertionError("No inspection from old state")):
            r = diagnostics.explain(earlier)
        self.assertIsNone(r["next"])
        self.assertEqual(r["gates"]["verification"]["status"], "unknown")
        self.assertIn("snapshot-changed", [e["code"] for e in r["errors"]])
        self.assertEqual(before, (Path(run["run"]) / "state.json").read_bytes())
        self.assertEqual(read_run(run["run"]), newer)

    def test_foreign_host_with_same_pid_never_inspects_current_files(self):
        run = self.checked(self.fixture())
        with locked(run["run"]):
            path = Path(run["run"]) / "lock/owner.json"
            original = json.loads(path.read_text())
            foreign = {**original, "host": "synthetic-other-host", "pid": os.getpid()}
            atomic_json(path, foreign)
            try:
                with patch.object(engine, "evidence", side_effect=AssertionError("Foreign owner forbids inspection")):
                    r = self.preserved(run)
                self.assertEqual(r["next"], {"action": "wait", "owner": foreign})
                self.assertEqual(r["gates"]["verification"]["status"], "unknown")
                self.assertEqual(diagnostics.exit_code(r), 3)
            finally:
                atomic_json(path, original)

    def test_cli_and_summary_remain_consistent_and_invalid_input_has_no_traceback(self):
        run = self.reviewed(self.fixture())
        (Path(run["worktree"]) / "extra").write_text("drift")
        output = self.cli("explain", "--run", run["run"], "--json")
        self.assertEqual(output.returncode, 0, output.stderr)
        r = json.loads(output.stdout)
        summary = self.summary(run)
        self.assertEqual(r["next"]["action"], summary["next"]["action"])
        self.assertTrue(summary["verification"]["passed"])
        self.assertEqual(r["gates"]["verification"]["status"], "stale")
        self.assertIn("verification: stale", self.cli("explain", "--run", run["run"]).stdout)
        output = self.cli("explain", "--json")
        self.assertEqual(output.returncode, 2)
        self.assertNotIn("Traceback", output.stderr)
