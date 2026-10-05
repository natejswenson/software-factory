"""Generate the Claude adapter from the authoritative Codex plugin metadata."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = {"name", "description", "author", "license", "homepage", "repository"}


def regular(root: Path, relative: str, directory: bool = False) -> Path:
    path = root / relative
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink():
            raise ValueError(f"Owned path must not be a symlink: {relative}")
    if not path.resolve().is_relative_to(root.resolve()) or not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"Missing or unsafe owned path: {relative}")
    return path


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read(root: Path, relative: str) -> dict:
    value = json.loads(regular(root, relative).read_text(encoding="utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {relative}")
    return value


def text_fields(value: dict, names: set[str], label: str) -> None:
    if set(value) != names or any(not isinstance(value[key], str) or not value[key].strip() for key in names):
        raise ValueError(f"Invalid {label} fields; expected nonempty strings: {sorted(names)}")


def generated(root: Path) -> dict[str, bytes]:
    manifest = read(root, ".codex-plugin/plugin.json")
    if set(manifest) != SHARED | {"skills", "interface"}:
        raise ValueError("Unsupported or missing Codex fields; capabilities need an explicit Claude adapter. Version is Git-derived.")
    text_fields({key: manifest[key] for key in SHARED - {"author"}}, SHARED - {"author"}, "plugin")
    if not isinstance(manifest["author"], dict):
        raise ValueError("Invalid author object")
    text_fields(manifest["author"], {"name"}, "author")
    if manifest["name"] != "software-factory" or manifest["skills"] != "./skills/":
        raise ValueError("Expected the software-factory plugin with ./skills/ at its root")
    interface = manifest["interface"]
    if not isinstance(interface, dict) or set(interface) != {"displayName", "shortDescription", "defaultPrompt"}:
        raise ValueError("Unsupported Codex interface fields")
    text_fields({key: interface[key] for key in ("displayName", "shortDescription")}, {"displayName", "shortDescription"}, "interface")
    prompts = interface["defaultPrompt"]
    if not isinstance(prompts, list) or not prompts or any(not isinstance(p, str) or not p.strip() for p in prompts):
        raise ValueError("defaultPrompt must contain nonempty strings")
    regular(root, "skills", directory=True)
    for name in ("SKILL.md", "protocol.md"):
        regular(root, f"skills/software-factory/{name}")
    catalog = read(root, ".agents/plugins/marketplace.json")
    expected = {
        "name": "software-factory",
        "plugins": [{"name": "software-factory", "source": {"source": "local", "path": "./"},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"}],
    }
    if catalog != expected:
        raise ValueError("Codex catalog must expose exactly one software-factory plugin at ./ with its reviewed policy")
    adapter = {key: manifest[key] for key in manifest if key in SHARED}
    marketplace = {"name": catalog["name"], "owner": manifest["author"],
                   "metadata": {"description": manifest["description"]},
                   "plugins": [{"name": manifest["name"], "source": "./", "description": manifest["description"]}]}
    return {f".claude-plugin/{name}.json": (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
            for name, value in (("plugin", adapter), ("marketplace", marketplace))}


def sync(root: Path = ROOT, *, check: bool = False) -> None:
    outputs = generated(root)
    directory = root / ".claude-plugin"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError("Unsafe Claude adapter directory")
    for relative, content in outputs.items():
        path = root / relative
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"Unsafe generated file: {relative}")
        if check:
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError(f"Generated metadata drift: {relative}; run python3 scripts/plugin_metadata.py")
        else:
            directory.mkdir(exist_ok=True)
            path.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        sync(check=args.check)
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
    print("Plugin metadata matches." if args.check else "Claude plugin metadata generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
