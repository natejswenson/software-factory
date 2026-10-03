# Software Factory

Use Python for all net-new implementation and tooling. Prefer the standard library.
The existing JavaScript runtime uses Node >=22 and built-in modules. macOS/Linux
are the supported platforms.
Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source`
before delivery. Preserve the rule that completed
tasks require fresh executable verification, review and observed delivery.
Keep runtime data and personal paths outside source. Never launch paid model APIs.
Start work branches from main and name them feature/<name>, bug/<name>, or
issue/<name>. Draft PRs target main or an explicitly selected
lower stack layer. No implicit merges, releases or deletion of task worktrees.
