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


def run_migrations(db_path: Path | None = None, conn: sqlite3.Connection | None = None) -> None:
    """Apply the schema to the database.  Safe to call on every startup."""
    own_conn = conn is None
    c = conn or get_db(db_path)
    try:
        sql = resources.files("scry.migrations").joinpath("001_initial.sql").read_text(encoding="utf-8")
        c.executescript(sql)
        c.commit()
    finally:
        if own_conn:
            c.close()
