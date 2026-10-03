"""Repository scope, frozen settings and Markdown freshness behavior."""

import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

from software_factory import engine
from software_factory.delivery import deliver
from software_factory.errors import FactoryError
from software_factory.git import git, snapshot
from software_factory.rules import read_project, read_rules, settings
from software_factory.store import atomic_json, read_json, read_run
from tests.support import FactoryCase, config_fence


class RulesTests(FactoryCase):
    def test_init_markdown_without_overwriting_rules(self):
        f = self.fixture()
        (f.repo / ".factory.json").unlink()
        self.rule(f.repo, "conventions.md", "# Conventions\nUse built-in modules.\n")
        checks = [{"name": "behavior", "argv": [sys.executable, "check.py"], "timeoutMs": 2000}]
        initialized = engine.init(str(f.repo), checks)
        self.assertEqual(initialized["config"], str(f.repo / ".rules" / "factory.md"))
        self.assertEqual(read_project(f.repo)["config"]["checks"], checks)
        self.assertIn("built-in modules", (f.repo / ".rules" / "conventions.md").read_text())
        with self.assertRaisesRegex(FactoryError, "already exists"):
            engine.init(str(f.repo), checks)
        self.commit_rules(f)
        run = self.checked(f)
        self.assertTrue(run["verification"]["passed"])
        self.review(run)
        local = replace(f, options=replace(f.options, endpoint="local"))
        self.assertEqual(deliver(self.reviewed(local)["run"])["phase"], "done")

    def test_split_sorted_markdown_is_repository_scoped(self):
        a, b = self.fixture(), self.fixture("draft-pr")
        config = read_json(a.repo / ".factory.json")
        (a.repo / ".factory.json").unlink()
        self.rule(a.repo, "20-checks.md", config_fence({"checks": config["checks"]}, "Use tests from repo A."))
        self.rule(a.repo, "10-policy.md", config_fence({"endpoint": "local", "version": 1}, "Plan repo A carefully."))
        self.rule(a.repo, "skip.txt", "not a rule")
        nested = a.repo / ".rules" / "nested"
        nested.mkdir()
        (nested / "skip.md").write_text(config_fence({"unknown": True}))
        self.rule(b.repo, "guide.md", "Instructions for repo B only.")
        self.commit_rules(a)
        self.commit_rules(b)
        ar, br = self.planned(a), engine.start(b.options)
        rules = engine.task_rules(read_run(ar["run"]))
        self.assertEqual([file["path"] for file in rules["files"]], [".rules/10-policy.md", ".rules/20-checks.md"])
        self.assertNotIn("repo B", json.dumps(rules))
        self.assertIn("repo B", engine.task_rules(read_run(br["run"]))["files"][0]["content"])
        self.assertEqual(ar["checks"], config["checks"])
        self.assertEqual(read_run(ar["run"])["planReview"]["context"]["rules"], rules["hash"])
        self.assertNotEqual(read_run(ar["run"])["configHash"], read_run(br["run"])["configHash"])
        self.assertEqual(ar["endpoint"], "local")
        self.assertEqual(br["endpoint"], "draft-pr")

    def test_overrides_exact_cli_content_resume_and_source_isolation(self):
        f = self.fixture("draft-pr")
        content = config_fence({"endpoint": "local"}, "Keep Unicode ✓, false, 0 and literal `commands`.\nSecond line.")
        self.rule(f.repo, "policy.md", content)
        self.commit_rules(f)
        run = engine.start(f.options)
        self.assertEqual(run["endpoint"], "local")
        output = self.cli("rules", "--run", run["run"], "--json")
        self.assertEqual(output.returncode, 0, output.stderr)
        rules = json.loads(output.stdout)
        self.assertEqual(rules["files"][0]["content"], content)
        self.assertIn("# .rules/policy.md", self.cli("rules", "--run", run["run"]).stdout)
        self.assertEqual(read_json(rules["snapshot"]), read_run(run["run"])["rules"]["initial"])
        resumed = json.loads(self.cli("resume", "--run", run["run"], "--json").stdout)
        self.assertEqual(resumed["rules"]["initialHash"], rules["hash"])
        self.rule(f.repo, "policy.md", "original checkout changed")
        self.assertEqual(engine.task_rules(read_run(run["run"]))["files"][0]["content"], content)

    def test_missing_rules_and_historical_exact_protocol(self):
        run = self.planned(self.fixture())
        self.assertEqual(engine.task_rules(read_run(run["run"]))["files"], [])
        state = read_run(run["run"])
        # Synthetic pre-rules run; only this temporary test state is adjusted.
        del state["rules"]
        del state["planReview"]["context"]["rules"]
        atomic_json(Path(run["run"]) / "state.json", state)
        self.rule(run["worktree"], "new.md", "Do not retroactively change a historical run.")
        self.assertFalse(engine.task_rules(read_run(run["run"]))["enabled"])
        self.assertEqual(engine.describe(read_run(run["run"]))["next"]["action"], "implement")
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        verified = engine.verify(run["run"])
        self.assertNotIn("rules", verified["next"]["evidence"])
        self.review(verified)
        self.assertEqual(deliver(run["run"])["phase"], "done")

    def test_edits_additions_removals_invalidate_all_downstream_proof(self):
        for operation in ("edit", "add", "remove"):
            with self.subTest(operation=operation):
                f = self.fixture()
                self.rule(f.repo, "guide.md", "Original instructions.")
                self.commit_rules(f)
                run = self.reviewed(f)
                initial = Path(run["rules"]["snapshot"]).read_bytes()
                stale = read_run(run["run"])["codeReview"]
                if operation == "edit":
                    self.rule(run["worktree"], "guide.md", "Updated instructions.")
                elif operation == "add":
                    self.rule(run["worktree"], "more.md", "Additional instructions.")
                else:
                    (Path(run["worktree"]) / ".rules" / "guide.md").unlink()
                self.assertEqual(engine.describe(read_run(run["run"]))["next"]["action"], "plan-review")
                with self.assertRaisesRegex(FactoryError, "plan review"):
                    engine.verify(run["run"])
                with self.assertRaisesRegex(FactoryError, "plan review"):
                    deliver(run["run"])
                self.assertEqual(Path(run["rules"]["snapshot"]).read_bytes(), initial)
                self.approve_plan(run)
                fresh = engine.verify(run["run"])
                self.assertTrue(fresh["verification"]["passed"])
                with self.assertRaisesRegex(FactoryError, "stale"):
                    engine.submit_review(run["run"], self.json_file(run["run"], "stale.json", stale))
                self.review(fresh)
                self.assertEqual(deliver(run["run"])["phase"], "done")

    def test_ignored_rules_invalidate_interrupted_commit(self):
        f = self.fixture()
        (f.repo / ".gitignore").write_text("ignored*\n.rules/local.md\n")
        git(f.repo, ["add", ".gitignore"])
        git(f.repo, ["commit", "-m", "ignore local rule fixture"])
        run = self.reviewed(f)
        state = read_run(run["run"])
        before = snapshot(run["worktree"], state["base"])
        state["commitIntent"] = {"parent": before["head"], "tree": before["tree"], "paths": before["paths"]}
        atomic_json(Path(run["run"]) / "state.json", state)
        git(run["worktree"], ["add", "--", *before["paths"]])
        git(run["worktree"], ["commit", "-m", "synthetic interrupted delivery"])
        self.rule(run["worktree"], "local.md", "Ignored but relevant instructions.")
        self.assertEqual(snapshot(run["worktree"], state["base"])["tree"], before["tree"])
        self.assertEqual(engine.describe(read_run(run["run"]))["next"]["action"], "plan-review")
        with self.assertRaisesRegex(FactoryError, "plan review"):
            deliver(run["run"])
        self.approve_plan(run)
        self.review(engine.verify(run["run"]))
        self.assertEqual(deliver(run["run"])["phase"], "done")

    def test_settings_edits_keep_frozen_checks_and_endpoint(self):
        f = self.fixture()
        self.rule(f.repo, "factory.md", config_fence({"endpoint": "local"}))
        self.commit_rules(f)
        run = self.reviewed(f)
        weaker = [{"name": "fake", "argv": [sys.executable, "-c", "pass"], "timeoutMs": 1000}]
        self.rule(run["worktree"], "factory.md", config_fence({"endpoint": "draft-pr", "checks": weaker}))
        self.assertEqual(engine.describe(read_run(run["run"]))["next"]["action"], "plan-review")
        with self.assertRaisesRegex(FactoryError, "plan review"):
            deliver(run["run"])
        self.assertEqual(read_run(run["run"])["config"]["checks"], run["checks"])
        self.approve_plan(run)
        (Path(run["worktree"]) / "value.txt").write_text("old\n")
        failed = engine.verify(run["run"])
        self.assertFalse(failed["verification"]["passed"])
        self.assertEqual(failed["verification"]["results"][0]["name"], "behavior")
        self.assertEqual(failed["endpoint"], "local")
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        self.review(engine.verify(run["run"]))
        self.assertEqual(deliver(run["run"])["phase"], "done")
        new = engine.start(replace(f.options, repo=run["worktree"], base=run["branch"], task="Use new settings"))
        self.assertEqual(new["checks"], weaker)
        self.assertEqual(new["endpoint"], "draft-pr")

    def test_selected_base_must_match_committed_rules(self):
        f = self.fixture()
        self.rule(f.repo, "guide.md", "Uncommitted instructions")
        with self.assertRaisesRegex(FactoryError, "committed on the selected base"):
            engine.start(f.options)
        self.commit_rules(f)
        git(f.repo, ["branch", "lower"])
        self.rule(f.repo, "guide.md", "New instructions")
        self.commit_rules(f)
        with self.assertRaisesRegex(FactoryError, "committed on the selected base"):
            engine.start(replace(f.options, base="lower"))
        self.assertEqual(engine.start(f.options)["phase"], "plan")

    def test_malformed_duplicate_unknown_and_empty_settings(self):
        f = self.fixture()
        cases = [
            ("```factory-config\n{bad}\n```", "invalid factory configuration JSON"),
            ("```factory-config\n{}", "unterminated"),
            (config_fence({"version": 2}), "version 1"),
            (config_fence({"checks": []}), "at least one"),
            (config_fence({"checks": [{"name": "test", "argv": "python test", "timeoutMs": 1000}]}), "argv"),
            (config_fence({"unexpected": True}), "unknown factory setting"),
            ('```factory-config\n{"endpoint":"local","end\\u0070oint":"draft-pr"}\n```', "duplicate JSON key"),
            ('```factory-config\n{"checks":[{"name":"a","name":"b"}]}\n```', "duplicate JSON key"),
            (config_fence({"endpoint": "local"}) * 2, "duplicate factory setting"),
            (config_fence(None), "JSON object"),
        ]
        for body, pattern in cases:
            with self.subTest(pattern=pattern):
                self.rule(f.repo, "bad.md", body)
                with self.assertRaisesRegex(FactoryError, pattern):
                    read_project(f.repo)
        self.rule(f.repo, "bad.md", config_fence({"endpoint": "local"}))
        self.rule(f.repo, "other.md", config_fence({"endpoint": "draft-pr"}))
        with self.assertRaisesRegex(FactoryError, "duplicate factory setting"):
            read_project(f.repo)

    def test_outer_example_fences_are_not_settings(self):
        f = self.fixture()
        self.rule(
            f.repo,
            "examples.md",
            '````markdown\n```factory-config\n{"unexpected":true}\n```\n````\n\n~~~factory-config\n{"endpoint":"local"}\n~~~\n',
        )
        self.assertEqual(settings(read_rules(f.repo)), {"endpoint": "local"})

    def test_symlinks_directories_utf8_and_limits(self):
        f = self.fixture()
        external = f.root / "external.md"
        external.write_text("private external fixture")
        directory = f.repo / ".rules"
        directory.symlink_to(f.root)
        with self.assertRaisesRegex(FactoryError, "not a symlink"):
            read_rules(f.repo)
        directory.unlink()
        directory.mkdir()
        link = directory / "link.md"
        link.symlink_to(external)
        with self.assertRaisesRegex(FactoryError, "regular file"):
            read_rules(f.repo)
        link.unlink()
        child = directory / "directory.md"
        child.mkdir()
        with self.assertRaisesRegex(FactoryError, "regular file"):
            read_rules(f.repo)
        child.rmdir()
        invalid = self.rule(f.repo, "invalid.md", b"\xff\xfe")
        with self.assertRaisesRegex(FactoryError, "valid UTF-8"):
            read_rules(f.repo)
        invalid.unlink()
        large = self.rule(f.repo, "large.md", "x" * (128 * 1024 + 1))
        with self.assertRaisesRegex(FactoryError, "128 KiB"):
            read_rules(f.repo)
        large.unlink()
        for i in range(9):
            self.rule(f.repo, f"{i}.md", "x" * (128 * 1024))
        with self.assertRaisesRegex(FactoryError, "1 MiB"):
            read_rules(f.repo)
        shutil.rmtree(directory)
        for i in range(129):
            self.rule(f.repo, f"{i}.md", "x")
        with self.assertRaisesRegex(FactoryError, "128 files"):
            read_rules(f.repo)

    def test_check_writing_ignored_rules_cannot_certify_itself(self):
        f = self.fixture()
        (f.repo / ".gitignore").write_text("ignored*\n.rules/local.md\n")
        (f.repo / "check.py").write_text(
            "from pathlib import Path\nPath('.rules').mkdir(exist_ok=True)\nPath('.rules/local.md').write_text('Instructions changed during checks.')\n"
        )
        git(f.repo, ["add", "--", ".gitignore", "check.py"])
        git(f.repo, ["commit", "-m", "rules writer fixture"])
        run = self.planned(f)
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        result = engine.verify(run["run"])
        self.assertTrue(result["verification"]["results"][0]["passed"])
        self.assertFalse(result["verification"]["unchanged"])
        self.assertFalse(result["verification"]["passed"])
        self.assertEqual(result["next"]["action"], "plan-review")

    def test_interrupted_start_restores_snapshot_and_rules_readonly(self):
        f = self.fixture()
        self.rule(f.repo, "guide.md", "Frozen initial rules.")
        self.commit_rules(f)
        run = engine.start(f.options)
        state = read_run(run["run"])
        state["phase"] = "preparing"
        atomic_json(Path(run["run"]) / "state.json", state)
        Path(run["rules"]["snapshot"]).unlink()
        engine.resume(run["run"])
        self.assertEqual(read_json(run["rules"]["snapshot"])["files"][0]["content"], "Frozen initial rules.")
        before = (Path(run["run"]) / "state.json").read_bytes()
        status, index = git(run["worktree"], ["status", "--porcelain"]), git(run["worktree"], ["write-tree"])
        output = self.cli("rules", "--run", run["run"], "--json")
        self.assertEqual(json.loads(output.stdout)["hash"], run["rules"]["initialHash"])
        self.assertEqual((Path(run["run"]) / "state.json").read_bytes(), before)
        self.assertEqual(git(run["worktree"], ["status", "--porcelain"]), status)
        self.assertEqual(git(run["worktree"], ["write-tree"]), index)

    def test_base_symlink_cannot_be_hidden_by_source_deletion(self):
        f = self.fixture()
        (f.repo / ".rules").symlink_to(f.root)
        git(f.repo, ["add", "--", ".rules"])
        git(f.repo, ["commit", "-m", "synthetic symlink rules"])
        (f.repo / ".rules").unlink()
        with self.assertRaisesRegex(FactoryError, "selected base must be a directory"):
            engine.start(f.options)

    def test_committed_directories_cannot_masquerade_as_absent_files(self):
        for kind in ("legacy", "rule"):
            f = self.fixture()
            if kind == "legacy":
                (f.repo / ".factory.json").unlink()
                bad = f.repo / ".factory.json"
                bad.mkdir()
                (bad / "child").write_text("not configuration")
                self.rule(
                    f.repo,
                    "factory.md",
                    config_fence(
                        {"checks": [{"name": "test", "argv": [sys.executable, "check.py"], "timeoutMs": 2000}]}
                    ),
                )
            else:
                bad = f.repo / ".rules" / "directory.md"
                bad.mkdir(parents=True)
                (bad / "child").write_text("not a rule")
            self.commit_rules(f)
            shutil.rmtree(bad)
            with self.assertRaisesRegex(FactoryError, "committed configuration must be a regular file"):
                engine.start(f.options)
