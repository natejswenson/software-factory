# Software Factory

## Request
Build a simple, clean, shareable factory that fits the user's Codex/Claude, Git,
skills, memory and worktree workflow and carries a task through completion.
The user selected CLI + agent skill. A universal superiority claim requires
comparative evaluation and is not an acceptance result we can honestly promise.

## Acceptance criteria
- Plain text or GitHub issue intake freezes a task with explicit acceptance criteria.
- One small dependency-free Node CLI creates an isolated Git worktree, gives the
  current agent its next action, and resumes a persisted run after interruption.
- Reviewed plan precedes implementation. Actual configured commands, final tree
  and structured review evidence gate delivery. Failed/stale checks cannot finish.
- Fix cycles are bounded, failures remain visible, and fresh evidence is required
  after any file, configuration or plan change.
- Local delivery produces a verified clean commit; draft-PR delivery checks the
  observed remote/head/draft URL and is retryable without creating duplicate PRs.
- Runtime task data, logs and machine paths stay outside committed source. The
  user's original checkout/dirty files and shared services remain undisturbed.
- Package and agent skill are portable, installable from an npm tarball/repo,
  MIT licensed, with no paid model API, daemon or mandatory account store.
- Automated adversarial integration tests plus a real agent-driven task demonstrate
  completion and resume; unobserved live GitHub behavior is explicitly distinguished.

## Decisions and scope
New standalone repository: `software-factory`.
Node >=22 on macOS/Linux, Git, optional gh for GitHub. Built-in modules only. Native host agent
does reasoning and edits; no subprocess model or API credential required.
Project-owned `.factory.json`: version, checks as argv arrays, timeouts, endpoint.
Private runtime: Git common-dir/factory/runs/<id>, atomically replaced JSON plus
artifact files, exclusive operation lock. Worktree root is an explicit host-approved
path. Default endpoint is draft PR, per the user's answer. Local commit requires
explicit selection; missing remote remains pending delivery. No implicit merge/release.
User permits stacked PRs: one run per layer with explicit `--base`, host manages ordering.
User authorized a new public `natejswenson/software-factory` GitHub repository.
CLI entry: init, start, list, status, next, plan, plan-review, verify, review, deliver.
start reuses a matching unfinished run; next emits exact current action and context.
Plan and code review come from native independent agents when available. CLI validates
their schema and file fingerprints, not the truth of reasoning or reviewer independence.
Hashes are freshness checks, not a security boundary against a malicious local user.
Plan is runtime Markdown. Review binds its hash, including criteria/check configuration.
Verify uses a temporary Git index covering tracked ignored files, nonignored untracked
files, modes, symlinks, paths and deletions. Reject conflicts/submodules. Evidence binds
base, HEAD, criteria, plan and frozen checks. Final commit tree must match the review.
Stage only enumerated reviewed paths with literal pathspecs. Execute argv with timeouts,
POSIX process-group termination and bounded logs, never shell interpolation.
Require a check and nonempty criteria. Code reviews identify reviewer, verdict, concrete
findings and evidenced results for every criterion; no unresolved blockers may pass.
Reviewer independence is a host obligation with self-review disclosure when unavailable.
Failed checks and rejected reviews consume a shared three-failure budget; infrastructure
failures do not. User-directed extension is a separate
explicit CLI action rather than hidden automatic retry. Repository instructions and
host permissions remain authoritative. Memory/preview hooks live in the skill and
are optional; this CLI app has no `.dev/preview.json` and requires no app preview.
Run identity includes canonical repo/common-dir, task source/text, criteria, endpoint
and frozen base. Resume rejects ambiguity, missing/altered worktree ownership.
Persist intents before worktree creation, commit, push and PR creation; retries reconcile
actual results. Recover only dead-process same-host locks, never a live owner.

## Repository evidence
No existing software-factory checkout or remote. Unborn feature/software-factory
branch; no upstream/base to refresh. Existing claude-skills checkout has unrelated
work, so it is left in place. Installed local-dev 0.1.0 and issueflow 0.18.0 provide
native planning and review precedent. Live global memory records require infrastructure
and machine state separation and assistant-led enrolled previews. Activity reporting
is enabled; durable project captures require an explicit request.
Primary comparison sources checked 2026-10-02:
- https://github.github.com/spec-kit/
- https://github.com/gsd-build/get-shit-done/blob/main/docs/COMMANDS.md
- https://aider.chat/docs/usage.html
These establish existing capabilities, not comparative benchmark results.

## Implementation
1. Validate project config; implement Git inspection, state/lock persistence, worktree
   creation and plain-text/issue intake.
2. Implement fingerprinted plan/review, executable verification, bounded repairs,
   deterministic next/resume and human-readable/JSON views.
3. Implement observed local/draft delivery and recovery receipts.
4. Package CLI, skill, configuration example, concise README, license and examples.
5. Integration tests exercise real Git and check processes; run real agent-driven
   acceptance task in a temporary fixture. Pack and run installed tarball.

## Validation
`npm test`; `npm run check`; `npm pack --dry-run`; installed tarball CLI smoke;
skill frontmatter validation; independent plan review; independent forward task.
Tests target stale plan/tree evidence, failing/timeout checks, zero checks, review
findings, unrelated dirty source, concurrent operations, interrupted recovery,
paths with spaces, issue snapshot and GitHub response validation/retry via local mocks.
Test GitHub adapter locally, then observe live draft PR and matching head on the
authorized new repository. Local mock results remain distinct from live evidence.

## Review
Independent read-only reviewer `/root/plan_review` identified six corrections:
draft PR default, complete fingerprint, per-operation crash recovery, descendant
containment, explicit evidence gates, and run/base ownership. All were accepted and
incorporated above. Additional tests cover operation interruption, dead/live locks,
tracked ignored files/modes/symlinks, altered worktrees and descendant writers.
Real native-agent task must include meaningful failure, repair and resume. No unresolved
design blocker. Live draft PR delivery will be verified on the authorized new repository.
