"""Compare actual wheel/sdist resource bytes with the canonical authored sources."""

import argparse
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = {f"software_factory/skills/software-factory/{name}": f"skills/software-factory/{name}"
         for name in ("SKILL.md", "protocol.md")}
TEMPLATES = {f"software_factory/templates/prd/{name}": f"software_factory/templates/prd/{name}"
             for name in ("README.md", "_template.md")}
SDIST_REQUIRED = ("scripts/build_resources.py", "scripts/factory.py", "pyproject.toml", "MANIFEST.in",
                  ".codex-plugin/plugin.json", ".agents/plugins/marketplace.json",
                  ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json")


def check(archives: list[Path], root: Path = ROOT) -> None:
    if not archives or not any(p.suffix == ".whl" for p in archives) or not any(p.name.endswith(".tar.gz") for p in archives):
        raise ValueError("Provide an actual wheel and source archive")
    for path in archives:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as wheel:
                for member, source in (SKILL | TEMPLATES).items():
                    if wheel.read(member) != (root / source).read_bytes():
                        raise ValueError(f"Wheel resource differs: {path.name}: {member}")
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path) as archive:
                names = archive.getnames()
                prefix = names[0].split("/")[0]
                for source in (*SKILL.values(), *TEMPLATES, *SDIST_REQUIRED):
                    stream = archive.extractfile(f"{prefix}/{source}")
                    if stream is None or stream.read() != (root / source).read_bytes():
                        raise ValueError(f"Source archive resource differs: {path.name}: {source}")
                if any(name.startswith(f"{prefix}/software_factory/skills/") for name in names):
                    raise ValueError("Source archive contains a second authored skill tree")
        else:
            raise ValueError(f"Unsupported distribution: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path, nargs="+")
    args = parser.parse_args()
    check(args.archives)
    print("Distribution resource bytes match canonical sources.")
