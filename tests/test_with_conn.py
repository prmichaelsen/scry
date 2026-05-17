"""Tests for with_conn retry-on-transient-error behavior."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from scry.tools._common import _MAX_RETRIES, _TRANSIENT_ERRORS, with_conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fn(side_effects):
    """Return a with_conn-wrapped fn that raises the given side effects in order."""
    call_log = []

    def _inner(conn, *args, **kwargs):
        call_log.append(1)
        if side_effects:
            exc = side_effects.pop(0)
            if exc is not None:
                raise exc
        return "ok"

    wrapped = with_conn(_inner)
    return wrapped, call_log


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

def test_with_conn_success(tmp_path):
    """Function succeeds on first attempt — no retries."""
    wrapped, log = _make_fn([])
    with patch("scry.tools._common.get_db") as mock_db:
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_db.return_value = mock_conn
        result = wrapped()
    assert result == "ok"
    assert len(log) == 1
    mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# Transient retry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", _TRANSIENT_ERRORS)
def test_with_conn_retries_transient(msg):
    """Transient errors trigger retries; succeeds on 2nd attempt."""
    call_log = []
    attempts = [0]

    def _inner(conn, *args, **kwargs):
        attempts[0] += 1
        call_log.append(attempts[0])
        if attempts[0] == 1:
            raise sqlite3.OperationalError(msg)
        return "recovered"

    wrapped = with_conn(_inner)

    with patch("scry.tools._common.get_db") as mock_db, \
         patch("scry.tools._common.time.sleep") as mock_sleep:
        mock_db.return_value = MagicMock(spec=sqlite3.Connection)
        result = wrapped()

    assert result == "recovered"
    assert attempts[0] == 2
    mock_sleep.assert_called_once()


def test_with_conn_exhausts_retries():
    """If all _MAX_RETRIES attempts fail with transient error, raises on last."""
    call_log = []

    def _inner(conn, *args, **kwargs):
        call_log.append(1)
        raise sqlite3.OperationalError("disk I/O error")

    wrapped = with_conn(_inner)

    with patch("scry.tools._common.get_db") as mock_db, \
         patch("scry.tools._common.time.sleep"):
        mock_db.return_value = MagicMock(spec=sqlite3.Connection)
        with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
            wrapped()

    assert len(call_log) == _MAX_RETRIES


# ---------------------------------------------------------------------------
# Non-transient errors are NOT retried
# ---------------------------------------------------------------------------

def test_with_conn_no_retry_on_non_transient():
    """Non-transient OperationalError raises immediately, no retry."""
    call_log = []

    def _inner(conn, *args, **kwargs):
        call_log.append(1)
        raise sqlite3.OperationalError("no such table: foo")

    wrapped = with_conn(_inner)

    with patch("scry.tools._common.get_db") as mock_db, \
         patch("scry.tools._common.time.sleep") as mock_sleep:
        mock_db.return_value = MagicMock(spec=sqlite3.Connection)
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            wrapped()

    assert len(call_log) == 1
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Connection is always closed
# ---------------------------------------------------------------------------

def test_with_conn_closes_on_success():
    """Connection is closed after a successful call."""
    def _inner(conn):
        return "done"

    wrapped = with_conn(_inner)
    with patch("scry.tools._common.get_db") as mock_db:
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_db.return_value = mock_conn
        wrapped()
    mock_conn.close.assert_called()


def test_with_conn_closes_on_failure():
    """Connection is closed even when the call raises."""
    def _inner(conn):
        raise ValueError("boom")

    wrapped = with_conn(_inner)
    with patch("scry.tools._common.get_db") as mock_db:
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_db.return_value = mock_conn
        with pytest.raises(ValueError):
            wrapped()
    mock_conn.close.assert_called()
