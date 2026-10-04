# Software Factory

Give your coding agent a task. Get verified changes and a draft pull request.

Software Factory runs in your existing Codex or Claude session. A small local CLI
keeps task state, creates an isolated worktree and checks completion evidence.
No model API key or background service is required.

```text
task → reviewed plan → implementation → executable checks → code review → draft PR
                              ↑                  │              │
                              └──────────────────┴──────────────┘
                                           repair
```

The engine requires tests and review for the current Git tree before delivery.
Edits invalidate evidence. Failures stay visible. Interrupted deliveries can be
retried without creating another PR. Three failed checks/reviews stop a repair
loop for user direction. Completion is a draft PR by default; merging and
releasing are separate decisions.

## Get started

Requires Python 3.11+, Git, macOS/Linux, and `gh` authenticated for GitHub delivery.
Install from source with [uv](https://docs.astral.sh/uv/guides/tools/):

```sh
git clone https://github.com/natejswenson/software-factory.git
cd software-factory
uv tool install .
factory --help
```

Add the bundled skill to Codex:

```sh
mkdir -p ~/.agents/skills
ln -sfn "$(factory skill-path)" ~/.agents/skills/software-factory
```

[Installation](docs/user-guide/installation.md) includes Claude Code, pip, source
invocation and migration from the earlier npm package. The runtime has no
third-party dependencies; packages are available through
[GitHub releases](https://github.com/natejswenson/software-factory/releases), not PyPI.

## Quickstart

Enroll your project with a meaningful check:

```sh
factory init --repo /path/to/app --check '["python3","-m","unittest","discover","-s","tests"]'
```

Review and commit the generated `.rules/factory.md` on your selected base. Then
ask your coding agent: **“Use software-factory in this repo to fix [task]. Finish
with verified changes and a draft PR.”** The skill drives the loop in your
current session; the CLI prints the next action and does not call a model itself.

## Read more

- [Project setup](docs/user-guide/project-setup.md): settings, repository rules and compatibility.
- [Tasks and recovery](docs/user-guide/tasks-and-recovery.md): intake, stacks, summaries and interrupted work.
- [Evidence](docs/reference/evidence.md): what verification and review establish.
- [Documentation](docs/README.md) and [contributing](CONTRIBUTING.md).
- [Execution designs](design/README.md) and [product requirements](prd/README.md).
- [Bundled skill](software_factory/skills/software-factory/SKILL.md) and [artifact protocol](software_factory/skills/software-factory/protocol.md).

The project aims for a small, dependable task loop that fits existing agents.
Universal “best factory” claims require comparative benchmarks and are not
claimed by this release.
