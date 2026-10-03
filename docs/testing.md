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
