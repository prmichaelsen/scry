"""MCP server boot: register tools, run migrations, start watcher, run."""
from __future__ import annotations

import atexit

from mcp.server.fastmcp import FastMCP

from scry.config import MarkerMode, get_db_path, get_marker_mode, get_project_root
from scry.service.migration import run_migrations
from scry.service.watcher import ScryWatcher
from scry.tools import register_tools


_D3_INLINE = """\
D3. Mark every created artifact. Every file a consumer creates
    should carry a @scry.entry marker with an ID minted through
    the implementation's mint surface — never invented. Marked
    files are reachable by meaning, tag, and question — not just
    path or content search."""

_D3_SIDECAR = """\
D3. Document every created artifact. This project uses sidecar mode:
    all @scry.* markers live in agent/scry/, never in source files.
    (Inline mode embeds markers directly in source; sidecar mode
    keeps source files clean by storing markers separately.)

    For every source file a consumer creates, write a corresponding
    @scry.entry marker in a markdown file under agent/scry/. Use the
    extras field with key "source" to reference the source file path
    (e.g. source: src/auth/middleware.ts). Marked files are reachable
    by meaning, tag, and question — not just path or content search.

    When renaming or moving a source file, update extras.source in
    its marker. When changing a file's contents, ensure its sidecar
    marker still applies and update if out of date."""


def _build_instructions(marker_mode: MarkerMode) -> str:
    d3 = _D3_SIDECAR if marker_mode == "sidecar" else _D3_INLINE
    return f"""\
Scry indexes structured @scry.* markers from source files into a
queryable knowledge graph. Markers carry artifact identity, metadata,
and traceability between artifacts.

Operating discipline for consumers:

D1. Orient first. Before reading files, traversing directories, or
    running text search, query scry. Index queries are cheap and
    ranked; many small queries is the expected access pattern.

D2. On unexpected failure, search for a prior lesson before
    attempting a fix. A prior consumer may have already recorded
    the cause. Skipping this search is how the same mistake is
    solved twice.

{d3}

D4. Author marker fields for the queries that will hit them.
    Summary leads with prose and ends with an "Also:" keyword
    cluster. Tags carry both classifier and bare-keyword forms.
    Applies is verb-shaped. Seeded_questions carry both full
    questions and short fragment queries.

D5. Use @scry.bind to connect implementations to the artifacts
    they fulfill — spec requirements, lessons addressed, design
    decisions applied. Bindings make the knowledge graph
    bidirectional.

Full operating-discipline reference: scry-spec, "Recommended
Operating Discipline" section.

Mechanical notes: this server indexes in-file @scry.* markers into a
SQLite cache (project.db). Query via scry_sql (read-only SQL). All
marker IDs MUST be minted via scry_mint before writing — never invent
IDs. The mint response contains per-field instructions — follow them
exactly. The file watcher keeps the DB in sync with disk automatically."""


def run_server() -> None:
    marker_mode = get_marker_mode()
    instructions = _build_instructions(marker_mode)
    mcp = FastMCP("scry", instructions=instructions)
    register_tools(mcp, marker_mode=marker_mode)

    run_migrations()

    watcher = ScryWatcher(get_project_root(), get_db_path())
    watcher.start()
    atexit.register(watcher.stop)

    mcp.run()
