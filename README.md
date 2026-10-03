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

## Enroll a project once

Select checks that actually establish the project's behavior:

```sh
factory init --repo /path/to/app --check '["python3","-m","unittest","discover","-s","tests"]'
```

`init` creates `.rules/factory.md`. Review and commit it on your selected base.
Settings and repository instructions live together in Markdown. For example,
create `.rules/factory.md` with:

````markdown
# Software Factory

```factory-config
{
  "version": 1,
  "endpoint": "draft-pr",
  "checks": [
    { "name": "tests", "argv": ["python3", "-m", "unittest", "discover", "-s", "tests"], "timeoutMs": 120000 }
  ]
}
```

## Repository instructions

Use the existing module patterns. Add a regression test for each bug fix.
Explain any change to public APIs in the README.
````

Add other instructions in files such as `.rules/testing.md` and
`.rules/review.md`. Direct lowercase `*.md` files are read in lexical filename
order; nested directories and other extensions are skipped. Missing `.rules`
means no extra instructions. Files must be regular UTF-8 files, at most 128 KiB
each, 128 files and 1 MiB total. Symlinks are rejected. Instructions are read by
the agent and both reviewers; the CLI does not execute Markdown or interpret
natural language as check commands. Explicit user and host/repository
instructions take priority. Rules do not authorize merges or bypass review.

A `factory-config` fence (backticks or tildes) contains a JSON object with only
`version`, `endpoint` and `checks`. Settings can be split among files, but each
key may appear only once across all config blocks. Duplicate JSON keys,
unknown settings and malformed/unterminated config blocks are errors. Examples
inside another code fence are not settings. Default version is 1 and endpoint
is `draft-pr`; at least one meaningful check is required. Checks use literal
argv arrays and `timeoutMs` (100–600000). No shell is added.

Existing `.factory.json` projects remain supported. When both formats exist,
the valid legacy file provides the baseline and Markdown settings explicitly
override its keys. To migrate, move the JSON into a `factory-config` fence and
remove `.factory.json`; commit both changes before starting the next task.
`init` refuses existing settings rather than overwriting them.

Configuration and selected rules must match the committed selected base at
start. The task then reads rules from its own worktree; edits in the original
checkout cannot replace those instructions. `factory rules --run <run>` prints
current rules; `--json` returns exact file paths, content, hashes and the initial
snapshot path. Initial content is preserved privately as `rules-initial.json`
and in saved state; `status` labels its initial hash and paths. Resume retains
that snapshot and checks current worktree instructions.

Adding, editing or removing a rule requires fresh plan review, checks and code
review before delivery, even if the rule file is ignored by Git. Settings are
frozen at task start: editing Markdown settings requires fresh plan review,
verification with the original checks and code review. The active task keeps its
original endpoint as well. Reviewed settings changes can be delivered normally;
subsequent tasks use the new configuration. Changes to legacy
`.factory.json` retain the existing frozen-check behavior and appear in the
reviewed diff. Runs created before rules support retain their original evidence
protocol; rules apply automatically to new runs without rewriting old receipts.

## Tasks and recovery

Your agent normally handles these commands:

```sh
factory start --repo /path/to/app --task "Fix empty search results" \
  --criterion "Empty search shows a clear message" --base main \
  --worktree-root /path/to/approved/worktrees
factory list --repo /path/to/app
factory summary --run /path/returned/by/start
factory rules --run /path/returned/by/start
factory next --run /path/returned/by/start --json
factory resume --run /path/returned/by/start --json
```

Use `--task-file` for longer requests, `--issue 42` for frozen GitHub issue intake,
and repeat `--criterion` for multiple outcomes. `--endpoint local` explicitly
selects a clean verified commit. A named `--base feature/lower-layer` supports
one dependent stack layer; automatic stack management is not included.

New runs use `feature/<task-slug>-<id>`. Select a branch with
`--branch feature/<name>`, `bug/<name>` or `issue/<name>` using lowercase words
separated by hyphens. `factory rename --run <run> --branch feature/<name>`
renames an owned task before delivery, records the intent and observed ownership,
and clears verification/code review. Resume reconciles interrupted renames;
collisions and changed ownership/HEAD are rejected.

Runs and logs live under the repository's Git common-dir (`factory/runs`), not
in source. Original dirty files are preserved. No branch/worktree is removed
automatically. `recover --run <run>` clears dead operation and start-allocation
locks; `recover --repo <repo>` recovers a start that never returned a run path.
Recovery refuses a live process lock. A `SIGKILL` can leave a
check process alive: inspect and stop that task's orphan before recovery.
`extend --attempts 1 --reason "User authorized another attempt"` extends a
blocked run only under explicit user direction.

Read the [skill](skills/software-factory/SKILL.md) and
[artifact protocol](skills/software-factory/protocol.md) for plan/review commands.
Use `--json` for every command when integrating another agent or UI.

`summary` is a read-only overview: task, criteria, last check results, findings
from the latest plan and code reviews, next action and delivery. Checks not
executed in the last attempt say `not run`, including checks skipped after a
failure. Findings stay visible until a newer review or verification supersedes
them. Last results may be stale after edits; the next action reflects the current
files. A committed change with PR delivery still pending is shown as pending.

`summary --json` emits one compact line with `id`, `task`, `phase`, `endpoint`,
`criteria`, `checks`, `verification`, `findings`, `next` and `delivery`.
Each configured check contains its exact `result`, or `null` when unrun.
`verification` retains `passed`, `unchanged` and `at`; `findings` has `plan` and
`code` arrays. `next` retains action, reason and applicable recovery details,
without review context or Git evidence. `delivery` is the exact current receipt
or `null`. Strings and result values are preserved; full evidence is available
through `status --json`. Like status, a blocked run returns exit code 2.

## What the evidence establishes

The snapshot includes tracked files even under ignore rules, nonignored new
files, deletions, executable modes and symlink targets. Check commands must all
pass without changing that snapshot. Review binds the plan, criteria, checks,
repository rules, base, HEAD and Git tree. Delivery observes the exact committed tree and, for
GitHub, an open draft PR with the same branch/head/base.

The engine validates evidence structure and freshness. It cannot prove that a
reviewer reasoned correctly, that tests cover every bug, or that two reviewers
are independent. Ignored dependencies, external services and environment state
are outside the Git fingerprint. Submodules and conflicted indexes are rejected.
Local processes and state files are trusted; hashes are not a security sandbox.

Checks execute repository code with your host's permissions. No shell is added
by the engine; an explicitly configured shell command still runs that shell.
Check output is capped at 1 MiB per log, with truncation recorded. Timeout and
interrupt handling terminate POSIX process groups. No paid model API, telemetry,
account database, memory service or Kubernetes platform is required. The skill
uses existing authorized memory/preview integrations when present.

## Development

```sh
python3 scripts/verify.py tests
python3 scripts/verify.py source
uv build
```

Integration tests use real Git repositories, worktrees and check processes;
GitHub failure/retry behavior is tested with a local adapter. Live delivery and
native-agent task evidence are recorded in `docs/plans/` when observed.

The project aims for a small, dependable task loop that fits existing agents.
Universal “best factory” claims require comparative benchmarks and are not
claimed by this release.
