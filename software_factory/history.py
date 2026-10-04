"""Tolerant local-ledger views; strict allocation and task gates stay unchanged."""

import errno
import json
import math
import os
import re
import socket
import stat
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from . import engine
from .checks import validate_config
from .errors import FactoryError
from .git import repository
from .store import fingerprint, runs_root
from .validation import json_integer

PHASES = ("preparing", "plan", "plan-review", "implement", "review", "deliver", "blocked", "done")
RUN_NAME = re.compile(r"[a-f0-9-]{36}")
FILE_LIMIT = 2 * 1024 * 1024
ATTEMPT_LIMIT = 1000
JSON_DEPTH_LIMIT = 64
MAX_DURATION_MS = 2**63 - 1


@contextmanager
def _directory(path: Path, *, parent_fd: int | None = None):
    try:
        fd = os.open(
            path.name if parent_fd is not None else path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
    except OSError as error:
        code = "invalid" if error.errno in (errno.ELOOP, errno.ENOTDIR, errno.ENOENT) else "infrastructure"
        raise FactoryError(f"Cannot safely open run directory: {error}.", code) from error
    try:
        yield fd
    finally:
        os.close(fd)


def _read(fd: int, name: str, *, optional: bool = False, limit: int = FILE_LIMIT) -> bytes | None:
    try:
        if not stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
            raise FactoryError(f"Unsafe non-regular artifact: {name}.")
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise FactoryError(f"Unsafe non-regular artifact: {name}.")
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise FactoryError(f"Artifact exceeds {limit} bytes: {name}.")
        return raw
    except FileNotFoundError as error:
        if optional:
            return None
        raise FactoryError(f"Missing artifact: {name}.") from error
    except OSError as error:
        raise FactoryError(f"Cannot safely read {name}: {error}.", "infrastructure") from error


def _owner(fd: int) -> dict[str, Any] | None:
    try:
        os.stat("lock", dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    with _directory(Path("lock"), parent_fd=fd) as lock_fd:
        owner = _json(_read(lock_fd, "owner.json", limit=131072))
    if (
        not isinstance(owner, dict)
        or set(owner) != {"pid", "host", "at"}
        or not json_integer(owner.get("pid"))
        or owner["pid"] <= 0
        or not isinstance(owner.get("host"), str)
        or not isinstance(owner.get("at"), str)
    ):
        raise FactoryError("Malformed operation owner.")
    return owner


def _unchanged(path: Path, fd: int, raw: bytes) -> None:
    info = os.fstat(fd)
    current = path.lstat()
    if (
        not stat.S_ISDIR(current.st_mode)
        or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)
        or raw != _read(fd, "state.json")
    ):
        raise FactoryError("Run changed during inspection.", "snapshot-changed")


def _integer(value: Any, label: str, *, maximum: int | None = None) -> int:
    if not json_integer(value) or value < 0 or (maximum is not None and value > maximum):
        raise FactoryError(f"Invalid {label}.")
    return int(value)


def _json(raw: bytes) -> Any:
    try:
        value = json.loads(raw.decode("utf-8"))
    except RecursionError as error:
        raise FactoryError("Metadata JSON nesting exceeds parser capacity.") from error
    stack = [(iter([value]), 0)]
    while stack:
        iterator, depth = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        if isinstance(item, (dict, list)):
            if depth >= JSON_DEPTH_LIMIT:
                raise FactoryError(f"Metadata JSON nesting exceeds {JSON_DEPTH_LIMIT} levels.")
            stack.append((iter(item.values() if isinstance(item, dict) else item), depth + 1))
        elif type(item) is float and not math.isfinite(item):
            raise FactoryError("Metadata contains non-finite JSON numbers.")
    return value


def _run(raw: bytes, path: Path, *, common: str | None = None) -> dict[str, Any]:
    data = _json(raw)
    if (
        not isinstance(data, dict)
        or not json_integer(data.get("version"))
        or data["version"] != 1
        or data.get("dir") != str(path)
        or data.get("id") != path.name
        or not RUN_NAME.fullmatch(path.name)
    ):
        raise FactoryError("Unsupported run identity or directory.")
    for key in ("task", "branch", "baseRef", "base", "common", "repo", "worktree", "configHash"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise FactoryError(f"Invalid saved {key}.")
    if common is not None and data["common"] != common:
        raise FactoryError("Run belongs to another Git common directory.")
    if data.get("phase") not in PHASES or data.get("endpoint") not in ("local", "draft-pr"):
        raise FactoryError("Unsupported saved phase or endpoint.")
    _integer(data.get("checkAttempt"), "attempt counter", maximum=2**31 - 1)
    _integer(data.get("failures"), "failure counter", maximum=2**31 - 1)
    if not isinstance(data.get("history"), list) or not isinstance(data.get("criteria"), list):
        raise FactoryError("Invalid saved history or criteria.")
    if any(
        not isinstance(item, dict)
        or set(item) != {"id", "text"}
        or any(not isinstance(item.get(key), str) or not item[key].strip() for key in ("id", "text"))
        for item in data["criteria"]
    ):
        raise FactoryError("Malformed saved criteria.")
    validate_config(data.get("config"))
    if data.get("delivery") is not None and not isinstance(data["delivery"], dict):
        raise FactoryError("Invalid recorded delivery.")
    return data


def _error(path: Path, error: Exception, *, code: str | None = None) -> dict[str, Any]:
    return {
        "run": str(path),
        "code": code or (error.code if isinstance(error, FactoryError) else "invalid"),
        "message": str(error),
    }


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo is not None and result.utcoffset().total_seconds() == 0 else None
    except ValueError:
        return None


def _row(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data["id"],
        "run": data["dir"],
        "taskTitle": data["task"].splitlines()[0],
        "phase": data["phase"],
        "branch": data["branch"],
        "base": data["baseRef"],
        "endpoint": data["endpoint"],
        "updatedAt": data.get("updatedAt"),
        "attempts": data["checkAttempt"],
        "failures": data["failures"],
        "delivery": data.get("delivery"),
        "nextAction": None,
        "nextAvailable": False,
    }


def _collect(path: Path, root_fd: int, common: str) -> tuple[dict[str, Any] | None, datetime | None, list]:
    row = date = None
    errors = []
    for retry in range(2):
        try:
            with _directory(path, parent_fd=root_fd) as fd:
                raw = _read(fd, "state.json")
                data = _run(raw, path, common=common)
                row = _row(data)
                errors = []
                date = _date(data.get("updatedAt"))
                if date is None:
                    date = _date(data.get("createdAt"))
                    errors.append(
                        _error(
                            path,
                            FactoryError(
                                "Invalid/missing updatedAt; using createdAt if valid, otherwise sorting last."
                            ),
                            code="timestamp",
                        )
                    )
                try:
                    owner = _owner(fd)
                    if owner and (owner["host"] != socket.gethostname() or owner["pid"] != os.getpid()):
                        action = "wait"
                    else:
                        if not Path(data["worktree"]).is_dir():
                            raise FactoryError("Saved worktree is unavailable.", "inspection")
                        plan = _read(fd, "plan.md", optional=True)
                        action = engine.next_action(data, captured_plan=plan)["action"]
                        if plan != _read(fd, "plan.md", optional=True):
                            raise FactoryError("Plan changed during inspection.", "snapshot-changed")
                    if owner != _owner(fd):
                        raise FactoryError("Ownership changed during inspection.", "snapshot-changed")
                    _unchanged(path, fd, raw)
                    row.update(nextAction=action, nextAvailable=True)
                except (
                    FactoryError,
                    OSError,
                    ValueError,
                    KeyError,
                    TypeError,
                    AttributeError,
                    RecursionError,
                    OverflowError,
                ) as error:
                    if isinstance(error, FactoryError) and error.code == "snapshot-changed":
                        raise
                    errors.append(_error(path, error, code="inspection"))
                    _unchanged(path, fd, raw)
                return row, date, errors
        except (
            FactoryError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            RecursionError,
            OverflowError,
        ) as error:
            if isinstance(error, FactoryError) and error.code == "snapshot-changed" and retry == 0:
                continue
            if row:
                row.update(nextAction=None, nextAvailable=False)
            return row, date, [*errors, _error(path, error)]
    raise AssertionError("Unreachable bounded retry")


def discover(repo: str, *, phase: str | None = None, limit: int = 20) -> dict[str, Any]:
    if phase is not None and phase not in PHASES:
        raise FactoryError("Choose an existing --phase.")
    if not json_integer(limit) or not 1 <= limit <= 1000:
        raise FactoryError("--limit must be 1–1000.")
    info = repository(repo)
    root = runs_root(info.common)
    report = {"version": 1, "repo": info.root, "total": 0, "matched": 0, "runs": [], "errors": []}
    try:
        if not root.exists() and not root.is_symlink():
            return report
        with (
            _directory(Path(info.common)) as common_fd,
            _directory(root.parent, parent_fd=common_fd) as factory_fd,
            _directory(root, parent_fd=factory_fd) as fd,
        ):
            # Names only. Candidate directories and descendants are opened relative to this pinned root.
            with os.scandir(fd) as entries:
                names = sorted(entry.name for entry in entries if RUN_NAME.fullmatch(entry.name))
            rows = []
            for name in names:
                row, date, errors = _collect(root / name, fd, info.common)
                report["errors"].extend(errors)
                if row is not None:
                    rows.append((row, date))
    except (FactoryError, OSError) as error:
        raise FactoryError(f"Cannot enumerate private runs: {error}.", "infrastructure") from error
    rows.sort(key=lambda pair: (pair[1] is None, -pair[1].timestamp() if pair[1] is not None else 0, pair[0]["id"]))
    report["total"] = len(rows)
    matching = [row for row, _ in rows if phase is None or row["phase"] == phase]
    report["matched"] = len(matching)
    report["runs"] = matching[: int(limit)]
    return report


def _attempt(fd: int, path: Path, number: int, names: list[str]) -> tuple[dict, bytes | None, list]:
    name = f"verification-{number}.json"
    raw = _read(fd, name, optional=True)
    report = {
        "attempt": number,
        "status": "missing",
        "at": None,
        "passed": None,
        "unchanged": None,
        "evidenceAvailable": False,
        "checks": [{"name": name, "status": "unknown", "durationMs": None, "log": None} for name in names],
    }
    errors = []
    if raw is None:
        return report, raw, [_error(path, FactoryError(f"Missing expected receipt: {name}."), code="missing-receipt")]
    try:
        receipt = _json(raw)
        if (
            not isinstance(receipt, dict)
            or type(receipt.get("passed")) is not bool
            or type(receipt.get("unchanged")) is not bool
            or not isinstance(receipt.get("results"), list)
        ):
            raise FactoryError(f"Malformed receipt: {name}.")
        results = receipt["results"]
        if len(results) > len(names) or any(
            not isinstance(item, dict) or item.get("name") != names[index] or type(item.get("passed")) is not bool
            for index, item in enumerate(results)
        ):
            raise FactoryError(f"Malformed check order/outcomes: {name}.")
        if receipt["passed"] and (
            not receipt["unchanged"] or len(results) != len(names) or not all(item["passed"] for item in results)
        ):
            raise FactoryError(f"Inconsistent passing receipt: {name}.")
        if receipt.get("evidence") is not None and not isinstance(receipt["evidence"], dict):
            raise FactoryError(f"Malformed evidence: {name}.")
        report.update(
            status="recorded",
            at=receipt.get("at"),
            passed=receipt["passed"],
            unchanged=receipt["unchanged"],
            evidenceAvailable=isinstance(receipt.get("evidence"), dict)
            and all(
                isinstance(receipt["evidence"].get(key), str) and receipt["evidence"][key]
                for key in ("base", "criteria", "config", "plan", "head", "tree")
            ),
        )
        if _date(receipt.get("at")) is None:
            errors.append(_error(path, FactoryError(f"Invalid/missing receipt timestamp: {name}."), code="timestamp"))
        for index, check in enumerate(report["checks"]):
            if index >= len(results):
                check["status"] = "not-run"
                continue
            result = results[index]
            duration = result.get("durationMs")
            if duration is not None and (not json_integer(duration) or not 0 <= duration <= MAX_DURATION_MS):
                errors.append(_error(path, FactoryError(f"Invalid duration: {name}/{check['name']}."), code="metric"))
                duration = None
            log = result.get("log")
            if log is not None and not isinstance(log, str):
                errors.append(
                    _error(path, FactoryError(f"Invalid log reference: {name}/{check['name']}."), code="metric")
                )
                log = None
            check.update(
                status="passed" if result["passed"] else "failed",
                durationMs=int(duration) if duration is not None else None,
                log=log,
            )
    except (FactoryError, ValueError, KeyError, TypeError) as error:
        report.update(status="invalid")
        errors.append(_error(path, error))
    return report, raw, errors


def inspect(directory: str, *, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    _integer(offset, "--offset")
    if not json_integer(limit) or not 1 <= limit <= 1000:
        raise FactoryError("--limit must be 1–1000.")
    path = Path(directory).absolute()
    report = None
    for retry in range(2):
        opened = False
        try:
            with _directory(path) as fd:
                opened = True
                raw = _read(fd, "state.json")
                data = _run(raw, path)
                report = {
                    "version": 1,
                    "id": data["id"],
                    "phase": data["phase"],
                    "eventsTotal": len(data["history"]),
                    "offset": int(offset),
                    "events": [],
                    "attempts": [],
                    "totals": {},
                    "delivery": data.get("delivery"),
                    "errors": [],
                }
                for index, event in enumerate(data["history"][int(offset) : int(offset) + int(limit)], int(offset)):
                    valid = isinstance(event, dict)
                    item = {
                        "index": index,
                        "at": event.get("at") if valid else None,
                        "action": event.get("action") if valid else None,
                        "details": {key: value for key, value in event.items() if key not in ("at", "action")}
                        if valid
                        else None,
                    }
                    report["events"].append(item)
                    if (
                        not valid
                        or _date(item["at"]) is None
                        or not isinstance(item["action"], str)
                        or not item["action"].strip()
                    ):
                        report["errors"].append(
                            _error(path, FactoryError(f"Invalid event at index {index}."), code="event")
                        )
                count = _integer(data["checkAttempt"], "attempt counter")
                if count > ATTEMPT_LIMIT:
                    report["errors"].append(
                        _error(
                            path,
                            FactoryError(
                                f"History supports at most {ATTEMPT_LIMIT} attempt records; saved counter is {count}."
                            ),
                            code="attempt-limit",
                        )
                    )
                    count = ATTEMPT_LIMIT
                names = [item["name"] for item in data["config"]["checks"]]
                saved = []
                for number in range(1, count + 1):
                    filename = f"verification-{number}.json"
                    try:
                        attempt, body, errors = _attempt(fd, path, number, names)
                        saved.append((filename, fingerprint(body) if body is not None else None))
                    except (FactoryError, OSError, ValueError) as error:
                        attempt = {
                            "attempt": number,
                            "status": "unavailable",
                            "at": None,
                            "passed": None,
                            "unchanged": None,
                            "evidenceAvailable": False,
                            "checks": [
                                {"name": name, "status": "unknown", "durationMs": None, "log": None} for name in names
                            ],
                        }
                        errors = [_error(path, error)]
                    report["attempts"].append(attempt)
                    report["errors"].extend(errors)
                recorded = [item for item in report["attempts"] if item["status"] == "recorded"]
                durations = [
                    check["durationMs"]
                    for item in recorded
                    for check in item["checks"]
                    if check["durationMs"] is not None
                ]
                report["totals"] = {
                    "knownAttempts": len(recorded),
                    "failures": data["failures"],
                    "checkExecutionMs": sum(durations),
                    "missingReceipts": sum(item["status"] == "missing" for item in report["attempts"]),
                    "missingDurationMetrics": sum(
                        check["durationMs"] is None and check["status"] in ("passed", "failed")
                        for item in recorded
                        for check in item["checks"]
                    ),
                }
                for filename, digest in saved:
                    body = _read(fd, filename, optional=True)
                    if digest != (fingerprint(body) if body is not None else None):
                        raise FactoryError("Attempt receipt changed during inspection.", "snapshot-changed")
                _unchanged(path, fd, raw)
                return report
        except (
            FactoryError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            RecursionError,
            OverflowError,
        ) as error:
            if not opened and isinstance(error, FactoryError) and error.code == "infrastructure":
                raise error
            if isinstance(error, FactoryError) and error.code == "snapshot-changed" and retry == 0:
                continue
            if report is None:
                report = {
                    "version": 1,
                    "id": path.name,
                    "phase": None,
                    "eventsTotal": None,
                    "offset": int(offset),
                    "events": [],
                    "attempts": [],
                    "totals": {},
                    "delivery": None,
                    "errors": [],
                }
            if isinstance(error, FactoryError) and error.code == "snapshot-changed":
                report["events"] = []
                report["eventsTotal"] = None
                report["delivery"] = None
                for attempt in report["attempts"]:
                    attempt.update(status="unavailable", at=None, passed=None, unchanged=None, evidenceAvailable=False)
                    for check in attempt["checks"]:
                        check.update(status="unknown", durationMs=None, log=None)
                report["totals"] = {
                    key: None
                    for key in (
                        "knownAttempts",
                        "failures",
                        "checkExecutionMs",
                        "missingReceipts",
                        "missingDurationMetrics",
                    )
                }
            report["errors"].append(_error(path, error))
            return report
    raise AssertionError("Unreachable bounded retry")


def format_runs(report: dict[str, Any]) -> str:
    lines = [f"Repository: {report['repo']}    Recorded rows: {report['total']}    Matched: {report['matched']}"]
    for row in report["runs"]:
        lines.extend(
            [
                f"{row['taskTitle']} [{row['phase']}]",
                f"  ID: {row['id']}    Run: {row['run']}",
                f"  Branch: {row['branch']}    Base: {row['base']}    Endpoint: {row['endpoint']}",
                f"  Updated: {row['updatedAt']}    Attempts: {row['attempts']}    Failures: {row['failures']}",
                f"  Current next: {row['nextAction']}    Available: {row['nextAvailable']}",
                f"  Recorded delivery: {row['delivery']}",
            ]
        )
    lines.extend(f"Error {item['run']} [{item['code']}]: {item['message']}" for item in report["errors"])
    return "\n".join(lines)


def format_history(report: dict[str, Any]) -> str:
    lines = [
        f"Run: {report['id']}    State: {report['phase']}    Events: {report['eventsTotal']}    Offset: {report['offset']}"
    ]
    lines.extend(
        f"Event {item['index']} {item['at']}: {item['action']}    Details: {item['details']}"
        for item in report["events"]
    )
    for attempt in report["attempts"]:
        lines.append(
            f"Attempt {attempt['attempt']}: {attempt['status']}    At: {attempt['at']}    Passed: {attempt['passed']}    Unchanged: {attempt['unchanged']}    Evidence available: {attempt['evidenceAvailable']}"
        )
        lines.extend(
            f"  {item['name']}: {item['status']}    Duration ms: {item['durationMs']}    Log: {item['log']}"
            for item in attempt["checks"]
        )
    lines.extend(
        [
            f"Totals (check execution time, not task wall time): {report['totals']}",
            f"Recorded delivery: {report['delivery']}",
        ]
    )
    lines.extend(f"Error [{item['code']}]: {item['message']}" for item in report["errors"])
    return "\n".join(lines)
