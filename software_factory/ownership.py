"""Observe private operation ownership without taking its lock."""

import stat
from pathlib import Path
from typing import Any

from .errors import FactoryError
from .store import read_json
from .validation import json_integer


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
