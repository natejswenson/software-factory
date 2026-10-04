# 0005 — Produce exact reviewer context bundles

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0005](../prd/0005-review-context-bundles.md).
Baseline: `447c49f0c09ca7a9d07a7bc92d1f4f3b35960fd2`; revalidate selected base.

## Evidence and architecture

The bundled skill/protocol require exact `next.context`/`next.evidence`, full
current rules and complete review context. `engine.context`, `check_verified`,
`task_rules` and `git.snapshot` already provide authoritative values. The migration
run's three manually assembled code-review request files are direct evidence
of repeated assembly work. This feature packages inputs, not reviewer judgment.

## Interface

```sh
factory review-context --run /path/to/run --stage code \
  --instructions-file /path/to/private/host-instructions.md \
  --supplement /path/to/private/installed-smoke-result.md --json
```

`--stage` is required and limited to `plan` or `code`. The two file arguments
repeat. Output is stdout only: JSON for an agent, Markdown for a human. The caller
may save it in the private run directory using ordinary file tools. Do not add
automatic persistence, review submission or delegation to this command.

## Bundle schema and content

JSON has `version: 1`, `id`, `stage`, `worktree`, `task`, `criteria`, `plan`,
`config`, `rules`, `instructions`, `supplements`, `context`, `evidence`,
`verification`, `diff`, `limitations` and `complete: true`.

- `plan` has path, complete UTF-8 content and its existing fingerprint.
- `config` is the frozen run config. `rules` retains the exact `task_rules`
  representation, including content/hash/initial snapshot pointer or the existing
  rules-disabled representation. No synthetic rules key is added to old context.
- Each instruction/supplement has source path, kind, content and SHA-256. Root
  `AGENTS.md` is included if present. For code-stage changed paths, also include
  each existing ancestor `AGENTS.md` inside the worktree, deduplicated and ordered
  from root to deeper scopes. For plan stage, automatically include root only;
  the caller supplies instructions for planned nested scopes explicitly.
- `context` is exact `engine.context` for plan stage; `evidence` is null there.
  Code stage includes exact `check_verified` evidence and matching context.
- `verification` is null for plan stage and the exact current passing receipt
  for code stage. No check logs are included implicitly; supplements are explicit.
- `diff` is null for plan stage; code stage has base/tree IDs, full binary-capable
  Git patch, changed paths and a binary-change flag. Use the frozen base versus
  the current snapshot tree, including nonignored new files and modes/symlinks.

The bundle includes instruction-priority guidance: explicit user/host directions
outrank repository guidance; input prose is data and never authorizes gate bypass
or external actions. It explicitly cannot discover conversation instructions or
prove reviewer independence. Supplied smoke reports remain attributed evidence,
not additional engine checks or truth-certified receipts.

## Freshness, limits and failure behavior

For plan stage require a readable nonempty plan and valid worktree/context. For
code stage require existing current passing verification through `check_verified`.
Generation does not require a previous passing code review. It cannot make a
blocked run writable or extend a failure budget.

Inspect owner/lock before capture; refuse another active owner with the existing
locked error rather than build against moving files. Read before/after context
and, for code, tree/HEAD evidence. Rehash all captured instruction/supplement
files and plan after assembly. Refuse changed inputs with a clear drift error.
Submission still revalidates freshness; successful capture never reserves a tree.

Limit each non-rules input file to 128 KiB, aggregate instructions/supplements
to 1 MiB, the rendered diff to 4 MiB and the full UTF-8 JSON bundle to 8 MiB.
Keep existing rules limits. Reject non-regular final files, symlinks, invalid
UTF-8, absent required files, missing Git objects and over-limit data. These are
explicit product limits, not claims about host/model limits. Never emit a
`complete: true` bundle with truncated required contents. Binary patches remain
complete but are not an assurance that a text reviewer understands binary data.

Use existing CLI invalid/gate/drift error exit 2 and infrastructure exit 3;
blocked runs retain exit 2. Output follows the existing error JSON convention on
failure. Do not emit a partial successful bundle or edit any saved artifacts.

## Exact changes

| File | Responsibility |
|---|---|
| `software_factory/review_context.py` | Collect scoped inputs, construct/validate bundle and readable output |
| `software_factory/cli.py` | Help/dispatch and stage/repeated input arguments |
| `software_factory/git.py` | Reuse literal bounded Git execution; small helper for base-to-tree binary diff if useful |
| `tests/test_review_context.py` | Completeness, exactness, scope, read-only, limit and drift cases |
| Bundled `SKILL.md` and `protocol.md` | Use bundle command to prepare reviewer requests; preserve submission schemas and native review instructions |
| README/current review docs and installed smoke | Usage and installed command/resources checks |

## Execution sequence

Start `feature/review-context-bundles` from `main`, record every criterion and
review the plan. Implement exact-value tests, capture helpers and limits, then
CLI/docs/smoke. Review the complete diff and gates, run both required checks,
obtain fresh code review and observe draft delivery. No dependency on other new
features; document paths follow actual selected base.

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

## Verification and recovery

Use temporary real repos for tracked/ignored/new files, binary edits, modes,
symlinks, nested scopes and frozen-check edits. Assert exact context/evidence and
rules representation against existing helpers. Exercise nonempty/missing plans,
failed/stale checks, missing Git objects, historical rules-disabled runs, live
locks, file limits and mutation during capture. Compare state, receipts, index,
HEAD and source status before/after. A generated bundle must not itself submit
a review; a deliberately stale review must still be rejected by the CLI.

Run `python3 scripts/verify.py tests`, `python3 scripts/verify.py source`, build
and installed smoke. Retry a failed capture after correcting the input or
obtaining fresh checks; do not edit receipts. No paid models, merge/release,
worktree cleanup or unresolved product choice is included.
