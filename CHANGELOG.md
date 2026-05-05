# Changelog

All notable changes to scry are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
