"""scry_sql MCP tool — read-only SQL gateway."""
from __future__ import annotations

from scry.config import get_db
from scry.service.query import run_query
from scry.tools._common import serialize


async def scry_sql(query: str) -> str:
    """Execute a read-only SQL query against the scry cache.

    Only SELECT and WITH statements are accepted. Mutating keywords
    (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, REPLACE, TRUNCATE, ATTACH,
    DETACH, PRAGMA, VACUUM, REINDEX) are rejected.

    Returns JSON: {"results": [...], "row_count": N} on success or
    {"error": "..."} on rejection.
    """
    conn = get_db()
    try:
        return serialize(run_query(conn, query))
    finally:
        conn.close()
