# 0015 — Design: Preserve meaning when guides are reorganized

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0015](../prd/0015-documentation-contracts.md).
Baseline: local `main` at `84f387e`; inspected 2026-10-05, revalidate before execution.

## Problem, evidence and decisions

Repository cleanup review found an unterminated nested Markdown fence and missing
rules guidance. Plugin-structure review found path prefixes inserted into ordinary
parentheticals, corrupting the run path, timeout range, fields and limit range.
Current documentation checks cover links, navigation and branding, and selected
rules/history limits, but not every guide's semantic promises. E6 in the
[run review](../design/run-review-2026-10-05.md) explains these already-repaired examples.

Goal: A documentation move preserves supported commands, literal limits and recovery
instructions. Executable checks catch malformed fences and mismatches in selected
public contracts before a reviewer has to rediscover them. Guides remain readable
and concise for Codex users.

Resolved scope: Extend current Python documentation checking to all maintained Markdown fence
balance and a small explicit set of public CLI/config/evidence contract assertions.
Keep existing branded guide ownership. Document a migration checklist for moving
content; author prose manually instead of broad path replacement.

## Interface and user experience

Keep `python3 scripts/documentation.py` and the existing source check entrypoint.
Add structured internal findings (path, line, contract, expected, observed) and
render concise failures on the console; no new runtime CLI or receipt schema.
Maintain contract fixtures in Python tests, using synthetic commands/paths only.
The checker must not rewrite prose or invoke brand regeneration.

## Architecture and implementation contract

Add a fence scanner shared with prose extraction. Opening fences may carry a
language label; closing fences match character, are at least opening length, and
have no trailing content. EOF with an open fence reports its original line.
Shorter inner fences remain literal content. Apply fence balance to maintained
guides and the skill/protocol, not historical specifications with quoted drafts.

Extend existing constant-based tests to check documented timeout bounds against
checks.validate_config, evidence dimensions against engine.EVIDENCE_KEYS and
storage wording against the public runs_root behavior using portable temp paths.
Probe supported commands with parser/dispatch help behavior; do not freeze the
number or ordering of commands. Assertions for recovery/frozen settings combine
required section/example presence with real temporary-repo tests for immutability;
a matching string alone does not prove the described runtime behavior.

Retain current link/anchor/brand checks. Use damaged copied documents to test
failure output; avoid turning the historical reviewed sentence into a fragile
verbatim requirement. For setup-guide completeness define the required contract
sections and executable example, not a word-count minimum. Link a short migration
checklist from docs/development/documentation.md and inspect actual rendered
Markdown using the available renderer, recording limitations if unavailable.

## Exact file responsibilities

| File | Change |
|---|---|
| `scripts/documentation.py` | Fence scanner, precise findings and retained checks |
| `tests/test_documentation.py` | Semantic constants, damaged guides and examples |
| `docs/development/documentation.md` | Retained-contract migration/review checklist |
| `docs/user-guide/project-setup.md; docs/reference/commands.md; docs/reference/evidence.md` | Clarify only audited current contract mismatches, if any |

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

Excluded: Generating all prose from code, validating arbitrary English, a new documentation
framework, changing brand metadata or rewriting historical specifications as current guides.

Overly exact prose assertions make harmless edits costly. Validate literal
contracts and section/example presence with clear scope; leave narrative quality
to review. Current-value enforcement excludes historical specs. No open choice.

## Implementation sequence

1. Start `feature/documentation-contracts` from `main`, freeze the complete PRD and every
   criterion, and obtain a reviewed private plan including this design's contract.
2. Inspect current public behavior and existing tests; add meaningful asserting
   cases for the new behavior and identified gaps rather than duplicate fixed bugs.
3. Implement the interface/helpers, preserving existing gates and failure semantics.
4. Update maintained docs/skill guidance where specified; review portable examples
   and privacy. Keep runtime outputs and real ledgers private.
5. Run the selected behavior checks and both full repository checks, obtain a
   fresh code review covering every criterion, then observe draft delivery.

## Acceptance criteria

- **AC1:** Python documentation checking rejects unterminated/mismatched maintained-guide fences with opening line details, correctly handles longer outer fences and ignores fenced examples for prose/link validation.
- **AC2:** An explicit maintained contract table covers run storage location, check timeout bounds, supported command names, evidence dimensions and recovery/frozen-settings promises, comparing values to authoritative code and exercising selected portable examples.
- **AC3:** Mutation tests prove detection of the historically observed wrong path/timeout/field/limit text and truncated setup guidance; unchanged current guides pass without asserting that arbitrary prose truth is automated.
- **AC4:** Documentation moves follow a retained-contract checklist and preserve links, navigation and pinned brand regions. Historical specs are excluded from current-value enforcement and no runtime or user configuration is changed by checks.
- **AC5:** Meaningful documentation tests and both required repository checks pass before fresh review and observed draft-PR delivery, including manual inspection of final rendered examples.

## Verification and review

Copy maintained guides to disposable fixtures and inject each historical failure
class separately. Run portable init/status snippets in disposable repos with
synthetic checks and no network. Compare public constants/parser output with the
maintained contract table, preserving all current documentation tests.

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
