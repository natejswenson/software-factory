"""Tolerant inventories preserve real local ledgers and strict task allocation."""

import json
import os
import shutil
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from software_factory import engine, history
from software_factory.delivery import deliver
from software_factory.errors import FactoryError
from software_factory.git import git
from software_factory.store import atomic_json, locked, read_run
from tests.support import FactoryCase


class HistoryTests(FactoryCase):
    def test_cli_malformed_neighbor_receipt_and_options_preserve_saved_outcomes(self):
        f = self.fixture()
        healthy = deliver(self.reviewed(f)["run"])
        affected = self.checked(replace(f, options=replace(f.options, task="Synthetic malformed neighbor")))
        expected_events = history.inspect(affected["run"])["events"]
        self.assertTrue(expected_events)
        state_path = Path(affected["run"]) / "state.json"
        state = state_path.read_bytes()
        receipt_path = Path(affected["run"]) / "verification-1.json"
        receipt_path.write_bytes(b'{"synthetic malformed receipt":')
        state_path.write_bytes(b'{"synthetic malformed metadata":')

        def snapshot():
            return {str(p.relative_to(f.root)): os.readlink(p) if p.is_symlink() else p.read_bytes()
                    for p in f.root.rglob("*") if p.is_file() or p.is_symlink()}

        before = snapshot()
        output = self.cli("runs", "--repo", f.repo, "--json")
        self.assertEqual(output.returncode, 2, output.stderr)
        self.assertEqual(output.stderr, "")
        report = json.loads(output.stdout)
        self.assertEqual([row["id"] for row in report["runs"]], [healthy["id"]])
        self.assertEqual(report["runs"][0]["delivery"], healthy["delivery"])
        self.assertTrue(any(error["run"] == affected["run"] for error in report["errors"]))
        self.assertEqual(snapshot(), before)

        state_path.write_bytes(state)
        before = snapshot()
        output = self.cli("history", "--run", affected["run"], "--json")
        self.assertEqual(output.returncode, 2, output.stderr)
        self.assertEqual(output.stderr, "")
        report = json.loads(output.stdout)
        self.assertEqual(report["attempts"][0]["status"], "invalid")
        self.assertIsNone(report["attempts"][0]["passed"])
        self.assertEqual(report["totals"]["knownAttempts"], 0)
        self.assertEqual(report["events"], expected_events)
        self.assertTrue(report["errors"])
        saved = self.cli("history", "--run", healthy["run"], "--json")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertEqual(json.loads(saved.stdout)["delivery"], healthy["delivery"])
        for command in (("runs", "--repo", f.repo, "--limit", "not-an-integer"),
                        ("history", "--run", affected["run"], "--limit", "0")):
            output = self.cli(*command, "--json")
            self.assertEqual(output.returncode, 2)
            self.assertEqual(output.stdout, "")
            self.assertEqual(json.loads(output.stderr)["code"], "invalid")
            self.assertNotIn("Traceback", output.stderr)
        self.assertEqual(snapshot(), before)

    def change(self, run, **fields):
        state = read_run(run["run"])
        state.update(fields)
        atomic_json(Path(run["run"]) / "state.json", state)
        return state

    def runs(self, fixture, **kwargs):
        return history.discover(str(fixture.repo), **kwargs)

    def test_order_fallback_ties_filter_before_limit_and_legacy_list(self):
        f = self.fixture()
        runs = [engine.start(replace(f.options, task=f"Task {i}")) for i in range(4)]
        dates = ["2026-01-03T00:00:00Z", "2026-01-03T00:00:00Z", "broken", None]
        for index, run in enumerate(runs):
            self.change(
                run,
                updatedAt=dates[index],
                createdAt="2026-01-02T00:00:00Z" if index == 2 else None,
                phase="blocked" if index == 3 else "plan",
            )
        report = self.runs(f)
        self.assertEqual(report["total"], 4)
        self.assertEqual(report["matched"], 4)
        expected = sorted(runs[:2], key=lambda item: item["id"]) + runs[2:]
        self.assertEqual([item["id"] for item in report["runs"]], [item["id"] for item in expected])
        self.assertEqual(sum(error["code"] == "timestamp" for error in report["errors"]), 2)
        filtered = self.runs(f, phase="blocked", limit=1)
        self.assertEqual(filtered["matched"], 1)
        self.assertEqual(filtered["runs"][0]["id"], runs[3]["id"])
        self.assertEqual(filtered["runs"][0]["nextAction"], "blocked")
        actual = json.loads(self.cli("list", "--repo", f.repo, "--json").stdout)
        expected_list = [
            {
                "id": state["id"],
                "task": state["task"].splitlines()[0],
                "phase": state["phase"],
                "endpoint": state["endpoint"],
                "run": state["dir"],
            }
            for state in sorted([read_run(run["run"]) for run in runs], key=lambda item: item["id"])
        ]
        self.assertEqual(actual, expected_list)
        self.assertEqual(self.cli("runs", "--repo", f.repo, "--phase", "blocked", "--json").returncode, 2)

    def test_bad_neighbor_and_missing_worktree_preserve_rows_strict_start_refuses(self):
        f = self.fixture()
        healthy = self.planned(f)
        missing = engine.start(replace(f.options, task="Another task"))
        shutil.rmtree(missing["worktree"])
        root = Path(healthy["run"]).parent
        invalid = root / ("a" * 36)
        invalid.mkdir()
        (invalid / "state.json").write_text("{broken")
        report = self.runs(f)
        self.assertEqual({row["id"] for row in report["runs"]}, {healthy["id"], missing["id"]})
        row = next(row for row in report["runs"] if row["id"] == missing["id"])
        self.assertFalse(row["nextAvailable"])
        self.assertIsNone(row["nextAction"])
        self.assertEqual(row["branch"], missing["branch"])
        self.assertEqual(row["base"], "main")
        self.assertTrue(any(error["run"] == str(invalid) for error in report["errors"]))
        self.assertTrue(
            any(error["run"] == missing["run"] and error["code"] == "inspection" for error in report["errors"])
        )
        with self.assertRaises(ValueError):
            engine.start(replace(f.options, task="Strict new task"))
        self.assertNotEqual(self.cli("list", "--repo", f.repo, "--json").returncode, 0)
        self.assertEqual(self.cli("runs", "--repo", f.repo, "--json").returncode, 2)

    def test_legacy_branch_live_foreign_owner_missing_owner_and_no_source_inspection(self):
        f = self.fixture()
        run = self.planned(f)
        git(run["worktree"], ["branch", "-m", "factory/historical"])
        self.change(run, branch="factory/historical", rules=None)
        self.assertEqual(self.runs(f)["runs"][0]["branch"], "factory/historical")
        with locked(run["run"]):
            owner = Path(run["run"]) / "lock/owner.json"
            original = json.loads(owner.read_text())
            atomic_json(owner, {**original, "host": "synthetic-other-host"})
            with patch(
                "software_factory.history.engine.next_action", side_effect=AssertionError("live owner inspected source")
            ):
                report = self.runs(f)
            self.assertEqual(report["runs"][0]["nextAction"], "wait")
            self.assertTrue(report["runs"][0]["nextAvailable"])
            before = owner.read_bytes()
            history.inspect(run["run"])
            self.assertEqual(before, owner.read_bytes())
            owner.unlink()
            report = self.runs(f)
            self.assertFalse(report["runs"][0]["nextAvailable"])
            self.assertTrue(report["errors"])

    def test_events_append_order_pages_distinct_receipts_skips_missing_metrics(self):
        f = self.fixture()
        config = json.loads((f.repo / ".factory.json").read_text())
        config["checks"].append(
            {"name": "second", "argv": [config["checks"][0]["argv"][0], "-c", 'print("second")'], "timeoutMs": 2000}
        )
        atomic_json(f.repo / ".factory.json", config)
        git(f.repo, ["add", "."])
        git(f.repo, ["commit", "-m", "synthetic two checks"])
        run = self.planned(f)
        engine.verify(run["run"])
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        final = engine.verify(run["run"])
        self.assertTrue(final["verification"]["passed"])
        first = Path(run["run"]) / "verification-1.json"
        receipt = json.loads(first.read_text())
        del receipt["results"][0]["durationMs"]
        atomic_json(first, receipt)
        state = read_run(run["run"])
        state["history"].extend(
            [
                {"at": "2026-02-01T00:00:00Z", "action": "synthetic later", "detail": "literal"},
                {"at": "2020-01-01T00:00:00Z", "action": "synthetic backward", "count": 3},
            ]
        )
        atomic_json(Path(run["run"]) / "state.json", state)
        report = history.inspect(run["run"], offset=len(state["history"]) - 2, limit=1)
        self.assertEqual(report["events"][0]["action"], "synthetic later")
        self.assertEqual(report["events"][0]["details"], {"detail": "literal"})
        following = history.inspect(run["run"], offset=len(state["history"]) - 1, limit=1)
        self.assertEqual(following["events"][0]["action"], "synthetic backward")
        self.assertEqual(following["events"][0]["index"], len(state["history"]) - 1)
        self.assertEqual(report["attempts"], following["attempts"])
        self.assertEqual([item["status"] for item in report["attempts"][0]["checks"]], ["failed", "not-run"])
        self.assertEqual([item["status"] for item in report["attempts"][1]["checks"]], ["passed", "passed"])
        self.assertIsNone(report["attempts"][0]["checks"][0]["durationMs"])
        self.assertEqual(report["totals"]["knownAttempts"], 2)
        self.assertEqual(report["totals"]["failures"], 1)
        self.assertEqual(report["totals"]["missingDurationMetrics"], 1)
        self.assertEqual(
            report["totals"]["checkExecutionMs"], sum(item["durationMs"] for item in final["verification"]["results"])
        )
        self.change(run, checkAttempt=3)
        missing = history.inspect(run["run"])
        self.assertEqual(missing["attempts"][2]["status"], "missing")
        self.assertEqual(missing["totals"]["missingReceipts"], 1)
        self.assertIsNone(missing["attempts"][2]["checks"][0]["durationMs"])
        self.assertEqual(self.cli("history", "--run", run["run"], "--json").returncode, 2)

    def test_invalid_limits_bounded_counter_unsafe_receipts_and_entries(self):
        f = self.fixture()
        run = self.checked(f)
        for kwargs in ({"limit": 0}, {"limit": 1001}, {"phase": "unknown"}):
            with self.assertRaises(FactoryError):
                self.runs(f, **kwargs)
        for kwargs in ({"offset": -1}, {"limit": 0}, {"limit": True}):
            with self.assertRaises(FactoryError):
                history.inspect(run["run"], **kwargs)
        first = Path(run["run"]) / "verification-1.json"
        first.unlink()
        first.symlink_to(Path(run["run"]) / "state.json")
        report = history.inspect(run["run"])
        self.assertEqual(report["attempts"][0]["status"], "unavailable")
        self.assertTrue(report["errors"])
        outside = Path(run["run"]).parent / ("b" * 36)
        outside.symlink_to(Path(run["run"]), target_is_directory=True)
        report = self.runs(f)
        self.assertEqual(report["total"], 1)
        self.assertTrue(any(error["run"] == str(outside) for error in report["errors"]))
        self.assertTrue(history.inspect(str(outside))["errors"])
        self.assertEqual(self.cli("history", "--run", outside, "--json").returncode, 2)
        self.change(run, checkAttempt=1001)
        report = history.inspect(run["run"])
        self.assertEqual(len(report["attempts"]), 1000)
        self.assertTrue(any(item["code"] == "attempt-limit" for item in report["errors"]))
        self.change(run, checkAttempt=True)
        self.assertTrue(history.inspect(run["run"])["errors"])

    def test_absent_root_readonly_and_normal_cli_reports(self):
        f = self.fixture()
        common = Path(git(f.repo, ["rev-parse", "--git-common-dir"]).strip())
        if not common.is_absolute():
            common = f.repo / common
        self.assertEqual(self.runs(f)["runs"], [])
        self.assertFalse((common / "factory").exists())
        run = self.checked(f)
        self.review(run)
        directory = Path(run["run"])
        before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        status, index, head, inventory = [
            git(run["worktree"], argv)
            for argv in (
                ["status", "--porcelain"],
                ["write-tree"],
                ["rev-parse", "HEAD"],
                ["worktree", "list", "--porcelain"],
            )
        ]
        with patch("software_factory.engine.execute_check", side_effect=AssertionError("reader executed checks")):
            report = self.runs(f)
            recorded = history.inspect(run["run"])
            self.assertFalse(report["errors"])
            self.assertFalse(recorded["errors"])
            self.assertEqual(self.cli("runs", "--repo", f.repo, "--json").returncode, 0)
            self.assertEqual(self.cli("history", "--run", run["run"], "--offset", 100000, "--json").returncode, 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()})
        self.assertEqual(
            [
                git(run["worktree"], argv)
                for argv in (
                    ["status", "--porcelain"],
                    ["write-tree"],
                    ["rev-parse", "HEAD"],
                    ["worktree", "list", "--porcelain"],
                )
            ],
            [status, index, head, inventory],
        )
        self.assertIn("Recorded delivery", self.cli("runs", "--repo", f.repo).stdout)
        self.assertIn("check execution time, not task wall time", self.cli("history", "--run", run["run"]).stdout)

    def test_plan_snapshot_adapter_explicit_absence_no_fallback_and_mutation_defaults(self):
        f = self.fixture()
        run = self.planned(f)
        state = read_run(run["run"])
        self.assertEqual(
            engine.context(state), engine.context(state, captured_plan=(Path(run["run"]) / "plan.md").read_bytes())
        )
        self.assertIsNone(engine.context(state, captured_plan=None)["plan"])
        self.assertEqual(engine.next_action(state, captured_plan=None)["action"], "plan")
        (Path(run["run"]) / "plan.md").write_text("edited plan")
        with self.assertRaisesRegex(FactoryError, "plan"):
            engine.verify(run["run"])

    def test_changed_snapshots_retry_once_then_report_unavailable(self):
        f = self.fixture()
        run = self.checked(f)
        original = history._unchanged
        calls = []

        def once(path, fd, raw):
            calls.append(path)
            if len(calls) == 1:
                raise FactoryError("synthetic change", "snapshot-changed")
            return original(path, fd, raw)

        with patch("software_factory.history._unchanged", side_effect=once):
            report = history.inspect(run["run"])
        self.assertFalse(report["errors"])
        self.assertEqual(len(calls), 2)
        with patch(
            "software_factory.history._unchanged", side_effect=FactoryError("continuous change", "snapshot-changed")
        ):
            report = self.runs(f)
        self.assertEqual(report["total"], 1)
        self.assertFalse(report["runs"][0]["nextAvailable"])
        self.assertTrue(any(item["code"] == "snapshot-changed" for item in report["errors"]))

    def test_directory_open_race_and_descendant_symlinks_never_read_outside(self):
        f = self.fixture()
        run = self.planned(f)
        directory = Path(run["run"])
        outside = f.root / "outside"
        outside.mkdir()
        (outside / "state.json").write_text("outside must never be read")
        saved = directory.with_name("saved-directory")
        original_open = os.open
        swapped = False

        def raced(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == directory.name and flags & os.O_DIRECTORY and not swapped:
                swapped = True
                directory.rename(saved)
                directory.symlink_to(outside, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)

        with patch("software_factory.history.os.open", side_effect=raced):
            report = self.runs(f)
        self.assertEqual(report["total"], 0)
        self.assertTrue(report["errors"])
        self.assertTrue(swapped)
        directory.unlink()
        saved.rename(directory)
        plan = directory / "plan.md"
        plan.unlink()
        plan.symlink_to(outside / "state.json")
        report = self.runs(f)
        self.assertEqual(report["total"], 1)
        self.assertFalse(report["runs"][0]["nextAvailable"])
        self.assertTrue(any("non-regular" in item["message"] for item in report["errors"]))
        lock = directory / "lock"
        lock.symlink_to(outside, target_is_directory=True)
        report = self.runs(f)
        self.assertFalse(report["runs"][0]["nextAvailable"])
        lock.unlink()
        state = directory / "state.json"
        original = state.read_bytes()
        state.unlink()
        state.symlink_to(outside / "state.json")
        report = self.runs(f)
        self.assertEqual(report["total"], 0)
        self.assertTrue(report["errors"])
        state.unlink()
        state.write_bytes(original)
        self.assertEqual((outside / "state.json").read_text(), "outside must never be read")

    def test_bound_metadata_invalid_receipts_metrics_and_top_infrastructure(self):
        f = self.fixture()
        run = self.checked(f)
        first = Path(run["run"]) / "verification-1.json"
        receipt = json.loads(first.read_text())
        receipt["results"][0]["durationMs"] = -4
        receipt["results"][0]["log"] = {"not": "a reference"}
        atomic_json(first, receipt)
        report = history.inspect(run["run"])
        self.assertIsNone(report["attempts"][0]["checks"][0]["durationMs"])
        self.assertIsNone(report["attempts"][0]["checks"][0]["log"])
        self.assertEqual(report["totals"]["missingDurationMetrics"], 1)
        self.assertTrue(any(item["code"] == "metric" for item in report["errors"]))
        first.write_bytes(b"x" * (history.FILE_LIMIT + 1))
        report = history.inspect(run["run"])
        self.assertEqual(report["attempts"][0]["status"], "unavailable")
        self.assertTrue(any("exceeds" in item["message"] for item in report["errors"]))
        with patch("software_factory.history.os.scandir", side_effect=PermissionError("synthetic enumeration denial")):
            with self.assertRaises(FactoryError) as caught:
                self.runs(f)
        self.assertEqual(caught.exception.code, "infrastructure")

    def test_inconsistent_saved_receipt_does_not_become_a_passing_claim(self):
        f = self.fixture()
        run = self.checked(f)
        path = Path(run["run"]) / "verification-1.json"
        receipt = json.loads(path.read_text())
        receipt["results"][0]["passed"] = False
        atomic_json(path, receipt)
        report = history.inspect(run["run"])
        self.assertEqual(report["attempts"][0]["status"], "invalid")
        self.assertIsNone(report["attempts"][0]["passed"])
        self.assertEqual(report["totals"]["knownAttempts"], 0)
        self.assertTrue(any("Inconsistent" in item["message"] for item in report["errors"]))

    def test_deep_metadata_real_cli_isolated_and_state_bytes_preserved(self):
        f = self.fixture()
        healthy = self.planned(f)
        malformed = engine.start(replace(f.options, task="Malformed neighbor"))
        path = Path(malformed["run"]) / "state.json"
        state = read_run(malformed["run"])
        state["criteria"] = None
        content = json.dumps(state).replace('"criteria": null', '"criteria": ' + "[" * 1100 + "0" + "]" * 1100)
        path.write_text(content)
        before = path.read_bytes()
        output = self.cli("runs", "--repo", f.repo, "--json")
        self.assertEqual(output.returncode, 2, output.stderr)
        report = json.loads(output.stdout)
        self.assertEqual([row["id"] for row in report["runs"]], [healthy["id"]])
        self.assertTrue(
            any(error["run"] == malformed["run"] and "nesting" in error["message"] for error in report["errors"])
        )
        self.assertNotIn("Traceback", output.stderr)
        self.assertEqual(before, path.read_bytes())
        state["criteria"] = [{"id": "AC1", "text": ["malformed"]}]
        atomic_json(path, state)
        report = self.runs(f)
        self.assertEqual(report["total"], 1)
        self.assertTrue(any("criteria" in error["message"] for error in report["errors"]))

    def test_history_directory_denial_exit3_and_record_denial_partial2(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from software_factory import cli

        f = self.fixture()
        run = self.planned(f)
        original = os.open

        def deny_directory(path, flags, *args, **kwargs):
            if str(path) == run["run"] and flags & os.O_DIRECTORY:
                raise PermissionError("synthetic directory denial")
            return original(path, flags, *args, **kwargs)

        output, error = io.StringIO(), io.StringIO()
        with (
            patch("software_factory.history.os.open", side_effect=deny_directory),
            redirect_stdout(output),
            redirect_stderr(error),
        ):
            self.assertEqual(cli.main(["history", "--run", run["run"], "--json"]), 3)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(json.loads(error.getvalue())["code"], "infrastructure")

        def deny_state(path, flags, *args, **kwargs):
            if path == "state.json":
                raise PermissionError("synthetic record denial")
            return original(path, flags, *args, **kwargs)

        output, error = io.StringIO(), io.StringIO()
        with (
            patch("software_factory.history.os.open", side_effect=deny_state),
            redirect_stdout(output),
            redirect_stderr(error),
        ):
            self.assertEqual(cli.main(["history", "--run", run["run"], "--json"]), 2)
        self.assertTrue(json.loads(output.getvalue())["errors"])
        self.assertEqual(error.getvalue(), "")
        self.assertEqual(self.cli("history", "--run", str(Path(run["run"]) / "missing"), "--json").returncode, 2)

    def test_saved_review_numeric_overflow_retains_rows_without_traceback(self):
        f = self.fixture()
        healthy = self.planned(f)
        affected = self.planned(replace(f, options=replace(f.options, task="Overflowing saved review")))
        state = read_run(affected["run"])
        state["planReview"]["context"]["syntheticOversizedInteger"] = 10**400
        self.change(affected, planReview=state["planReview"])
        path = Path(affected["run"]) / "state.json"
        before = path.read_bytes()
        output = self.cli("runs", "--repo", f.repo, "--json")
        self.assertEqual(output.returncode, 2, output.stderr)
        report = json.loads(output.stdout)
        rows = {row["id"]: row for row in report["runs"]}
        self.assertEqual(set(rows), {healthy["id"], affected["id"]})
        self.assertTrue(rows[healthy["id"]]["nextAvailable"])
        self.assertFalse(rows[affected["id"]]["nextAvailable"])
        self.assertIsNone(rows[affected["id"]]["nextAction"])
        self.assertTrue(
            any(item["run"] == affected["run"] and item["code"] == "inspection" for item in report["errors"])
        )
        self.assertNotIn("Traceback", output.stderr)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(OverflowError):
            engine.next_action(read_run(affected["run"]))

    def test_extreme_duration_metrics_never_emit_infinity_and_integral_values_are_integers(self):
        f = self.fixture()
        run = self.checked(f)
        path = Path(run["run"]) / "verification-1.json"
        receipt = json.loads(path.read_text())
        self.change(run, checkAttempt=2)
        receipt["results"][0]["durationMs"] = 1e308
        atomic_json(path, receipt)
        atomic_json(Path(run["run"]) / "verification-2.json", receipt)
        output = self.cli("history", "--run", run["run"], "--json")
        self.assertEqual(output.returncode, 2, output.stderr)
        self.assertNotIn("Infinity", output.stdout)
        report = json.loads(output.stdout)
        self.assertEqual(report["totals"]["checkExecutionMs"], 0)
        self.assertEqual(report["totals"]["missingDurationMetrics"], 2)
        self.assertTrue(any(item["code"] == "metric" for item in report["errors"]))
        receipt["results"][0]["durationMs"] = 12.0
        atomic_json(path, receipt)
        atomic_json(Path(run["run"]) / "verification-2.json", receipt)
        report = history.inspect(run["run"])
        self.assertEqual(report["totals"]["checkExecutionMs"], 24)
        self.assertIs(type(report["attempts"][0]["checks"][0]["durationMs"]), int)
        path.write_text(json.dumps(receipt).replace("12.0", "1e400"))
        report = history.inspect(run["run"])
        self.assertEqual(report["attempts"][0]["status"], "invalid")
        self.assertTrue(any("non-finite" in item["message"] for item in report["errors"]))

    def test_continuous_history_drift_makes_metrics_and_attempts_explicitly_unavailable(self):
        f = self.fixture()
        run = self.checked(f)
        with patch(
            "software_factory.history._unchanged", side_effect=FactoryError("continuous change", "snapshot-changed")
        ):
            report = history.inspect(run["run"])
        self.assertTrue(report["errors"])
        self.assertEqual(report["attempts"][0]["status"], "unavailable")
        self.assertIsNone(report["attempts"][0]["passed"])
        self.assertIsNone(report["totals"]["checkExecutionMs"])
        self.assertEqual(report["events"], [])
        self.assertIsNone(report["eventsTotal"])
