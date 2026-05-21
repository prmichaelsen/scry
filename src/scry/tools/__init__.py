"""Tool registration."""
from __future__ import annotations

from scry.tools.scry_sql import scry_sql
from scry.tools.scry_mint import scry_mint
from scry.tools.scry_mint_with_check import scry_mint_with_check
from scry.tools.scry_surface import scry_surface
from scry.tools.scry_sink import scry_sink
from scry.tools.scry_scrub import scry_scrub
from scry.tools.scry_script import scry_script
from scry.tools.scry_grep import scry_grep
from scry.tools.scry_db_health import scry_db_health


def register_tools(mcp) -> None:
    mcp.tool()(scry_sql)
    mcp.tool()(scry_mint)
    mcp.tool()(scry_mint_with_check)
    mcp.tool()(scry_surface)
    mcp.tool()(scry_sink)
    mcp.tool()(scry_scrub)
    mcp.tool()(scry_script)
    mcp.tool()(scry_grep)
    mcp.tool()(scry_db_health)
