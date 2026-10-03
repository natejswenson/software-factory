"""Prove an installed factory's local lifecycle with Node and npm absent from PATH.

Usage: /path/to/isolated/venv/bin/python scripts/smoke_install.py
The executing environment must already have the wheel installed.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> int:
    factory = Path(sys.executable).parent / "factory"
    if not factory.is_file():
        raise RuntimeError("Install the wheel into this Python environment first.")
    with TemporaryDirectory(prefix="factory-install-") as temporary:
        root = Path(temporary).resolve()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").symlink_to(shutil.which("git"))
        (bin_dir / "python3").symlink_to(sys.executable)
        env = {**os.environ, "PATH": str(bin_dir), "PYTHONPATH": "", "GIT_CONFIG_NOSYSTEM": "1"}
        if shutil.which("node", path=env["PATH"]) or shutil.which("npm", path=env["PATH"]):
            raise RuntimeError("Node or npm unexpectedly available.")

        def run(argv, cwd=root):
            output = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)
            if output.returncode:
                raise RuntimeError(output.stderr or output.stdout)
            return output.stdout

        def cli(*argv):
            return json.loads(run([str(factory), *map(str, argv), "--json"]))

        repo = root / "repo"
        repo.mkdir()
        run(["git", "init", "-b", "main"], repo)
        run(["git", "config", "user.name", "Factory Installation Test"], repo)
        run(["git", "config", "user.email", "factory@example.invalid"], repo)
        run(["git", "config", "commit.gpgsign", "false"], repo)
        (repo / "check.py").write_text("from pathlib import Path\nassert Path('value.txt').read_text() == 'new\\n'\n")
        (repo / "value.txt").write_text("old\n")
        cli("init", "--repo", repo, "--check", '["python3", "check.py"]')
        run(["git", "add", "."], repo)
        run(["git", "commit", "-m", "synthetic installation baseline"], repo)
        status = cli(
            "start",
            "--repo",
            repo,
            "--task",
            "Test installed Python factory",
            "--criterion",
            "value contains new",
            "--endpoint",
            "local",
            "--worktree-root",
            root / "worktrees",
        )
        directory = Path(status["run"])
        plan = directory / "plan.md"
        plan.write_text("# Plan\nUpdate the value and execute check.py.\n")
        status = cli("plan", "--run", directory, "--file", plan)
        plan_review = directory / "synthetic-plan.json"
        plan_review.write_text(
            json.dumps(
                {
                    "reviewer": "synthetic installed-wheel test",
                    "context": status["next"]["context"],
                    "verdict": "pass",
                    "findings": [],
                }
            )
        )
        cli("plan-review", "--run", directory, "--file", plan_review)
        (Path(status["worktree"]) / "value.txt").write_text("new\n")
        status = cli("verify", "--run", directory)
        assert status["verification"]["passed"]
        review = directory / "synthetic-review.json"
        review.write_text(
            json.dumps(
                {
                    "reviewer": "synthetic installed-wheel test",
                    "evidence": status["next"]["evidence"],
                    "verdict": "pass",
                    "findings": [],
                    "criteria": [{"id": "AC1", "passed": True, "evidence": "Real installed check.py passed"}],
                }
            )
        )
        cli("review", "--run", directory, "--file", review)
        done = cli("deliver", "--run", directory)
        assert done["phase"] == "done"
        assert cli("summary", "--run", directory)["delivery"] == done["delivery"]
        skill = Path(cli("skill-path"))
        assert skill.is_relative_to(Path(sys.prefix))
        assert (skill / "SKILL.md").is_file() and (skill / "protocol.md").is_file()
        assert run([str(factory), "--help"])
        print(
            json.dumps(
                {
                    "installedLifecycle": "passed",
                    "nodeOnPath": False,
                    "npmOnPath": False,
                    "bundledSkill": "present",
                    "endpoint": done["delivery"]["endpoint"],
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
