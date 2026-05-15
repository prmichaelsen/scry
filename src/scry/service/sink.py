"""scry_sink service — lower the index back to disk-only state.

Truncates all five scry index tables in a single atomic transaction.
Schema is preserved; FTS tables update via existing triggers; the
migration table is never touched.  Disk markers remain intact.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from scry.config import get_project_root
from scry.service.surface import surface as _surface

# Tables cleared by sink, in dependency-safe order.
SINK_TABLES = (
    "doc_relationship",
    "scry__warning",
    "scry__bind",
    "scry__anchor",
    "scry__doc",
)


def get_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Return current row counts for all sink-affected tables."""
    counts: dict[str, int] = {}
    for table in SINK_TABLES:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        counts[table] = int(row["n"]) if row else 0
    return counts


def sink(
    conn: sqlite3.Connection,
    then_surface: bool = False,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Truncate all scry index tables in a single atomic transaction.

    FTS shadow tables update automatically via the existing AFTER DELETE
    triggers.  The migration table is not touched.  Disk markers are
    never modified.

    Args:
        conn: Database connection.
        then_surface: If True, immediately runs surface() after the sink.
                      Lets the caller express "reset + reindex" in one call.
        project_root: Project root for then_surface (defaults to get_project_root()).

    Returns a dict with the counts of rows cleared (pre-deletion counts)
    and optional surface results.

    Raises on any DB error; partial deletes are rolled back.
    """
    counts = get_counts(conn)
    try:
        for table in SINK_TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    result: dict[str, Any] = {"cleared": counts}

    if then_surface:
        root = project_root or get_project_root()
        result["surface"] = _surface(conn, project_root=root)

    return result
