"""scry_sink service — lower the index back to disk-only state.

Truncates all scry index tables in a single atomic transaction.
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
# Join tables (scry__doc_tag, scry__doc_seeded_question, scry__anchor_seeded_question)
# are cleared via ON DELETE CASCADE from scry__doc. scry__rel cascades from scry__doc.
# scry__anchor cascades from scry__doc. scry__bind cascades from scry__doc.
# We clear them explicitly here so FTS shadow table triggers fire correctly.
SINK_TABLES = (
    "scry__warning",
    "scry__anchor_seeded_question",
    "scry__anchor",
    "scry__doc_seeded_question",
    "scry__doc_tag",
    "scry__rel",
    "scry__bind",
    "scry__doc",
    "scry__file",
)

# Legacy tables that may exist in older DBs — dropped if present, silently skipped if not.
_LEGACY_TABLES = (
    "doc_relationship",
    "scry__impl",
    "scry__test",
)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def get_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Return current row counts for all sink-affected tables (skips missing tables)."""
    counts: dict[str, int] = {}
    for table in SINK_TABLES:
        if _table_exists(conn, table):
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
        then_surface: If True, immediately runs surface() after the sink to
                      rebuild the index from disk markers. The schema is
                      preserved as-is; use this for "reset + reindex."
        project_root: Project root for then_surface (defaults to get_project_root()).

    Returns a dict with the counts of rows cleared (pre-deletion counts)
    and optional surface results.

    Raises on any DB error; partial deletes are rolled back.
    """
    counts = get_counts(conn)
    try:
        for table in SINK_TABLES:
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        # Clear legacy tables silently if they still exist.
        for table in _LEGACY_TABLES:
            if _table_exists(conn, table):
                conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    result: dict[str, Any] = {"cleared": counts}

    if then_surface:
        root = project_root or get_project_root()
        result["surface"] = _surface(conn, project_root=root)

    return result
