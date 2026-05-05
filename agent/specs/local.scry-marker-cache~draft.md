# Spec: Scry — Marker-Indexed SQL Cache

<!-- @scry markers not yet active; using @acp.meta.spec for now -->
<!-- @acp.meta.spec
topic: scry, markers, sqlite, mcp, indexing, fts5
description: Deterministic MCP server that indexes in-file markers into a queryable SQLite cache
requirements: FR1..FR28
status: draft
updated: 2026-05-05
@acp.meta.end -->

**Namespace**: local  
**Version**: 1.0.0  
**Created**: 2026-05-05  

---

## Purpose

Index in-file `@scry.*` markers into a SQLite database that agents query via read-only SQL, providing structured project knowledge without LLM reasoning.

---

## Source

- **Mode**: `interactive`
- **Derived from**: Diver project audits (`audit-3-sql-layer.md`, `audit-4-marker-system.md`) and design conversation (2026-05-05)

---

## Scope

### In Scope
- 5 marker types: `@scry.doc`, `@scry.file`, `@scry.anchor`, `@scry.impl`, `@scry.test`
- SQLite database as queryable cache (gitignored, fully reconstructable from disk)
- File watcher daemon (continuous indexing)
- FTS5 with auto-sync triggers
- 5 MCP tools: `scry_sql`, `scry_mint`, `scry_surface`, `scry_scrub`, `scry_script`
- Content-hash deduplication
- Ephemeral docs via `.scratch.md` filename convention
- `doc_relationship` table with cycle detection

### Out of Scope
- Workflow execution engine (replaced by `scry_script`)
- Lifecycle state machine tables
- `@diver.bail` or any terminal marker convention
- Sink tool (DB is gitignored, not committed)
- Relink tool (watcher + surface cover all cases)
- Any LLM reasoning or orchestration

---

## Requirements

1. **FR1** — The system MUST parse `@scry.doc` block markers from any text file and extract all 8 YAML fields (id, kind, summary, status, weight, tags, rationale, applies, seeded_questions).
2. **FR2** — The system MUST parse `@scry.file` block markers with the same field set as `@scry.doc` except `kind` is freeform string (no enum constraint).
3. **FR3** — The system MUST parse `@scry.anchor` block markers extracting name (from open line), description, and seeded_questions from the YAML body.
4. **FR4** — The system MUST parse `@scry.impl` line markers extracting both id and ref from the two-token format `@scry.impl <id> <ref>`.
5. **FR5** — The system MUST parse `@scry.test` line markers extracting both id and ref from the two-token format `@scry.test <id> <ref>`.
6. **FR6** — The parser MUST strip comment prefixes from marker bodies using the context-inference algorithm (find first YAML key, measure offset, strip from all lines).
7. **FR7** — The parser MUST skip `@scry.impl` and `@scry.test` matches that fall between a block marker's open and close tokens (positional exclusion).
8. **FR8** — The file watcher MUST detect file create, modify, and delete events using watchdog with a 150ms debounce window.
9. **FR9** — The file watcher MUST compute a content hash (SHA-256 of full marker body, truncated to 16 hex chars) and skip upsert when hash matches the existing DB record.
10. **FR10** — The file watcher MUST set `ephemeral = 1` on any doc/file record whose `current_path` ends in `.scratch.md`.
11. **FR11** — The file watcher MUST support multi-session primary election via a lock file; only the primary instance writes to the DB.
12. **FR12** — The file watcher MUST perform a cold scan of all project files on startup (or promotion to primary).
13. **FR13** — The file watcher MUST scan all non-binary files regardless of extension; excluded directories only (`.git`, `node_modules`, `__pycache__`, `.venv`, `dist`).
14. **FR14** — On file deletion, docs and files MUST be soft-deleted (`missing_since` set); anchors, impls, and tests MUST be hard-deleted.
15. **FR15** — `scry_sql` MUST reject any query containing mutator keywords (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, REPLACE, TRUNCATE, ATTACH, DETACH, PRAGMA). Only SELECT and WITH pass.
16. **FR16** — `scry_sql` MUST execute valid queries against the SQLite database and return results as JSON (`{"results": [...], "row_count": N}`).
17. **FR17** — `scry_mint` MUST generate collision-free IDs in the format `{prefix}~{8hex}` using `secrets.token_hex(4)`, checking collisions against the appropriate table.
18. **FR18** — `scry_mint` MUST enforce prefix rules: doc/file prefixes must contain a dot; anchor/impl/test prefixes must not contain dots.
19. **FR19** — `scry_mint` MUST return the marker schema (marker_open, marker_close, fields with instructions, suggested file path for doc/file kinds).
20. **FR20** — `scry_surface` MUST walk all project files, parse markers, and upsert to DB (same logic as watcher but in batch).
21. **FR21** — `scry_surface` MUST set `missing_since` on any DB doc/file record whose `current_path` does not exist on disk.
22. **FR22** — `scry_surface` MUST warn (not delete) about records with `missing_since` set. `scry_surface(force=true)` MUST hard-delete those records.
23. **FR23** — `scry_scrub` MUST create a `{branch}--clean` git branch, strip all `@scry.*` markers from tracked files, and delete the `agent/` directory.
24. **FR24** — `scry_script` MUST discover scripts from bundled (`src/scry/scripts/`) and driver-local (`agent/drivers/@namespace/scry/scripts/`) directories.
25. **FR25** — `scry_script(action='list')` MUST return available script names and descriptions.
26. **FR26** — `scry_script(action='run', script='<name>')` MUST execute the named script with read-write DB access and return structured JSON output.
27. **FR27** — FTS5 tables MUST be maintained via INSERT/UPDATE/DELETE triggers on their source tables (no manual rebuild required).
28. **FR28** — `doc_relationship` MUST enforce cycle detection via recursive CTE before inserting edges. Only `depends_on` relationship type is valid.

---

## Behavior Table

| # | Scenario | Expected Behavior | Tests |
|---|----------|-------------------|-------|
| 1 | File with `@scry.doc` marker created | Watcher indexes doc into `scry__doc` within 200ms | `watcher-indexes-new-doc` |
| 2 | File with `@scry.file` marker created | Watcher indexes file into `scry__file` within 200ms | `watcher-indexes-new-file` |
| 3 | File with `@scry.anchor` marker created | Watcher indexes anchor into `scry__anchor` | `watcher-indexes-anchor` |
| 4 | File with `@scry.impl` line marker | Watcher indexes impl into `scry__impl` | `watcher-indexes-impl` |
| 5 | File with `@scry.test` line marker | Watcher indexes test into `scry__test` | `watcher-indexes-test` |
| 6 | Marker content unchanged on save | Watcher skips upsert (content hash match) | `watcher-skips-unchanged-marker` |
| 7 | File deleted that contained a doc marker | `missing_since` set on doc record; no hard delete | `watcher-soft-deletes-doc` |
| 8 | File deleted that contained impl markers | Impl records hard-deleted | `watcher-hard-deletes-impls` |
| 9 | Agent runs SELECT query via `scry_sql` | Results returned as JSON | `sql-returns-results` |
| 10 | Agent runs INSERT via `scry_sql` | Query rejected with error | `sql-rejects-mutator` |
| 11 | Agent mints a doc ID | Returns `{prefix}~{8hex}` with no collision | `mint-generates-unique-id` |
| 12 | Agent mints impl with dotted prefix | Rejected (impl prefix must not contain dots) | `mint-rejects-dotted-impl-prefix` |
| 13 | `scry_surface` called on fresh checkout | All markers indexed, stale records get `missing_since` | `surface-full-reindex` |
| 14 | `scry_surface(force=true)` called | Records with `missing_since` hard-deleted | `surface-force-deletes-stale` |
| 15 | `scry_scrub` called on feature branch | Clean branch created, all markers stripped, agent/ deleted | `scrub-creates-clean-branch` |
| 16 | `scry_scrub` called on main | Rejected (must not be on main/master) | `scrub-rejects-main-branch` |
| 17 | `scry_script(action='list')` called | Returns available scripts from both directories | `script-list-discovers-scripts` |
| 18 | `scry_script(action='run', script='validate_coverage')` | Script executes with DB access, returns JSON | `script-run-executes-with-db` |
| 19 | FTS search for doc by summary keyword | Returns matching docs | `fts-doc-search-by-summary` |
| 20 | FTS search after watcher indexes new doc | New doc appears in FTS results (trigger maintained) | `fts-auto-syncs-on-insert` |
| 21 | `@scry.impl` inside a `@scry.doc` block body | Impl is NOT parsed (positional exclusion) | `parser-excludes-impl-inside-doc-block` |
| 22 | `@scry.impl` after a closed `@scry.doc` block | Impl IS parsed (not excluded) | `parser-includes-impl-after-closed-doc` |
| 23 | File named `foo.scratch.md` with doc marker | Watcher sets `ephemeral = 1` on DB record | `watcher-sets-ephemeral-from-filename` |
| 24 | Cycle would be created in `doc_relationship` | Insert rejected with error | `relationship-rejects-cycle` |
| 25 | Two MCP sessions start; second watcher instance | Second becomes secondary; only primary writes | `watcher-primary-election` |
| 26 | Primary watcher dies; secondary promotes | Secondary claims lock and runs cold scan | `watcher-secondary-promotes` |
| 27 | Binary file in project tree | Watcher skips it (no parse attempt) | `watcher-skips-binary-files` |
| 28 | Marker in `.git/` directory | Watcher ignores it (excluded dir) | `watcher-excludes-git-dir` |

---

## Interfaces / Data Shapes

### Database Schema

```sql
-- Marker-backed tables
CREATE TABLE scry__doc (
  id TEXT PRIMARY KEY,
  current_path TEXT,
  summary TEXT,
  kind TEXT CHECK(kind IN ('design','spec','task','milestone','clarification','pattern','internal')),
  weight REAL,
  status TEXT CHECK(status IN ('draft','active','approved','stale','complete')),
  tags TEXT,
  rationale TEXT,
  applies TEXT,
  seeded_questions TEXT,
  ephemeral INTEGER DEFAULT 0,
  missing_since TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE scry__file (
  id TEXT PRIMARY KEY,
  current_path TEXT,
  summary TEXT,
  kind TEXT,
  weight REAL,
  status TEXT CHECK(status IN ('draft','active','approved','stale','complete')),
  tags TEXT,
  rationale TEXT,
  applies TEXT,
  seeded_questions TEXT,
  ephemeral INTEGER DEFAULT 0,
  missing_since TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE scry__anchor (
  name TEXT PRIMARY KEY,
  description TEXT,
  seeded_questions TEXT,
  current_path TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE scry__impl (
  id TEXT PRIMARY KEY,
  ref TEXT NOT NULL,
  file_path TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE scry__test (
  id TEXT PRIMARY KEY,
  ref TEXT NOT NULL,
  file_path TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

-- Infrastructure
CREATE TABLE doc_relationship (
  from_id TEXT,
  to_id TEXT,
  relationship TEXT CHECK(relationship IN ('depends_on')),
  PRIMARY KEY (from_id, to_id, relationship)
);

CREATE TABLE migration (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- FTS5 with triggers
CREATE VIRTUAL TABLE scry__doc_fts USING fts5(
  id, summary, tags, rationale, applies, seeded_questions,
  content='scry__doc', content_rowid='rowid'
);

CREATE VIRTUAL TABLE scry__file_fts USING fts5(
  id, summary, tags, rationale, applies, seeded_questions,
  content='scry__file', content_rowid='rowid'
);

CREATE VIRTUAL TABLE scry__anchor_fts USING fts5(
  name, description, seeded_questions,
  content='scry__anchor'
);
```

### Marker Syntax

```
# Block markers:
<!-- @scry.doc
id: design.auth-flow~a1b2c3d4
kind: design
summary: >
  JWT auth middleware, token validation, refresh flow
status: active
weight: 0.85
tags: ["scope:auth", "topic:security"]
rationale: >
  Missing this causes auth bypass bugs
applies: modifying auth, adding protected endpoints
seeded_questions:
  - How does token refresh work?
  - What roles are required for admin?
@scry.doc.end -->

<!-- @scry.file
id: file.auth-middleware~e5f6a7b8
kind: middleware
summary: >
  Express middleware that validates JWT on every request
status: active
weight: 0.7
tags: ["scope:auth", "topic:middleware"]
rationale: >
  All protected routes depend on this
applies: adding routes, changing auth logic
seeded_questions:
  - How do I add a new protected route?
@scry.file.end -->

<!-- @scry.anchor auth-check~f1e2d3c4
description: >
  JWT validation point for protected routes
seeded_questions:
  - What happens if the token is expired?
@scry.anchor.end -->

# Line markers:
# @scry.impl validate-jwt~a1b2c3d4 spec.auth~xyz89012#FR3
# @scry.test jwt-expiry~b2c3d4e5 spec.auth~xyz89012#UT1
```

### MCP Tool Signatures

```
scry_sql(query: str) -> str (JSON)
scry_mint(kind: str, prefix: str) -> str (JSON)
scry_surface(force: bool = false) -> str (JSON)
scry_scrub() -> str (JSON)
scry_script(action: str, script: str? = null, params: dict? = null) -> str (JSON)
```

### Connection Configuration

```python
conn = sqlite3.connect(db_path, timeout=10)
conn.execute("PRAGMA journal_mode = WAL")
# No foreign keys (application-level enforcement)
conn.row_factory = sqlite3.Row
```

---

## Behavior

1. MCP server boots: run migrations, start watcher daemon, register 5 tools.
2. Watcher claims primary lock. If already claimed by a live PID, becomes secondary.
3. Primary performs cold scan: walks all non-binary files outside excluded dirs, parses markers, upserts to DB.
4. Watcher enters event loop: on create/modify, debounce 150ms, then parse+upsert. On delete, soft-delete docs/files, hard-delete anchors/impls/tests.
5. FTS tables are maintained automatically via triggers on every INSERT/UPDATE/DELETE to source tables.
6. Agents query via `scry_sql` (read-only). Agents generate IDs via `scry_mint`. Agents batch-reindex via `scry_surface`. Agents strip markers via `scry_scrub`. Agents run validation scripts via `scry_script`.
7. `scry_surface(force=true)` is the garbage collection pass — removes records whose files are truly gone.
8. DB is gitignored. After `git pull`, agent calls `scry_surface` to rebuild from disk.

---

## Acceptance Criteria

- [ ] All 5 marker types parse correctly from files with any comment syntax (Python, JS, Go, Rust, HTML, bare YAML)
- [ ] Watcher indexes new markers within 200ms of file save
- [ ] Content-hash dedup prevents redundant writes on unchanged files
- [ ] FTS results are current after every watcher upsert (trigger-maintained)
- [ ] `scry_sql` blocks all mutation attempts
- [ ] `scry_mint` generates collision-free IDs for all 5 kinds
- [ ] `scry_surface` fully reconstructs DB from disk markers
- [ ] `scry_surface(force=true)` cleans stale records
- [ ] `scry_scrub` produces a clean branch with no `@scry.*` markers and no `agent/` directory
- [ ] `scry_script` discovers and executes scripts with DB access
- [ ] `.scratch.md` files are marked `ephemeral=1` automatically
- [ ] `doc_relationship` rejects cycles
- [ ] Multi-session primary election works correctly
- [ ] DB connection uses WAL mode with 10s timeout

---

## Tests

### Base Cases

#### Test: watcher-indexes-new-doc (covers FR1, FR8, FR9)

**Given**: Watcher is running as primary  
**When**: A file is created containing a valid `@scry.doc` marker  
**Then** (assertions):
- **doc-in-db**: `scry__doc` contains a row with the marker's id
- **fields-correct**: summary, kind, status, weight, tags, rationale, applies, seeded_questions all match marker YAML
- **hash-stored**: content_hash column is populated
- **path-stored**: current_path matches the file's relative path

#### Test: watcher-indexes-new-file (covers FR2, FR8)

**Given**: Watcher is running as primary  
**When**: A source file is created containing a valid `@scry.file` marker with `kind: middleware`  
**Then** (assertions):
- **file-in-db**: `scry__file` contains a row with the marker's id
- **kind-freeform**: kind column is `middleware` (no enum constraint)

#### Test: watcher-indexes-anchor (covers FR3, FR8)

**Given**: Watcher is running as primary  
**When**: A file is created containing `@scry.anchor my-anchor~abc12345` with description and seeded_questions  
**Then** (assertions):
- **anchor-in-db**: `scry__anchor` row exists with name `my-anchor~abc12345`
- **description-parsed**: description field matches YAML body
- **questions-parsed**: seeded_questions contains the list from YAML

#### Test: watcher-indexes-impl (covers FR4, FR8)

**Given**: Watcher is running  
**When**: A file contains `# @scry.impl validate-jwt~a1b2c3d4 spec.auth~xyz#FR3`  
**Then** (assertions):
- **impl-in-db**: `scry__impl` row with id `validate-jwt~a1b2c3d4`
- **ref-correct**: ref column is `spec.auth~xyz#FR3`
- **path-correct**: file_path matches the file's relative path

#### Test: watcher-indexes-test (covers FR5, FR8)

**Given**: Watcher is running  
**When**: A file contains `# @scry.test jwt-expiry~b2c3d4e5 spec.auth~xyz#UT1`  
**Then** (assertions):
- **test-in-db**: `scry__test` row with id `jwt-expiry~b2c3d4e5`
- **ref-correct**: ref column is `spec.auth~xyz#UT1`

#### Test: watcher-skips-unchanged-marker (covers FR9)

**Given**: A doc is already indexed with content_hash `abc123`  
**When**: The file is saved again with identical marker content  
**Then** (assertions):
- **no-write**: `updated_at` does not change
- **hash-unchanged**: content_hash remains `abc123`

#### Test: watcher-soft-deletes-doc (covers FR14)

**Given**: A file containing `@scry.doc` with id `task.foo~12345678` is indexed  
**When**: The file is deleted  
**Then** (assertions):
- **row-persists**: `scry__doc` row still exists
- **missing-since-set**: `missing_since` is a non-null timestamp
- **no-hard-delete**: row is NOT removed

#### Test: watcher-hard-deletes-impls (covers FR14)

**Given**: A file containing `@scry.impl` markers is indexed  
**When**: The file is deleted  
**Then** (assertions):
- **rows-gone**: all `scry__impl` rows with that file_path are deleted

#### Test: sql-returns-results (covers FR15, FR16)

**Given**: `scry__doc` has 3 rows  
**When**: Agent calls `scry_sql("SELECT id, summary FROM scry__doc")`  
**Then** (assertions):
- **json-shape**: response is `{"results": [...], "row_count": 3}`
- **data-correct**: each result has `id` and `summary` keys

#### Test: sql-rejects-mutator (covers FR15)

**Given**: Database is running  
**When**: Agent calls `scry_sql("DELETE FROM scry__doc")`  
**Then** (assertions):
- **rejected**: response contains error message
- **no-mutation**: `scry__doc` row count unchanged

#### Test: mint-generates-unique-id (covers FR17, FR18)

**Given**: `scry__doc` has a row with id `design.auth~a1b2c3d4`  
**When**: Agent calls `scry_mint(kind='doc', prefix='design.auth')`  
**Then** (assertions):
- **format-correct**: returned id matches `design.auth~[0-9a-f]{8}`
- **no-collision**: returned id is different from existing `design.auth~a1b2c3d4`
- **schema-returned**: response includes marker_open, fields, file path

#### Test: mint-rejects-dotted-impl-prefix (covers FR18)

**Given**: Database is running  
**When**: Agent calls `scry_mint(kind='impl', prefix='spec.auth')`  
**Then** (assertions):
- **rejected**: response contains error about dots in impl prefix

#### Test: surface-full-reindex (covers FR20, FR21)

**Given**: DB is empty; project has 5 files with markers  
**When**: `scry_surface()` is called  
**Then** (assertions):
- **all-indexed**: DB contains records for all markers across 5 files
- **stale-flagged**: any pre-existing DB records without matching files get `missing_since` set

#### Test: surface-force-deletes-stale (covers FR22)

**Given**: `scry__doc` has a row with `missing_since` set  
**When**: `scry_surface(force=true)` is called  
**Then** (assertions):
- **stale-deleted**: that row is no longer in `scry__doc`

#### Test: scrub-creates-clean-branch (covers FR23)

**Given**: On branch `feature/foo` with `@scry.impl` markers in source files and `agent/` directory  
**When**: `scry_scrub()` is called  
**Then** (assertions):
- **branch-created**: git branch `feature/foo--clean` exists
- **markers-stripped**: no `@scry.*` strings in any tracked file
- **agent-removed**: `agent/` directory not present in clean branch

#### Test: scrub-rejects-main-branch (covers FR23)

**Given**: On branch `main`  
**When**: `scry_scrub()` is called  
**Then** (assertions):
- **rejected**: response contains error about being on main

#### Test: script-list-discovers-scripts (covers FR24, FR25)

**Given**: Bundled scripts dir has `validate_coverage.py`; driver scripts dir has `check_refs.py`  
**When**: `scry_script(action='list')` is called  
**Then** (assertions):
- **both-found**: response lists both `validate_coverage` and `check_refs`

#### Test: script-run-executes-with-db (covers FR26)

**Given**: A script `validate_coverage.py` exists that queries `scry__impl`  
**When**: `scry_script(action='run', script='validate_coverage')` is called  
**Then** (assertions):
- **executed**: script runs to completion
- **json-output**: response is structured JSON from the script
- **db-accessible**: script was able to read from `scry__impl`

#### Test: fts-doc-search-by-summary (covers FR27)

**Given**: `scry__doc` has a row with summary containing "authentication middleware"  
**When**: Agent queries `SELECT id FROM scry__doc_fts WHERE scry__doc_fts MATCH 'authentication'`  
**Then** (assertions):
- **match-found**: result includes that doc's id

#### Test: fts-auto-syncs-on-insert (covers FR27)

**Given**: FTS table is empty  
**When**: Watcher indexes a new doc with summary "payment processing"  
**Then** (assertions):
- **immediately-searchable**: FTS query for "payment" returns the new doc without manual rebuild

#### Test: relationship-rejects-cycle (covers FR28)

**Given**: `doc_relationship` has edge A -> B and B -> C  
**When**: Attempt to insert C -> A  
**Then** (assertions):
- **rejected**: insert fails with cycle detection error
- **no-row**: `doc_relationship` does not contain the C -> A edge

### Edge Cases

#### Test: parser-excludes-impl-inside-doc-block (covers FR7)

**Given**: A file contains `@scry.doc ... @scry.impl foo~123 spec.x~abc#FR1 ... @scry.doc.end`  
**When**: Watcher parses the file  
**Then** (assertions):
- **impl-not-indexed**: no `scry__impl` row for `foo~123`
- **doc-indexed**: `scry__doc` row exists

#### Test: parser-includes-impl-after-closed-doc (covers FR7)

**Given**: A file has `@scry.doc ... @scry.doc.end` followed by `# @scry.impl bar~456 spec.x~abc#FR2`  
**When**: Watcher parses the file  
**Then** (assertions):
- **impl-indexed**: `scry__impl` row exists for `bar~456`
- **doc-indexed**: `scry__doc` row exists

#### Test: watcher-sets-ephemeral-from-filename (covers FR10)

**Given**: Watcher is running  
**When**: A file named `agent/tasks/spike-auth.scratch.md` is created with a `@scry.doc` marker  
**Then** (assertions):
- **ephemeral-set**: `scry__doc` row has `ephemeral = 1`

#### Test: watcher-primary-election (covers FR11)

**Given**: A lock file exists with a live PID  
**When**: A second watcher instance starts  
**Then** (assertions):
- **secondary-mode**: second instance does not write to DB
- **no-cold-scan**: second instance does not run cold scan

#### Test: watcher-secondary-promotes (covers FR11)

**Given**: Lock file exists but PID is dead  
**When**: Secondary watcher checks liveness  
**Then** (assertions):
- **lock-claimed**: secondary overwrites lock with its own PID
- **cold-scan-runs**: full project scan executes

#### Test: watcher-skips-binary-files (covers FR13)

**Given**: Project contains a `.png` file with bytes that happen to match `@scry.doc`  
**When**: Watcher processes the directory  
**Then** (assertions):
- **no-parse-attempt**: file is skipped (null bytes detected in first 512 bytes)

#### Test: watcher-excludes-git-dir (covers FR13)

**Given**: `.git/` directory contains a file with `@scry.doc` text  
**When**: Watcher scans project  
**Then** (assertions):
- **not-indexed**: no DB record from any `.git/` file

#### Test: comment-stripping-jsdoc (covers FR6)

**Given**: A file contains an anchor marker inside a JSDoc block (`/** ... */`) with ` * ` line prefixes  
**When**: Parser extracts the marker  
**Then** (assertions):
- **yaml-clean**: description field contains clean text without ` * ` prefixes

#### Test: comment-stripping-python (covers FR6)

**Given**: A file contains an anchor marker with `# ` line prefixes  
**When**: Parser extracts the marker  
**Then** (assertions):
- **yaml-clean**: description field contains clean text without `# ` prefixes

#### Test: mint-retries-on-collision (covers FR17)

**Given**: First generated hex suffix would collide with existing row  
**When**: `scry_mint` is called  
**Then** (assertions):
- **succeeds**: returns a different ID on retry (up to 3 attempts)
- **unique**: returned ID does not exist in the table

#### Test: surface-idempotent (covers FR20)

**Given**: DB is fully populated from a previous surface call  
**When**: `scry_surface()` is called again with no file changes  
**Then** (assertions):
- **no-mutations**: no `updated_at` values change
- **same-row-count**: DB has identical row counts

---

## Non-Goals

- Multi-database support (only SQLite)
- Distributed/remote database
- Real-time push notifications to agents (agents poll via SQL)
- Marker validation beyond parsing (semantic correctness is `scry_script`'s job)
- Version control integration beyond `scry_scrub` branch creation
- Any form of LLM reasoning or agent orchestration

---

## Open Questions

- [ ] **OQ-1**: Should `scry_surface` report warnings as structured JSON or as human-readable text in the response?
- [ ] **OQ-2**: What is the maximum file size the watcher should attempt to parse before skipping (to avoid reading multi-MB generated files)?
- [ ] **OQ-3**: Should `scry_script` scripts have a timeout, and if so what default?

---

## Key Design Decisions

### Architecture

| Decision | Choice | Rationale |
|---|---|---|
| DB committed to git? | No — gitignored, fully reconstructable | Eliminates merge conflicts on DB, simplifies workflow (no sink needed) |
| FTS maintenance | Triggers (auto-sync) | Eliminates staleness gap between watcher writes and search availability |
| Foreign keys | Disabled | Only one optional FK existed (anchor.doc_id, dropped). Simplifies write ordering during surface |
| Extension whitelist | None — scan everything | Any text file might contain markers. Binary detection via null-byte heuristic |
| Lifecycle tables | Dropped | Premature abstraction with no consumers |
| Relink tool | Dropped | Watcher + surface cover all rename/move cases |
| Sink tool | Dropped | DB is gitignored, nothing to clean before merge |
| @scry.bail | Dropped | Parser processes entire files; no terminal marker convention |

### Markers

| Decision | Choice | Rationale |
|---|---|---|
| Ephemeral encoding | Filename convention (`.scratch.md`) not marker field | Gitignore handles enforcement; watcher derives the flag; agents don't need to remember to set it |
| Impl/test ID format | Minted (`name~shortuuid`), not derived from path | Stable across renames; matches deployed convention |
| Impl exclusion rule | Positional (inside block = excluded) | Prevents false matches from requirement text in doc bodies without over-excluding legitimate impls |
| Comment stripping | Context-inference from first YAML key | Language-agnostic, zero-maintenance, works for any syntax |
| Content hash scope | Full marker body | If any field changes, hash changes — no risk of missing a field |

---

## Related Artifacts

- **Source**: Diver audits: `agent/reports/audit-3-sql-layer.md`, `agent/reports/audit-4-marker-system.md`
- **Design conversation**: 2026-05-05 session (diver → scry port decisions)
- **Related**: ACP `@acp.spec` command (this spec follows its format)

---

**Namespace**: local  
**Spec**: scry-marker-cache  
**Version**: 1.0.0  
**Created**: 2026-05-05  
**Last Updated**: 2026-05-05  
**Status**: Draft  
**Author**: prmichaelsen + Claude Opus 4.6
