"""Shared helpers for tool wrappers."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from scry.config import get_db


def serialize(payload: Any) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


_TRANSIENT_ERRORS = ("disk I/O error", "database is locked")
_MAX_RETRIES = 3


def with_conn(fn):
    """Decorator: open a DB connection, pass as first arg, always close.

    Retries up to _MAX_RETRIES times on transient SQLite errors (disk I/O
    error, database is locked) caused by WAL write-lock contention under
    concurrent wake load. Each retry opens a fresh connection. Delays
    use exponential back-off: 0.1 s, 0.3 s (then raise on attempt 3).
    The finally clause always closes the connection regardless of outcome.
    """
    def wrapper(*args, **kwargs):
        for attempt in range(_MAX_RETRIES):
            conn: sqlite3.Connection = get_db()
            try:
                return fn(conn, *args, **kwargs)
            except sqlite3.OperationalError as exc:
                is_transient = any(e in str(exc) for e in _TRANSIENT_ERRORS)
                is_last = attempt == _MAX_RETRIES - 1
                if is_transient and not is_last:
                    time.sleep(0.1 * (3 ** attempt))  # 0.1 s, 0.3 s
                    continue
                raise
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper
