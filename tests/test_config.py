"""config path resolution + marker_mode tests."""
from __future__ import annotations

from pathlib import Path

from scry.config import (
    get_db_path,
    get_lock_path,
    get_marker_mode,
    get_project_root,
    get_scripts_dir,
    get_scry_dir,
)


def test_get_project_root_walks_for_dot_scry(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / ".scry").mkdir(parents=True)
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    assert get_project_root(nested) == root


def test_get_project_root_falls_back_to_start(tmp_path: Path) -> None:
    start = tmp_path / "no-sentinel"
    start.mkdir()
    assert get_project_root(start) == start.resolve()


def test_path_helpers_root_under_dot_scry(tmp_path: Path) -> None:
    assert get_scry_dir(tmp_path) == tmp_path / ".scry"
    assert get_db_path(tmp_path) == tmp_path / ".scry" / "data" / "project.db"
    assert get_lock_path(tmp_path) == tmp_path / ".scry" / "runtime" / "lock"
    assert get_scripts_dir(tmp_path) == tmp_path / ".scry" / "scripts"


def test_marker_mode_defaults_to_inline_when_no_config(tmp_path: Path) -> None:
    assert get_marker_mode(tmp_path) == "inline"


def test_marker_mode_reads_off_from_config(tmp_path: Path) -> None:
    scry_dir = tmp_path / ".scry"
    scry_dir.mkdir()
    (scry_dir / "config.toml").write_text('marker_mode = "off"\n', encoding="utf-8")
    assert get_marker_mode(tmp_path) == "off"


def test_marker_mode_reads_sidecar_from_config(tmp_path: Path) -> None:
    scry_dir = tmp_path / ".scry"
    scry_dir.mkdir()
    (scry_dir / "config.toml").write_text('marker_mode = "sidecar"\n', encoding="utf-8")
    assert get_marker_mode(tmp_path) == "sidecar"


def test_marker_mode_invalid_value_defaults_to_inline(tmp_path: Path) -> None:
    scry_dir = tmp_path / ".scry"
    scry_dir.mkdir()
    (scry_dir / "config.toml").write_text('marker_mode = "bogus"\n', encoding="utf-8")
    assert get_marker_mode(tmp_path) == "inline"
