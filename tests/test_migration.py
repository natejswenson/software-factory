"""Version-1 fingerprints, compliant branches and guarded rename recovery."""

import json
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from software_factory import engine
from software_factory.checks import validate_config
from software_factory.delivery import deliver
from software_factory.errors import FactoryError
from software_factory.git import git
from software_factory.store import atomic_json, fingerprint, read_json, read_run
from tests.support import ROOT, FactoryCase


class MigrationTests(FactoryCase):
    def test_integral_github_json_numbers_remain_compatible(self):
        f = self.fixture("draft-pr")
        file = self.github(f)
        original = engine.command

        def response(argv, cwd, **kwargs):
            value = original(argv, cwd, **kwargs)
            if argv[:2] == ["gh", "issue"]:
                issue = json.loads(value)
                issue["number"] = 42.0
                return json.dumps(issue)
            return value

        with patch("software_factory.engine.command", response):
            run = engine.start(replace(f.options, task=None, issue="42"))
        self.assertEqual(read_run(run["run"])["source"]["snapshot"]["number"], 42)
        run = self.reviewed(f)
        with patch.dict(os.environ, {"MOCK_FAIL": "1"}), self.assertRaises(FactoryError):
            deliver(run["run"])
        atomic_json(file, {**read_json(file), "number": 1.0})
        result = deliver(run["run"])
        self.assertEqual(result["phase"], "done")
        self.assertEqual(result["delivery"]["number"], 1)

    def test_legacy_integral_json_numbers_remain_valid(self):
        config = json.loads(
            '{"version":1.0,"endpoint":"local","checks":[{"name":"test","argv":["python3"],"timeoutMs":1e3}]}'
        )
        self.assertEqual(validate_config(config), config)
        for version in (True, "1"):
            with self.assertRaises(FactoryError):
                validate_config({**config, "version": version})
        for timeout in (True, 100.5, float("inf"), float("nan")):
            with self.assertRaises(FactoryError):
                validate_config({**config, "checks": [{**config["checks"][0], "timeoutMs": timeout}]})

    def test_original_node_hash_vectors(self):
        vectors = json.loads((ROOT / "tests/fixtures/node-v1-hashes.json").read_text())
        self.assertIn("Original Node v1", vectors["source"])
        for case in vectors["cases"]:
            with self.subTest(case=case):
                value = json.loads(case["rawJson"]) if "rawJson" in case else case["text"]
                self.assertEqual(fingerprint(value), case["digest"])

    def test_default_and_explicit_convention_branches(self):
        f = self.fixture()
        run = engine.start(f.options)
        self.assertRegex(run["branch"], r"^feature/change-old-to-new-[a-f0-9]{8}$")
        for branch in ("feature/explicit", "bug/specific-fix", "issue/42-migration"):
            result = engine.start(replace(f.options, task=branch, branch=branch))
            self.assertEqual(result["branch"], branch)
        for branch in (
            "factory/old",
            "feature/UPPER",
            "feature/a/b",
            "feature/-bad",
            "bug/name.lock",
            "main",
            "issue/a--b",
        ):
            with self.subTest(branch=branch), self.assertRaisesRegex(FactoryError, "Branch must"):
                engine.start(replace(f.options, task=branch, branch=branch))
        with self.assertRaisesRegex(FactoryError, "already exists"):
            engine.start(replace(f.options, task="different task", branch="feature/explicit"))
        with self.assertRaisesRegex(FactoryError, "different branch"):
            engine.start(replace(f.options, branch="feature/other"))

    def test_rename_invalidates_proofs_records_ownership_and_is_idempotent(self):
        run = self.reviewed(self.fixture())
        renamed = engine.rename_branch(run["run"], "feature/python-migration")
        self.assertEqual(renamed["branch"], "feature/python-migration")
        self.assertEqual(git(run["worktree"], ["branch", "--show-current"]).strip(), renamed["branch"])
        state = read_run(run["run"])
        self.assertIsNone(state["verification"])
        self.assertIsNone(state["codeReview"])
        self.assertIsNone(state["renameIntent"])
        self.assertEqual(state["history"][-1]["action"], "branch-renamed")
        self.assertEqual(renamed["next"]["action"], "verify")
        self.assertEqual(engine.rename_branch(run["run"], renamed["branch"])["branch"], renamed["branch"])
        with self.assertRaisesRegex(FactoryError, "current verification"):
            deliver(run["run"])

    def test_rename_recovers_before_and_after_git_mutation(self):
        for after in (False, True):
            with self.subTest(after=after):
                run = self.planned(self.fixture())
                original_git = engine.git

                def interrupted(cwd, args, **kwargs):
                    if args[:2] == ["branch", "-m"]:
                        if after:
                            original_git(cwd, args, **kwargs)
                        raise FactoryError("Synthetic rename interruption", "infrastructure")
                    return original_git(cwd, args, **kwargs)

                with (
                    patch("software_factory.engine.git", interrupted),
                    self.assertRaisesRegex(FactoryError, "interruption"),
                ):
                    engine.rename_branch(run["run"], "feature/renamed")
                self.assertEqual(engine.describe(read_run(run["run"]))["next"]["action"], "resume")
                result = engine.resume(run["run"])
                self.assertEqual(result["branch"], "feature/renamed")
                self.assertIsNone(read_run(run["run"])["renameIntent"])

    def test_rename_rejects_collisions_head_drift_and_delivery(self):
        run = self.planned(self.fixture())
        git(run["worktree"], ["branch", "feature/collision"])
        with self.assertRaisesRegex(FactoryError, "already exists"):
            engine.rename_branch(run["run"], "feature/collision")
        original_git = engine.git

        def interrupted(cwd, args, **kwargs):
            if args[:2] == ["branch", "-m"]:
                raise FactoryError("interruption")
            return original_git(cwd, args, **kwargs)

        with patch("software_factory.engine.git", interrupted), self.assertRaises(FactoryError):
            engine.rename_branch(run["run"], "feature/rename")
        git(run["worktree"], ["commit", "--allow-empty", "-m", "unexpected HEAD"])
        with self.assertRaisesRegex(FactoryError, "HEAD changed"):
            engine.resume(run["run"])
        f = self.fixture("draft-pr")
        self.github(f)
        run = self.reviewed(f)
        with patch.dict(os.environ, {"MOCK_FAIL": "1"}), self.assertRaises(FactoryError):
            deliver(run["run"])
        with self.assertRaisesRegex(FactoryError, "before delivery"):
            engine.rename_branch(run["run"], "feature/no-rename")

    def test_cli_invalid_inputs_return_json_without_traceback(self):
        for argv in (["start", "--bad-option"], ["unknown"], ["extend", "--attempts", "nan"], ["status", "extra"]):
            result = self.cli(*argv, "--json")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)["code"], "invalid")
            self.assertNotIn("Traceback", result.stderr)

    def test_bundled_skill_path_and_python_entrypoint(self):
        result = self.cli("skill-path")
        self.assertEqual(result.returncode, 0, result.stderr)
        skill = Path(result.stdout.strip())
        self.assertTrue((skill / "SKILL.md").is_file())
        self.assertTrue((skill / "protocol.md").is_file())
        self.assertEqual((ROOT / "skills/software-factory").resolve(), skill)
        self.assertIn("Software Factory", self.cli("--help").stdout)
