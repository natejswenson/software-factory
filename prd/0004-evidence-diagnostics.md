# 0004 — Evidence diagnostics

Status: ready; proposed feature, implementation pending.

## Problem and users

An agent can see that verification or review is required without seeing exactly
why its previous proof became stale. `next_action` uses a generic missing/changed
reason; summary deliberately retains the last check's historical pass result.
The rules and Python migration runs renewed evidence repeatedly after legitimate
edits. Clear diagnostics would explain those renewals without skipping them.

## Desired outcome

Users can distinguish absent, failed, stale and current proof, inspect changed
fingerprint dimensions/files, and understand the engine's next action through a
read-only command. Historical passing results remain historical facts.

## Scope

Add `factory explain --run PATH [--json]`. Compare current context/tree to saved
plan, verification and code-review evidence; identify changed dimensions and,
where retained Git trees allow it, exact changed paths.

## Non-goals

Repairing or editing receipts, accepting stale proof, showing source contents,
replacing `next`, changing summary's exact JSON contract, or creating new reviews.

## User workflow

When the next step requires renewed evidence, run explain, inspect the causes,
then follow the normal next action. After editing rules or a plan, re-review and
verify normally. An explanation never grants delivery permission.

## Requirements

- Explain each gate separately and preserve saved hashes/results.
- Compare the previous proof's tree with the current tree, rather than confuse
  all changes against task base with edits since verification.
- Handle missing worktrees, unavailable Git objects, malformed rules and locks
  explicitly; never invent changed paths or a successful gate result.
- Recognize the engine's owned delivery-commit recovery exception and terminal
  receipts without treating historical completion as fresh current verification.

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

## Constraints and compatibility

Use Python 3.11+, standard library and existing canonical hashes/evidence helpers.
No receipt migration or new evidence key. Start `feature/evidence-diagnostics`
from `main`; merging, releasing or deleting worktrees is outside this feature.

## Dependencies

No hard prerequisite. [Design 0004](../design/0004-evidence-diagnostics.md) defines
the report. It can be used alongside preflight and review bundles, but each stays
independent and the engine remains authoritative.

## Verification

Exercise absent proof, failed checks/reviews, plan/rules edits, tree/HEAD-only
drift, tracked ignored files, deletions, modes, symlinks, missing Git objects,
owned delivery recovery and live locks. Compare all mutable state before/after.

## Risks and open questions

Git garbage collection can make earlier tree detail unavailable. Rules that were
ignored may have hashes without a historical tree representation. Label those
limits. No consequential requirement decision remains open.

## Delivery and follow-up

Deliver one reviewed draft PR with passing checks and clear diagnostics examples.
Preserve required re-verification rather than optimizing it away.
