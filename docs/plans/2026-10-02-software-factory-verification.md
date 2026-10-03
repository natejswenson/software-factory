# Software Factory verification

Reviewed plan commit: `3a99787`. Bootstrap/main: `32f6d4f`.

The CLI uses built-in Node modules and Git worktrees. The packaged host skill
drives planning, implementation, repairs and independent review in the current
agent session. Draft PR is the default endpoint. Runtime receipts remain in Git
common-dir storage; no machine paths, secrets or private memory are bundled.

Independent read-only implementation reviewer found four concrete failures:
repair after interrupted remote delivery, same-SHA stack base identity, rename
staging, and intake allocation-lock recovery. All were fixed with behavioral
regressions. Reviewer also corrected initial draft-branch installation guidance.
No unresolved reviewer blocker remains.

Validation observed before initial delivery:
- 25 integration tests pass using real Git/worktrees/processes and local GitHub mocks.
- `npm run check`: every JavaScript source parses.
- Skill frontmatter/name/placeholder validation passes.
- npm tarball builds with 10 intended runtime/documentation files, no dependencies,
  tests, task records, personal logs or installation state.
- Tarball installs offline into an isolated prefix and its CLI runs successfully.
- GitHub adapter observes remote HEAD and draft state; uncertain creation retries,
  closed/ready/wrong-head/wrong-base responses and missing remote are tested locally.

Live GitHub delivery and an independent native-agent forward task will be recorded
as separate observed results after execution. Adapter tests are not live evidence.
No comparative performance benchmark or universal superiority claim is established.
macOS was exercised; Linux is supported by the same POSIX mechanism but was not
executed on this host. Windows and submodules are outside current support.
