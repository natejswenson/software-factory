# Architecture

Software Factory is a small dependency-free Python CLI. The coding agent owns
investigation, plans, implementation and review; the CLI stores task state and
checks freshness and observed delivery. It does not launch a model or daemon.

## Runtime ownership

| Module | Responsibility |
|---|---|
| `__main__.py` | Source invocation entry point for `python3 -m software_factory` |
| `__init__.py` | Runtime package version, supplied by build-time setuptools-scm when packaged |
| `cli.py` | Argument parsing, dispatch, human/JSON output and exit codes |
| `engine.py` | Enrollment, task allocation, phases, freshness gates, verification, recovery and branch rename |
| `rules.py` | Bounded Markdown rules/config discovery, parsing and committed-base validation |
| `checks.py` | Frozen argv validation, bounded check logs, timeout/signal handling and process cleanup |
| `git.py` | Literal Git commands, supported repository state, temporary-index snapshots and worktree ownership |
| `store.py` | Canonical version-1 hashing, private atomic JSON, run identity/history and operation locks |
| `delivery.py` | Exact reviewed commit, remote head observation and idempotent draft PR reconciliation |
| `preflight.py` | Read-only local readiness probes; advisory preparation, without task allocation or remote checks |
| `summary.py` | Read-only human/JSON projection of recorded checks, findings, next action and delivery |
| `validation.py` | Shared JSON integer compatibility checks |
| `errors.py` | Structured factory errors and error codes |
| `skills/software-factory/` | Bundled agent workflow and authoritative artifact protocol |

## Task flow

CLI input reaches the engine, which validates the committed base and repository
rules, freezes the task/criteria/checks, then allocates an owned branch/worktree.
A reviewed plan permits implementation. Verification executes all frozen checks
and records exact context/tree evidence. Code review covers each criterion at
that evidence. Delivery commits only the reviewed tree, observes the pushed head,
and creates or reconciles an open draft PR at the selected head/base.

The [evidence guide](../reference/evidence.md) explains freshness and limits;
[task operations](../user-guide/tasks-and-recovery.md) describe repair and recovery.
The [bundled protocol](../../software_factory/skills/software-factory/protocol.md)
defines plan/review artifacts. Documentation links to that protocol rather than
maintaining another schema.

## Source, instructions and private data

- `software_factory/`, `tests/` and `scripts/` retain the flat source layout.
- `.rules/*.md` provides repository instructions and validated executable settings.
- `design/` describes implementation; `prd/` describes requirements. Both are task
  inputs, not authority to bypass review or proof of completion.
- Factory runs, receipts, logs and locks live under the Git common-dir's
  `factory/runs`, outside committed source. Ignored dependencies and host services
  are outside the Git fingerprint.
- `skills/software-factory` is a retained relative compatibility symlink to the
  canonical bundled directory. `factory skill-path` resolves the installed path.

Repository automation lives in `.github/workflows/` and the Python `scripts/`
helpers; it is separate from the CLI's default draft endpoint. See
[automation](automation.md) for the required CI and authorized ready-PR/release flow.
