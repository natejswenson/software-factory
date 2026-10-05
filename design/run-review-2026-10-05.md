# Software Factory run review — 2026-10-05

Review scope: efficiency, output quality, and ease of use/simplicity.
Inspected product baseline: local `main` at `84f387e` (plugin structure merge).
The original documentation checkout remains at `447c49f`; new proposals target
main in a separate worktree. This review does not execute backlog features.

## Method and limits

Read all 27 saved run states, their append-order histories, 48 numbered
verification receipts and available plan/code review findings. Repeated copies
of the same finding were deduplicated for interpretation. Inspected current main
source, tests, command/skill protocol and documentation tooling. Private run
files remain in their existing store; the tables below contain concise summaries.

This is the complete local saved-run inventory available at inspection, not a
sample of all users or all agent conversations. The central outcome-history
recall returned `ACTIVITY_UNREADABLE_OR_INVALID`; it was not treated as empty
and was not bypassed. Current scoped recall provided a source-backed Codex-primary
preference consistent with main's plugin/skill direction. No transcript archive,
remote PR/CI refresh, model-token trace or user usability session was inspected.

Counts describe saved evidence at inspection: 23 runs are `done` (15 recorded
draft deliveries and 8 local deliveries); 4 remain unfinished (2 review, 1 plan,
1 implement). A `done` receipt establishes the recorded endpoint, not present
remote merge/release state or freshness of surviving worktrees. Multiple active
and delivered attempts may represent the same work; do not infer supersession.

Recorded test-check durations span about 21–194 seconds. The earliest summary
failure intentionally established missing behavior. Repeated passing checks
followed legitimate edits/reviews; this review does not classify them as waste.
Elapsed test time is not task wall time, model latency, token cost or CI time.

## Run inventory

| Saved task | Saved phase | Verification attempts | Recorded outcome |
|---|---|---|---|
| Summary command | done | 2 | [Recorded draft PR #2](https://github.com/natejswenson/software-factory/pull/2) |
| Repository rules | done | 2 | [Recorded draft PR #4](https://github.com/natejswenson/software-factory/pull/4) |
| Migrate Software Factory completely from Node to clean Python | done | 4 | [Recorded draft PR #6](https://github.com/natejswenson/software-factory/pull/6) |
| Original automatic merge/release attempt | review | 1 | No completed delivery receipt |
| Bootstrap tested CI, automatic ready PR merges into main and GitHub patch release workflows | done | 1 | [Recorded draft PR #7](https://github.com/natejswenson/software-factory/pull/7) |
| Strengthen release checksum readback regression coverage and validate the automatic main delivery flow | plan | 0 | No completed delivery receipt |
| Strengthen release checksum readback regression coverage and validate the automatic main delivery flow | done | 1 | [Recorded draft PR #8](https://github.com/natejswenson/software-factory/pull/8) |
| Keep GitHub Latest release selection monotonic when recovering older drafts | done | 1 | [Recorded draft PR #9](https://github.com/natejswenson/software-factory/pull/9) |
| 0001 — Clean up the repository structure | done | 2 | [Recorded draft PR #10](https://github.com/natejswenson/software-factory/pull/10) |
| 0002 — Add PRD folder setup to Software Factory | done | 2 | [Recorded draft PR #11](https://github.com/natejswenson/software-factory/pull/11) |
| 0003 — Implement read-only task preflight | done | 2 | [Recorded draft PR #12](https://github.com/natejswenson/software-factory/pull/12) |
| 0004 — Explain stale and missing task evidence | done | 3 | [Recorded draft PR #13](https://github.com/natejswenson/software-factory/pull/13) |
| 0005 — Produce exact reviewer context bundles | done | 3 | [Recorded draft PR #14](https://github.com/natejswenson/software-factory/pull/14) |
| 0006 — Observe active checks and read bounded logs | done | 3 | [Recorded draft PR #15](https://github.com/natejswenson/software-factory/pull/15) |
| 0007 — Discover runs and inspect their recorded history | done | 4 | [Recorded draft PR #16](https://github.com/natejswenson/software-factory/pull/16) |
| 0008 — Submit and deliver concise PR descriptions | done | 3 | [Recorded draft PR #17](https://github.com/natejswenson/software-factory/pull/17) |
| Integrate reviewed PR 11 onto merged main | done | 2 | Recorded local commit |
| Repair observed macOS CI regressions before merging PR12 | review | 1 | No completed delivery receipt |
| Repair actual macOS group cleanup failure before PR11 merge | implement | 1 | No completed delivery receipt |
| Repair actual macOS group cleanup failure before PR11 merge | done | 2 | Recorded local commit |
| Integrate reviewed PR17 with the reviewed cleanup repair | done | 1 | Recorded local commit |
| Prepare PR12 for normal protected merge | done | 1 | Recorded local commit |
| Integrate reviewed command cleanup into existing PR15 | done | 1 | Recorded local commit |
| Integrate reviewed command cleanup into existing PR17 | done | 1 | Recorded local commit |
| Resolve GitHub PR15 merge ancestry without changing reviewed source | done | 1 | Recorded local commit |
| Complete PR17 with actual main ancestry and unchanged final feature source | done | 1 | Recorded local commit |
| 0009 — Simplify Software Factory into one installable plugin | done | 2 | [Recorded draft PR #18](https://github.com/natejswenson/software-factory/pull/18) |

## Findings and proposed work

| Finding | Category | Priority | PRD | Design | Confidence |
|---|---|---|---|---|---|
| E1: Integration readiness is separate from draft delivery | Efficiency, quality | 1 | [0010](../prd/0010-integration-readiness.md) | [0010](0010-integration-readiness.md) | High for repeated integration; benefit inferred |
| E2: Development needs faster feedback and per-test timing | Efficiency | 2 | [0011](../prd/0011-focused-feedback.md) | [0011](0011-focused-feedback.md) | High for observed durations; speedup unmeasured |
| E3: Passing suites missed recurring boundary classes | Quality, efficiency | 1 | [0012](../prd/0012-boundary-test-contracts.md) | [0012](0012-boundary-test-contracts.md) | High for recorded review repros |
| E4: PRD intake repeats criterion text manually | Simplicity, quality | 2 | [0013](../prd/0013-prd-intake.md) | [0013](0013-prd-intake.md) | High for interface; omission not observed |
| E5: Selecting/resuming related runs needs clearer guidance | Simplicity, efficiency | 1 | [0014](../prd/0014-guided-resume.md) | [0014](0014-guided-resume.md) | High for overlapping attempts; UX benefit inferred |
| E6: Documentation checks need selected semantic contracts | Quality, simplicity | 1 | [0015](../prd/0015-documentation-contracts.md) | [0015](0015-documentation-contracts.md) | High for recorded corruption findings |

### E1 — Integration readiness

Seven completed local integration tasks prepared PR12, integrated PR11, repaired
PR15 cleanup/ancestry, and integrated PR17 cleanup/ancestry. This count excludes
the completed macOS cleanup repair task. One PR15 plan review independently
reproduced a source-identical pending merge being skipped by `_commit`, leaving
`MERGE_HEAD` and returning the previous head. The finished task used a corrected
approach; this review does not claim the old plan is current behavior.

Current `delivery.py` binds the frozen reviewed task to a commit/open draft.
It is not a general later-main integration engine. `engine` and `git` retain
frozen-base evidence. A local read-only integration report would expose target
ancestry and pending operations before another manual repair. It deliberately
does not add automatic merging or relax full checks for source-identical changes.

Success measure: exact target/head ancestry and pending-operation reporting on
fixtures; follow-up compare separately recorded integration tasks per comparable
feature. A reduction target needs future matched data, not an invented baseline.

### E2 — Focused development feedback

Python migration recorded four passing test checks at approximately 56, 58, 58
and 63 seconds. PR-description work recorded three at 158–160 seconds; plugin
structure recorded two at 194 and 182 seconds. These suites differed materially.
Current `scripts/verify.py` discovers the full suite and has no dedicated per-test
profiler or focused selection mode. Full rechecks remain necessary after edits.

Provide exact-ID feedback plus timing, then keep full frozen verification for
delivery. Measure same-tree full/focused samples before claiming a speedup.
No parallel execution, caching or check-budget change is proposed.

Success measure: selected tests only, honest timing/outcomes, lower measured
latency for a chosen repair selection, and unchanged full-gate behavior.

### E3 — Boundary test quality

Passing verification preceded review repros of host/PID confusion in diagnostics,
symlinked ancestor instructions in bundles, an oversized PID in progress,
recursive/overflow data and error exits in history, and attached/double-slash
private paths in PR descriptions. macOS cleanup repair reviews additionally
reproduced nested-signal and duplicate-terminal-kill races. These findings are
historical, with regressions/fixes or an unfinished attempt recorded separately.

Review is valuable and must remain. Audit current regressions first, then use a
small applicable contract map so new public surfaces exercise the same risk
classes earlier. A mapped test must assert behavior; a cited test name or test
count does not establish correctness. Do not add blanket review stages.

Success measure: historical classes stay covered, real CLI faults remain bounded
and read-only, and future substantive post-verification findings are categorized
for comparison. No first-pass review-rate improvement is yet measured.

### E4 — PRD intake simplicity

Eight numbered design runs (0001–0008) and plugin design 0009 used full design
text as tasks. The current CLI accepts task/task-file/issue plus explicit criteria;
the skill instructs agents to copy every criterion separately and load designs
manually. There is no recorded proof of omission. The opportunity comes from
observed interface duplication, not an invented incident.

Strict PRD preview and `start --prd` can freeze one snapshot and exact criteria,
with line-specific errors. Original task-file intake stays available. Links remain
explicit context, rather than creating an implicit recursive instruction loader.

Success measure: one-file intake yields identical full criteria, refuses ambiguous
format before allocation, and preserves frozen requirements after source edits.

### E5 — Guided selection and recovery

The older automation run remains in review even though main contains later
automation; a checksum task remains at plan alongside a delivered checksum task.
Two macOS repair attempts also remain unfinished. This is not proof that they
are obsolete or safe to close. Most delivered worktrees are now detached, so
recorded phase alone cannot promise resumable ownership.

Current `history.py`, `summary.py`, diagnostics and progress expose useful pieces,
while the skill still asks agents to discover and resume using separate commands.
Compose a read-only guide with unique prefix selection, candidate relations,
current availability and one literal next-command recommendation. Do not add an
ambient current-task pointer or automatically resume/recover/extend anything.

Success measure: exact selection or explicit ambiguity, correct next guidance
across lifecycle cases, and no fabricated merged/obsolete status. Later UX
validation can measure command count and selection errors on scripted scenarios.

### E6 — Documentation meaning

Cleanup review found an unterminated outer fence and missing configuration/rules
contracts in the setup guide. Plugin review found four inserted path prefixes
that corrupted ordinary parenthetical facts. They were reviewed and repaired.
Current `scripts/documentation.py` checks links, headings/navigation and pinned
branding; tests compare selected rules/history constants. It does not generally
reject an unclosed fence or verify all selected semantic guide contracts.

Extend the existing Python checker with fence balance, a small public-contract
table and damaged-guide regression fixtures. Preserve prose ownership and branding;
exclude historical specifications from current-value enforcement.

Success measure: each observed corruption class fails a damaged fixture check,
current guides pass, and reviewers still inspect the final rendered examples.

## Priority and boundaries

Start with 0010 and 0014 to clarify integration/resume decisions; implement 0012
and 0015 to reduce repeated review-discovered errors. Add 0011 and 0013 for
shorter development/intake flows. All six are independent against inspected main;
priorities express expected value, not measured ROI or an automatically started queue.

Earlier proposals 0003–0008 and plugin structure 0009 are present at local main.
Keep their historical drafting text, with index notes identifying the inspected
implementation baseline. This review creates six new pairs rather than repeating
preflight, explain, bundles, progress, history or PR descriptions as missing features.

Excluded for lack of evidence or authority: fewer mandatory final checks, removing
independent review, automated closing of old runs, deleting worktrees, automatic
stack rebasing, new paid models or a browser UI. A command guide fits the current
agent/CLI product; no GUI usability claims were established by this review.
