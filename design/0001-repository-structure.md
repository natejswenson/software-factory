# 0001 — Clean up the repository structure

Status: ready for factory planning; implementation pending.

Baseline inspected: `447c49f0c09ca7a9d07a7bc92d1f4f3b35960fd2` on `main`.
Recheck the actual selected base before implementation; this is evidence, not a
requirement to reset the repository to this commit.

## Problem and outcome

The repository has a small, coherent Python package, but its documentation does
not clearly distinguish user instructions, contributor guidance, historical
designs and observations from earlier runs. The README carries almost all user
reference material. `docs/plans/` contains an initial Node design and two
verification narratives, even though the current implementation is Python.
The root `skills/software-factory` symlink adds a second route to files whose
canonical home is inside the installed package.

Make the repository easy to navigate and maintain: one canonical location for
each document, a short entry-point README, an explicit location for future
execution designs and preserved historical evidence. Keep package layout and
task behavior stable so the cleanup does not become an engine rewrite.

## Current evidence

| Location | Current responsibility or issue |
|---|---|
| `README.md` | Installation, enrollment, rules syntax, task commands, recovery, evidence limits and development all live together |
| `software_factory/` | Dependency-free runtime; `cli.py` dispatches, `engine.py` coordinates transitions, specialized modules own checks, Git, storage, rules and delivery |
| `software_factory/skills/software-factory/` | Canonical bundled `SKILL.md` and `protocol.md`; `factory skill-path` resolves here |
| `skills/software-factory` | Tracked relative symlink to the canonical bundled skill; current README links use this route |
| `docs/plans/` | Three historical files, including superseded Node setup instructions and a summary note explicitly awaiting final evidence |
| `docs/testing.md` | Behavioral mapping, migration proof and installed-wheel smoke instructions |
| `scripts/verify.py` | Stable repository checks; searches the current package, scripts and tests paths |
| `pyproject.toml`, `MANIFEST.in` | Setuptools package discovery, bundled skill data and source-distribution inclusions |
| `.rules/factory.md` | Actual tests/source commands and branch/completion rules |

The checkout has no `.dev/preview.json`; this CLI cleanup requires no application
preview. Runtime runs are already stored under the Git common-dir, outside source.

## Scope and decisions

1. Keep the flat `software_factory/`, `tests/` and `scripts/` layout. A `src/`
   migration or splitting the 555-line engine is unnecessary for this change and
   would introduce import and installed-package risks without solving navigation.
2. Make `docs/` the home for maintained explanatory documentation and explicitly
   labeled history. Make top-level `design/` the home for future implementation
   specifications. The `prd/` feature belongs to design 0002.
3. Keep `skills/software-factory` as a compatibility symlink. Change maintained
   links to the canonical package path; document the symlink's purpose instead of
   deleting a possibly installed integration.
4. Preserve historical document bodies, dates and claims. A migration note must
   say they are historical and that their Node commands are superseded; never
   turn a pending verification narrative into a completed delivery claim.
5. Change no CLI commands, module imports, package version, rules configuration,
   hash serialization, review schemas, run paths or delivery behavior.

## Target tree

```text
software-factory/
├── README.md
├── AGENTS.md
├── CONTRIBUTING.md
├── LICENSE
├── pyproject.toml
├── MANIFEST.in
├── .gitignore
├── .rules/factory.md
├── design/
│   ├── README.md
│   ├── 0001-repository-structure.md
│   └── 0002-prd-folder-setup.md
├── docs/
│   ├── README.md
│   ├── user-guide/
│   │   ├── installation.md
│   │   ├── project-setup.md
│   │   └── tasks-and-recovery.md
│   ├── reference/evidence.md
│   ├── development/
│   │   ├── architecture.md
│   │   └── testing.md
│   └── history/
│       ├── README.md
│       └── [three preserved historical documents]
├── software_factory/
│   ├── [existing Python modules]
│   └── skills/software-factory/{SKILL.md,protocol.md}
├── skills/software-factory → ../software_factory/skills/software-factory
├── scripts/{verify.py,smoke_install.py}
└── tests/[existing tests and fixtures]
```

Bracketed entries describe existing files; they are not literal filenames to
create. No empty future directories or generated build artifacts are added.
Preserve any additional designs and hand-authored `prd/` requirements present
when this cleanup executes; this illustrative tree is not a pruning instruction.

## Exact changes and content ownership

| File or move | Required content/change |
|---|---|
| `README.md` | Keep product explanation, task-loop diagram, prerequisites, one source-install example, one skill-install example and a quickstart; link to detailed docs, contributing and `design/README.md` |
| `CONTRIBUTING.md` | Python 3.11+, standard library runtime, setuptools, branch/base conventions, the two required checks, build/smoke pointers and reviewed draft delivery; point to `AGENTS.md` rather than maintaining another policy copy |
| `docs/README.md` | Navigation by user setup, task operations, evidence, development, history and execution designs |
| `docs/user-guide/installation.md` | Existing uv/pip install examples, source invocation, skill symlinks and npm-to-Python migration cautions |
| `docs/user-guide/project-setup.md` | Enrollment, complete Markdown settings example, `.rules` discovery/limits, precedence, legacy settings compatibility, committed-base requirements and frozen active settings |
| `docs/user-guide/tasks-and-recovery.md` | Existing start/intake, criteria, stack/base, branch rename, summaries, next/resume, recovery/locks, failure budget and delivery retry behavior |
| `docs/reference/evidence.md` | Freshness, tracked/ignored behavior, review/criteria, observed draft delivery, external-state limits and synthetic-versus-live distinctions from the current README |
| `docs/development/architecture.md` | Explain each current runtime module and the flow from CLI through state/evidence to delivery; distinguish source, `.rules`, specifications and private Git-common-dir runs |
| `docs/testing.md` → `docs/development/testing.md` | Preserve behavioral mapping and migration proof; correct relative links after move |
| `docs/plans/2026-10-02-software-factory.md` → `docs/history/2026-10-02-software-factory.md` | Preserve historical design body |
| `docs/plans/2026-10-02-software-factory-verification.md` → `docs/history/2026-10-02-software-factory-verification.md` | Preserve historical observation body |
| `docs/plans/2026-10-02-summary-verification.md` → `docs/history/2026-10-02-summary-verification.md` | Preserve pending/final-evidence distinctions |
| `docs/history/README.md` | Index the three documents; label historical Node guidance and observations; link to current Python setup/testing and the new design index |
| `docs/plans/README.md` | Compatibility pointer from the old directory to history and `design/`; no new designs go here |
| `MANIFEST.in` | Include `CONTRIBUTING.md` and recursively include `design/*.md` and existing `prd/*.md`; retain existing scripts/tests/docs/rules inclusions |

Update maintained internal links after moves, including README skill/protocol
links. Keep the bundled skill/protocol authoritative for execution instructions;
link to them rather than copying their artifact schemas into documentation.
Preserve every substantive user contract currently in README somewhere in the
maintained docs. Moving text must not simplify away rules limits or recovery
constraints. Historical external links remain unchanged unless factually invalid.

## Implementation sequence

1. Start an isolated factory run from `main`, branch
   `feature/repository-structure`, with every acceptance criterion below. Inspect
   current instructions, `.rules/`, tracked files and packaging rules.
2. Make a README-section-to-destination inventory in the private plan. Obtain
   plan review before editing. Check whether another change already moved a file.
3. Move the four documents, add navigation/contributor/architecture documents and
   split README content by the ownership table. Add packaging inclusions.
4. Review current links and paths, including the compatibility skill symlink.
   Make historical labeling explicit. Preserve any intervening contributor text.
5. Run verification, inspect distribution contents and obtain fresh code review.
   Deliver a draft PR; record its observed URL separately from design readiness.

## Acceptance criteria

- **AC1:** The maintained repository tree follows the target layout, with clear
  README, contributor and docs entry points and an accessible `design/` index;
  existing runtime module, test and script locations remain unchanged.
- **AC2:** Every substantive current README instruction is retained in the new
  maintained documentation or compact README, all local links in maintained
  documents resolve, and skill/protocol links use their canonical packaged paths.
- **AC3:** The four specified document moves preserve their historical or
  behavioral content; the history index labels obsolete Node guidance and pending
  verification accurately, and `docs/plans/README.md` points to the new locations.
- **AC4:** The compatibility skill symlink and installed `factory skill-path`
  behavior remain valid; CLI interfaces, runtime dependencies, frozen checks,
  evidence schemas and saved-run compatibility are unchanged.
- **AC5:** A built source distribution contains contributor guidance, design
  documents and reorganized docs; its wheel retains the bundled skill and runs the
  installed smoke outside the checkout with no Node/npm requirement.
- **AC6:** Both required repository checks pass on the final tree, a fresh review
  covers every criterion, and the observed draft PR targets `main` with no merge,
  release or worktree deletion performed.

## Verification and review

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source`.
Do not add runtime behavior tests for Markdown moves. Compare the README content
inventory to the resulting files; inspect renamed file diffs and every maintained
relative link. Use a temporary standard-library link scan or manual inspection;
do not introduce a dependency or a permanent checker for this documentation task.

Run `uv build`, inspect the sdist and wheel using Python's `tarfile`/`zipfile`,
install the wheel into a disposable venv and execute
`<venv>/bin/python scripts/smoke_install.py`. Review packaging and smoke results
explicitly; the existing source check only parses Python and detects Node files,
so it does not establish document links or distribution contents.

The reviewer checks navigation, retained contracts, accurate historical labeling,
packaging and compatibility. Do not claim GitHub delivery based on local smoke.
Use factory verification and reviews for final freshness; edits after checks or
review require fresh evidence.

## Risks, recovery and exclusions

Old deep links to moved historical files may change; preserve a directory-level
migration pointer and list exact old/new paths in the PR. The compatibility skill
symlink stays. If packaging omits documents, fix `MANIFEST.in` before delivery.
Do not rewrite current rules/checks to make the cleanup easier. Changes can be
reverted with ordinary Git changes; no runtime state migration is needed.

Excluded: source refactoring, `src/` layout, new CI, changing test frameworks,
deleting historical evidence, updating historical delivery claims, PRD
scaffolding, merges and releases. No consequential product decision remains open.
