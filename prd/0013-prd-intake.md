# 0013 — Start a PRD without copying every criterion

Status: ready; proposed feature, implementation pending.
Review date: 2026-10-05. Category: Ease of use and simplicity; output quality. Priority: 2.
Baseline: local `main` at `84f387e`; revalidate the selected base before execution.

## Problem and users

All nine numbered design runs used long frozen task documents; current start
requires separate literal criterion flags even though PRDs already contain an
acceptance section. Links do not load design context automatically. This is an
observed manual interface cost, not proof that a criterion was lost. E4 in the
[run review](../design/run-review-2026-10-05.md) explains this distinction.

## Desired outcome

An agent previews a canonical PRD once, checks exact extracted criteria, and
starts with one PRD argument. Formatting ambiguity produces a clear error before
allocation. Original arbitrary task-file and explicit-criterion intake continues.

## Scope

Add `factory prd-check --file PATH [--json]` and `start --prd PATH` for a bounded,
strict Markdown format. Preserve full original task text and extracted criterion
meaning. Do not recursively load links; the agent still reads the matching design.

## Non-goals

General Markdown interpretation, model extraction, automatic lifecycle updates,
bulk backlog execution, accepting ambiguous criteria or silently combining intake sources.

## User workflow

Author a ready PRD using the existing template, preview exact criteria with
prd-check, then start with --prd plus repo/base/worktree arguments. The planning
agent incorporates the design explicitly. Later source edits cannot alter a saved
run. Draft or ambiguous documents must be corrected before starting.

## Requirements

- Require one top-level title, one status line starting `Status: ready` and one level-two acceptance section.
- Parse contiguous AC1..ACn bullets with wrapped lines, supporting plain and bold AC labels.
- Ignore fenced examples and reject ambiguous nested bullets, repeated sections, gaps or duplicate labels.
- Preview preserves criterion text and source line spans; intake reads one bounded snapshot.
- Retain exact frozen task text, generated AC IDs and normal plan/review/check gates.

## Acceptance criteria

- **AC1:** PRD preview returns the exact full title, ready status, ordered acceptance text and source line spans for plain/bold AC bullets with wrapped lines, and rejects draft, missing, duplicate, gapped, fenced-only or ambiguous criteria with actionable line errors.
- **AC2:** Start --prd uses one validated UTF-8 snapshot for full frozen task text and every criterion in order, rejects combining task/task-file/issue/criterion sources, and fails before any run/worktree allocation on invalid PRDs.
- **AC3:** Existing task, task-file, issue, explicit criteria and historical resume/duplicate behavior remain unchanged; modifying the original PRD after start cannot change saved requirements and linked documents are never loaded implicitly.
- **AC4:** Preview is read-only, bounded and deterministic; human and version-1 JSON output agree, invalid input exits 2 without a traceback and read infrastructure errors exit 3. Preview itself confers no approval or delivery.
- **AC5:** Meaningful parse, allocation-preservation and frozen-task lifecycle tests plus both required repository checks pass before fresh review and observed draft-PR delivery.

## Constraints and compatibility

Python 3.11+, macOS/Linux, standard-library runtime and setuptools remain required.
Codex is the primary host; Claude follows the same protocol as a compatibility
host. Keep personal paths, task state, logs and receipts outside source. No paid
model API, implicit merge/release, worktree deletion or stale-proof reuse.
Start the implementation branch from `main`; keep the existing frozen checks,
failure budget, review and observed delivery gates. These are specifications,
not implemented features.
Implementation branch: `feature/prd-intake`.

## Dependencies

The inspected main already contains proposals 0001–0009 and their implementation.
No other new pair is required. [Matching design](../design/0013-prd-intake.md) contains the
build contract. Read it explicitly and include relevant details in the reviewed
private plan; linked content is not implicitly loaded by existing task intake.

## Verification

Use real current PRDs as compatibility samples, plus strict-format synthetic
fixtures for CRLF/wrapping, fences, empty text, label gaps and multiple sections.
Snapshot Git/run inventory on invalid intake. Start a temporary valid PRD, edit
its source, resume and assert frozen criteria/text unchanged.

## Risks and open questions

Some hand-authored Markdown is deliberately outside the grammar. Provide a
line-specific correction or the existing task-file route with explicit criteria.
Strict format is the resolved product choice; no permissive extraction fallback.

## Delivery and follow-up

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source` on
the final tree. Obtain fresh plan and code review, then observe a draft PR against
`main` (or an explicitly selected lower stack layer). Report the actual endpoint;
update lifecycle only with evidence. Do not execute other backlog pairs implicitly.
