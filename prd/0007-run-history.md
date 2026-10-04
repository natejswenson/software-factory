# 0007 — Run history and discovery

Status: ready; proposed feature, implementation pending.

## Problem and users

The repository already has four saved runs spanning repairs, stacked bases,
branch renaming and active work. `factory list` exposes only basic task/state/run
fields; understanding the sequence requires inspecting private JSON files.
`store.list_runs` also loads every matching state in one comprehension, so one
unreadable record can prevent discovery of healthy ones. No corrupt production
ledger was observed; isolation is a preventive improvement supported by the code.

## Desired outcome

Users can find the right task by recency, branch, base and phase, then inspect its
event sequence and separate verification attempts. Healthy runs remain visible
when another record is unavailable, without automatically repairing anything.

## Scope

Add `factory runs --repo PATH` with phase/limit filters, and
`factory history --run PATH` with bounded event pagination. Provide human and JSON
output, attempt timings/results from retained receipts, and precise errors.
Keep the existing `list` command and its output compatible.

## Non-goals

Archiving or deleting runs/worktrees, task scheduling, remote PR status queries,
repairing corrupt state, rewriting history, inventing missing metrics, exporting
raw logs/transcripts or changing task gates.

## User workflow

Use runs to locate active/recent tasks and their recorded delivery links. Select
a run explicitly and read history to understand rejection, repair, rename,
verification and delivery events. Resume/recover only through existing commands
under their normal ownership and user-direction rules.

## Requirements

- Sort and filter deterministically; show recorded branch/base/phase, attempts,
  failures, delivery and next-action availability.
- Keep each verification attempt separate, including failed and skipped checks;
  use existing durations without calling the sum total task duration.
- Isolate unreadable/invalid records and missing worktrees, with visible errors
  rather than disappearing tasks or falsely current outcomes.
- Support historical branch names/run schemas and read-only operation under locks.

## Acceptance criteria

- **AC1:** Runs provides deterministic bounded recency/phase discovery with
  recorded branch/base/attempt/failure/delivery information and an explicit
  current-next-action availability indicator; legacy list output is unchanged.
- **AC2:** History exposes ordered, paginated saved events and distinct retained
  verification attempts/results/durations, including failures/skips, without
  claiming that recorded completion establishes present remote state.
- **AC3:** One invalid/unreadable ledger or missing worktree does not hide healthy
  runs; errors and unavailable metrics/actions are explicit, and reads preserve
  all state, receipts, source/index/HEAD, locks and worktree inventories.
- **AC4:** Historical runs/branch names remain readable; new tests and both
  required checks pass, with fresh review before observed draft-PR delivery and
  no automatic recovery, archive, deletion, merge or release.

## Constraints and compatibility

Python 3.11+, macOS/Linux, dependency-free runtime. Add new projection schemas
rather than changing existing list/summary contracts or run identity. Use
`feature/run-history` from `main`; private history remains outside source.

## Dependencies

No hard prerequisite. [Design 0007](../design/0007-run-history.md) specifies report
schemas. Progress/diagnostics can help later, but discovery must work without them
and without valid/current worktrees for every saved record.

## Verification

Create multiple temporary runs with diverse phases/bases, historical branch names,
separate attempts, missing worktrees and an invalid ledger. Assert stable ordering,
pagination, healthy-row retention, explicit errors and no mutations. Compare
history totals to saved receipts and retain exact existing list assertions.

## Risks and open questions

Recorded history is a trusted-local ledger, not tamper-proof audit evidence.
Missing receipts and malformed timestamps must remain visible. All consequential
choices are resolved; storage retention/repair remains a separate feature.

## Delivery and follow-up

Deliver a reviewed draft PR with realistic synthetic multi-run fixtures. Report
recorded outcomes accurately and keep actual run details private.
