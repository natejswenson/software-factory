# Behavioral coverage

Run `python3 scripts/verify.py tests` for real temporary Git/worktree and process
integration tests. Reviews in fixtures are explicitly synthetic.

The table maps all 46 tests from the Node implementation at base commit
`20f9fb2d5aa781bb1bdc91fad47e749caf2ae3fa` to Python tests. The Python index-conflict
case also creates a real merge conflict, extending its original ownership checks.

| Original behavior | Python test (`tests.` prefix) |
|---|---|
| real Git local lifecycle preserves dirty source and resumes idempotently | `test_lifecycle.LifecycleTests.test_dirty_source_idempotent_local_lifecycle` |
| missing criteria, checks and uncommitted config cannot start | `test_lifecycle.LifecycleTests.test_missing_criteria_checks_and_uncommitted_config` |
| default endpoint is draft PR and base selects a stack layer | `test_lifecycle.LifecycleTests.test_default_draft_and_stack_base` |
| plan rejection, stale plan and key order are handled | `test_lifecycle.LifecycleTests.test_plan_rejection_stale_and_key_order` |
| failed executable check is recorded and repair can pass | `test_lifecycle.LifecycleTests.test_failed_check_recorded_then_repaired` |
| three failures stop; extension requires an explicit reason | `test_lifecycle.LifecycleTests.test_three_failures_and_explicit_extension` |
| tracked ignored files, modes, symlinks and untracked files invalidate evidence | `test_lifecycle.LifecycleTests.test_tracked_ignored_modes_symlinks_and_untracked_drift` |
| check config edits do not weaken frozen checks; edits are reviewed as code | `test_lifecycle.LifecycleTests.test_config_edits_do_not_weaken_frozen_checks` |
| a check that edits the tree cannot certify itself | `test_lifecycle.LifecycleTests.test_check_cannot_certify_self_edits` |
| review must cover criteria and cannot pass with major findings | `test_lifecycle.LifecycleTests.test_review_covers_every_criterion_and_no_major_findings` |
| edits after review and HEAD-only drift prevent delivery | `test_lifecycle.LifecycleTests.test_reviewed_tree_and_head_drift_prevent_delivery` |
| altered/missing worktree and conflicted index are rejected | `test_lifecycle.LifecycleTests.test_altered_missing_worktree_and_index_conflicts` |
| live locks refuse concurrent mutation; dead same-host locks recover | `test_lifecycle.LifecycleTests.test_live_locks_refuse_and_dead_same_host_recover` |
| interrupted commit reconciles exact reviewed tree without duplicate commit | `test_lifecycle.LifecycleTests.test_interrupted_commit_reconciles_without_duplicate` |
| interrupted worktree receipt can resume owned worktree | `test_lifecycle.LifecycleTests.test_interrupted_start_resumes_owned_worktree` |
| timeout kills descendant writer and logs are bounded | `test_processes.ProcessTests.test_timeout_kills_descendant_and_bounds_logs` |
| argv arguments are literal and missing executable is a failed check | `test_processes.ProcessTests.test_literal_argv_and_missing_executable` |
| CLI JSON round trip and duplicate intake is idempotent across processes | `test_lifecycle.LifecycleTests.test_cli_json_roundtrip_and_process_deduplication` |
| GitHub issue snapshot is frozen and repeated intake reuses identity | `test_lifecycle.LifecycleTests.test_issue_snapshot_frozen_and_identity_reused` |
| draft delivery observes remote head and recovers uncertain PR creation | `test_lifecycle.LifecycleTests.test_draft_remote_head_and_uncertain_create_recovery` |
| closed, ready, wrong-head or wrong-base PR cannot complete | `test_lifecycle.LifecycleTests.test_closed_ready_wrong_head_wrong_base_cannot_complete` |
| missing remote does not downgrade the default endpoint | `test_lifecycle.LifecycleTests.test_missing_remote_does_not_downgrade_endpoint` |
| repair after interrupted delivery supersedes its old commit intent | `test_lifecycle.LifecycleTests.test_repair_supersedes_interrupted_commit_intent` |
| renames and already-committed deletions deliver the exact reviewed tree | `test_lifecycle.LifecycleTests.test_renames_and_committed_deletions_exact_tree` |
| recovering a killed start also clears its dead allocation lock | `test_lifecycle.LifecycleTests.test_dead_allocation_lock_recovered` |
| summary before checks preserves exact multiline task/criteria and scans in human form | `test_summary.SummaryTests.test_multiline_exact_values_and_human_labels_before_checks` |
| summary reports failed check, skipped checks, exact diagnostics and subsequent repair | `test_summary.SummaryTests.test_failed_skipped_diagnostics_and_repair` |
| summary surfaces latest rejected plan/code findings and clears superseded reviews | `test_summary.SummaryTests.test_latest_rejected_findings_and_superseded_reviews` |
| summary retains timeout and executable error details | `test_summary.SummaryTests.test_timeout_and_executable_error_details` |
| summary supports wait, interrupted start, blocked and completed lifecycle without mutation | `test_summary.SummaryTests.test_wait_preparing_blocked_and_completed_readonly` |
| summary shows pending PR receipt during delivery recovery and exact completed draft receipt | `test_summary.SummaryTests.test_pending_and_completed_draft_receipts` |
| init creates Markdown configuration without overwriting existing project rules | `test_rules.RulesTests.test_init_markdown_without_overwriting_rules` |
| Markdown-only settings can be split across sorted rules and remain repository scoped | `test_rules.RulesTests.test_split_sorted_markdown_is_repository_scoped` |
| Markdown settings explicitly override legacy settings and CLI rules preserves exact content | `test_rules.RulesTests.test_overrides_exact_cli_content_resume_and_source_isolation` |
| missing rules is compatible and historical runs retain their exact evidence protocol | `test_rules.RulesTests.test_missing_rules_and_historical_exact_protocol` |
| edits, additions and removal of rules invalidate plan, verification and delivery | `test_rules.RulesTests.test_edits_additions_removals_invalidate_all_downstream_proof` |
| ignored rules still invalidate evidence and cannot bypass interrupted commit recovery | `test_rules.RulesTests.test_ignored_rules_invalidate_interrupted_commit` |
| settings changes cannot switch an active task to weaker checks | `test_rules.RulesTests.test_settings_edits_keep_frozen_checks_and_endpoint` |
| rules and settings must match the selected committed base | `test_rules.RulesTests.test_selected_base_must_match_committed_rules` |
| configuration parser rejects malformed, duplicate and unknown settings with file context | `test_rules.RulesTests.test_malformed_duplicate_unknown_and_empty_settings` |
| example code fences do not accidentally configure the project | `test_rules.RulesTests.test_outer_example_fences_are_not_settings` |
| rules reject symlinks, directories, invalid UTF-8 and excessive input | `test_rules.RulesTests.test_symlinks_directories_utf8_and_limits` |
| a check that writes ignored rules cannot certify its own verification | `test_rules.RulesTests.test_check_writing_ignored_rules_cannot_certify_itself` |
| interrupted start restores the initial rule receipt and rules command is read only | `test_rules.RulesTests.test_interrupted_start_restores_snapshot_and_rules_readonly` |
| a symlink rules directory on the base cannot be hidden by a dirty source deletion | `test_rules.RulesTests.test_base_symlink_cannot_be_hidden_by_source_deletion` |
| committed directories cannot masquerade as absent configuration files | `test_rules.RulesTests.test_committed_directories_cannot_masquerade_as_absent_files` |

## Migration additions

- Captured original Node hash vectors: UTF-16 keys, numeric enumeration, numbers,
  escaped Unicode and lone surrogates.
- Default/explicit branch validation, deduplication and collision rejection.
- Ledger rename invalidates proof, records ownership and recovers interruptions
  on either side of the Git mutation; HEAD drift and delivery are rejected.
- CLI input failures produce JSON without tracebacks.
- Bundled skill lookup and source entry point.
- Successful parent cleanup, inherited child pipes, SIGTERM cleanup and handler
  restoration, plus bounded command stdout/stderr.
- Real local lifecycle with Node/npm absent from PATH.

## Installed wheel

Build and install in a disposable environment, then run the standalone smoke:

```sh
uv build
python3 -m venv /tmp/factory-smoke
/tmp/factory-smoke/bin/python -m pip install --no-deps dist/*.whl
/tmp/factory-smoke/bin/python scripts/smoke_install.py
```

The smoke executes the installed console script outside the source checkout,
with only Git/Python on PATH. It runs init, start, plan/reviews, verification,
local delivery and summary, and checks the installed bundled skill. Synthetic
repositories disable inherited commit signing. No real PR or review is claimed.

## Cross-runtime proof

During the migration a synthetic task was started and plan-reviewed with the
original Node CLI, then resumed, verified, reviewed and locally delivered with
Python. Resume preserved state bytes; identity/config hashes and the approved
plan review remained unchanged. No receipt edits were used. The actual migration
task was also created and plan-reviewed in Node, then resumed and ledger-renamed
in Python. Live task evidence stays in the private run directory.

## PRD scaffolding

`tests/test_prd.py` exercises actual Git roots/linked worktrees, additive CLI output,
custom-byte preservation, unsafe-path/resource preflight, exclusive-create races and
partial open/write/close failures. Enrollment retains original settings validation.
The lifecycle test freezes full PRD text and multiple explicit criteria, deduplicates,
resumes after source edits and completes a synthetic-reviewed real local lifecycle.
Installed smoke asserts enrollment, standalone existing-project setup and repeats
outside the source tree without Node/npm, using packaged scaffold resources.

## Read-only preflight

`tests/test_preflight.py` compares exact source/index/saved receipt bytes and
Git worktree inventory before/after observations, including absent allocation and
worktree directories. Real Git fixtures cover independent blockers, required
settings drift, conflicts/submodules, branch collisions, allocation parent files,
selected-base executables, missing tools and credential-bearing synthetic origins.
Injected observation errors distinguish unavailable infrastructure from known
blockers. Installed smoke exercises local preflight without creating its root.


## Evidence diagnostics

`tests/test_diagnostics.py` uses real snapshot trees for modes, symlinks,
deletions, rename-as-delete/add and tracked ignored edits since verification.
It checks every fingerprint dimension, failed/historical proof, legacy rules,
owned delivery recovery, unavailable objects/worktrees, malformed rules/receipts,
live operation locks and edits during inspection. State, receipt, index, HEAD
and source bytes are compared. Summary tests retain exact historical projections;
installed smoke checks current explanation and terminal historical delivery.

## Reviewer bundles

`tests/test_review_context.py` asserts exact stage/context/evidence/task/criteria/
plan/rules/frozen checks, scoped instruction order and complete binary-capable
Git patch bytes. It covers explicit attributed inputs, file/aggregate/diff/bundle
bounds, unsafe/invalid UTF-8 files, live/foreign owners, changing inputs/new scopes,
historical rules-disabled contexts and stale review rejection. Automatic scope tests
reject outside directory symlinks and metadata/open races before external reads,
while retaining explicit path semantics. Non-UTF-8 Git patch
bytes round-trip through JSON; human output spells surrogate escapes explicitly.
State, receipts, source/index/HEAD and legacy schemas stay intact. Installed smoke
exercises both stages and compares their exact values with the real lifecycle.

## Verification observations

`tests/test_progress.py` synchronizes real verifier/check processes to prove active
attempt/check identity, completed/pending order, early small-output flushing and
read-only state/receipt/lock/source/index/HEAD behavior. SIGTERM retains the real
failed receipt/budget and interrupted observation. Tests cover fail-fast/skipped
checks, legacy/stale/malformed sidecars, dead/foreign/mismatched ownership, clock
clamping, changing snapshots, bounded/replacement log tails, unsafe files and
invalid attempts. Existing process cleanup/timeouts and summary regressions run
in the same suite. Installed smoke exercises both observations with the package.

The repository tests check allows 300000ms for the expanding real-process suite
(actual 140-test suite took about 101s against its prior 120s limit). The command and
all assertions remain unchanged; source still allows 30000ms. An active task always
uses its original frozen settings: a reviewed rules edit affects subsequent runs.

## Run discovery and history

`tests/test_history.py` creates real multiple runs and distinct failed/repaired
verification receipts. It asserts recency/fallback/ties, filtering before limits,
append-order stable event indices across clock reversal, pages, skipped checks and
missing timings/receipts. Invalid neighbors, missing worktrees, historical branches,
foreign/live/malformed locks, bounded counters and files, directory-open races and
symlink descendants retain explicit errors. Discovery/history preserve saved bytes,
source/index/HEAD, locks and worktree inventory. Legacy list and strict allocation
still reject malformed ledgers. The read-only captured-plan adapter uses a sentinel
for explicit absence; mutation gates retain live plan reads. Installed smoke uses
both commands and compares retained verification details.

## PR presentation and CI regressions

`tests/test_pr_description.py` uses real verified repositories and a synthetic GitHub
adapter that records literal title/body-file contents. It asserts exact evidence paths,
verbatim multiline criteria, Unicode/Markdown, private command withholding, input/body
bounds and file safety, no-op previews, interrupted metadata publication, immutable
commit/body selection and owned-commit recovery. Failed pushes, uncertain creates,
existing metadata, wrong head/base/state and ambiguous PRs stay explicit. No-input
delivery retains the exact old title/body/intent, including bodies beyond the custom
limit. Installed smoke submits a preview and retains its hash through local delivery.

Process tests inject cleanup permission failures and assert that the primary interrupt
and separate cleanup diagnostics survive; cleanup-only errors still fail. Existing real
process-group and restored-handler assertions remain. Disposable test repositories
disable automatic Git maintenance/GC before their first commit, preventing background
maintenance locks from racing strict file snapshots; preflight byte assertions remain.
