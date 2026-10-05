# 0015 — Preserve meaning when guides are reorganized

Status: ready; proposed feature, implementation pending.
Review date: 2026-10-05. Category: Output quality; ease of use and simplicity. Priority: 1.
Baseline: local `main` at `84f387e`; revalidate the selected base before execution.

## Problem and users

Repository cleanup review found an unterminated nested Markdown fence and missing
rules guidance. Plugin-structure review found path prefixes inserted into ordinary
parentheticals, corrupting the run path, timeout range, fields and limit range.
Current documentation checks cover links, navigation and branding, and selected
rules/history limits, but not every guide's semantic promises. E6 in the
[run review](../design/run-review-2026-10-05.md) explains these already-repaired examples.

## Desired outcome

A documentation move preserves supported commands, literal limits and recovery
instructions. Executable checks catch malformed fences and mismatches in selected
public contracts before a reviewer has to rediscover them. Guides remain readable
and concise for Codex users.

## Scope

Extend current Python documentation checking to all maintained Markdown fence
balance and a small explicit set of public CLI/config/evidence contract assertions.
Keep existing branded guide ownership. Document a migration checklist for moving
content; author prose manually instead of broad path replacement.

## Non-goals

Generating all prose from code, validating arbitrary English, a new documentation
framework, changing brand metadata or rewriting historical specifications as current guides.

## User workflow

Before a guide move, inventory supported command/examples/limits and retained
sections. Move by explicit destination/link updates, run structural and semantic
checks, then review the rendered Markdown and exact changed prose. A mismatch
names its guide and expected public contract; the author corrects it.

## Requirements

- Check nested fence closing by delimiter type/length and disclose unclosed openings.
- Assert selected documented values against public constants or parser behavior.
- Distinguish executable examples from historical/proposed snippets.
- Exercise portable enrollment/status examples in disposable repos, never user source.
- Keep historical PRD/design text intact; it may intentionally describe earlier behavior.

## Acceptance criteria

- **AC1:** Python documentation checking rejects unterminated/mismatched maintained-guide fences with opening line details, correctly handles longer outer fences and ignores fenced examples for prose/link validation.
- **AC2:** An explicit maintained contract table covers run storage location, check timeout bounds, supported command names, evidence dimensions and recovery/frozen-settings promises, comparing values to authoritative code and exercising selected portable examples.
- **AC3:** Mutation tests prove detection of the historically observed wrong path/timeout/field/limit text and truncated setup guidance; unchanged current guides pass without asserting that arbitrary prose truth is automated.
- **AC4:** Documentation moves follow a retained-contract checklist and preserve links, navigation and pinned brand regions. Historical specs are excluded from current-value enforcement and no runtime or user configuration is changed by checks.
- **AC5:** Meaningful documentation tests and both required repository checks pass before fresh review and observed draft-PR delivery, including manual inspection of final rendered examples.

## Constraints and compatibility

Python 3.11+, macOS/Linux, standard-library runtime and setuptools remain required.
Codex is the primary host; Claude follows the same protocol as a compatibility
host. Keep personal paths, task state, logs and receipts outside source. No paid
model API, implicit merge/release, worktree deletion or stale-proof reuse.
Start the implementation branch from `main`; keep the existing frozen checks,
failure budget, review and observed delivery gates. These are specifications,
not implemented features.
Implementation branch: `feature/documentation-contracts`.

## Dependencies

The inspected main already contains proposals 0001–0009 and their implementation.
No other new pair is required. [Matching design](../design/0015-documentation-contracts.md) contains the
build contract. Read it explicitly and include relevant details in the reviewed
private plan; linked content is not implicitly loaded by existing task intake.

## Verification

Copy maintained guides to disposable fixtures and inject each historical failure
class separately. Run portable init/status snippets in disposable repos with
synthetic checks and no network. Compare public constants/parser output with the
maintained contract table, preserving all current documentation tests.

## Risks and open questions

Overly exact prose assertions make harmless edits costly. Validate literal
contracts and section/example presence with clear scope; leave narrative quality
to review. Current-value enforcement excludes historical specs. No open choice.

## Delivery and follow-up

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source` on
the final tree. Obtain fresh plan and code review, then observe a draft PR against
`main` (or an explicitly selected lower stack layer). Report the actual endpoint;
update lifecycle only with evidence. Do not execute other backlog pairs implicitly.
