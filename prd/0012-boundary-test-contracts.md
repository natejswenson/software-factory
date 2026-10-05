# 0012 — Turn reviewed boundary failures into test contracts

Status: ready; proposed feature, implementation pending.
Review date: 2026-10-05. Category: Output quality; efficiency. Priority: 1.
Baseline: local `main` at `84f387e`; revalidate the selected base before execution.

## Problem and users

Passing full checks preceded major review findings in diagnostics, review bundles,
progress, history, PR descriptions and plugin documentation. Findings included
foreign-host PID ownership, numeric overflow/deep JSON, symlinked instruction
ancestors, private path encodings and corruption of documented behavior. Review
caught them; the opportunity is to catch the same classes earlier. E3 in the
[run review](../design/run-review-2026-10-05.md) summarizes these historical fixes.

## Desired outcome

Every future public command/reader has a compact, risk-based test contract linking
its promised behavior to positive and adversarial executable cases. Reviewers
can see uncovered claims without relying on test counts or passing booleans.

## Scope

Add a maintained testing contract and a plan/review checklist, audit current
command boundaries, and close any uncovered cases with meaningful Python tests.
Use existing standard-library tests and review schemas. Require only applicable
cases, with reasons for omissions, rather than a matrix for every internal helper.

## Non-goals

Adding more mandatory review stages, replacing native review, inferring correctness
from coverage percentages, changing receipt schemas or claiming old fixed bugs remain.

## User workflow

During planning, select relevant boundary classes and map each acceptance claim
to an asserting test or an explicit observation limitation. Run focused repros
while implementing; after full verification, give reviewers this map with exact
context. A review-discovered failure gets a regression before fresh full checks.

## Requirements

- Cover CLI no-traceback/valid-JSON exits, owner host+PID, bounded nested input,
  symlink ancestors, portable/private path forms and signal cleanup where applicable.
- Distinguish synthetic fault injection from real Git/process observations.
- Include read-only preservation and missing/change-during-read cases for observers.
- Do not count structural assertions or a nonempty evidence string as behavioral coverage.
- Record coverage gaps honestly; the reviewer decides whether the claim is supported.

## Acceptance criteria

- **AC1:** A maintained boundary-test contract maps each relevant current public command/reader to promised outcomes and asserting test IDs, including input limits, ownership, filesystem boundaries, exit/JSON behavior and observation freshness, or an explained nonapplicability.
- **AC2:** The audit checks existing regressions for the cited historical findings and adds behavior tests for uncovered promises; it labels already-fixed cases accurately and includes at least one real CLI malformed-input/partial-result preservation test.
- **AC3:** Plans and reviewer guidance require criterion-to-test or observed-evidence mapping and regression proof for repaired findings, preserving exact context, existing review schemas and reviewer independence expectations.
- **AC4:** Synthetic adversarial cases cannot be reported as live task delivery; test counts and checklist completion cannot bypass full checks, current review, failure limits or observed delivery.
- **AC5:** Applicable macOS/Linux process and Git tests plus both required repository checks pass before fresh review and observed draft-PR delivery, with unobserved platform coverage disclosed.

## Constraints and compatibility

Python 3.11+, macOS/Linux, standard-library runtime and setuptools remain required.
Codex is the primary host; Claude follows the same protocol as a compatibility
host. Keep personal paths, task state, logs and receipts outside source. No paid
model API, implicit merge/release, worktree deletion or stale-proof reuse.
Start the implementation branch from `main`; keep the existing frozen checks,
failure budget, review and observed delivery gates. These are specifications,
not implemented features.
Implementation branch: `feature/boundary-test-contracts`.

## Dependencies

The inspected main already contains proposals 0001–0009 and their implementation.
No other new pair is required. [Matching design](../design/0012-boundary-test-contracts.md) contains the
build contract. Read it explicitly and include relevant details in the reviewed
private plan; linked content is not implicitly loaded by existing task intake.

## Verification

Inspect tests against each original recorded finding before adding duplicates.
Use actual CLI subprocesses with malformed private fixtures, unchanged receipts
and healthy neighboring runs. Test numeric/depth limits, host mismatch and
symlink ancestry independently. Retain real descendant/signal tests alongside
deterministic injection. Report available OS coverage precisely.

## Risks and open questions

A large mechanical checklist increases work without improving reasoning. Scope
it to public promises and applicable risks; reuse existing regressions. No new
runtime dependency or consequential product choice is required.

## Delivery and follow-up

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source` on
the final tree. Obtain fresh plan and code review, then observe a draft PR against
`main` (or an explicitly selected lower stack layer). Report the actual endpoint;
update lifecycle only with evidence. Do not execute other backlog pairs implicitly.
