#!/usr/bin/env python3
"""Run real project checks during the transition from Node to Python.

The migration keeps these argv commands frozen in its factory run. This bridge
checks the existing implementation until the Python implementation replaces it.
"""

import argparse
import ast
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def test_project() -> int:
    """Require and execute the suite for each implementation present."""
    suites = 0
    legacy = sorted((ROOT / "test").glob("*.test.mjs"))
    if legacy:
        suites += 1
        result = subprocess.run(["node", "--test", *map(str, legacy)], cwd=ROOT)
        if result.returncode:
            return result.returncode
    if (ROOT / "tests").is_dir():
        sys.path.insert(0, str(ROOT))
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        if not suite.countTestCases():
            print("Python test discovery returned zero tests.", file=sys.stderr)
            return 2
        suites += 1
        if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
            return 1
    if not suites:
        print("No executable project tests found.", file=sys.stderr)
        return 2
    return 0


def check_source() -> int:
    """Parse source without creating bytecode or changing the working tree."""
    sources = []
    for folder in ("bin", "lib", "scripts", "test", "tests", "software_factory"):
        path = ROOT / folder
        for source in sorted(path.rglob("*.py")):
            ast.parse(source.read_bytes(), filename=str(source))
            sources.append(source)
        for source in sorted(path.glob("*.mjs")):
            result = subprocess.run(["node", "--check", str(source)], cwd=ROOT)
            if result.returncode:
                return result.returncode
            sources.append(source)
    if not sources:
        print("No project source found.", file=sys.stderr)
        return 2
    print(f"All {len(sources)} source files parse.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=("tests", "source"))
    args = parser.parse_args()
    return test_project() if args.check == "tests" else check_source()


if __name__ == "__main__":
    sys.exit(main())
