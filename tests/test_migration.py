"""Migration tests — ensure ALTER paths run idempotently on legacy DBs.

The fresh-install path (`001_initial.sql`) is exercised by the `conn`
fixture in every other test file; these tests cover the backfill paths
that mutate already-migrated databases.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scry.service.migration import run_migrations


def _table_columns(c: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}


def test_extras_column_added_to_legacy_db(tmp_path: Path):
    """A pre-extras scry__doc table gets the column on next migrate run."""
    db = tmp_path / "legacy.db"
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    try:
        # Simulate a legacy DB: create scry__doc WITHOUT the extras column.
        c.execute(
            """
            CREATE TABLE scry__doc (
              id           TEXT PRIMARY KEY,
              kind         TEXT NOT NULL DEFAULT 'internal',
              summary      TEXT NOT NULL DEFAULT '',
              rationale    TEXT,
              applies      TEXT,
              status       TEXT NOT NULL DEFAULT 'active',
              weight       REAL NOT NULL DEFAULT 0.5,
              current_path TEXT,
              content_hash TEXT,
              ephemeral    INTEGER NOT NULL DEFAULT 0,
              missing_since TEXT,
              created_at   TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        c.commit()
        assert "extras" not in _table_columns(c, "scry__doc")

        run_migrations(conn=c)

        assert "extras" in _table_columns(c, "scry__doc")
    finally:
        c.close()


def test_migration_idempotent_on_already_migrated_db(tmp_path: Path):
    """Running migrations twice does not raise (no duplicate-column error)."""
    db = tmp_path / "fresh.db"
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    try:
        run_migrations(conn=c)
        run_migrations(conn=c)  # must not raise

        assert "extras" in _table_columns(c, "scry__doc")
    finally:
        c.close()
