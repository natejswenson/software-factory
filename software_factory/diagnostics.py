"""Explain saved proof versus current files; gate decisions stay in the engine."""

import json
import os
import re
import socket
import stat
from pathlib import Path
from typing import Any

from . import engine
from .errors import FactoryError
from .git import git
from .store import Run, read_json
from .validation import json_integer

LIMITATIONS = [
    "Observations do not reserve files or authorize delivery; follow the engine next action.",
    "Ignored dependencies and host services are not fingerprinted.",
    "Rules per-file detail is initial versus current, not the contents at the last review.",
    "Completed delivery is historical recorded evidence, not a fresh remote observation.",
]


def inspect_owner(directory: str | Path) -> dict[str, Any] | None:
    """Observe ownership without acquiring, recovering, or probing process identity."""
    lock = Path(directory) / "lock"
    try:
        mode = lock.lstat().st_mode
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(mode):
        raise FactoryError("Operation lock is not a regular directory.", "ownership")
    path = lock / "owner.json"
    try:
        if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 131072:
            raise FactoryError("Operation owner receipt is unsafe.", "ownership")
        owner = read_json(path)
    except (OSError, ValueError) as error:
        raise FactoryError("Operation owner receipt is unavailable or malformed.", "ownership") from error
    if (
        not isinstance(owner, dict)
        or not json_integer(owner.get("pid"))
        or owner["pid"] <= 0
        or not isinstance(owner.get("host"), str)
        or not isinstance(owner.get("at"), str)
        or set(owner) != {"pid", "host", "at"}
    ):
        raise FactoryError("Operation owner receipt is malformed.", "ownership")
    return owner


def _gate(
    record: Any, field: str, current: dict[str, Any] | None, keys: tuple[str, ...], predicate, historical_key: str
) -> dict[str, Any]:
    result = {"status": "missing", "reasons": ["No saved proof."], "differences": [], historical_key: None}
    if record is None:
        return result
    if not isinstance(record, dict):
        result.update(status="unknown", reasons=["Saved proof is malformed."])
        return result
    # Verification has a passed bool; reviews have a verdict. Both retain historical facts.
    value = record.get(historical_key)
    result[historical_key] = value
    valid = type(value) is bool if historical_key == "passed" else value in ("pass", "fail")
    saved = record.get(field)
    if (
        not valid
        or not isinstance(saved, dict)
        or any(key not in saved for key in keys if key != "rules")
        or any(
            value is not None and not isinstance(value, str)
            for key, value in saved.items()
            if key in engine.EVIDENCE_KEYS
        )
    ):
        result.update(status="unknown", reasons=["Saved proof verdict or fingerprint is malformed."])
        return result
    failed = value is False or value == "fail"
    result.update(status="failed" if failed else "unknown", reasons=["Saved proof failed."] if failed else [])
    if current is None:
        result["reasons"].append("Current fingerprint is unavailable; historical result is not current proof.")
        return result
    result["differences"] = [
        {"key": key, "recorded": saved.get(key), "current": current.get(key)}
        for key in keys
        if saved.get(key) != current.get(key)
    ]
    matches = predicate(saved, current)
    if not failed:
        result["status"] = "current" if matches else "stale"
        result["reasons"].append(
            "Saved proof matches current fingerprint." if matches else "Saved fingerprint differs from current inputs."
        )
    elif not matches:
        result["reasons"].append("Inputs also differ from the failed proof.")
    return result


def explain(run: Run) -> dict[str, Any]:
    report: dict[str, Any] = {
        "version": 1,
        "id": run["id"],
        "phase": run["phase"],
        "next": None,
        "gates": {},
        "changedPaths": {
            "baseline": None,
            "paths": [],
            "available": False,
            "recordedHead": None,
            "recordedTree": None,
            "currentHead": None,
            "currentTree": None,
        },
        "deliveryRecoveryAllowed": None,
        "delivery": run.get("delivery"),
        "rulesDetail": {"baseline": "initial", "initialPaths": None, "currentPaths": None},
        "limitations": list(LIMITATIONS),
        "errors": [],
    }

    def error(code, message):
        report["errors"].append({"code": code, "message": message})

    current = ctx = None
    state_path = Path(run["dir"]) / "state.json"
    try:
        before_state = state_path.read_bytes()
        if json.loads(before_state) != run:
            raise FactoryError("Saved run changed before diagnostic capture.", "snapshot-changed")
        owner = inspect_owner(run["dir"])
        if owner and (owner["pid"] != os.getpid() or owner["host"] != socket.gethostname()):
            report["next"] = {"action": "wait", "owner": owner}
            error("locked", "Another operation owns the run; current comparisons were not inspected.")
        else:
            # Terminal next actions are available without current files; they stay historical.
            if run["phase"] in ("done", "blocked", "preparing") or run.get("renameIntent"):
                report["next"] = engine.next_action(run)
            first = engine.evidence(run)
            report["next"] = engine.next_action(run)
            recovery = engine.own_delivery_commit(run, first)
            current_rules = engine.task_rules(run)
            second = engine.evidence(run)
            after_owner = inspect_owner(run["dir"])
            if first != second or owner != after_owner or before_state != state_path.read_bytes():
                report["next"] = None
                raise FactoryError("Inputs or operation ownership changed during inspection.", "snapshot-changed")
            current = first
            ctx = {key: current[key] for key in ("base", "criteria", "config", "plan", "rules") if key in current}
            report["deliveryRecoveryAllowed"] = recovery
            report["rulesDetail"]["currentPaths"] = (
                [file["path"] for file in current_rules["files"]] if current_rules["enabled"] else None
            )
    except (FactoryError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        if run["phase"] not in ("done", "blocked", "preparing") and not run.get("renameIntent"):
            report["next"] = None
        error(exc.code if isinstance(exc, FactoryError) else "inspection", str(exc))
    initial = run["rules"].get("initial") if isinstance(run.get("rules"), dict) else None
    if isinstance(initial, dict) and isinstance(initial.get("files"), list):
        report["rulesDetail"]["initialPaths"] = [
            item.get("path") for item in initial["files"] if isinstance(item, dict)
        ]
    plan_record = run.get("planReview")
    plan_keys = (
        tuple(ctx)
        if ctx is not None
        else ("base", "criteria", "config", "plan", *(("rules",) if run.get("rules") else ()))
    )
    # plan_current compares the whole context. Include extra saved keys in differences as well.
    if isinstance(plan_record, dict) and isinstance(plan_record.get("context"), dict):
        plan_keys = tuple(dict.fromkeys((*plan_keys, *plan_record["context"])))
    report["gates"]["planReview"] = _gate(
        plan_record,
        "context",
        ctx,
        plan_keys,
        lambda saved, now: engine.plan_current({**run, "planReview": {"verdict": "pass", "context": saved}}, now),
        "verdict",
    )
    for name in ("verification", "codeReview"):
        report["gates"][name] = _gate(
            run.get(name),
            "evidence",
            current,
            engine.EVIDENCE_KEYS,
            engine.same_evidence,
            "passed" if name == "verification" else "verdict",
        )
    for name, gate in report["gates"].items():
        if gate["status"] == "unknown" and any("malformed" in reason for reason in gate["reasons"]):
            error("malformed-proof", f"{name}: saved proof could not be compared.")
    for name in ("verification", "codeReview"):
        record = run.get(name)
        saved = record.get("evidence") if isinstance(record, dict) else None
        if isinstance(saved, dict) and isinstance(saved.get("tree"), str) and saved["tree"]:
            changes = report["changedPaths"]
            changes.update(baseline=name, recordedHead=saved.get("head"), recordedTree=saved["tree"])
            if current is not None:
                changes.update(currentHead=current["head"], currentTree=current["tree"])
                try:
                    if not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", saved["tree"]):
                        raise FactoryError("Saved baseline tree is not a Git object ID.", "malformed-proof")
                    changes["paths"] = sorted(
                        p
                        for p in git(
                            run["worktree"],
                            [
                                "diff",
                                "--no-ext-diff",
                                "--no-renames",
                                "--name-only",
                                "-z",
                                saved["tree"],
                                current["tree"],
                                "--",
                            ],
                        ).split("\0")
                        if p
                    )
                    changes["available"] = True
                except (FactoryError, OSError, ValueError) as exc:
                    changes.update(paths=[], available=False)
                    error(exc.code if isinstance(exc, FactoryError) else "inspection", str(exc))
                # A failed consistency read is unavailable, never a fresh claim.
                try:
                    if (
                        engine.evidence(run) != current
                        or inspect_owner(run["dir"]) != owner
                        or state_path.read_bytes() != before_state
                    ):
                        raise FactoryError("Inputs changed during changed-path inspection.", "snapshot-changed")
                except (FactoryError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                    error("snapshot-changed", f"Current comparison no longer available: {exc}")
                    report["next"] = None
                    report["deliveryRecoveryAllowed"] = None
                    report["rulesDetail"]["currentPaths"] = None
                    changes.update(paths=[], available=False, currentHead=None, currentTree=None)
                    for gate in report["gates"].values():
                        if gate["status"] in ("current", "stale"):
                            gate["status"] = "unknown"
                        gate["differences"] = []
                        gate["reasons"].append("Snapshot changed; current comparison unavailable.")
            break
    return report


def exit_code(report: dict[str, Any]) -> int:
    if report["phase"] == "blocked":
        return 2
    return 3 if report["errors"] else 0


def format_report(report: dict[str, Any]) -> str:
    lines = [f"Task {report['id']} — {report['phase']}"]
    for name, gate in report["gates"].items():
        lines.append(f"{name}: {gate['status']}")
        lines.extend("  " + reason for reason in gate["reasons"])
        lines.extend(f"  {diff['key']}: {diff['recorded']} → {diff['current']}" for diff in gate["differences"])
    changes = report["changedPaths"]
    lines.append(
        f"Changed since {changes['baseline'] or 'no saved proof'}: {'available' if changes['available'] else 'unavailable'}"
    )
    lines.extend("  " + path for path in changes["paths"])
    lines.append("Next: " + (report["next"]["action"] if report["next"] else "unavailable"))
    if report["deliveryRecoveryAllowed"]:
        lines.append("Engine-owned delivery commit recovery is allowed; HEAD differs from the proof.")
    lines.extend(f"Error {item['code']}: {item['message']}" for item in report["errors"])
    lines.extend("Limit: " + item for item in report["limitations"])
    return "\n".join(lines)
