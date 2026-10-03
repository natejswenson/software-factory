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
