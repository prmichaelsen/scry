"""scry_surface MCP tool — batch reindex from disk."""
from __future__ import annotations

from scry.config import get_db
from scry.service.surface import surface
from scry.tools._common import serialize


async def scry_surface(force: bool = False) -> str:
    """Walk the project, parse all markers, and rebuild the cache from disk.

    Args:
        force: If true, hard-delete records whose source file no longer exists
            (records previously soft-flagged with `missing_since`).

    Returns JSON summarizing scanned files, indexed markers, flagged records,
    and any force-deleted rows.
    """
    conn = get_db()
    try:
        return serialize(surface(conn, force=force))
    finally:
        conn.close()
