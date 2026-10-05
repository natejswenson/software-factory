# Installation

## Codex native plugin (primary)

Requires Python 3.11+, Git, macOS/Linux, and authenticated `gh` for GitHub delivery.
Install the standalone repository as one marketplace/plugin:

```sh
codex plugin marketplace add natejswenson/software-factory
codex plugin add software-factory@software-factory
codex plugin list --json
```

Start a fresh session and invoke `$software-factory` (use the plugin-qualified
skill name if the host's picker presents it). The shared skill locates its loaded
physical root and runs `python3 /loaded/plugin/scripts/factory.py`. User project
paths remain explicit. Nothing installs dependencies or changes shell PATH.

The repository root contains the engine plus `skills/software-factory/`;
`.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json` own its metadata.
The Claude files are generated compatibility adapters. Git manifests omit fixed
versions: native Git revision/cache identity tracks updates, while Python wheels
keep the existing tag-derived release version. A source fallback version is not
proof of the installed Git revision.


## Standalone Python tool

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


## Update and activate

For Codex's Git marketplace, refresh its source snapshot, then start a fresh
session so the configured plugin's cached skill and engine are loaded:

```sh
codex plugin marketplace upgrade software-factory
codex plugin list --json
```

For Claude compatibility:

```sh
claude plugin marketplace add natejswenson/software-factory
claude plugin install software-factory@software-factory
# Later:
claude plugin marketplace update software-factory
claude plugin update software-factory@software-factory
```

Restart Claude after updating and invoke `software-factory:software-factory`.
Installation, files updated on disk and activation in a session are separate
observations. Inspect the loaded skill's physical path and run its bound engine's
`skill-path` to verify they match. Never infer active code from a manifest label.
Claude's validator warns that there is no fixed version; this is deliberate so
Git revisions can refresh. Validate with `claude plugin validate --json /path/to/plugin`.
Other errors or unsupported fields still require repair.

For a standalone uv tool, update the checkout to the intended release/ref and
run `uv tool install --reinstall .`; for a venv, install the intended wheel with
that environment's Python. Re-resolve `skill-path` and reload the agent session.
A native plugin works offline after fetching if its required Python/Git tools are
present. Failures preserve user settings and saved runs; select the prior known
plugin source to roll back, without editing factory receipts.

## Migrate manual skill links

Install and validate the native plugin first. Inspect any existing same-named
link under `~/.agents/skills`, `~/.codex/skills` or `~/.claude/skills` and its real
target. When choosing native discovery, disable only the identified superseded
manual link, then verify a fresh session loads the native plugin. Do not remove
regular skill directories, unrelated plugins or standalone CLI installs.

Manual wheel links remain a supported alternative. `factory skill-path` still
returns the generated wheel-internal `software_factory/skills/software-factory/`
directory. Verify the exact matching environment before linking or executing
its skill, as described in the [skill's engine selection](../skills/software-factory/SKILL.md#select-the-loaded-engine).
For source links, repoint the old package-owned directory to the regular
`skills/software-factory/` directory. The root alias and old authored package
copies are removed; no runtime receipts move.

## Documentation move map

| Former path | Current guide |
|---|---|
| `docs/user-guide/installation.md` | [Installation](installation.md) |
| `docs/user-guide/project-setup.md`, `docs/user-guide/tasks-and-recovery.md` | [Usage](usage.md) |
| `docs/reference/evidence.md` | [Evidence](evidence.md) |
| `docs/development/architecture.md`, `docs/development/testing.md`, earlier `docs/testing.md` | [Development](development.md) |
| `docs/development/automation.md` | [Automation](automation.md) |
| `docs/README.md` | [Root navigation](../README.md) |
| `docs/history/README.md`, `docs/plans/README.md` | [Historical context](development.md#historical-designs-and-observations) |
| `docs/plans/2026-10-02-software-factory.md` | [Preserved initial design](history/2026-10-02-software-factory.md) |
| `docs/plans/2026-10-02-software-factory-verification.md` | [Preserved initial verification](history/2026-10-02-software-factory-verification.md) |
| `docs/plans/2026-10-02-summary-verification.md` | [Preserved summary observation](history/2026-10-02-summary-verification.md) |

Historical bodies and numbered specifications keep their original claims and
paths. Current behavior comes from the five maintained guides and shared skill.
