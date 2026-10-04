# 0003 — Task preflight

Status: ready; proposed feature, implementation pending.

## Problem and users

Agents and developers currently discover readiness problems while starting or
delivering a task. `engine.start` checks rules/base consistency but also creates
run allocation state and a worktree; draft delivery checks GitHub prerequisites
later. The saved rules and migration runs demonstrate settings/base and stacked
branch coordination. A read-only readiness report would make these choices
reviewable before task allocation. No failed preflight incident is claimed.

## Desired outcome

A user can inspect locally observable repository, base, configuration, branch,
worktree-root and delivery prerequisites without creating a task or executing
checks. The report distinguishes starting readiness from unverified remote
delivery readiness and gives a concrete corrective action for each blocker.

## Scope

Add `factory preflight --repo PATH --worktree-root PATH`, with optional `--base`,
`--branch`, `--endpoint` and `--json`. Reuse authoritative validators. Report
resolved base, frozen-settings candidate, executable availability and host
limitations. Do not allocate or mutate anything.

## Non-goals

Executing tests, installing dependencies, testing write access by creating files,
network/authentication probes, starting a task, validating an application's
behavior, automatically fixing settings or replacing checks at task start.

## User workflow

Run preflight, inspect all reported blockers, correct the actual configuration or
environment, rerun, then start normally. The normal start/delivery gates still
revalidate their requirements because the repository can change after preflight.

## Requirements

- Keep output useful when one probe fails; dependent probes say unknown rather
  than fabricate a result. Dirty unrelated source files are allowed and described.
- Locally inspect selected base, committed settings/rules, branch naming/collision,
  supported Git state, check executables and the proposed worktree parent.
- Report missing local GitHub prerequisites for draft delivery, while explicitly
  leaving remote auth, access and PR acceptance unknown without network calls.
- Provide stable machine-readable statuses and exit codes plus readable actions.

## Acceptance criteria

- **AC1:** Preflight reports all locally observable start prerequisites and
  independent blockers, with pass/fail/unknown statuses, concrete remedies and
  resolved base/endpoint; unrelated dirty source does not become a false blocker.
- **AC2:** Invocation leaves source/index/HEAD, branches, worktrees, config, private
  run directories and existing receipts unchanged and runs no checks or network
  commands; absent run/worktree-root directories are not created.
- **AC3:** Human/JSON output and exit codes distinguish start-ready, locally
  blocked and unavailable probes; draft remote readiness is never reported as
  verified from offline checks, and invalid input has no traceback.
- **AC4:** Normal start/delivery continue to revalidate their original gates;
  Python/runtime dependencies, legacy configuration and saved runs remain
  compatible; meaningful preflight tests and both repository checks pass before
  fresh review and observed draft-PR delivery.

## Constraints and compatibility

Python 3.11+, macOS/Linux, standard library runtime, setuptools, no paid models.
No existing JSON schemas or command defaults change. Use branch
`feature/task-preflight` from `main`; preserve frozen checks and review gates.
No implicit merge, release or worktree deletion.

## Dependencies

No feature prerequisite. [Design 0003](../design/0003-task-preflight.md) specifies
the implementation. If cleanup is present, use its maintained documentation paths;
otherwise update current README/testing guidance. The optional preview platform
is not a factory-readiness prerequisite.

## Verification

Temporary Git repositories cover valid settings, wrong base, unsafe rules,
conflicts, branches, unavailable executables, missing parents, unrelated dirty
files and absent GitHub tooling. Compare filesystem, index, HEAD and state bytes
before/after. Run both required checks and the installed command smoke.

## Risks and open questions

Permission and executable probes are advisory snapshots, not proof that a later
check or delivery will work. Report that limitation explicitly. All consequential
choices for this scope are resolved; network validation is deferred.

## Delivery and follow-up

Deliver a reviewed draft PR to the selected base with passing executable evidence.
Do not call a local preflight report a verified software task. Implementation
status changes only after observing the requested endpoint.
