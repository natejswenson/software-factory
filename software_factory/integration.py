"""Read local integration facts without changing task proof or Git objects."""

import os
import re
import stat
from pathlib import Path
from typing import Any

from . import history
from .errors import FactoryError
from .git import git

COMMIT = re.compile(r"[0-9a-f]{40}")
MARKERS = (("MERGE_HEAD", "merge", False), ("CHERRY_PICK_HEAD", "cherry-pick", False),
           ("rebase-merge", "rebase", True), ("rebase-apply", "rebase", True))
LIMITATIONS = [
    "Recorded delivery is historical; no remote PR, CI, merge or release state was queried.",
    "The target is a local ref at the reported hash; ancestry does not establish conflict freedom or passing checks.",
    "This inspection does not establish fresh task proof or authorize integration; follow the task engine's gates.",
    "Git must support --no-lazy-fetch; unsupported offline inspection fails closed.",
]


def _git(cwd: str | Path, args: list[str]) -> str:
    env = dict(os.environ)
    for name in ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        env.pop(name, None)
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")
    return git(cwd, ["--no-lazy-fetch", *args], env=env).strip()


def _object_git(common: Path, args: list[str]) -> str:
    return _git(common, ["--git-dir", str(common), *args])


def _validate_target(target: str) -> None:
    if (not target or target in ("HEAD", "@") or re.fullmatch(r"[0-9a-fA-F]{40}", target) or target.startswith("-")
            or any(ord(c) <= 32 or ord(c) == 127 or c in "~^:?*[\\" for c in target)
            or "@{" in target or ".." in target
            or (target.startswith("refs/") and not target.startswith(("refs/heads/", "refs/remotes/")))):
        raise FactoryError("Supply a named local branch/tracking ref as --target, without revision syntax.")


def _commit(common: Path, ref: str) -> str:
    value = _object_git(common, ["rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"])
    if not COMMIT.fullmatch(value):
        raise FactoryError("Commit observation returned an unsupported object ID.", "infrastructure")
    return value


def _target(common: Path, name: str) -> tuple[str, str]:
    ref = _object_git(common, ["rev-parse", "--symbolic-full-name", "--verify", "--end-of-options", name])
    if not ref.startswith(("refs/heads/", "refs/remotes/")) or "\n" in ref:
        raise FactoryError("Target must name a local branch or local tracking ref.", "invalid-target")
    return ref, _commit(common, ref)


def _identity(path: Path) -> tuple[int, int]:
    value = path.lstat()
    if not stat.S_ISDIR(value.st_mode):
        raise FactoryError("Repository/worktree directory is unavailable or unsafe.", "infrastructure")
    return value.st_dev, value.st_ino


def _current(root: Path, common: Path) -> tuple:
    identity = _identity(root)
    actual_root = Path(_git(root, ["rev-parse", "--show-toplevel"])).resolve()
    actual_common = (root / _git(root, ["rev-parse", "--git-common-dir"])).resolve()
    if actual_root != root.resolve() or actual_common != common.resolve():
        raise FactoryError("Worktree does not belong to the recorded repository.", "infrastructure")
    head = _git(root, ["rev-parse", "--verify", "HEAD^{commit}"])
    if not COMMIT.fullmatch(head):
        raise FactoryError("Current HEAD is unavailable.", "infrastructure")
    markers = []
    for name, label, directory in MARKERS:
        path = root / _git(root, ["rev-parse", "--git-path", name])
        try:
            info = path.lstat()
        except FileNotFoundError:
            markers.append((label, None))
            continue
        if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            raise FactoryError(f"Unsafe Git operation marker: {name}.", "infrastructure")
        markers.append((label, (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)))
    return identity, head, tuple(markers)


def _error(report: dict, code: str, message: str) -> None:
    report["errors"].append({"code": code, "message": message})


def _invalidate(report: dict) -> None:
    report["target"]["commit"] = report["target"]["resolvedRef"] = None
    report["head"]["commit"] = None
    report["ancestry"] = dict(targetIsAncestor=None, ahead=None, behind=None)
    report["current"].update(worktreeAvailable=None, pendingOperations=None, headMatchesReceipt=None, head=None)


def _observe(report: dict, run: dict, target: str) -> None:
    common = Path(run["common"])
    identity = _identity(common)
    resolved_common = Path(_object_git(common, ["rev-parse", "--git-common-dir"])).resolve()
    if resolved_common != common.resolve():
        raise FactoryError("Recorded Git common directory is not available.", "infrastructure")
    observed_target = current = None
    try:
        observed_target = _target(common, target)
        report["target"].update(resolvedRef=observed_target[0], commit=observed_target[1])
    except (FactoryError, OSError, ValueError) as error:
        if isinstance(error, FactoryError) and error.code == "invalid-target":
            raise
        _error(report, "target-unavailable", str(error))
    root = Path(run["worktree"])
    try:
        current = _current(root, common)
        report["current"].update(worktreeAvailable=True, head=current[1],
                                 pendingOperations=sorted({label for label, info in current[2] if info is not None}))
    except (FactoryError, OSError, ValueError) as error:
        report["current"]["worktreeAvailable"] = False if not root.exists() else None
        _error(report, "worktree-unavailable", str(error))
    receipt = report["recordedDelivery"]
    if receipt is not None:
        saved = receipt.get("commit")
        if receipt.get("endpoint") not in ("local", "draft-pr") or not isinstance(saved, str) or not COMMIT.fullmatch(saved):
            _error(report, "delivery-unavailable", "Recorded delivery commit/endpoint is malformed.")
        else:
            try:
                report["head"].update(source="recorded-delivery", commit=_commit(common, saved))
            except (FactoryError, OSError, ValueError) as error:
                _error(report, "head-unavailable", str(error))
            if current:
                report["current"]["headMatchesReceipt"] = current[1] == saved
    elif current:
        report["head"].update(source="worktree", commit=current[1])
    else:
        _error(report, "head-unavailable", "No recorded commit or available worktree HEAD.")
    head, target_commit = report["head"]["commit"], report["target"]["commit"]
    if head and target_commit:
        try:
            if _object_git(common, ["rev-parse", "--is-shallow-repository"]) != "false":
                raise FactoryError("Shallow or unavailable history cannot establish complete ancestry counts.", "infrastructure")
            counts = _object_git(common, ["rev-list", "--left-right", "--count", f"{target_commit}...{head}"]).split()
            if len(counts) != 2 or any(not re.fullmatch(r"[0-9]+", value) for value in counts):
                raise FactoryError("Ancestry counts are unavailable.", "infrastructure")
            behind, ahead = map(int, counts)
            report["ancestry"].update(targetIsAncestor=behind == 0, ahead=ahead, behind=behind)
        except (FactoryError, OSError, ValueError) as error:
            _error(report, "ancestry-unavailable", str(error))
    # A moving ref/HEAD/operation directory must not produce a mixed observation.
    if (_identity(common) != identity or (observed_target and _target(common, target) != observed_target)
            or (current and _current(root, common) != current)):
        raise FactoryError("Target, worktree or Git operation changed during inspection.", "snapshot-changed")


def inspect(directory: str | Path, target: str) -> dict[str, Any]:
    _validate_target(target)
    path = Path(directory).absolute()
    report = {
        "version": 1, "recordedDelivery": None, "target": {"ref": target, "resolvedRef": None, "commit": None},
        "head": {"commit": None, "source": None},
        "ancestry": {"targetIsAncestor": None, "ahead": None, "behind": None},
        "current": {"worktreeAvailable": None, "pendingOperations": None, "owner": None,
                    "headMatchesReceipt": None, "head": None},
        "nextSteps": [], "limitations": list(LIMITATIONS), "errors": [],
    }
    with history._directory(path) as fd:
        raw = history._read(fd, "state.json")
        run = history._run(raw, path)
        report["recordedDelivery"] = run.get("delivery")
        try:
            owner = history._owner(fd)
            report["current"]["owner"] = owner
        except (FactoryError, OSError, ValueError) as error:
            _error(report, "ownership-unavailable", str(error))
            owner = None
        if owner:
            _error(report, "locked", "Another operation owns the run; only saved delivery was read.")
        elif not report["errors"]:
            try:
                _observe(report, run, target)
            except (FactoryError, OSError, ValueError) as error:
                if isinstance(error, FactoryError) and error.code == "invalid-target":
                    raise
                _invalidate(report)
                _error(report, error.code if isinstance(error, FactoryError) else "inspection-unavailable", str(error))
        try:
            history._unchanged(path, fd, raw)
            if history._owner(fd) != owner:
                raise FactoryError("Operation ownership changed during inspection.", "snapshot-changed")
        except (FactoryError, OSError, ValueError) as error:
            _invalidate(report)
            _error(report, "snapshot-changed", str(error))
    if report["errors"]:
        report["nextSteps"] = ["Inspect the reported unavailable input or owner, then rerun after it is stable."]
    elif report["current"]["pendingOperations"]:
        report["nextSteps"] = ["Inspect the pending Git operation; resolve it only as a separately authorized task."]
    elif report["ancestry"]["targetIsAncestor"] is False:
        report["nextSteps"] = ["Plan a separately authorized integration task against the reported target commit.",
                               "Obtain fresh checks and review after integration edits before delivery."]
    else:
        report["nextSteps"] = ["Follow existing task verification, review and delivery gates; ancestry alone certifies none."]
    return report


def exit_code(report: dict) -> int:
    if report["errors"]:
        return 3
    return 2 if report["current"]["pendingOperations"] else 0


def format_report(report: dict) -> str:
    receipt = report["recordedDelivery"]
    lines = [f"Recorded delivery: {receipt.get('endpoint', 'unknown') if receipt else 'none (undelivered)'}"]
    if receipt:
        lines.append(f"  Commit: {receipt.get('commit', 'unknown')}")
        if receipt.get("pr"):
            lines.append(f"  PR: {receipt['pr']} (recorded; remote state unknown)")
    lines.extend([f"Local target: {report['target']['ref']} at {report['target']['commit'] or 'unknown'}",
                  f"Compared head: {report['head']['commit'] or 'unknown'} ({report['head']['source'] or 'unavailable'})"])
    ancestry = report["ancestry"]
    condition = {True: "target is an ancestor", False: "target is not an ancestor", None: "unknown"}[ancestry["targetIsAncestor"]]
    availability = {True: "available", False: "missing", None: "unknown"}[report["current"]["worktreeAvailable"]]
    lines.extend([f"Ancestry: {condition} (ahead: {ancestry['ahead']}; behind: {ancestry['behind']})",
                  f"Current worktree: {availability}"])
    pending = report["current"]["pendingOperations"]
    lines.append("Pending operations: " + ("unknown" if pending is None else ", ".join(pending) or "none observed"))
    lines.append(f"Current HEAD matches receipt: {report['current']['headMatchesReceipt']}")
    lines.extend(f"Unavailable: {item['code']}: {item['message']}" for item in report["errors"])
    lines.extend(f"Next: {item}" for item in report["nextSteps"])
    lines.extend(f"Limit: {item}" for item in report["limitations"])
    return "\n".join(lines)
