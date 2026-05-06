"""Misplacement warnings: docs belong inside agent/, files describe non-agent source."""
from __future__ import annotations

from pathlib import Path

from scry.service.surface import handle_file_deletion, surface


DOC_BLOCK = """\
<!-- @scry.doc
id: task.example~12345678
kind: task
summary: example
status: active
weight: 0.5
@scry.doc.end -->
"""

FILE_BLOCK = """\
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


def test_file_inside_agent_warns_but_indexes(conn, project_tree):
    _write(project_tree / "agent" / "internal" / "weird.py", FILE_BLOCK)
    surface(conn, project_root=project_tree)
    row = conn.execute("SELECT id FROM scry__file WHERE id = 'file.app~aaaaaaaa'").fetchone()
    assert row is not None
    w = conn.execute("SELECT kind, marker_id FROM scry__warning").fetchall()
    assert len(w) == 1
    assert w[0]["kind"] == "misplaced_file"


def test_doc_inside_agent_no_warning(conn, project_tree):
    _write(project_tree / "agent" / "tasks" / "ok.md", DOC_BLOCK)
    surface(conn, project_root=project_tree)
    rows = conn.execute("SELECT * FROM scry__warning").fetchall()
    assert rows == []


def test_file_outside_agent_no_warning(conn, project_tree):
    _write(project_tree / "src" / "app.py", FILE_BLOCK)
    surface(conn, project_root=project_tree)
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


def test_file_marker_indexed_when_outside_agent(conn, project_tree):
    """Regression: confirm the surface→DB pipeline for files (not previously covered)."""
    _write(project_tree / "src" / "app.py", FILE_BLOCK)
    out = surface(conn, project_root=project_tree)
    assert out["markers_indexed"] >= 1
    rows = conn.execute("SELECT id, kind, current_path FROM scry__file").fetchall()
    assert len(rows) == 1
    assert rows[0]["id"] == "file.app~aaaaaaaa"
    assert rows[0]["kind"] == "module"
    assert rows[0]["current_path"] == "src/app.py"
