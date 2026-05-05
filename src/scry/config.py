"""Configuration: project root detection, DB path, connection factory."""
from __future__ import annotations

import sqlite3
from pathlib import Path

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


def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn
