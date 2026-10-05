# 0010 — Integration readiness before handoff

Status: ready; proposed feature, implementation pending.
Review date: 2026-10-05. Category: Efficiency; output quality. Priority: 1.
Baseline: local `main` at `84f387e`; revalidate the selected base before execution.

## Problem and users

Seven completed local integration runs prepared or repaired existing PRs after their
original factory deliveries. The PR15 ancestry review reproduced a local delivery
that left `MERGE_HEAD` present while returning the earlier commit. PR17 required
multiple integration tasks. Frozen task-base proof and readiness against a later
main are different questions. See findings E1 in the [run review](../design/run-review-2026-10-05.md).
These are historical observations; no current merge defect is asserted.

## Desired outcome

Before handing off a delivered branch, an agent can see which target revision was
inspected, whether that target is an ancestor of the delivered head, and whether
an unfinished Git operation needs attention. It can select the next authorized
integration task without implying that draft delivery included main integration.

## Scope

Add read-only `factory integration --run PATH --target main [--json]` using local
refs. Report recorded delivery, current worktree availability, target/head hashes,
ancestry and pending merge/rebase/cherry-pick operations. Provide a proposed
integration checklist; execute none of it.

## Non-goals

Automatic stack management, fetch, rebasing, merging, rewriting frozen bases,
source-identical merge commits, PR updates, CI queries or release automation.

## User workflow

After delivery, inspect integration readiness against an explicit named target.
If the target has advanced, start a separately authorized integration task using
that exact revision and meaningful checks. If the worktree has disappeared,
inspect available committed proof and label current files unavailable. Refresh
local refs separately when the user requests remote information.

## Requirements

- Keep draft/local delivery and target ancestry separate in human and JSON output.
- Report ahead/behind counts only for available commits and include inspected hashes.
- An ancestry result never certifies conflict freedom, passing target checks or remote readiness.
- Expose pending Git operations even with empty porcelain output; do not finish them.
- Honor live run owners and distinguish recorded history from current inspection.

## Acceptance criteria

- **AC1:** Integration reports the exact locally resolved target and recorded head, ancestry and ahead/behind counts, while separately labeling delivery, current-file availability and unverified CI/remote state.
- **AC2:** Pending merge, rebase and cherry-pick operations are reported explicitly, including a source-identical pending merge; missing refs, objects, worktrees and live owners produce unknown or blocked observations without fabricated readiness.
- **AC3:** Invocation preserves source, index, HEAD, refs, Git operation files, run state and receipts, runs no network or check command, and offers no implicit integration action.
- **AC4:** Human and version-1 JSON output agree; exit 0 means a complete observation, 2 means invalid input or a known pending-operation blocker, and 3 means unavailable required inspection. Historical runs and original delivery gates remain compatible.
- **AC5:** Meaningful ancestry/read-only/error tests and both required repository checks pass before fresh review and observed draft-PR delivery.

## Constraints and compatibility

Python 3.11+, macOS/Linux, standard-library runtime and setuptools remain required.
Codex is the primary host; Claude follows the same protocol as a compatibility
host. Keep personal paths, task state, logs and receipts outside source. No paid
model API, implicit merge/release, worktree deletion or stale-proof reuse.
Start the implementation branch from `main`; keep the existing frozen checks,
failure budget, review and observed delivery gates. These are specifications,
not implemented features.
Implementation branch: `feature/integration-readiness`.

## Dependencies

The inspected main already contains proposals 0001–0009 and their implementation.
No other new pair is required. [Matching design](../design/0010-integration-readiness.md) contains the
build contract. Read it explicitly and include relevant details in the reviewed
private plan; linked content is not implicitly loaded by existing task intake.

## Verification

Use real temporary repositories with advanced main, divergent branches, deleted
worktrees, absent objects and a pending source-identical merge. Snapshot refs,
index, operation files and state before/after. Confirm the report never calls
fetch, push, commit, reset, merge or verification.

## Risks and open questions

Local target freshness is limited to its observed hash. Conflict prediction is
deferred because ancestry alone cannot establish it. No unresolved product choice.

## Delivery and follow-up

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source` on
the final tree. Obtain fresh plan and code review, then observe a draft PR against
`main` (or an explicitly selected lower stack layer). Report the actual endpoint;
update lifecycle only with evidence. Do not execute other backlog pairs implicitly.
