"""scry_surface tests (FR20-FR22)."""
from __future__ import annotations

from pathlib import Path

from scry.service.surface import handle_file_deletion, reindex_file, surface


DOC_BLOCK = """\
<!-- @scry.doc
id: task.example~12345678
kind: task
summary: example
status: active
weight: 0.5
@scry.doc.end -->
"""


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_surface_indexes_markers(conn, project_tree):
    _write(project_tree / "agent" / "tasks" / "ex.md", DOC_BLOCK)
    out = surface(conn, project_root=project_tree)
    assert out["files_scanned"] >= 1
    rows = conn.execute("SELECT id, current_path, kind FROM scry__doc").fetchall()
    assert any(r["id"] == "task.example~12345678" for r in rows)


def test_surface_idempotent_no_updates(conn, project_tree):
    f = project_tree / "agent" / "tasks" / "ex.md"
    _write(f, DOC_BLOCK)
    surface(conn, project_root=project_tree)
    before = conn.execute(
        "SELECT updated_at FROM scry__doc WHERE id = 'task.example~12345678'"
    ).fetchone()["updated_at"]
    surface(conn, project_root=project_tree)
    after = conn.execute(
        "SELECT updated_at FROM scry__doc WHERE id = 'task.example~12345678'"
    ).fetchone()["updated_at"]
    assert before == after


def test_surface_flags_missing(conn, project_tree):
    f = project_tree / "agent" / "tasks" / "ex.md"
    _write(f, DOC_BLOCK)
    surface(conn, project_root=project_tree)
    f.unlink()
    out = surface(conn, project_root=project_tree)
    flagged = [x for x in out["flagged_missing"] if x["id"] == "task.example~12345678"]
    assert flagged
    row = conn.execute(
        "SELECT missing_since FROM scry__doc WHERE id = 'task.example~12345678'"
    ).fetchone()
    assert row["missing_since"] is not None


def test_surface_force_deletes_missing(conn, project_tree):
    f = project_tree / "agent" / "tasks" / "ex.md"
    _write(f, DOC_BLOCK)
    surface(conn, project_root=project_tree)
    f.unlink()
    surface(conn, project_root=project_tree)
    out = surface(conn, project_root=project_tree, force=True)
    assert any(d.get("id") == "task.example~12345678" for d in out["force_deleted"])
    row = conn.execute(
        "SELECT id FROM scry__doc WHERE id = 'task.example~12345678'"
    ).fetchone()
    assert row is None


def test_handle_file_deletion_soft_deletes_doc_hard_deletes_impl(conn):
    rel = "src/foo.py"
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status, current_path) VALUES ('task.x~aaaaaaaa','task','active',?)",
        (rel,),
    )
    conn.execute(
        "INSERT INTO scry__impl(id, ref, file_path) VALUES ('imp~bbbbbbbb','spec.x~yz#FR1',?)",
        (rel,),
    )
    conn.commit()
    handle_file_deletion(conn, rel)
    doc = conn.execute("SELECT missing_since FROM scry__doc WHERE id='task.x~aaaaaaaa'").fetchone()
    assert doc is not None and doc["missing_since"] is not None
    impl = conn.execute("SELECT id FROM scry__impl WHERE id='imp~bbbbbbbb'").fetchone()
    assert impl is None


def test_reindex_skips_binary(conn, project_tree):
    f = project_tree / "blob.bin"
    f.write_bytes(b"abc\x00@scry.doc id: task.x~88888888 @scry.doc.end")
    parsed = reindex_file(conn, f, project_tree)
    assert len(parsed.docs) == 0


def test_ephemeral_set_for_scratch_files(conn, project_tree):
    f = project_tree / "agent" / "tasks" / "spike.scratch.md"
    _write(f, DOC_BLOCK)
    surface(conn, project_root=project_tree)
    row = conn.execute(
        "SELECT ephemeral FROM scry__doc WHERE id='task.example~12345678'"
    ).fetchone()
    assert row["ephemeral"] == 1


def test_excluded_dirs_skipped(conn, project_tree):
    git_file = project_tree / ".git" / "evil.md"
    _write(git_file, DOC_BLOCK)
    surface(conn, project_root=project_tree)
    row = conn.execute(
        "SELECT id FROM scry__doc WHERE id='task.example~12345678'"
    ).fetchone()
    assert row is None


def test_fts_auto_syncs_after_index(conn, project_tree):
    _write(project_tree / "agent" / "tasks" / "ex.md", DOC_BLOCK)
    surface(conn, project_root=project_tree)
    rows = conn.execute(
        "SELECT id FROM scry__doc_fts WHERE scry__doc_fts MATCH 'example'"
    ).fetchall()
    assert any(r["id"] == "task.example~12345678" for r in rows)
