"""Real verification monitoring; synthetic fixtures never represent reviews."""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from software_factory import engine, progress
from software_factory.errors import FactoryError
from software_factory.git import git
from software_factory.store import atomic_json, locked, read_run
from tests.support import ROOT, FactoryCase


class ProgressTests(FactoryCase):
    def observe(self, run):
        return progress.observe(read_run(run["run"]))

    def log(self, run, **kwargs):
        return progress.logs(read_run(run["run"]), check_name="behavior", **kwargs)

    def slow(self, *, first=False):
        f = self.fixture()
        ready, release = f.root / "ready", f.root / "release"
        script = (
            "import time\nfrom pathlib import Path\n"
            "print('small live output ✓', flush=True)\n"
            f'Path({str(ready)!r}).write_text("ready")\n'
            f"while not Path({str(release)!r}).exists(): time.sleep(0.01)\n"
        )
        (f.repo / "check.py").write_text(script)
        config = json.loads((f.repo / ".factory.json").read_text())
        config["checks"][0]["timeoutMs"] = 10000
        if first:
            config["checks"].insert(
                0, {"name": "first", "argv": [sys.executable, "-c", 'print("first done")'], "timeoutMs": 2000}
            )
        config["checks"].append(
            {"name": "last", "argv": [sys.executable, "-c", 'print("last done")'], "timeoutMs": 2000}
        )
        atomic_json(f.repo / ".factory.json", config)
        git(f.repo, ["add", "."])
        git(f.repo, ["commit", "-m", "synthetic slow checks"])
        run = self.planned(f)
        child = subprocess.Popen(
            [sys.executable, "-m", "software_factory", "verify", "--run", run["run"], "--json"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def cleanup():
            release.touch()
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
            child.communicate(timeout=5)

        self.addCleanup(cleanup)
        self.wait_for(lambda: ready.exists())
        return run, child, release

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                result = predicate()
                if result:
                    return result
            except FactoryError as error:
                if error.code != "snapshot-changed":
                    raise
            time.sleep(0.02)
        self.fail("Synchronized fixture did not reach its observation condition")

    def test_live_second_process_progress_flushed_small_log_and_readonly(self):
        run, child, release = self.slow(first=True)
        directory = Path(run["run"])
        log = self.wait_for(lambda: self.log(run) if (directory / "check-1-behavior.log").stat().st_size else None)
        self.assertIn("small live output ✓", log["content"])
        self.assertIsNone(log["logTruncated"])
        before = (directory / "state.json").read_bytes()
        owner = (directory / "lock/owner.json").read_bytes()
        status = git(run["worktree"], ["status", "--porcelain"])
        index, head = git(run["worktree"], ["write-tree"]), git(run["worktree"], ["rev-parse", "HEAD"])
        output = self.cli("progress", "--run", run["run"], "--json")
        self.assertEqual(output.returncode, 0, output.stderr)
        report = json.loads(output.stdout)
        self.assertEqual(report["attempt"], 1)
        self.assertEqual(report["status"], "running")
        self.assertEqual(report["activeCheck"], "behavior")
        self.assertGreaterEqual(report["elapsedMs"], 0)
        self.assertEqual([x["status"] for x in report["checks"]], ["passed", "running", "pending"])
        self.assertEqual(report["owner"]["pid"], child.pid)
        self.assertEqual(
            self.cli("logs", "--run", run["run"], "--check-name", "first", "--tail-bytes", 4, "--json").returncode, 0
        )
        self.assertEqual((directory / "state.json").read_bytes(), before)
        self.assertEqual((directory / "lock/owner.json").read_bytes(), owner)
        self.assertEqual(git(run["worktree"], ["status", "--porcelain"]), status)
        self.assertEqual(git(run["worktree"], ["write-tree"]), index)
        self.assertEqual(git(run["worktree"], ["rev-parse", "HEAD"]), head)
        self.assertEqual((directory / progress.SIDECAR).stat().st_mode & 0o777, 0o600)
        release.touch()
        stdout, stderr = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0, stderr)
        final = json.loads(stdout)
        self.assertTrue(final["verification"]["passed"])
        report = self.observe(run)
        self.assertEqual(report["status"], "completed")
        self.assertEqual([x["status"] for x in report["checks"]], ["passed"] * 3)
        self.assertGreaterEqual(report["elapsedMs"], sum(x["result"]["durationMs"] for x in report["checks"]) - 5)
        self.assertFalse(self.log(run)["logTruncated"])

    def test_failure_skips_later_and_preserves_budget_receipt(self):
        f = self.fixture()
        config = json.loads((f.repo / ".factory.json").read_text())
        config["checks"].append(
            {"name": "unrun", "argv": [sys.executable, "-c", 'raise AssertionError("unrun")'], "timeoutMs": 2000}
        )
        atomic_json(f.repo / ".factory.json", config)
        git(f.repo, ["add", "."])
        git(f.repo, ["commit", "-m", "synthetic failfast"])
        run = self.planned(f)
        failed = engine.verify(run["run"])
        state = read_run(run["run"])
        before = (Path(run["run"]) / "state.json").read_bytes()
        report = self.observe(run)
        self.assertEqual(report["status"], "completed")
        self.assertEqual([x["status"] for x in report["checks"]], ["failed", "skipped"])
        self.assertEqual(report["checks"][0]["result"], failed["verification"]["results"][0])
        self.assertEqual(state["failures"], 1)
        self.assertEqual(before, (Path(run["run"]) / "state.json").read_bytes())
        self.assertFalse((Path(run["run"]) / "check-1-unrun.log").exists())
        self.assertEqual(self.cli("logs", "--run", run["run"], "--check-name", "unrun", "--json").returncode, 2)

    def test_handled_sigterm_final_interrupted_without_forged_pass(self):
        run, child, release = self.slow()
        self.wait_for(lambda: self.observe(run)["status"] == "running")
        child.send_signal(signal.SIGTERM)
        stdout, stderr = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 2, stderr)
        final = json.loads(stdout)
        self.assertFalse(final["verification"]["passed"])
        self.assertEqual(read_run(run["run"])["failures"], 1)
        result = self.observe(run)
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(result["checks"][0]["result"]["error"], "Verification interrupted")
        self.assertEqual(result["checks"][1]["status"], "skipped")
        self.assertFalse((Path(run["run"]) / "lock").exists())
        self.assertEqual(self.cli("progress", "--run", run["run"], "--json").returncode, 0)

    def test_not_started_legacy_final_stale_and_malformed_sidecars(self):
        f = self.fixture()
        run = self.planned(f)
        self.assertEqual(self.observe(run)["status"], "not-started")
        self.assertEqual(self.observe(run)["checks"][0]["status"], "pending")
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        done = engine.verify(run["run"])
        path = Path(run["run"]) / progress.SIDECAR
        original = path.read_bytes()
        path.unlink()
        report = self.observe(run)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["elapsedMs"], done["verification"]["results"][0]["durationMs"])
        for content in (b"{broken", json.dumps({"id": "wrong", "attempt": 400}).encode(), original):
            path.write_bytes(content)
            report = self.observe(run)
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["checks"][0]["result"], done["verification"]["results"][0])
        path.unlink()
        path.symlink_to(Path(run["run"]) / "state.json")
        self.assertEqual(self.observe(run)["status"], "completed")
        self.assertTrue(any("unavailable" in x for x in self.observe(run)["limitations"]))

    def active_fixture(self):
        f = self.fixture()
        run = self.planned(f)
        state = read_run(run["run"])
        state.update(checkAttempt=2, verification=None, operation={"kind": "verify", "attempt": 2})
        atomic_json(Path(run["run"]) / "state.json", state)
        return run, state

    def test_active_missing_sidecar_dead_foreign_and_mismatched_owner(self):
        run, state = self.active_fixture()
        self.assertEqual(self.observe(run)["status"], "unknown")
        with locked(run["run"]):
            self.assertEqual(self.observe(run)["status"], "unknown")
            obs = progress.Observation(state)
            obs.begin("behavior")
            self.assertEqual(self.observe(run)["status"], "running")
            path = Path(run["run"]) / "lock/owner.json"
            owner = json.loads(path.read_text())
            foreign = {**owner, "host": "synthetic-other-host"}
            atomic_json(path, foreign)
            self.assertEqual(self.observe(run)["status"], "unknown")
            atomic_json(path, {**owner, "at": "2000-01-01T00:00:00Z"})
            self.assertEqual(self.observe(run)["status"], "unknown")
            atomic_json(path, owner)
            with patch("software_factory.progress.os.kill", side_effect=ProcessLookupError):
                report = self.observe(run)
            self.assertEqual(report["status"], "interrupted")
            self.assertEqual(report["checks"][0]["status"], "unknown")
            with patch("software_factory.progress.os.kill", side_effect=PermissionError):
                self.assertEqual(self.observe(run)["status"], "unknown")
            self.assertTrue(path.exists())

    def test_latest_attempt_never_reuses_previous_results_clock_clamp_and_drift(self):
        f = self.fixture()
        run = self.checked(f)
        state = read_run(run["run"])
        state.update(checkAttempt=2, verification=None, operation={"kind": "verify", "attempt": 2})
        atomic_json(Path(run["run"]) / "state.json", state)
        report = self.observe(run)
        self.assertEqual(report["attempt"], 2)
        self.assertEqual(report["status"], "unknown")
        self.assertIsNone(report["checks"][0]["result"])
        with locked(run["run"]):
            obs = progress.Observation(state)
            obs.begin("behavior")
            obs.data["startedAt"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
            obs.write()
            report = self.observe(run)
            self.assertEqual(report["elapsedMs"], 0)
            self.assertTrue(any("clamped" in x for x in report["limitations"]))
            original = progress._snapshot
            calls = 0

            def changing(value):
                nonlocal calls
                calls += 1
                if calls == 2:
                    obs.data["activeCheck"] = None
                    obs.data["checks"][0]["status"] = "pending"
                    obs.write()
                return original(value)

            with (
                patch("software_factory.progress._snapshot", side_effect=changing),
                self.assertRaisesRegex(FactoryError, "changed"),
            ):
                self.observe(run)

    def test_bounded_log_tail_replacement_and_historical_writer_flag(self):
        f = self.fixture()
        run = self.checked(f)
        path = Path(run["run"]) / "check-1-behavior.log"
        path.write_bytes(b"A" * 100000 + b"\xfftail")
        report = self.log(run, tail_bytes=5)
        self.assertEqual(report["content"], "�tail")
        self.assertEqual(report["bytesRead"], 5)
        self.assertTrue(report["tailTruncated"])
        self.assertFalse(report["logTruncated"])
        self.assertEqual(report["encoding"], "utf-8 with replacement")
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        engine.verify(run["run"])
        report = self.log(run, attempt=1, tail_bytes=1)
        self.assertEqual(report["attempt"], 1)
        self.assertEqual(report["content"], "l")
        self.assertFalse(report["logTruncated"])
        self.assertEqual(self.log(run)["attempt"], 2)
        self.assertEqual(
            self.cli(
                "logs", "--run", run["run"], "--check-name", "behavior", "--tail-bytes", 65536, "--json"
            ).returncode,
            0,
        )

    def test_invalid_log_inputs_symlink_nonregular_and_read_race(self):
        f = self.fixture()
        run = self.checked(f)
        for kwargs in (
            {"attempt": 0},
            {"attempt": 2},
            {"attempt": True},
            {"tail_bytes": 0},
            {"tail_bytes": 65537},
            {"tail_bytes": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(FactoryError):
                self.log(run, **kwargs)
        with self.assertRaises(FactoryError):
            progress.logs(read_run(run["run"]), check_name="../state")
        path = Path(run["run"]) / "check-1-behavior.log"
        path.unlink()
        path.symlink_to(Path(run["run"]) / "state.json")
        with self.assertRaisesRegex(FactoryError, "regular"):
            self.log(run)
        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(FactoryError, "regular"):
            self.log(run)
        path.rmdir()
        path.write_bytes(b"output")
        original = progress._stable

        def drift(state, before):
            changed = dict(state)
            changed["checkAttempt"] = 2
            atomic_json(Path(run["run"]) / "state.json", changed)
            original(state, before)

        with (
            patch("software_factory.progress._stable", side_effect=drift),
            self.assertRaisesRegex(FactoryError, "changed"),
        ):
            self.log(run)

    def test_exception_observation_no_receipt_or_failure_budget_and_cli_labels(self):
        f = self.fixture()
        run = self.planned(f)
        with patch(
            "software_factory.engine.execute_check", side_effect=FactoryError("synthetic infra", "infrastructure")
        ):
            with self.assertRaises(FactoryError):
                engine.verify(run["run"])
        state = read_run(run["run"])
        self.assertIsNone(state["verification"])
        self.assertEqual(state["failures"], 0)
        self.assertFalse((Path(run["run"]) / "verification-1.json").exists())
        self.assertEqual(json.loads((Path(run["run"]) / progress.SIDECAR).read_text())["status"], "interrupted")
        self.assertEqual(self.observe(run)["status"], "unknown")
        self.assertIn("Verification attempt", self.cli("progress", "--run", run["run"]).stdout)
        self.assertEqual(self.cli("logs", "--run", run["run"], "--check-name", "behavior", "--json").returncode, 2)
        self.assertIn("progress", self.cli("--help").stdout)
        self.assertIn("--tail-bytes", self.cli("--help").stdout)

    def test_settings_budget_is_reviewed_source_only(self):
        root = ROOT
        from software_factory.rules import read_project

        project = read_project(str(root))
        self.assertEqual(project["config"]["checks"][0]["argv"], ["python3", "scripts/verify.py", "tests"])
        self.assertEqual(project["config"]["checks"][0]["timeoutMs"], 300000)
        self.assertEqual(project["config"]["checks"][1]["timeoutMs"], 30000)
        f = self.fixture()
        run = self.planned(f)
        self.rule(run["worktree"], "guidance.md", "Reviewed source settings differ from frozen runtime.\n")
        self.assertEqual(read_run(run["run"])["config"]["checks"][0]["timeoutMs"], 2000)

    def test_log_seek_bound_and_readers_do_not_execute_or_mutate_receipts(self):
        f = self.fixture()
        run = self.checked(f)
        directory = Path(run["run"])
        (directory / "check-1-behavior.log").write_bytes(b"x" * (1024 * 1024))
        files = {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
        original = os.fdopen
        reads, seeks = [], []

        class Bounded:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def fileno(self):
                return self.stream.fileno()

            def seek(self, offset):
                seeks.append(offset)
                return self.stream.seek(offset)

            def read(self, bound):
                reads.append(bound)
                return self.stream.read(bound)

        def wrapped(fd, *args, **kwargs):
            stream = original(fd, *args, **kwargs)
            if os.fstat(fd).st_size == 1024 * 1024:
                return Bounded(stream)
            return stream

        with (
            patch("software_factory.progress.os.fdopen", side_effect=wrapped),
            patch("software_factory.engine.execute_check", side_effect=AssertionError("reader executed a check")),
        ):
            self.assertEqual(self.log(run, tail_bytes=13)["content"], "x" * 13)
            self.assertEqual(self.observe(run)["status"], "completed")
        self.assertEqual(reads, [13])
        self.assertEqual(seeks, [1024 * 1024 - 13])
        self.assertEqual(files, {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()})

    def test_log_metadata_and_open_errors_are_infrastructure(self):
        f = self.fixture()
        run = self.checked(f)
        original = os.open

        def unavailable(path, *args, **kwargs):
            if str(path).endswith("check-1-behavior.log"):
                raise PermissionError("synthetic log denial")
            return original(path, *args, **kwargs)

        with (
            patch("software_factory.progress.os.open", side_effect=unavailable),
            self.assertRaises(FactoryError) as caught,
        ):
            self.log(run)
        self.assertEqual(caught.exception.code, "infrastructure")

    def test_missing_corrupt_sidecar_during_live_attempt_stays_unknown(self):
        run, state = self.active_fixture()
        with locked(run["run"]):
            obs = progress.Observation(state)
            path = Path(run["run"]) / progress.SIDECAR
            for content in (
                b"{invalid",
                json.dumps({**obs.data, "attempt": 1}).encode(),
                json.dumps({**obs.data, "owner": {}}).encode(),
            ):
                path.write_bytes(content)
                report = self.observe(run)
                self.assertEqual(report["status"], "unknown")
                self.assertIsNone(report["checks"][0]["result"])
                self.assertTrue(any("stale" in x for x in report["limitations"]))
            path.unlink()
            self.assertEqual(self.observe(run)["status"], "unknown")

    def test_progress_cli_exit_uses_the_same_snapshot_and_readable_facts(self):
        import io
        from contextlib import redirect_stdout

        from software_factory import cli

        f = self.fixture()
        run = self.checked(f)
        state = read_run(run["run"])
        state["phase"] = "blocked"
        atomic_json(Path(run["run"]) / "state.json", state)
        original = cli.read_run
        calls = []

        def once(path):
            calls.append(path)
            if len(calls) > 1:
                raise AssertionError("CLI re-read state after coherent observation")
            return original(path)

        output = io.StringIO()
        with patch("software_factory.cli.read_run", side_effect=once), redirect_stdout(output):
            self.assertEqual(cli.main(["progress", "--run", run["run"], "--json"]), 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "completed")
        self.assertEqual(len(calls), 1)
        human = cli.format_output("progress", report)
        for value in (report["id"], report["observedAt"], "durationMs", "exitCode"):
            self.assertIn(value, human)
        self.assertIn("Encoding: utf-8 with replacement", cli.format_output("logs", self.log(run)))

    def test_unrepresentable_owner_pid_never_probed_or_crashes_real_cli(self):
        run, state = self.active_fixture()
        with locked(run["run"]):
            observation = progress.Observation(state)
            path = Path(run["run"]) / "lock/owner.json"
            owner = json.loads(path.read_text())
            before = (Path(run["run"]) / "state.json").read_bytes()
            for malformed in (10**100, 1e100):
                atomic_json(path, {**owner, "pid": malformed})
                observation.data["owner"] = {**owner, "pid": malformed}
                observation.write()
                owner_bytes = path.read_bytes()
                with patch("software_factory.progress.os.kill", side_effect=AssertionError("malformed PID was probed")):
                    report = self.observe(run)
                self.assertEqual(report["status"], "unknown")
                self.assertTrue(any("OS range" in item for item in report["limitations"]))
                output = self.cli("progress", "--run", run["run"], "--json")
                self.assertEqual(output.returncode, 0, output.stderr)
                self.assertEqual(json.loads(output.stdout)["status"], "unknown")
                self.assertNotIn("Traceback", output.stderr)
                self.assertEqual(before, (Path(run["run"]) / "state.json").read_bytes())
                self.assertEqual(owner_bytes, path.read_bytes())
