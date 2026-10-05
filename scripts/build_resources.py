"""Standard setuptools build_py adapter for the one authored skill directory."""

from pathlib import Path

from setuptools.command.build_py import build_py

FILES = ("SKILL.md", "protocol.md")
SOURCE = Path("skills/software-factory")
DESTINATION = Path("software_factory/skills/software-factory")


class BuildResources(build_py):
    def run(self):
        super().run()
        for name in FILES:
            source = SOURCE / name
            if source.is_symlink() or not source.is_file():
                raise RuntimeError(f"Missing canonical skill resource: {source}")
            output = Path(self.build_lib) / DESTINATION / name
            output.parent.mkdir(parents=True, exist_ok=True)
            # Unconditional copying also refreshes same-timestamp changed inputs.
            output.write_bytes(source.read_bytes())

    def get_source_files(self):
        return [*super().get_source_files(), *[str(SOURCE / name) for name in FILES]]

    def get_outputs(self, include_bytecode=1):
        return [*super().get_outputs(include_bytecode),
                *[str(Path(self.build_lib) / DESTINATION / name) for name in FILES]]
