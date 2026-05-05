"""Sequential SQL migration runner."""
from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from scry.config import get_db


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def _applied(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM migration").fetchall()
    return {r["name"] for r in rows}


def _list_migration_files() -> list[tuple[str, str]]:
    files = resources.files("scry.migrations")
    out: list[tuple[str, str]] = []
    for entry in files.iterdir():
        name = entry.name
        if name.endswith(".sql"):
            out.append((name, entry.read_text(encoding="utf-8")))
    out.sort(key=lambda x: x[0])
    return out


def run_migrations(db_path: Path | None = None, conn: sqlite3.Connection | None = None) -> list[str]:
    """Apply pending migrations. Returns names of newly applied migrations."""
    own_conn = conn is None
    c = conn or get_db(db_path)
    try:
        _ensure_migration_table(c)
        already = _applied(c)
        applied: list[str] = []
        for name, sql in _list_migration_files():
            if name in already:
                continue
            c.executescript(sql)
            c.execute("INSERT INTO migration(name) VALUES (?)", (name,))
            c.commit()
            applied.append(name)
        return applied
    finally:
        if own_conn:
            c.close()
