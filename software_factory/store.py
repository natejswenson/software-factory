"""Private, atomic run storage and version-1 compatible fingerprints."""

import hashlib
import json
import math
import os
import re
import shutil
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from .errors import FactoryError
from .validation import json_integer

Run = dict[str, Any]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _string(value: str) -> str:
    # JSON.stringify escapes lone surrogates, but emits valid pairs as UTF-8.
    value = value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "".join(f"\\u{ord(c):04x}" if 0xD800 <= ord(c) <= 0xDFFF else c for c in encoded)


def _number(value: int | float) -> str:
    # v1 used JavaScript numbers, including IEEE-754 rounding of JSON integers.
    number = float(value)
    if not math.isfinite(number):
        return "null"
    if number == 0:
        return "0"
    decimal = Decimal(repr(number))
    if 1e-6 <= abs(number) < 1e21:
        return format(decimal, "f").rstrip("0").rstrip(".") if "." in format(decimal, "f") else format(decimal, "f")
    mantissa, exponent = format(decimal.normalize(), "e").split("e")
    return f"{mantissa}e{int(exponent):+d}"


def canonical_json(value: Any) -> str:
    """Match v1's JSON.stringify(stable(value)), rather than Python key ordering."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Fingerprint object keys must be strings.")
        ordered = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        indices = [
            key for key in ordered if len(key) <= 10 and re.fullmatch(r"0|[1-9][0-9]*", key) and int(key) < 2**32 - 1
        ]
        keys = sorted(indices, key=int) + [key for key in ordered if key not in indices]
        return "{" + ",".join(_string(key) + ":" + canonical_json(value[key]) for key in keys) + "}"
    raise TypeError(f"Unsupported fingerprint value: {type(value).__name__}")


def fingerprint(value: Any) -> str:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace").encode("utf-8")
    else:
        raw = canonical_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with open(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def runs_root(common: str | Path) -> Path:
    return Path(common) / "factory" / "runs"


def read_run(directory: str | Path) -> Run:
    run = read_json(Path(directory) / "state.json")
    if (
        not isinstance(run, dict)
        or not json_integer(run.get("version"))
        or run["version"] != 1
        or run.get("dir") != str(directory)
    ):
        raise FactoryError("Invalid run directory.")
    return run


def save(run: Run, action: str, **details: Any) -> None:
    run["updatedAt"] = now()
    run["history"].append({"at": run["updatedAt"], "action": action, **details})
    atomic_json(Path(run["dir"]) / "state.json", run)


def list_runs(common: str | Path) -> list[Run]:
    root = runs_root(common)
    if not root.exists():
        return []
    return [read_run(path) for path in sorted(root.iterdir()) if re.fullmatch(r"[a-f0-9-]{36}", path.name)]


@contextmanager
def locked(directory: str | Path) -> Iterator[None]:
    lock = Path(directory) / "lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as error:
        raise FactoryError(
            "An operation owns this run. Use status; recover only after its process exits.", "locked"
        ) from error
    try:
        atomic_json(lock / "owner.json", {"pid": os.getpid(), "host": socket.gethostname(), "at": now()})
        yield
    finally:
        shutil.rmtree(lock)


def recover_lock(directory: str | Path) -> dict[str, Any]:
    lock = Path(directory) / "lock"
    if not lock.exists():
        return {"recovered": False}
    if not (lock / "owner.json").exists():
        raise FactoryError("Lock has no owner receipt. Inspect it manually; automatic takeover refused.")
    owner = read_json(lock / "owner.json")
    if owner.get("host") != socket.gethostname():
        raise FactoryError("Lock belongs to another host.")
    pid = owner.get("pid")
    if not json_integer(pid) or pid <= 0:
        raise FactoryError("Lock has an invalid owner PID.")
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        shutil.rmtree(lock)
        return {"recovered": True, "owner": owner}
    raise FactoryError("Lock owner is still alive.")
