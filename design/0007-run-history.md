# 0007 — Discover runs and inspect their recorded history

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0007](../prd/0007-run-history.md).
Baseline: `447c49f0c09ca7a9d07a7bc92d1f4f3b35960fd2`; revalidate selected base.

## Evidence and approach

`store.save` already appends timestamped events, and verification receipts already
retain check durations/results. The four inspected runs include a rejected plan,
check repair, branch rename, stacked delivery and an active task. CLI `list`
projects little of this data; its all-or-nothing reader fails on one bad record.
Add separate read-only discovery/history projections. Keep legacy `list` and the
allocation/deduplication reader strict; error isolation must not weaken start.

## Interfaces and schemas

```sh
factory runs --repo /path/to/app --phase implement --limit 20 --json
factory history --run /path/to/run --offset 0 --limit 100 --json
```

`runs` uses optional `--phase` from existing phases, default limit 20, range
1–1000. Sort by valid `updatedAt` descending, falling back to `createdAt`, then
ID for ties; invalid/missing times sort last and are labeled. Filtering precedes
limit. Enumerate only run-directory names supported by the existing ledger;
do not turn incidental files into candidate tasks.

JSON: `version: 1`, `repo`, `total`, `matched`, `runs`, `errors`. Each row includes
`id`, `run`, `taskTitle`, `phase`, `branch`, `base`, `endpoint`, `updatedAt`,
`attempts`, `failures`, `delivery`, `nextAction` and `nextAvailable`.
Values are projections of saved fields; `delivery` is explicitly recorded data,
not a refreshed GitHub response. A missing worktree can leave a row with
`nextAction: null`, `nextAvailable: false` and a corresponding error. A live lock
can report wait through existing `describe`. No need to inspect source content.

`history` defaults to offset 0/limit 100, permits nonnegative offset and limits
1–1000. JSON includes `version`, `id`, `phase`, `eventsTotal`, `offset`,
`events`, `attempts`, `totals`, `delivery` and `errors`. Events retain append order
and have stable original `index`, `at`, `action` and saved `details`. Do not sort
them by wall-clock time, which can move backward. Pagination covers events only;
attempt summaries stay available across pages.

Each attempt contains its number, saved timestamp/passed/unchanged, evidence
availability, and check-name/status/duration/log-reference projections. Frozen
configured checks missing from that attempt are `not-run`, not passed or reused
from an earlier attempt. Missing expected receipts are explicit missing records;
absent old duration fields are null. Totals include known attempts, failures and
sum of available check execution milliseconds with missing-metric counts. This
sum is **check execution time**, never total wall-clock task duration.

Normal discovery/history exit 0 even with blocked rows; these are inventories,
not next-action commands. Return a valid partial report and exit 2 when records
are unreadable/invalid or required per-run inspection is unavailable. Top-level
infrastructure failures return 3. Invalid arguments retain normal error JSON
and exit 2. Existing list/summary/status behavior remains unchanged.

## Safe collection and partial results

Resolve repository/common-dir with existing helpers. Do not create an absent
run directory. For discovery use a dedicated tolerant collector that validates
the fields it projects and catches per-record parsing/schema/I/O errors. Keep
`read_run` identity/path validation, and report unsupported records instead of
repairing or treating them as valid. Do not enforce new branch prefixes on
historical runs; actual saved `factory/<id>` branches must remain readable.

Do not follow symlink run entries or verification receipts. Read known numeric
`verification-N.json` artifacts referenced by the saved counter/history, not raw
logs or arbitrary requested paths. Retry a changed atomic read once if appropriate;
then report the record unavailable rather than hide it. Bound receipt reads to
the existing artifact expectations; reject unreasonable counters/invalid shapes
instead of looping over untrusted ranges. Use at most 1000 attempt records per
history report and disclose that limit with an error for larger ledgers; a future
attempt-pagination feature can extend it without rewriting state.

Project stored fields before attempting live `describe`, so failed ownership or
missing worktrees cannot erase the row. Do not acquire mutation locks, call
recover/save, validate a remote PR, import memory or rewrite history. No new
cryptographic audit claim is made: these are local source-attributed records.

## Exact file changes

| File | Responsibility |
|---|---|
| `software_factory/history.py` | Tolerant discovery and per-run history projections, pagination/formatting |
| `software_factory/store.py` | Small enumeration/read helper if needed; preserve strict `list_runs` use in allocation |
| `software_factory/cli.py` | New commands and `--phase`, `--limit`, `--offset` with command-local validation |
| `tests/test_history.py` | Multi-run, timing, invalid ledger, historical and read-only behavior |
| `tests/test_lifecycle.py`, `tests/test_summary.py` | Preserve list/summary and start/dedup invariants |
| README/task docs, bundled skill, installed smoke | How to choose/read/resume a run; recorded-versus-live outcome distinction |

## Implementation sequence

Start `feature/run-history` from `main`, persist all criteria and review the plan.
Write multi-run fixtures and isolation tests, implement projections, then CLI/docs
and installed smoke. Verify and review before observed draft delivery.

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

## Verification, risks and recovery

Use real temporary repositories with multiple task bases/phases and synthetic
saved receipts/events for interruption cases. Test all ordering/tie/filter/page
boundaries, failed/skipped checks, missing timing fields, malformed timestamps,
corrupt/unsupported records, missing worktrees, live locks, absent run directories,
unsafe symlinks and changing reads. Show healthy rows survive an invalid neighbor
while strict duplicate-start/allocation still refuses ambiguous invalid state.
Compare state/artifact bytes and source/index/HEAD/worktree inventory before/after.

Run `python3 scripts/verify.py tests`, `python3 scripts/verify.py source`, build
and installed smoke. Errors require user-directed ledger/repository inspection;
this feature never repairs or deletes evidence. No consequential choice remains.
