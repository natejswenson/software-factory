# 0005 — Review context bundles

Status: ready; proposed feature, implementation pending.

## Problem and users

Native reviewers need the task, every criterion, current rules, plan, exact
freshness object and, for code review, verification and the complete diff.
Today the agent assembles those inputs manually. The Python migration run has
three separate hand-built reviewer requests; the active automation task has
initial and revised plan requests. Consistent context assembly would reduce this
repeated work and the chance of omitting an instruction or copying stale hashes.

## Desired outcome

The agent can obtain a complete, bounded, read-only reviewer bundle for a specific
stage, add explicit host instructions/supporting evidence, and pass it to a native
reviewer. The bundle clearly states what it captures and what the caller must
supply. It produces no reviewer verdict or approval.

## Scope

Add `factory review-context --run PATH --stage plan|code`, with optional repeated
`--instructions-file` and `--supplement` inputs and `--json`. Include full task,
criteria, plan, current rules, frozen checks, stage-specific context/evidence,
applicable repository instructions and the code-stage diff/verification.

## Non-goals

Launching reviewers or paid models, approving plans/code, discovering conversation
instructions, executing prose, generating fake review evidence, changing artifact
schemas, truncating required context silently or committing private bundles.

## User workflow

After writing a plan, request the plan bundle and delegate a native reviewer with
the current user/host instructions. After verification, request the code bundle,
include relevant supplemental proofs, and request the structured review artifact.
Submit that artifact through the existing CLI and obey freshness rejection.

## Requirements

- Use exact existing context/evidence; include full current rules with precedence
  guidance and historical rules-disabled behavior.
- Include the full reviewed-tree diff for code review, not a diff of an unrelated
  original checkout or only a path list. Identify binary changes explicitly.
- Capture supplied instructions/supporting files as data, including hashes and
  any limits; never treat them as authorization or successful verification.
- Reject stale/moving/incomplete inputs before presenting a complete bundle.
  Remain read-only and preserve submission gates.

## Acceptance criteria

- **AC1:** Plan/code bundles contain exact stage-specific engine context/evidence,
  full task/criteria/plan/current rules/frozen checks and applicable repository
  instructions; code bundles include complete reviewed-tree diff and verification.
- **AC2:** Explicit instruction/supplement inputs are preserved and attributed,
  host/conversation discovery limits are disclosed, and oversized, unsafe or
  changing required inputs cause a clear failure rather than silent truncation
  or a falsely complete bundle.
- **AC3:** Bundle generation creates no verdict, review receipt, run mutation,
  source/index change or model/network call; code bundles require current passing
  verification, and normal review submission continues to reject stale artifacts.
- **AC4:** Historical runs, rules-disabled contexts and exact review schemas stay
  compatible; meaningful bundle tests and both required checks pass, with fresh
  review before observed draft-PR delivery.

## Constraints and compatibility

Python 3.11+, macOS/Linux, standard-library runtime. Bundle schema versioning is
independent of review/evidence schemas. Use `feature/review-context-bundles` from
`main`; no automatic merge, release, reviewer launch or worktree cleanup.

## Dependencies

No hard prerequisite. [Design 0005](../design/0005-review-context-bundles.md) specifies
the bundle. Evidence diagnostics can help explain a rejected request, but are
not required. PR description inputs may be attached as supplements later.

## Verification

Compare exact bundle values to the existing engine helpers; test multiline and
Unicode content, current rules, frozen-check edits, historical runs, binary
diffs, path scopes, missing files, limits and changes during capture. Assert no
state/index mutation and prove stale artifact submission still fails.

## Risks and open questions

Large tasks may exceed the explicit bundle limit. Fail with actionable guidance
to narrow/split the task; never drop required evidence. Native independence
remains a host responsibility. No unresolved consequential choice remains.

## Delivery and follow-up

Deliver a reviewed draft PR and show a synthetic fixture producing both stages.
Keep actual bundles private; generating them does not establish review success.
