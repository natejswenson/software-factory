# 0013 — Design: Start a PRD without copying every criterion

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0013](../prd/0013-prd-intake.md).
Baseline: local `main` at `84f387e`; inspected 2026-10-05, revalidate before execution.

## Problem, evidence and decisions

All nine numbered design runs used long frozen task documents; current start
requires separate literal criterion flags even though PRDs already contain an
acceptance section. Links do not load design context automatically. This is an
observed manual interface cost, not proof that a criterion was lost. E4 in the
[run review](../design/run-review-2026-10-05.md) explains this distinction.

Goal: An agent previews a canonical PRD once, checks exact extracted criteria, and
starts with one PRD argument. Formatting ambiguity produces a clear error before
allocation. Original arbitrary task-file and explicit-criterion intake continues.

Resolved scope: Add `factory prd-check --file PATH [--json]` and `start --prd PATH` for a bounded,
strict Markdown format. Preserve full original task text and extracted criterion
meaning. Do not recursively load links; the agent still reads the matching design.

## Interface and user experience

`prd-check --file /path/to/0013-prd.md --json` emits `version: 1`, `title`,
`status`, `criteria` (id, text, startLine, endLine), `warnings` and `sourceHash`.
`start --prd /path/to/0013-prd.md --repo /path/to/app --base main
--worktree-root /path/to/worktrees --json` calls existing start with the full
original snapshot and ordered extracted text. Mutually exclusive intake arguments
fail before reading configuration or allocating a run. A SHA-256 source hash is
preview metadata, not a new engine evidence key.

## Architecture and implementation contract

Use one bounded regular UTF-8 file read (maximum 128 KiB), rejecting symlinked
input files and changed metadata/bytes during the read. Do not require the file
be inside the target repo; explicit task sources can live elsewhere. Parse fences
using delimiter character/length so inner examples cannot supply real criteria.

Outside fences require exactly one H1 title and one status line before
`## Acceptance criteria`; allow the exact ready value or its existing
semicolon-qualified pending note. That section ends at the next H1/H2 heading. Allow
`- AC1: text` and `- **AC1:** text` labels, contiguous from AC1; strip label and
normalize wrapped prose with single spaces into criterion text. Permit blank
lines between criteria; reject nested lists, headings, tables, code fences or
unlabeled prose within the section. Require nonempty criterion text. Retain exact
full file bytes as task text after UTF-8 decoding; CRLF normalization affects
parsing only. Warn that links are context and not intake.

Preview uses the same parser as start. Preview-to-start file changes create a
new validated snapshot rather than inheriting earlier approval. Reuse existing
StartOptions and duplicate identity on task/criteria; no version-1 state migration.
The template is already canonical; update its instructions without inventing
new ready examples. Native planning still reads instructions and design.

## Exact file responsibilities

| File | Change |
|---|---|
| `software_factory/prd_intake.py` | Bounded snapshot and strict parser |
| `software_factory/cli.py` | prd-check and mutually exclusive --prd intake |
| `tests/test_prd_intake.py; tests/test_lifecycle.py` | Parsing, no allocation, freeze and duplicate tests |
| `software_factory/templates/prd/_template.md; prd/_template.md` | Canonical format instructions |
| `docs/user-guide/tasks-and-recovery.md; docs/reference/commands.md; skills/software-factory/SKILL.md` | Preview, start and explicit design handoff |
| `scripts/smoke_install.py` | Installed parser/PRD intake smoke |

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

Excluded: General Markdown interpretation, model extraction, automatic lifecycle updates,
bulk backlog execution, accepting ambiguous criteria or silently combining intake sources.

Some hand-authored Markdown is deliberately outside the grammar. Provide a
line-specific correction or the existing task-file route with explicit criteria.
Strict format is the resolved product choice; no permissive extraction fallback.

## Implementation sequence

1. Start `feature/prd-intake` from `main`, freeze the complete PRD and every
   criterion, and obtain a reviewed private plan including this design's contract.
2. Inspect current public behavior and existing tests; add meaningful asserting
   cases for the new behavior and identified gaps rather than duplicate fixed bugs.
3. Implement the interface/helpers, preserving existing gates and failure semantics.
4. Update maintained docs/skill guidance where specified; review portable examples
   and privacy. Keep runtime outputs and real ledgers private.
5. Run the selected behavior checks and both full repository checks, obtain a
   fresh code review covering every criterion, then observe draft delivery.

## Acceptance criteria

- **AC1:** PRD preview returns the exact full title, ready status, ordered acceptance text and source line spans for plain/bold AC bullets with wrapped lines, and rejects draft, missing, duplicate, gapped, fenced-only or ambiguous criteria with actionable line errors.
- **AC2:** Start --prd uses one validated UTF-8 snapshot for full frozen task text and every criterion in order, rejects combining task/task-file/issue/criterion sources, and fails before any run/worktree allocation on invalid PRDs.
- **AC3:** Existing task, task-file, issue, explicit criteria and historical resume/duplicate behavior remain unchanged; modifying the original PRD after start cannot change saved requirements and linked documents are never loaded implicitly.
- **AC4:** Preview is read-only, bounded and deterministic; human and version-1 JSON output agree, invalid input exits 2 without a traceback and read infrastructure errors exit 3. Preview itself confers no approval or delivery.
- **AC5:** Meaningful parse, allocation-preservation and frozen-task lifecycle tests plus both required repository checks pass before fresh review and observed draft-PR delivery.

## Verification and review

Use real current PRDs as compatibility samples, plus strict-format synthetic
fixtures for CRLF/wrapping, fences, empty text, label gaps and multiple sections.
Snapshot Git/run inventory on invalid intake. Start a temporary valid PRD, edit
its source, resume and assert frozen criteria/text unchanged.

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
