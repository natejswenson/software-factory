"""Require an executable test change in every commit proposed for main.

This establishes structural association, not relevance. Reviewers must still
check that the changed tests exercise the behavior they accompany.
"""

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

SHA = re.compile(r"[a-f0-9]{40}")


def git(repo: Path, *args: str, missing: bool = False) -> str:
    result = subprocess.run(["git", "--literal-pathspecs", *args], cwd=repo, text=True, capture_output=True, timeout=30)
    if result.returncode and not missing:
        raise RuntimeError(result.stderr.strip())
    return "" if result.returncode else result.stdout


def test_bodies(source: str) -> dict[str, str]:
    """Ignore comments/docstrings and count test bodies containing assertions."""
    tree = ast.parse(source)
    result = {}
    for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
        for node in cls.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test"):
                continue
            assertions = any(
                isinstance(part, ast.Assert)
                or isinstance(part, ast.Call)
                and isinstance(part.func, ast.Attribute)
                and part.func.attr.startswith("assert")
                for part in ast.walk(node)
            )
            if assertions:
                body = [
                    part
                    for part in node.body
                    if not (
                        isinstance(part, ast.Expr)
                        and isinstance(part.value, ast.Constant)
                        and isinstance(part.value.value, str)
                    )
                ]
                result[f"{cls.name}.{node.name}"] = ast.dump(ast.Module(body=body, type_ignores=[]))
    return result


def inspect_range(repo: Path, base: str, head: str, passed: set[str] | None = None) -> list[dict[str, object]]:
    for value in (base, head):
        if not SHA.fullmatch(value):
            raise ValueError("Base and head must be full hexadecimal commit SHAs.")
        git(repo, "cat-file", "-e", f"{value}^{{commit}}")
    commits = git(repo, "rev-list", "--reverse", f"{base}..{head}").splitlines()
    reports = []
    for commit in commits:
        parents = git(repo, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        if not parents:
            raise ValueError("A proposed root commit has no reviewed baseline.")
        parent = parents[0]
        paths = git(repo, "diff", "--no-renames", "--name-only", "-z", parent, commit).split("\0")
        paths = [path for path in paths if path]
        if not paths:
            reports.append({"commit": commit, "tests": [], "empty": True})
            continue
        changed = []
        for path in paths:
            candidate = Path(path)
            if not (candidate.parts[0] == "tests" and candidate.name.startswith("test") and candidate.suffix == ".py"):
                continue
            before = test_bodies(git(repo, "show", f"{parent}:{path}", missing=True))
            after = test_bodies(git(repo, "show", f"{commit}:{path}", missing=True))
            for name, body in after.items():
                identifier = f"{path[:-3].replace('/', '.')}.{name}"
                if before.get(name) != body and (passed is None or identifier in passed):
                    changed.append(identifier)
        if not changed:
            raise ValueError(
                f"Commit {commit[:12]} needs an added or semantically changed Python test with assertions."
            )
        reports.append({"commit": commit, "tests": changed, "empty": False})
    return reports


def event_range(repo: Path, event: dict, event_name: str) -> tuple[str, str]:
    if event_name == "pull_request":
        return event["pull_request"]["base"]["sha"], event["pull_request"]["head"]["sha"]
    head = event.get("after") or git(repo, "rev-parse", "HEAD").strip()
    base = event.get("before", "")
    if not base or base == "0" * 40:
        base = git(repo, "merge-base", "origin/main", head).strip()
    return base, head


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--event-file", type=Path)
    parser.add_argument("--event-name", default="")
    parser.add_argument("--results", type=Path, help="Require associated tests actually passed in the current suite")
    args = parser.parse_args()
    repo = Path.cwd()
    base, head = (args.base, args.head)
    if args.event_file:
        base, head = event_range(repo, json.loads(args.event_file.read_text()), args.event_name)
    if not base or not head:
        parser.error("Provide base/head or a GitHub event file.")
    passed = set(json.loads(args.results.read_text())) if args.results else None
    print(json.dumps(inspect_range(repo, base, head, passed), indent=2))


if __name__ == "__main__":
    main()
