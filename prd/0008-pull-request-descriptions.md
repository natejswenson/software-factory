# 0008 — Evidence-bound pull request descriptions

Status: ready; proposed feature, implementation pending.

## Problem and users

The engine currently copies the whole frozen task into the PR body and uses the
task's first line as its title. That works for short requests but will make PRs
from full PRDs/designs verbose and can retain Markdown heading markers in titles.
The rules run already has both the generated body and a separately authored
summary with behavior, validation and compatibility details. Reviewers need that
concise explanation without a separate manual rewrite after delivery.

## Desired outcome

The current agent can prepare a concise title and change summary bound to the
verified implementation, inspect a preview, and let normal delivery create the
draft using it. Actual criterion/check evidence remains generated from receipts.
Stale descriptions are rejected and uncertain PR creation remains retryable.

## Scope

Add `factory pr-description --run PATH --file PATH`, accepting a structured,
evidence-bound title/summary with optional compatibility/risks. Store it privately,
render a preview, and use it for subsequent draft creation. Keep default delivery
and all historical receipts compatible when no custom description exists.

## Non-goals

Model calls by the CLI, inferring code behavior from filenames, altering task
criteria, fabricating verification, editing an existing PR on retry, marking a
draft ready, merging/releasing or publishing private run records/logs.

## User workflow

After verification, the agent writes concise prose grounded in the actual diff
and receipts, submits it and inspects the preview. Include it in reviewer context
as appropriate. Complete current code review and deliver normally. If the tree
changes, renew verification/review and resubmit the description before delivery.

## Requirements

- Use structured file input and literal argv/body files; task prose is never
  shell code. Keep human and JSON previews reviewable.
- Bind submitted prose to exact verification evidence and reject stale input.
  Preserve criteria and actual check results without dumping the full PRD.
- Validate metadata before committing/pushing; retain the selected presentation
  through interrupted delivery and reconcile existing PRs without duplicate
  creation or implicit metadata edits.
- Distinguish agent-authored claims from engine-established verification; the CLI
  cannot prove that summary prose accurately describes behavior.

## Acceptance criteria

- **AC1:** A verified run accepts bounded structured title/summary input tied to
  exact current evidence and produces a private readable/JSON preview retaining
  every criterion and actual check details without copying the full task text.
- **AC2:** Missing/invalid/stale description input is rejected without clearing
  gates or consuming repair attempts; no description preserves existing default
  delivery, saved-run identity and artifact/evidence schemas.
- **AC3:** Draft creation uses the accepted title/body and final observed commit;
  interrupted retries preserve the selected presentation and reconcile an
  existing matching PR without duplication or automatic metadata overwrite.
- **AC4:** Rendering/retry tests and both required checks pass; fresh code review
  and exact-head/base open-draft observation remain mandatory, with no model
  calls, readying, merge, release or worktree deletion.

## Constraints and compatibility

Python 3.11+, macOS/Linux, standard library runtime and existing delivery gates.
Optional presentation metadata is not a new proof key or approval. Use
`feature/pull-request-descriptions` from `main`. Keep state and presentation files
private, and examples synthetic and portable.

## Dependencies

No hard prerequisite. [Design 0008](../design/0008-pull-request-descriptions.md)
defines submission/render/retry contracts. A reviewer bundle can include the
preview as a supplement, but ordinary native review still works without it.

## Verification

Test Unicode/Markdown/long task input, complete criteria/check rendering, stale
evidence, invalid limits, no-input compatibility, failed push, uncertain PR
creation and existing matching PR reconciliation through the local GitHub adapter.
Use normal final checks and observed delivery, not mock outcomes as live proof.

## Risks and open questions

Human prose can be inaccurate even when its evidence is fresh; the agent/reviewer
remain responsible for assessing it. Existing PR metadata is left to an explicit
follow-up edit. All consequential choices for this scope are resolved.

## Delivery and follow-up

Deliver a reviewed draft PR demonstrating the preview and retry behavior. A
prepared description is drafted metadata, not an observed GitHub publication.
