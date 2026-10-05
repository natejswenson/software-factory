# 0011 — Faster feedback without weakening verification

Status: ready; proposed feature, implementation pending.
Review date: 2026-10-05. Category: Efficiency. Priority: 2.
Baseline: local `main` at `84f387e`; revalidate the selected base before execution.

## Problem and users

Saved test-check durations grew from about 56–63 seconds in Python migration to
182–194 seconds in plugin structure. That reflects different source trees and
suite sizes, not a measured performance regression. Forty-eight verification
receipts include legitimate repair cycles. Full checks currently provide no
per-test timing report or dedicated focused-development mode. E2 in the
[run review](../design/run-review-2026-10-05.md) describes the evidence.

## Desired outcome

Agents identify expensive tests and run an explicit small set while developing,
then execute the unchanged full frozen checks for delivery. Improve feedback
latency without describing a focused pass as task verification.

## Scope

Add per-test timing to `scripts/profile_tests.py` and an explicit
`scripts/verify.py focused --test FULL_TEST_ID` mode. Profile the existing suite
with standard unittest discovery. Focused selection is manual and exact, with
repeatable literal IDs; it does not infer test impact from changed paths.

## Non-goals

Verification caching, parallel test execution, automatic affected-test selection,
changing configured checks/timeouts, suppressing failures or resetting budgets.

## User workflow

Profile a representative full suite into a private report, inspect the slowest
tests, run explicit selected tests during a repair, then use normal factory verify.
A misspelled/empty selection fails. A focused pass displays that full task proof
is still required. Timing artifacts stay outside source.

## Requirements

- Profile setup, test and teardown together with monotonic elapsed timing.
- Record stable test ID and outcome, including failures, skips and expected failures.
- Focused mode rejects discovery wildcards, unknown IDs and empty selection.
- Keep existing tests/source argv and verification receipts unchanged.
- Compare timings only on a recorded matching tree and environment; no claimed savings without measurements.

## Acceptance criteria

- **AC1:** Profiling runs normal unittest discovery, emits each test ID/outcome/duration and a full-suite total with tree and interpreter metadata, and preserves failing exit status without treating skips as passes.
- **AC2:** Focused mode executes only explicitly selected valid test IDs, rejects unknown or empty selections, and prominently reports that its result is development feedback rather than factory verification.
- **AC3:** Neither mode changes frozen checks, run receipts, failure budgets or delivery gates; profiling reports require an explicit destination outside tracked source and include no raw environment or secret values.
- **AC4:** A same-tree benchmark records full and focused wall time plus command/environment metadata, with any improvement stated only for the measured selection; the full final suite still runs and no fixed speedup is claimed from historical comparisons.
- **AC5:** Selection, timing/outcome and failure-propagation tests plus both required repository checks pass before fresh review and observed draft-PR delivery.

## Constraints and compatibility

Python 3.11+, macOS/Linux, standard-library runtime and setuptools remain required.
Codex is the primary host; Claude follows the same protocol as a compatibility
host. Keep personal paths, task state, logs and receipts outside source. No paid
model API, implicit merge/release, worktree deletion or stale-proof reuse.
Start the implementation branch from `main`; keep the existing frozen checks,
failure budget, review and observed delivery gates. These are specifications,
not implemented features.
Implementation branch: `feature/focused-feedback`.

## Dependencies

The inspected main already contains proposals 0001–0009 and their implementation.
No other new pair is required. [Matching design](../design/0011-focused-feedback.md) contains the
build contract. Read it explicitly and include relevant details in the reviewed
private plan; linked content is not implicitly loaded by existing task intake.

## Verification

Use synthetic suites with pass/fail/skip, setUp/tearDown failure and invalid IDs.
Assert exact executed IDs and valid finite timing values. Measure five same-tree
full/focused samples on one host and report medians and ranges privately; compare
matching commands and fixture setup. Avoid flaky wall-clock threshold assertions.

## Risks and open questions

Focused selection can miss related behavior; it cannot satisfy a gate. Profiling
adds overhead, so report observed totals and the timing method. Further test-suite
optimization requires its own measured, reviewed change. No unresolved choice.

## Delivery and follow-up

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source` on
the final tree. Obtain fresh plan and code review, then observe a draft PR against
`main` (or an explicitly selected lower stack layer). Report the actual endpoint;
update lifecycle only with evidence. Do not execute other backlog pairs implicitly.
