# 0004 — Explain stale and missing task evidence

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0004](../prd/0004-evidence-diagnostics.md).
Baseline: `447c49f0c09ca7a9d07a7bc92d1f4f3b35960fd2`; revalidate selected base.

## Current evidence and architecture

`context`, `evidence`, `same_evidence`, `plan_current`, `own_delivery_commit` and
`next_action` in `engine.py` already determine freshness. `test_summary.py`
explicitly verifies a historical passing result alongside a new `verify` action.
Rules and migration receipts show multiple legitimate verification/review cycles.
Add an explanation projection; do not create another gate implementation.

## Interface and schema

```sh
factory explain --run /path/to/run --json
```

Return `version: 1`, `id`, `phase`, `next`, `gates`, `changedPaths`, `limitations`
and `errors`. Each gate (`planReview`, `verification`, `codeReview`) contains
`status` (`missing`, `failed`, `stale`, `current`, `unknown`), `reasons` and
`differences`. Each difference has `key`, `recorded` and `current` values.
Historical verdict/passed status is included separately; a failed old check can
also have fingerprint differences without being mislabeled successful.

`next` is the exact existing next-action projection when available. If ownership,
rules or Git inspection prevents it, return null and an explicit error; never
manufacture a next action. Honor another live owner by reporting wait; include
only safe persisted information and label unavailable current comparisons.

`changedPaths` is `{baseline: "verification"|"codeReview"|null, paths: [...],
available: bool}`. Prefer the latest verification's saved tree; fall back to code
review only when no verification tree exists. Paths are sorted, repository-relative
and describe edits since that proof, not the whole feature diff against base.
Include the chosen baseline hashes in the report.

Exit 0 for a complete explanation even when evidence is stale or failed; exit 2
for invalid input or blocked runs (consistent with current blocked projections),
and 3 for incomplete infrastructure/ownership inspection. Output partial JSON
where a readable run exists. Existing `summary` schema/exit semantics stay intact.

## Comparison algorithm

1. Read the run once, check any active lock, and collect current context/evidence
   with existing helpers when inspection is possible. Do not acquire a mutation
   lock, recover one or call `save`.
2. Classify proof presence and verdict; compare expected context/evidence keys
   using existing rules-enabled/historical behavior. A passing stale record is
   stale; a failed record remains failed with additional differences.
3. Read Git trees using saved/current object IDs and use literal Git diff,
   `--no-renames --name-only -z`, to expose additions, deletions, mode and symlink
   changes. Do not run `git add` on the user's index. Existing snapshot uses a
   temporary index, which is allowed; source/index/HEAD remain unchanged.
4. For rules hash drift, compare initial/current rule path lists only if labeling
   the baseline as **initial**. The original content at the last review may not
   exist; do not imply the initial snapshot is that review. Fingerprint mismatch
   itself remains useful when per-file historical detail is unavailable.
5. Keep `own_delivery_commit` behavior visible: an engine-owned commit can change
   HEAD while delivery recovery is allowed. Report the changed HEAD plus
   `deliveryRecoveryAllowed`; do not call its proof byte-identical or override
   `next_action`. Completed runs show their historical delivery separately from
   any optional current-file inspection.

If tree objects are gone or malformed rules make current context unreadable,
return explicit unknowns/errors. If evidence changes during inspection, compare
before/after context/tree and report `snapshot-changed` rather than combine
inconsistent observations into a current-proof claim. Do not hash host services
or ignored dependencies; retain current engine limitations.

## Files and implementation

| File | Change |
|---|---|
| `software_factory/diagnostics.py` | Pure comparison/report helpers and human formatting |
| `software_factory/cli.py` | `explain` help, dispatch and report-specific exits |
| `software_factory/engine.py` | Reuse existing predicates; only extract helpers if needed, preserving gate behavior |
| `tests/test_diagnostics.py` | Freshness, read-only, historical and partial-inspection tests |
| `tests/test_summary.py` | Keep current exact summary contract assertions; add a cross-command consistency case |
| Bundled skill and current task/evidence docs | Explain when to use diagnostics and that new proof is still required |

Start `feature/evidence-diagnostics` from `main`, create a reviewed plan, implement
comparison tests first, then projection/CLI/docs. Complete checks, fresh review
and observed draft delivery. No runtime ledger migration is required.

## Acceptance criteria

- **AC1:** Explain distinguishes missing/failed/stale/current plan review,
  verification and code review, identifies changed fingerprint dimensions, and
  reports the engine's authoritative next action or its explicit inspection error.
- **AC2:** Changed paths are derived from the saved proof tree versus the current
  tree, including deletions, modes and symlinks; unavailable baseline objects or
  rules detail are labeled unknown rather than guessed or treated as unchanged.
- **AC3:** The command is read-only across live locks, historical/blocked/done
  runs and invalid worktrees; it preserves state, receipts, index/HEAD and source
  files and changes neither gates nor existing summary JSON output.
- **AC4:** Diagnostic tests and both required repository checks pass, saved-run
  compatibility remains intact, and fresh review precedes observed draft delivery.

## Validation and failure cases

Use real temporary Git snapshots and synthetic review fixtures. Exercise every
fingerprint dimension, absent/failed proof, dirty files created after a passing
check, tracked ignored files, modes, symlinks, rename-as-delete/add, removed tree
objects, invalid rules, dead/missing worktrees, locked/blocked/terminal runs and
owned delivery recovery. Compare state/receipt bytes and original index/HEAD.
Assert gate outcomes match engine predicates rather than copied logic.

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source`; build
and smoke the installed command. Review partial results and double-observation
behavior. Recovery is ordinary user-directed repository repair and rerunning the
read-only command; no diagnostic action edits receipts. No open product decision.
