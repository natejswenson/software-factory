"""Bounded Markdown instructions and explicit JSON configuration fences."""

import json
import re
import stat
from pathlib import Path
from typing import Any

from .checks import validate_config
from .errors import FactoryError
from .git import git, git_bytes
from .store import fingerprint

MAX_FILE = 128 * 1024
MAX_TOTAL = 1024 * 1024
MAX_FILES = 128


def _stat(path: Path) -> Any:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _regular(path: Path) -> Any:
    info = _stat(path)
    if info and not stat.S_ISREG(info.st_mode):
        raise FactoryError(f"{path}: expected a regular file, not a symlink or directory.")
    if info and info.st_size > MAX_FILE:
        raise FactoryError(f"{path}: exceeds 128 KiB.")
    return info


def _decode(raw: bytes, path: str) -> str:
    if len(raw) > MAX_FILE:
        raise FactoryError(f"{path}: exceeds 128 KiB.")
    try:
        # TextDecoder strips a UTF-8 BOM in the v1 rules protocol.
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise FactoryError(f"{path}: expected valid UTF-8.") from error


def _bundle(entries: list[tuple[str, bytes]]) -> dict[str, Any]:
    if len(entries) > MAX_FILES or sum(len(raw) for _, raw in entries) > MAX_TOTAL:
        raise FactoryError("Rules exceed 128 files or 1 MiB total.")
    files = [
        {"path": path, "content": _decode(raw, path), "hash": fingerprint(raw)}
        for path, raw in sorted(entries, key=lambda entry: entry[0].encode("utf-16-be", "surrogatepass"))
    ]
    return {"files": files, "hash": fingerprint(files)}


def read_rules(root: str | Path) -> dict[str, Any]:
    directory = Path(root) / ".rules"
    info = _stat(directory)
    if info is None:
        return _bundle([])
    if not stat.S_ISDIR(info.st_mode):
        raise FactoryError(".rules must be a directory, not a symlink.")
    paths = sorted(path for path in directory.iterdir() if path.name.endswith(".md"))
    if len(paths) > MAX_FILES:
        raise FactoryError("Rules exceed 128 files.")
    entries = []
    total = 0
    for path in paths:
        info = _regular(path)
        if info is None:
            raise FactoryError(f"{path}: rule disappeared during discovery.")
        total += info.st_size
        if total > MAX_TOTAL:
            raise FactoryError("Rules exceed 1 MiB total.")
        entries.append((f".rules/{path.name}", path.read_bytes()))
    return _bundle(entries)


def parse_config(raw: str, path: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise FactoryError(f"{path}: duplicate JSON key {key}.")
            result[key] = value
        return result

    def depth(value: Any, level: int = 0) -> None:
        if level > 64:
            raise FactoryError(f"{path}: configuration nesting exceeds 64 levels.")
        children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
        for child in children:
            depth(child, level + 1)

    def invalid_constant(value: str) -> None:
        raise ValueError(f"Invalid JSON constant {value}")

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
        depth(value)
        return value
    except (ValueError, RecursionError) as error:
        raise FactoryError(f"{path}: invalid factory configuration JSON: {error}") from error


def settings(rules: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    owners: dict[str, str] = {}
    for file in rules["files"]:
        fence = None
        lines: list[str] = []
        for line in re.split(r"\r?\n", file["content"]):
            if fence:
                close = re.fullmatch(r" {0,3}(`{3,}|~{3,})\s*", line)
                if close and close[1][0] == fence[0] and len(close[1]) >= fence[1]:
                    if fence[2]:
                        block = parse_config("\n".join(lines), file["path"])
                        if not isinstance(block, dict):
                            raise FactoryError(f"{file['path']}: factory-config must be a JSON object.")
                        for key, value in block.items():
                            if key not in ("version", "endpoint", "checks"):
                                raise FactoryError(f"{file['path']}: unknown factory setting {key}.")
                            if key in owners:
                                raise FactoryError(
                                    f"{file['path']}: duplicate factory setting {key}, already set in {owners[key]}."
                                )
                            owners[key] = file["path"]
                            result[key] = value
                    fence, lines = None, []
                elif fence[2]:
                    lines.append(line)
            else:
                opening = re.fullmatch(r" {0,3}(`{3,}|~{3,})(.*)", line)
                if opening and not (opening[1][0] == "`" and "`" in opening[2]):
                    fence = (opening[1][0], len(opening[1]), opening[2].strip() == "factory-config")
        if fence and fence[2]:
            raise FactoryError(f"{file['path']}: unterminated factory-config fence.")
    return result


def configuration(rules: dict[str, Any], legacy: dict[str, Any] | None = None) -> dict[str, Any]:
    return validate_config({"version": 1, "endpoint": "draft-pr", **(legacy or {}), **settings(rules)})


def read_project(root: str | Path) -> dict[str, Any]:
    path = Path(root) / ".factory.json"
    raw = _decode(path.read_bytes(), ".factory.json") if _regular(path) else None
    legacy = parse_config(raw, ".factory.json") if raw is not None else None
    if raw is not None and not isinstance(legacy, dict):
        raise FactoryError(".factory.json must be a JSON object.")
    if legacy is not None:
        validate_config(legacy)
    rules = read_rules(root)
    return {"rules": rules, "legacy": legacy, "legacyRaw": raw, "config": configuration(rules, legacy)}


def _tree_entries(raw: str) -> list[dict[str, str]]:
    entries = []
    for line in raw.split("\0"):
        if line:
            header, path = line.split("\t", 1)
            mode, _, oid = header.split(" ")
            entries.append({"mode": mode, "oid": oid, "path": path})
    return entries


def assert_committed(root: str | Path, base: str, project: dict[str, Any]) -> None:
    entries = []
    for entry in _tree_entries(git(root, ["ls-tree", "-z", base, "--", ".rules", ".factory.json"])):
        if entry["path"] == ".rules":
            if entry["mode"] != "040000":
                raise FactoryError(".rules on the selected base must be a directory, not a symlink.")
            for child in _tree_entries(git(root, ["ls-tree", "-z", entry["oid"]])):
                if child["path"].endswith(".md"):
                    entries.append({**child, "path": f".rules/{child['path']}"})
        else:
            entries.append(entry)
    rules = []
    legacy_raw = None
    total = 0
    if sum(entry["path"].startswith(".rules/") for entry in entries) > MAX_FILES:
        raise FactoryError("Committed rules exceed 128 files.")
    for entry in entries:
        if entry["mode"] not in ("100644", "100755"):
            raise FactoryError(f"{entry['path']}: committed configuration must be a regular file.")
        size = int(git(root, ["cat-file", "-s", entry["oid"]]).strip())
        if size > MAX_FILE:
            raise FactoryError(f"{entry['path']}: exceeds 128 KiB.")
        if entry["path"].startswith(".rules/"):
            total += size
        if total > MAX_TOTAL:
            raise FactoryError("Committed rules exceed 1 MiB total.")
        raw = git_bytes(root, ["cat-file", "blob", entry["oid"]])
        if entry["path"] == ".factory.json":
            legacy_raw = _decode(raw, entry["path"])
        else:
            rules.append((entry["path"], raw))
    if legacy_raw != project["legacyRaw"] or _bundle(rules)["hash"] != project["rules"]["hash"]:
        raise FactoryError(
            "Configuration and .rules/*.md must be committed on the selected base. Review and commit them first."
        )
