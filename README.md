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

Scry recognizes five marker kinds. Block markers carry a YAML body between
open/close tokens; line markers are single-line `@scry.<kind> <id> <ref>`.

```html
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
@scry.doc.end -->

<!-- @scry.file
id: file.auth-middleware~e5f6a7b8
kind: middleware
summary: Express middleware that validates JWT on every request
status: active
weight: 0.7
@scry.file.end -->

<!-- @scry.anchor auth-check~f1e2d3c4
description: JWT validation point for protected routes
@scry.anchor.end -->
```

```python
# @scry.impl validate-jwt~a1b2c3d4 spec.auth~xyz89012#FR3
# @scry.test jwt-expiry~b2c3d4e5 spec.auth~xyz89012#UT1
```

Block markers can be embedded in any host-language comment style (HTML,
Python, JS, JSDoc, Rust, bare YAML). Comment prefixes are inferred from
the YAML body — there is no per-language config.

## MCP tools

| Tool | Purpose |
|---|---|
| `scry_sql(query)` | Read-only SQL gateway. Rejects mutator keywords. Returns `{results, row_count}` JSON. |
| `scry_mint(kind, prefix)` | Generate a collision-free ID and the marker schema. |
| `scry_surface(force=false)` | Batch reindex from disk. `force=true` hard-deletes records whose source file no longer exists. |
| `scry_scrub()` | Create a `<branch>--clean` git branch with all `@scry.*` markers stripped and `agent/` removed. |
| `scry_script(action, script?, params?)` | Discover and run validation scripts from `src/scry/scripts/` and `agent/drivers/@<ns>/scry/scripts/`. |

## Database schema

Five marker-backed tables (`scry__doc`, `scry__file`, `scry__anchor`,
`scry__impl`, `scry__test`) plus `doc_relationship` (with cycle detection)
and `migration`. FTS5 is maintained via triggers on the source tables —
no manual rebuild step.

The cache is fully reconstructable from disk via `scry_surface`. The DB is
gitignored; after `git pull`, agents call `scry_surface` to rebuild.

## Watcher

A daemon thread runs alongside the MCP server, watching the project tree
with a 150 ms debounce window. A lock file at
`agent/drivers/@<ns>/scry/runtime/lock` performs PID-based primary
election so multiple sessions don't race writes. The primary instance
runs a cold scan on startup; secondaries observe and wait.

On file deletion: docs and files are soft-deleted (`missing_since` set);
anchors, impls, and tests are hard-deleted.

## Tests

```bash
uv pip install -e ".[dev]"
pytest
```

43 unit tests cover the parser, SQL gateway, mint, surface, watcher
plumbing, script discovery, and relationship cycle detection.

## License

MIT — see [LICENSE](LICENSE).
