# Changelog

All notable changes to scry are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.3] - 2026-05-14

### Fixed

- `__version__` in `__init__.py` now correctly reports `0.5.3` (was accidentally left at
  `0.5.1` in 0.5.2 — all watcher fixes were present; only the version string was wrong).
- `sys` import moved to module level in `watcher.py` for cleaner style.

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
