# 0006 — Observe active checks and read bounded logs

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0006](../prd/0006-verification-progress.md).
Baseline: `447c49f0c09ca7a9d07a7bc92d1f4f3b35960fd2`; revalidate selected base.

## Current behavior and evidence

`engine.verify` records a verify intent, runs frozen checks serially, then saves a
final receipt. `checks.execute_check` already caps each log at 1 MiB, records
`durationMs` and cleans process groups. `describe` reports wait under another
owner's lock. Real migration test checks took 56–63 seconds. Add observational
progress around this loop; do not change executable evidence or parallelize it.

## Commands and data contracts

```sh
factory progress --run /path/to/run --json
factory logs --run /path/to/run --check-name tests \
  --attempt 2 --tail-bytes 8192 --json
```

`progress` returns `version: 1`, `id`, `attempt`, `status`, `activeCheck`,
`elapsedMs`, `checks`, `owner`, `observedAt` and `limitations`. Status is
`not-started`, `running`, `completed`, `interrupted` or `unknown`. Each check
contains its name and `pending`, `running`, `passed`, `failed`, `skipped` or
`unknown` status with existing final result when available. It must distinguish
the latest sidecar attempt from the previous final receipt.

`logs` requires a single `--check-name` matching a frozen configured name. Attempt
defaults to the latest known attempt; explicit positive attempts cannot exceed
the saved attempt counter. `--tail-bytes` defaults to 8192 and is limited to
1–65536. Return `version`, `id`, `attempt`, `check`, `log`, `bytesRead`,
`tailTruncated`, `logTruncated`, `encoding` and `content`. Decode the bounded byte
tail with UTF-8 replacement, marking that encoding explicitly. Distinguish
reader-tail truncation from the writer's 1 MiB log truncation; if the writer flag
is not yet known, `logTruncated` is null rather than inferred from file size.

Readable output has the same facts without raw JSON. Exit 0 for readable
observations, including a failed/interrupted check; exit 2 for invalid inputs
or missing selected logs, 3 for infrastructure errors. Existing blocked-run
exit behavior can remain on `progress` (2 with a valid report); log retrieval
itself does not signal check success or consume repair attempts.

## Writer integration and sidecar

The verification owner writes `verification-progress.json` atomically, mode 0600,
inside its private run directory. Schema includes version, run ID, attempt,
owner PID/host, attempt/check start times, active check, completed results and
terminal status. Use a small callback from `execute_check` only if needed;
persist start/end transitions around each check in `engine.verify`, not every
output chunk. Keep `state.json`'s saved attempt/operation and final receipt as
the source of task state. Sidecars never certify unchanged files or passing gates.

At attempt start write running/pending. Before each check record its name/start;
after it finishes append its existing result. On ordinary finish mark remaining
checks skipped if fail-fast stopped execution, save final verification as today,
then record completed progress. In handled exceptions record interrupted/unknown
observations without forging a final pass. SIGKILL may leave a stale sidecar;
reader identifies that possibility rather than writing a repair receipt.

Flush bounded log buffers on a small interval (at most roughly 100 ms of
buffering while chunks arrive) and at exit so a second process can observe output.
Do not emit check bytes onto JSON stdout or remove existing log caps, signal
handlers, timeout grace period or descendant cleanup.

## Reader integrity and interruption

Readers never acquire/recover the writer lock. Read atomic state/sidecar snapshots
and verify run ID, attempt and owner correspondence. If the owner receipt exists
and matches the active operation, report observed running status, while disclosing
that PID/receipt checks are not a hostile-process identity guarantee. If the same
host owner is demonstrably dead, label interrupted; cross-host/missing/mismatched
ownership is unknown. Do not kill a PID or automatically clear the lock.

For old runs with no sidecar, project latest final results or not-started; if a
verify intent has no final record, show unknown/interrupted as observable. On
sidecar/state disagreement, prefer the matching final receipt for completed facts
and explain the stale sidecar. Compute live elapsed from UTC start/observation,
clamp negative values to zero and report clock uncertainty; final durations use
the existing monotonic measurement.

Derive log filenames only from a validated positive attempt and frozen simple
check name. Reject symlink/non-regular log files and never accept arbitrary
`--file` paths for this command. Read using seek plus the bounded byte limit,
not the full file. Re-read state metadata if a new attempt started during lookup;
return a coherent selected-attempt result or an explicit changed-snapshot error.

## Exact changes and sequence

| File | Responsibility |
|---|---|
| `software_factory/progress.py` | Sidecar helpers, read-only progress/log projection and formatting |
| `software_factory/engine.py` | Write observation transitions around existing serial verify loop |
| `software_factory/checks.py` | Bounded periodic log flush only; preserve existing results/cleanup |
| `software_factory/cli.py` | Progress/log dispatch and `--check-name`, `--attempt`, `--tail-bytes` options |
| `tests/test_progress.py`, `tests/test_processes.py` | Real concurrent reader, bounded log and interruption/regression cases |
| Bundled skill, README/task docs, installed smoke | Monitoring usage and its non-proof limits |

Start `feature/verification-progress` from `main`, review a plan with race/error
contracts, implement synchronized real-process tests, then owner/reader/CLI/docs.
Run required checks and installed smoke; obtain fresh review and observed draft
delivery. Runtime sidecars stay outside source and require no migration.

## Acceptance criteria

- **AC1:** During verification a second process can identify the current attempt,
  active check, elapsed time and completed/pending checks without taking the lock;
  final or interrupted states are labeled accurately and historical runs work
  without a progress sidecar.
- **AC2:** Log access returns only the selected frozen check's bounded output
  tail, preserves explicit truncation/decoding information, and rejects unsafe
  paths, invalid attempts/checks or excessive bounds without executing a check.
- **AC3:** Progress/log reads mutate no run/source/index state and make no network
  or model calls; sidecars are private observational data, and fail-fast order,
  timeouts, descendant cleanup, final receipts and failure budgets remain intact.
- **AC4:** Real-process progress/interruption tests and both required checks pass;
  old saved runs and summary output remain compatible, with fresh review before
  observed draft-PR delivery.

## Validation, risks and recovery

Use synchronization files/events rather than timing-only sleeps to observe a real
slow check, its live lock and flushed output. Exercise failed-first/skipped-later,
new attempt superseding old sidecar, handled SIGTERM, dead-owner observations,
missing/corrupt sidecars, old receipts, clock shifts, truncation and unsafe inputs.
Prove read commands preserve state/receipt bytes and the source/index/HEAD.
Rerun existing process-cleanup tests to guard against flush-related regressions.

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source`, build
and installed smoke. Private progress can be recreated by the next legitimate
verify; it must never clear a gate or authorize a retry. No open product choice,
paid models, implicit merge/release or worktree deletion is included.
