from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scry.service.migration import run_migrations


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "scry.db"


@pytest.fixture
def conn(db_path: Path):
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    run_migrations(conn=c)
    yield c
    c.close()


@pytest.fixture
def project_tree(tmp_path: Path) -> Path:
    (tmp_path / "agent").mkdir()
    return tmp_path
