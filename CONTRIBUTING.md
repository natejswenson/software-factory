# Contributing

Read [AGENTS.md](AGENTS.md) for repository policy. Use Python 3.11+ for implementation
and tooling, the standard library at runtime, and the standard setuptools build
backend. Keep changes small enough to review and share.

## Work and verification

Start from `main`. Work branches use `feature/<name>`, `bug/<name>` or
`issue/<name>` with lowercase words separated by hyphens. An explicitly selected
lower branch can be a stack base; draft PRs target that base. Obtain fresh plan
and code reviews and run both required checks before delivery:

```sh
python3 scripts/verify.py tests
python3 scripts/verify.py source
uv build
```

Every nonempty commit needs an added or semantically updated asserting test that
passes. Documentation and configuration commits follow the same policy. Inspect
test relevance in review; structural association is not proof of coverage.

[Testing](docs/development/testing.md) explains behavior coverage and the installed
wheel smoke. [Architecture](docs/development/architecture.md) maps implementation
ownership. [Automation](docs/development/automation.md) explains ready PR merges,
required CI, patch releases, queue limits and retry behavior.

## Designs and evidence

Execution-ready specifications live in [design/](design/README.md). The hand-authored
[PRDs](prd/README.md) describe user requirements; adding them does not execute them
or establish completion. A design still needs its own reviewed factory plan.

Factory verification, review and delivery receipts remain private under the Git
common-dir. [Historical observations](docs/history/README.md) retain their original
claims. Do not publish raw run records or turn a pending observation into a
completed claim. Keep draft implementation PRs draft at the task endpoint.
