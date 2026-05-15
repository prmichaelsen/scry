"""Schema initializer — applies 001_initial.sql to a fresh or existing DB.

The DB is a pure cache of on-disk markers.  Customers can `rm project.db`
at any time; the watcher rebuilds on next startup.  No migration history
table is needed — the schema is idempotent (CREATE TABLE IF NOT EXISTS).
"""
from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from scry.config import get_db


def _cleanup_legacy_triggers(c: sqlite3.Connection) -> None:
    """Drop triggers that were added in old schema versions but conflict with the
    explicit FTS management in surface.py.

    Specifically, scry__doc_tag_ai / scry__doc_tag_ad and the seeded-question
    equivalents were created by pre-0.12.0 schema but cause 'SQL logic error'
    when the FTS tables are managed explicitly (as they are now).  These triggers
    are not present in 001_initial.sql, so new DBs are clean; this function
    sanitises existing DBs.
    """
    legacy = [
        # Join-table FTS triggers that used the content-backed 'delete' INSERT
        # syntax on standard FTS5 tables.  Removed in 0.15.0; surface.py now
        # manages join-table FTS explicitly.
        "scry__doc_tag_ai",
        "scry__doc_tag_ad",
        "scry__doc_sq_ai",
        "scry__doc_sq_ad",
        "scry__anchor_sq_ai",
        "scry__anchor_sq_ad",
    ]
    for name in legacy:
        c.execute(f"DROP TRIGGER IF EXISTS {name}")
    c.commit()


def run_migrations(db_path: Path | None = None, conn: sqlite3.Connection | None = None) -> None:
    """Apply the schema to the database.  Safe to call on every startup."""
    own_conn = conn is None
    c = conn or get_db(db_path)
    try:
        sql = resources.files("scry.migrations").joinpath("001_initial.sql").read_text(encoding="utf-8")
        c.executescript(sql)
        _cleanup_legacy_triggers(c)
        c.commit()
    finally:
        if own_conn:
            c.close()
