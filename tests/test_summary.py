"""Exact, read-only CLI summaries across task and delivery states."""

import os
import socket
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from software_factory import engine
from software_factory.delivery import deliver
from software_factory.errors import FactoryError
from software_factory.git import git
from software_factory.store import atomic_json, locked, read_json, read_run
from tests.support import FactoryCase


class SummaryTests(FactoryCase):
    def test_multiline_exact_values_and_human_labels_before_checks(self):
        f = self.fixture()
        task = "Fix “empty” output\n\nKeep values: false, 0, `literal` and unicode ✓"
        run = engine.start(
            replace(f.options, task=task, criteria=["Value equals new", "Keep second criterion\nwith detail"])
        )
        result = self.summary(run)
        self.assertEqual(
            set(result),
            {"id", "task", "phase", "endpoint", "criteria", "checks", "verification", "findings", "next", "delivery"},
        )
        self.assertEqual(result["task"], task)
        self.assertEqual(result["criteria"], run["criteria"])
        self.assertEqual(result["checks"], [{**check, "result": None} for check in run["checks"]])
        self.assertIsNone(result["verification"])
        self.assertIsNone(result["delivery"])
        self.assertEqual(result["findings"], {"plan": [], "code": []})
        self.assertEqual(result["next"], {"action": "plan"})
        human = self.summary(run, human=True)
        for label in ("Task:", "Criteria:", "Checks:", "Findings:", "Next:", "Delivery:"):
            self.assertIn(label, human)
        self.assertIn(task, human)
        self.assertIn("AC2: Keep second criterion", human)
        self.assertIn("behavior: not run", human)
        self.assertIn("Delivery: pending", human)
        self.assertNotIn('"evidence"', human)

    def test_failed_skipped_diagnostics_and_repair(self):
        f = self.fixture()
        config = read_json(f.repo / ".factory.json")
        config["checks"].append({"name": "later", "argv": [sys.executable, "-c", "pass"], "timeoutMs": 2000})
        atomic_json(f.repo / ".factory.json", config)
        git(f.repo, ["add", ".factory.json"])
        git(f.repo, ["commit", "-m", "second check"])
        run = self.planned(f)
        failed = engine.verify(run["run"])
        result = self.summary(failed)
        self.assertEqual(result["checks"][0]["result"], read_run(run["run"])["verification"]["results"][0])
        self.assertEqual(result["checks"][0]["result"]["exitCode"], 1)
        self.assertIsNone(result["checks"][1]["result"])
        self.assertEqual(
            result["verification"], {"passed": False, "unchanged": True, "at": failed["verification"]["at"]}
        )
        self.assertEqual(result["next"], failed["next"])
        human = self.summary(failed, human=True)
        self.assertIn("behavior: failed", human)
        self.assertIn("later: not run", human)
        self.assertIn(failed["verification"]["results"][0]["log"], human)
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        passed = engine.verify(run["run"])
        self.assertEqual(self.summary(passed)["next"]["action"], "review")
        self.assertTrue(all(check["result"]["passed"] for check in self.summary(passed)["checks"]))
        (Path(run["worktree"]) / "extra").write_text("drift")
        stale = self.summary(passed)
        self.assertTrue(stale["verification"]["passed"])
        self.assertEqual(stale["next"]["action"], "verify")

    def test_latest_rejected_findings_and_superseded_reviews(self):
        run = self.planned(self.fixture())
        finding = {"severity": "major", "location": "plan:7", "issue": "Missing edge case\nexact detail"}
        context = read_run(run["run"])["planReview"]["context"]
        run = engine.submit_plan_review(
            run["run"],
            self.json_file(
                run["run"],
                "rejected-plan.json",
                {"reviewer": "synthetic fixture", "verdict": "fail", "context": context, "findings": [finding]},
            ),
        )
        self.assertEqual(self.summary(run)["findings"], {"plan": [finding], "code": []})
        self.assertEqual(self.summary(run)["next"]["action"], "plan")
        self.assertIn(finding["issue"], self.summary(run, human=True))
        self.approve_plan(run)
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        run = engine.verify(run["run"])
        finding = {"severity": "major", "location": "value.txt:1", "issue": "Missing review coverage"}
        run = self.review(run, verdict="fail", findings=[finding])
        self.assertEqual(self.summary(run)["findings"], {"plan": [], "code": [finding]})
        self.assertEqual(self.summary(run)["next"]["action"], "implement")
        self.assertIn("code major value.txt:1", self.summary(run, human=True))
        run = engine.verify(run["run"])
        minor = {"severity": "minor", "location": "value.txt:1", "issue": "Optional polish"}
        run = self.review(run, findings=[minor])
        self.assertEqual(self.summary(run)["findings"], {"plan": [], "code": [minor]})

    def test_timeout_and_executable_error_details(self):
        for timeout in (True, False):
            f = self.fixture()
            config = read_json(f.repo / ".factory.json")
            config["checks"][0] = {
                "name": "timeout" if timeout else "missing",
                "argv": [sys.executable, "-c", "import time; time.sleep(30)"] if timeout else ["/not/a/real/program"],
                "timeoutMs": 100,
            }
            atomic_json(f.repo / ".factory.json", config)
            git(f.repo, ["add", ".factory.json"])
            git(f.repo, ["commit", "-m", "diagnostic check"])
            run = self.planned(f)
            failed = engine.verify(run["run"])
            result = self.summary(failed)["checks"][0]["result"]
            self.assertEqual(result, read_run(run["run"])["verification"]["results"][0])
            self.assertIsNone(result["exitCode"])
            self.assertEqual(result["timedOut"], timeout)
            human = self.summary(failed, human=True)
            self.assertIn("timeout" if timeout else result["error"], human)

    def test_wait_preparing_blocked_and_completed_readonly(self):
        f = self.fixture()
        run = engine.start(f.options)
        with locked(run["run"]):
            output = self.summary(run)
            self.assertEqual(output["next"]["action"], "wait")
            self.assertEqual(output["next"]["owner"]["pid"], os.getpid())
            self.assertEqual(output["next"]["owner"]["host"], socket.gethostname())
        state = read_run(run["run"])
        state["phase"] = "preparing"
        atomic_json(Path(run["run"]) / "state.json", state)
        self.assertEqual(self.summary(run)["next"]["action"], "resume")
        engine.resume(run["run"])
        run = self.planned(f)
        engine.verify(run["run"])
        engine.verify(run["run"])
        run = engine.verify(run["run"])
        self.assertEqual(
            self.summary(run)["next"],
            {"action": "blocked", "reason": "Repair limit reached.", "failures": 3, "limit": 3},
        )
        engine.extend(run["run"], 1, "Synthetic test user direction")
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        run = self.review(engine.verify(run["run"]))
        run = deliver(run["run"])
        output = self.summary(run)
        self.assertEqual(output["phase"], "done")
        self.assertEqual(output["delivery"], run["delivery"])
        self.assertEqual(output["next"]["action"], "done")
        self.assertEqual(output["next"]["receipt"], str(Path(run["run"]) / "delivery.json"))
        self.assertIn(run["delivery"]["commit"], self.summary(run, human=True))
        self.assertIn("Delivery: local", self.summary(run, human=True))

    def test_pending_and_completed_draft_receipts(self):
        f = self.fixture("draft-pr")
        file = self.github(f)
        run = self.reviewed(f)
        with patch.dict(os.environ, {"MOCK_FAIL": "1"}), self.assertRaises(FactoryError):
            deliver(run["run"])
        partial = self.summary(run)
        self.assertEqual(partial["delivery"], read_run(run["run"])["delivery"])
        self.assertTrue(partial["delivery"]["commit"])
        self.assertNotIn("pr", partial["delivery"])
        self.assertEqual(partial["next"]["action"], "deliver")
        self.assertEqual(partial["next"]["reason"], "Reconcile interrupted delivery.")
        self.assertIn("PR: pending", self.summary(run, human=True))
        self.assertTrue(file.exists())
        run = deliver(run["run"])
        complete = self.summary(run)
        self.assertEqual(complete["delivery"], run["delivery"])
        self.assertIn(run["delivery"]["pr"], self.summary(run, human=True))
        self.assertEqual(complete["next"]["action"], "done")
