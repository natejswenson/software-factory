# Software Factory repository rules

## Factory settings

```factory-config
{
  "version": 1,
  "endpoint": "draft-pr",
  "checks": [
    {
      "name": "tests",
      "argv": [
        "python3",
        "scripts/verify.py",
        "tests"
      ],
      "timeoutMs": 120000
    },
    {
      "name": "source",
      "argv": [
        "python3",
        "scripts/verify.py",
        "source"
      ],
      "timeoutMs": 30000
    }
  ]
}
```

## Branch naming

Use one of these formats for work branches:

- `feature/<name>` for features, enhancements and repository setup.
- `bug/<name>` for bug fixes.
- `issue/<name>` for work organized around a GitHub issue.

Use a short, descriptive name, with lowercase words separated by hyphens.
Examples: `feature/repo-rules`, `bug/rule-parsing`, `issue/42-rule-loading`.

## New code

Write all net-new implementation and tooling in Python.
Use Python tests for new Python behavior and add meaningful Python test commands
to the factory checks when Python code is introduced.
The existing JavaScript implementation remains subject to its current tests.

## Completion

Run the configured checks and obtain fresh plan and code reviews before delivery.
The default endpoint is a draft pull request.
