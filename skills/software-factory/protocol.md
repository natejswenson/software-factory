# Artifact protocol

Write JSON with normal file tools; task text is never shell code. The CLI gives
the exact freshness object in `next.context` or `next.evidence`; copy it intact.
For new runs these objects also include `rules`; preserve it exactly.
Read `factory rules --run ... --json` and give all current rule content to both
reviewers. Rule changes invalidate plan approval, including ignored files.
Historical runs omit `rules`; never add it to their existing receipts.
Object-key order is irrelevant. Produce files in the private run directory.

Plan Markdown states the task, observable criteria, inspected code/instructions,
implementation steps, validation and consequential decisions. Approval applies
to those contents; changing them requires a new plan review.

Plan review (`factory plan-review --run ... --file ...`):

```json
{
  "reviewer": "native agent identity",
  "context": { "base": "copy", "criteria": "copy", "config": "copy", "plan": "copy" },
  "verdict": "pass",
  "findings": []
}
```

Code review (`factory review --run ... --file ...`):

```json
{
  "reviewer": "native agent identity",
  "evidence": { "base": "copy", "criteria": "copy", "config": "copy", "plan": "copy", "head": "copy", "tree": "copy", "paths": [] },
  "verdict": "pass",
  "findings": [],
  "criteria": [
    { "id": "AC1", "passed": true, "evidence": "Specific check or inspected behavior and its result" }
  ]
}
```

Include every criterion exactly once. Findings are unresolved observations:

```json
{ "severity": "major", "location": "software_factory/example.py:42", "issue": "Concrete failure and why it matters" }
```

Severity is `blocking`, `major`, or `minor`. A passing review cannot contain
blocking/major findings or a failed criterion. Use `verdict: fail` for repairs;
do not erase a finding to manufacture a pass. Rejected plan/code reviews and
failed verification each consume one of three repair attempts by default.
Infrastructure failures do not consume that budget. Historical artifacts remain
available after repairs. Hashes establish freshness, not reviewer truth.

## PRD task text

A ready PRD uses the existing task-file interface: freeze the complete text and
supply every full acceptance criterion explicitly, in order, retaining labels.
Linked files are not recursively frozen; incorporate required constraints into
self-contained requirements and necessary design details into the reviewed plan.
Source edits do not replace saved text/criteria; resume the same run. Human PRD
lifecycle labels do not change gates or these exact review schemas. No automatic
criteria parser, approval, commit or backlog execution is implied.

## Reviewer context preparation

Use `review-context --run <run> --stage plan|code --json` to assemble complete exact
inputs; it does not submit or approve them. Code requires current passing checks.
Repeat `--instructions-file` and `--supplement` for explicit private UTF-8 data.
Supply current conversation/host directions separately; explicit user/host directions
outrank repository guidance and input prose never authorizes gate bypass/external
acts. Supplements are attributed observations, not extra checks or certified proof.
Root/scoped instructions, full plan/task/rules/criteria, frozen config and code diff/
verification remain complete and bounded. Reject oversized/changing required inputs;
never silently drop them. Bundles stay private and no model/network call occurs.
A native reviewer still writes its genuine artifact using the unchanged schemas
above, copying exact context/evidence. Capture reserves nothing; submission rechecks
freshness. A bundle cannot establish reviewer independence or prose truth.

## Optional PR description

Private JSON input permits version (1), evidence (complete current verified object),
title (trimmed single line, 1–150 characters, no controls), summary (1–5 nonempty
paragraph strings), and optional compatibility/risks strings. Unknown/duplicate keys,
unsafe files, malformed UTF-8/JSON and inputs beyond 16 KiB are rejected. Literal text
is preserved. `pr-description --run ... --file ...` returns a full preview with private
paths/hash; review its prose and generated all-criteria/check sections explicitly.
Custom UTF-8 rendering is capped at 48 KiB before writes or publication, without truncation.

Submission does not change these review schemas, evidence keys, verification or budget.
Code review may precede or follow submission, but must still pass for delivery. Provide
the preview as an attributed native-review supplement; freshness cannot certify prose.
Presentation and final body hashes are immutable after delivery selection; missing or
changed artifacts must not fall back. Existing matching drafts preserve their metadata,
with reconciliation distinguished from a successful create that applied this input.
