"""scry_mint_with_check — preferred minter; wraps scry_mint with explicit collision guidance."""
from __future__ import annotations

from scry.config import get_db
from scry.service.mint import mint
from scry.tools._common import serialize


async def scry_mint_with_check(kind: str, prefix: str) -> str:
    """PREFERRED over raw scry_mint. Generates a collision-free scry marker ID (same as
    scry_mint) and augments the response with existing-marker warnings:

      Tier 1 — exact-prefix collision: markers with the same prefix already in scry__doc.
        If any tier-1 hit is the same logical concept, ABANDON the new ID and reference
        the existing marker instead — stranded IDs pollute scry.

      Tier 2 — family-slug neighbors: related markers in the same slug family
        (informational; may reveal related prior work to link against).

    Args:
        kind: 'entry', 'anchor', or 'bind'
        prefix: Human-readable prefix. entry MUST contain a dot (e.g. 'design.auth-flow',
                'task.fix-bug'). anchor/bind must NOT contain dots (e.g. 'auth-check',
                'validate-jwt').

    Returns: id, marker schema (same as scry_mint), plus tier-1/tier-2 collision info.
    """
    from scry.tools import get_marker_mode
    conn = get_db()
    try:
        return serialize(mint(conn, kind, prefix, marker_mode=get_marker_mode()))
    finally:
        conn.close()
