"""Configuration: project root detection, DB path, connection factory."""
from __future__ import annotations

import sqlite3
import tomllib
from pathlib import Path
from typing import Literal

EXCLUDED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "dist"})
DEBOUNCE_MS = 150
BINARY_SNIFF_BYTES = 512


def get_project_root(start: Path | None = None) -> Path:
    p = (start or Path.cwd()).resolve()
    while p != p.parent:
        if (p / "agent").is_dir():
            return p
        p = p.parent
    return (start or Path.cwd()).resolve()


def get_namespace(project_root: Path | None = None) -> str:
    root = project_root or get_project_root()
    drivers = root / "agent" / "drivers"
    if drivers.is_dir():
        for entry in sorted(drivers.iterdir()):
            if entry.name.startswith("@") and (entry / "scry").is_dir():
                return entry.name[1:]
    return "local"


def get_driver_dir(project_root: Path | None = None) -> Path:
    root = project_root or get_project_root()
    return root / "agent" / "drivers" / f"@{get_namespace(root)}" / "scry"


def get_db_path(project_root: Path | None = None) -> Path:
    return get_driver_dir(project_root) / "data" / "project.db"


def get_lock_path(project_root: Path | None = None) -> Path:
    return get_driver_dir(project_root) / "runtime" / "lock"


def get_driver_scripts_dir(project_root: Path | None = None) -> Path:
    return get_driver_dir(project_root) / "scripts"


MarkerMode = Literal["inline", "sidecar"]

_VALID_MARKER_MODES: frozenset[str] = frozenset({"inline", "sidecar"})


def get_marker_mode(project_root: Path | None = None) -> MarkerMode:
    """Read marker_mode from config.toml. Defaults to 'inline'."""
    config_path = get_driver_dir(project_root) / "config.toml"
    if not config_path.is_file():
        return "inline"
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return "inline"
    mode = data.get("marker_mode", "inline")
    if mode not in _VALID_MARKER_MODES:
        return "inline"
    return mode  # type: ignore[return-value]


def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # timeout=30: Python-level busy handler (seconds).
    # PRAGMA busy_timeout: SQLite C-level timeout (milliseconds).
    # Both are set because WAL write-lock acquisition can go through
    # either path depending on SQLite build and platform. Under
    # concurrent wake load (3-5 scry serve processes sharing one DB),
    # 10 s was too short for write-lock contention — 30 s covers the
    # observed worst case without masking actual errors.
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    return conn
