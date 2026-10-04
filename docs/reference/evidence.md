# What the evidence establishes

The snapshot includes tracked files even under ignore rules, nonignored new
files, deletions, executable modes and symlink targets. Check commands must all
pass without changing that snapshot. Review binds the plan, criteria, checks,
repository rules, base, HEAD and Git tree. Delivery observes the exact committed tree and, for
GitHub, an open draft PR with the same branch/head/base.

The engine validates evidence structure and freshness. It cannot prove that a
reviewer reasoned correctly, that tests cover every bug, or that two reviewers
are independent. Ignored dependencies, external services and environment state
are outside the Git fingerprint. Submodules and conflicted indexes are rejected.
Local processes and state files are trusted; hashes are not a security sandbox.

Checks execute repository code with your host's permissions. No shell is added
by the engine; an explicitly configured shell command still runs that shell.
Check output is capped at 1 MiB per log, with truncation recorded. Timeout and
interrupt handling terminate POSIX process groups. No paid model API, telemetry,
account database, memory service or Kubernetes platform is required. The skill
uses existing authorized memory/preview integrations when present.
