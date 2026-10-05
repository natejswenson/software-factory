# 0012 — Design: Turn reviewed boundary failures into test contracts

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0012](../prd/0012-boundary-test-contracts.md).
Baseline: local `main` at `84f387e`; inspected 2026-10-05, revalidate before execution.

## Problem, evidence and decisions

Passing full checks preceded major review findings in diagnostics, review bundles,
progress, history, PR descriptions and plugin documentation. Findings included
foreign-host PID ownership, numeric overflow/deep JSON, symlinked instruction
ancestors, private path encodings and corruption of documented behavior. Review
caught them; the opportunity is to catch the same classes earlier. E3 in the
[run review](../design/run-review-2026-10-05.md) summarizes these historical fixes.

Goal: Every future public command/reader has a compact, risk-based test contract linking
its promised behavior to positive and adversarial executable cases. Reviewers
can see uncovered claims without relying on test counts or passing booleans.

Resolved scope: Add a maintained testing contract and a plan/review checklist, audit current
command boundaries, and close any uncovered cases with meaningful Python tests.
Use existing standard-library tests and review schemas. Require only applicable
cases, with reasons for omissions, rather than a matrix for every internal helper.

## Interface and user experience

No new CLI or evidence schema. Add `docs/development/boundary-tests.md` with
rows: surface, promised behavior, risk class, asserting test IDs, observation
limits. Test IDs must be discoverable. Keep the map compact: shared risks may
reference shared tests where they exercise that surface. The run-specific plan
records only applicable additions and criterion evidence.

Reviewer inputs remain the existing exact context plus an explicit plan section
or supplement; no new required JSON fields. A human/native reviewer assesses
relevance, not a validator that accepts any cited test name.

## Architecture and implementation contract

Reproduce the audit on selected main by reading test cases for the historical
findings. Do not replay private production ledgers or mutate another run. Group
shared boundary classes in a documented table: numeric/recursive data, race and
snapshot stability, owner identity, unsafe path ancestry, external presentation,
process interruption, and error-channel consistency.

Add only missing public-behavior cases to existing domain tests, preferring
real temporary repos/CLI executions for integration outcomes. Assertions must
establish intended behavior and no unintended writes, not merely mock call order.
For cleanup cases, preserve existing real process tests; make fault-injection
state transitions explicit and assert no duplicate terminal kill or erased primary
error. Link the contract from testing and from plan/code review guidance.
Review checks test relevance per nonempty commit as current AGENTS.md requires.

## Exact file responsibilities

| File | Change |
|---|---|
| `docs/development/boundary-tests.md` | Audited test contract and uncovered limits |
| `docs/development/testing.md; docs/README.md` | Navigation and usage |
| `skills/software-factory/SKILL.md; skills/software-factory/protocol.md` | Plan/review evidence-map guidance, unchanged schemas |
| `tests/test_history.py; tests/test_progress.py; tests/test_review_context.py; tests/test_processes.py; tests/test_pr_description.py` | Only missing asserting regressions after audit |
| `tests/test_documentation.py` | Referenced test-ID discovery and new navigation checks |

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

Excluded: Adding more mandatory review stages, replacing native review, inferring correctness
from coverage percentages, changing receipt schemas or claiming old fixed bugs remain.

A large mechanical checklist increases work without improving reasoning. Scope
it to public promises and applicable risks; reuse existing regressions. No new
runtime dependency or consequential product choice is required.

## Implementation sequence

1. Start `feature/boundary-test-contracts` from `main`, freeze the complete PRD and every
   criterion, and obtain a reviewed private plan including this design's contract.
2. Inspect current public behavior and existing tests; add meaningful asserting
   cases for the new behavior and identified gaps rather than duplicate fixed bugs.
3. Implement the interface/helpers, preserving existing gates and failure semantics.
4. Update maintained docs/skill guidance where specified; review portable examples
   and privacy. Keep runtime outputs and real ledgers private.
5. Run the selected behavior checks and both full repository checks, obtain a
   fresh code review covering every criterion, then observe draft delivery.

## Acceptance criteria

- **AC1:** A maintained boundary-test contract maps each relevant current public command/reader to promised outcomes and asserting test IDs, including input limits, ownership, filesystem boundaries, exit/JSON behavior and observation freshness, or an explained nonapplicability.
- **AC2:** The audit checks existing regressions for the cited historical findings and adds behavior tests for uncovered promises; it labels already-fixed cases accurately and includes at least one real CLI malformed-input/partial-result preservation test.
- **AC3:** Plans and reviewer guidance require criterion-to-test or observed-evidence mapping and regression proof for repaired findings, preserving exact context, existing review schemas and reviewer independence expectations.
- **AC4:** Synthetic adversarial cases cannot be reported as live task delivery; test counts and checklist completion cannot bypass full checks, current review, failure limits or observed delivery.
- **AC5:** Applicable macOS/Linux process and Git tests plus both required repository checks pass before fresh review and observed draft-PR delivery, with unobserved platform coverage disclosed.

## Verification and review

Inspect tests against each original recorded finding before adding duplicates.
Use actual CLI subprocesses with malformed private fixtures, unchanged receipts
and healthy neighboring runs. Test numeric/depth limits, host mismatch and
symlink ancestry independently. Retain real descendant/signal tests alongside
deterministic injection. Report available OS coverage precisely.

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
