# 0011 — Design: Faster feedback without weakening verification

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0011](../prd/0011-focused-feedback.md).
Baseline: local `main` at `84f387e`; inspected 2026-10-05, revalidate before execution.

## Problem, evidence and decisions

Saved test-check durations grew from about 56–63 seconds in Python migration to
182–194 seconds in plugin structure. That reflects different source trees and
suite sizes, not a measured performance regression. Forty-eight verification
receipts include legitimate repair cycles. Full checks currently provide no
per-test timing report or dedicated focused-development mode. E2 in the
[run review](../design/run-review-2026-10-05.md) describes the evidence.

Goal: Agents identify expensive tests and run an explicit small set while developing,
then execute the unchanged full frozen checks for delivery. Improve feedback
latency without describing a focused pass as task verification.

Resolved scope: Add per-test timing to `scripts/profile_tests.py` and an explicit
`scripts/verify.py focused --test FULL_TEST_ID` mode. Profile the existing suite
with standard unittest discovery. Focused selection is manual and exact, with
repeatable literal IDs; it does not infer test impact from changed paths.

## Interface and user experience

`python3 scripts/profile_tests.py --output /path/to/private/timings.json` runs
full discovery. The version-1 report has `tree`, `pythonVersion`, `platform`,
`durationMs`, `tests` (id, outcome, durationMs) and `successful`. Do not record
hostnames, full environment variables or raw exception bodies in JSON. Ordinary
unittest failure output remains available on the console.

`python3 scripts/verify.py focused --test tests.test_example.ExampleTests.test_case`
accepts repeated `--test` IDs. Exit 0 only if the selection succeeds, 1 for an
executed failure, 2 for invalid selection/report destination. Profile write failures
exit 3 and do not erase completed test results. `tests` and `source` retain their
existing behavior and are the only configured factory checks.

## Architecture and implementation contract

Implement a small shared result class using `time.perf_counter_ns` and unittest
startTest/stopTest plus addError/addFailure/addSkip/addExpectedFailure and
addUnexpectedSuccess. Include subtest failures in their parent outcome. Account
explicitly for module/class setup errors represented by unittest error holders;
never silently drop them from the report or successful flag.

Load selected tests through `loadTestsFromName`, flatten the loaded suite and
reject loader errors, wildcards, module/class selectors and IDs absent from the
normal discovered suite. Deduplicate requested IDs in supplied order. Print the
feedback-only label before and after execution. Never invoke engine.verify or
write its receipt format. Validate the explicit report destination before running:
refuse any path within a Git worktree or its tracked/source directories, resolve
symlink ancestors, and create the report atomically without overwriting existing
files. Default console output needs no report. Keep fixture environment setup
identical to the full runner; do not disable production behavior for speed.

## Exact file responsibilities

| File | Change |
|---|---|
| `scripts/profile_tests.py` | Profiler CLI and explicit report handling |
| `scripts/test_results.py` | Shared unittest timing/outcome and selection helpers |
| `scripts/verify.py` | Focused mode only; preserve tests/source commands |
| `tests/test_feedback_tools.py` | Synthetic suites, exact selection and failures |
| `docs/development/testing.md; skills/software-factory/SKILL.md` | Development feedback and required final proof |

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

Excluded: Verification caching, parallel test execution, automatic affected-test selection,
changing configured checks/timeouts, suppressing failures or resetting budgets.

Focused selection can miss related behavior; it cannot satisfy a gate. Profiling
adds overhead, so report observed totals and the timing method. Further test-suite
optimization requires its own measured, reviewed change. No unresolved choice.

## Implementation sequence

1. Start `feature/focused-feedback` from `main`, freeze the complete PRD and every
   criterion, and obtain a reviewed private plan including this design's contract.
2. Inspect current public behavior and existing tests; add meaningful asserting
   cases for the new behavior and identified gaps rather than duplicate fixed bugs.
3. Implement the interface/helpers, preserving existing gates and failure semantics.
4. Update maintained docs/skill guidance where specified; review portable examples
   and privacy. Keep runtime outputs and real ledgers private.
5. Run the selected behavior checks and both full repository checks, obtain a
   fresh code review covering every criterion, then observe draft delivery.

## Acceptance criteria

- **AC1:** Profiling runs normal unittest discovery, emits each test ID/outcome/duration and a full-suite total with tree and interpreter metadata, and preserves failing exit status without treating skips as passes.
- **AC2:** Focused mode executes only explicitly selected valid test IDs, rejects unknown or empty selections, and prominently reports that its result is development feedback rather than factory verification.
- **AC3:** Neither mode changes frozen checks, run receipts, failure budgets or delivery gates; profiling reports require an explicit destination outside tracked source and include no raw environment or secret values.
- **AC4:** A same-tree benchmark records full and focused wall time plus command/environment metadata, with any improvement stated only for the measured selection; the full final suite still runs and no fixed speedup is claimed from historical comparisons.
- **AC5:** Selection, timing/outcome and failure-propagation tests plus both required repository checks pass before fresh review and observed draft-PR delivery.

## Verification and review

Use synthetic suites with pass/fail/skip, setUp/tearDown failure and invalid IDs.
Assert exact executed IDs and valid finite timing values. Measure five same-tree
full/focused samples on one host and report medians and ranges privately; compare
matching commands and fixture setup. Avoid flaky wall-clock threshold assertions.

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
