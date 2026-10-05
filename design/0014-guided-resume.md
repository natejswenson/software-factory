# 0014 — Design: Find the right run and get one clear next step

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0014](../prd/0014-guided-resume.md).
Baseline: local `main` at `84f387e`; inspected 2026-10-05, revalidate before execution.

## Problem, evidence and decisions

The 27-run history contains four unfinished runs alongside delivered work,
including an older automation attempt and an unplanned checksum attempt whose
related implementation is on local main. Other repair attempts share task names.
Saved phases cannot establish that unfinished work is obsolete. Existing runs,
history, summary, explain, progress and next split discovery and recovery across
commands. E5 in the [run review](../design/run-review-2026-10-05.md) documents the evidence.

Goal: A user can select a run by an unambiguous short ID, see recorded outcome and
current availability together, and get the exact next command with its reason.
Related attempts are visible as candidates; the UI does not choose a task or
rewrite its history on the user's behalf.

Resolved scope: Add read-only `factory guide --repo PATH [--select ID_OR_PREFIX] [--json]`.
Without a selection, show recent runs and possible related attempts. With a
selection, compose existing summary/next/explain/progress observations into one
screen and give one recommended command. Mutations still use exact run paths.

## Interface and user experience

`guide --repo /path/to/app --json` emits `version: 1`, `runs`, `possibleRelations`,
`selected`, `errors`, `partial`. `--select 1234abcd` or a full UUID resolves within
the actual repo common-dir. Inventory is bounded to 20 recent rows plus unfinished
rows up to a total limit of 100; include `omitted` counts and explicit selection
can resolve an older run without increasing the display limit.

`selected` has `id`, `run`, `recordedOutcome`, `currentAvailability`, `next`,
`findings`, `diagnostics`, `progress`, `recommended` (argv, reason, requiresDirection).
For terminal done states `recommended` is null. Return argv as data; never evaluate it. Exit 0 for a complete view, 2 for invalid,
ambiguous, partial or blocked observations, 3 for top-level infrastructure failure.
A complete locked/wait view can exit 0. Existing projections keep their schemas.

## Architecture and implementation contract

Reuse tolerant history discovery/validation and authoritative engine.next_action.
Selection checks all supported run directory names, not merely the visible page;
validate prefixes before filesystem access and refuse traversal/foreign paths.
Inventory sorting is stable: unfinished first, then update time descending and
ID as tie-breaker. Same-task grouping hashes normalized task text; label as a
candidate relation. No source/task-body content appears in relation keys.

For a selected run collect only required projections: summary always, diagnostics
for missing/stale proof, progress for active verification. Avoid redundant Git
snapshots; factor a shared read-only captured observation if necessary, retaining
existing command behavior. Recheck state/owner/head tokens and return partial on
change rather than stitch together contradictory gates. Unavailable worktrees
still show the saved receipt; terminal next remains done with `recommended: null` and no action command.

Map next actions to existing literal argv: plan/review actions include expected
artifact paths as data; verify/deliver use exact --run; wait recommends progress
or status. Blocked, recovery and unknown conditions recommend inspection with
requiresDirection set appropriately. No guide call clears a lock or extends a
budget. Escape human examples with shlex.join on supported POSIX hosts.

## Exact file responsibilities

| File | Change |
|---|---|
| `software_factory/guide.py` | Bounded inventory selection, composition and formatting |
| `software_factory/history.py; software_factory/summary.py; software_factory/diagnostics.py; software_factory/progress.py` | Small shared-observation extraction only if needed |
| `software_factory/cli.py` | guide and --select dispatch |
| `tests/test_guide.py` | Selection, lifecycle, partial and no-write behavior |
| `docs/user-guide/tasks-and-recovery.md; docs/reference/commands.md; skills/software-factory/SKILL.md` | One entrypoint for discovery with existing action commands |

Inspect actual file paths/functions on the selected base. Preserve existing
public schemas and extract only helpers needed by this contract. All new tooling
uses Python and standard-library APIs.

## Compatibility and failure cases

Python 3.11+, macOS/Linux, standard-library runtime and setuptools remain required.
Codex is the primary host; Claude follows the same protocol as a compatibility
host. Keep personal paths, task state, logs and receipts outside source. No paid
model API, implicit merge/release, worktree deletion or stale-proof reuse.
Start the implementation branch from `main`; keep the existing frozen checks,
failure budget, review and observed delivery gates. These are specifications,
not implemented features.

Excluded: A browser/dashboard server, automatic resume or recovery, changing phases,
automatic supersession, shared current-run files or passing task text to a shell.

Task similarity is limited to normalized exact text hashes in this first scope,
so different repair titles will not be auto-linked. Run-ID prefixes may collide.
Show uncertainty rather than choosing by recency. No unresolved product choice.

## Implementation sequence

1. Start `feature/guided-resume` from `main`, freeze the complete PRD and every
   criterion, and obtain a reviewed private plan including this design's contract.
2. Inspect current public behavior and existing tests; add meaningful asserting
   cases for the new behavior and identified gaps rather than duplicate fixed bugs.
3. Implement the interface/helpers, preserving existing gates and failure semantics.
4. Update maintained docs/skill guidance where specified; review portable examples
   and privacy. Keep runtime outputs and real ledgers private.
5. Run the selected behavior checks and both full repository checks, obtain a
   fresh code review covering every criterion, then observe draft delivery.

## Acceptance criteria

- **AC1:** Guide lists recent/unfinished runs with recorded endpoints and current-inspection availability, preserves healthy rows beside unreadable records, and groups same-task attempts only as possible relations without changing phases.
- **AC2:** Exact UUID or a hexadecimal prefix of at least eight characters selects only a unique run in the resolved repo; absent or ambiguous matches return candidates/error and never resume, allocate or mutate any task.
- **AC3:** The selected view shows recorded delivery, current next action/reason, unresolved findings, stale-proof explanation or live progress when applicable, and one literal recommended-command argv array bound to the exact run path for actionable states; terminal done states return recommended=null.
- **AC4:** Guide remains read-only and honors live locks, missing worktrees, blocked budgets and terminal receipts. Human/JSON output label partial or unknown observations and never equate done with merged/released or obsolete with an unfinished phase.
- **AC5:** Discovery/ambiguity/lifecycle/read-only tests and both required repository checks pass before fresh review and observed draft-PR delivery; existing commands and machine schemas remain compatible.

## Verification and review

Exercise new, failed, stale, locked, blocked, missing-worktree and done fixtures.
Create two runs with similar tasks and colliding prefixes; assert no implicit
selection or resume. Compare run files, refs/index and lock bytes. Use an argv
containing spaces/metacharacters to check literal output and safe human quoting.

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source` on
the final tree. Obtain fresh plan and code review, then observe a draft PR against
`main` (or an explicitly selected lower stack layer). Report the actual endpoint;
update lifecycle only with evidence. Do not execute other backlog pairs implicitly.

The reviewer checks criterion coverage, snapshot consistency, exact exit/JSON
semantics where applicable, compatibility and absence of unauthorized mutations.
For tooling changes, also build/install and smoke the affected installed command
outside the source checkout. A fixture pass is test evidence, not live delivery.

## Rollout and recovery

No automatic run migration or existing-receipt edits. Retain current commands and
intake as compatibility paths. If observation/tooling fails, report its concrete
error and use the existing workflow; do not fabricate proof or reset the run.
Introduce the feature in one reviewed change and document its actual limitations.
