"""scry_mint MCP tool — collision-free ID minter."""
from __future__ import annotations

from scry.config import get_db
from scry.service.mint import mint
from scry.tools._common import serialize


async def scry_mint(kind: str, prefix: str) -> str:
    """REQUIRED before writing any @scry.* marker. Generates a collision-free
    ID and returns the marker schema with per-field instructions. Follow the
    returned instructions exactly when filling fields.

    Also performs collision detection and returns warnings alongside the ID:

      tier1_collisions — markers with the SAME prefix already in the DB.
        If any tier-1 hit is the same logical concept, ABANDON the new ID
        and reference the existing marker instead — stranded IDs pollute scry.

      tier2_neighbors — markers in the same kind+first-segment family
        (informational; may reveal related prior work to link against).

    Args:
        kind: "entry", "anchor", or "bind"
        prefix: Human-readable prefix.
                entry: MUST contain a dot (e.g. "design.auth-flow", "task.fix-bug")
                anchor/bind: MUST NOT contain dots (e.g. "auth-check", "validate-jwt")

    Returns JSON with: id, schema (marker_open/close + per-field instructions),
    and optionally tier1_collisions + tier2_neighbors when they exist.

    Field quality matters (FR4.A authoring guidance):
      summary   — prose sentences + 'Also:' keyword cluster at the end.
                  "JWT auth middleware, validates bearer tokens. Also: JWT, bearer-token, auth-guard, refresh-flow"
      tags      — carry both classifier and bare-keyword forms.
                  ["topic:auth", "auth", "scope:runtime", "runtime"]
      rationale — Why this artifact exists: the problem it solves or the role it fills.
                  Not why you would search for it, not a findability claim, not its importance.
                  Lesson: "prevents re-introducing the auth bypass fixed in PR 412".
                  Design: "centralizes token checks so endpoints do not each re-implement them".
                  Track wake: "owns the reflect-mcp build-to-PyPI path".
                  Bad: "invisible to scry without this", "this is important".
      applies   — verb-shaped triggers (actions, not topics).
                  "modifying auth, adding protected endpoints" not "when working on auth"
      seeded_questions — include both full questions AND fragment queries.
                  ["What is the JWT refresh flow?", "JWT refresh token implementation"]
    """
    conn = get_db()
    try:
        return serialize(mint(conn, kind, prefix))
    finally:
        conn.close()
