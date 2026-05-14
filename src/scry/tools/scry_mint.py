"""scry_mint MCP tool — collision-free ID minter."""
from __future__ import annotations

from scry.config import get_db
from scry.service.mint import mint
from scry.tools._common import serialize


async def scry_mint(kind: str, prefix: str) -> str:
    """REQUIRED before writing any @scry.* marker. Generates a collision-free
    ID and returns the marker schema with per-field instructions. Follow the
    returned instructions exactly when filling fields.

    Args:
        kind: "entry", "anchor", or "bind"
        prefix: Human-readable prefix.
                entry: MUST contain a dot (e.g. "design.auth-flow", "task.fix-bug")
                anchor/bind: MUST NOT contain dots (e.g. "auth-check", "validate-jwt")

    Returns JSON with: id, marker_open, marker_close, fields (with per-field
    instructions), and file info (directory, filename, path).

    Field quality matters:
      summary   — dense, keyword-rich, no filler. "JWT auth middleware, token validation, refresh flow" not "This describes authentication"
      rationale — consequence of NOT reading. "missing this causes auth bypass bugs" not "this is important"
      applies   — comma-separated activities. "modifying auth, adding protected endpoints" not "when working on auth"
    """
    conn = get_db()
    try:
        return serialize(mint(conn, kind, prefix))
    finally:
        conn.close()
