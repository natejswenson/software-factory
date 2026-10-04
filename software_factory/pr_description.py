"""Private, evidence-bound agent prose and deterministic PR receipt rendering."""

import html
import json
import math
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import engine
from .errors import FactoryError
from .store import Run, atomic_json, fingerprint, save
from .validation import json_integer

INPUT_LIMIT = 16 * 1024
BODY_LIMIT = 48 * 1024
ARTIFACT_LIMIT = 128 * 1024
PRESENTATION = "pr-presentation.json"
PREVIEW = "pr-preview.md"
BODY = "pr-body.md"


def _read(path: Path, limit: int, *, optional: bool = False) -> bytes | None:
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise FactoryError(f"Expected a regular non-symlink file: {path.name}.")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise FactoryError(f"Expected a regular file: {path.name}.")
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        current = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino):
            raise FactoryError(f"File changed during capture: {path.name}.", "drift")
        if len(raw) > limit:
            raise FactoryError(f"{path.name} exceeds {limit} bytes; shorten the input, never truncate criteria.")
        return raw
    except FileNotFoundError as error:
        if optional:
            return None
        raise FactoryError(f"Missing required file: {path.name}.") from error
    except OSError as error:
        raise FactoryError(f"Cannot read {path.name}: {error}.", "infrastructure") from error


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in items:
        if key in result:
            raise FactoryError(f"Duplicate JSON key: {key}.")
        result[key] = value
    return result


def _parse(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise FactoryError("Description must be bounded valid UTF-8 JSON.") from error
    stack = [(data, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > 32:
            raise FactoryError("Description JSON nesting exceeds 32 levels.")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise FactoryError("Description JSON numbers must be finite.")
    return validate(data)


def validate(data: Any) -> dict[str, Any]:
    allowed = {"version", "evidence", "title", "summary", "compatibility", "risks"}
    if (
        not isinstance(data, dict)
        or set(data) - allowed
        or not json_integer(data.get("version"))
        or data["version"] != 1
    ):
        raise FactoryError("Description requires version 1 and only the documented keys.")
    title = data.get("title")
    if not isinstance(title, str) or any(unicodedata.category(c) == "Cc" or c in "\u2028\u2029" for c in title):
        raise FactoryError("Title must be a single line without control characters.")
    title = title.strip()
    if not 1 <= len(title) <= 150:
        raise FactoryError("Trimmed title must contain 1–150 characters.")
    summary = data.get("summary")
    if (
        not isinstance(summary, list)
        or not 1 <= len(summary) <= 5
        or any(not isinstance(item, str) or not item.strip() for item in summary)
    ):
        raise FactoryError("Summary requires 1–5 nonempty paragraph strings.")
    if any(key in data and not isinstance(data[key], str) for key in ("compatibility", "risks")):
        raise FactoryError("Compatibility and risks must be strings when supplied.")
    evidence = data.get("evidence")
    required = {"base", "criteria", "config", "plan", "head", "tree", "paths"}
    if not isinstance(evidence, dict) or not required <= set(evidence) or set(evidence) - (required | {"rules"}):
        raise FactoryError("Copy the complete verified evidence object, including paths.")
    if any(not isinstance(evidence.get(key), str) or not evidence[key] for key in set(evidence) - {"paths"}):
        raise FactoryError("Evidence fingerprints must be nonempty strings.")
    if not isinstance(evidence["paths"], list) or any(not isinstance(path, str) for path in evidence["paths"]):
        raise FactoryError("Evidence paths must be strings.")
    result = {**data, "title": title}
    try:
        json.dumps(result, ensure_ascii=False).encode("utf-8")
    except UnicodeError as error:
        raise FactoryError("Description strings must represent valid UTF-8 text.") from error
    return result


def _atomic_text(path: Path, raw: bytes) -> None:
    _read(path, BODY_LIMIT, optional=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _cell(text: str) -> str:
    return html.escape(text).replace("|", "&#124;").replace("\n", "&#10;").replace("\r", "&#13;")


def _command(result: dict[str, Any] | None) -> str:
    argv = result.get("argv") if result else None
    if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv):
        return "Command unavailable in private verification"
    host_path = re.compile(
        r"(?:^|[\s=:,;@\"'(\[])"
        r"(?:-[-A-Za-z0-9]+)?(?:/|[A-Za-z]:[\\/]|\\\\|~/)"
        r"|\bfile:/+",
        flags=re.IGNORECASE,
    )
    portable_url = re.compile(r"https?://[^/\s]+(?:/[^\s]*)?", flags=re.IGNORECASE)
    if any(host_path.search(arg) for arg in argv if not portable_url.fullmatch(arg)):
        return "Command retained in private verification"
    return "<code>" + _cell(json.dumps(argv, ensure_ascii=False)) + "</code>"


def render(run: Run, data: dict[str, Any], *, commit: str | None = None) -> bytes:
    lines = ["## Summary (agent-authored)", "", "\n\n".join(data["summary"])]
    for key in ("compatibility", "risks"):
        if key in data:
            lines.extend(["", f"## {key.capitalize()} (agent-authored)", "", data[key]])
    lines.extend(["", "## Acceptance criteria", ""])
    lines.extend(f"{index}. {item['text']}" for index, item in enumerate(run["criteria"], 1))
    lines.extend(
        [
            "",
            "## Verification (recorded)",
            "",
            "| Check | Command (argv) | Outcome | Duration ms |",
            "| --- | --- | --- | --- |",
        ]
    )
    results = {item["name"]: item for item in run["verification"]["results"]}
    for check in run["config"]["checks"]:
        result = results.get(check["name"])
        outcome = "not-run" if result is None else "passed" if result.get("passed") is True else "failed"
        duration = result.get("durationMs") if result else None
        metric = str(int(duration)) if json_integer(duration) and duration >= 0 else "unavailable"
        lines.append(f"| {_cell(check['name'])} | {_command(result)} | {outcome} | {metric} |")
    lines.extend(["", f"Reviewed tree: {data['evidence']['tree']}"])
    if commit is not None:
        lines.extend(["", f"Reviewed commit: {commit}"])
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    if len(raw) > BODY_LIMIT:
        raise FactoryError(
            f"Custom PR body exceeds {BODY_LIMIT} UTF-8 bytes; shorten prose or revise task criteria before a new run. Criteria are never truncated."
        )
    return raw


def load(run: Run, *, evidence: dict[str, Any] | None = None) -> dict[str, Any] | None:
    reference = run.get("prPresentation")
    if reference is None:
        return None
    if (
        not isinstance(reference, dict)
        or set(reference) != {"file", "hash", "evidenceHash"}
        or reference.get("file") != PRESENTATION
    ):
        raise FactoryError("Invalid saved PR presentation reference.")
    raw = _read(Path(run["dir"]) / PRESENTATION, ARTIFACT_LIMIT)
    if fingerprint(raw) != reference["hash"]:
        raise FactoryError("Selected PR presentation changed; inspect the immutable delivery attempt.", "drift")
    data = _parse(raw)
    if fingerprint(data["evidence"]) != reference["evidenceHash"]:
        raise FactoryError("Saved presentation evidence hash differs.", "drift")
    if evidence is not None and (not engine.same_evidence(data["evidence"], evidence) or data["evidence"] != evidence):
        raise FactoryError(
            "PR presentation evidence is stale; submit current verified evidence before delivery.", "gate"
        )
    return data


def submit(directory: str | Path, file: str | Path) -> dict[str, Any]:
    data = _parse(_read(Path(file), INPUT_LIMIT))
    with engine.transaction(directory) as run:
        engine.active(run)
        if run["phase"] == "preparing" or any(
            run.get(key) is not None for key in ("operation", "commitIntent", "delivery")
        ):
            raise FactoryError("PR metadata requires a prepared run without an operation or delivery intent.", "gate")
        current = engine.check_verified(run)
        if not engine.same_evidence(data["evidence"], current) or data["evidence"] != current:
            raise FactoryError("Description evidence is stale; copy complete current verified evidence.", "gate")
        preview = render(run, data)
        # Check final-body size too, before any write or publication.
        render(run, data, commit=current["head"])
        target, preview_path = Path(run["dir"]) / PRESENTATION, Path(run["dir"]) / PREVIEW
        stored = _read(target, ARTIFACT_LIMIT, optional=True)
        captured = _parse(stored) if stored is not None else None
        reference = run.get("prPresentation")
        if reference is not None and not isinstance(reference, dict):
            raise FactoryError("Invalid saved PR presentation reference.")
        if reference is not None and stored is not None and fingerprint(stored) == reference.get("hash"):
            previous = load(run)
        elif captured == data:
            # An interrupted replacement can leave the new owned payload before
            # its state reference. Explicit resubmission authorizes this payload;
            # delivery still rejects any referenced mismatch without resubmission.
            previous = None
        elif reference is not None:
            raise FactoryError("Saved presentation differs; inspect it before resubmitting.", "drift")
        else:
            previous = None
        old_preview = _read(preview_path, BODY_LIMIT, optional=True)
        changed = previous != data
        if changed:
            atomic_json(target, data)
        if old_preview != preview:
            _atomic_text(preview_path, preview)
        reference = {
            "file": PRESENTATION,
            "hash": fingerprint(_read(target, ARTIFACT_LIMIT)),
            "evidenceHash": fingerprint(current),
        }
        if changed:
            run["prPresentation"] = reference
            save(run, "pr-description-submitted", presentationHash=reference["hash"])
        return {
            "version": 1,
            "id": run["id"],
            "title": data["title"],
            "presentation": str(target),
            "previewFile": str(preview_path),
            "preview": preview.decode("utf-8"),
            "evidenceHash": reference["evidenceHash"],
            "changed": changed,
        }


def selected(run: Run) -> dict[str, Any] | None:
    data = load(run, evidence=run["verification"]["evidence"])
    intent = run.get("commitIntent")
    if intent is not None:
        expected = run["prPresentation"]["hash"] if data is not None else None
        if intent.get("presentationHash") != expected or (data is None and "bodyHash" in intent):
            raise FactoryError("Delivery presentation selection differs from immutable intent.", "drift")
    return data


def body_file(run: Run, data: dict[str, Any], commit: str) -> Path:
    selected(run)
    raw = render(run, data, commit=commit)
    path = Path(run["dir"]) / BODY
    intent = run["commitIntent"]
    if "bodyHash" in intent:
        saved = _read(path, BODY_LIMIT)
        if fingerprint(saved) != intent["bodyHash"] or saved != raw:
            raise FactoryError("Selected PR body changed or differs from the observed commit.", "drift")
    else:
        _atomic_text(path, raw)
        intent["bodyHash"] = fingerprint(raw)
        save(run, "pr-body-selected", bodyHash=intent["bodyHash"])
    return path


def format_preview(result: dict[str, Any]) -> str:
    return f"Title: {result['title']}\n\n{result['preview']}"
