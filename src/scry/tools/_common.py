"""Shared helpers for tool wrappers."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from scry.config import get_db


def serialize(payload: Any) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


def with_conn(fn):
    """Decorator: open a DB connection, pass as first arg, always close."""
    def wrapper(*args, **kwargs):
        conn: sqlite3.Connection = get_db()
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper
