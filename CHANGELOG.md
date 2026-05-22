# Changelog

All notable changes to scry are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.19.0] - 2026-05-22

### Added

- **scry-spec v1.2.0 — `kind: goal` + `satisfies` predicate.** Adds
  `goal` to the recognized baseline kinds (UI-hint only — unknown
  kinds were already preserved as-is per FR8). Adds the `satisfies`
  typed-edge predicate (parallel to `depends_on` / `implements` /
  `supersedes`) and surfaces it in `scry__rel`. `DocMarker` gains a
  `satisfies: list[str]` field; the parser adapter reads it via
  `getattr(e, "satisfies", None)` so older scry-parse builds (no
  attribute) coerce cleanly to `[]`. End-to-end activation lands
  when scry-parse 1.2.0 ships the field; until then, in-band
  `satisfies` markers are inert at the parser layer but the
  backend rel-writer + predicate enum + `scry_sql` schema
  description are ready. See the scry-spec v1.2.0 broadcast
  (`scry-spec` commit `faf4767`, tag `v1.2.0`).
- `SUPPORTED_PREDICATES` (`scry.service.relationship`) now includes
  `"satisfies"`. `add_relationship` accepts it; cycle detection
  remains scoped to `depends_on` (satisfies is acyclic by
  semantics).

### Notes

- INV-GOAL-COMPLETION write-time enforcement (rejecting hand-edited
  `status: met` on `kind: goal` markers) is **not** included in this
  release. Non-validating ingestion preserves the field as-is per
  FR8. Deferred to a future release pending the v1.3+ candidate
  enforcement design.

## [0.18.1] - 2026-05-21

### Added

- **`scry_db_health` MCP tool** — sqlite integrity probe that
  distinguishes corruption from transient lock contention. Returns
  `status` ∈ {`ok`, `corrupt`, `locked`} along with `integrity`
  (`PRAGMA integrity_check` result), `doc_count`, and structured error
  fields. Designed for substrate code (e.g. reflection's `wake.py`
  auto-restore loop) that previously inlined `sqlite3.connect(...,
  timeout=2)` and conflated `SQLITE_BUSY` with on-disk corruption,
  causing healthy DBs to be quarantined under concurrent-wake load.
  Uses the same WAL + `busy_timeout=30000` connection primitives as
  every other scry-mcp tool, so the probe sees the DB as scry-mcp
  itself does. See `report.scry-corruption-diagnostic-prevention~876104b1`
  for the failure mode this closes.
- **`tests/test_db_health.py`** — 8 new tests covering: healthy
  migrated DB with and without rows; fresh-and-unmigrated DB
  (`status=ok`, `doc_count=null`, `doc_count_error` populated);
  hard corruption (garbage file header); synthetic non-`ok`
  `integrity_check` result; and lock/`SQLITE_IOERR` paths at both
  connect time and pragma time — both of which MUST report
  `status="locked"`, never `status="corrupt"`.

## [0.18.0] - 2026-05-21

### Added

- **MCP `instructions` field now carries the scry-spec v1.1.2
  Recommended Operating Discipline** (Canonical Minimal Form).
  `SERVER_INSTRUCTIONS` in `src/scry/server.py` was previously a
  five-line mechanical server description; it now leads with the
  five named operating disciplines (D1 orient-first, D2
  lesson-search-on-failure, D3 mark-every-artifact, D4
  author-fields-for-queries, D5 bind-implementations-to-targets)
  verbatim from scry-spec v1.1.2, followed by a "Mechanical notes"
  paragraph that preserves the prior content (SQL surface, mint
  discipline, watcher behavior). Consumer projects that previously
  duplicated scry-usage guidance in their own CLAUDE.md / wake.md
  may now trim those blocks to a pointer; the operating discipline
  travels with the MCP server.
- **`test_server_instructions_carry_canonical_minimal_form`** —
  unit assertion that `SERVER_INSTRUCTIONS` contains each of the
  named disciplines `D1.`, `D2.`, `D3.`, `D4.`, `D5.` and the
  spec-pointer line. Catches regression on the embedded text
  without coupling to exact wording.
- **`test_mcp_initialize_returns_canonical_minimal_form_instructions`** —
  handshake-level assertion that the `instructions` field returned
  by the MCP `initialize` response carries `D1.` through `D5.`
  Catches regression at the wire surface, not just the constant.

### Changed

- **`scry-spec` floor implicit at 1.1.2** for the operating-discipline
  text. (No `pyproject.toml` dependency change — the spec is text the
  server embeds, not a Python package.)

## [0.17.0] - 2026-05-20

### Added

- **`extras` indexing on `scry__doc`** (scry-spec v1.1.0 FR4.B). New
  `extras TEXT` column on `scry__doc` stores the marker's `extras`
  field as compact JSON-text (NULL when absent). The fresh-install
  schema (`001_initial.sql`) includes the column directly; legacy
  databases get an idempotent `ALTER TABLE ADD COLUMN` on next
  migration run.
- **JSON1 query surface for `extras`** — the column is queryable via
  SQLite JSON1 (`json_extract`, `->>`, `json_each`) through
  `scry_sql`. Tool docstring updated with the new column and an
  example query.
- **Parser uptake** — `DocMarker.extras` propagates the
  `scry-parse>=1.1.0` `extras` attribute (single-depth scalar map);
  the ingestion path serializes to JSON-text on upsert. Older
  parsers degrade to an empty dict / NULL column.
- **Tests** — 7 new tests covering parser propagation, ingestion to
  the column, JSON1 round-trip, sparse-NULL semantics, and migration
  backfill on legacy DBs.

### Changed

- **`scry-parse` floor bumped to `>=1.1.0`** in `pyproject.toml`.

## [0.16.1] - 2026-05-19

### Changed

- **`scry_mint` `rationale` gloss aligned with scry-spec v1.0.7** —
  both the MCP tool-description docstring and the per-field
  instruction string returned by a `scry_mint` call now describe
  `rationale` as *why this artifact exists* (the problem it solves
  or role it fills), not as a consequence-of-not-reading or
  findability claim. The prior gloss ("consequence of NOT reading")
  silently misfired on `design`, `spec`, and track-wake markers and
  produced authoring errors in the field. New gloss carries positive
  framing + explicit findability exclusion + lesson-case
  clarification. No parser or DB schema change.

## [0.16.0] - 2026-05-17

### Fixed

- **Transient SQLite disk-I/O errors under concurrent write load** —
  bumped `busy_timeout` and added a small retry loop around
  disk-I/O failures inside the writer path. Surfaces on busy
  multi-track projects where many wakes index simultaneously.

## [0.15.9] - 2026-05-16

### Fixed

- **scry_sql tool description out of sync with live schema** — the `Key
  tables:` block in the `scry_sql` docstring was missing columns that
  exist in the actual DB, and had no column listing for `scry__warning`.
  Six divergences fixed:

  1. `scry__anchor`: added `content_hash`, `created_at`, `updated_at`
  2. `scry__bind`: added `content_hash`, `created_at`, `updated_at`
  3. `scry__file`: added `last_modified`
  4. `scry__warning`: added full column list (`id, kind, marker_kind,
     marker_id, file_path, message, detected_at`) — previously had only
     a prose note with no queryable column info
  5. `scry__doc_tag_fts`: added explicit column list `(tag, doc_id
     UNINDEXED)` — agents need to know `doc_id` is available for joins
  6. `scry__doc_seeded_question_fts`: added explicit column list
     `(question, doc_id UNINDEXED)`

  The description is the agent-facing schema contract. A stale
  description causes silent query failures without any DB error.

## [0.15.8] - 2026-05-15

### Fixed

- **scry__file bloat causing DB corruption** — on projects with many
  symlinked sub-projects, `scry__file` body storage grew unbounded (74 MB
  observed), making WAL checkpoints risky under concurrent write load and
  leading to SQLite corruption ("file is not a database").

  Three-part fix to the body-indexing exclusion policy:

  1. **`.json` extension excluded** — package manifests, API responses, and
     preview caches are machine-generated; indexing their bodies adds no FTS
     value and adds significant bulk (1.6 MB of JSON in the affected project).

  2. **Dependency lock files excluded by filename** — `pnpm-lock.yaml`,
     `package-lock.json`, `yarn.lock`, `bun.lockb`, `Cargo.lock`,
     `poetry.lock`, `Gemfile.lock`, `composer.lock`, `pdm.lock`, `uv.lock`.
     Lock files were the single largest body contributors (100-230 KB each,
     many per project).

  3. **`agent/runtime/wakes/` path segment excluded** — wake system-prompt
     files are ephemeral (regenerated every wake), unique per session, and
     not useful for FTS. Excluding the path segment prevents constant re-index
     churn on frequently-changing files.

  4. **`_FILE_MAX_BYTES` reduced from 1 MB to 128 KB** — sufficient for any
     real source file; prevents generated TypeScript declarations and other
     large machine-generated files from slipping through the filename/extension
     filters.

## [0.15.7] - 2026-05-15

### Fixed

- **MCP reconnect failure (-32000 CONNECTION_CLOSED)** — On projects where
  `agent/projects/` contained a symlink back to the project root itself (circular
  self-reference), `_setup_existing_symlink_observers()` would start a recursive
  watchdog Observer on the same tree. inotify followed the circular path and
  immediately exhausted `max_user_watches`, raising `OSError: inotify watch limit
  reached`. This unhandled exception propagated through `watcher.start()` and
  `run_server()`, crashing the process before `mcp.run()` was reached. The MCP
  client saw `CONNECTION_CLOSED` (-32000).

  Two-part fix:
  1. `_schedule_for_symlink` now detects when a symlink's resolved target is the
     project root or an ancestor of it, and silently skips it (already watched by
     the main Observer).
  2. `obs.start()` is wrapped in `try/except OSError` with a graceful degradation
     warning, so large-project symlinks that would exceed the inotify watch limit
     log a warning and continue rather than crashing the server.

- **Main observer crash hardening** — `Observer.start()` in `watcher.start()` is
  also now wrapped with the same `OSError` guard.

### Added

- **Regression test** (`test_circular_symlink_does_not_crash_watcher`) — verifies
  that a project with a circular `agent/projects/self → project_root` symlink
  starts cleanly without raising.

## [0.15.6] - 2026-05-15

### Fixed

- **MCP connection timeout on startup** — `ScryWatcher.start()` was running the
  cold scan synchronously before `mcp.run()` was called. On large projects with
  many symlinked sub-projects and `scry__file` body indexing, the scan takes 30+
  seconds, causing every MCP client to time out on the initialize handshake. Cold
  scan now runs in a background daemon thread so `mcp.run()` starts accepting
  connections immediately.

### Added

- **MCP handshake smoke test** (`tests/test_server_handshake.py`) — starts
  `python -m scry` in a subprocess, sends an MCP `initialize` request, and asserts
  a valid response arrives within 5 s. Catches the startup-blocking regression
  that shipped clean through prior test suites.

- **Improved `scry_mint` field guidance** — `scry_mint` and `scry_mint_with_check`
  now return authoring instructions aligned with FR4.A (wake.md Entry 008):
  summary `Also:` keyword cluster, tag classifier+bare-keyword forms, verb-shaped
  `applies` triggers, fragment-query `seeded_questions`.

### Internal

- 144/144 tests pass.

---

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
