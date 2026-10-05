"""Prove an installed factory's local lifecycle with Node and npm absent from PATH.

Usage: /path/to/isolated/venv/bin/python scripts/smoke_install.py
The executing environment must already have the wheel installed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main(plugin: Path | None = None) -> int:
    factory = Path(sys.executable).parent / "factory"
    command = [sys.executable, str(plugin / "scripts/factory.py")] if plugin else [str(factory)]
    if not plugin and not factory.is_file():
        raise RuntimeError("Install the wheel into this Python environment first.")
    with TemporaryDirectory(prefix="factory-install-") as temporary:
        root = Path(temporary).resolve()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").symlink_to(shutil.which("git"))
        (bin_dir / "python3").symlink_to(sys.executable)
        if plugin:
            sentinel = bin_dir / "factory"
            sentinel.write_text("#!/bin/sh\nexit 99\n")
            sentinel.chmod(0o755)
        env = {**os.environ, "PATH": str(bin_dir), "PYTHONPATH": "", "GIT_CONFIG_NOSYSTEM": "1"}
        if shutil.which("node", path=env["PATH"]) or shutil.which("npm", path=env["PATH"]):
            raise RuntimeError("Node or npm unexpectedly available.")

        def run(argv, cwd=root):
            output = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)
            if output.returncode:
                raise RuntimeError(output.stderr or output.stdout)
            return output.stdout

        def cli(*argv):
            return json.loads(run([*command, *map(str, argv), "--json"]))

        repo = root / "repo"
        repo.mkdir()
        run(["git", "init", "-b", "main"], repo)
        run(["git", "config", "user.name", "Factory Installation Test"], repo)
        run(["git", "config", "user.email", "factory@example.invalid"], repo)
        run(["git", "config", "commit.gpgsign", "false"], repo)
        (repo / "check.py").write_text("from pathlib import Path\nassert Path('value.txt').read_text() == 'new\\n'\n")
        (repo / "value.txt").write_text("old\n")
        enrolled = cli("init", "--repo", repo, "--check", '["python3", "check.py"]')
        assert enrolled["prd"]["created"] == ["prd/README.md", "prd/_template.md"]
        assert "Status: draft" in (repo / "prd/_template.md").read_text()
        custom = b"Synthetic customized requirement guidance\n"
        (repo / "prd/README.md").write_bytes(custom)
        repeated = cli("prd-init", "--repo", repo)
        assert repeated["created"] == [] and repeated["skipped"] == ["prd/README.md", "prd/_template.md"]
        assert (repo / "prd/README.md").read_bytes() == custom
        retrofit = root / "existing project"
        retrofit.mkdir()
        run(["git", "init", "-b", "main"], retrofit)
        standalone = cli("prd-init", "--repo", retrofit)
        assert standalone["created"] == ["prd/README.md", "prd/_template.md"]
        assert not (retrofit / ".rules").exists() and not (retrofit / ".factory.json").exists()
        assert cli("prd-init", "--repo", retrofit)["created"] == []
        run(["git", "add", "."], repo)
        run(["git", "commit", "-m", "synthetic installation baseline"], repo)
        readiness = cli(
            "preflight", "--repo", repo, "--worktree-root", root / "preflight worktrees", "--endpoint", "local"
        )
        assert readiness["ready"] is True and readiness["deliveryReady"] is True
        assert not (root / "preflight worktrees").exists()
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
        plan_bundle = cli("review-context", "--run", directory, "--stage", "plan")
        assert plan_bundle["context"] == status["next"]["context"]
        assert plan_bundle["evidence"] is None and plan_bundle["complete"]
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
        assert cli("progress", "--run", directory)["status"] == "not-started"
        status = cli("verify", "--run", directory)
        assert status["verification"]["passed"]
        observed = cli("progress", "--run", directory)
        assert observed["status"] == "completed" and observed["attempt"] == 1
        assert observed["checks"][0]["result"] == status["verification"]["results"][0]
        tail = cli("logs", "--run", directory, "--check-name", "check1", "--tail-bytes", 8)
        assert tail["bytesRead"] <= 8 and tail["logTruncated"] is False
        assert tail["encoding"] == "utf-8 with replacement"
        explained = cli("explain", "--run", directory)
        assert explained["gates"]["verification"]["status"] == "current"
        assert explained["next"] == status["next"]
        assert explained["changedPaths"]["paths"] == []
        code_bundle = cli("review-context", "--run", directory, "--stage", "code")
        assert code_bundle["evidence"] == status["next"]["evidence"]
        assert code_bundle["verification"] == status["verification"]
        assert "value.txt" in code_bundle["diff"]["patch"] and code_bundle["complete"]
        prose = directory / "synthetic-description.json"
        prose.write_text(
            json.dumps(
                {
                    "version": 1,
                    "evidence": status["next"]["evidence"],
                    "title": "Installed presentation test",
                    "summary": ["Change the synthetic value and retain verified delivery."],
                }
            )
        )
        preview = cli("pr-description", "--run", directory, "--file", prose)
        assert preview["changed"] and "value contains new" in preview["preview"]
        assert "## Task" not in preview["preview"]
        assert not cli("pr-description", "--run", directory, "--file", prose)["changed"]
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
        state = json.loads((directory / "state.json").read_text())
        assert state["commitIntent"]["presentationHash"] == state["prPresentation"]["hash"]
        assert cli("explain", "--run", directory)["delivery"] == done["delivery"]
        assert cli("summary", "--run", directory)["delivery"] == done["delivery"]
        inventory = cli("runs", "--repo", repo)
        assert inventory["total"] == 1 and inventory["runs"][0]["delivery"] == done["delivery"]
        recorded = cli("history", "--run", directory)
        assert recorded["attempts"][0]["checks"][0]["status"] == "passed"
        assert recorded["totals"]["knownAttempts"] == 1 and recorded["delivery"] == done["delivery"]
        skill = Path(cli("skill-path"))
        assert skill == plugin / "skills/software-factory" if plugin else skill.is_relative_to(Path(sys.prefix))
        assert (skill / "SKILL.md").is_file() and (skill / "protocol.md").is_file()
        canonical = Path(__file__).resolve().parents[1] / "skills/software-factory"
        for name in ("SKILL.md", "protocol.md"):
            assert (skill / name).read_bytes() == (canonical / name).read_bytes()
        assert run([*command, "--help"])
        print(
            json.dumps(
                {
                    "pluginLifecycle" if plugin else "installedLifecycle": "passed",
                    "nodeOnPath": False,
                    "npmOnPath": False,
                    "bundledSkill": "present",
                    "endpoint": done["delivery"]["endpoint"],
                }
            )
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", type=Path)
    args = parser.parse_args()
    sys.exit(main(args.plugin_root.resolve() if args.plugin_root else None))
