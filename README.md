# Software Factory

Give Codex a task. Get verified changes and a draft pull request.

Software Factory is one standalone plugin for Codex, with Claude Code compatibility.
It runs in your current agent session. Its dependency-free Python engine keeps task
state, creates an isolated worktree and checks completion evidence. No model API
key or background service is required.

```text
task → reviewed plan → implementation → executable checks → code review → draft PR
                              ↑                  │              │
                              └──────────────────┴──────────────┘
                                           repair
```

The engine requires tests and review for the current Git tree before delivery.
Edits invalidate evidence, failed attempts stay visible, and interrupted deliveries
can be retried without another PR. Three failed checks/reviews stop for user
direction. The task endpoint is a draft; merging and releasing are separate actions.

## Get started in Codex

Requires Python 3.11+, Git, macOS/Linux and authenticated `gh` for GitHub delivery.

```sh
codex plugin marketplace add natejswenson/software-factory
codex plugin add software-factory@software-factory
```

Start a fresh Codex session and ask: **“Use $software-factory in this repo to fix
[task]. Finish with verified changes and a draft PR.”** Review and commit the
project's meaningful check configuration before starting. The skill selects the
engine from its own loaded plugin root; it does not rely on a global `factory`.

[Installation and migration](docs/installation.md) covers native updates, Claude,
standalone uv/pip tools, source use and legacy skill links. Python wheel/source
archives remain available through [GitHub releases](https://github.com/natejswenson/software-factory/releases),
not PyPI. Existing saved runs retain their evidence and original executable checks.

## Read more

- [Usage](docs/usage.md): project setup, commands, observations, stacks and recovery.
- [Evidence](docs/evidence.md): freshness, review, delivery and proof limits.
- [Development](docs/development.md): ownership, build resources, behavior coverage and history.
- [Automation](docs/automation.md): required CI, ready PR merges and patch releases.
- [Contributing](CONTRIBUTING.md), [requirements](prd/README.md) and [designs](design/README.md).
- [Shared skill](skills/software-factory/SKILL.md) and [artifact protocol](skills/software-factory/protocol.md).

Universal “best factory” claims require comparative benchmarks and are not claimed.
