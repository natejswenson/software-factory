# Tasks and recovery

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

Read the [skill](../../software_factory/skills/software-factory/SKILL.md) and
[artifact protocol](../../software_factory/skills/software-factory/protocol.md) for plan/review commands.
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

## Ready PRDs

Copy `prd/_template.md` to `NNNN-short-description.md`. Cover all sections,
observable criteria and concrete checks; resolve consequential choices and remove
placeholders. Use N/A with reasons. Ready requirements are self-contained; links
are context, not recursively loaded task text. PRDs explain what/why, designs how,
and .rules remains settings/instructions. Review/commit the ready PRD on the base.

Pass full text via `--task-file` and each complete criterion via separate literal
`--criterion` flags, in order. The generated PRD README includes a complete synthetic
example. The normal reviewed plan/checks/code review/observed delivery loop applies.
Resume the same run: source edits cannot alter frozen task text/criteria. Consequential
changes need user direction and a separately planned replacement, never state edits.
Human lifecycle labels draft/ready/in-progress/delivered are not enforced states.
In-progress requires an actual run; delivered requires observed endpoint evidence.
Only update labels when requested/included in reviewed work before final checks;
record post-delivery links through a subsequent reviewed change. Do not auto-run PRDs.

## Optional task preflight

```sh
factory preflight --repo /path/to/app --base main \
  --branch feature/example --worktree-root /path/to/approved/worktrees --json
```

Inspect readiness before allocation: Git/base/index, committed settings/rules,
branch collision, private run allocation path, worktree parent and configured
executables. No directories, files, locks, branch, worktree or run are created;
no checks, interpreter imports or network/auth queries run. Unrelated dirt is
allowed; required settings must match the committed base. Relative executable
existence/mode comes from that base, not unrelated dirty source.

The report separates start and delivery probes with pass/fail/unknown statuses and
remedies. JSON version1 returns repo/baseRef/base/endpoint, ready/deliveryReady,
checks (name/scope/status/message/remedy) and limitations. Exit0 means locally
start-ready, even with a delivery-only blocker; exit2 means invalid/known start
blocker, and exit3 means required observations unavailable through infrastructure.
Missing flags retain the usual error JSON. Unresolved values are null.

For a draft PR, only gh/origin/named-base availability is inspected; origin URL
values are withheld. Authentication, access, remote branches and PR eligibility
remain unknown offline. A local endpoint's delivery readiness describes local
prerequisites only. Access is advisory; host policy and actual worktree creation
are authoritative. Duplicate runs, allocation locks and task-derived branches
are not certified or reserved. Normal start/delivery revalidate all their gates.
A passing report does not establish executable verification or task completion.
