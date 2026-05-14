# Changelog

All notable changes to scry are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2026-05-14

### Added

- **`scry_mint` now returns collision warnings** — `mint()` service function
  and `scry_mint` MCP tool return `tier1_collisions` and `tier2_neighbors`
  alongside the freshly-minted ID when matching markers exist in the DB.

  - **Tier 1** (`tier1_collisions`): markers with the same prefix already in
    scry. If a tier-1 hit is the same logical concept, abandon the new ID and
    reference the existing one — stranded IDs pollute scry.
  - **Tier 2** (`tier2_neighbors`): markers in the same kind + first-segment
    family (informational; may reveal related prior work).
  - `bind` minting is exempt — bind IDs are file-scoped, no global collision
    semantics apply.

  This makes `scry_mint` equivalent to the previously-separate
  `scry_mint_with_check` wrapper, unifying the two call sites.

### Internal

- `_check_collisions(conn, kind, prefix)` added to `scry/service/mint.py`.
- `_SUMMARY_COL` mapping added to support per-table summary column lookup.
- 10 new tests covering tier-1 exact-prefix collisions, tier-2 family
  neighbors, tier-1/tier-2 disjointness, bind exemption, and anchor kind.
- 91/91 tests pass.

---

## [0.8.0] - 2026-05-14

### Changed

- **Parser delegated to `scry-parse`** — the inline parsing engine in
  `src/scry/domain/markers.py` is replaced by a thin adapter over the
  `scry-parse>=1.0.0` library. This makes `scry-parse` the single source of
  truth for scry-spec v1.0 parsing semantics; spec updates now flow through
  one library rather than two parallel implementations.

- **`requires-python` bumped to `>=3.11`** — required by `scry-parse`.

- **`STATUS_VALUES` now sourced from `scry_parse.BASELINE_STATUSES`** —
  guarantees consistency between scry-mcp's mint hints and the spec library.

- **Mixed inline+block bind behavior** (FR2 mutual exclusion): the inline
  parser silently skipped these markers; scry-parse accepts-and-discards
  (uses the inline comment, ignores the block body). Both behaviors are
  spec-conformant — the spec's MUST NOT is against producing *two* records,
  not against producing one.

### Added

- `scry-parse>=1.0.0` runtime dependency.

### Removed

- Inline parsing engine (~250 lines of custom regex/YAML parse loop). Parsing
  logic now lives in `scry-parse`. The `strip_markers_from_content` function
  (used by `scry_scrub`) remains local — `scry-parse` has no strip API.

### Internal

- 83/83 tests pass against the new adapter.

---

## [0.7.0] - 2026-05-14

### BREAKING CHANGES

**Replaced `@scry.impl` / `@scry.test` with `@scry.bind` (scry-spec v1.0 FR2).**

The parser no longer recognizes `@scry.impl` or `@scry.test` line markers.
Scry now recognizes exactly three marker kinds:

- `@scry.entry` (block) — unified knowledge-graph entry
- `@scry.anchor` (block) — named code location bookmark
- `@scry.bind` (line or block) — universal binding marker (replaces impl + test)

**Database tables `scry__impl` and `scry__test` are dropped** (migration 004).
Data from these tables is not migrated — these were index tables rebuilt from
source scans. Re-run `scry surface` after upgrading to repopulate `scry__bind`.

**`scry__doc` kind and status columns no longer have CHECK constraints.**
Unknown kind and status values are preserved as-is (FR8/FR9).

If you have files with `@scry.impl` or `@scry.test`, migrate them:

```bash
# @scry.impl validate-jwt~a1b2c3d4 spec.auth~xyz#FR3
# becomes:
# @scry.bind validate-jwt~a1b2c3d4 spec.auth~xyz#FR3

find . -name "*.py" -o -name "*.ts" | xargs sed -i \
  -e 's/@scry\.impl/@scry.bind/g' \
  -e 's/@scry\.test/@scry.bind/g'
```

### Added

- **`@scry.bind` marker** — universal binding marker per scry-spec v1.0 FR2.
  Replaces the separate `@scry.impl` and `@scry.test` markers with a single
  generic binding that relates any source to any target artifact or anchor.
- **Block form for `@scry.bind`** — multi-line commentary via
  `@scry.bind {local-id} {ref}` + free-form text + `@scry.bind.end`.
- **Comma-expanded loose anchors** — a single `@scry.bind` with
  `spec.auth~xyz#FR1,FR2,FR3` expands to three binding records.
- **Optional `comment` field** — free-form text after the ref on single-line
  form is indexed and queryable.
- **`scry__bind` table** — stores binding records with `local_id`, `ref`,
  `comment`, `file_path`, `content_hash` fields.
- **Migration 004** — creates `scry__bind`, drops `scry__impl`/`scry__test`,
  and relaxes `scry__doc` kind/status constraints.
- **Kind preservation (FR8)** — unknown kind values are stored as-is;
  no silent coercion to `internal`.
- **Status preservation (FR9)** — custom status values preserved as-is.
- **v1.0 baseline statuses** — `STATUS_VALUES = ("draft", "active", "deprecated")`.

### Removed

- `@scry.impl` line marker — replaced by `@scry.bind`.
- `@scry.test` line marker — replaced by `@scry.bind`.
- `ImplMarker` / `TestMarker` dataclasses — replaced by `BindMarker`.
- `ParseResult.impls` / `ParseResult.tests` fields — replaced by `ParseResult.binds`.
- `upsert_impl()` / `upsert_test()` surface helpers — replaced by `upsert_bind()`.
- `scry__impl` and `scry__test` tables.
- Kind coercion: unknown kinds no longer silently map to `internal`.
- Old status values `approved`, `stale`, `complete` from `STATUS_VALUES`
  (these continue to work as custom values and are preserved as-is).

## [0.6.0] - 2026-05-14

### BREAKING CHANGES

**Removed legacy `@scry.doc` and `@scry.file` markers (scry-spec v1.0).**

The parser no longer recognizes `@scry.doc` or `@scry.file` block markers.
Scry now recognizes exactly four marker kinds:

- `@scry.entry` (block) — unified knowledge-graph entry
- `@scry.anchor` (block) — named code location bookmark
- `@scry.impl` (line) — implementation linkage
- `@scry.test` (line) — test linkage

If you have files with legacy markers, migrate them:

```bash
find . \( -name "*.md" -o -name "*.py" \) | xargs sed -i \
  -e 's/@scry\.doc\.end/@scry.entry.end/g' \
  -e 's/@scry\.doc/@scry.entry/g' \
  -e 's/@scry\.file\.end/@scry.entry.end/g' \
  -e 's/@scry\.file/@scry.entry/g'
```

### Added

- **scry-spec v1.0 conformance** — four marker types only; no legacy aliases.
- **Extended baseline kinds** — `DOC_KIND_VALUES` now includes `lesson`,
  `report`, `audit`, `research`, and `code` in addition to the original seven.
  Unknown kinds map to `internal` instead of being rejected.
- **Database migration 003** — drops `scry__file` table (and its FTS/triggers),
  recreates `scry__doc` with the expanded kind `CHECK` constraint.

### Removed

- `@scry.doc` marker support (parser, mint, tests, README examples)
- `@scry.file` marker support (parser, mint, tests, README examples)
- `FileMarker` dataclass
- `ParseResult.files` field
- `upsert_file` function
- `scry__file` table, `scry__file_fts` FTS table, and related triggers

## [0.5.4] - 2026-05-14

### Added

- **`@scry.entry` block marker** — unified replacement for `@scry.doc` (markdown) and
  `@scry.file` (code). Both legacy kinds remain supported for backward compatibility.
  `@scry.entry` indexes into `scry__doc`, eliminating agent confusion about which marker
  type to use. See design doc at `~/.acp/agent/design/scry-entry-marker-migration.md`.
- **`entry` mint kind** — `scry_mint kind=entry prefix=design.X` now works and returns
  the `@scry.entry` template. Prefix rules match `doc` (must contain a dot).

## [0.5.3] - 2026-05-14

### Fixed

- `__version__` in `__init__.py` now correctly reports `0.5.3` (was accidentally left at
  `0.5.1` in 0.5.2 — all watcher fixes were present; only the version string was wrong).
- `sys` import moved to module level in `watcher.py` for cleaner style.
- **Startup sanity check**: `cold_scan` now logs the surface result to `stderr` when
  net-new markers are indexed or markers are flagged missing. When >5 net-new docs are
  discovered, it emits an explicit `WARNING` line noting that watcher drift likely occurred.
  Makes behind-watcher situations visible in server logs without manual inspection.

## [0.5.2] - 2026-05-14

### Fixed

- **Watcher drift bug**: `_Handler._excluded` was calling `Path(path).parts` on the
  absolute filesystem path, not the path relative to the project root. For projects
  installed under a dotted ancestor directory (e.g. `~/.acp/projects/...`), the `.acp`
  component matched the `startswith(".")` guard and caused every `on_created` /
  `on_modified` event to be silently dropped. The watcher appeared to run but indexed
  nothing after the initial cold scan. Fix: compute `Path(path).relative_to(project_root)`
  before checking parts. Files outside the project root are now excluded (safe) rather
  than accidentally excluded via the dotted-ancestor path.
- **Watcher error visibility**: `_Debouncer._fire` now logs exceptions to `stderr` instead
  of silently swallowing them. The watcher still never crashes on per-event errors; it just
  makes them visible.

### Tests

- Added `test_excluded_uses_relative_path` regression test covering the dotted-ancestor
  path bug — verifies that files inside the project are not excluded, dotted dirs inside
  the project are still excluded, and files outside the project root are excluded.

## [0.5.1] - 2026-05-14

### Added

- `scry scrub` CLI subcommand exposing the scrub operation directly from the
  shell. Accepts `--include-agent` to opt in to full scrubbing (prior behavior).
- `scry_scrub` MCP tool now accepts `include_agent: bool = false` parameter.
  Update the tool description to document the new default-exclusion behavior.

### Changed

- **Default scrub scope narrowed**: `scry scrub` and `scry_scrub` now skip
  `agent/**` and any `AGENT.md` file by default. Only tracked files outside
  the agent workspace are scrubbed. This matches the common workflow where
  `agent/` is excluded from git via `.git/info/exclude` — those files don't
  need clean markers for PR submission, and scrubbing them was noise.
- Pass `--include-agent` (CLI) or `include_agent=true` (MCP) to restore the
  prior behavior: scrub everything and remove the `agent/` directory.
- Result dict now includes `skipped_agent` (list of paths not scrubbed) and
  `skipped_agent_hint` when agent files were excluded.

## [0.3.0] - 2026-05-06

### Added

- `scry__warning` table for lint-style misplacement warnings, queryable
  via `scry_sql`. Schema: `(id, kind, marker_kind, marker_id, file_path,
  message, detected_at)`.
- Location rule: `@scry.doc` markers belong inside `agent/`; `@scry.file`
  markers describe non-agent source. Misplaced markers are still indexed
  so agents can find them, but a row is recorded in `scry__warning`.
- `scry_surface` return now includes `warnings.counts`, `warnings.sample`,
  and a hint pointing to the table.
- Verbatim tool descriptions and FastMCP `instructions=` text — agents
  now see field-quality examples for `summary`/`rationale`/`applies` and
  the full table list at connect time.
- New migration `002_warnings.sql`.
- 7 new tests covering warning insert, no-warning happy paths, auto-clear
  on move/delete, and a regression test for `@scry.file` indexing.

### Notes

- Warnings are pure derived state. `scry_surface` wipes the table at
  the start of each call and rebuilds from the live walk; the watcher's
  `reindex_file` clears warnings for the touched path on each event.

## [0.2.1] - 2026-05-05

### Fixed

- Lowered `requires-python` from `>=3.11` to `>=3.10`. The code already
  uses `from __future__ import annotations` and no 3.11-only features,
  so the higher floor was unnecessarily blocking installs. The `mcp`
  dependency itself caps the floor at 3.10.

## [0.2.0] - 2026-05-05

### Added

- `scry` CLI dispatcher with subcommands: bare `scry` runs the MCP server
  (default), `scry init` scaffolds an `agent/` tree + driver dirs in the
  current project, `scry surface [--force]` runs a one-shot batch reindex,
  `scry version` prints the package version.
- `scry init` is ACP-aware: when `agent/commands/` or `agent/progress.yaml`
  exists, it preserves the tree and only adds scry-specific subdirs.
  Idempotent — safe to re-run.
- Local `.gitignore` written inside `agent/drivers/@<ns>/scry/` (ignoring
  `data/` and `runtime/`) instead of polluting the project's root
  `.gitignore`.
- `README.md`, `LICENSE` (MIT), and full publish metadata in
  `pyproject.toml` (authors, classifiers, URLs, keywords).

### Changed

- PyPI distribution name is `scry-mcp` (the bare `scry` name was already
  taken on PyPI by an unrelated SPARQL package). The import name and the
  installed console command remain `scry`.
- `__main__.py` now delegates to `scry.cli:main`. The MCP server boot
  logic moved to `scry.server.run_server`.
- Console script entry registered under the `scry` command via
  `[project.scripts]`.

## [0.1.0] - 2026-05-05

Initial implementation built from the spec
(`agent/specs/local.scry-marker-cache~draft.md`, FR1–FR28) and the design
doc (`agent/design/local.scry-architecture~draft.md`, DR1–DR18).

### Added

- Marker parser for `@scry.{doc,file,anchor,impl,test}` with positional
  exclusion and context-inferred comment-prefix stripping.
- SQLite cache schema with FTS5 indexes maintained by triggers; sequential
  migration runner driven by `src/scry/migrations/*.sql`.
- File watcher daemon: 150 ms debounce, lock-file primary election, cold
  scan, soft-delete for docs/files and hard-delete for anchors/impls/tests
  on file removal, binary-file skip, excluded-dir skip.
- Batch reindex (`scry_surface`) with `missing_since` flagging and
  `force=true` hard-delete sweep.
- `scry_sql` read-only gateway that rejects mutator keywords after stripping
  comments.
- `scry_mint` collision-free ID minter with prefix rules and marker schema
  responses for the five marker kinds.
- `scry_scrub` to produce a `<branch>--clean` git branch with markers
  stripped and the `agent/` directory removed.
- `scry_script` discovery + execution from bundled
  (`src/scry/scripts/`) and driver
  (`agent/drivers/@<namespace>/scry/scripts/`) directories. Bundled
  `validate_coverage` example included.
- `doc_relationship` insert helper with cycle detection (FR28). Not
  exposed as a tool — callable from validation scripts.
- 43 pytest unit tests covering markers, query, mint, surface, watcher,
  script, and relationship layers.

### Notes

- Two intentional deviations from the design doc:
  - Parser strips line markers from inside block bodies before YAML parse,
    so a stray `@scry.impl` text inside a doc body still allows the doc to
    be indexed (per FR7's expectation that the doc is preserved).
  - Added `service/relationship.py` for FR28 cycle-checked inserts because
    no MCP tool in the design exposes relationship writes; intended to be
    invoked from `scry_script` validators.

[0.1.0]: about:blank
