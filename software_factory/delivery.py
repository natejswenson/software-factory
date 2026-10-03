"""Observe the reviewed commit and reconcile draft PR delivery after interruption."""

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .engine import (
    EVIDENCE_KEYS,
    active,
    check_plan,
    describe,
    evidence,
    own_delivery_commit,
    same_evidence,
    transaction,
)
from .errors import FactoryError
from .git import command, git, snapshot
from .store import Run, atomic_json, now, save
from .validation import json_integer


def _remote_repo(run: Run) -> dict[str, Any]:
    info = json.loads(command(["gh", "repo", "view", "--json", "nameWithOwner,url"], run["worktree"]))
    if (
        not isinstance(info, dict)
        or not isinstance(info.get("nameWithOwner"), str)
        or not re.fullmatch(r"[\w.-]+/[\w.-]+", info["nameWithOwner"], flags=re.ASCII)
        or not isinstance(info.get("url"), str)
        or not info["url"].startswith("https://")
    ):
        raise FactoryError("Invalid GitHub repository response.")
    return info


def _find_pr(run: Run, target: dict[str, Any]) -> dict[str, Any] | None:
    prs = json.loads(
        command(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                target["nameWithOwner"],
                "--head",
                run["branch"],
                "--state",
                "all",
                "--json",
                "number,url,isDraft,headRefOid,baseRefName,headRefName,state",
            ],
            run["worktree"],
        )
    )
    if not isinstance(prs, list) or len(prs) > 1 or (prs and not isinstance(prs[0], dict)):
        raise FactoryError("Ambiguous PR response; inspect GitHub before retrying.")
    return prs[0] if prs else None


def _commit(run: Run, current: dict[str, Any], recovering: bool) -> dict[str, Any]:
    if not run.get("commitIntent"):
        run["commitIntent"] = {"parent": current["head"], "tree": current["tree"], "paths": current["paths"]}
        save(run, "commit-intent")
    if not recovering and not (run.get("delivery") or {}).get("commit"):
        paths = [
            path
            for path in git(
                run["worktree"], ["diff", "--no-renames", "--name-only", "-z", "HEAD", current["tree"]]
            ).split("\0")
            if path
        ]
        # Directory-to-symlink/file changes report both the replacement root and
        # deleted children. Git cannot add a child path through the new symlink.
        # Stage each changed root once; the exact-tree check below still applies.
        if git(run["worktree"], ["write-tree"]).strip() != current["tree"] and paths:
            selected = set(paths)
            roots = [
                path for path in paths if not any(str(parent) in selected for parent in PurePosixPath(path).parents)
            ]
            git(run["worktree"], ["add", "--", *roots])
        if git(run["worktree"], ["write-tree"]).strip() != current["tree"]:
            raise FactoryError("Index differs from reviewed tree.", "drift")
        if git(run["worktree"], ["rev-parse", "HEAD^{tree}"]).strip() != current["tree"]:
            git(run["worktree"], ["commit", "-m", f"factory: {run['task'].splitlines()[0][:100]}"])
    final = snapshot(run["worktree"], run["base"])
    if (
        final["tree"] != current["tree"]
        or git(run["worktree"], ["rev-parse", "HEAD^{tree}"]).strip() != final["tree"]
        or git(run["worktree"], ["status", "--porcelain"]).strip()
    ):
        raise FactoryError("Final commit/worktree differs from reviewed files.", "drift")
    run["delivery"] = {
        "endpoint": run["endpoint"],
        "commit": final["head"],
        "tree": final["tree"],
        "branch": run["branch"],
        "at": now(),
    }
    save(run, "commit-observed")
    return final


def _draft_pr(run: Run, final: dict[str, Any]) -> None:
    target = _remote_repo(run)
    if run["baseRef"] == "HEAD" or re.fullmatch(r"[a-f0-9]{40}", run["baseRef"]):
        raise FactoryError("Draft PR needs a named --base branch.", "delivery")
    base_branch = run["baseRef"].removeprefix("origin/")
    origin = git(run["worktree"], ["remote", "get-url", "origin"]).strip()
    if target["nameWithOwner"] not in origin:
        raise FactoryError("origin does not match the selected GitHub repository.", "delivery")
    run["operation"] = {"kind": "push", "commit": final["head"], "repository": target["nameWithOwner"]}
    save(run, "push-intent")
    git(run["worktree"], ["push", "--set-upstream", "origin", run["branch"]])
    remote = git(run["worktree"], ["ls-remote", "origin", f"refs/heads/{run['branch']}"]).strip().split()
    if not remote or remote[0] != final["head"]:
        raise FactoryError("Remote head does not match the verified commit.", "delivery")
    save(run, "push-observed")
    pr = _find_pr(run, target)
    if pr is None:
        body = Path(run["dir"]) / "pr-body.md"
        criteria = "\n".join(f"- {criterion['text']}" for criterion in run["criteria"])
        checks = "\n".join(f"- {check['name']}: passed" for check in run["verification"]["results"])
        body.write_text(
            f"## Task\n\n{run['task']}\n\n## Acceptance criteria\n\n{criteria}\n\n## Verification\n\n{checks}\n\nReviewed commit: {final['head']}\n",
            encoding="utf-8",
        )
        run["operation"] = {"kind": "pr-create", "commit": final["head"], "repository": target["nameWithOwner"]}
        save(run, "pr-intent")
        command(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                target["nameWithOwner"],
                "--draft",
                "--head",
                run["branch"],
                "--base",
                base_branch,
                "--title",
                run["task"].splitlines()[0][:150],
                "--body-file",
                str(body),
            ],
            run["worktree"],
        )
        pr = _find_pr(run, target)
    if (
        not pr
        or pr.get("state") != "OPEN"
        or pr.get("isDraft") is not True
        or pr.get("headRefOid") != final["head"]
        or pr.get("headRefName") != run["branch"]
        or pr.get("baseRefName") != base_branch
        or not json_integer(pr.get("number"))
        or not isinstance(pr.get("url"), str)
        or not pr["url"].startswith(f"{target['url']}/pull/")
    ):
        raise FactoryError("PR is not an open draft for the verified head/base.", "delivery")
    run["delivery"].update(pr=pr["url"], number=pr["number"])


def deliver(directory: str | Path) -> dict[str, Any]:
    with transaction(directory) as run:
        if run["phase"] == "done":
            return describe(run)
        active(run)
        check_plan(run)
        current = evidence(run)
        recovering = own_delivery_commit(run, current)
        verification, review = run.get("verification"), run.get("codeReview")
        if (
            not verification
            or not verification["passed"]
            or not review
            or review["verdict"] != "pass"
            or not (same_evidence(verification["evidence"], current) or recovering)
            or not same_evidence(review["evidence"], verification["evidence"])
            or not all(current.get(key) == verification["evidence"].get(key) for key in EVIDENCE_KEYS if key != "head")
        ):
            raise FactoryError("Delivery requires current verification and passing code review.", "gate")
        if not current["paths"]:
            raise FactoryError("Task has no changes against its base.")
        final = _commit(run, current, recovering)
        if run["endpoint"] == "draft-pr":
            _draft_pr(run, final)
        if (
            not same_evidence({**current, "head": final["head"]}, evidence(run))
            or git(run["worktree"], ["status", "--porcelain"]).strip()
        ):
            raise FactoryError("Files changed during delivery.", "drift")
        run.update(phase="done", operation=None)
        atomic_json(Path(directory) / "delivery.json", run["delivery"])
        save(run, "completed")
        return describe(run)
