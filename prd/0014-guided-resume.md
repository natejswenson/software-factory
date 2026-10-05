# 0014 — Find the right run and get one clear next step

Status: ready; proposed feature, implementation pending.
Review date: 2026-10-05. Category: Ease of use and simplicity; efficiency. Priority: 1.
Baseline: local `main` at `84f387e`; revalidate the selected base before execution.

## Problem and users

The 27-run history contains four unfinished runs alongside delivered work,
including an older automation attempt and an unplanned checksum attempt whose
related implementation is on local main. Other repair attempts share task names.
Saved phases cannot establish that unfinished work is obsolete. Existing runs,
history, summary, explain, progress and next split discovery and recovery across
commands. E5 in the [run review](../design/run-review-2026-10-05.md) documents the evidence.

## Desired outcome

A user can select a run by an unambiguous short ID, see recorded outcome and
current availability together, and get the exact next command with its reason.
Related attempts are visible as candidates; the UI does not choose a task or
rewrite its history on the user's behalf.

## Scope

Add read-only `factory guide --repo PATH [--select ID_OR_PREFIX] [--json]`.
Without a selection, show recent runs and possible related attempts. With a
selection, compose existing summary/next/explain/progress observations into one
screen and give one recommended command. Mutations still use exact run paths.

## Non-goals

A browser/dashboard server, automatic resume or recovery, changing phases,
automatic supersession, shared current-run files or passing task text to a shell.

## User workflow

Use guide to see unfinished and recent delivered work. Select an exact UUID or
unique prefix; ambiguity shows candidates and refuses selection. Inspect recorded
endpoint, live availability, outstanding findings and next command. Execute that
command separately; blocked budgets or unknown owners still require direction.

## Requirements

- Prioritize unfinished runs without hiding completed work or corrupt neighbors.
- Treat same-task matches as possible relations, never proof of replacement or completion.
- Make historical delivery, current next action and unavailable worktree state explicit.
- Recommend recover/extend only as inspection or user-direction requirements, never auto-execute.
- Return literal argv arrays for agent actions and safely quoted readable examples for humans.

## Acceptance criteria

- **AC1:** Guide lists recent/unfinished runs with recorded endpoints and current-inspection availability, preserves healthy rows beside unreadable records, and groups same-task attempts only as possible relations without changing phases.
- **AC2:** Exact UUID or a hexadecimal prefix of at least eight characters selects only a unique run in the resolved repo; absent or ambiguous matches return candidates/error and never resume, allocate or mutate any task.
- **AC3:** The selected view shows recorded delivery, current next action/reason, unresolved findings, stale-proof explanation or live progress when applicable, and one literal recommended-command argv array bound to the exact run path for actionable states; terminal done states return recommended=null.
- **AC4:** Guide remains read-only and honors live locks, missing worktrees, blocked budgets and terminal receipts. Human/JSON output label partial or unknown observations and never equate done with merged/released or obsolete with an unfinished phase.
- **AC5:** Discovery/ambiguity/lifecycle/read-only tests and both required repository checks pass before fresh review and observed draft-PR delivery; existing commands and machine schemas remain compatible.

## Constraints and compatibility

Python 3.11+, macOS/Linux, standard-library runtime and setuptools remain required.
Codex is the primary host; Claude follows the same protocol as a compatibility
host. Keep personal paths, task state, logs and receipts outside source. No paid
model API, implicit merge/release, worktree deletion or stale-proof reuse.
Start the implementation branch from `main`; keep the existing frozen checks,
failure budget, review and observed delivery gates. These are specifications,
not implemented features.
Implementation branch: `feature/guided-resume`.

## Dependencies

The inspected main already contains proposals 0001–0009 and their implementation.
No other new pair is required. [Matching design](../design/0014-guided-resume.md) contains the
build contract. Read it explicitly and include relevant details in the reviewed
private plan; linked content is not implicitly loaded by existing task intake.

## Verification

Exercise new, failed, stale, locked, blocked, missing-worktree and done fixtures.
Create two runs with similar tasks and colliding prefixes; assert no implicit
selection or resume. Compare run files, refs/index and lock bytes. Use an argv
containing spaces/metacharacters to check literal output and safe human quoting.

## Risks and open questions

Task similarity is limited to normalized exact text hashes in this first scope,
so different repair titles will not be auto-linked. Run-ID prefixes may collide.
Show uncertainty rather than choosing by recency. No unresolved product choice.

## Delivery and follow-up

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source` on
the final tree. Obtain fresh plan and code review, then observe a draft PR against
`main` (or an explicitly selected lower stack layer). Report the actual endpoint;
update lifecycle only with evidence. Do not execute other backlog pairs implicitly.
