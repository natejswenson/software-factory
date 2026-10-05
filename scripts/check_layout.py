"""Check owned source layout without traversing generated data or following links."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNED = {"skills", "software_factory", "scripts", "tests", "docs", "prd", "design", "plugins",
         ".codex-plugin", ".claude-plugin", ".agents"}
GENERATED = {"__pycache__", ".venv", "build", "dist", ".git", ".factory-worktrees"}
RETIRED = {"docs/README.md", "docs/history/README.md", "docs/plans/README.md"}


def check(root: Path = ROOT) -> None:
    root = root.resolve()
    inventory = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root,
                               capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    files = {name for name in inventory if name and name.split("/")[0] in OWNED
             and ((root / name).exists() or (root / name).is_symlink())}
    for name in sorted(files):
        path = root / name
        if path.is_symlink():
            raise ValueError(f"Source alias/link is not allowed: {name}")
        if path.name == ".gitkeep" or name in RETIRED:
            raise ValueError(f"Placeholder or redundant index: {name}")
        if name.startswith(("plugins/", "skills/software-factory/skills/", "software_factory/skills/")):
            raise ValueError(f"Duplicate or nested plugin source: {name}")
        if path.name in {"SKILL.md", "protocol.md"} and name != f"skills/software-factory/{path.name}":
            raise ValueError(f"Duplicate authored skill resource: {name}")
    for folder in sorted(OWNED):
        start = root / folder
        if start.is_symlink():
            raise ValueError(f"Source directory alias: {folder}")
        if not start.exists() and not start.is_symlink():
            continue
        for directory, children, names in os.walk(start, followlinks=False):
            path = Path(directory)
            if path.is_symlink():
                raise ValueError(f"Source directory alias: {path.relative_to(root)}")
            visible = []
            for child in children:
                candidate = path / child
                if child in GENERATED or child.endswith(".egg-info"):
                    continue
                ignored = subprocess.run(["git", "check-ignore", "-q", str(candidate.relative_to(root))], cwd=root)
                if ignored.returncode == 0:
                    continue
                if candidate.is_symlink():
                    raise ValueError(f"Source directory alias: {candidate.relative_to(root)}")
                visible.append(child)
            children[:] = visible
            if not children and not names:
                raise ValueError(f"Empty source directory: {path.relative_to(root)}")
    for name in ("SKILL.md", "protocol.md"):
        path = root / f"skills/software-factory/{name}"
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing regular canonical skill: {path.relative_to(root)}")


if __name__ == "__main__":
    try:
        check()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
    print("Plugin source layout matches.")
