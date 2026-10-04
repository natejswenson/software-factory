# 0006 — Verification progress and log access

Status: ready; proposed feature, implementation pending.

## Problem and users

The real rules and migration runs spent about 50–63 seconds per test check.
`execute_check` already saves duration and bounded logs, but `verify` publishes
final results after its loop and a second process mostly sees a lock/wait state.
Users and agents cannot directly ask which check is running or request a bounded
tail of its output through the CLI. The summary run also demonstrated a failed
first check with subsequent checks skipped.

## Desired outcome

A separate read-only invocation shows the active verification attempt/check,
completed and unrun checks, elapsed time and bounded log output. Agents can keep
the user informed during long checks and diagnose a failure without rerunning it.

## Scope

Add private progress snapshots written by the existing verification owner,
`factory progress --run PATH`, and bounded
`factory logs --run PATH --check-name NAME` with optional `--attempt`,
`--tail-bytes` and `--json`. Retain serial execution, fail-fast and existing logs.

## Non-goals

Parallel checks, daemon/watch server, terminal streaming/follow mode, new failure
budget rules, automatic process killing/recovery, repeating a check just to read
output, log uploads or treating progress snapshots as verification proof.

## User workflow

Start verification normally. While it runs, another process reads progress or a
bounded log tail. After completion, inspect the final receipt and next action.
If interrupted, report uncertain/interrupted progress and use existing
user-directed recovery; no monitoring command takes ownership.

## Requirements

- Include attempt, active check, elapsed time, completed results and pending or
  skipped checks. Use existing duration values after completion.
- Flush enough bounded output to make live log inspection useful without
  unbounded I/O, stdout mixing or changes to final verification semantics.
- Associate sidecars with their attempt/owner and never call stale snapshots live
  evidence. Handle historical runs without sidecars.
- Keep read operations bounded, safe and compatible with active locks.

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

## Constraints and compatibility

Python 3.11+, macOS/Linux and standard library runtime. New sidecars do not
change run versions or evidence keys. Use `feature/verification-progress` from
`main`; do not merge, release, kill foreign processes or delete worktrees.

## Dependencies

No hard prerequisite. [Design 0006](../design/0006-verification-progress.md) defines
the snapshots/read commands. Existing summary and final verification remain
authoritative; diagnostics or run history can consume observations later.

## Verification

Use a synchronized real slow check to observe progress while its owner holds the
lock. Test failed-first/skipped-later checks, bounded/flushed logs, timeout,
interruption, missing sidecars, historical attempts and no reader mutation.

## Risks and open questions

Wall-clock jumps and abrupt process termination can make elapsed/live status
uncertain. Label that uncertainty and keep monotonic durations for final results.
All consequential scope choices are resolved; continuous follow mode is deferred.

## Delivery and follow-up

Deliver a reviewed draft PR with observed live-progress fixture evidence. A
progress report is never a replacement for the final executable check receipt.
