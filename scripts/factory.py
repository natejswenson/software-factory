"""Run the engine in this loaded plugin; never consult a global factory command."""

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        package = ROOT / "software_factory"
        if package.is_symlink() or not (package / "__init__.py").is_file():
            raise ValueError(f"Missing or unsafe plugin engine: {package}")
        # Reject package file aliases before executing their import side effects.
        for module in package.glob("*.py"):
            if module.is_symlink():
                raise ValueError(f"Unsafe plugin engine module: {module}")
        sys.path.insert(0, str(ROOT))
        import software_factory

        if Path(software_factory.__file__).resolve() != package / "__init__.py":
            raise ValueError("Loaded factory package does not belong to this plugin")
        from software_factory.resources import plugin_resources

        plugin_resources(ROOT)
        from software_factory import cli

        if Path(cli.__file__).resolve() != package / "cli.py":
            raise ValueError("Loaded factory CLI does not belong to this plugin")
    except Exception as error:
        message = f"Plugin setup failed: {error}. Restore/reinstall this plugin's complete source."
    else:
        return cli.main()
    if "--json" in sys.argv[1:]:
        print(json.dumps({"error": message, "code": "resources"}), file=sys.stderr)
    else:
        print(message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
