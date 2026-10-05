"""Resolve skill resources from the executing package, independent of CWD/PATH."""

from pathlib import Path

from .errors import FactoryError


def required(path: Path, root: Path, *, directory: bool = False) -> Path:
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink():
            raise FactoryError(f"Unsafe factory resource (symlink): {path}", "resources")
    if not path.resolve().is_relative_to(root) or not (path.is_dir() if directory else path.is_file()):
        raise FactoryError(f"Missing or unsafe factory resource: {path}", "resources")
    return path


def skill_path(package: Path | None = None) -> Path:
    package = (package or Path(__file__).parent).resolve()
    source = package.parent
    # This owned launcher plus manifest identify a source/plugin distribution.
    # Never silently use wheel copies when a marked source tree is incomplete.
    if (source / ".codex-plugin").exists() or (source / "scripts/factory.py").exists():
        required(source / ".codex-plugin/plugin.json", source)
        required(source / "scripts/factory.py", source)
        skill = source / "skills/software-factory"
        root = source
    else:
        skill = package / "skills/software-factory"
        root = package
    required(skill, root, directory=True)
    for name in ("SKILL.md", "protocol.md"):
        required(skill / name, root)
    return skill


def plugin_resources(root: Path) -> None:
    root = root.resolve()
    required(root / "software_factory", root, directory=True)
    for relative in ("software_factory/__init__.py", "software_factory/cli.py",
                     "software_factory/templates/prd/README.md", "software_factory/templates/prd/_template.md"):
        required(root / relative, root)
    if skill_path(root / "software_factory") != root / "skills/software-factory":
        raise FactoryError(f"Missing plugin source layout: {root}", "resources")
