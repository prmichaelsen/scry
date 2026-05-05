"""scry_sql — read-only SQL gateway."""
from __future__ import annotations

import re
import sqlite3
from typing import Any

_MUTATORS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "REPLACE", "TRUNCATE", "ATTACH", "DETACH", "PRAGMA",
    "VACUUM", "REINDEX",
)


def _strip_sql(sql: str) -> str:
    """Remove block (/* */) and line (-- ...) comments, then collapse whitespace."""
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", " ", no_block)
    return " ".join(no_line.split())


def validate_query(query: str) -> str | None:
    """Return error string if the query is rejected, else None."""
    if not query or not query.strip():
        return "empty query"
    cleaned = _strip_sql(query).upper()
    for kw in _MUTATORS:
        if re.search(rf"\b{kw}\b", cleaned):
            return f"query rejected: contains mutator keyword `{kw}`"
    first = cleaned.lstrip().split(" ", 1)[0] if cleaned.strip() else ""
    if first not in {"SELECT", "WITH"}:
        return "query rejected: must start with SELECT or WITH"
    return None


def run_query(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    err = validate_query(query)
    if err:
        return {"error": err}
    cursor = conn.execute(query)
    rows = cursor.fetchall()
    columns = [d[0] for d in cursor.description] if cursor.description else []
    results = [dict(zip(columns, row)) for row in rows]
    return {"results": results, "row_count": len(results)}
