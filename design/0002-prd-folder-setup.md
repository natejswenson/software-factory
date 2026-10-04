# 0002 — Add PRD folder setup to Software Factory

Status: ready for factory planning; implementation pending.

Baseline inspected: `447c49f0c09ca7a9d07a7bc92d1f4f3b35960fd2` on `main`.
Preferred predecessor: [design 0001](0001-repository-structure.md). If executing
independently, update the current README and `docs/testing.md` instead of paths
that only exist after design 0001. No runtime behavior depends on that cleanup.

## Problem and outcome

`factory init` enrolls a project by creating `.rules/factory.md`, but provides no
place or template for product requirements. Teams must improvise both folder
conventions and the handoff from a PRD to a verified task. Already enrolled
projects cannot rerun `init` because it correctly refuses existing settings.

Add a consistent top-level `prd/` folder to new enrollments and provide a separate
safe setup command for existing repositories. Bundle the scaffold in the Python
distribution so it works outside this checkout. Teach the agent to use a complete
PRD as task input while preserving explicit acceptance criteria, independent plan
and code review, fresh executable verification and observed delivery.

## Current evidence

- `software_factory/engine.py:init` validates actual executable checks, refuses
  existing legacy or Markdown settings, writes `.rules/factory.md` exclusively
  and returns `config` and `next`.
- `software_factory/cli.py` has a flat command dispatcher. `start --task-file`
  reads UTF-8 text and sends it through the same task path as `--task`.
- `engine.start` requires criteria, deduplicates unfinished runs by task text,
  criteria, endpoint and base, and freezes task text in private state and `task.md`.
- `pyproject.toml` includes only the bundled skill Markdown as package data.
  No PRD resource, setup command or automatic criteria parser currently exists.
- `tests/test_rules.py` checks non-overwriting enrollment; `tests/test_lifecycle.py`
  checks task identity, recovery and frozen evidence; `scripts/smoke_install.py`
  exercises a real installed wheel outside source.

## Scope and chosen interface

Implement these behaviors in Python, using the standard library:

```sh
# New enrollment: existing command now also scaffolds prd/.
factory init --repo /path/to/app \
  --check '["python3","-m","unittest","discover","-s","tests"]' --json

# Existing enrollment, or standalone folder setup in a Git repository.
factory prd-init --repo /path/to/app --json
```

Use `prd-init` to fit the existing flat CLI rather than introducing nested command
parsing. It requires a Git repository but does not require or create factory
configuration, checks, a run, a branch, a commit or a PR. `init` retains all current
configuration validation and refusal behavior. Default PRD setup is additive for
new enrollments; existing runs/repositories change only when explicitly set up.

Do not add `--prd`, a Markdown/YAML parser, a `.factory.json` setting, a PRD state
schema or a new evidence key. Execute PRDs with existing `--task-file` and repeated
`--criterion` flags. This gives a complete folder workflow without introducing a
second task engine or weakening saved-run compatibility.

## Folder and template contract

The scaffold creates exactly two UTF-8 Markdown files:

```text
prd/
├── README.md
├── _template.md
└── 0001-feature-name.md      # authored later; not a generated sample
```

`prd/README.md` explains purpose, naming, authoring, readiness, task execution and
the boundary with `.rules/`, `design/` and private runs. PRDs use
`NNNN-short-description.md`; numbers are author-selected, not allocated by the
CLI. Files remain at their original paths throughout their lifecycle. Avoid
draft/ready/completed subfolders that would change task links.

`prd/_template.md` contains the following required headings and concise prompts:

```markdown
# NNNN — Product requirement title

Status: draft

## Problem and users
## Desired outcome
## Scope
## Non-goals
## User workflow
## Requirements
## Acceptance criteria
- AC1: [Observable behavior and how it will be checked]
## Constraints and compatibility
## Dependencies
## Verification
## Risks and open questions
## Delivery and follow-up
```

The template must distinguish requirements from implementation suggestions, ask
for observable criteria, require concrete checks and identify consequential open
choices. A ready PRD is self-contained: incorporate necessary linked constraints
and decisions so frozen task text includes them. Links are context, not recursively
loaded task inputs. Split oversized or unrelated work into separate ready PRDs.

Lifecycle labels are `draft`, `ready`, `in-progress` and `delivered`. They are
human/agent-maintained documentation, not enforced CLI states. Ready means no
blocking requirement decision or placeholder remains. In-progress requires an
actual run; delivered requires observed endpoint evidence and its commit/PR link.
Do not automatically change these labels or equate scaffold creation with a ready
requirement. Use `N/A` with an explanation for inapplicable sections.

PRDs describe **what and why**; `design/` specifies **how** where needed. A PRD
may link a design, but the agent's reviewed private plan remains required.
`.rules/` stays the instruction/configuration source; do not put settings fences
in generated PRDs or teach the CLI to execute Markdown instructions.

## Files and implementation responsibilities

| File | Change |
|---|---|
| `software_factory/prd.py` | New scaffold helper: resource reading, destination preflight and exclusive creation; no model calls or runtime task mutations |
| `software_factory/templates/prd/README.md` | Canonical portable folder guidance, including a complete synthetic execution example |
| `software_factory/templates/prd/_template.md` | Canonical template described above |
| `software_factory/engine.py` | Call scaffold helper from `init` after config validation/preflight; add a repository-scoped entry function for `prd-init` |
| `software_factory/cli.py` | Register help/dispatch for `prd-init`; render readable created/skipped output; retain error/JSON conventions |
| `pyproject.toml` | Add `templates/prd/*.md` to `software_factory` package-data, alongside existing skill data |
| `MANIFEST.in` | Explicitly include template Markdown in source distributions |
| `software_factory/skills/software-factory/SKILL.md` | Add authoring/readiness/intake guidance; preserve the existing plan-review/check/review/delivery loop |
| `software_factory/skills/software-factory/protocol.md` | Briefly document PRD text/criteria handoff and frozen-task semantics; retain exact artifact schemas |
| `prd/README.md`, `prd/_template.md` | Set up this repository using the implemented command; no invented ready example or copy of these designs |
| `tests/test_prd.py` | New scaffold/CLI/resource tests using temporary real Git repos |
| `tests/test_rules.py` | Extend enrollment regression coverage for generated PRD files and unchanged refusal/check behavior |
| `tests/test_lifecycle.py` | Add PRD task-file freeze/dedup/resume behavior coverage through the existing interface |
| `scripts/smoke_install.py` | Assert installed scaffold resources, new enrollment and existing-repo setup work outside source |
| Maintained setup/tasks/testing docs | Document the commands and workflow; use design 0001 paths if available, otherwise current README/testing paths |

Load templates with `importlib.resources.files("software_factory")`; do not read
from a repository-relative path or depend on the process working directory.

## Creation, compatibility and failure semantics

Resolve the actual Git root using the existing `repository()` helper, including
when `--repo` names a subdirectory or a linked worktree. Mutate only that root's
`prd/`, never another worktree, private runs or the user's installed skills.

Preflight both resource reads and all managed destination paths before writing.
Reject a symlink at `prd`, `prd/README.md` or `prd/_template.md`, a non-directory
`prd`, or a non-regular managed file. Do not follow redirected destinations.
Unrelated files within an existing `prd/` folder are not inspected or modified.
For a trusted local filesystem, repeat path checks before writes and create
missing managed files with exclusive mode `x`; this is not a security sandbox
against hostile concurrent filesystem replacement.

Existing regular managed files are skipped byte-for-byte, even if customized or
different from the bundled version. There is no force or upgrade option. Create
only missing files; do not delete user content or edit `.gitignore`. If a target
appears between preflight and exclusive creation, classify a regular file as
skipped; reject unsafe types. Return observed results instead of claiming writes
that did not occur.

`init` must detect invalid checks, existing legacy/Markdown configuration, unsafe
PRD paths and missing resources before any writes. An existing configuration
still returns exit 2 and creates no PRD files; direct the user to `prd-init`.
Keep `.rules/factory.md`'s exclusive creation and existing user conventions.

There is no cross-file transaction. An I/O failure after writes begin may leave a
valid configuration or a subset of scaffold files. Report partial paths in the
error message; do not delete them or claim rollback. Existing CLI error JSON
remains `error`/`code`: use `FactoryError(code="infrastructure")` and exit 3 for
write/resource failures, and exit 2 for invalid/unsafe input. Repair access and
rerun `prd-init` to fill missing files; if config creation also failed, rerun
`init` after resolving that error. Interrupted/rerun setup never overwrites files.

`prd-init --json` returns one object with stable keys:

```json
{
  "repo": "/path/to/app",
  "prd": "/path/to/app/prd",
  "created": ["prd/README.md", "prd/_template.md"],
  "skipped": [],
  "next": "Review the scaffold, author a PRD from _template.md, and commit the intended files."
}
```

Paths in `created`/`skipped` are repository-relative, sorted and disjoint; each
managed file appears exactly once on success. A second call returns empty
`created` and both paths in `skipped`, with byte-identical content.
This repository now has hand-authored PRDs and an index from a later documentation
request. Preserve those files; running setup here skips its existing README and
adds only a missing `_template.md`. These authored requirements are not generated
samples or proof that this feature has already been implemented.

`init --json` retains top-level `config` and `next`, and adds `prd` containing
the same scaffold result object. Its `next` mentions reviewing/committing settings
and the scaffold before starting. Account for the broader nested return type in
annotations; do not alter saved configuration or run version numbers. Existing
scripts that read `config` continue to work; document the additive JSON field.

## PRD-to-factory execution

1. Author a copy of `_template.md`. The agent may help write it when requested.
   Read all headings, resolve consequential choices, remove placeholders, and
   verify each criterion has an observable outcome and a proposed check.
2. Review and commit the ready PRD on the intended base before starting dependent
   implementation. This is workflow guidance; the existing CLI continues to
   support arbitrary task files. Do not introduce an implicit commit operation.
3. Read that exact PRD and relevant linked designs. Pass its full text using
   `--task-file` and every acceptance criterion using a separate `--criterion`,
   in document order. Keep criterion labels and meaning intact; the engine assigns
   its existing AC identifiers. Do not start a draft with unresolved choices.
4. Use the normal factory loop. The private `task.md`/state freeze the request;
   reviewers receive the task, explicit criteria and required instructions.
   A linked design's necessary implementation details go into the reviewed plan.
5. Resume the same run after interruption. Edits to the original PRD do not change
   frozen task text/criteria. A consequential requirement change requires user
   direction and a separately planned replacement task; never edit saved state.
6. Report actual endpoint evidence. Update repository PRD lifecycle only when
   requested or included in the reviewed change, before final verification/review
   if editing it within the task. Do not dirty an already delivered tree merely
   to mark a PRD delivered; record the observed link in a subsequent documentation
   change when appropriate.

The generated README includes a complete example using a synthetic one-criterion
PRD and a literal `--criterion`, portable paths and an approved worktree root. It
must not imply that `start` extracts criteria, validates lifecycle labels or
automatically commits/approves a PRD. Do not scan and start every ready PRD.

## Implementation sequence

1. Start from `main` after cleanup is available, or explicitly select the cleanup
   branch as a stack base. Use `feature/prd-folder-setup`; persist every criterion
   below and obtain a reviewed plan with scaffold and failure contracts.
2. Add packaged resources and a small helper; write meaningful tests for new
   filesystem behavior, then implement creation/preflight/error handling.
3. Integrate `init` and `prd-init` with JSON/human output and regression tests.
4. Add skill guidance and PRD task-file lifecycle tests. Set up this repository's
   folder, inspect generated text, and document installation/resource semantics.
5. Run required checks, build/install and smoke. Obtain fresh code review covering
   all criteria and deliver an observed draft PR to the selected base.

## Acceptance criteria

- **AC1:** Valid new-project `factory init` creates `.rules/factory.md` plus
  `prd/README.md` and `prd/_template.md` from packaged resources; existing check
  validation, config contents and top-level JSON `config` remain compatible.
- **AC2:** `factory prd-init` works in new and already enrolled Git repositories,
  including subdirectory/linked-worktree inputs, without changing configuration,
  HEAD, branches, the index, task state or unrelated files; only intended new
  scaffold files affect working-tree status, and human and JSON output match the
  specified created/skipped contract.
- **AC3:** Reruns and partial setups preserve existing regular files byte-for-byte
  and create only missing files; unsafe managed paths and preflight failures
  produce no writes, while write-time failures report partial results and recover
  through a rerun without overwriting or deleting user files.
- **AC4:** The generated template/guidance cover every required section, readiness,
  lifecycle, self-contained requirements, observable acceptance criteria and a
  correct task-file example; this repository has the two intended scaffold files
  with no generated ready PRD or duplicated design.
- **AC5:** A PRD passed through existing `--task-file` plus all explicit criteria
  freezes the task, preserves duplicate-start/resume behavior and remains unchanged
  after source PRD edits; normal review, verification and delivery gates still
  apply, and existing text/issue intake and historical runs remain compatible.
- **AC6:** Built wheel and sdist contain both PRD resources and the bundled skill;
  the installed smoke exercises default enrollment and repeat/existing-project
  PRD setup outside the checkout without Node/npm or third-party runtime packages.
- **AC7:** Both required repository checks pass on the final tree, a fresh review
  covers every criterion, and the observed draft PR targets `main` or the explicitly
  selected cleanup stack base; no merge, release or worktree deletion occurs.

## Verification matrix

| Area | Required executable evidence |
|---|---|
| Enrollment | Valid init makes all three files; invalid/empty checks and existing legacy/Markdown settings retain current failure behavior and create no scaffold |
| Idempotence | Empty, partial and customized folders; preservation of existing bytes, unrelated files, config, HEAD/index and run state; a no-op rerun preserves working-tree status |
| Unsafe input | Symlink directory, symlink managed file, file in place of directory, directory in place of managed file; reject before creating any missing peer |
| I/O and interruption | Inject resource/read or permission/write failure; assert error code and partial paths; retry creates only missing files; simulate exclusive-create collision |
| Repo resolution | Git root, nested input, paths containing spaces and linked worktree; non-Git input fails; original worktree is untouched |
| CLI | `prd-init` help, required repo, exact JSON shape, human created/skipped output, init additive JSON; error messages do not contain tracebacks |
| Task semantics | Temporary committed PRD started by CLI task-file with multiple criteria; same content deduplicates; original PRD edits leave saved request unchanged; resumed run completes existing verified local fixture lifecycle |
| Packaging | Inspect sdist/wheel; install into disposable venv; default init and repeated/existing-repo setup succeed outside source using bundled resources |

Use `tests.support.FactoryCase` and real temporary Git repos where relevant;
clearly label synthetic review fixtures. Fault injection belongs in tests, never
in production receipts. Keep tests focused on public behavior and preservation
of existing data, not implementation-specific call sequences.

Run `python3 scripts/verify.py tests`, `python3 scripts/verify.py source`, `uv build`
and the installed-wheel smoke in a disposable venv. Inspect package data directly
with Python `zipfile`/`tarfile`. No live application preview is needed unless the
actual selected worktree has an applicable enrollment. Live draft delivery is
verified by factory receipts, not inferred from synthetic tests.

## Risks, alternatives and exclusions

Default setup adds two files to enrollment; expose them clearly in `next` and
document that `prd-init` is the recovery/retrofit path. Customized files are never
upgraded automatically. Template drift can be handled by a later explicit review.
Per-file exclusive writes make reruns safe without pretending the setup is atomic.

An automatic criteria parser or dedicated PRD intake could add value later, but
would require a separately specified format, provenance/freshness model and
compatibility review. Folder setup plus the existing frozen task interface is
sufficient for this design.

Excluded: bulk PRD execution, nested command parser, lifecycle automation,
backlog scheduling, requirement state migration, changed evidence schemas,
template overwrite/upgrade, paid model APIs, deployment, merges and releases.
No consequential product decision remains open for this scope.
