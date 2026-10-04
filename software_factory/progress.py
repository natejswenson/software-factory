"""Private verification observations and safe, bounded read-only log tails."""

import json
import os
import socket
import stat
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .checks import validate_config
from .errors import FactoryError
from .ownership import inspect_owner
from .store import Run, atomic_json, now
from .validation import json_integer

SIDECAR = "verification-progress.json"
JSON_LIMIT = 2 * 1024 * 1024
# Supported macOS/Linux pid_t is a signed 32-bit value. Never probe malformed IDs.
MAX_PID = 2**31 - 1
LIMITATIONS = [
    "Progress is observational, not evidence of freshness, review or delivery.",
    "Owner receipts and PID probes do not guarantee hostile-process identity.",
]


def _read(path: Path, *, optional: bool = False, limit: int = JSON_LIMIT) -> bytes | None:
    try:
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise FactoryError(f"Unsafe non-regular file: {path.name}.")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise FactoryError(f"Unsafe non-regular file: {path.name}.")
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise FactoryError(f"Observation file exceeds {limit} bytes: {path.name}.")
        return raw
    except FileNotFoundError as error:
        if optional:
            return None
        raise FactoryError(f"Missing file: {path.name}.") from error
    except OSError as error:
        raise FactoryError(f"Cannot read {path.name}: {error}.", "infrastructure") from error


def _counter(run: Run) -> int:
    attempt = run.get("checkAttempt")
    if not json_integer(attempt) or attempt < 0:
        raise FactoryError("Saved verification attempt is invalid.")
    validate_config(run.get("config"))
    return int(attempt)


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Missing UTC time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Time must be UTC")
    return parsed


def _results(value: Any, names: list[str]) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= len(names)
        and all(
            isinstance(item, dict) and item.get("name") == names[index] and type(item.get("passed")) is bool
            for index, item in enumerate(value)
        )
    )


class Observation:
    """Only the existing verification owner writes these non-proof transitions."""

    def __init__(self, run: Run):
        self.path = Path(run["dir"]) / SIDECAR
        self.started = time.monotonic()
        self.data = {
            "version": 1,
            "id": run["id"],
            "attempt": run["checkAttempt"],
            "owner": inspect_owner(run["dir"]),
            "startedAt": now(),
            "observedAt": now(),
            "status": "running",
            "activeCheck": None,
            "elapsedMs": None,
            "checks": [
                {"name": item["name"], "status": "pending", "startedAt": None, "result": None}
                for item in run["config"]["checks"]
            ],
        }
        self.write()

    def write(self) -> None:
        self.data["observedAt"] = now()
        atomic_json(self.path, self.data)

    def begin(self, name: str) -> None:
        self.data["activeCheck"] = name
        check = next(item for item in self.data["checks"] if item["name"] == name)
        check.update(status="running", startedAt=now())
        self.write()

    def end(self, result: dict[str, Any]) -> None:
        check = next(item for item in self.data["checks"] if item["name"] == result["name"])
        check.update(status="passed" if result["passed"] else "failed", result=result)
        self.data["activeCheck"] = None
        self.write()

    def finish(self, status: str = "completed") -> None:
        self.data.update(status=status, activeCheck=None, elapsedMs=round((time.monotonic() - self.started) * 1000))
        for check in self.data["checks"]:
            if check["status"] in ("pending", "running"):
                check["status"] = "skipped" if status == "completed" else "unknown"
        self.write()


def _sidecar(raw: bytes | None, run: Run, names: list[str]) -> dict[str, Any] | None:
    if raw is None:
        return None
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or type(data.get("version")) is not int
        or data["version"] != 1
        or data.get("id") != run["id"]
        or not json_integer(data.get("attempt"))
        or data["attempt"] != run["checkAttempt"]
        or data.get("status") not in ("running", "completed", "interrupted", "unknown")
        or not isinstance(data.get("checks"), list)
        or len(data["checks"]) != len(names)
        or data.get("activeCheck") not in (None, *names)
        or (data.get("elapsedMs") is not None and (not json_integer(data["elapsedMs"]) or data["elapsedMs"] < 0))
    ):
        raise ValueError("Sidecar identity, attempt or shape disagrees with state")
    _time(data.get("startedAt"))
    _time(data.get("observedAt"))
    seen_results = []
    running = []
    for name, check in zip(names, data["checks"]):
        if (
            not isinstance(check, dict)
            or check.get("name") != name
            or check.get("status") not in ("pending", "running", "passed", "failed", "skipped", "unknown")
        ):
            raise ValueError("Invalid check observation")
        result = check.get("result")
        if result is not None:
            seen_results.append(result)
            if not isinstance(result, dict) or result.get("name") != name or type(result.get("passed")) is not bool:
                raise ValueError("Invalid observed result")
            if check["status"] != ("passed" if result["passed"] else "failed"):
                raise ValueError("Result and status disagree")
        elif check["status"] in ("passed", "failed"):
            raise ValueError("Result is missing")
        if check["status"] == "running":
            running.append(name)
        if check.get("startedAt") is not None:
            _time(check["startedAt"])
    if not _results(seen_results, names) or running != ([] if data["activeCheck"] is None else [data["activeCheck"]]):
        raise ValueError("Sidecar check order or active check disagrees")
    owner = data.get("owner")
    if (
        not isinstance(owner, dict)
        or set(owner) != {"pid", "host", "at"}
        or not json_integer(owner.get("pid"))
        or not 1 <= owner["pid"] <= MAX_PID
        or not isinstance(owner.get("host"), str)
    ):
        raise ValueError("Invalid sidecar owner")
    _time(owner.get("at"))
    return data


def _snapshot(run: Run) -> tuple[bytes, bytes | None, dict[str, Any] | None, list[str]]:
    state = _read(Path(run["dir"]) / "state.json")
    if json.loads(state) != run:
        raise FactoryError("Run changed before observation.", "snapshot-changed")
    limitations = list(LIMITATIONS)
    try:
        raw = _read(Path(run["dir"]) / SIDECAR, optional=True)
    except FactoryError as error:
        raw = None
        limitations.append(f"Sidecar unavailable: {error}")
    try:
        owner = inspect_owner(run["dir"])
    except (FactoryError, OSError, ValueError) as error:
        owner = None
        limitations.append(f"Owner unavailable: {error}")
    return state, raw, owner, limitations


def _stable(run: Run, before: tuple) -> None:
    after = _snapshot(run)
    if before != after:
        raise FactoryError("Run, sidecar or ownership changed during observation; retry.", "snapshot-changed")


def _duration(results: list[dict[str, Any]]) -> int | None:
    values = [
        int(item["durationMs"]) for item in results if json_integer(item.get("durationMs")) and item["durationMs"] >= 0
    ]
    return sum(values) if values else None


def observe(run: Run) -> dict[str, Any]:
    attempt = _counter(run)
    names = [item["name"] for item in run["config"]["checks"]]
    before = _snapshot(run)
    _, raw, owner, initial_limitations = before
    limitations = list(initial_limitations)
    sidecar = None
    try:
        sidecar = _sidecar(raw, run, names)
    except (ValueError, TypeError, KeyError) as error:
        limitations.append(f"Sidecar unavailable or stale: {error}.")
    report = {
        "version": 1,
        "id": run["id"],
        "attempt": attempt,
        "status": "unknown",
        "activeCheck": None,
        "elapsedMs": None,
        "checks": [{"name": name, "status": "unknown", "result": None} for name in names],
        "owner": owner,
        "observedAt": now(),
        "limitations": limitations,
    }
    operation = run.get("operation")
    verifying = isinstance(operation, dict) and operation.get("kind") == "verify"
    record = run.get("verification")
    if not verifying and attempt > 0 and isinstance(record, dict) and _results(record.get("results"), names):
        results = record["results"]
        interrupted = any(item.get("error") == "Verification interrupted" for item in results)
        report["status"] = "interrupted" if interrupted else "completed"
        report["checks"] = [
            {"name": name, "status": "passed" if results[index]["passed"] else "failed", "result": results[index]}
            if index < len(results)
            else {"name": name, "status": "skipped", "result": None}
            for index, name in enumerate(names)
        ]
        if (
            sidecar
            and sidecar["status"] in ("completed", "interrupted")
            and sidecar["elapsedMs"] is not None
            and [item["result"] for item in sidecar["checks"] if item["result"] is not None] == results
        ):
            report["elapsedMs"] = sidecar["elapsedMs"]
        else:
            report["elapsedMs"] = _duration(results)
            limitations.append("Elapsed time sums available check durations; gaps and task wall time are not measured.")
            if raw is not None:
                limitations.append("Matching saved final results take precedence over a stale sidecar.")
    elif attempt == 0 and not verifying:
        report.update(
            status="not-started", checks=[{"name": name, "status": "pending", "result": None} for name in names]
        )
    elif verifying and operation.get("attempt") == attempt:
        identity_matches = sidecar is not None and owner == sidecar["owner"]
        if owner is not None and not 1 <= owner["pid"] <= MAX_PID:
            limitations.append("Owner PID is outside the supported OS range; no process probe was made.")
        elif owner is not None and owner["host"] == socket.gethostname():
            try:
                os.kill(int(owner["pid"]), 0)
                live = True
            except ProcessLookupError:
                live = False
            except (OSError, OverflowError):
                live = None
            if live is False:
                report["status"] = "interrupted"
                limitations.append("The saved same-host owner is dead; abrupt exit may leave check descendants.")
            elif live is True and identity_matches and sidecar["status"] == "running":
                report["status"] = "running"
            else:
                limitations.append("Live progress could not be established from matching owner and sidecar.")
        else:
            limitations.append("Missing or cross-host ownership makes live progress unknown.")
        if identity_matches:
            report["checks"] = [
                {"name": item["name"], "status": item["status"], "result": item["result"]} for item in sidecar["checks"]
            ]
            if report["status"] == "running":
                report["activeCheck"] = sidecar["activeCheck"]
                elapsed = round((_time(report["observedAt"]) - _time(sidecar["startedAt"])).total_seconds() * 1000)
                report["elapsedMs"] = max(0, elapsed)
                limitations.append("Live elapsed uses UTC clocks and may be affected by clock adjustments.")
                if elapsed < 0:
                    limitations.append("Clock moved before the start time; elapsed was clamped to zero.")
            elif sidecar["status"] == "interrupted":
                report["status"] = "interrupted" if report["status"] != "unknown" else "unknown"
            if report["status"] != "running":
                for item in report["checks"]:
                    if item["status"] in ("running", "pending"):
                        item["status"] = "unknown"
    _stable(run, before)
    return report


def logs(run: Run, *, check_name: str, attempt: int | None = None, tail_bytes: int = 8192) -> dict[str, Any]:
    latest = _counter(run)
    names = [item["name"] for item in run["config"]["checks"]]
    if check_name not in names:
        raise FactoryError("Choose a single frozen configured --check-name.")
    selected = latest if attempt is None else attempt
    if not json_integer(selected) or not 1 <= selected <= latest:
        raise FactoryError("Attempt must be positive and cannot exceed the saved counter.")
    if not json_integer(tail_bytes) or not 1 <= tail_bytes <= 65536:
        raise FactoryError("--tail-bytes must be 1–65536.")
    before = _snapshot(run)
    path = Path(run["dir"]) / f"check-{int(selected)}-{check_name}.log"
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise FactoryError("Selected log is not a regular non-symlink file.")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise FactoryError("Selected log is not a regular file.")
            start = max(0, info.st_size - tail_bytes)
            stream.seek(start)
            content = stream.read(min(tail_bytes, info.st_size - start))
    except FileNotFoundError as error:
        raise FactoryError("Selected check log is missing.") from error
    except OSError as error:
        raise FactoryError(f"Cannot read selected log: {error}.", "infrastructure") from error
    result = None
    if selected == latest:
        record = run.get("verification")
        if (
            not (isinstance(run.get("operation"), dict) and run["operation"].get("kind") == "verify")
            and isinstance(record, dict)
            and _results(record.get("results"), names)
        ):
            result = next((item for item in record["results"] if item["name"] == check_name), None)
        if result is None:
            try:
                sidecar = _sidecar(before[1], run, names)
                if sidecar and sidecar["owner"] == before[2]:
                    result = next(item["result"] for item in sidecar["checks"] if item["name"] == check_name)
            except (ValueError, KeyError, TypeError):
                pass
    else:
        raw = _read(Path(run["dir"]) / f"verification-{int(selected)}.json", optional=True)
        if raw is not None:
            try:
                record = json.loads(raw)
                if isinstance(record, dict) and _results(record.get("results"), names):
                    result = next((item for item in record["results"] if item["name"] == check_name), None)
            except (ValueError, TypeError):
                pass
            if raw != _read(Path(run["dir"]) / f"verification-{int(selected)}.json", optional=True):
                raise FactoryError("Selected attempt receipt changed during lookup.", "snapshot-changed")
    _stable(run, before)
    return {
        "version": 1,
        "id": run["id"],
        "attempt": int(selected),
        "check": check_name,
        "log": str(path),
        "bytesRead": len(content),
        "tailTruncated": start > 0,
        "logTruncated": result.get("truncated") if result and type(result.get("truncated")) is bool else None,
        "encoding": "utf-8 with replacement",
        "content": content.decode("utf-8", "replace"),
    }


def format_progress(report: dict[str, Any]) -> str:
    owner = report["owner"]
    lines = [
        f"Run: {report['id']}    Observation version: {report['version']}",
        f"Verification attempt {report['attempt']}: {report['status']}",
        f"Observed at: {report['observedAt']}",
        f"Owner: {owner['host']} / PID {owner['pid']} / since {owner['at']}" if owner else "Owner: unavailable",
        f"Active check: {report['activeCheck'] or 'none'}    Elapsed ms: {report['elapsedMs']}",
    ]
    for item in report["checks"]:
        lines.append(f"Check {item['name']}: {item['status']}")
        if item["result"] is not None:
            lines.extend(f"  {key}: {value}" for key, value in item["result"].items())
    lines.extend(f"Limit: {item}" for item in report["limitations"])
    return "\n".join(lines)


def format_logs(report: dict[str, Any]) -> str:
    return (
        f"Run: {report['id']}    Observation version: {report['version']}\n"
        f"Attempt {report['attempt']} / {report['check']}: {report['bytesRead']} bytes\n"
        f"Log: {report['log']}\n"
        f"Tail truncated: {report['tailTruncated']}    Writer truncated: {report['logTruncated']}\n"
        f"Encoding: {report['encoding']}\n\n{report['content']}"
    )
