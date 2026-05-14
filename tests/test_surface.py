"""scry_surface tests (FR20-FR22, optional-fields)."""
from __future__ import annotations

from pathlib import Path

from scry.service.surface import handle_file_deletion, reindex_file, surface


DOC_BLOCK = """\
<!-- @scry.entry
id: task.example~12345678
kind: task
summary: example
status: active
weight: 0.5
@scry.entry.end -->
"""

BIND_LINE = "# @scry.bind impl-x~aabbccdd spec.x~yz#FR1\n"


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


def test_handle_file_deletion_soft_deletes_doc_hard_deletes_bind(conn):
    rel = "src/foo.py"
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status, current_path) VALUES ('task.x~aaaaaaaa','task','active',?)",
        (rel,),
    )
    conn.execute(
        "INSERT INTO scry__bind(local_id, ref, file_path) VALUES ('impl~bbbbbbbb','spec.x~yz#FR1',?)",
        (rel,),
    )
    conn.commit()
    handle_file_deletion(conn, rel)
    doc = conn.execute("SELECT missing_since FROM scry__doc WHERE id='task.x~aaaaaaaa'").fetchone()
    assert doc is not None and doc["missing_since"] is not None
    bind = conn.execute(
        "SELECT local_id FROM scry__bind WHERE local_id='impl~bbbbbbbb' AND file_path=?",
        (rel,),
    ).fetchone()
    assert bind is None


def test_reindex_skips_binary(conn, project_tree):
    f = project_tree / "blob.bin"
    f.write_bytes(b"abc\x00@scry.entry id: task.x~88888888 @scry.entry.end")
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


def test_surface_indexes_bind_markers(conn, project_tree):
    """Bind markers are indexed via surface."""
    content = DOC_BLOCK + BIND_LINE
    _write(project_tree / "agent" / "tasks" / "ex.md", content)
    surface(conn, project_root=project_tree)
    rows = conn.execute(
        "SELECT local_id, ref FROM scry__bind WHERE local_id = 'impl-x~aabbccdd'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["ref"] == "spec.x~yz#FR1"


def test_bind_fts_searchable(conn, project_tree):
    """Bind comments are searchable via FTS (FR2 requirement)."""
    content = "# @scry.bind impl-y~bbccddee spec.y~ab#FR2 OAuth integration pending\n"
    _write(project_tree / "agent" / "tasks" / "ex.md", content)
    surface(conn, project_root=project_tree)
    rows = conn.execute(
        "SELECT local_id FROM scry__bind_fts WHERE scry__bind_fts MATCH 'OAuth'"
    ).fetchall()
    assert len(rows) >= 1


# ---------------------------------------------------------------------------
# Optional fields: implements, supersedes, depends_on
# ---------------------------------------------------------------------------

DOC_WITH_OPTIONALS = """\
<!-- @scry.entry
id: design.foo~aaaaaaaa
kind: design
summary: foo design
status: active
weight: 0.8
rationale: ""
applies: ""
seeded_questions: []
tags: []
implements: spec.foo~bbbbbbbb
supersedes: design.old~cccccccc
depends_on:
  - design.dep1~dddddddd
  - design.dep2~eeeeeeee
@scry.entry.end -->
"""

DOC_DEP1 = """\
<!-- @scry.entry
id: design.dep1~dddddddd
kind: design
summary: dep1
status: active
weight: 0.5
@scry.entry.end -->
"""


def test_implements_supersedes_stored(conn, project_tree):
    """implements and supersedes are stored in scry__doc."""
    _write(project_tree / "agent" / "design" / "foo.md", DOC_WITH_OPTIONALS)
    surface(conn, project_root=project_tree)
    row = conn.execute(
        "SELECT implements, supersedes FROM scry__doc WHERE id = 'design.foo~aaaaaaaa'"
    ).fetchone()
    assert row is not None
    assert row["implements"] == "spec.foo~bbbbbbbb"
    assert row["supersedes"] == "design.old~cccccccc"


def test_depends_on_populates_doc_relationship(conn, project_tree):
    """depends_on fields are auto-indexed into doc_relationship on surface."""
    _write(project_tree / "agent" / "design" / "foo.md", DOC_WITH_OPTIONALS)
    surface(conn, project_root=project_tree)
    rows = conn.execute(
        "SELECT from_id, to_id, relationship FROM doc_relationship WHERE from_id = 'design.foo~aaaaaaaa'"
    ).fetchall()
    to_ids = {r["to_id"] for r in rows}
    assert "design.dep1~dddddddd" in to_ids
    assert "design.dep2~eeeeeeee" in to_ids
    assert all(r["relationship"] == "depends_on" for r in rows)


def test_depends_on_cleared_on_update(conn, project_tree):
    """Removing a depends_on entry clears its doc_relationship row on re-index."""
    f = project_tree / "agent" / "design" / "foo.md"
    _write(f, DOC_WITH_OPTIONALS)
    surface(conn, project_root=project_tree)
    # Rewrite without dep2
    updated = DOC_WITH_OPTIONALS.replace("  - design.dep2~eeeeeeee\n", "")
    _write(f, updated)
    surface(conn, project_root=project_tree)
    rows = conn.execute(
        "SELECT to_id FROM doc_relationship WHERE from_id = 'design.foo~aaaaaaaa'"
    ).fetchall()
    to_ids = {r["to_id"] for r in rows}
    assert "design.dep1~dddddddd" in to_ids
    assert "design.dep2~eeeeeeee" not in to_ids


def test_depends_on_cycle_produces_warning(conn, project_tree):
    """A depends_on cycle is recorded in scry__warning, not silently dropped."""
    # doc A depends_on doc B
    doc_a = """\
<!-- @scry.entry
id: design.a~11111111
kind: design
summary: a
status: active
weight: 0.5
depends_on:
  - design.b~22222222
@scry.entry.end -->
"""
    # doc B depends_on doc A (cycle)
    doc_b = """\
<!-- @scry.entry
id: design.b~22222222
kind: design
summary: b
status: active
weight: 0.5
depends_on:
  - design.a~11111111
@scry.entry.end -->
"""
    _write(project_tree / "agent" / "design" / "a.md", doc_a)
    _write(project_tree / "agent" / "design" / "b.md", doc_b)
    surface(conn, project_root=project_tree)
    warnings = conn.execute(
        "SELECT message FROM scry__warning WHERE kind = 'depends_on_cycle'"
    ).fetchall()
    # At least one cycle warning should appear (for whichever edge is inserted second).
    assert len(warnings) >= 1


def test_depends_on_cleared_on_file_deletion(conn, project_tree):
    """doc_relationship rows are cleaned up when the source file is deleted."""
    _write(project_tree / "agent" / "design" / "foo.md", DOC_WITH_OPTIONALS)
    surface(conn, project_root=project_tree)
    handle_file_deletion(conn, "agent/design/foo.md")
    rows = conn.execute(
        "SELECT to_id FROM doc_relationship WHERE from_id = 'design.foo~aaaaaaaa'"
    ).fetchall()
    assert len(rows) == 0


def test_self_loop_depends_on_produces_warning(conn, project_tree):
    """A self-referential depends_on is recorded as a warning."""
    doc_self = """\
<!-- @scry.entry
id: design.self~33333333
kind: design
summary: self
status: active
weight: 0.5
depends_on:
  - design.self~33333333
@scry.entry.end -->
"""
    _write(project_tree / "agent" / "design" / "self.md", doc_self)
    surface(conn, project_root=project_tree)
    warnings = conn.execute(
        "SELECT message FROM scry__warning WHERE kind = 'depends_on_cycle' AND marker_id = 'design.self~33333333'"
    ).fetchall()
    assert len(warnings) == 1
    assert "self-loop" in warnings[0]["message"]


def test_cycle_warning_cleared_when_cycle_fixed(conn, project_tree):
    """Fixing a depends_on cycle removes the stale warning on re-index."""
    doc_self = """\
<!-- @scry.entry
id: design.self~44444444
kind: design
summary: self-loop
status: active
weight: 0.5
depends_on:
  - design.self~44444444
@scry.entry.end -->
"""
    fixed_doc = """\
<!-- @scry.entry
id: design.self~44444444
kind: design
summary: self-loop fixed
status: active
weight: 0.5
@scry.entry.end -->
"""
    path = project_tree / "agent" / "design" / "cyclic.md"
    _write(path, doc_self)
    surface(conn, project_root=project_tree)
    # Warning should be present after first index.
    before = conn.execute(
        "SELECT id FROM scry__warning WHERE kind = 'depends_on_cycle' AND marker_id = 'design.self~44444444'"
    ).fetchall()
    assert len(before) == 1

    # Fix the cycle and re-index.
    _write(path, fixed_doc)
    surface(conn, project_root=project_tree)
    after = conn.execute(
        "SELECT id FROM scry__warning WHERE kind = 'depends_on_cycle' AND marker_id = 'design.self~44444444'"
    ).fetchall()
    assert len(after) == 0, "stale cycle warning should be cleared after fix"
