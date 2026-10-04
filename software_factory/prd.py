"""Additive PRD scaffolding from packaged resources on a trusted local filesystem."""

import stat
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from .errors import FactoryError

MANAGED = ("README.md", "_template.md")
NEXT = "Review the scaffold, author a PRD from _template.md, and commit the intended files."


def _mode(path: Path) -> int | None:
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def regular_or_missing(path: Path) -> bool:
    mode = _mode(path)
    if mode is None:
        return False
    if not stat.S_ISREG(mode):
        raise FactoryError(f"prd/{path.name} must be a regular file, not a symlink or another file type.")
    return True


def validate_paths(root: Path) -> None:
    directory = root / "prd"
    mode = _mode(directory)
    if mode is not None and not stat.S_ISDIR(mode):
        raise FactoryError("prd must be a real directory, not a symlink or another file type.")
    for name in MANAGED:
        regular_or_missing(directory / name)


def partial_message(error: Exception, created: list[str], skipped: list[str]) -> str:
    return (
        f"PRD setup failed: {error}. Created paths (may be incomplete): {sorted(created)}; "
        f"preserved paths: {sorted(skipped)}. No rollback occurred. Inspect/repair incomplete content; "
        "prd-init only fills missing files and preserves existing regular files."
    )


@dataclass(frozen=True)
class Scaffold:
    root: Path
    contents: tuple[tuple[str, str], ...]


def prepare(root: Path) -> Scaffold:
    """Read every resource and validate every destination before any writes."""
    try:
        resources = files("software_factory").joinpath("templates", "prd")
        contents = tuple((name, resources.joinpath(name).read_text(encoding="utf-8")) for name in MANAGED)
        validate_paths(root)
    except (OSError, UnicodeError) as error:
        raise FactoryError(f"Cannot preflight PRD scaffold: {error}. No files created.", "infrastructure") from error
    return Scaffold(root, contents)


def create(scaffold: Scaffold, *, prior_created: list[str] | None = None) -> dict[str, Any]:
    """Exclusive writes preserve customized files; failures retain truthful partial paths."""
    root = scaffold.root
    created: list[str] = []
    skipped: list[str] = []
    try:
        validate_paths(root)
        (root / "prd").mkdir(exist_ok=True)
        for name, content in scaffold.contents:
            validate_paths(root)
            path = root / "prd" / name
            relative = f"prd/{name}"
            if regular_or_missing(path):
                skipped.append(relative)
                continue
            try:
                stream = path.open("x", encoding="utf-8")
            except FileExistsError:
                validate_paths(root)
                if not regular_or_missing(path):
                    raise OSError(f"{relative} disappeared during exclusive creation")
                skipped.append(relative)
                continue
            created.append(relative)  # Open created it, even if the following write/close fails.
            with stream:
                stream.write(content)
    except (OSError, FactoryError) as error:
        code = error.code if isinstance(error, FactoryError) else "infrastructure"
        raise FactoryError(partial_message(error, [*(prior_created or []), *created], skipped), code) from error
    return {
        "repo": str(root),
        "prd": str(root / "prd"),
        "created": sorted(created),
        "skipped": sorted(skipped),
        "next": NEXT,
    }
