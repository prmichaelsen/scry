"""scry_surface MCP tool — batch reindex from disk."""
from __future__ import annotations

from scry.config import get_db
from scry.service.surface import surface
from scry.tools._common import serialize


async def scry_surface(force: bool = False) -> str:
    """Rebuild the DB from disk markers. Use after git pull, bulk file moves,
    or if query results seem stale. The file watcher handles live indexing —
    only call this for full re-scans.

    Walks all project files, parses @scry.* markers, upserts to DB.
    Idempotent. Uses content-hash dedup.

    Args:
        force: If true, hard-deletes records whose files no longer exist.
               If false (default), sets missing_since and warns.

    Returns JSON with counts per marker type and any warnings.
    """
    conn = get_db()
    try:
        return serialize(surface(conn, force=force))
    finally:
        conn.close()
