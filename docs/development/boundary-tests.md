# Boundary test contracts

Use this map when changing a public command or reader. Select applicable risks,
map each criterion to asserting test IDs or actual observations, and explain
omissions. Read the test bodies: a listed ID, test count, passing boolean or
checklist is not behavioral evidence. This audit records existing fixes and
limits; it does not introduce a CLI, receipt field or new approval stage.

## Risk classes

| Code | Applicable promise | Evidence and nonapplicability |
|---|---|---|
| B | Bounded numeric, recursive and byte inputs | Check the surface's actual bounds and unknown/error behavior. Bounded observers differ from legacy mutation readers; no universal depth bound is promised. |
| O | Host plus PID ownership | Foreign, missing, malformed and local owners remain distinct. Metadata/PID probes are observations, not hostile-process identity. No owner exists for help/resource lookup or initial scaffolding. |
| F | Filesystem scope and ancestry | Inspect unsafe links, nonregular inputs, missing files and changed ancestors where files are read/written. Parser-only errors need no filesystem case. |
| S | Snapshot freshness and preservation | Readers preserve their promised source/ledger bytes and discard moving facts. Mutation commands instead prove frozen evidence/ownership and their intended writes. |
| E | CLI exit and JSON channels | Parse actual subprocess stdout/stderr separately. Success/partial reports use stdout; refused input uses JSON stderr. Do not assume every surface uses identical 2/3 meanings. |
| P | Portable/literal/private presentation | Test exact values/argv and withholding host paths when publishing. A private local context is deliberately complete, not a public redaction surface. |
| X | Process interruption/cleanup | Applies to spawned checks/commands. Pure readers do not spawn checks or take over locks; blocking writers retain cleanup and primary errors. |

Every surface below names applicable codes. Other codes are nonapplicable for
the reasons above: scaffolding is an intended write, lifecycle writers are not
read-only monitors, and private bundles are not published PR bodies. Git readers
may spawn bounded Git subprocesses; shared X tests cover the command runner,
not a claim that all read-only Git calls leave the object store unchanged.

## Current public surfaces

Each ID has its full unittest discovery name. Shared cases are used only for
surfaces that their assertions exercise. Limits supplement, rather than replace,
the promised behavior.

| Surface | Promised outcome and applicable risks | Asserting test IDs | Limits |
|---|---|---|---|
| `help`, `skill-path`, source/plugin entrypoint | Literal help names, loaded plugin owns resource lookup, missing/unsafe resources do not fall back; E F P | `tests.test_integration.IntegrationTests.test_help_retains_literal_command_names_across_terminal_widths`; `tests.test_plugin_structure.PluginStructureTests.test_launcher_uses_loaded_root_with_literal_arguments_and_unrelated_cwd`; `tests.test_plugin_structure.PluginStructureTests.test_missing_plugin_resources_fail_without_global_fallback`; `tests.test_plugin_structure.PluginStructureTests.test_unsafe_engine_alias_fails_before_outside_import_side_effects` | Plugin discovery/schema checks do not prove host activation/update. |
| `init`, `prd-init` | Validate before writes; preserve regular custom files; report partial creations; B F E | `tests.test_rules.RulesTests.test_init_markdown_without_overwriting_rules`; `tests.test_prd.PrdTests.test_cli_setup_root_nested_repeat_and_custom_bytes`; `tests.test_prd.PrdTests.test_unsafe_paths_and_invalid_resources_never_write_peers_or_config`; `tests.test_prd.PrdTests.test_write_and_close_failures_report_created_incomplete_and_preserve_bytes` | Initial scaffolding has no task owner/proof receipt. Incomplete created files require inspection, not implied success. |
| `preflight` | Observe selected-base prerequisites without allocation or source writes; independent blockers and dependent unknowns; F S E P | `tests.test_preflight.PreflightTests.test_ready_with_unrelated_dirt_is_read_only_including_saved_receipts`; `tests.test_preflight.PreflightTests.test_private_allocation_parent_shapes_are_known_blockers_with_no_writes`; `tests.test_preflight.PreflightTests.test_access_and_infrastructure_unknown_reports_exit_three_not_success`; `tests.test_preflight.PreflightTests.test_cli_exact_contract_human_output_exit_and_no_tracebacks` | No reservation, executable check, remote readiness or delivery proof. |
| `start` (task/file/issue), `resume` | Freeze explicit criteria/checks/issue snapshot; deduplicate safely and reconcile owned interrupted creation; B O F S E P | `tests.test_lifecycle.LifecycleTests.test_cli_json_roundtrip_and_process_deduplication`; `tests.test_lifecycle.LifecycleTests.test_issue_snapshot_frozen_and_identity_reused`; `tests.test_lifecycle.LifecycleTests.test_missing_criteria_checks_and_uncommitted_config`; `tests.test_lifecycle.LifecycleTests.test_interrupted_start_resumes_owned_worktree`; `tests.test_lifecycle.LifecycleTests.test_prd_file_freezes_full_text_criteria_dedup_and_resume_gates` | Issue API fixture uses a synthetic gh executable, not live GitHub approval. No automatic linked-PRD loading. |
| `list`, `status`, `next` | Legacy strict inventory/projection; gates retain original live inspection defaults; O F S E | `tests.test_history.HistoryTests.test_order_fallback_ties_filter_before_limit_and_legacy_list`; `tests.test_history.HistoryTests.test_bad_neighbor_and_missing_worktree_preserve_rows_strict_start_refuses`; `tests.test_history.HistoryTests.test_plan_snapshot_adapter_explicit_absence_no_fallback_and_mutation_defaults`; `tests.test_lifecycle.LifecycleTests.test_live_locks_refuse_and_dead_same_host_recover` | Strict legacy readers are not tolerant inventories. A next action is not authority to bypass it; source fingerprinting may create local Git objects. |
| `summary` | Exact compact historical overview, failed/skipped checks, current next and saved endpoint; O F S E P | `tests.test_summary.SummaryTests.test_multiline_exact_values_and_human_labels_before_checks`; `tests.test_summary.SummaryTests.test_failed_skipped_diagnostics_and_repair`; `tests.test_summary.SummaryTests.test_wait_preparing_blocked_and_completed_readonly`; `tests.test_summary.SummaryTests.test_pending_and_completed_draft_receipts` | A historical passed check is not current proof or refreshed remote state; same snapshot/object-store limit as next. |
| `runs`, `history` | Tolerate malformed neighbors/attempts; bound depth/count/metrics; distinguish recorded outcome, unavailable next and real history order; B O F S E P | `tests.test_history.HistoryTests.test_deep_metadata_real_cli_isolated_and_state_bytes_preserved`; `tests.test_history.HistoryTests.test_saved_review_numeric_overflow_retains_rows_without_traceback`; `tests.test_history.HistoryTests.test_extreme_duration_metrics_never_emit_infinity_and_integral_values_are_integers`; `tests.test_history.HistoryTests.test_directory_open_race_and_descendant_symlinks_never_read_outside`; `tests.test_history.HistoryTests.test_continuous_history_drift_makes_metrics_and_attempts_explicitly_unavailable`; `tests.test_history.HistoryTests.test_cli_malformed_neighbor_receipt_and_options_preserve_saved_outcomes` | Partial observations are not empty or passing proof. History timing is recorded check time, not task wall time. Strict list/start behavior stays separate. |
| `guide` | Unique explicit selection, one literal recommendation, done has none; read-only coherent observer across all owners/source/config; B O F S E P | `tests.test_guide.GuideTests.test_prefix_collision_including_corrupt_hidden_candidates_and_invalid_before_fs`; `tests.test_guide.GuideTests.test_real_lifecycle_matches_authoritative_next_and_literal_recommendations`; `tests.test_guide.GuideTests.test_cli_human_json_exit_quote_and_help_names`; `tests.test_guide.GuideTests.test_local_explicit_and_default_global_ignores_preserve_engine_evidence_and_precedence`; `tests.test_guide.GuideTests.test_local_and_global_ignore_drift_discards_current_advice` | Similarity is only a possible relation; no recovery, extension or implicit resume. Required tree inspection refuses filters/unsupported Git/sparse trees instead of guessing. |
| `integration` | Separate saved delivery head, current availability and exact local target ancestry; all owners respected, no fetch/object writes; B O F S E P | `tests.test_integration.IntegrationTests.test_recorded_head_current_head_and_real_target_ancestry_are_separate`; `tests.test_integration.IntegrationTests.test_real_source_identical_pending_merge_and_cli_exits`; `tests.test_integration.IntegrationTests.test_promised_missing_commit_never_fetches_or_populates_object_store`; `tests.test_integration.IntegrationTests.test_every_owner_or_malformed_lock_prevents_git_without_takeover`; `tests.test_integration.IntegrationTests.test_moving_target_state_and_owner_clear_current_observations` | Local topology is not merge/rebase permission, a fetch, conflict prediction or remote CI. |
| `explain` | Separate verdict/freshness, unknown proof under owners/missing/drifting source; O F S E P | `tests.test_diagnostics.DiagnosticTests.test_missing_current_and_failed_proofs_match_authoritative_next`; `tests.test_diagnostics.DiagnosticTests.test_foreign_host_with_same_pid_never_inspects_current_files`; `tests.test_diagnostics.DiagnosticTests.test_malformed_proofs_and_inspection_failure_after_next_remain_partial`; `tests.test_diagnostics.DiagnosticTests.test_run_change_between_initial_read_and_capture_is_not_current` | Engine fingerprinting can create local Git objects; source/index/ledger preservation is not a universal no-object-write claim. |
| `rules` and settings reader | Current selected-worktree instructions are exact/bounded; changes invalidate downstream proof while frozen checks/endpoint remain; B F S E | `tests.test_rules.RulesTests.test_overrides_exact_cli_content_resume_and_source_isolation`; `tests.test_rules.RulesTests.test_symlinks_directories_utf8_and_limits`; `tests.test_rules.RulesTests.test_edits_additions_removals_invalidate_all_downstream_proof`; `tests.test_rules.RulesTests.test_settings_edits_keep_frozen_checks_and_endpoint` | Rules are guidance, not commands or permission. Legacy rules-disabled records retain their protocol. |
| `review-context` | Complete exact plan/code inputs or refusal, bounded attributed text/binary diff, changing/unsafe ancestors rejected; B O F S E P | `tests.test_review_context.ReviewContextTests.test_plan_full_exact_values_and_explicit_attributed_inputs`; `tests.test_review_context.ReviewContextTests.test_code_complete_binary_diff_scopes_and_frozen_checks`; `tests.test_review_context.ReviewContextTests.test_automatic_ancestry_never_imports_outside_instructions_but_explicit_paths_work`; `tests.test_review_context.ReviewContextTests.test_directory_swap_between_metadata_and_open_cannot_read_outside_scope`; `tests.test_review_context.ReviewContextTests.test_cli_json_human_help_and_invalid_stage` | Private context includes explicit private inputs. Completeness/freshness cannot certify supplement truth or reviewer independence; capture may write Git snapshot objects. |
| `progress`, `logs` | Matching host/PID/attempt, bounded tail, unknown corrupt/missing sidecar, stable observation and no proof mutation; B O F S E P | `tests.test_progress.ProgressTests.test_live_second_process_progress_flushed_small_log_and_readonly`; `tests.test_progress.ProgressTests.test_unrepresentable_owner_pid_never_probed_or_crashes_real_cli`; `tests.test_progress.ProgressTests.test_active_missing_sidecar_dead_foreign_and_mismatched_owner`; `tests.test_progress.ProgressTests.test_invalid_log_inputs_symlink_nonregular_and_read_race`; `tests.test_progress.ProgressTests.test_latest_attempt_never_reuses_previous_results_clock_clamp_and_drift` | Real synchronized subprocess test observes liveness; injected PID/clock/race cases test branches. Neither authorizes takeover. |
| `plan`, `plan-review`, `review` | Exact context/evidence, complete criteria, no major finding on pass; O F S E | `tests.test_lifecycle.LifecycleTests.test_plan_rejection_stale_and_key_order`; `tests.test_lifecycle.LifecycleTests.test_review_covers_every_criterion_and_no_major_findings`; `tests.test_review_context.ReviewContextTests.test_legacy_exact_context_readonly_and_stale_review_submission` | Schema checks cannot establish relevance, independence or honesty; fixture reviews are explicitly synthetic. |
| `verify` and command/check runner | Frozen checks, self edits cannot pass, failed/interrupted checks retain errors/cleanup and budget; B O F S E X | `tests.test_lifecycle.LifecycleTests.test_config_edits_do_not_weaken_frozen_checks`; `tests.test_lifecycle.LifecycleTests.test_check_cannot_certify_self_edits`; `tests.test_progress.ProgressTests.test_handled_sigterm_final_interrupted_without_forged_pass`; `tests.test_processes.ProcessTests.test_timeout_kills_descendant_and_bounds_logs`; `tests.test_processes.ProcessTests.test_interrupt_kills_group_and_restores_handlers`; `tests.test_processes.ProcessTests.test_command_cleanup_failure_preserves_primary_and_reaps_child`; `tests.test_processes.ProcessTests.test_successful_group_kill_is_not_repeated_after_parent_exit` | POSIX groups/handlers tested with real descendants plus injected fault branches. A local OS pass does not establish the other supported OS. |
| `pr-description` and public body renderer | Evidence-bound literal title/summary, bounded input/body, private argv withheld, unsafe owned files refused, immutable retries; B O F S E P | `tests.test_pr_description.PresentationTests.test_portable_literal_commands_table_escape_and_recorded_outcomes`; `tests.test_pr_description.PresentationTests.test_unsafe_encoding_duplicate_keys_limits_and_infrastructure`; `tests.test_pr_description.PresentationTests.test_unicode_storage_expansion_and_owned_symlinks_are_safe`; `tests.test_pr_description.PresentationTests.test_cli_json_human_and_exact_idempotence_missing_preview`; `tests.test_pr_description.PresentationTests.test_failed_push_and_immutable_artifact_body_recovery` | Privacy is conservative for generated check argv, not a sanitizer for arbitrary agent-authored prose. Binding does not certify the prose. |
| `deliver` | Exact reviewed tree/head, observed requested endpoint, owned commit/create recovery; O F S E P X | `tests.test_lifecycle.LifecycleTests.test_reviewed_tree_and_head_drift_prevent_delivery`; `tests.test_lifecycle.LifecycleTests.test_interrupted_commit_reconciles_without_duplicate`; `tests.test_lifecycle.LifecycleTests.test_draft_remote_head_and_uncertain_create_recovery`; `tests.test_lifecycle.LifecycleTests.test_missing_remote_does_not_downgrade_endpoint`; `tests.test_pr_description.PresentationTests.test_uncertain_create_reconciles_existing_metadata_without_duplicates` | gh fixtures/local remotes prove branches, not a live PR. Live delivery needs the actual receipt/URL and exact head; merge/release remain separate actions. |
| `recover`, `extend`, `rename` | Explicit engine actions retain host/ownership, budget and branch history; O F S E | `tests.test_lifecycle.LifecycleTests.test_live_locks_refuse_and_dead_same_host_recover`; `tests.test_lifecycle.LifecycleTests.test_dead_allocation_lock_recovered`; `tests.test_lifecycle.LifecycleTests.test_three_failures_and_explicit_extension`; `tests.test_migration.MigrationTests.test_rename_invalidates_proofs_records_ownership_and_is_idempotent` | Budget extension requires user direction; terminal outcome is historical. Renaming invalidates checks/review; no implicit worktree deletion. |

## Already-fixed findings and complementary audit case

The following regressions already contain behavioral assertions; these are fixed
classes, not newly discovered defects. Host/PID and numeric cases inject private
fixture faults. Filesystem/process cases combine real temporary repos/processes
with deterministic swaps, simulated permission errors and interrupt reentry.

| Historical class | Existing regression and observed assertion |
|---|---|
| Foreign host with this process's PID | `tests.test_diagnostics.DiagnosticTests.test_foreign_host_with_same_pid_never_inspects_current_files`: wait/unknown, unchanged bytes, source inspection forbidden. |
| Deep JSON and oversized numeric saved evidence | `tests.test_history.HistoryTests.test_deep_metadata_real_cli_isolated_and_state_bytes_preserved`; `tests.test_history.HistoryTests.test_saved_review_numeric_overflow_retains_rows_without_traceback`: real subprocess isolates bad neighbor and preserves healthy rows without traceback. |
| Unrepresentable PID | `tests.test_progress.ProgressTests.test_unrepresentable_owner_pid_never_probed_or_crashes_real_cli`: unknown observation; no unsafe process probe. |
| Symlink instruction ancestors and directory swaps | `tests.test_review_context.ReviewContextTests.test_automatic_ancestry_never_imports_outside_instructions_but_explicit_paths_work`; `tests.test_review_context.ReviewContextTests.test_directory_swap_between_metadata_and_open_cannot_read_outside_scope`: no outside automatic content and no partial complete bundle. |
| Host/private argv path forms | `tests.test_pr_description.PresentationTests.test_portable_literal_commands_table_escape_and_recorded_outcomes`: POSIX, Windows, UNC, tilde, URL and option-attached host paths withheld; portable literal argv retained. |
| Cleanup reentry and primary error | `tests.test_processes.ProcessTests.test_nested_interrupt_cannot_clear_successful_group_kill`; `tests.test_processes.ProcessTests.test_cleanup_permission_diagnostics_preserve_primary_interrupt`: successful group kill not repeated, original interrupt/error retained alongside cleanup diagnosis. |
| Reorganized guide meanings | `tests.test_plugin_structure.PluginStructureTests.test_moved_usage_preserves_run_location_and_numeric_limits_as_prose`: run location and bounded reader behavior remain prose, not hidden in command examples. |

The added `tests.test_history.HistoryTests.test_cli_malformed_neighbor_receipt_and_options_preserve_saved_outcomes`
combines malformed neighbor metadata and malformed attempt bytes with a real local
delivered healthy neighbor. It checks subprocess channels/exits, retained exact
outcome/events, invalid proof and unchanged source/Git/ledger bytes. Its local
fixture delivery and fixture verdicts are test evidence, never live task delivery.
`tests.test_documentation.DocumentationTests.test_boundary_contract_ids_are_discovered_asserting_and_navigation_is_present`
checks discoverability/assertion structure/navigation, including a damaged ID.
It does not grade behavioral relevance; native review must read the cited bodies.

## Using the contract

In plans and reviewer inputs provide a compact mapping:

| Criterion/claim | Relevant test or actual observation | Evidence kind | Limit/omission reason |
|---|---|---|---|
| Example: malformed neighbor cannot hide an endpoint | exact discovered test ID and its asserted retained outcome | real CLI over synthetic ledger fixtures | no live GitHub delivery implied |

After a finding, add a regression that fails for the defect and asserts the repaired
public behavior, then obtain fresh full verification and native review with exact
context/evidence. Keep per-commit associated test relevance separate from structural
CI policy. An evidence string or checked row cannot bypass full checks, freshness,
repair limits, independent review or observed delivery.

## Observation limits and remaining gaps

This is a risk-based audit, not every malformed combination or a coverage percentage.
Legacy mutation/status readers use their original protocols; the bounded tolerant
reader regressions do not prove uniform malicious-JSON handling for all commands.
Do not extrapolate history's depth limits or its healthy-neighbor semantics to list,
start or mutation endpoints. A change to those promises needs its own behavior test.
Signal/error races use deterministic injection as well as real POSIX processes;
hostile PID reuse, network filesystems and unsupported Windows process semantics
remain unproven. Current tests are portable Python/POSIX/Git cases, with Linux
Python3.11/3.14 and macOS Python3.14 in CI. Report actual local OS and current CI
results for each delivery; a prior platform run does not prove this final tree.
No raw personal paths, private ledgers or production receipt mutations belong here.

Navigation: [testing](testing.md), [documentation index](../README.md),
[shared skill](../../skills/software-factory/SKILL.md),
[artifact protocol](../../skills/software-factory/protocol.md).
