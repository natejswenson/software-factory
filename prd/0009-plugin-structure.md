# 0009 — Simplify Software Factory into one installable plugin

Status: implementation under review in draft PR #18; not merged or released.

Documentation decision updated 2026-10-05: the user requested useful nested
guides with claude-skills PRESS branding, superseding the earlier flat-guide
proposal. The runtime/plugin ownership contract remains unchanged.

## Problem and users

People installing Software Factory should recognize the same plugin model used
in `natejswenson/claude-skills`. Today it is a Python package with a manually
linked skill, without native Claude or Codex plugin manifests or marketplace
catalogs. Updating the Python tool and updating the agent's loaded skill are
separate operations. An older command can also win through shell PATH order.

Contributors encounter two routes to the skill:
`skills/software-factory` is a symlink into
`software_factory/skills/software-factory`. Maintained documentation is spread
across several single-purpose subdirectories and indexes. The directory names
obscure which files are instructions, executable code, requirements or history.

The inspected v0.2.11 release has no empty source directories or observed
filesystem recursion. The complaint is a navigation and ownership problem;
generated caches, build folders and retained task worktrees are separate from
the source tree. Cleanup must not indiscriminately delete them.

## Desired outcome

Keep Software Factory in its own repository, as explicitly selected by the user.
Codex is the primary product, authoring and verification target; Claude is a
compatibility target. Make the repository one self-contained plugin with a shared
skill entrypoint, Codex metadata, a generated Claude adapter, and native
marketplace installation. Every maintained file has one clear home. The installed
plugin's instructions and engine come
from the same installed plugin root, even when a different global `factory`
command exists.

## Scope

- Make the repository root the single `software-factory` plugin root. Author the
  Codex manifest/catalog and generate the Claude manifest/catalog for compatibility.
- Make `skills/software-factory/{SKILL.md,protocol.md}` regular, canonical source
  files. Keep the Python modules flat in `software_factory/`, tests in `tests/`
  and all repository tooling in `scripts/`.
- Provide a small Python launcher for plugin execution from any working
  directory. Keep the standalone installed `factory` command supported.
- Generate wheel copies of the skill from its canonical source during the build;
  do not maintain a second authored copy inside the Python package.
- Keep useful nested documentation under `docs/user-guide/`, `docs/reference/`
  and `docs/development/`, with one task-oriented `docs/README.md` index. Match
  claude-skills PRESS Markdown branding using generated pinned mastheads.
  Preserve the three historical bodies in `docs/history/` and original numbered
  specifications in `prd/` and `design/`.
- Add checks for metadata drift, directory ownership, distribution resources
  and plugin execution/update compatibility. Document migration and recovery.

## Non-goals

Moving into claude-skills, creating a multi-plugin monorepo, dividing the engine
into more packages, changing task behavior or proof semantics, adding model APIs,
MCP servers, hooks, Node dependencies or automatic dependency installation.
No sweeping deletion of ignored files, personal configuration, runs or worktrees.
Submitting to a public plugin directory and creating a new release process are
outside this change; existing automatic repository release behavior is retained.

## User workflow

1. Add `natejswenson/software-factory` as a marketplace in the selected host and
   install `software-factory@software-factory`. A local checkout also works as a
   marketplace for development.
2. Start a fresh session and invoke the shared software-factory skill. It uses
   the Python engine inside that installed plugin, with Python 3.11+ and Git.
   GitHub delivery still needs authenticated `gh`; local work does not.
3. Run tasks through the existing investigated plan, review, verification and
   observed delivery gates. Private run state remains in the task repository's
   Git common-dir, never in the plugin cache.
4. Refresh and update through the host's supported plugin controls, then reload
   the session. Confirm the loaded root and actual changed skill/runtime files;
   a successful refresh message alone does not prove activation.
5. Standalone CLI users may continue installing the Python wheel with uv/pip and
   locating its bundled skill with `factory skill-path`.

If required executables or bundled resources are missing, report the concrete
problem before starting a task. A failed plugin update preserves saved tasks;
repair installation or return to the previous known source revision without
editing receipts or replacing an active task's frozen checks.

## Requirements

- The plugin root is the repository root, with no additional
  `plugins/software-factory` or `skills/software-factory/skills` wrapper. Both
  catalogs identify exactly this root using a contained relative source.
- Reuse the claude-skills shared-entrypoint and deterministic metadata pattern,
  reversing its authoring direction for this Codex-primary product. The Codex
  manifest/catalog are authoritative; Python tooling generates Claude-compatible
  fields and checks drift. Both expose the same name, description and shared
  skill. Components are declared only when they exist. Codex-specific behavior
  must not be removed merely to simplify the Claude adapter; unsupported mappings
  fail explicitly and require a reviewed compatibility decision.
- Git-distributed manifests/catalog entries intentionally omit a fixed plugin
  version. Claude can then identify updates by source commit; Codex's native
  refresh/load behavior must also be demonstrated. Python package versions
  remain derived from existing release tags. Do not introduce a constant manifest
  version that prevents updates or a bot commit that modifies reviewed source.
- Resolve engine and resources from the physical loaded plugin/package location,
  not the current directory, a development checkout, or an unrelated executable
  on PATH. Preserve the caller's explicit target repository and run arguments.
- Each skill document has one authored source. Wheel copies are generated
  distribution resources, byte-identical to that source, and are not committed.
  Installed `factory skill-path` remains usable; source invocation resolves the
  new regular skill directory. Retain the real PRD templates inside the package.
- Each directory must contain actual maintained content or be required by a host
  convention. Avoid empty scaffolds, speculative extension points, directory
  symlink aliases and cycles. The layout check inspects source ownership without
  walking ignored caches or deleting anything.
- Preserve all substantive user guidance, historical evidence, numbered PRDs,
  designs, runtime interfaces and saved-run formats. Repair maintained local
  links after moves. Historical text remains labeled as historical.
- Keep one authoritative repository policy in AGENTS.md and existing `.rules/`.
  Plugin packaging does not confer permission to merge, publish, capture private
  memory, change accounts or create previews.

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
- **AC6:** The nested maintained guides preserve all current user/contributor
  contracts and have resolving maintained links; historical documents and all
  existing numbered PRDs/designs are retained, with a clear migration guide for
  native plugins, standalone CLI users and legacy manual skill links.
- **AC7:** Both required repository checks and meaningful new Python layout,
  metadata, packaging and launcher tests pass on the final implementation; fresh
  reviews cover every criterion and delivery is an observed draft PR targeting
  main, with no manual merge, release, task-state edits or worktree deletion.

## Constraints and compatibility

Python 3.11+, macOS/Linux, a dependency-free runtime and the standard setuptools
backend remain supported. Preserve CLI arguments and output contracts, importable
Python modules, artifact schemas, freshness hashes, run locations, historical
branches, original check argv and recovery/delivery behavior.

Adopt a single-plugin layout, not every monorepo-specific directory or release
tag convention in claude-skills. Preserve this repository's existing `vX.Y.Z`
tags, protected-main automation and release checksums. Adding native plugin
support does not require a new independently installed engine for plugin users.

## Dependencies

Implement from current main, including the features already shipped through
v0.2.11. The drafting checkout is older and has pre-existing edits; it is not the
implementation baseline. Design 0009 supplies the concrete tree, moves, build
adapter, launcher and verification sequence. These requirements include the
essential decisions because task intake does not recursively read linked files.

## Verification

Run `python3 scripts/verify.py tests` and `python3 scripts/verify.py source`.
Add the proposed `python3 scripts/plugin_metadata.py --check` and
`python3 scripts/check_layout.py` to source verification. Build wheel and source
archives, rebuild from the extracted source archive, compare resource bytes,
and run installed/copy-only lifecycle smoke tests under Python 3.11 and a current
supported Python on macOS/Linux. Test paths containing spaces, missing resources,
read-only plugin roots, conflicting PATH commands and rejected manifest fields.

Validate Codex first with native tooling and separately observe discovery,
installation, update and session activation; then verify the Claude compatibility
adapter. Use temporary test marketplaces and
supported test profiles; do not overwrite real plugin records. File/schema tests
are useful but do not substitute for observed host loading. Do not launch models
to verify loading. Record unavailable native verification honestly and leave its
criterion outstanding.

## Risks and open questions

The consequential choices are resolved: keep this repository and build primarily
for Codex, retaining Claude compatibility. The main
risks are host update caching, source-versus-wheel resource resolution, packaging
hooks and legacy manual links. A copied plugin may have no Git metadata, so
diagnostics must not present a fallback Python version as a verified release.
Native host proof is required before claiming the update path works. A failure
requires a revised reviewed plan, not a silent new versioning policy.

## Delivery and follow-up

This document and its matching design are authored specifications, not an engine
migration. Review and commit the pair on the intended base before starting the
implementation run. Use `feature/plugin-structure` from main and submit every
complete AC as a separate criterion. Deliver a reviewed draft PR with tree,
package and host-load evidence. Change lifecycle labels to delivered only after
an observed endpoint; installation changes on a user's machine are a separately
requested follow-up.
