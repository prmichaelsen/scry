"""Tool registration."""
from __future__ import annotations

from scry.config import MarkerMode
from scry.tools.scry_sql import scry_sql
from scry.tools.scry_mint import scry_mint
from scry.tools.scry_mint_with_check import scry_mint_with_check
from scry.tools.scry_surface import scry_surface
from scry.tools.scry_sink import scry_sink
from scry.tools.scry_scrub import scry_scrub
from scry.tools.scry_script import scry_script
from scry.tools.scry_grep import scry_grep
from scry.tools.scry_db_health import scry_db_health

_marker_mode: MarkerMode = "inline"


def get_marker_mode() -> MarkerMode:
    return _marker_mode


def register_tools(mcp, *, marker_mode: MarkerMode = "inline") -> None:
    global _marker_mode
    _marker_mode = marker_mode
    if marker_mode == "off":
        # No markers: only file-body search, manual re-scan, and health.
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
