"""MCP server boot: register tools, run migrations, start watcher, run."""
from __future__ import annotations

import atexit

from mcp.server.fastmcp import FastMCP

from scry.config import get_db_path, get_project_root
from scry.service.migration import run_migrations
from scry.service.watcher import ScryWatcher
from scry.tools import register_tools


def run_server() -> None:
    mcp = FastMCP("scry")
    register_tools(mcp)

    run_migrations()

    watcher = ScryWatcher(get_project_root(), get_db_path())
    watcher.start()
    atexit.register(watcher.stop)

    mcp.run()
