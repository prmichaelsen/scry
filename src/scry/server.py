"""MCP server boot: register tools, run migrations, start watcher, run."""
from __future__ import annotations

import atexit

from mcp.server.fastmcp import FastMCP

from scry.config import get_db_path, get_project_root
from scry.service.migration import run_migrations
from scry.service.watcher import ScryWatcher
from scry.tools import register_tools


SERVER_INSTRUCTIONS = """\
Scry indexes in-file @scry.* markers into a SQLite cache (project.db).
Query via scry_sql (read-only SQL). All marker IDs MUST be minted via
scry_mint before writing — never invent IDs. The mint response contains
per-field instructions — follow them exactly. The file watcher keeps
the DB in sync with disk automatically."""


def run_server() -> None:
    mcp = FastMCP("scry", instructions=SERVER_INSTRUCTIONS)
    register_tools(mcp)

    run_migrations()

    watcher = ScryWatcher(get_project_root(), get_db_path())
    watcher.start()
    atexit.register(watcher.stop)

    mcp.run()
