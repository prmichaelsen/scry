<!-- @diver.doc
id: internal.scry-tool-descriptions~d14791ad
kind: internal
summary: >
  scry MCP server instructions + tool descriptions — verbatim text for FastMCP constructor and each tool docstring, field quality examples, table enumeration
status: active
weight: 0.8
tags: ["scope:scry", "topic:mcp-descriptions"]
rationale: >
  agents misuse tools when descriptions are vague. this defines the exact text scry must expose so agents mint before writing, follow field instructions, and know all queryable tables.
applies: >
  implementing scry MCP server, writing tool docstrings, reviewing agent behavior with scry tools
ephemeral: false
@diver.doc.end -->

# Scry Tool & Server Descriptions

Verbatim text to use in the scry MCP implementation. These are not suggestions — use them word-for-word.

---

## Server Instructions

Passed to `FastMCP("scry", instructions=...)`:

```
Scry indexes in-file @scry.* markers into a SQLite cache (project.db).
Query via scry_sql (read-only SQL). All marker IDs MUST be minted via
scry_mint before writing — never invent IDs. The mint response contains
per-field instructions — follow them exactly. The file watcher keeps
the DB in sync with disk automatically.
```

---

## scry_sql

```
Execute a read-only SQL query against the scry project database.
Use this to discover project state, search docs, check coverage, inspect anchors.

Supports SELECT and WITH (CTE) queries only. All mutator keywords
(INSERT, UPDATE, DELETE, DROP, etc.) are blocked.

Key tables:
  scry__doc        — knowledge graph entities (designs, specs, tasks, milestones, patterns, internals)
  scry__file       — source code file metadata (modules, services, components)
  scry__anchor     — named code location bookmarks with descriptions and seeded questions
  scry__impl       — implementation markers linking source code to requirement refs (DR/FR)
  scry__test       — test markers linking test files to test requirement refs (UT/ST/ET)
  doc_relationship — typed edges between docs (depends_on only)
  scry__doc_fts    — full-text search over docs (summary, tags, rationale, applies, seeded_questions)
  scry__file_fts   — full-text search over files (same fields)
  scry__anchor_fts — full-text search over anchors (name, description, seeded_questions)
  migration        — applied schema migrations

Returns JSON: {"results": [...], "row_count": N}
```

---

## scry_mint

```
REQUIRED before writing any @scry.* marker. Generates a collision-free
ID and returns the marker schema with per-field instructions. Follow the
returned instructions exactly when filling fields.

Args:
    kind: "doc", "file", "anchor", "impl", or "test"
    prefix: Human-readable prefix.
            doc/file: MUST contain a dot (e.g. "design.auth-flow", "task.fix-bug")
            anchor/impl/test: MUST NOT contain dots (e.g. "auth-check", "validate-jwt")

Returns JSON with: id, marker_open, marker_close, fields (with per-field
instructions), and file info (directory, filename, path).

Field quality matters:
  summary   — dense, keyword-rich, no filler. "JWT auth middleware, token validation, refresh flow" not "This describes authentication"
  rationale — consequence of NOT reading. "missing this causes auth bypass bugs" not "this is important"
  applies   — comma-separated activities. "modifying auth, adding protected endpoints" not "when working on auth"
```

---

## scry_surface

```
Rebuild the DB from disk markers. Use after git pull, bulk file moves,
or if query results seem stale. The file watcher handles live indexing —
only call this for full re-scans.

Walks all project files, parses @scry.* markers, upserts to DB.
Idempotent. Uses content-hash dedup.

Args:
    force: If true, hard-deletes records whose files no longer exist.
           If false (default), sets missing_since and warns.

Returns JSON with counts per marker type and any warnings.
```

---

## scry_scrub

```
Create a clean PR branch with all @scry.* markers stripped and agent/
directory removed. For submitting code review without exposing agent
infrastructure.

Creates {branch}--clean from current HEAD. Does not stage or commit —
leaves unstaged changes for the user.

Fails if on main/master or if working tree is dirty.
```

---

## scry_script

```
Run validation or transformation scripts with DB access.

Actions:
  list — discover available scripts (bundled + project-local)
  run  — execute a named script

Args:
    action: "list" or "run"
    script: script name (required for action="run")
    params: arbitrary params passed to the script (optional)

Scripts have read-write DB access. They return structured JSON.
```
