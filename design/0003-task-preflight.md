# 0003 — Implement read-only task preflight

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0003](../prd/0003-task-preflight.md).
Baseline: `447c49f0c09ca7a9d07a7bc92d1f4f3b35960fd2`; revalidate selected base.

## Evidence and decisions

`engine.start`, `rules.read_project`/`assert_committed`, Git ownership helpers and
`delivery._draft_pr` contain the relevant validations. Today no command projects
them before allocation. Reuse them rather than weakening gates or introducing
an alternative settings parser. Saved rules/migration tasks show committed
settings and named stack bases in use; the time-saving benefit is inferred.

## Interface and report contract

```sh
factory preflight --repo /path/to/app --base main \
  --worktree-root /path/to/approved/worktrees \
  --branch feature/example --json
```

`--repo` and `--worktree-root` are required. Base/endpoint defaults match `start`;
branch is optional. No task or issue text is required, so preflight cannot promise
duplicate-run detection or reserve the default task-derived branch.

JSON is an object with `version: 1`, `repo`, `baseRef`, `base`, `endpoint`, `ready`,
`deliveryReady`, `checks` and `limitations`. Each check has `name`, `scope`
(`start` or `delivery`), `status` (`pass`, `fail`, `unknown`), `message` and
`remedy` (string or null). Unresolved top-level values are null. Probe order is
fixed; errors never disappear merely because a later probe passes.

`ready` is true only when every required start probe passes. `deliveryReady` is
null for offline draft delivery unless a local delivery blocker makes it false;
for local endpoints it means local prerequisites, not completed delivery. A
successful probe does not certify permissions, dependencies or test outcomes.
Exit 0 when locally start-ready, 2 for invalid input or known start blockers, 3
when infrastructure prevents establishing required start readiness. A missing
delivery-only prerequisite is reported without blocking an otherwise valid start.

## Probes and semantics

1. Resolve Git repository/common-dir and selected base using existing helpers.
   Validate supported index/submodules. Read configuration/rules and assert they
   match the selected committed base. Failures here block dependent probes only.
2. Resolve endpoint and check explicit branch with `validate_branch`; report any
   existing branch collision. With no branch supplied, say the task-derived
   branch will be validated at start; do not guess it.
3. Inspect the proposed worktree-root path and nearest existing ancestor with
   `stat`/`os.access`. Do not mkdir, create a probe file or reserve a path. Reject
   a non-directory existing root. Report access as advisory; actual worktree
   creation is authoritative. Display the resolved path so existing symlinked
   roots follow current start semantics rather than a new policy.
4. Inspect each frozen candidate argv's executable. Resolve bare names using
   `shutil.which`; inspect absolute executables directly. For repo-relative
   executables report existence/mode on the selected base and explain that the
   eventual worktree is authoritative. Do not execute them or inspect interpreter
   imports. Report installed-tool resolution limitations honestly.
5. For draft delivery, inspect presence of `gh`, an `origin` URL and a named base.
   Do not call `gh auth`, fetch, push, `ls-remote` or query GitHub. Remote auth,
   access, branch state and PR eligibility remain unknown. Do not print credentials
   embedded in a remote URL; present a sanitized host/repo or availability flag.

Unrelated source dirt is information, not a start blocker. Required settings
dirt is still blocked by the committed-base validator. No paid-model call,
preview enrollment or host configuration repair is part of this feature.

## Exact changes

| File | Responsibility |
|---|---|
| `software_factory/preflight.py` | Probe/report projection and readable formatting; standard-library path/executable checks |
| `software_factory/cli.py` | Help and dispatch, command-specific required arguments, exit handling for this report |
| `software_factory/engine.py`, `rules.py`, `git.py` | Extract a small pure helper only if needed to reuse start defaults; keep validators authoritative |
| `tests/test_preflight.py` | Real repo/read-only/edge-case and CLI contracts |
| `scripts/smoke_install.py` | Installed local preflight invocation outside source |
| README and bundled skill | Explain preflight as optional preparation, never as verification or authorization |

Prefer no `engine.start` refactor beyond sharing base/default resolution. Keep
existing `list`, `summary` and review schemas unchanged. Document new command in
current README or cleanup's user-guide paths, depending on actual base.

## Implementation sequence

Start `feature/task-preflight` from `main`, record all criteria and obtain plan
review. Add temporary-repo tests for no writes and multiple independent failures;
implement probe dependencies and formatting. Integrate CLI, docs and smoke.
Run executable checks, inspect final changes and obtain fresh code review before
observed draft delivery. Preflight itself creates no run or evidence receipt.

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

## Verification, risks and recovery

Use `FactoryCase` for committed/dirty rules, wrong base, conflict, submodule,
branch collision, paths with spaces, missing executable and absent root tests.
Mock tool discovery/access errors; assert there are no model/network/check calls.
Compare original state bytes, Git index tree, HEAD, branches, worktree inventory
and parent-directory contents. Cover legacy settings and stack-base defaults.

Run `python3 scripts/verify.py tests`, `python3 scripts/verify.py source`, build
and installed smoke. A reviewer checks default-resolution parity and that no
probe silently turns advisory readiness into executable proof. No runtime state
migration or rollback is needed; the feature is a read-only command. No open
consequential choice remains.
