"""Read-only, advisory probes for task start; no allocation, execution or network."""

import errno
import os
import re
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import validate_branch
from .errors import FactoryError
from .git import assert_supported, git, repository
from .rules import assert_committed, read_project
from .store import runs_root

LIMITATIONS = [
    "Local observations are advisory snapshots; start and delivery revalidate their original gates.",
    "No checks, interpreter imports, network/auth probes, writes, locks or task allocation were performed.",
    "Access and tool presence do not prove host approval, dependencies, test outcomes or actual worktree creation.",
    "No task was supplied: duplicate runs, allocation lock availability and the task-derived branch are not reserved or certified.",
    "Relative executable modes are inspected on the selected base; the eventual worktree is authoritative.",
]


class Probes:
    def __init__(self):
        self.checks: list[dict[str, Any]] = []

    def add(self, name: str, scope: str, status: str, message: str, remedy: str | None = None) -> None:
        self.checks.append({"name": name, "scope": scope, "status": status, "message": message, "remedy": remedy})

    def observe(self, name: str, function: Callable[[], tuple[Any, str]], remedy: str, scope: str = "start") -> Any:
        try:
            value, message = function()
            self.add(name, scope, "pass", message)
            return value
        except (FactoryError, OSError, ValueError) as error:
            status = (
                "fail"
                if (
                    isinstance(error, ValueError)
                    or (isinstance(error, FactoryError) and error.code != "infrastructure")
                    or (isinstance(error, OSError) and error.errno == errno.ELOOP)
                )
                else "unknown"
            )
            self.add(name, scope, status, str(error), remedy)
            return None

    def unknown(self, name: str, reason: str, scope: str = "start") -> None:
        self.add(name, scope, "unknown", reason, "Resolve the preceding prerequisite and rerun preflight.")


def _resolve_path(path: str | Path) -> Path:
    try:
        return Path(path).resolve()
    except RuntimeError as error:  # Python 3.11 reports symlink loops this way.
        raise FactoryError("Path contains a symlink loop.") from error
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise FactoryError("Path contains a symlink loop.") from error
        raise


def _repository(path: str):
    candidate = _resolve_path(path)
    try:
        mode = candidate.stat().st_mode
    except (FileNotFoundError, NotADirectoryError) as error:
        raise FactoryError("--repo must name an existing Git worktree directory.") from error
    if not stat.S_ISDIR(mode):
        raise FactoryError("--repo must name an existing Git worktree directory.")
    try:
        return repository(candidate), "Git worktree and common directory resolved."
    except FactoryError as error:
        if any(message in str(error).lower() for message in ("not a git repository", "must be run in a work tree")):
            raise FactoryError("--repo is not a Git worktree.") from error
        raise


def _base(root: str, requested: str | None):
    reference = requested or ("main" if git(root, ["branch", "--list", "main"]).strip() else "HEAD")
    value = git(root, ["rev-parse", "--revs-only", "--end-of-options", f"{reference}^{{commit}}"]).strip()
    if not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", value):
        raise FactoryError(f"Selected base {reference!r} does not resolve to one commit.")
    return (reference, value), f"Selected base {reference!r} resolves to {value}."


def _path(path: str | Path):
    resolved = _resolve_path(path)
    ancestor = resolved
    while True:
        try:
            info = ancestor.stat()
            break
        except FileNotFoundError:
            ancestor = ancestor.parent
        except NotADirectoryError as error:
            raise FactoryError(f"{resolved}: an existing parent is not a directory.") from error
    if not stat.S_ISDIR(info.st_mode):
        raise FactoryError(f"{ancestor}: expected a directory.")
    if not os.access(ancestor, os.W_OK | os.X_OK):
        raise FactoryError(f"{ancestor}: write/traversal access is not available (advisory).")
    return str(resolved), f"{resolved}: nearest existing directory {ancestor} permits advisory write/traversal access."


def _branch(root: str | None, value: str | None):
    if value is None:
        return True, "No explicit branch; start will derive and validate it from the task."
    validate_branch(value)
    if root is None:
        raise FactoryError("Cannot inspect branch collision without a Git worktree.", "infrastructure")
    if git(root, ["branch", "--list", value]).strip():
        raise FactoryError(f"Branch {value!r} already exists.")
    return True, f"Explicit branch {value!r} is valid and locally unused (not reserved)."


def _executable(root: str, base: str | None, executable: str):
    if Path(executable).is_absolute():
        path = Path(executable)
        try:
            mode = path.stat().st_mode
        except (FileNotFoundError, NotADirectoryError) as error:
            raise FactoryError(f"Absolute executable {executable!r} is missing.") from error
        if not stat.S_ISREG(mode) or not os.access(path, os.X_OK):
            raise FactoryError(f"Absolute executable {executable!r} is missing or not executable.")
        return True, f"Absolute executable {executable!r} is locally available."
    if "/" not in executable:
        if shutil.which(executable) is None:
            raise FactoryError(f"Executable {executable!r} is not available on PATH.")
        return True, f"Executable {executable!r} is available on PATH; imports/dependencies were not checked."
    relative = os.path.normpath(executable)
    if relative == ".." or relative.startswith("../"):
        raise FactoryError(
            f"Relative executable {executable!r} resolves outside the future worktree; availability cannot be established before allocation.",
            "infrastructure",
        )
    if base is None:
        raise FactoryError("Repository-relative executable requires an available selected base.", "infrastructure")
    entries = git(root, ["ls-tree", "-z", base, "--", relative]).split("\0")
    entry = next((entry for entry in entries if entry and entry.split("\t", 1)[1] == relative), None)
    if entry is None:
        raise FactoryError(f"Relative executable {executable!r} is absent on the selected base.")
    mode, kind, _ = entry.split("\t", 1)[0].split()
    if mode == "120000":
        raise FactoryError(
            f"Relative executable {executable!r} is a base symlink; target execution remains unknown.", "infrastructure"
        )
    if kind != "blob" or mode != "100755":
        raise FactoryError(
            f"Relative executable {executable!r} is not an executable regular file on the selected base."
        )
    return True, f"Relative executable {executable!r} exists with executable mode on the selected base."


def inspect(
    repo: str, worktree_root: str, *, base: str | None = None, branch: str | None = None, endpoint: str | None = None
) -> dict[str, Any]:
    probes = Probes()
    info = probes.observe(
        "repository", lambda: _repository(repo), "Select an accessible Git worktree; check Git installation/access."
    )
    root = info.root if info else None
    selected = None
    project = None
    if info:
        probes.observe(
            "git-state",
            lambda: (assert_supported(root), "Index has no conflicts or unsupported submodules."),
            "Resolve index conflicts or remove unsupported submodules.",
        )
        selected = probes.observe(
            "base", lambda: _base(root, base), "Select an existing local base commit/branch and rerun."
        )
        project = probes.observe(
            "configuration",
            lambda: (read_project(root), "Factory checks/settings and repository rules are valid."),
            "Correct the repository settings/rules and configure meaningful checks.",
        )
        if selected and project:
            probes.observe(
                "committed-settings",
                lambda: (
                    assert_committed(root, selected[1], project),
                    "Settings/rules match the committed selected base.",
                ),
                "Review and commit settings/rules on the selected base.",
            )
        else:
            probes.unknown("committed-settings", "Base or valid settings could not be established.")
        probes.observe(
            "allocation-path",
            lambda: _path(runs_root(info.common)),
            "Repair non-directory allocation paths or unavailable parent access; do not delete run evidence.",
        )
        probes.observe(
            "source-dirt",
            lambda: (
                True,
                "Unrelated source dirt is allowed; settings dirt is validated separately. "
                + (
                    "Working tree contains changes."
                    if git(root, ["--no-optional-locks", "status", "--porcelain"]).strip()
                    else "Working tree is clean."
                ),
            ),
            "Inspect local source status/access.",
        )
    else:
        for name in ("git-state", "base", "configuration", "committed-settings", "allocation-path", "source-dirt"):
            probes.unknown(name, "Git repository could not be established.")
    chosen = endpoint if endpoint is not None else project["config"]["endpoint"] if project else None
    if chosen is None:
        probes.unknown("endpoint", "Default endpoint depends on valid settings.")
    elif chosen not in ("local", "draft-pr"):
        probes.add(
            "endpoint", "start", "fail", "Endpoint must be local or draft-pr.", "Select --endpoint local or draft-pr."
        )
        chosen = None
    else:
        probes.add("endpoint", "start", "pass", f"Selected endpoint: {chosen}.")
    probes.observe(
        "branch", lambda: _branch(root, branch), "Choose a valid unused feature/name, bug/name or issue/name branch."
    )
    probes.observe(
        "worktree-root", lambda: _path(worktree_root), "Select a directory beneath an accessible writable parent."
    )
    if project:
        for check in project["config"]["checks"]:
            probes.observe(
                f"executable:{check['name']}",
                lambda check=check: _executable(root, selected[1] if selected else None, check["argv"][0]),
                "Install/select the executable or commit its executable file on the selected base.",
            )
    else:
        probes.unknown("executables", "Executable candidates require valid settings.")
    if chosen == "draft-pr":
        try:
            available = shutil.which("gh") is not None
            probes.add(
                "delivery-gh",
                "delivery",
                "pass" if available else "fail",
                "gh is locally available." if available else "gh is not available on PATH.",
                None if available else "Install gh and authenticate before actual delivery.",
            )
        except OSError:
            probes.unknown("delivery-gh", "Could not inspect local gh availability.", "delivery")
        if root:
            try:
                remotes = git(root, ["remote", "-v"]).splitlines()
                origin = any(
                    line.startswith("origin\t")
                    and line.endswith(" (fetch)")
                    and bool(line.split("\t", 1)[1].removesuffix(" (fetch)").strip())
                    for line in remotes
                )
                probes.add(
                    "delivery-origin",
                    "delivery",
                    "pass" if origin else "fail",
                    "origin URL is configured (value withheld)." if origin else "origin URL is not configured.",
                    None if origin else "Configure the intended GitHub origin before delivery.",
                )
            except FactoryError:
                probes.unknown(
                    "delivery-origin",
                    "Could not establish origin availability; no remote URL or raw error is displayed.",
                    "delivery",
                )
        else:
            probes.unknown("delivery-origin", "Repository is unavailable.", "delivery")
        if selected:
            try:
                symbolic = git(
                    root, ["rev-parse", "--symbolic-full-name", "--revs-only", "--end-of-options", selected[0]]
                ).strip()
                named = selected[0] != "HEAD" and symbolic.startswith(("refs/heads/", "refs/remotes/"))
                probes.add(
                    "delivery-base",
                    "delivery",
                    "pass" if named else "fail",
                    "A named base was selected; remote eligibility is unknown."
                    if named
                    else "Draft PR delivery needs a named base branch.",
                    None if named else "Select a named --base branch for draft delivery.",
                )
            except FactoryError:
                probes.unknown("delivery-base", "Could not establish a named local base branch.", "delivery")
        else:
            probes.unknown("delivery-base", "Selected base is unavailable.", "delivery")
    elif chosen is None:
        probes.unknown("delivery", "Delivery prerequisites depend on a valid endpoint.", "delivery")
    start = [check for check in probes.checks if check["scope"] == "start" and check["name"] != "source-dirt"]
    ready = all(check["status"] == "pass" for check in start)
    local_blocked = any(check["status"] == "fail" for check in start)
    delivery_blocked = any(check["scope"] == "delivery" and check["status"] == "fail" for check in probes.checks)
    delivery_ready = (
        (True if ready else False if local_blocked else None)
        if chosen == "local"
        else False
        if delivery_blocked
        else None
    )
    return {
        "version": 1,
        "repo": root,
        "baseRef": selected[0] if selected else base,
        "base": selected[1] if selected else None,
        "endpoint": chosen,
        "ready": ready,
        "deliveryReady": delivery_ready,
        "checks": probes.checks,
        "limitations": [
            *LIMITATIONS,
            *(
                ["Remote authentication, access, branch state and PR eligibility remain unknown offline."]
                if chosen == "draft-pr"
                else []
            ),
        ],
    }


def exit_code(report: dict[str, Any]) -> int:
    if report["ready"]:
        return 0
    return 2 if any(check["scope"] == "start" and check["status"] == "fail" for check in report["checks"]) else 3


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"Start ready: {report['ready']}    Delivery ready: {report['deliveryReady']}",
        f"Repository: {report['repo']}    Base: {report['baseRef']} ({report['base']})    Endpoint: {report['endpoint']}",
    ]
    for check in report["checks"]:
        lines.append(f"{check['scope']}/{check['name']}: {check['status']} — {check['message']}")
        if check["remedy"]:
            lines.append(f"  Remedy: {check['remedy']}")
    lines.extend(f"Limit: {limitation}" for limitation in report["limitations"])
    return "\n".join(lines)
