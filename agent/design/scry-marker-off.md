# scry-marker-off

<!-- @scry.entry
id: design.scry-marker-off~f39cb13d
kind: design
summary: Decouples scry storage from ACP's agent/ dir by moving to .scry/, and adds marker_mode=off for markerless file-body indexing. Also: scry, marker-mode, off, readonly, .scry, storage, decouple, grep, indexing
status: draft
weight: 0.7
tags: [topic:storage, storage, topic:config, config, marker-mode, off, decouple, scry-grep]
rationale: Scry storage currently lives under agent/drivers/@<ns>/scry/, forcing every scry consumer to adopt ACP's agent/ scaffold; this design frees scry to run on any project and to index files without requiring marker adoption.
applies: adding a new marker_mode, changing scry storage paths, running scry on a markerless project, wiring scry_grep without markers, modifying tool registration
seeded_questions: ['How does scry store its DB without an agent/ dir?', 'What does marker_mode=off do?', 'How do I use scry on a project that has not adopted markers?', 'marker_mode off readonly', '.scry storage path']
informs: ""
depends_on: []
design_requirements: DR1..DR9
updated: 2026-08-18
@scry.entry.end -->

**Concept**: Move scry storage to a self-contained `.scry/` directory and add a `marker_mode=off` value for markerless, grep-only operation
**Created**: 2026-08-18
**Status**: Draft

---

## Overview

Scry indexes structured `@scry.*` markers from source files into a queryable SQLite cache. Two coupling problems limit where scry can run:

1. **Storage is coupled to ACP.** Scry's DB, lock file, and config currently live under `agent/drivers/@<ns>/scry/`, a path that only exists after ACP's `agent/` scaffold is created. Scry cannot run on a project that has not adopted ACP.

2. **Usefulness is coupled to marker adoption.** Scry's structured queries depend on authors embedding `@scry.*` markers. On a codebase with no markers, scry offers little beyond what already exists.

This design addresses both: relocate scry storage to `.scry/` at the project root (scry's own sentinel, independent of ACP), and add a third `marker_mode` value, `off`, that indexes file bodies for full-text search without requiring or writing any markers.

---

## Problem Statement

**Coupling to ACP.** `get_project_root()` walks ancestors looking for an `agent/` directory, and `get_driver_dir()` / `get_namespace()` resolve the `agent/drivers/@<ns>/scry/` path where the DB, lock, and config live. This means scry is unusable outside an ACP project — you cannot point it at an arbitrary repository. The consequence: scry cannot serve as a general codebase-orientation tool, and it cannot be demoed on a production codebase without first scaffolding ACP into it.

**Coupling to marker adoption.** Even within an ACP project, scry's value comes from `@scry.*` markers. An agent exploring an unfamiliar repo with no markers falls back to grep and file traversal. There is no mode where scry acts as a fast, SQL-backed full-text search over raw file content without the marker machinery — despite the fact that the file-body index (`scry__file`) is already populated for every file regardless of markers.

Without solving these, scry remains an opt-in tool for ACP-adopting projects only, when it could be a general orientation tool for any codebase.

---

## Solution

Two independent but complementary changes:

**1. Relocate storage to `.scry/`.** Move the DB, lock file, and config from `agent/drivers/@<ns>/scry/` to `.scry/` at the project root. Change `get_project_root()` to walk for `.scry/` instead of `agent/`. Delete `get_namespace()` and `get_driver_dir()` — they exist solely to resolve the ACP-coupled path. The DB is a pure cache, so no data migration is needed; it rebuilds at the new path on next startup.

**2. Add `marker_mode=off`.** Extend the existing `marker_mode` config (currently `inline` | `sidecar`) with a third value, `off`. In `off` mode, scry registers only `scry_grep` and `scry_db_health`, uses a minimal instruction set that omits the marker-oriented operating discipline, and never mints or writes markers. File-body indexing already works unconditionally, so `scry_grep` operates correctly with no pipeline changes.

To use scry on a markerless project: create `.scry/config.toml` with `marker_mode = "off"`. Because storage now lives in `.scry/` (no `agent/` needed), this works on any repository.

**Alternatives considered.** An environment variable (`SCRY_MARKER_MODE=off`) was considered for configuring foreign projects, but since the `.scry/` rework already lets any project hold a `.scry/config.toml`, a config file is sufficient and keeps a single config surface. A separate `--read-only` CLI subcommand was rejected in favor of folding the behavior into the existing `marker_mode` axis.

---

## Implementation

### DR1: `.scry/` storage layout

Storage moves from the ACP driver path to a flat `.scry/` directory at the project root.

**Before:**
```
agent/drivers/@local/scry/data/project.db
agent/drivers/@local/scry/runtime/lock
agent/drivers/@local/scry/config.toml
```

**After:**
```
.scry/data/project.db
.scry/runtime/lock
.scry/config.toml
```

### DR2: `get_project_root()` walks for `.scry/`

Change the sentinel from `agent/` to `.scry/`, falling back to `cwd()` when not found.

```python
def get_project_root(start: Path | None = None) -> Path:
    p = (start or Path.cwd()).resolve()
    while p != p.parent:
        if (p / ".scry").is_dir():
            return p
        p = p.parent
    return (start or Path.cwd()).resolve()
```

### DR3: Remove `get_namespace()` and `get_driver_dir()`

Both functions exist only to resolve `agent/drivers/@<ns>/scry/`. With DR1, they have no purpose. The path helpers become flat:

```python
def get_db_path(project_root: Path | None = None) -> Path:
    root = project_root or get_project_root()
    return root / ".scry" / "data" / "project.db"

def get_lock_path(project_root: Path | None = None) -> Path:
    root = project_root or get_project_root()
    return root / ".scry" / "runtime" / "lock"
```

### DR4: `get_marker_mode()` reads `.scry/config.toml`

Config location moves to `.scry/config.toml`; the key and parsing are otherwise unchanged.

```python
def get_marker_mode(project_root: Path | None = None) -> MarkerMode:
    root = project_root or get_project_root()
    config_path = root / ".scry" / "config.toml"
    ...
```

### DR5: `MarkerMode` type gains `off`

```python
MarkerMode = Literal["inline", "sidecar", "off"]
_VALID_MARKER_MODES = frozenset({"inline", "sidecar", "off"})
```

`get_marker_mode()` returns `"off"` when config value is `"off"`; default remains `"inline"` when config is absent or invalid.

### DR6: `off` mode tool registration

When `marker_mode == "off"`, register only the tools that make sense without markers: `scry_grep` (file-body FTS), `scry_db_health` (mode-independent integrity probe), and `scry_surface` (manual re-scan after git pull or bulk file moves — mechanically works in off mode since it upserts file bodies and simply finds no markers to parse).

```python
def register_tools(mcp, *, marker_mode: MarkerMode = "inline") -> None:
    global _marker_mode
    _marker_mode = marker_mode
    if marker_mode == "off":
        mcp.tool()(scry_grep)
        mcp.tool()(scry_surface)
        mcp.tool()(scry_db_health)
        return
    mcp.tool()(scry_sql)
    mcp.tool()(scry_mint)
    mcp.tool()(scry_mint_with_check)
    mcp.tool()(scry_surface)
    mcp.tool()(scry_sink)
    mcp.tool()(scry_scrub)
    mcp.tool()(scry_script)
    mcp.tool()(scry_grep)
    mcp.tool()(scry_db_health)
```

Omitted in `off` mode: `scry_sql` (its description advertises marker tables that would all be empty — `scry_grep` covers the file-search need), `scry_mint`, `scry_mint_with_check`, `scry_sink`, `scry_scrub`, and `scry_script` — all marker-graph tooling with nothing to operate on.

### DR7: `off` mode server instructions

`_build_instructions()` gains an `off` branch that replaces the D1–D5 marker discipline with a minimal instruction set. It must not mention minting, stamping, `@scry.bind`, marker-field authoring, or `scry_sql` — those are meaningless without markers.

```
Scry indexes file content for fast full-text search. This project
runs in marker-off mode: no @scry.* markers are read or written.

- Use scry_grep to search file content across the project.
- No markers, no minting, no stamping.
- scry_surface re-scans the project if results seem stale.
- scry_db_health reports index status.
```

### DR8: Indexing pipeline is unchanged

`reindex_file()` already calls `upsert_file()` unconditionally, populating `scry__file` with body content for every file regardless of markers. `scry_grep` reads `scry__file` and works on a markerless project today. **No changes to the indexing pipeline are required for `off` mode.**

### DR9: `.gitignore` handling for `.scry/`

`.scry/` holds a rebuildable cache and should not be committed. On first startup scry should ensure `.scry/` is gitignored (append to `.gitignore` if a `.scry/` entry is absent), so consumers do not accidentally commit the DB.

---

## Benefits

- **Runs anywhere**: scry no longer requires ACP's `agent/` scaffold; point it at any repo.
- **Markerless orientation**: `marker_mode=off` turns scry into a fast SQL-backed full-text search for unfamiliar codebases and live demos, with no adoption prerequisite.
- **Simpler config code**: `get_namespace()` and `get_driver_dir()` are deleted; path resolution flattens.
- **Single config axis**: `off` folds into the existing `marker_mode` rather than introducing a parallel flag or env var.
- **Zero migration risk**: the DB is a pure cache; relocating the path just triggers a rebuild.

---

## Trade-offs

- **DB rebuild on upgrade**: existing projects rebuild the index at the new `.scry/` path on first startup after the change. This is a one-time cost, seconds to tens of seconds depending on project size. No data is lost (mitigated: DB is pure cache).
- **`.scry/` at project root**: adds a top-level hidden directory to every scry project. Mitigated by auto-gitignoring (DR9) and matching the familiar `.git` / `.venv` convention.
- **`off` mode reduces feature surface**: no structured queries, relationships, or minting. This is intentional — `off` is for orientation and search, not knowledge-graph authoring.

---

## Dependencies

- No external services or libraries.
- Internal: `config.py` (path + mode resolution), `server.py` (instructions + registration), `tools/__init__.py` (registration), `watcher.py` (consumes `get_db_path()` / `get_lock_path()`).
- `scry init` scaffolding (separate change) should create `.scry/` instead of the driver path — out of scope for this design but implied by DR1.

---

## Testing Strategy

- **Unit**: `get_project_root()` finds `.scry/` and falls back to cwd; `get_db_path()` / `get_lock_path()` resolve under `.scry/`; `get_marker_mode()` reads `.scry/config.toml` and accepts `off`; invalid values default to `inline`.
- **Registration**: in `off` mode only `scry_grep` + `scry_surface` + `scry_db_health` are registered; in `inline`/`sidecar` the full set is registered.
- **Instructions**: `_build_instructions("off")` contains no D3/D4/D5 or `scry_sql`/mint references.
- **Integration**: on a fixture project with no markers and `marker_mode=off`, the watcher cold-scan populates `scry__file` and `scry_grep` returns body matches.
- **Gitignore**: fresh `.scry/` results in a `.scry/` entry in `.gitignore`.

---

## Migration Path

1. Ship the `.scry/` path change. On next startup, scry creates `.scry/`, rebuilds the DB there, and the old `agent/drivers/@<ns>/scry/data/project.db` is orphaned.
2. Consumers may delete the old driver `scry/` storage manually; it is no longer read.
3. `marker_mode=off` is additive — existing `inline`/`sidecar` projects are unaffected.

---

## Future Considerations

- `scry init` should scaffold `.scry/` and optionally write a starter `config.toml`.
- An optional one-time auto-copy of the old DB to `.scry/` could skip the first rebuild, but is likely unnecessary given cache rebuild speed.
- `off` mode could later expose lightweight path/filename ranking on top of body FTS.

---

**Status**: Draft
**Recommendation**: Review, then derive an implementation spec (`/acp-spec-create`) covering DR1–DR9.
**Related Documents**: `agent/design/scry-architecture~draft.md`, `agent/specs/scry-marker-cache~draft.md`
