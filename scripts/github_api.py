"""Bounded GitHub CLI calls shared by trusted repository automation."""

import json
import re
import subprocess


def command(*argv: str) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Command failed.")
    return result.stdout


def api(path: str, *, method: str = "GET", data: dict | None = None, missing: bool = False):
    argv = ["gh", "api", "--method", method, path]
    if data is not None:
        argv.extend(["--input", "-"])
    result = subprocess.run(
        argv, input=json.dumps(data) if data is not None else None, text=True, capture_output=True, timeout=60
    )
    if result.returncode:
        if missing and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip() or "GitHub API failed.")
    return json.loads(result.stdout) if result.stdout.strip() else None


def repository(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Invalid repository name.")
    return value


def sha(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}", value):
        raise ValueError("A full commit SHA is required.")
    return value
