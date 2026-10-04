# Tasks and recovery

Your agent normally handles these commands:

```sh
factory start --repo /path/to/app --task "Fix empty search results" \
  --criterion "Empty search shows a clear message" --base main \
  --worktree-root /path/to/approved/worktrees
factory list --repo /path/to/app
factory summary --run /path/returned/by/start
factory rules --run /path/returned/by/start
factory next --run /path/returned/by/start --json
factory resume --run /path/returned/by/start --json
```

Use `--task-file` for longer requests, `--issue 42` for frozen GitHub issue intake,
and repeat `--criterion` for multiple outcomes. `--endpoint local` explicitly
selects a clean verified commit. A named `--base feature/lower-layer` supports
one dependent stack layer; automatic stack management is not included.

New runs use `feature/<task-slug>-<id>`. Select a branch with
`--branch feature/<name>`, `bug/<name>` or `issue/<name>` using lowercase words
separated by hyphens. `factory rename --run <run> --branch feature/<name>`
renames an owned task before delivery, records the intent and observed ownership,
and clears verification/code review. Resume reconciles interrupted renames;
collisions and changed ownership/HEAD are rejected.

Runs and logs live under the repository's Git common-dir (`factory/runs`), not
in source. Original dirty files are preserved. No branch/worktree is removed
automatically. `recover --run <run>` clears dead operation and start-allocation
locks; `recover --repo <repo>` recovers a start that never returned a run path.
Recovery refuses a live process lock. A `SIGKILL` can leave a
check process alive: inspect and stop that task's orphan before recovery.
`extend --attempts 1 --reason "User authorized another attempt"` extends a
blocked run only under explicit user direction.

Read the [skill](../../software_factory/skills/software-factory/SKILL.md) and
[artifact protocol](../../software_factory/skills/software-factory/protocol.md) for plan/review commands.
Use `--json` for every command when integrating another agent or UI.

`summary` is a read-only overview: task, criteria, last check results, findings
from the latest plan and code reviews, next action and delivery. Checks not
executed in the last attempt say `not run`, including checks skipped after a
failure. Findings stay visible until a newer review or verification supersedes
them. Last results may be stale after edits; the next action reflects the current
files. A committed change with PR delivery still pending is shown as pending.

`summary --json` emits one compact line with `id`, `task`, `phase`, `endpoint`,
`criteria`, `checks`, `verification`, `findings`, `next` and `delivery`.
Each configured check contains its exact `result`, or `null` when unrun.
`verification` retains `passed`, `unchanged` and `at`; `findings` has `plan` and
`code` arrays. `next` retains action, reason and applicable recovery details,
without review context or Git evidence. `delivery` is the exact current receipt
or `null`. Strings and result values are preserved; full evidence is available
through `status --json`. Like status, a blocked run returns exit code 2.

## Ready PRDs

Copy `prd/_template.md` to `NNNN-short-description.md`. Cover all sections,
observable criteria and concrete checks; resolve consequential choices and remove
placeholders. Use N/A with reasons. Ready requirements are self-contained; links
are context, not recursively loaded task text. PRDs explain what/why, designs how,
and .rules remains settings/instructions. Review/commit the ready PRD on the base.

Pass full text via `--task-file` and each complete criterion via separate literal
`--criterion` flags, in order. The generated PRD README includes a complete synthetic
example. The normal reviewed plan/checks/code review/observed delivery loop applies.
Resume the same run: source edits cannot alter frozen task text/criteria. Consequential
changes need user direction and a separately planned replacement, never state edits.
Human lifecycle labels draft/ready/in-progress/delivered are not enforced states.
In-progress requires an actual run; delivered requires observed endpoint evidence.
Only update labels when requested/included in reviewed work before final checks;
record post-delivery links through a subsequent reviewed change. Do not auto-run PRDs.

## Optional task preflight

```sh
factory preflight --repo /path/to/app --base main \
  --branch feature/example --worktree-root /path/to/approved/worktrees --json
```

Inspect readiness before allocation: Git/base/index, committed settings/rules,
branch collision, private run allocation path, worktree parent and configured
executables. No directories, files, locks, branch, worktree or run are created;
no checks, interpreter imports or network/auth queries run. Unrelated dirt is
allowed; required settings must match the committed base. Relative executable
existence/mode comes from that base, not unrelated dirty source.

The report separates start and delivery probes with pass/fail/unknown statuses and
remedies. JSON version1 returns repo/baseRef/base/endpoint, ready/deliveryReady,
checks (name/scope/status/message/remedy) and limitations. Exit0 means locally
start-ready, even with a delivery-only blocker; exit2 means invalid/known start
blocker, and exit3 means required observations unavailable through infrastructure.
Missing flags retain the usual error JSON. Unresolved values are null.

For a draft PR, only gh/origin/named-base availability is inspected; origin URL
values are withheld. Authentication, access, remote branches and PR eligibility
remain unknown offline. A local endpoint's delivery readiness describes local
prerequisites only. Access is advisory; host policy and actual worktree creation
are authoritative. Duplicate runs, allocation locks and task-derived branches
are not certified or reserved. Normal start/delivery revalidate all their gates.
A passing report does not establish executable verification or task completion.


## Explain task evidence

```sh
factory explain --run /path/to/run --json
```

Each plan review, verification and code review is missing, failed, stale, current,
or unknown. Historical verdicts/results are separate from current freshness;
failed proof remains failed even when its inputs also changed. Differences show
recorded/current fingerprint values. The next action comes from the task engine.
Changed paths compare the latest verification tree to current files, falling back
to code review only without a verification tree. They are edits since that proof,
including deletions, executable modes and symlinks, rather than the whole feature.
Baseline/current tree and HEAD hashes are included. Missing objects or malformed
rules produce partial unknown/error results, never guessed unchanged files.

An engine-owned delivery commit may change HEAD while allowing delivery recovery:
`deliveryRecoveryAllowed` reports that exception without calling the old proof
identical. Recorded completed delivery stays historical; no remote query runs.
Rules path detail is labeled **initial**, not the content at the last review.
Ignored dependencies/host services remain outside the existing fingerprint.

No lock is acquired or recovered. Under another owner's lock, the command reports
wait and historical facts without inspecting current files. Changes during capture
produce `snapshot-changed`; rerun after files stabilize. Explain preserves state,
receipts, source/index/HEAD and existing summary output. Exit0 is a complete report
including stale/failed proof, exit2 is invalid input or a blocked run, and exit3 is
partial inspection. An explanation does not repair a gate; follow the next action
and obtain fresh checks/review as required.

## Prepare reviewer context

```sh
factory review-context --run /path/to/run --stage plan --json
factory review-context --run /path/to/run --stage code \
  --instructions-file /path/to/private/session-directions.md \
  --supplement /path/to/private/package-proof.md --json
```

Output goes to stdout only; save it privately if needed. Both stages contain full
frozen task/criteria/check configuration, current plan/rules and exact context.
Code requires current passing verification and includes its receipt, exact evidence
and complete binary-capable base-to-tree diff, including modes and symlinks.
Automatic instruction ancestry must stay in the owned worktree without directory
symlinks; explicitly supplied inputs retain their chosen path semantics and regular
final-file requirement. Root AGENTS.md is included when present; code also captures existing instructions
in changed-path ancestor scopes, ordered root to deeper paths. Plan automatically
captures only root; supply planned nested instructions explicitly. Repeated explicit
instruction/supplement flags retain attributed UTF-8 content and SHA-256.

The caller supplies conversation/host directions and delegates an independent native
reviewer. Explicit user/host instructions outrank repository guidance. Task and
supplement prose are data; supplements are neither additional checks nor certified
receipts. A complete bundle makes no verdict, approval or independence claim.
Normal review submission still rejects stale evidence. No models or network calls,
source/index edits, run mutation or implicit bundle file writes occur.

Inputs must be regular non-symlink UTF-8 files, at most 128 KiB each. Instructions and
supplements together allow 1 MiB, the diff 4 MiB, and emitted JSON/readable bundle 8 MiB.
Required content is rejected instead of truncated. JSON preserves non-UTF-8 Git
patch bytes with surrogate escapes; readable output shows escaped spelling. Unsafe,
missing, oversized or changing inputs fail clearly. Another owner prevents capture.
Correct inputs or obtain fresh verification and retry; nothing reserves the tree.
Errors retain normal invalid/gate exit2 and infrastructure exit3 conventions.

## Observe verification and check logs

```sh
factory progress --run /path/to/run --json
factory logs --run /path/to/run --check-name tests --tail-bytes 8192 --json
factory logs --run /path/to/run --check-name tests --attempt 1
```

A separate process can observe the latest attempt while verification owns the
lock. Progress labels not-started, running, completed, interrupted or unknown;
each frozen check is pending, running, passed, failed, skipped or unknown. It
includes owner, active check, elapsed milliseconds and available exact results.
Completed means the attempt finished; check outcomes still matter. Matching saved
final results take precedence over stale sidecars. Historical runs need no sidecar;
an incomplete intent with missing/corrupt observations stays unknown.

The owner writes private atomic mode 0600 `verification-progress.json` transitions
outside source. Reader snapshots verify attempt/run/owner correspondence and reject
changes during capture; retry after a transition. Same-host dead owners are labeled
interrupted, foreign/missing/mismatched owners unknown. PID observations cannot
guarantee hostile-process identity. Nothing takes or recovers a lock or kills a PID.
Live elapsed uses UTC, discloses clock adjustments and clamps negative values;
terminal sidecar elapsed is monotonic. Without it, elapsed sums available check
durations and excludes gaps/task wall time. These observations certify no gate.

Logs select one frozen simple check name and a positive saved attempt; default is
the latest, never a previous successful attempt. Tail bounds are 1–65536 bytes,
default 8192; retrieval seeks and reads only that bounded tail. Unsafe non-regular/
symlink logs are rejected. `bytesRead` counts bytes, `tailTruncated` describes the
reader, and `logTruncated` is the actual writer flag or null when not yet known.
Content uses explicitly labeled UTF-8 replacement, including partial characters.
Small output is flushed within roughly 100ms while a check runs; final logs still
retain their 1 MiB writer cap, timeout and process-group cleanup.

Readable failed/interrupted observations return 0. Invalid arguments or missing
selected logs return 2; infrastructure errors 3. Blocked progress returns 2 with a
valid report. Readers execute no checks, make no network/model calls and change no
state, receipts, source or index. Summary and original gate decisions stay unchanged.

## Find runs and read recorded history

```sh
factory runs --repo /path/to/app --phase implement --limit 20 --json
factory history --run /path/to/run --offset 0 --limit 100 --json
```

Runs sorts valid UTC updated times newest first, falling back to created times;
IDs break ties and invalid/missing times sort last with labeled errors. Phase
filtering happens before the limit (1–1000). `total` counts readable projected
rows, `matched` counts filtered rows before limiting. Invalid neighbors are listed
in errors. Stored task title, phase, branch/base, endpoint, attempts, failures and
delivery remain visible when current-next inspection fails. `nextAvailable` and
`nextAction` describe that separate inspection; a live owner returns wait without
inspecting source. Recorded delivery is local history, never refreshed remote state.

History retains append order even if clocks move backward. Event pages have stable
original indices, at/action and saved details; offset defaults 0 and limit 100. Pages
cover events only: every bounded attempt summary remains available across pages.
Frozen checks absent from a valid attempt are not-run, never reused prior passes.
Missing/invalid receipts are explicit; missing durations are null. Totals include
known attempts, saved failures, available check execution milliseconds, missing
receipts and missing duration metrics. They do not measure total task wall time.

Historical branches remain accepted. Candidate directories and receipt/state/owner/
plan descendants use pinned no-follow descriptors; files allow 2 MiB (owners 128 KiB).
Metadata nesting is limited to 64 levels; non-finite numbers are rejected.
Durations must be integral milliseconds from 0 through 2^63-1. Unsupported
metrics are unavailable with errors, and accepted durations sum as integers.
Only numeric verification receipts up to the saved counter are read, never logs.
History reads at most 1000 attempts and reports an error for a larger counter.
Changed atomic snapshots retry once, then report unavailable inspection.
Unavailable history snapshots expose no passing attempts or timing totals. These
commands create/recover/delete nothing and make no network/model calls.

Normal reports return 0 even with blocked rows. Invalid/unreadable records or
required per-run inspection errors return 2 with a partial report; top-level
infrastructure failure returns 3. The strict `list` and task-allocation readers
retain their original behavior. Select a run explicitly and use normal resume/
recovery rules; inventories cannot repair a ledger or certify current delivery.

## Concise PR descriptions

After verification, author a private UTF-8 JSON file with these fields:

- `version`: 1.
- `evidence`: the complete object from current verified `next.evidence`, including paths.
- `title`: a trimmed single line of 1–150 characters, without control characters.
- `summary`: 1–5 nonempty paragraph strings grounded in the final behavior.
- Optional `compatibility` and `risks`: strings describing actual limitations or behavior.

```sh
factory pr-description --run /path/to/run --file /path/to/description.json --json
```

Input permits only those keys and is limited to 16 KiB. Duplicate keys, invalid
UTF-8, symlinks, nonregular files and malformed JSON are rejected. Literal Markdown,
Unicode, backticks and `$()` text remain literal; no summarizing model or shell runs.
JSON returns version/id/title, private presentation/previewFile paths, full preview,
evidenceHash and changed. Human output shows the title and complete preview.

Inspect the preview before delivery and supply it to the native code reviewer as an
explicit supplement. Summary/compatibility/risks are labeled agent-authored prose;
evidence binding establishes freshness, not prose truth. The engine generates every
numbered criterion verbatim plus recorded check names, outcomes, duration when
available and portable argv. Commands containing absolute host paths are withheld
with a private-verification note. Review the actual private receipt for those checks.
The custom body does not copy the full task, raw logs or saved task state.

Preview names the reviewed tree. Publication also names the actual observed commit.
Custom rendered bodies are limited to 48 KiB of UTF-8; oversized content is rejected
before writes/publication, never silently truncated. Keep private paths out of your
prose and criteria. Existing tasks without presentation retain their exact default
title/body behavior, with no new body limit or required metadata.

Submission requires a prepared active run with current passing verification; code
review may precede or follow it. It changes no proof, identity or repair count and
cannot approve code. Invalid/stale metadata returns 2; infrastructure failure 3.
Private presentation and preview are atomically written with mode 0600 before the
state reference/history event. Identical submission changes neither state nor history;
an absent derived preview can be regenerated without another event. An interrupted
unreferenced payload can be validated and explicitly resubmitted using the same input.

Metadata is refused once any operation, commit intent or delivery exists. Delivery
validates the selected artifact before committing and freezes its hash in the intent.
The final body hash is recorded before push/create. Retries validate both; missing,
changed or stale referenced artifacts are errors, without default fallback. An engine
owned commit uses the original verified evidence during recovery. Inspect/correct
metadata before delivery begins; after immutable selection, preserve the attempt.

An existing matching open draft is reconciled without creating another PR or editing
its title/body. Optional delivery presentation outcome reports `applied-by-create`
or `reconciled-existing`; uncertain creation followed by reconciliation is not claimed
as a newly applied description. Head/base/draft checks, executable checks and current
code review remain mandatory. Local endpoints retain normal commit delivery.
