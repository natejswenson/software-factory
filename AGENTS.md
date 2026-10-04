# Software Factory

Use Python for all net-new implementation and tooling. Prefer the standard library.
Python >=3.11 and macOS/Linux are supported. Use the standard setuptools build
backend and keep the runtime dependency-free.
Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source`
before delivery. Preserve the rule that completed
tasks require fresh executable verification, review and observed delivery.
Keep runtime data and personal paths outside source. Never launch paid model APIs.
Start work branches from main and name them feature/<name>, bug/<name>, or
issue/<name>. Draft PRs target main or an explicitly selected
lower stack layer. No implicit merges, releases or deletion of task worktrees.

Every nonempty commit, including documentation/configuration changes, must add or
semantically update an executable Python unittest test containing assertions.
The associated test must pass in the final PR suite; comments, deletions, skipped
tests and undiscovered helpers do not satisfy the gate. Inspect each commit's
test relevance in review. GitHub CI's stable `test` check is required on main.
Ready same-repository PRs from writers automatically squash-merge to main after
passing protection; drafts remain drafts. Successful main merges create GitHub
patch releases with tested wheel/source archives. Repository automation handles
these authorized actions; the factory's task endpoint remains a reviewed draft PR.
