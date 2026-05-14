"""Misplacement warnings: docs belong inside agent/.

scry-spec v1.0: @scry.file is no longer recognized; only @scry.entry and
@scry.anchor block markers are parsed. Legacy @scry.file content is ignored.
"""
from __future__ import annotations

from pathlib import Path

from scry.service.surface import handle_file_deletion, surface


DOC_BLOCK = """\
<!-- @scry.entry
id: task.example~12345678
kind: task
summary: example
status: active
weight: 0.5
@scry.entry.end -->
"""

# Legacy @scry.file marker — should NOT be parsed or indexed.
LEGACY_FILE_BLOCK = """\
# @scry.file
# id: file.app~aaaaaaaa
# kind: module
# summary: app entry
# status: active
# weight: 0.5
# @scry.file.end
"""


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_doc_outside_agent_warns_but_indexes(conn, project_tree):
    _write(project_tree / "src" / "stray.md", DOC_BLOCK)
    out = surface(conn, project_root=project_tree)
    # Doc is still indexed.
    row = conn.execute("SELECT id FROM scry__doc WHERE id = 'task.example~12345678'").fetchone()
    assert row is not None
    # Warning recorded.
    w = conn.execute("SELECT kind, marker_id, file_path FROM scry__warning").fetchall()
    assert len(w) == 1
    assert w[0]["kind"] == "misplaced_doc"
    assert w[0]["marker_id"] == "task.example~12345678"
    assert out["warnings"]["counts"].get("misplaced_doc") == 1


def test_legacy_file_marker_not_indexed(conn, project_tree):
    """@scry.file is no longer recognized — legacy files are ignored, no warnings emitted."""
    _write(project_tree / "agent" / "internal" / "weird.py", LEGACY_FILE_BLOCK)
    out = surface(conn, project_root=project_tree)
    assert out["markers_indexed"] == 0
    rows = conn.execute("SELECT * FROM scry__warning").fetchall()
    assert rows == []


def test_doc_inside_agent_no_warning(conn, project_tree):
    _write(project_tree / "agent" / "tasks" / "ok.md", DOC_BLOCK)
    surface(conn, project_root=project_tree)
    rows = conn.execute("SELECT * FROM scry__warning").fetchall()
    assert rows == []


def test_legacy_file_outside_agent_no_warning(conn, project_tree):
    """Legacy @scry.file content outside agent/ — not parsed, no warnings."""
    _write(project_tree / "src" / "app.py", LEGACY_FILE_BLOCK)
    out = surface(conn, project_root=project_tree)
    assert out["markers_indexed"] == 0
    rows = conn.execute("SELECT * FROM scry__warning").fetchall()
    assert rows == []


def test_warning_clears_when_marker_moves(conn, project_tree):
    stray = project_tree / "src" / "stray.md"
    _write(stray, DOC_BLOCK)
    surface(conn, project_root=project_tree)
    assert conn.execute("SELECT COUNT(*) FROM scry__warning").fetchone()[0] == 1

    # Move it into agent/
    stray.unlink()
    _write(project_tree / "agent" / "tasks" / "moved.md", DOC_BLOCK)
    surface(conn, project_root=project_tree)
    rows = conn.execute("SELECT * FROM scry__warning").fetchall()
    assert rows == []


def test_warning_clears_on_file_deletion(conn, project_tree):
    f = project_tree / "src" / "stray.md"
    _write(f, DOC_BLOCK)
    surface(conn, project_root=project_tree)
    assert conn.execute("SELECT COUNT(*) FROM scry__warning").fetchone()[0] == 1
    handle_file_deletion(conn, "src/stray.md")
    assert conn.execute("SELECT COUNT(*) FROM scry__warning").fetchone()[0] == 0
