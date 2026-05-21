"""scry_db_health MCP tool — sqlite integrity probe with lock/corruption split."""
from __future__ import annotations

import sqlite3

from scry.config import get_db
from scry.tools._common import serialize


_TRANSIENT_FRAGMENTS = ("database is locked", "disk i/o error")
_HARD_CORRUPTION_FRAGMENTS = (
    "file is not a database",
    "database disk image is malformed",
    "not a database",
    "malformed",
)


def _classify_open_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if any(f in msg for f in _TRANSIENT_FRAGMENTS):
        return "locked"
    if any(f in msg for f in _HARD_CORRUPTION_FRAGMENTS):
        return "corrupt"
    return "corrupt"


async def scry_db_health() -> str:
    """Probe the scry project database and report health.

    Designed for substrate code (e.g. reflection's `wake.py` auto-restore
    loop) that needs to distinguish actual corruption from transient WAL
    write-lock contention. The same scry-mcp connection primitives are
    used as for every other tool — long `busy_timeout`, WAL journal mode,
    retry semantics — so a healthy-but-busy DB will not be reported as
    corrupt.

    Returns JSON with these fields:

      status         "ok" | "corrupt" | "locked"
      integrity      result of `PRAGMA integrity_check` (string), or null
                     when the probe could not run (e.g. status=locked)
      doc_count      integer row count of `scry__doc`, or null when the
                     table does not exist yet (fresh / unmigrated DB)
      doc_count_error  populated when doc_count is null and the count
                     query failed for a known-benign reason (table
                     missing); null otherwise
      db_path        absolute path to the project.db file probed
      error          string explanation when status != "ok"; null otherwise

    Status semantics for substrate decisions:

      status="ok"      DB is healthy. Do not quarantine.
      status="locked"  DB is healthy but contended. Do NOT quarantine;
                       retry the probe on the next wake. Substrate code
                       that conflates this with corruption causes the
                       Group-C cascade described in the May 2026
                       diagnostic.
      status="corrupt" DB failed `PRAGMA integrity_check` or could not
                       be opened as a SQLite database at all. Safe to
                       initiate auto-restore.

    A status="ok" with doc_count=null and doc_count_error="no such
    table: scry__doc" is a fresh-and-unmigrated DB. Substrate should
    run migrations (or call `scry_surface`) rather than quarantine.
    """
    from scry.config import get_db_path

    db_path = get_db_path()
    payload: dict = {
        "status": "ok",
        "integrity": None,
        "doc_count": None,
        "doc_count_error": None,
        "db_path": str(db_path),
        "error": None,
    }

    try:
        conn = get_db()
    except sqlite3.OperationalError as exc:
        payload["status"] = _classify_open_error(exc)
        payload["error"] = str(exc)
        return serialize(payload)
    except Exception as exc:
        payload["status"] = "corrupt"
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return serialize(payload)

    try:
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if any(f in msg for f in _TRANSIENT_FRAGMENTS):
                payload["status"] = "locked"
                payload["error"] = str(exc)
                return serialize(payload)
            payload["status"] = "corrupt"
            payload["error"] = str(exc)
            return serialize(payload)

        if row is None:
            payload["status"] = "corrupt"
            payload["error"] = "PRAGMA integrity_check returned no row"
            return serialize(payload)

        integrity_value = row[0]
        payload["integrity"] = integrity_value
        if integrity_value != "ok":
            payload["status"] = "corrupt"
            payload["error"] = f"integrity_check: {integrity_value}"
            return serialize(payload)

        try:
            count_row = conn.execute("SELECT count(*) FROM scry__doc").fetchone()
            payload["doc_count"] = int(count_row[0]) if count_row else 0
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "no such table" in msg:
                # Fresh / unmigrated DB. Not corruption — substrate should
                # migrate, not quarantine.
                payload["doc_count_error"] = str(exc)
            elif any(f in msg for f in _TRANSIENT_FRAGMENTS):
                payload["status"] = "locked"
                payload["error"] = str(exc)
            else:
                payload["status"] = "corrupt"
                payload["error"] = str(exc)

        return serialize(payload)
    finally:
        try:
            conn.close()
        except Exception:
            pass
