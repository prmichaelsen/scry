"""Tool registration."""
from __future__ import annotations

from scry.tools.scry_sql import scry_sql
from scry.tools.scry_mint import scry_mint
from scry.tools.scry_mint_with_check import scry_mint_with_check
from scry.tools.scry_surface import scry_surface
from scry.tools.scry_scrub import scry_scrub
from scry.tools.scry_script import scry_script


def register_tools(mcp) -> None:
    mcp.tool()(scry_sql)
    mcp.tool()(scry_mint)
    mcp.tool()(scry_mint_with_check)
    mcp.tool()(scry_surface)
    mcp.tool()(scry_scrub)
    mcp.tool()(scry_script)
