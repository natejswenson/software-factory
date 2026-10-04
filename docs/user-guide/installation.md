# Installation

## Get started

Requires Python 3.11+, Git, macOS/Linux, and `gh` authenticated for GitHub delivery.
Install from source with [uv](https://docs.astral.sh/uv/guides/tools/) (no PyPI release yet):

```sh
git clone https://github.com/natejswenson/software-factory.git
cd software-factory
uv tool install .
factory --help
```

Add the bundled skill to your agent. `factory skill-path` locates it in the
installed Python package:

```sh
# Codex
mkdir -p ~/.agents/skills
ln -sfn "$(factory skill-path)" ~/.agents/skills/software-factory

# Claude Code
mkdir -p ~/.claude/skills
ln -sfn "$(factory skill-path)" ~/.claude/skills/software-factory
```

Then ask your agent: **“Use software-factory in this repo to fix [task]. Finish
with verified changes and a draft PR.”** The skill drives the loop in your
current session. The CLI prints the next action; it does not call a model itself.


## Python installation and existing runs

The runtime has no third-party dependencies. `uv tool install .` builds a standard
wheel with setuptools in an isolated build environment. A pip alternative is:

```sh
python3 -m venv /path/to/factory-venv
/path/to/factory-venv/bin/python -m pip install .
/path/to/factory-venv/bin/factory --help
```

From a checkout, use `python3 -m software_factory` wherever examples say `factory`.
No installation is needed for source development or the test suite.

When replacing an earlier npm installation, uninstall that package explicitly
(`npm uninstall --global @natejswenson/software-factory`), then install this Python
version and reconnect the skill symlinks using `factory skill-path`. Keep the old
runtime until active work has been reviewed if you prefer a gradual migration.
Run directories, version-1 JSON receipts, context hashes and historical branch
ownership are retained. No state migration or receipt editing is required.
Existing tasks keep their original check argv: if a project's frozen checks use
Node, that project still requires Node for those checks. The factory itself does
not. `resume`, `summary` and delivery operate on the same saved run directory.


The source compatibility route `skills/software-factory` is a relative symlink
to `software_factory/skills/software-factory`. Maintained documentation links use
that canonical packaged directory. Installed users should use `factory skill-path`.
