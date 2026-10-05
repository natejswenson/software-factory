# 0010 — Design: Integration readiness before handoff

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0010](../prd/0010-integration-readiness.md).
Baseline: local `main` at `84f387e`; inspected 2026-10-05, revalidate before execution.

## Problem, evidence and decisions

Seven completed local integration runs prepared or repaired existing PRs after their
original factory deliveries. The PR15 ancestry review reproduced a local delivery
that left `MERGE_HEAD` present while returning the earlier commit. PR17 required
multiple integration tasks. Frozen task-base proof and readiness against a later
main are different questions. See findings E1 in the [run review](../design/run-review-2026-10-05.md).
These are historical observations; no current merge defect is asserted.

Goal: Before handing off a delivered branch, an agent can see which target revision was
inspected, whether that target is an ancestor of the delivered head, and whether
an unfinished Git operation needs attention. It can select the next authorized
integration task without implying that draft delivery included main integration.

Resolved scope: Add read-only `factory integration --run PATH --target main [--json]` using local
refs. Report recorded delivery, current worktree availability, target/head hashes,
ancestry and pending merge/rebase/cherry-pick operations. Provide a proposed
integration checklist; execute none of it.

## Interface and user experience

`integration --run /path/to/run --target main --json` requires both arguments.
JSON has `version: 1`, `recordedDelivery`, `target`, `head`, `ancestry`, `current`,
`nextSteps`, `limitations`, `errors`. Hash values are null when unavailable.
`ancestry` contains `targetIsAncestor`, `ahead`, `behind`; `current` contains
`worktreeAvailable`, `pendingOperations`, `owner` and `headMatchesReceipt`.
A complete divergent observation exits 0: divergence is information. Pending
operations exit 2; incomplete required commit inspection exits 3. Human output
leads with recorded endpoint, target hash and the integration condition.

## Architecture and implementation contract

Read the run without saving. Inspect owner receipts before examining current
worktree state; another owner permits persisted history only. Select the immutable
recorded delivery commit when present; otherwise label the available run head as
undelivered. Resolve the explicitly named local target through literal Git argv.
Use `merge-base --is-ancestor` and `rev-list --left-right --count` for committed
ancestry, handling the expected non-ancestor exit separately from errors.

Use `git rev-parse --git-path` to locate operation markers in the actual linked
worktree, checking MERGE_HEAD, CHERRY_PICK_HEAD, rebase-merge and rebase-apply.
Never infer absence from clean status alone. Recheck target/worktree HEAD and
markers after observation; changed inputs yield `snapshot-changed` and unknown
current readiness. Do not run merge-tree, create commits or mutate Git objects.
Existing engine freshness remains authoritative for task proof. Document that
new checks/reviews are required after actual integration edits.

## Exact file responsibilities

| File | Change |
|---|---|
| `software_factory/integration.py` | Read-only observation, ancestry and formatting |
| `software_factory/cli.py` | New command, argument validation and exits |
| `tests/test_integration.py` | Ancestry, operation markers, locks and preservation |
| `docs/user-guide/tasks-and-recovery.md; docs/reference/commands.md` | Delivery versus integration examples |
| `skills/software-factory/SKILL.md` | Optional handoff inspection and separate integration-task guidance |

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

Excluded: Automatic stack management, fetch, rebasing, merging, rewriting frozen bases,
source-identical merge commits, PR updates, CI queries or release automation.

Local target freshness is limited to its observed hash. Conflict prediction is
deferred because ancestry alone cannot establish it. No unresolved product choice.

## Implementation sequence

1. Start `feature/integration-readiness` from `main`, freeze the complete PRD and every
   criterion, and obtain a reviewed private plan including this design's contract.
2. Inspect current public behavior and existing tests; add meaningful asserting
   cases for the new behavior and identified gaps rather than duplicate fixed bugs.
3. Implement the interface/helpers, preserving existing gates and failure semantics.
4. Update maintained docs/skill guidance where specified; review portable examples
   and privacy. Keep runtime outputs and real ledgers private.
5. Run the selected behavior checks and both full repository checks, obtain a
   fresh code review covering every criterion, then observe draft delivery.

## Acceptance criteria

- **AC1:** Integration reports the exact locally resolved target and recorded head, ancestry and ahead/behind counts, while separately labeling delivery, current-file availability and unverified CI/remote state.
- **AC2:** Pending merge, rebase and cherry-pick operations are reported explicitly, including a source-identical pending merge; missing refs, objects, worktrees and live owners produce unknown or blocked observations without fabricated readiness.
- **AC3:** Invocation preserves source, index, HEAD, refs, Git operation files, run state and receipts, runs no network or check command, and offers no implicit integration action.
- **AC4:** Human and version-1 JSON output agree; exit 0 means a complete observation, 2 means invalid input or a known pending-operation blocker, and 3 means unavailable required inspection. Historical runs and original delivery gates remain compatible.
- **AC5:** Meaningful ancestry/read-only/error tests and both required repository checks pass before fresh review and observed draft-PR delivery.

## Verification and review

Use real temporary repositories with advanced main, divergent branches, deleted
worktrees, absent objects and a pending source-identical merge. Snapshot refs,
index, operation files and state before/after. Confirm the report never calls
fetch, push, commit, reset, merge or verification.

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
