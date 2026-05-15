# Changelog

All notable changes to scry are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.15.5] - 2026-05-15

### Changed

- **Minimum scry-parse raised to 1.0.8** — FR11.6 v1.0.4 conformance: single-line
  `@scry.bind` markers inside HTML (`<!-- ... -->`) or C-style (`/* ... */`) block
  comments now correctly strip the closing delimiter from the `comment` field.
  Users on scry-parse 1.0.7 would leak ` -->` or ` */` into comment values.
  Constraint updated from `>=1.0.7` to `>=1.0.8`.

### Internal

- 143/143 tests pass.

---

## [0.15.4] - 2026-05-15

### Added

- **`path` parameter on `scry_surface`** — optional scope for targeted re-indexing.
  - `path=None` (default) — full corpus walk, unchanged behavior.
  - `path=<file>` — re-index exactly one file; counts reflect that one file.
  - `path=<directory>` — re-index every file under that directory, recursively.
  - Scoped reconciliation: `flagged_missing`, `misplaced_doc` warnings, and
    `force=True` hard-deletes are all scoped to the path. Docs outside the scope
    are never flagged as missing by a scoped surface call.
  - Non-existent path returns a clear `{"error": "...", "scope": path}` response
    (via the MCP tool wrapper) or raises `ValueError` (service layer).
  - Result shape gains a `scope` field echoing the `path` argument (`null` for
    a full walk).

### Internal

- 143/143 tests pass (6 new: `test_surface_full_walk_unchanged`,
  `test_surface_single_file`, `test_surface_directory_recursive`,
  `test_surface_scoped_missing`, `test_surface_scoped_force`,
  `test_surface_nonexistent_path`).

---

## [0.15.3] - 2026-05-15

### Fixed

- **`__version__` corrected to match pyproject.toml** — `src/scry/__init__.py` was
  stuck at `"0.15.1"` after the v0.15.2 version bump (pyproject.toml was updated but
  `__init__.py` was not). `scry.__version__` now returns the correct value.

### Internal

- 137/137 tests pass.

---

## [0.15.2] - 2026-05-15

### Changed

- **Minimum scry-parse raised to 1.0.7** — FR11.4 strict array enforcement for
  `depends_on`, `implements`, and `supersedes` fields landed in scry-parse 1.0.7.
  Users on 1.0.6 would silently accept scalar values for these fields, producing
  non-conformant behavior. Constraint updated from `>=1.0.6` to `>=1.0.7`.

### Internal

- 137/137 tests pass.

---

## [0.15.1] - 2026-05-15

### Fixed

- **Legacy FTS trigger cleanup on startup** — `run_migrations()` now calls
  `_cleanup_legacy_triggers()` which drops six triggers (`scry__doc_tag_ai/ad`,
  `scry__doc_sq_ai/ad`, `scry__anchor_sq_ai/ad`) that were created by pre-0.12.0
  schema versions. These triggers used content-backed FTS5 delete syntax on standard
  FTS5 tables, causing `sqlite3.OperationalError: SQL logic error` when deleting rows
  from `scry__doc_tag` or `scry__doc_sq`. The cleanup is idempotent (`DROP TRIGGER IF
  EXISTS`) so it is safe to run on fresh databases.

### Internal

- 137/137 tests pass.

---

## [0.15.0] - 2026-05-15

### Fixed

- **`implements` and `supersedes` typed as `list[str]`** — `DocMarker` fields were
  `str | None`; now `list[str]` (matching scry-parse >=1.0.6 which changed these
  from scalar to array in its `_strict_array` validation). Added `_coerce_list_field`
  shim so scry-mcp handles both 1.0.5 (str) and 1.0.6 (list[str]) at runtime.
- **`_sync_relationships` array passthrough** — no longer wraps `marker.implements`
  / `marker.supersedes` in `[...]`; passes the list directly to `_sync_rel_predicate`
  so all elements (not just the stringified list) are inserted into `scry__rel`.
- **Test fixture updated** — `DOC_WITH_OPTIONALS` uses YAML array syntax for
  `implements` and `supersedes` (e.g. `implements:\n  - spec.foo~bbbbbbbb`) so it
  works correctly with both scry-parse 1.0.5 and 1.0.6.

### Changed

- **`scry-parse` requirement bumped to `>=1.0.6`** — picks up array relationship
  fields and FR11.4 strict-array enforcement for `implements`/`supersedes`.
- **`uv.lock` updated** — scry-parse 1.0.5 → 1.0.6.

### Added

- **Code-construct exclusion integration tests** — `test_fenced_code_block_markers_not_indexed`
  and `test_inline_code_markers_not_indexed` verify that markers inside fenced code blocks
  and inline code spans are not indexed by scry-mcp's surface/reindex pipeline (CR-1 proxy).

### Internal

- 137/137 tests pass.

---

## [0.14.0] - 2026-05-15

### Fixed

- **Anchor `id` column in mint** — `mint.py` was querying `name` as the PK column for
  anchors; corrected to `id` to match the schema in `001_initial.sql`.
- **`tags` and `seeded_questions` typed as `list[str]`** — `markers.py` types were
  `str | None`; now correctly `list[str]`. Fixes downstream crashes when iterating
  these fields.
- **`relationship.py` fully rewritten for `scry__rel`** — previous version referenced
  the removed `doc_relationship` table. Now reads/writes `scry__rel` with correct
  columns (`from_id`, `to_id`, `predicate`, `fragment`). Covers `depends_on`,
  `implements`, and `supersedes` predicates.
- **Test suite updated to new schema** — `test_markers.py`, `test_mint.py`,
  `test_relationship.py`, `test_surface.py` updated for `scry__rel` and the anchor
  `id`/`doc_id` column layout. 135/135 tests pass.

---

## [0.13.0] - 2026-05-15

### Added

- **`scry__file` body index** — all git-tracked text files are indexed into
  `scry__file` (path, doc_id, body, content_hash) with exclusions for binary
  extensions, paths matching `node_modules`/`dist`/`.venv`/etc., files >1 MB,
  lines >10k chars, and LICENSE files. FTS5 (porter + unicode61) makes the body
  searchable.
- **`scry_grep` MCP tool** — full-text search over `scry__file_fts`. Supports
  `kind`, `status`, and `path_glob` filters; returns one hit per file with a BM25-
  ranked snippet (matched terms highlighted with `<mark>` tags). 25 new tests.
- **Single-schema migration** — `001_initial.sql` is the only migration file.
  Migration files `002`–`006` deleted; `migration.py` simplified to run
  `001_initial.sql` once at startup with no migration-tracking table. DB is a
  pure cache: drop and re-index at any time.
- **`scry__file` added to `SINK_TABLES`** — `scry_sink` now truncates the file
  body index along with the marker tables.

### Changed

- **`scry-parse` upgraded to `>=1.0.5`** — picks up phantom-marker suppression
  for code blocks and Python single-line string literals (prevents false marker
  rows from code like `"marker_open": f"<!-- @scry.anchor {ident}"`).
- **`scry_sink` elicitation message updated** — `doc_relationship` → `scry__rel`,
  `scry__file` added to listed tables.
- **`scry_sql` docstring updated** — `scry__file` and `scry__file_fts` documented;
  migration table entry removed.

### Internal

- 135/135 tests pass (25 new for grep/file indexing).

---

## [0.12.0] - 2026-05-15

### Fixed

- **Local `scry-parse` source override removed** — `[tool.uv.sources]` override
  for a local path to `scry-parse` removed now that v1.0.5 is on PyPI.

### Internal

- 135/135 tests pass.

---

## [0.11.0] - 2026-05-15

### Added

- **`scry_sink` MCP tool** — operational mirror of `scry_surface`: lowers the
  index back to disk-only state. Truncates `scry__doc`, `scry__anchor`,
  `scry__bind`, `doc_relationship`, and `scry__warning` in a single atomic
  transaction. Schema is preserved; FTS tables update via existing AFTER DELETE
  triggers; the migration table is not touched. Disk markers are never modified.
  Tool description: `scry_sink: lower the index back to disk-only state. The DB
  forgets; the disk remembers.`
- **MCP elicitation on `scry_sink`** — the tool requires protocol-level user
  confirmation before executing. It computes live row counts and displays them
  in the elicitation prompt before proceeding. If the user declines, cancels, or
  elicitation is unavailable, the operation fails closed (no data deleted). This
  establishes the elicitation pattern for future destructive scry tools.
- **`then_surface` parameter on `scry_sink`** — `then_surface: bool = False`; if
  true, runs `scry_surface()` immediately after the sink in a single call,
  expressing "reset + reindex."
- 5 new tests: `test_sink_truncates_all_tables`, `test_sink_preserves_schema`,
  `test_sink_atomic`, `test_sink_then_surface`, `test_sink_requires_elicitation`.

---

## [0.10.4] - 2026-05-14

### Fixed

- **`__version__` string corrected to match `pyproject.toml`** — releases 0.10.1 through 0.10.3
  were published with `__version__ = "0.10.0"` in `src/scry/__init__.py` because the string
  was not updated when `pyproject.toml` was bumped. `scry --version` and any programmatic
  read of `scry.__version__` reported the wrong value. Now `__version__ = "0.10.4"` and
  matches the installed package version.

---

## [0.10.3] - 2026-05-14

### Fixed

- **Tightened `scry-parse` minimum constraint from `>=1.0.0` to `>=1.0.1`** — block-comment
  support (JSDoc `/** */`, C `/* */`, OCaml `(* *)`, Haskell `{- -}`, PowerShell `<# #>`) was
  added in scry-parse v1.0.1. Declaring `>=1.0.0` allowed users with a cached 1.0.0 to install
  it alongside scry-mcp 0.10.2, breaking marker parsing in any language using block-comment
  comment syntax. The 0.10.2 release depended on this feature but did not constrain for it.

---

## [0.10.2] - 2026-05-14

### Added

- **`scry_mint_with_check` MCP tool** — preferred minter; wraps `scry_mint` with clearer
  docstring framing and is the explicit preferred entry point for agents. Exposes the same
  tier-1/tier-2 collision warnings already present in `scry_mint` but under a name that
  signals its recommended status. Register via `mcp.tool()(scry_mint_with_check)`.

### Changed

- **Upgraded `scry-parse` dependency from 1.0.0 to 1.0.2** — picks up block-comment
  support (JSDoc `/** */`, C `/* */`, OCaml `(* *)`, Haskell `{- -}`, PowerShell `<# #>`)
  added in v1.0.1. Without this, scry markers inside block-comment style in `.js`/`.ts`/
  `.c`/`.hs` files silently failed to parse. Also includes `check_cycles()` added in v1.0.2.

## [0.10.1] - 2026-05-14

### Fixed

- **Stale `depends_on_cycle` warnings now cleared on re-index** — when a
  marker previously recorded a cycle warning and the cycle is subsequently
  fixed, the old warning was not removed on re-index. `upsert_doc` now
  deletes existing `depends_on_cycle` warnings for the marker before
  re-evaluating relationships, so the warning table stays accurate after
  edits.

### Internal

- 1 new regression test (`test_cycle_warning_cleared_when_cycle_fixed`).
- 98/98 tests pass.

---

## [0.10.0] - 2026-05-14

### Added

- **`implements` and `supersedes` fields now indexed** — `@scry.entry` markers
  with `implements` or `supersedes` fields are persisted to `scry__doc` and
  queryable via `scry_sql`. Previously these optional spec fields (FR4) were
  parsed but silently dropped.

- **`depends_on` relationships auto-populated into `doc_relationship`** —
  `@scry.entry` markers with a `depends_on` list now drive `doc_relationship`
  inserts automatically on surface/watch. Cycle detection (FR12) runs at index
  time; cycles are recorded as `depends_on_cycle` warnings in `scry__warning`
  rather than halting the index. The `doc_relationship` table is now the
  authoritative source for dependency edges and is kept in sync on every
  file change.

- **`scry_sql` docstring** — the `scry__doc` column list now enumerates
  `implements`, `supersedes`, and `doc_relationship` notes so agents know
  these fields are queryable.

### Changed

- **`_sync_relationships`** (new internal helper in `surface.py`) — clears all
  `depends_on` rows for a doc before re-inserting from the current marker body,
  ensuring stale edges are removed when a marker is edited.

### Internal

- 97/97 tests pass (6 new tests covering implements/supersedes persistence,
  depends_on edge insertion, cycle detection at index time, and
  depends_on_cycle warning generation).

---

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
