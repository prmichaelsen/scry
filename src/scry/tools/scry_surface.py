"""scry_surface MCP tool — batch reindex from disk."""
from __future__ import annotations

from scry.config import get_db
from scry.service.surface import surface
from scry.tools._common import serialize


async def scry_surface(force: bool = False, path: str | None = None) -> str:
    """Rebuild the DB from disk markers. Use after git pull, bulk file moves,
    or if query results seem stale. The file watcher handles live indexing —
    only call this for full re-scans.

    Walks all project files, parses @scry.* markers, upserts to DB.
    Idempotent. Uses content-hash dedup.

    Args:
        force: If true, hard-deletes records whose files no longer exist.
               If false (default), sets missing_since and warns.
        path: Optional scope, relative to project root.
              None (default) — full corpus walk. Current behavior, unchanged.
              <file> — re-index exactly that one file.
              <directory> — re-index every file under that directory, recursively.
              If path does not exist on disk, returns a clear error.
              Scoped reconciliation: flagged_missing, misplaced_doc warnings, and
              force-deletes are all scoped to the path — docs outside the scope
              are never flagged as missing.

    Returns JSON with counts per marker type, any warnings, and a scope field
    echoing the path argument (null for a full walk).
    """
    conn = get_db()
    try:
        try:
            return serialize(surface(conn, force=force, path=path))
        except ValueError as exc:
            return serialize({"error": str(exc), "scope": path})
    finally:
        conn.close()
