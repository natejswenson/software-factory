"""Temporary test repositories. Synthetic reviews never represent native reviews."""

import json
import os
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from software_factory import engine
from software_factory.git import git
from software_factory.store import atomic_json, read_run

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, "-m", "software_factory"]


@dataclass
class Fixture:
    root: Path
    repo: Path
    options: engine.StartOptions


class FactoryCase(unittest.TestCase):
    def fixture(self, endpoint="local"):
        temporary = TemporaryDirectory(prefix="factory test ")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        repo = root / "source repo"
        repo.mkdir()
        git(repo, ["init", "-b", "main"])
        git(repo, ["config", "user.name", "Factory Test"])
        git(repo, ["config", "user.email", "factory@example.invalid"])
        git(repo, ["config", "commit.gpgsign", "false"])
        atomic_json(
            repo / ".factory.json",
            {
                "version": 1,
                "endpoint": endpoint,
                "checks": [{"name": "behavior", "argv": [sys.executable, "check.py"], "timeoutMs": 2000}],
            },
        )
        (repo / "value.txt").write_text("old\n")
        (repo / "check.py").write_text(
            "from pathlib import Path\nimport sys\nsys.exit(0 if Path('value.txt').read_text().strip() == 'new' else 1)\n"
        )
        (repo / ".gitignore").write_text("ignored*\n")
        git(repo, ["add", "--", ".factory.json", "value.txt", "check.py", ".gitignore"])
        git(repo, ["commit", "-m", "fixture baseline"])
        return Fixture(
            root,
            repo,
            engine.StartOptions(
                repo=str(repo),
                worktree_root=str(root / "worktrees"),
                task="Change old to new",
                criteria=["value.txt contains new"],
                base="main",
            ),
        )

    def json_file(self, directory, name, data):
        path = Path(directory) / name
        atomic_json(path, data)
        return path

    def approve_plan(self, run):
        context = engine.context(read_run(run["run"]))
        return engine.submit_plan_review(
            run["run"],
            self.json_file(
                run["run"],
                "synthetic-plan-review.json",
                {"reviewer": "synthetic test fixture", "verdict": "pass", "findings": [], "context": context},
            ),
        )

    def planned(self, fixture):
        run = engine.start(fixture.options)
        plan = Path(run["run"]) / "plan.md"
        plan.write_text("# Plan\nChange value.txt to new. Run the behavior check.\n")
        engine.submit_plan(run["run"], plan)
        return self.approve_plan(run)

    def checked(self, fixture):
        run = self.planned(fixture)
        (Path(run["worktree"]) / "value.txt").write_text("new\n")
        return engine.verify(run["run"])

    def code_review(self, run, **overrides):
        return {
            "reviewer": "synthetic test fixture",
            "verdict": "pass",
            "findings": [],
            "evidence": run["next"]["evidence"],
            "criteria": [{"id": "AC1", "passed": True, "evidence": "behavior check passed"}],
            **overrides,
        }

    def reviewed(self, fixture):
        return self.review(self.checked(fixture))

    def review(self, run, **overrides):
        return engine.submit_review(
            run["run"], self.json_file(run["run"], "synthetic-code-review.json", self.code_review(run, **overrides))
        )

    def cli(self, *argv):
        return subprocess.run([*CLI, *map(str, argv)], cwd=ROOT, capture_output=True, text=True)

    def summary(self, run, human=False):
        path = Path(run["run"]) / "state.json"
        before, status, index = (
            path.read_bytes(),
            git(run["worktree"], ["status", "--porcelain"]),
            git(run["worktree"], ["write-tree"]),
        )
        output = self.cli("summary", "--run", run["run"], *([] if human else ["--json"]))
        self.assertEqual(output.returncode, 2 if read_run(run["run"])["phase"] == "blocked" else 0, output.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(git(run["worktree"], ["status", "--porcelain"]), status)
        self.assertEqual(git(run["worktree"], ["write-tree"]), index)
        if human:
            return output.stdout
        self.assertEqual(len(output.stdout.strip().splitlines()), 1)
        return json.loads(output.stdout)

    def github(self, fixture):
        bin_dir = fixture.root / "mockbin"
        bin_dir.mkdir()
        file = fixture.root / "mock-pr.json"
        script = bin_dir / "gh"
        script.write_text(
            f"#!{sys.executable}\n"
            + """import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
file = Path(os.environ['MOCK_PR'])
if args[0] == 'repo':
    print(json.dumps({'nameWithOwner': 'example/demo', 'url': 'https://github.com/example/demo'}))
elif args[0] == 'issue':
    print(json.dumps({'number': 42, 'title': 'Frozen issue', 'body': 'Change old to new', 'url': 'https://github.com/example/demo/issues/42'}))
elif args[1] == 'list':
    print('[' + file.read_text() + ']' if file.exists() else '[]')
elif args[1] == 'create':
    get = lambda key: args[args.index(key) + 1]
    file.write_text(json.dumps({'number': 1, 'url': 'https://github.com/example/demo/pull/1', 'isDraft': True, 'state': 'OPEN',
        'headRefName': get('--head'), 'baseRefName': get('--base'),
        'headRefOid': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()}))
    sys.exit(1 if os.environ.get('MOCK_FAIL') == '1' else 0)
else:
    sys.exit(9)
"""
        )
        script.chmod(0o755)
        environment = patch.dict(
            os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "MOCK_PR": str(file)}
        )
        environment.start()
        self.addCleanup(environment.stop)
        parent = fixture.root / "example"
        parent.mkdir()
        bare = parent / "demo.git"
        git(fixture.root, ["init", "--bare", str(bare)])
        git(fixture.repo, ["remote", "add", "origin", str(bare)])
        git(fixture.repo, ["push", "origin", "main"])
        return file

    def rule(self, root, name, content):
        directory = Path(root) / ".rules"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return path

    def commit_rules(self, fixture):
        git(fixture.repo, ["add", "-A", "--", ".rules", ".factory.json"])
        git(fixture.repo, ["commit", "-m", "repository rules fixture"])


def config_fence(config, prose="Use repository conventions."):
    return f"{prose}\n\n```factory-config\n{json.dumps(config, indent=2)}\n```\n"
