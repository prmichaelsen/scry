# Design: Scry Implementation Architecture

<!-- @acp.meta.design
topic: scry, architecture, mcp, python, sqlite, project-structure
description: Implementation architecture for the scry marker-indexed SQL cache MCP server
design_requirements: DR1..DR18
status: draft
updated: 2026-05-05
@acp.meta.end -->

**Namespace**: local  
**Version**: 1.0.0  
**Created**: 2026-05-05  

---

## Purpose

Define the internal implementation architecture for scry — the project layout, dependency choices, module boundaries, boot sequence, and contracts that an implementing agent needs to build the system described in `agent/specs/local.scry-marker-cache~draft.md`.

---

## Spec Reference

This design implements: `agent/specs/local.scry-marker-cache~draft.md` (FR1–FR28).

---

## DR1: Project Layout

```
scry/
├── pyproject.toml
├── src/
│   └── scry/
│       ├── __init__.py
│       ├── __main__.py              # MCP server entry: python -m scry
│       ├── config.py                # DB path, project root detection, constants
│       ├── domain/
│       │   ├── __init__.py
│       │   └── markers.py           # Dataclasses, regex, parse_markers(), strip functions
│       ├── migrations/
│       │   └── 001_initial.sql      # Single migration for greenfield
│       ├── service/
│       │   ├── __init__.py
│       │   ├── migration.py         # Run SQL migrations
│       │   ├── watcher.py           # File watcher daemon
│       │   ├── surface.py           # Batch re-index
│       │   ├── mint.py              # ID generation
│       │   ├── scrub.py             # Clean branch creation
│       │   ├── query.py             # Read-only SQL validation + execution
│       │   └── script.py            # Script discovery + execution
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── scry_sql.py
│       │   ├── scry_mint.py
│       │   ├── scry_surface.py
│       │   ├── scry_scrub.py
│       │   └── scry_script.py
│       ├── util/
│       │   ├── __init__.py
│       │   └── comments.py          # strip_comment_prefix()
│       └── scripts/                  # Bundled validation scripts
│           ├── __init__.py
│           └── validate_coverage.py
├── tests/
│   ├── __init__.py
│   ├── test_markers.py
│   ├── test_watcher.py
│   ├── test_surface.py
│   ├── test_mint.py
│   ├── test_query.py
│   └── test_script.py
└── agent/
    └── drivers/
        └── @namespace/
            └── scry/
                ├── data/             # project.db lives here (gitignored)
                ├── runtime/          # lock file
                └── scripts/          # Project-specific scripts
```

## DR2: Dependencies

```toml
[project]
name = "scry"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0",           # FastMCP server
    "watchdog>=4.0",      # File system events
    "pyyaml>=6.0",        # Marker YAML parsing
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
```

No pydantic. Domain models are plain dataclasses. Validation is in the parser and service layer, not declarative models.

## DR3: Entry Point

```python
# src/scry/__main__.py
"""python -m scry — boots the MCP server."""

from scry.config import get_db_path, get_project_root, run_migrations
from scry.service.watcher import ScryWatcher
from scry.tools import register_tools

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("scry")
register_tools(mcp)

run_migrations()

watcher = ScryWatcher(get_project_root(), get_db_path())
watcher.start()

import atexit
atexit.register(watcher.stop)
```

Invoked in claude_desktop_config.json or equivalent:
```json
{
  "mcpServers": {
    "scry": {
      "command": "python",
      "args": ["-m", "scry"],
      "cwd": "/path/to/project"
    }
  }
}
```

## DR4: Project Root Detection

Walk up from CWD looking for an `agent/` directory. The first directory containing `agent/` is the project root. All paths are relative to this root.

```python
def get_project_root() -> Path:
    p = Path.cwd()
    while p != p.parent:
        if (p / "agent").is_dir():
            return p
        p = p.parent
    return Path.cwd()
```

## DR5: Database Path

```
{project_root}/agent/drivers/@{namespace}/scry/data/project.db
```

The namespace is read from `agent/drivers/` — first `@*` directory found that contains a `scry/` subdirectory. If none found, use `@local`.

## DR6: Connection Factory

```python
def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn
```

No foreign keys. WAL mode. 10-second timeout. Row factory for dict-like access.

## DR7: Migration System

Single-file sequential migrations in `src/scry/migrations/`. File naming: `NNN_description.sql`. A `migration` table tracks what's been applied.

For greenfield, ship one migration (`001_initial.sql`) containing the full schema. Future changes add `002_*.sql`, etc.

Migration runner:
1. Ensure `migration` table exists
2. List `.sql` files in migrations dir, sorted by name
3. Skip any already in `migration` table
4. Execute each pending migration, record in `migration` table

## DR8: Tool Registration

```python
# src/scry/tools/__init__.py
from mcp.server.fastmcp import FastMCP
from scry.tools.scry_sql import scry_sql
from scry.tools.scry_mint import scry_mint
from scry.tools.scry_surface import scry_surface
from scry.tools.scry_scrub import scry_scrub
from scry.tools.scry_script import scry_script

def register_tools(mcp: FastMCP) -> None:
    mcp.tool()(scry_sql)
    mcp.tool()(scry_mint)
    mcp.tool()(scry_surface)
    mcp.tool()(scry_scrub)
    mcp.tool()(scry_script)
```

Each tool is an async function in its own file. Thin wrapper — calls the service layer, returns JSON string.

## DR9: Tool ↔ Service Boundary

Tools are thin. They:
1. Parse MCP params
2. Get a DB connection
3. Call the service
4. Serialize the result to JSON
5. Close the connection

Services contain the logic. Services accept a `sqlite3.Connection` as an argument (dependency injection). Services return dataclasses or dicts, not JSON strings.

## DR10: Watcher Architecture

Single daemon thread. Components:
- **Debouncer**: 150ms window per file path. Timer-based.
- **LockFile**: PID-based primary election at `{driver_dir}/runtime/lock`.
- **Observer**: watchdog `Observer` with recursive watch on project root.
- **Processor**: reads file, detects binary (null bytes in first 512), calls `parse_markers()`, computes content hash, upserts.

Cold scan on startup (primary only): walk all files, process each.

Excluded directories: `.git`, `node_modules`, `__pycache__`, `.venv`, `dist`. Configurable via constant, not config file.

## DR11: Content Hash Formula

For ALL marker types: SHA-256 of the raw marker body text (the full text between open/close tokens for block markers, or the full line content for line markers). Truncated to 16 hex chars.

```python
import hashlib

def content_hash(raw_body: str) -> str:
    return hashlib.sha256(raw_body.encode()).hexdigest()[:16]
```

This is compared against `content_hash` column before upsert. If match → skip.

## DR12: FTS5 Triggers

Define INSERT/UPDATE/DELETE triggers on each source table that maintain the FTS index automatically:

```sql
-- For scry__doc_fts
CREATE TRIGGER scry__doc_ai AFTER INSERT ON scry__doc BEGIN
  INSERT INTO scry__doc_fts(rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES (new.rowid, new.id, new.summary, new.tags, new.rationale, new.applies, new.seeded_questions);
END;

CREATE TRIGGER scry__doc_ad AFTER DELETE ON scry__doc BEGIN
  INSERT INTO scry__doc_fts(scry__doc_fts, rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES ('delete', old.rowid, old.id, old.summary, old.tags, old.rationale, old.applies, old.seeded_questions);
END;

CREATE TRIGGER scry__doc_au AFTER UPDATE ON scry__doc BEGIN
  INSERT INTO scry__doc_fts(scry__doc_fts, rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES ('delete', old.rowid, old.id, old.summary, old.tags, old.rationale, old.applies, old.seeded_questions);
  INSERT INTO scry__doc_fts(rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES (new.rowid, new.id, new.summary, new.tags, new.rationale, new.applies, new.seeded_questions);
END;
```

Same pattern for `scry__file_fts` and `scry__anchor_fts`.

## DR13: Script Contract

A script is a Python file that exports a `run` function:

```python
# agent/drivers/@namespace/scry/scripts/validate_coverage.py
"""Validate that all FRs have @scry.impl markers."""

DESCRIPTION = "Check impl coverage for all active specs"

def run(db: sqlite3.Connection, params: dict) -> dict:
    """Execute the script.
    
    Args:
        db: Read-write SQLite connection
        params: Arbitrary params passed from MCP tool call
    
    Returns:
        Structured result dict (serialized to JSON by the tool)
    """
    specs = db.execute(
        "SELECT id FROM scry__doc WHERE kind = 'spec' AND status = 'active'"
    ).fetchall()
    # ... validation logic ...
    return {"covered": 12, "missing": ["spec.auth~abc#FR3"]}
```

Discovery: `scry_script(action='list')` scans both directories for `.py` files that aren't `__init__.py`, imports them, reads `DESCRIPTION` and `run.__doc__`.

Execution: `scry_script(action='run', script='validate_coverage', params={...})` imports the module, calls `run(db, params)`, serializes the return value.

## DR14: Binary File Detection

Before attempting to parse, read the first 512 bytes. If any null byte (`\x00`) is found, skip the file entirely. This catches images, compiled files, and other binaries without maintaining an extension blocklist.

## DR15: Positional Impl/Test Exclusion

The parser must determine whether an `@scry.impl` or `@scry.test` match falls *inside* a block marker (between open and close tokens). Algorithm:

1. Find all block marker spans (start offset, end offset) in the content
2. For each impl/test match, check if `match.start()` falls within any span
3. If inside → skip (it's a reference in a doc body, not a real marker)
4. If outside → include

This replaces diver's broken "skip if any doc precedes it" logic.

## DR16: Scrub Implementation

1. Verify not on main/master
2. Verify clean working tree
3. Create or reset `{branch}--clean` branch at current HEAD
4. Use `git grep -l '@scry\.'` to find files with markers
5. For each file: read content, call `strip_markers_from_content()`, write back
6. Remove `agent/` directory entirely (`git rm -rf agent/`)
7. Leave changes unstaged (user commits)

`strip_markers_from_content()` uses the same `BLOCK_MARKERS` and `LINE_MARKERS` constants as the parser to identify and remove marker regions.

## DR17: Error Response Shape

All tools use consistent error responses:

```json
{"error": "human-readable message"}
```

The presence of the `"error"` key distinguishes error responses from success. MCP infrastructure exceptions (connection timeout, etc.) are NOT caught — they propagate as tool-call failures.

## DR18: Ephemeral Detection

In the watcher and surface, after parsing a file's markers and before upserting doc/file records:

```python
ephemeral = 1 if rel_path.endswith(".scratch.md") else 0
```

This value is set on the DB record. It is NOT read from the marker YAML (the marker has no `ephemeral` field).

---

## Key Simplifications Over Diver

| Diver | Scry | Rationale |
|-------|------|-----------|
| 9 migrations | 1 migration (greenfield) | No legacy, ship full schema at once |
| Pydantic domain models | Plain dataclasses | Less dependency, simpler |
| Workflow engine (7 tables, service, registry) | `scry_script` (import + call) | Deterministic validation doesn't need state machines |
| Sink + surface lifecycle | Surface only (DB gitignored) | No merge-time cleanup needed |
| Relink tool | Watcher + surface | All cases covered without dedicated tool |
| Content hash per-field formula | Hash full marker body | Simpler, more correct |
| FTS manual rebuild | FTS triggers | No staleness gap |
| Extension whitelist | Scan everything (binary detection) | No maintenance, any language works |
| `@diver.bail` convention | Nothing | Parser processes full files |
| Lifecycle tables (5 tables) | Nothing | No consumers, premature abstraction |
| `created_by` columns | Nothing | Never populated |
| Foreign keys enabled | Disabled | Simplifies write ordering |

---

## Implementation Order

Recommended build sequence for an implementing agent:

1. **Project scaffolding**: pyproject.toml, directory structure, `__main__.py`
2. **Config**: project root detection, DB path, connection factory
3. **Migration system + initial schema**: single SQL file with all tables + triggers
4. **Domain**: `markers.py` (dataclasses, regex, parser, strip functions, comment stripping)
5. **Services**: query (simplest), mint, surface, watcher, scrub, script
6. **Tools**: thin wrappers over services
7. **Boot**: wire everything in `__main__.py`
8. **Tests**: one test file per service, in-memory SQLite

Each step is independently testable before moving to the next.

---

## Related Artifacts

- **Spec**: `agent/specs/local.scry-marker-cache~draft.md` (FR1–FR28)
- **Source audits**: `agent/reports/audit-3-sql-layer.md`, `agent/reports/audit-4-marker-system.md`

---

**Namespace**: local  
**Design**: scry-architecture  
**Version**: 1.0.0  
**Created**: 2026-05-05  
**Last Updated**: 2026-05-05  
**Status**: Draft  
**Author**: prmichaelsen + Claude Opus 4.6
