# 0008 — Submit and deliver concise PR descriptions

Status: ready for factory planning; implementation pending.
Requirement: [PRD 0008](../prd/0008-pull-request-descriptions.md).
Baseline: `447c49f0c09ca7a9d07a7bc92d1f4f3b35960fd2`; revalidate selected base.

## Evidence and approach

`delivery._draft_pr` currently renders `## Task` with the full request, criteria
and passed check names; title is the first task line. The saved rules run includes
a separately authored summary adding concrete behavior and compatibility.
Let the current agent author presentation prose; the engine validates its shape
and freshness and generates factual receipt sections. No summarizing model runs
inside the CLI and no default/historical delivery behavior changes.

## Input, submission and preview

```sh
factory pr-description --run /path/to/run \
  --file /path/to/private/pr-description-input.json --json
```

Input object permits only `version`, `evidence`, `title`, `summary`,
`compatibility` and `risks`. Version is 1. Evidence is copied intact from the
current verified `next.evidence`/status evidence. Title is a trimmed single-line
string of 1–150 characters; reject newlines/control characters and empty titles.
Summary is an array of 1–5 nonempty paragraphs. Optional compatibility/risks are
strings; omit their sections when absent rather than invent concerns. Reject
unknown/duplicate JSON keys, invalid UTF-8, non-regular/symlink input and files
over 16 KiB. Do not alter literal Markdown, Unicode, backticks or `$()` text.

Under the normal run transaction, require an active prepared run with current
passing verification using `check_verified`. Compare input evidence exactly via
existing `same_evidence`. Refuse submission once commit/delivery intent or an
operation exists, so metadata cannot change during an interrupted publication.
Passing code review may be obtained before or after metadata submission; delivery
still requires it. Submitting metadata does not approve code or reset failures.

Write validated `pr-presentation.json` atomically and render `pr-preview.md` in
the private run directory before saving the optional `prPresentation`
hash/reference and appending `pr-description-submitted`. An identical repeat is
a no-op with the existing result; if only its preview is missing, regenerate that
owned preview without adding a duplicate history event.
Use existing atomic/private file conventions. If an interrupted submission leaves
an unreferenced artifact, a retry validates it and safely replaces only these
factory-owned presentation files; never rewrite task/review/verification receipts.

JSON output includes `version`, `id`, `title`, `presentation`, `previewFile`,
`preview`, `evidenceHash` and `changed`. Human output shows title and full preview.
Invalid/stale input uses existing exit 2; file/infrastructure failures use exit 3.
Presentation input does not change run identity, EVIDENCE_KEYS or review schemas.

## Rendering and truth boundaries

Render a compact summary, optional compatibility/risks, all numbered acceptance
criteria and a verification table from the saved current receipt. Include actual
check names, portable argv (or a private-command pointer), outcome, available
duration and the reviewed tree.
Never turn a skipped, failed or historical result into a passing claim. Preserve
every criterion verbatim. Before delivery the preview references reviewed tree;
after the exact commit is observed, the body names that final commit as today.

For custom descriptions only, cap the rendered UTF-8 body at 48 KiB; reject
oversized rendering with an actionable error before submission/publication. This
is a local product bound, not a claim about GitHub limits. Do not silently
truncate criteria or broaden compatibility claims. Existing default rendering
remains unchanged, so old saved tasks gain no new length restriction.

The summary is attributed agent-authored prose; evidence binding proves freshness,
not prose truth or coverage. Teach the agent to ground it in final behavior and
review the preview. It may be supplied to native reviewers as an explicit
supplement. Do not embed raw logs, private paths, task state or full PRDs in the
custom body. The engine's configured argv may include host paths; custom rendering
must represent checks by name and outcome and include argv only when portable.
If argv contains an absolute host path, omit it with a clear “command retained in
private verification” note rather than publishing that path. The reviewer checks
the actual private command receipt.

## Delivery and retry integration

Before `_commit`, validate any referenced presentation artifact hash and bind its
evidence to the current verified receipt. A stale/missing/changed optional artifact
is an error; do not silently fall back. Record the chosen hash in the existing
commit intent as optional presentation metadata, preserving old intents with no
such field. This selected presentation is immutable for that delivery attempt.

After exact commit observation, render `pr-body.md` with the final commit, then
push/create using existing literal `--title` and `--body-file` arguments. Keep
current remote HEAD, open-draft and named-base checks. Reuse recorded evidence for
the owned commit-recovery exception; do not invalidate descriptions solely
because the engine made its own exact reviewed commit.

On retry validate selected artifact/body hashes before creating. Reconcile the
existing matching PR before another create. If it exists, preserve its metadata:
do not call `gh pr edit`, ready or merge. Report whether the selected presentation
was applied by this create or an existing PR was reconciled. A changed existing
title/body does not authorize overwriting it or make an otherwise correct
head/base draft a code-verification failure. An unmatched/ambiguous PR retains
current delivery failure behavior. Errors stay pending; no local downgrade.

## File changes and sequence

| File | Responsibility |
|---|---|
| `software_factory/pr_description.py` | Input validation, submission and deterministic private/public rendering |
| `software_factory/cli.py` | New command/help and readable/JSON preview |
| `software_factory/delivery.py` | Optional presentation validation, immutable selection and title/body use with retry reconciliation |
| `tests/test_pr_description.py` | Input/preview/freshness/limits and no-input parity |
| `tests/support.py`, `tests/test_lifecycle.py` | Adapter assertions for title/body, uncertain creation and preserved existing metadata |
| Bundled skill/protocol and README/task docs | Agent-authored prose workflow and freshness/truth boundaries |

Start `feature/pull-request-descriptions` from `main`, record every criterion and
review the optional metadata/recovery plan. Add tests before integrating delivery.
Implement rendering/submission, immutable intent and adapter scenarios. Run both
required checks and installed smoke; obtain fresh code review and observe draft
delivery. Keep old no-presentation delivery tests unchanged.

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

## Verification and recovery

Exercise full PRD-like task text, Markdown titles, Unicode, multiline criteria,
portable/nonportable argv, schema/duplicate-key errors, size limits, identical
resubmission, missing/tampered artifacts and edits after verification. Assert
description submission leaves verification/code review/failure count unchanged.
Test no presentation against current exact defaults; local endpoints keep their
normal behavior and need no presentation to complete.

Use local GitHub adapter tests for failed push, uncertain creation, owned commit
recovery, existing metadata preservation, wrong head/base/state and ambiguous PRs.
Mutated selected metadata must never publish silently. Run
`python3 scripts/verify.py tests`, `python3 scripts/verify.py source`, build and
installed smoke. Report actual observed draft URL after real delivery; adapter
results alone are not remote proof. Correct stale metadata before delivery starts;
after it starts, reconcile the immutable attempt or seek explicit direction.
No consequential scope choice remains open.
