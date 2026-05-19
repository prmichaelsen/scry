# scry

Marker-indexed SQL cache MCP server. Scry indexes in-file `@scry.*` markers
into a SQLite database that agents query via read-only SQL, providing
structured project knowledge without LLM reasoning.

[![PyPI](https://img.shields.io/pypi/v/scry-mcp.svg)](https://pypi.org/project/scry-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/scry-mcp.svg)](https://pypi.org/project/scry-mcp/)

## Install

```bash
uv pip install scry-mcp
# or:
pip install scry-mcp
```

The PyPI distribution is `scry-mcp` (the bare name `scry` was already taken
on PyPI). The import name and the installed console command are both
`scry`.

## Quickstart

```bash
# In your project root:
scry init                # scaffolds agent/ + driver dirs, updates .gitignore
```

Then add it to your MCP client config:

```json
{
  "mcpServers": {
    "scry": {
      "command": "scry"
    }
  }
}
```

The MCP client inherits cwd from wherever it's launched, and scry walks
up from there looking for an `agent/` directory — so the same config
works for any project. Bare `scry` (no subcommand) starts the MCP
server over stdio — that's what Claude calls. Other subcommands:

| Command | Purpose |
|---|---|
| `scry` | Run the MCP server (default). |
| `scry init [path]` | Create `agent/` + `agent/drivers/@local/scry/{data,runtime,scripts}/` and a local `.gitignore` inside the driver dir. Idempotent — safe to run inside an ACP project. |
| `scry surface [--force]` | One-shot batch reindex without booting the server. |
| `scry version` | Print the package version. |

The server walks up from `cwd` until it finds an `agent/` directory; that
becomes the project root. The cache lives at
`agent/drivers/@<namespace>/scry/data/project.db` and is gitignored.

## Markers

Scry recognizes three marker kinds per scry-spec v1.1: `@scry.entry` and
`@scry.anchor` are block markers with a YAML body between open/close tokens;
`@scry.bind` is a line or block marker declaring cross-references.

```html
<!-- @scry.entry
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
extras:
  owner: auth-team
  jira: AUTH-1247
  reviewed_at: 2026-05-19
@scry.entry.end -->

<!-- @scry.anchor auth-check~f1e2d3c4
description: JWT validation point for protected routes
@scry.anchor.end -->
```

```python
# @scry.bind validate-jwt~a1b2c3d4 spec.auth~xyz89012#FR3
# @scry.bind jwt-expiry~b2c3d4e5 spec.auth~xyz89012#UT1
```

Block markers can be embedded in any host-language comment style (HTML,
Python, JS, JSDoc, Rust, bare YAML). Comment prefixes are inferred from
the YAML body — there is no per-language config.

### `extras` field (scry-spec v1.1, FR4.B)

`@scry.entry` accepts an optional `extras` field: a single-depth map of
arbitrary string keys to scalar values (`string | number | boolean | null`).
Use it to attach structured metadata that isn't part of the core schema —
ownership, ticket IDs, cost ledgers, review timestamps, anything you want
to query later.

Constraints:

- Single depth only — values must be scalars; nested maps and lists are
  diagnostic violations.
- Serialized size ≤ 4 KB (the spec's SHOULD-level cap).
- Backends MAY index `extras` keys for query (SHOULD-level on this
  Python implementation; supported via `json_extract` against the
  serialized blob).

Oversize payloads MUST round-trip intact — the cap is a diagnostic, not a
truncation gate. Empty `extras: {}` emits a SHOULD-level warning.

### `@scry.entry` kind values (v1.1 baseline)

| kind | use for |
|---|---|
| `design` | architecture and design docs |
| `pattern` | canonical recipes, established patterns |
| `spec` | requirements and specifications |
| `lesson` | post-mortems, "I tried X and it failed because Y" |
| `internal` | service quirks, undocumented behaviors |
| `task` | discrete work items |
| `milestone` | phase markers, exit criteria |
| `report` | wake/session reports |
| `audit` | security or integrity audits |
| `research` | research notes |
| `code` | implementation-specific docs |

## MCP tools

| Tool | Purpose |
|---|---|
| `scry_sql(query)` | Read-only SQL gateway. Rejects mutator keywords. Returns `{results, row_count}` JSON. |
| `scry_grep(query, kind?, status?, path_glob?, limit?)` | Full-text search over indexed file bodies (`scry__file_fts`). Complements `scry_sql` when you want to search prose, not just marker fields. |
| `scry_mint(kind, prefix)` | Generate a collision-free ID and the marker schema. |
| `scry_mint_with_check(kind, prefix)` | Preferred minter — same as `scry_mint` plus tier-1/tier-2 collision warnings. |
| `scry_surface(force=false, path?)` | Batch reindex from disk. `force=true` hard-deletes records whose source file no longer exists; `path` scopes the walk to a single file or subdirectory. |
| `scry_sink(then_surface=false)` | Lower the index back to disk-only state — truncates all index tables atomically (schema preserved, disk markers untouched). Requires user confirmation; `then_surface=true` rebuilds in one call. |
| `scry_scrub()` | Create a `<branch>--clean` git branch with all `@scry.*` markers stripped from non-agent files. |
| `scry_script(action, script?, params?)` | Discover and run validation scripts from `src/scry/scripts/` and `agent/drivers/@<ns>/scry/scripts/`. |

## Database schema

Marker-backed core tables:

| Table | Holds |
|---|---|
| `scry__doc` | One row per `@scry.entry` marker — id, kind, status, weight, summary, rationale, applies, current_path, ephemeral, missing_since, content_hash, extras, timestamps. |
| `scry__doc_tag` | Tags as a join table — `(doc_id, tag)`. |
| `scry__doc_seeded_question` | Seeded questions per doc — `(doc_id, ordinal, question)`. |
| `scry__anchor` | One row per `@scry.anchor` marker — id, doc_id, description, content_hash, timestamps. |
| `scry__anchor_seeded_question` | Seeded questions per anchor — `(anchor_id, ordinal, question)`. |
| `scry__bind` | One row per `@scry.bind` marker — source_doc_id, source_local_id, target_id, target_fragment, comment, content_hash, timestamps. |
| `scry__rel` | Typed edges between docs — `(from_id, to_id, predicate, fragment)`. Predicates: `depends_on`, `implements`, `supersedes`. Cycle detection enforced on `depends_on`. |
| `scry__file` | Universal file-body index — `(path, doc_id, body, content_hash, last_modified)`. Populated during `scry_surface`. |
| `scry__warning` | Lint-style warnings emitted by the parser/indexer — id, kind, marker_kind, marker_id, file_path, message, detected_at. |
| `migration` | Schema migration ledger. |

FTS5 virtual tables (trigger-maintained, queryable via FTS MATCH):

| FTS table | Searches |
|---|---|
| `scry__doc_fts` | Doc summary, rationale, applies, current_path. |
| `scry__doc_tag_fts` | Tag strings. |
| `scry__doc_seeded_question_fts` | Doc seeded questions. |
| `scry__anchor_fts` | Anchor descriptions. |
| `scry__bind_fts` | Bind source_local_id, target_id, comment. |
| `scry__file_fts` | Full file bodies. Prefer the `scry_grep` tool over hand-rolled queries. |

The cache is fully reconstructable from disk via `scry_surface`. The DB is
gitignored; after `git pull`, agents call `scry_surface` to rebuild.

## Watcher

A daemon thread runs alongside the MCP server, watching the project tree
with a 150 ms debounce window. A lock file at
`agent/drivers/@<ns>/scry/runtime/lock` performs PID-based primary
election so multiple sessions don't race writes. The primary instance
runs a cold scan on startup; secondaries observe and wait.

On file deletion: docs are soft-deleted (`missing_since` set);
anchors and binds are hard-deleted.

## Tests

```bash
uv pip install -e ".[dev]"
pytest
```

152 tests cover the parser, SQL gateway, mint, surface, watcher
plumbing, script discovery, relationship cycle detection, FR4.B `extras`
conformance, and concurrent-connection retry behavior.

## License

MIT — see [LICENSE](LICENSE).
