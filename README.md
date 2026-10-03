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

Requires Node 22+, Git, macOS/Linux, and `gh` authenticated for GitHub delivery.
Install from the source (there is no published npm release yet):

```sh
git clone --branch feature/software-factory https://github.com/natejswenson/software-factory.git
cd software-factory
npm install --global .
factory --help
```

During initial review, use the draft PR's branch: `feature/software-factory`.

Add the skill to your agent. Symlink the bundled directory so its code remains
available; replace `/path/to/software-factory` with this checkout's real path:

```sh
# Codex
mkdir -p ~/.agents/skills
ln -s /path/to/software-factory/skills/software-factory ~/.agents/skills/software-factory

# Claude Code
mkdir -p ~/.claude/skills
ln -s /path/to/software-factory/skills/software-factory ~/.claude/skills/software-factory
```

Then ask your agent: **“Use software-factory in this repo to fix [task]. Finish
with verified changes and a draft PR.”** The skill drives the loop in your
current session. The CLI prints the next action; it does not call a model itself.

## Enroll a project once

Select checks that actually establish the project's behavior:

```sh
factory init --repo /path/to/app --check '["npm","test"]' --check '["npm","run","build"]'
```

Review and commit `.factory.json` on your selected base. Checks use argv arrays,
so paths and arguments containing spaces remain literal. Configure names and
`timeoutMs` (100–600000) in that file. Check definitions are frozen at task start;
editing the project configuration cannot weaken an active task's verification.
Configuration changes themselves appear in the reviewed diff.

```json
{
  "version": 1,
  "endpoint": "draft-pr",
  "checks": [
    { "name": "tests", "argv": ["npm", "test"], "timeoutMs": 120000 }
  ]
}
```

## Tasks and recovery

Your agent normally handles these commands:

```sh
factory start --repo /path/to/app --task "Fix empty search results" \
  --criterion "Empty search shows a clear message" --base main \
  --worktree-root /path/to/approved/worktrees
factory list --repo /path/to/app
factory next --run /path/returned/by/start --json
factory resume --run /path/returned/by/start --json
```

Use `--task-file` for longer requests, `--issue 42` for frozen GitHub issue intake,
and repeat `--criterion` for multiple outcomes. `--endpoint local` explicitly
selects a clean verified commit. A named `--base feature/lower-layer` supports
one dependent stack layer; automatic stack management is not included.

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

## What the evidence establishes

The snapshot includes tracked files even under ignore rules, nonignored new
files, deletions, executable modes and symlink targets. Check commands must all
pass without changing that snapshot. Review binds the plan, criteria, checks,
base, HEAD and Git tree. Delivery observes the exact committed tree and, for
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
npm test
npm run check
npm pack --dry-run
```

Integration tests use real Git repositories, worktrees and check processes;
GitHub failure/retry behavior is tested with a local adapter. Live delivery and
native-agent task evidence are recorded in `docs/plans/` when observed.

The project aims for a small, dependable task loop that fits existing agents.
Universal “best factory” claims require comparative benchmarks and are not
claimed by this release.
