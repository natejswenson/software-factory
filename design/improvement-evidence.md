# Evidence behind the next six improvements

Inspected baseline: `447c49f0c09ca7a9d07a7bc92d1f4f3b35960fd2` and its current
Python source, tests, documentation and Git-common-dir factory runs. Inspection
occurred on 2026-10-03, America/Chicago. This document contains concise findings,
not copies of private run records.

## Saved runs inspected

| Run/task | Direct local observations | What this establishes |
|---|---|---|
| Summary command; saved delivery for PR #2 | One failed verification followed by a passing second attempt; first log contains `Unknown command: summary`; source check was skipped after the first failure; a separate fresh-process resume receipt exists | A real failure/repair/resume workflow. The initial failure was intentional behavioral proof, not evidence of a production regression |
| Repository rules; saved delivery for PR #4 | Two plan submissions/reviews and two passing verifications; tests took about 50 and 51 seconds; both an engine-generated `pr-body.md` and a separately authored `pr-summary.md` exist | Repeated fresh evidence and manually improved presentation were part of an actual task; no claim that the second verification was unnecessary |
| Python migration; saved delivery for PR #6 | Ledger branch rename, renewed reviews, four passing verification receipts; test counts progressed from 58 to 59 to 60, taking about 56–63 seconds; three manually assembled code-review request files exist | Context assembly, review and re-verification were repeated during legitimate edits; all four final-check records remain distinct |
| Automatic merge/release task | Saved phase was `implement` at inspection, with an initial failed plan review and a later passing revised plan review; findings concerned ready-for-review triggering and release coordination/recovery | This is active work, not a delivered feature. Avoid proposing a second CI/merge/release implementation that duplicates it |

Delivery references above identify saved local receipts. They do not establish
the present remote PR state. Central activity history also reported earlier
draft deliveries and later merges; that history was contextual evidence rather
than authority or a substitute for local receipt inspection.

## Selected improvements and their evidence

| Pair | Observed code/workflow gap | Proposed benefit | Evidence type |
|---|---|---|---|
| 0003 — Task preflight | `engine.start` validates rules/base, but worktree path/branch errors are encountered around allocation; GitHub prerequisites are checked late in delivery; no readiness command exists | Discover locally observable blockers before allocating a run, without changing the authoritative gates | Source observation; operational benefit inferred |
| 0004 — Evidence diagnostics | `next_action` can say “Evidence is missing or files changed”; summary tests intentionally retain historical `passed` while `next` requires verification; rules/migration tasks refreshed evidence repeatedly | Explain which proof is absent, failed or stale and which files changed, while preserving all required rechecks | Source/tests plus real repeated-evidence workflow |
| 0005 — Review context bundles | Migration has three hand-built reviewer requests; active automation has initial/revised plan requests; skill requires exact evidence, full rules, task, criteria and diff | Produce a consistent read-only bundle so agents spend less effort assembling reviewer inputs | Direct run artifacts plus source/protocol |
| 0006 — Verification progress and logs | Checks already record `durationMs`, bounded logs and results, but `verify` saves its final results only after the loop; summary under another process's lock shows wait, not current check; real checks lasted around a minute | Show the active check and expose bounded log tails without rerunning it | Source and measured saved receipts |
| 0007 — Run history and discovery | CLI `list` exposes only id/task/phase/endpoint/run; `store.list_runs` reads every state with one failing comprehension; four runs include stacked bases, repairs, rename and active work | Find the right run, inspect its sequence and keep healthy records visible if another ledger is unreadable | Source and actual multi-run history; corruption handling is preventive, not an observed incident |
| 0008 — PR descriptions | `_draft_pr` copies the whole frozen task into the body and uses its first line as title; the rules run has a separately authored summary with behavior/compatibility context | Let the current agent supply concise, evidence-bound reviewer prose rather than requiring a later manual rewrite | Source and direct manually authored artifact |

## Scope boundaries

The six pairs do not duplicate repository cleanup, PRD folder generation or the
active CI/automatic merge/release work. They do not remove verification, reuse
stale reviews, change failure budgets, execute paid models, implicitly merge or
release, or delete worktrees. Each can run independently from the current Python
base; cleanup affects documentation destinations only.

Start with 0003–0005 because they reduce setup and review mistakes. Then add
0006–0008 for visibility and delivery quality. This order is a recommendation,
not a hard dependency or a requirement to execute any feature now.

All runtime evidence stays private. The matching designs reference current
functions and test files so future agents can revalidate observations against
their actual selected base. Where behavior was not observed, the documents label
it as a proposed or inferred improvement.
