"""Executable repository checks, shared by local development and factory runs."""

import argparse
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project() -> int:
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    if suite.countTestCases() == 0:
        raise RuntimeError("No tests discovered.")
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def check_source() -> int:
    if (ROOT / "package.json").exists() or any(ROOT.glob("**/*.mjs")):
        raise RuntimeError("Node source or packaging remains in this Python repository.")
    paths = sorted(
        path for folder in ("software_factory", "scripts", "tests") for path in (ROOT / folder).rglob("*.py")
    )
    if not paths:
        raise RuntimeError("No Python sources discovered.")
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"{len(paths)} Python source files parse.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=("tests", "source"))
    args = parser.parse_args()
    return test_project() if args.check == "tests" else check_source()


if __name__ == "__main__":
    sys.exit(main())
