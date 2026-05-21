"""Tests for the scry_db_health MCP tool."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from scry.service.migration import run_migrations
from scry.tools.scry_db_health import scry_db_health


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def _migrated_db(path: Path) -> None:
    """Create a migrated empty DB at `path`."""
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    run_migrations(conn=c)
    c.close()


def _call_health(db_path: Path) -> dict:
    """Invoke scry_db_health against a custom DB path. Returns parsed JSON."""
    # The tool calls scry.config.get_db() with no args, which uses
    # get_db_path() under the hood. Patch both to return our test path.
    real_get_db = sqlite3.connect

    def _fake_get_db():
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.row_factory = sqlite3.Row
        return conn

    with patch("scry.tools.scry_db_health.get_db", _fake_get_db), \
         patch("scry.config.get_db_path", return_value=db_path):
        out = _run(scry_db_health())
    return json.loads(out)


# ---------------------------------------------------------------------------
# Happy path — healthy DB with rows
# ---------------------------------------------------------------------------

def test_health_ok_on_migrated_empty_db(tmp_path):
    db = tmp_path / "project.db"
    _migrated_db(db)

    result = _call_health(db)

    assert result["status"] == "ok"
    assert result["integrity"] == "ok"
    assert result["doc_count"] == 0
    assert result["doc_count_error"] is None
    assert result["error"] is None
    assert result["db_path"] == str(db)


def test_health_ok_with_row_count(tmp_path):
    db = tmp_path / "project.db"
    _migrated_db(db)

    # Drop a row into scry__doc directly so doc_count > 0.
    c = sqlite3.connect(str(db))
    c.execute(
        "INSERT INTO scry__doc (id, kind, status, weight, summary, "
        "rationale, applies, current_path, content_hash) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "design.test~deadbeef",
            "design",
            "active",
            1.0,
            "summary",
            "rationale",
            "applies",
            "test.md",
            "deadbeef",
        ),
    )
    c.commit()
    c.close()

    result = _call_health(db)
    assert result["status"] == "ok"
    assert result["doc_count"] == 1


# ---------------------------------------------------------------------------
# Fresh / unmigrated DB
# ---------------------------------------------------------------------------

def test_health_ok_but_unmigrated_reports_missing_table(tmp_path):
    db = tmp_path / "project.db"
    # Touch the file so SQLite opens it — but do NOT run migrations.
    sqlite3.connect(str(db)).close()

    result = _call_health(db)

    assert result["status"] == "ok"
    assert result["integrity"] == "ok"
    assert result["doc_count"] is None
    assert "no such table" in (result["doc_count_error"] or "").lower()


# ---------------------------------------------------------------------------
# Hard corruption — "file is not a database"
# ---------------------------------------------------------------------------

def test_health_corrupt_on_garbage_file(tmp_path):
    db = tmp_path / "project.db"
    # Write garbage bytes — SQLite header check will fail.
    db.write_bytes(b"NOT_A_SQLITE_DB_HEADER" + b"\x00" * 200)

    result = _call_health(db)

    assert result["status"] == "corrupt"
    # Either integrity_check failed OR connect/PRAGMA raised — either way
    # the tool reports an error string.
    assert result["error"] is not None


# ---------------------------------------------------------------------------
# Integrity-check failure (synthetic)
# ---------------------------------------------------------------------------

def test_health_corrupt_when_integrity_check_returns_non_ok(tmp_path):
    """If PRAGMA integrity_check returns anything but 'ok', status=corrupt."""
    db = tmp_path / "project.db"
    _migrated_db(db)

    # Patch the connection so integrity_check reports a malformed-page row.
    class _FakeConn:
        def __init__(self):
            self.closed = False

        def execute(self, sql, *a, **kw):
            class _C:
                def __init__(self, sql_):
                    self.sql = sql_

                def fetchone(self):
                    if "integrity_check" in self.sql:
                        return ("*** in database main ***\nPage 5: btreeInitPage()",)
                    return (0,)
            return _C(sql)

        def close(self):
            self.closed = True

    with patch("scry.tools.scry_db_health.get_db", return_value=_FakeConn()), \
         patch("scry.config.get_db_path", return_value=db):
        out = _run(scry_db_health())

    result = json.loads(out)
    assert result["status"] == "corrupt"
    assert "integrity_check" in result["error"]


# ---------------------------------------------------------------------------
# Locked DB — must NOT be reported as corrupt
# ---------------------------------------------------------------------------

def test_health_locked_when_open_raises_lock_error(tmp_path):
    """A 'database is locked' error from get_db must produce status=locked."""
    db = tmp_path / "project.db"

    def _raises_lock():
        raise sqlite3.OperationalError("database is locked")

    with patch("scry.tools.scry_db_health.get_db", side_effect=_raises_lock), \
         patch("scry.config.get_db_path", return_value=db):
        out = _run(scry_db_health())

    result = json.loads(out)
    assert result["status"] == "locked"
    assert "database is locked" in result["error"]


def test_health_locked_when_integrity_check_raises_lock(tmp_path):
    """A lock error inside integrity_check must produce status=locked, not corrupt."""
    db = tmp_path / "project.db"

    class _LockingConn:
        def execute(self, sql, *a, **kw):
            if "integrity_check" in sql:
                raise sqlite3.OperationalError("database is locked")
            class _C:
                def fetchone(self):
                    return (0,)
            return _C()

        def close(self):
            pass

    with patch("scry.tools.scry_db_health.get_db", return_value=_LockingConn()), \
         patch("scry.config.get_db_path", return_value=db):
        out = _run(scry_db_health())

    result = json.loads(out)
    assert result["status"] == "locked"
    assert "database is locked" in result["error"]


def test_health_locked_when_disk_io_error_on_open(tmp_path):
    """SQLITE_IOERR — surfaced as 'disk I/O error' — is transient, not corruption."""
    db = tmp_path / "project.db"

    def _raises_io():
        raise sqlite3.OperationalError("disk I/O error")

    with patch("scry.tools.scry_db_health.get_db", side_effect=_raises_io), \
         patch("scry.config.get_db_path", return_value=db):
        out = _run(scry_db_health())

    result = json.loads(out)
    assert result["status"] == "locked"
