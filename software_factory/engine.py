"""Task transitions. Every mutation goes through an owned run transaction."""

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import prd, progress
from .checks import execute_check, validate_config
from .errors import FactoryError
from .git import assert_supported, assert_worktree, command, git, repository, snapshot
from .rules import assert_committed, configuration, read_project, read_rules, settings
from .store import (
    Run,
    atomic_json,
    fingerprint,
    list_runs,
    locked,
    now,
    read_json,
    read_run,
    recover_lock,
    runs_root,
    save,
)
from .validation import json_integer

EVIDENCE_KEYS = ("base", "criteria", "config", "plan", "rules", "head", "tree")


def nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FactoryError(f"{name} must be nonempty.")
    return value.strip()


def init(repo: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    root = Path(repository(repo).root)
    rules = read_rules(root)
    if (root / ".factory.json").exists() or settings(rules):
        raise FactoryError("Factory configuration already exists; use prd-init for scaffold setup.")
    config = validate_config({"version": 1, "endpoint": "draft-pr", "checks": checks})
    path = root / ".rules" / "factory.md"
    if path.exists() or path.is_symlink():
        raise FactoryError(
            ".rules/factory.md already exists; inspect it before editing. Use prd-init for scaffold setup."
        )
    scaffold = prd.prepare(root)
    created: list[str] = []
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("x", encoding="utf-8")
        created.append(".rules/factory.md")
        with stream:
            stream.write(
                "# Software Factory\n\n```factory-config\n"
                + json.dumps(config, indent=2)
                + "\n```\n\n## Repository instructions\n\nDescribe this repository's conventions and completion requirements here.\n"
            )
    except OSError as error:
        code = "invalid" if isinstance(error, FileExistsError) else "infrastructure"
        raise FactoryError(prd.partial_message(error, created, []), code) from error
    result = prd.create(scaffold, prior_created=created)
    return {
        "config": str(path),
        "prd": result,
        "next": "Review and commit .rules/factory.md and the PRD scaffold, then start a task.",
    }


def prd_init(repo: str) -> dict[str, Any]:
    return prd.create(prd.prepare(Path(repository(repo).root)))


@dataclass(frozen=True)
class StartOptions:
    repo: str
    worktree_root: str
    task: str | None = None
    issue: str | None = None
    criteria: list[str] = field(default_factory=list)
    base: str | None = None
    endpoint: str | None = None
    branch: str | None = None


def validate_branch(branch: str) -> str:
    if not isinstance(branch, str) or not re.fullmatch(r"(?:feature|bug|issue)/[a-z0-9]+(?:-[a-z0-9]+)*", branch):
        raise FactoryError(
            "Branch must be feature/<name>, bug/<name> or issue/<name>, using lowercase words separated by hyphens."
        )
    return branch


def start(options: StartOptions) -> dict[str, Any]:
    repo = repository(options.repo)
    assert_supported(repo.root)
    if (options.task is None) == (options.issue is None):
        raise FactoryError("Choose exactly one task or issue.")
    source = (
        {"kind": "issue", "id": nonempty(options.issue, "Issue")} if options.issue is not None else {"kind": "text"}
    )
    criteria = [{"id": f"AC{i + 1}", "text": nonempty(item, "Criterion")} for i, item in enumerate(options.criteria)]
    if not criteria:
        raise FactoryError("Supply at least one --criterion.")
    base_ref = options.base or ("main" if git(repo.root, ["branch", "--list", "main"]).strip() else "HEAD")
    base = git(repo.root, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"]).strip()
    project = read_project(repo.root)
    config = project["config"]
    endpoint = options.endpoint or config["endpoint"]
    if endpoint not in ("local", "draft-pr"):
        raise FactoryError("Unknown endpoint.")
    if options.branch is not None:
        validate_branch(options.branch)
    assert_committed(repo.root, base, project)
    if options.issue is None:
        source["text"] = nonempty(options.task, "Task")
    identity = fingerprint(
        {
            "common": repo.common,
            "source": source,
            "criteria": criteria,
            "endpoint": endpoint,
            "baseRef": base_ref,
            "base": base,
        }
    )
    allocation = runs_root(repo.common)
    allocation.mkdir(parents=True, exist_ok=True, mode=0o700)
    with locked(allocation):
        matches = [run for run in list_runs(repo.common) if run["identity"] == identity and run["phase"] != "done"]
        if len(matches) > 1:
            raise FactoryError("Multiple matching runs; select an explicit --run.")
        if matches:
            with transaction(matches[0]["dir"]) as run:
                if options.branch and options.branch != run["branch"]:
                    raise FactoryError("Matching run already owns a different branch. Use its explicit run and rename.")
                prepare(run)
                return describe(run)
        task = source.get("text")
        if options.issue is not None:
            issue = json.loads(
                command(["gh", "issue", "view", options.issue, "--json", "number,title,body,url"], repo.root)
            )
            if (
                not isinstance(issue, dict)
                or not json_integer(issue.get("number"))
                or not isinstance(issue.get("title"), str)
                or not isinstance(issue.get("body"), str)
                or not isinstance(issue.get("url"), str)
                or not issue["url"].startswith("https://")
            ):
                raise FactoryError("Invalid GitHub issue response.")
            source["snapshot"] = issue
            task = f"{issue['title']}\n\n{issue['body']}"
        identifier = str(uuid4())
        directory = allocation / identifier
        root = Path(nonempty(options.worktree_root, "Worktree root")).resolve()
        root.mkdir(parents=True, exist_ok=True)
        worktree = root / f"factory-{identifier[:8]}"
        if worktree.exists():
            raise FactoryError("Worktree path already exists.")
        slug = re.sub(r"[^a-z0-9]+", "-", str(task).splitlines()[0].lower()).strip("-")[:48].rstrip("-") or "task"
        branch = options.branch or f"feature/{slug}-{identifier[:8]}"
        if git(repo.root, ["branch", "--list", branch]).strip():
            raise FactoryError("Branch already exists. Choose an unused branch.")
        directory.mkdir(mode=0o700)
        run = {
            "version": 1,
            "id": identifier,
            "dir": str(directory),
            "common": repo.common,
            "repo": repo.root,
            "identity": identity,
            "task": task,
            "source": source,
            "criteria": criteria,
            "config": config,
            "configHash": fingerprint(config),
            "rules": {"version": 1, "initial": project["rules"]},
            "endpoint": endpoint,
            "baseRef": base_ref,
            "base": base,
            "worktree": str(worktree),
            "branch": branch,
            "phase": "preparing",
            "failures": 0,
            "failureLimit": 3,
            "history": [],
            "checkAttempt": 0,
            "createdAt": now(),
        }
        save(run, "start-intent")
        with locked(directory):
            prepare(run)
            return describe(run)


def prepare(run: Run) -> None:
    reconcile_rename(run)
    if run["phase"] != "preparing":
        assert_worktree(run)
        return
    worktree = Path(run["worktree"])
    if worktree.exists():
        assert_worktree(run)
        if git(worktree, ["rev-parse", "HEAD"]).strip() != run["base"]:
            raise FactoryError("Interrupted start has unexpected worktree HEAD.", "ownership")
    elif git(run["repo"], ["branch", "--list", run["branch"]]).strip():
        if git(run["repo"], ["rev-parse", run["branch"]]).strip() != run["base"]:
            raise FactoryError("Interrupted start branch changed.", "ownership")
        git(run["repo"], ["worktree", "add", run["worktree"], run["branch"]])
    else:
        git(run["repo"], ["worktree", "add", "-b", run["branch"], run["worktree"], run["base"]])
    criteria = "\n".join(f"- {item['id']}: {item['text']}" for item in run["criteria"])
    (Path(run["dir"]) / "task.md").write_text(
        f"# Task\n\n{run['task']}\n\n## Acceptance criteria\n\n{criteria}\n", encoding="utf-8"
    )
    if run.get("rules"):
        atomic_json(Path(run["dir"]) / "rules-initial.json", run["rules"]["initial"])
    run["phase"] = "plan"
    save(run, "worktree-created")


def task_rules(run: Run) -> dict[str, Any]:
    if not run.get("rules"):
        return {"enabled": False, "files": [], "hash": None, "snapshot": None}
    assert_worktree(run)
    rules = read_rules(run["worktree"])
    configuration(rules, run["config"])  # Validate edits; checks and endpoint remain frozen.
    return {"enabled": True, **rules, "snapshot": str(Path(run["dir"]) / "rules-initial.json")}


def context(run: Run) -> dict[str, Any]:
    assert_worktree(run)
    plan = Path(run["dir"]) / "plan.md"
    result = {
        "base": run["base"],
        "criteria": fingerprint(run["criteria"]),
        "config": run["configHash"],
        "plan": fingerprint(plan.read_bytes()) if plan.exists() else None,
    }
    if run.get("rules"):
        result["rules"] = task_rules(run)["hash"]
    return result


def evidence(run: Run) -> dict[str, Any]:
    return {**context(run), **snapshot(run["worktree"], run["base"])}


def same_evidence(left: Any, right: Any) -> bool:
    return (
        isinstance(left, dict)
        and isinstance(right, dict)
        and all(left.get(key) == right.get(key) for key in EVIDENCE_KEYS)
    )


def own_delivery_commit(run: Run, current: dict[str, Any]) -> bool:
    intent = run.get("commitIntent")
    if (
        not intent
        or not run.get("verification")
        or current["head"] == intent["parent"]
        or current["tree"] != intent["tree"]
    ):
        return False
    return git(run["worktree"], ["rev-parse", "HEAD^"]).strip() == intent["parent"] and all(
        current.get(key) == run["verification"]["evidence"].get(key) for key in EVIDENCE_KEYS if key != "head"
    )


def plan_current(run: Run, ctx: dict[str, Any]) -> bool:
    review = run.get("planReview")
    return bool(review and review["verdict"] == "pass" and fingerprint(review["context"]) == fingerprint(ctx))


def active(run: Run) -> None:
    if run["phase"] == "done":
        raise FactoryError("This run has completed. Start a new task for further work.")
    if run["phase"] == "blocked":
        raise FactoryError("Repair limit reached. Report the findings; extend only with user direction.", "blocked")


def fail(run: Run, action: str) -> None:
    run["failures"] += 1
    if run["failures"] >= run["failureLimit"]:
        run["phase"] = "blocked"
    save(run, action, failures=run["failures"])


def check_plan(run: Run) -> None:
    if not plan_current(run, context(run)):
        raise FactoryError("Current plan needs a passing plan review.", "gate")


def check_verified(run: Run) -> dict[str, Any]:
    check_plan(run)
    current = evidence(run)
    verification = run.get("verification")
    if not verification or not verification["passed"] or not same_evidence(verification["evidence"], current):
        raise FactoryError("Current files need successful verification.", "gate")
    return current


def next_action(run: Run) -> dict[str, Any]:
    if run.get("renameIntent"):
        return {"action": "resume", "reason": "Reconcile interrupted branch rename."}
    if run["phase"] == "preparing":
        return {"action": "resume", "reason": "Reconcile interrupted worktree creation."}
    if run["phase"] == "done":
        return {"action": "done", "delivery": run["delivery"], "receipt": str(Path(run["dir"]) / "delivery.json")}
    if run["phase"] == "blocked":
        return {
            "action": "blocked",
            "reason": "Repair limit reached.",
            "failures": run["failures"],
            "limit": run["failureLimit"],
        }
    ctx = context(run)
    if not ctx["plan"]:
        return {"action": "plan", "output": str(Path(run["dir"]) / "plan.md")}
    review = run.get("planReview")
    if review and review["verdict"] == "fail" and fingerprint(review["context"]) == fingerprint(ctx):
        return {"action": "plan", "reason": "Address the rejected plan review.", "findings": review["findings"]}
    if not plan_current(run, ctx):
        return {"action": "plan-review", "plan": str(Path(run["dir"]) / "plan.md"), "context": ctx}
    if run["phase"] == "implement":
        failed = run.get("verification") and not run["verification"]["passed"]
        return {
            "action": "implement",
            "reason": "Fix failed checks, then verify." if failed else "Implement the reviewed plan, then verify.",
        }
    current = evidence(run)
    verification, code_review = run.get("verification"), run.get("codeReview")
    if (
        code_review
        and code_review["verdict"] == "pass"
        and own_delivery_commit(run, current)
        and same_evidence(code_review["evidence"], verification["evidence"])
    ):
        return {
            "action": "deliver",
            "endpoint": run["endpoint"],
            "reason": "Reconcile interrupted delivery.",
            "evidence": current,
        }
    if not verification or not verification["passed"] or not same_evidence(verification["evidence"], current):
        return {"action": "verify", "reason": "Evidence is missing or files changed."}
    if not code_review or code_review["verdict"] != "pass" or not same_evidence(code_review["evidence"], current):
        return {"action": "review", "evidence": current}
    return {"action": "deliver", "endpoint": run["endpoint"], "evidence": current}


def describe(run: Run) -> dict[str, Any]:
    owner_path = Path(run["dir"]) / "lock" / "owner.json"
    owner = read_json(owner_path) if owner_path.exists() else None
    result = {
        "id": run["id"],
        "run": run["dir"],
        "task": run["task"],
        "worktree": run["worktree"],
        "branch": run["branch"],
        "base": run["baseRef"],
        "endpoint": run["endpoint"],
        "phase": run["phase"],
        "failures": run["failures"],
        "criteria": run["criteria"],
        "checks": run["config"]["checks"],
        "next": {"action": "wait", "owner": owner} if owner and owner["pid"] != os.getpid() else next_action(run),
        "plan": str(Path(run["dir"]) / "plan.md"),
        "taskFile": str(Path(run["dir"]) / "task.md"),
    }
    if run.get("rules"):
        result["rules"] = {
            "initialHash": run["rules"]["initial"]["hash"],
            "initialPaths": [file["path"] for file in run["rules"]["initial"]["files"]],
            "snapshot": str(Path(run["dir"]) / "rules-initial.json"),
        }
    for public, stored in (("verification", "verification"), ("review", "codeReview"), ("delivery", "delivery")):
        if stored in run:
            result[public] = run[stored]
    return result


@contextmanager
def transaction(directory: str | Path) -> Iterator[Run]:
    with locked(directory):
        yield read_run(directory)


def resume(directory: str | Path) -> dict[str, Any]:
    with transaction(directory) as run:
        prepare(run)
        return describe(run)


def submit_plan(directory: str | Path, file: str | Path) -> dict[str, Any]:
    with transaction(directory) as run:
        active(run)
        assert_worktree(run)
        content = nonempty(Path(file).read_text(encoding="utf-8"), "Plan")
        target = Path(directory) / "plan.md"
        if Path(file).resolve() != target:
            target.write_text(content + "\n", encoding="utf-8")
        run.update(
            phase="plan-review", planReview=None, verification=None, codeReview=None, commitIntent=None, delivery=None
        )
        save(run, "plan-submitted")
        return describe(run)


def validate_review(input: Any) -> dict[str, Any]:
    if not isinstance(input, dict):
        raise FactoryError("Review must be a JSON object.")
    nonempty(input.get("reviewer"), "Reviewer")
    if input.get("verdict") not in ("pass", "fail") or not isinstance(input.get("findings"), list):
        raise FactoryError("Review needs verdict pass/fail and findings array.")
    for finding in input["findings"]:
        if not isinstance(finding, dict) or finding.get("severity") not in ("blocking", "major", "minor"):
            raise FactoryError("Finding severity must be blocking, major or minor.")
        nonempty(finding.get("location"), "Finding location")
        nonempty(finding.get("issue"), "Finding issue")
    if input["verdict"] == "pass" and any(finding["severity"] != "minor" for finding in input["findings"]):
        raise FactoryError("Passing review contains unresolved blocking/major findings.")
    return input


def submit_plan_review(directory: str | Path, file: str | Path) -> dict[str, Any]:
    with transaction(directory) as run:
        active(run)
        input = validate_review(read_json(file))
        ctx = context(run)
        if not ctx["plan"] or fingerprint(input.get("context")) != fingerprint(ctx):
            raise FactoryError("Plan review context is stale or missing.", "gate")
        run["planReview"] = {**input, "at": now()}
        run.update(verification=None, codeReview=None)
        atomic_json(Path(directory) / f"plan-review-{len(run['history'])}.json", run["planReview"])
        run["phase"] = "implement" if input["verdict"] == "pass" else "plan"
        fail(run, "plan-review-failed") if input["verdict"] == "fail" else save(run, "plan-reviewed")
        return describe(run)


def verify(directory: str | Path) -> dict[str, Any]:
    with transaction(directory) as run:
        active(run)
        check_plan(run)
        before = evidence(run)
        run.update(commitIntent=None, delivery=None, verification=None, codeReview=None)
        run["checkAttempt"] += 1
        run["operation"] = {"kind": "verify", "evidence": before, "attempt": run["checkAttempt"]}
        save(run, "verify-intent")
        observation = progress.Observation(run)
        try:
            results = []
            for check in run["config"]["checks"]:
                observation.begin(check["name"])
                result = execute_check(check, run["worktree"], directory, run["checkAttempt"])
                results.append(result)
                observation.end(result)
                if not result["passed"]:
                    break
            after = evidence(run)
            unchanged = same_evidence(before, after)
            run["verification"] = {
                "evidence": after,
                "unchanged": unchanged,
                "results": results,
                "passed": unchanged
                and len(results) == len(run["config"]["checks"])
                and all(item["passed"] for item in results),
                "at": now(),
            }
            atomic_json(Path(directory) / f"verification-{run['checkAttempt']}.json", run["verification"])
            run["operation"] = None
            run["phase"] = "review" if run["verification"]["passed"] else "implement"
            save(run, "verified") if run["verification"]["passed"] else fail(run, "verify-failed")
            observation.finish(
                "interrupted"
                if any(item.get("error") == "Verification interrupted" for item in results)
                else "completed"
            )
        except BaseException:
            try:
                observation.finish("interrupted")
            except (OSError, FactoryError):
                pass
            raise
        return describe(run)


def submit_review(directory: str | Path, file: str | Path) -> dict[str, Any]:
    with transaction(directory) as run:
        active(run)
        current = check_verified(run)
        input = validate_review(read_json(file))
        if not same_evidence(input.get("evidence"), current):
            raise FactoryError("Code review evidence is stale or missing.", "gate")
        criteria = input.get("criteria")
        if (
            not isinstance(criteria, list)
            or len(criteria) != len(run["criteria"])
            or any(
                sum(isinstance(item, dict) and item.get("id") == criterion["id"] for item in criteria) != 1
                for criterion in run["criteria"]
            )
        ):
            raise FactoryError("Review must cover every acceptance criterion exactly once.")
        for criterion in criteria:
            if type(criterion.get("passed")) is not bool:
                raise FactoryError("Criterion passed must be boolean.")
            nonempty(criterion.get("evidence"), "Criterion evidence")
        if input["verdict"] == "pass" and any(not criterion["passed"] for criterion in criteria):
            raise FactoryError("Passing review has an unmet criterion.")
        run["codeReview"] = {**input, "at": now()}
        atomic_json(Path(directory) / f"code-review-{len(run['history'])}.json", run["codeReview"])
        run["phase"] = "deliver" if input["verdict"] == "pass" else "implement"
        fail(run, "code-review-failed") if input["verdict"] == "fail" else save(run, "code-reviewed")
        return describe(run)


def extend(directory: str | Path, count: int, reason: str) -> dict[str, Any]:
    with transaction(directory) as run:
        if run["phase"] != "blocked" or type(count) is not int or not 1 <= count <= 10:
            raise FactoryError("Extend a blocked run by 1–10 attempts.")
        nonempty(reason, "User-directed extension reason")
        run["failureLimit"] += count
        run["phase"] = "implement" if (run.get("planReview") or {}).get("verdict") == "pass" else "plan"
        save(run, "user-extension", count=count, reason=reason)
        return describe(run)


def recover(directory: str | Path) -> dict[str, Any]:
    return {"allocation": recover_lock(runs_root(read_run(directory)["common"])), "operation": recover_lock(directory)}


def recover_allocation(repo: str) -> dict[str, Any]:
    return recover_lock(runs_root(repository(repo).common))


def reconcile_rename(run: Run) -> None:
    intent = run.get("renameIntent")
    if not intent:
        return
    info = repository(run["worktree"])
    if (
        info.root != run["worktree"]
        or info.common != run["common"]
        or git(info.root, ["rev-parse", "HEAD"]).strip() != intent["head"]
    ):
        raise FactoryError("Interrupted rename ownership or HEAD changed.", "ownership")
    validate_branch(intent["to"])
    if run["branch"] != intent["from"]:
        raise FactoryError("Interrupted rename has inconsistent ownership.", "ownership")
    current = git(info.root, ["branch", "--show-current"]).strip()
    if current == intent["from"]:
        if git(info.root, ["branch", "--list", intent["to"]]).strip():
            raise FactoryError("Rename destination already exists.", "ownership")
        git(info.root, ["branch", "-m", intent["to"]])
    elif current != intent["to"] or git(info.root, ["branch", "--list", intent["from"]]).strip():
        raise FactoryError("Interrupted rename branch ownership changed.", "ownership")
    run.update(branch=intent["to"], renameIntent=None, verification=None, codeReview=None)
    assert_worktree(run)
    save(run, "branch-renamed", previous=intent["from"], branch=intent["to"])


def rename_branch(directory: str | Path, branch: str) -> dict[str, Any]:
    validate_branch(branch)
    with transaction(directory) as run:
        active(run)
        if run["phase"] == "preparing" or run.get("commitIntent") or run.get("delivery") or run.get("operation"):
            raise FactoryError("Rename requires a prepared run before delivery, with no operation in progress.")
        reconcile_rename(run)
        assert_worktree(run)
        if run["branch"] == branch:
            return describe(run)
        if git(run["worktree"], ["branch", "--list", branch]).strip():
            raise FactoryError("Rename destination already exists.")
        run["renameIntent"] = {
            "from": run["branch"],
            "to": branch,
            "head": git(run["worktree"], ["rev-parse", "HEAD"]).strip(),
        }
        save(run, "branch-rename-intent")
        reconcile_rename(run)
        return describe(run)
