# Forward task: summary command

The real Software Factory task adds `factory summary --run PATH` on a dependent
branch above `feature/software-factory`, the open [initial draft PR](https://github.com/natejswenson/software-factory/pull/1).
Frozen base: `7809f65267b67972d8c952383eff5003bdd5bb36`.
Run ID: `d33a62d9-c498-4e22-9978-27af7f01d4cd`.

## Observed evidence before final verification

- An independent native agent passed the plan review with no findings;
  `native-plan-review.json` contains the exact engine context.
- Six CLI behavior tests were written before summary implementation. Factory
  verification attempt 1 returned exit 2: the original 25 tests passed, and all
  six new tests failed with `Unknown command: summary`. `verification-1.json`
  and `check-1-tests.log` preserve the executable failure. The source check was
  skipped after the failing test command.
- After implementation, a fresh CLI subprocess resumed the same run in phase
  `implement`, with one recorded failure and next action `implement`. The
  `fresh-process-resume.json` receipt records its PID, exit 0, run identity,
  failed verification timestamp and next action. No engine state was edited.
- The behavior tests use temporary real Git repositories and CLI subprocesses.
  They cover pre-check output, skipped checks, exact saved diagnostics, rejected
  plan/code reviews and superseded findings, timeout/process errors, drift,
  blocked/wait/resume states, interrupted PR delivery and completed receipts.
  Summary calls must preserve state bytes, source status and index tree.

Artifacts are retained in this repository's Git common-dir under
`factory/runs/<run-id>`; they are private runtime evidence, outside source.
Synthetic interruption/review data exists only in temporary tests. Final
verification, independent code review and draft delivery are required after this
note; their CLI receipts establish the final outcome.
