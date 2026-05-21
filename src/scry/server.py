"""MCP server boot: register tools, run migrations, start watcher, run."""
from __future__ import annotations

import atexit

from mcp.server.fastmcp import FastMCP

from scry.config import get_db_path, get_project_root
from scry.service.migration import run_migrations
from scry.service.watcher import ScryWatcher
from scry.tools import register_tools


SERVER_INSTRUCTIONS = """\
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

D3. Mark every created artifact. Every file a consumer creates
    should carry a @scry.entry marker with an ID minted through
    the implementation's mint surface — never invented. Unmarked
    files are reachable only by path; marked files are reachable
    by meaning, tag, and question.

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
    mcp = FastMCP("scry", instructions=SERVER_INSTRUCTIONS)
    register_tools(mcp)

    run_migrations()

    watcher = ScryWatcher(get_project_root(), get_db_path())
    watcher.start()
    atexit.register(watcher.stop)

    mcp.run()
