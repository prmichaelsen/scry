"""scry_mint MCP tool — collision-free ID minter."""
from __future__ import annotations

from scry.config import get_db
from scry.service.mint import mint
from scry.tools._common import serialize


async def scry_mint(kind: str, prefix: str) -> str:
    """Mint a collision-free ID for a new scry marker.

    Args:
        kind: One of doc, file, anchor, impl, test.
        prefix: Identifier prefix. doc/file require a dot
            (e.g. "design.auth"); anchor/impl/test must not contain dots
            (e.g. "validate-jwt").

    Returns JSON containing the minted id and the marker schema (open/close
    tokens, expected fields) on success, or {"error": "..."} on rejection.
    """
    conn = get_db()
    try:
        return serialize(mint(conn, kind, prefix))
    finally:
        conn.close()
