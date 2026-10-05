# 0009 — Repository-root plugin and simpler source ownership

Status: ready for factory planning; proposed change, implementation pending.

Product contract: [PRD 0009](../prd/0009-plugin-structure.md).

## Evidence and baseline

Inspected Software Factory release v0.2.11 at
`bbe48d592ef507a1517f53de2bef7ad2a49f009a`, its packaging/CLI/resources/release
code, and the claude-skills marketplace, issuecreator/city-report plugin manifests
and metadata tooling. Reinspect the selected main baseline before implementation;
the current drafting checkout predates these shipped features.

| Inspected source | Finding |
|---|---|
| Software Factory `software_factory/cli.py` | skill-path returns a directory inside the package |
| `skills/software-factory` | A compatibility symlink to the same skill; no native plugin manifests exist |
| `pyproject.toml`, `MANIFEST.in` | Standard setuptools, tag-derived version, bundled skill and PRD template resources |
| `software_factory/prd.py` | Reads actual packaged PRD templates with importlib.resources |
| `docs/` | Multiple navigation layers: user-guide, reference, development, history and plans |
| `scripts/release.py` | Chooses releases from tags and publishes verified wheel/source/checksum assets |
| claude-skills catalogs and per-plugin manifests | Shared skill entrypoints, authored Claude metadata, generated Codex metadata |
| claude-skills `tools/sync_codex.py` | Useful generation model, but hardcodes its monorepo paths; do not copy unchanged |

No empty source directories or filesystem cycles were observed in the inspected
release. Retained local worktrees and build/cache directories are operational
data, not candidates for a source reorganization.

The user explicitly selected a standalone repository and reaffirmed Codex as
the primary target. Promote the **per-plugin root pattern** in claude-skills to
this repository root, with Codex metadata authoritative and Claude generated as
an adapter. Do not reproduce the outer monorepo wrapper or its Claude-first
metadata ownership.

## Target source tree

```text
software-factory/                    # repository AND plugin root
├── .codex-plugin/plugin.json         # authored primary plugin metadata
├── .agents/plugins/marketplace.json  # authored catalog: source.path ./
├── .claude-plugin/
│   ├── plugin.json                  # generated Claude adapter
│   └── marketplace.json             # generated catalog: source ./
├── .github/workflows/               # existing automation
├── .rules/factory.md                # existing repository settings
├── AGENTS.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── pyproject.toml
├── MANIFEST.in
├── .gitignore
├── skills/
│   └── software-factory/
│       ├── SKILL.md                 # sole authored entrypoint
│       └── protocol.md              # sole authored artifact protocol
├── software_factory/
│   ├── [existing flat Python modules]
│   └── templates/prd/{README.md,_template.md}
├── scripts/
│   ├── [existing verification and automation tools]
│   ├── factory.py                   # plugin-bound launcher
│   ├── plugin_metadata.py           # deterministic sync/check
│   ├── check_layout.py              # read-only source ownership check
│   └── build_resources.py           # setuptools build_py extension
├── tests/
│   ├── [existing tests and fixtures]
│   ├── test_plugin_metadata.py
│   ├── test_plugin_launcher.py
│   └── test_layout.py
├── docs/
│   ├── installation.md
│   ├── usage.md
│   ├── evidence.md
│   ├── development.md
│   ├── automation.md
│   └── history/[three preserved historical documents]
├── prd/{README.md,_template.md,numbered requirements}
└── design/{README.md,numbered designs,improvement-evidence.md}
```

Bracketed entries mean existing real content, not placeholder files or new
directories. Keep the package's real template nesting because it expresses a
resource type and is already consumed by runtime code. Keep tests and tooling at
the root for direct unittest/source verification. No src/ migration, tools/
directory, extra plugin wrapper, hooks/, agents/, assets/ or MCP scaffolding.

The only intentional skill nesting is `skills/<skill>/`, which hosts discover.
The plugin directory includes its engine; it never imports sibling repositories
or content outside the installed root. Marketplace source `./` refers to that
directory and does not cause a filesystem link or recursive source traversal.

## Metadata and update contract

Use `.codex-plugin/plugin.json` as the authored identity/description source:
name `software-factory`, author Nate Swenson, MIT license, existing repository/
homepage URLs, `skills` set to `./skills/`, and minimal interface fields matching
the current Codex catalog conventions. Make Codex setup, tool mapping, native
reviewers and discovery the default shared-skill instructions. Generate the
Claude manifest from supported shared descriptive fields; its default skills
discovery uses the same root entrypoint. Explicitly conditional Claude guidance
must not displace the primary Codex workflow.

The authored Codex catalog is named `software-factory`, with one plugin entry
whose source is
`{ "source": "local", "path": "./" }`, installation `AVAILABLE`, authentication
`ON_INSTALL` and category `Productivity`, following the existing catalog shape.
That policy field does not create an external authentication service. Generate
the Claude catalog with matching identity and the one plugin entry
`{ "name": "software-factory", "source": "./" }`, plus owner/description metadata.
Both Claude files in the target tree are generated, not independently edited.
No hooks, remote connections or capabilities are declared without a real component.

Implement `scripts/plugin_metadata.py` with default sync and read-only `--check`.
Resolve paths from the script, validate names/field types/contained real paths,
refuse unsupported host components, and compare deterministic UTF-8 JSON output.
It must not change user configuration or derive a root from arbitrary CWD.
Adapt the reference generator to one root and reverse its direction: authored
Codex inputs, generated Claude outputs. Its monorepo membership/basename checks
are inappropriate here. Unsupported Codex component fields require an explicit
Claude adapter or documented host-specific behavior; never silently discard the
primary capability to force compatibility.

**Git plugin revision and Python release version are distinct labels for the
same source, not separately maintained release numbers.** Omit `version` from
both Git host manifests and catalog entries. Do not add a version to SKILL.md.
Claude uses the Git source revision when version fields are absent; a fixed
manifest version can otherwise keep an old cached copy despite newer commits.
This behavior is documented in the [Claude loading reference](https://code.claude.com/docs/en/plugins/loading#how-claude-code-computes-the-version).

Keep setuptools-scm and existing `vX.Y.Z` release selection/checksum handling.
No new metadata commits, duplicate version constant or change to automatic-main
release semantics. Git plugin installs track their selected source/ref and native
cache identity; wheel installs keep their tag-derived package version. Confirm
Codex's actual update behavior with two Git revisions before accepting this
strategy. Do not infer active code from either a manifest label or a fallback
`__version__` when a copied plugin has no generated version file.

The compatibility manifest and root skill conventions are supported by
[OpenAI's plugin packaging guidance](https://developers.openai.com/plugins/build/plugins).
Use the requested claude-skills adapters here; adopting a third portable manifest
format or public-directory publication is a separate task.

## Plugin execution and resources

`scripts/factory.py` is a thin Python launcher, not another engine or installer.
It resolves its own real path, determines the plugin root, disables bytecode
writes before imports, and imports `software_factory.cli` from that root. Verify
the imported module is inside that exact package before dispatch. Delegate
unchanged argv and exit handling to the existing CLI. Do not chdir into the plugin
or consult a global factory executable. Required files missing from the loaded
root produce a clear failure; there is no fallback to another checkout.

Update SKILL.md to select execution by distribution:

- A root-discovered native plugin uses Python plus the absolute bundled
  `scripts/factory.py` path resolved from the loaded SKILL.md.
- A wheel-bundled skill continues using its installed Python CLI as documented;
  verify that command resolves to the package containing that skill rather than
  allowing an unrelated PATH command. Resolve the matching environment executable
  when available; if it cannot be established, stop with setup guidance.
- Direct source development may keep `python3 -m software_factory` from the
  repository root. These are adapters to one engine, not parallel implementations.

Treat the user's repo/run/worktree paths as separate explicit inputs. The plugin
root never becomes the target application by inference. Keep memory and preview
hooks conditional on actual host/user instructions. This CLI has no enrolled
`.dev/preview.json` and needs no application preview for restructuring.

Keep packaged PRD resources at `software_factory/templates/prd/` and preserve
their current behavior. Change `factory skill-path` resolution only as necessary:
an installed wheel returns its generated internal skill resource directory;
source/plugin execution returns the regular root skill directory. Select by
trusted package/source layout markers and exact ownership, not the user's CWD or
an arbitrary first matching directory. Missing/incomplete resources are errors.

## Python distributions without duplicate authored files

Move the canonical skill/protocol to the regular root directory, replacing the
old symlink. Remove the old authored package copies and obsolete
`software_factory/skills/__init__.py`; preserve Python engine module locations.

Use the standard setuptools backend with a Python `build_py` command extension
in `scripts/build_resources.py`, declared through setuptools' cmdclass mapping.
It copies the two canonical files into the build output at
`software_factory/skills/software-factory/`. This generated wheel-internal path
preserves existing installed skill links and `factory skill-path` consumers;
it is not a second source directory to browse or edit.

The extension must declare source inputs and output files correctly, refresh
copies on rebuild and fail when required source is missing. It writes only into
the selected build output, never creates package-resource copies in the source
tree. Include the root skill, manifests/catalogs and build adapter in MANIFEST.in,
so extracted source distributions can build the same complete wheel. Preserve
the existing PRD package-data declaration. Test wheel membership instead of
assuming that copy operations guarantee archive inclusion.

No custom build backend, runtime dependencies, checkout-only symlink trick or
editable-install-only proof. Source, copied plugin, wheel and rebuilt source
archive must all work. Continue installed smoke tests with Node/npm absent.

## Documentation moves and ownership

| Existing latest-main file | Destination/action |
|---|---|
| `docs/user-guide/installation.md` | `docs/installation.md`; lead with host plugin installation; retain uv/pip/source and migration instructions |
| `docs/user-guide/project-setup.md` | Merge into `docs/usage.md`; retain every settings, rules, scaffold and frozen-check constraint |
| `docs/user-guide/tasks-and-recovery.md` | Merge into `docs/usage.md`; retain all current commands and recovery semantics |
| `docs/reference/evidence.md` | `docs/evidence.md`; preserve proof/freshness/observation limits |
| `docs/development/architecture.md` | `docs/development.md`; explain the ownership tree, adapters and flat engine |
| `docs/development/testing.md` | Merge into `docs/development.md`; retain behavior mappings and runnable verification/build instructions |
| `docs/development/automation.md` | `docs/automation.md`; retain CI, reviewed changes, protected main and automatic release contracts |
| `docs/history/*.md` | Retain the three historical bodies; add clearly labeled history links in development.md |
| `docs/history/README.md`, `docs/README.md`, `docs/plans/README.md` | Remove redundant indexes after transferring unique context and updating incoming maintained links |
| `README.md`, `CONTRIBUTING.md` | Short entrypoints linking directly to the five docs, shared skill, requirements and designs |
| `prd/`, `design/` | Keep stable filenames/content and their useful task indexes; preserve all intervening documents |

Prepare an inventory of substantive content before merging files. Repository
navigation belongs in root README, operation detail in usage, proof limits in
evidence, contributor/build detail in development, automation in automation.
SKILL.md and protocol.md own agent execution and review artifact schemas; docs
link to them instead of copying the complete schema. PRDs answer what/why and
designs answer how; do not combine or erase those roles.

Remove only source directories left empty by reviewed moves. Do not recursively
remove arbitrary empty local directories or rewrite historical narratives to
claim new outcomes. Old documentation URLs receive a move map in the migration
guide; avoid retaining whole empty compatibility directory trees. Existing
design 0001 records the earlier cleanup; this design supersedes its future path
retention choices without retroactively invalidating that delivered change.

## Installation and migration

Document the planned native marketplace commands, validated against the actual
host versions during implementation:

```sh
# Codex, terminal
codex plugin marketplace add natejswenson/software-factory
codex plugin add software-factory@software-factory

# Claude Code, terminal
claude plugin marketplace add natejswenson/software-factory
claude plugin install software-factory@software-factory
```

Use `$software-factory` in Codex and the host-discovered software-factory skill
in Claude, including its plugin-qualified name where required. Use a fresh
session after installation/update. Keep host-specific reload/refresh instructions
based on observed CLI help and native behavior, not invented universal flags.

Migration order: install and validate the native plugin; identify any same-named
legacy manual skill links; disable only the known superseded link when switching
that user's active discovery route; verify a fresh session loads the plugin.
Never remove regular directories, unrelated plugins or standalone CLI installs
automatically. Manual wheel skill links remain a supported alternative. Current
wheel links keep the generated internal package path. Source links into the old
authored package directory must be explicitly repointed to root skills.

Installation, disk update and session activation are separate observations.
Preserve user settings and saved runs on failure. A copied plugin works offline
after fetching, assuming required Python/Git executables are present. No hook
installs dependencies or silently modifies shell PATH.

## Layout check and executable verification

Add a small read-only `scripts/check_layout.py`. Check the owned source paths,
one authored skill/protocol, contained catalog paths, no authored skill alias,
no nested monorepo wrappers and no `.gitkeep`/empty speculative source scaffolds.
Use the Git file inventory to distinguish source from ignored/generated content;
inspect untracked candidate source in reviewed changes as appropriate. Never
follow directory symlinks recursively or traverse Git internals, worktree data,
build output or caches. Report specific paths; perform no deletion.

Extend source verification to invoke this check and metadata drift checking.
Add assertion-based Python tests for supported fixtures and meaningful failures;
do not assert file counts, module line limits or an incidental exhaustive tree.

| Check | What it establishes |
|---|---|
| Metadata tests/check | Shared identity, deterministic generated adapter/catalog, root source containment and drift/unsupported-field rejection |
| Layout tests/check | One authored source and clear real folder ownership; cycles/aliases/placeholders fail without touching user files |
| Launcher tests | Exact root imports, explicit target preservation, arbitrary CWD, spaces, read-only roots and conflicting PATH |
| Copy-only lifecycle smoke | Plugin contains its own engine/resources; complete synthetic local delivery works without a global install or Node/npm |
| Packaging tests/build smoke | Wheel and extracted-sdist rebuild include canonical skill bytes and real PRD resources; installed skill-path and lifecycle work |
| Maintained-link/content review | All moved contracts survive and relative links resolve; history and stable specs are preserved |
| Native host validation/load/update | Codex discovery and two-source-revision activation first, followed by Claude adapter validation; schema checks alone prove less |
| Existing tests/source checks | Runtime/saved-task regressions remain covered on final implementation |

Native host tests use supported isolated profiles and temporary Git marketplaces,
not hand-edited personal installation records. Exercise revision A then revision
B with an observable changed skill and harmless runtime marker, refresh/update,
start/reload the host and inspect the loaded copy. Include missing resource and
stale global executable cases. No model invocation is needed. If native testing
is unavailable, retain an outstanding criterion rather than claiming both hosts
are supported from JSON validation alone.

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source`, then
the actual distribution build/rebuild and both plugin/installed smoke routes.
Support Python 3.11 and current Python on macOS/Linux. Update CI/release resource
inclusions and tests, preserving stable required checks and release asset names.
Any implementation commit must satisfy the current repository's meaningful
Python unittest change policy, including commits with metadata/docs changes.

## Implementation sequence and review

1. Commit/review this specification pair on the intended current main base.
   Start `feature/plugin-structure` as one factory task with every complete AC.
   Inventory source, existing rules, docs, packaging and installed integration
   assumptions; obtain independent plan review through the factory protocol.
2. Add authored Codex metadata and deterministic Claude generation/check tests.
   Prove native Codex root-source discovery before the rest of the migration;
   then test the compatibility adapter in Claude.
3. Move the skill to its canonical regular source directory; implement the thin
   launcher, source/installed skill-path selection and tested build adapter.
   Preserve engine interfaces and original packaged PRD resource behavior.
4. Flatten docs according to the content inventory, repair links, document
   migration and add the small ownership check. Preserve historical/spec bodies.
5. Build wheel/source archives and rebuild an extracted source archive; execute
   both lifecycle smoke routes and observe native host updates across revisions.
6. Run final checks, inspect the full diff and obtain fresh code review covering
   all acceptance criteria, update behavior, package bytes and missing-resource
   failures. Deliver the observed draft PR; preserve task/worktree receipts.

Keep run-specific plans, review contexts, test logs and native observation
receipts in private run storage. No edits to this specification implement the
layout. Do not start other backlog tasks, remove worktrees or perform manual
merges/releases as part of writing or delivering this pair.

## Acceptance criteria

- **AC1:** The repository is one standalone Codex-primary plugin with authoritative
  Codex metadata and generated Claude-compatible manifests/catalogs pointing to
  its root; native discovery exposes the same shared software-factory skill in
  both hosts without monorepo wrappers, and the primary workflow and setup docs
  lead with Codex.
- **AC2:** Exactly one authored SKILL.md and protocol.md exist at the regular
  `skills/software-factory/` source directory; runtime, tests, scripts, PRDs and
  designs follow the ownership contract, with no source directory aliases,
  recursive links, empty placeholders or duplicated documentation indexes.
- **AC3:** From an unrelated working directory, a copied plugin runs its own
  Python engine and complete synthetic local task lifecycle without an installed
  global factory, Node, npm, paid model calls or writes into the plugin root; a
  conflicting global factory cannot change which engine it runs.
- **AC4:** Native host installation and update observations show that two distinct
  Git source revisions load their respective changed skill and engine after
  refresh/session reload; missing resources fail clearly, and generated metadata
  checks catch drift without requiring fixed manifest versions or changing the
  existing tag-derived Python release policy.
- **AC5:** Wheel and source distributions build from the canonical sources; a
  wheel rebuilt from the extracted source archive contains byte-identical skill
  documents and working PRD templates, installed skill-path resolves, and the
  installed lifecycle smoke passes outside the checkout with Node/npm absent.
- **AC6:** The five maintained docs preserve all current user/contributor
  contracts and have resolving maintained links; historical documents and all
  existing numbered PRDs/designs are retained, with a clear migration guide for
  native plugins, standalone CLI users and legacy manual skill links.
- **AC7:** Both required repository checks and meaningful new Python layout,
  metadata, packaging and launcher tests pass on the final implementation; fresh
  reviews cover every criterion and delivery is an observed draft PR targeting
  main, with no manual merge, release, task-state edits or worktree deletion.

These criteria match PRD 0009. Supply this full design to the planning agent and
carry its contract into the reviewed private plan; the task file does not
automatically import linked content.

## Risks and delivery

Main risks are source-root cache copying, native revision detection, build input
declarations and legacy manual skill shadowing. Retain working native profiles
and standalone wheel installs while verification runs. Installation rollback
selects the prior known plugin source; saved task state is untouched. Changing
metadata/version semantics after a host test failure requires a reviewed plan
change and fresh proof.

The implementation endpoint is a draft PR on main, with observed head/base and
the concrete verification evidence above. No delivery link exists yet. This
document is ready for planning, not implementation approval or shipped behavior.
