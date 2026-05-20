"""scry_surface tests (FR20-FR22, optional-fields, schema-rewrite)."""
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
    rel = "agent/foo.py"
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status, current_path) VALUES ('task.x~aaaaaaaa','task','active',?)",
        (rel,),
    )
    conn.execute(
        """INSERT INTO scry__bind(source_doc_id, source_local_id, target_id, target_fragment)
           VALUES ('task.x~aaaaaaaa', 'impl~bbbbbbbb', 'spec.x~yz', '#FR1')""",
    )
    conn.commit()
    handle_file_deletion(conn, rel)
    doc = conn.execute("SELECT missing_since FROM scry__doc WHERE id='task.x~aaaaaaaa'").fetchone()
    assert doc is not None and doc["missing_since"] is not None
    bind = conn.execute(
        "SELECT source_local_id FROM scry__bind WHERE source_local_id='impl~bbbbbbbb'"
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
        "SELECT source_local_id, target_id, target_fragment FROM scry__bind "
        "WHERE source_local_id = 'impl-x~aabbccdd'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["target_id"] == "spec.x~yz"
    assert rows[0]["target_fragment"] == "#FR1"


def test_bind_fts_searchable(conn, project_tree):
    """Bind comments are searchable via FTS (FR2 requirement)."""
    content = DOC_BLOCK + "# @scry.bind impl-y~bbccddee spec.y~ab#FR2 OAuth integration pending\n"
    _write(project_tree / "agent" / "tasks" / "ex.md", content)
    surface(conn, project_root=project_tree)
    rows = conn.execute(
        "SELECT source_local_id FROM scry__bind_fts WHERE scry__bind_fts MATCH 'OAuth'"
    ).fetchall()
    assert len(rows) >= 1


# ---------------------------------------------------------------------------
# Tags and seeded_questions as join tables
# ---------------------------------------------------------------------------

DOC_WITH_TAGS = """\
<!-- @scry.entry
id: design.tagged~aaaaaaaa
kind: design
summary: tagged design
status: active
weight: 0.8
tags: ["scope:identity", "topic:memory"]
seeded_questions:
  - "Why does this exist?"
  - "How does memory work?"
@scry.entry.end -->
"""


def test_tags_stored_in_join_table(conn, project_tree):
    """tags are stored as rows in scry__doc_tag, not as a column on scry__doc."""
    _write(project_tree / "agent" / "design" / "tagged.md", DOC_WITH_TAGS)
    surface(conn, project_root=project_tree)
    tags = {r["tag"] for r in conn.execute(
        "SELECT tag FROM scry__doc_tag WHERE doc_id = 'design.tagged~aaaaaaaa'"
    ).fetchall()}
    assert "scope:identity" in tags
    assert "topic:memory" in tags


def test_tags_fts_searchable(conn, project_tree):
    """Tags are searchable via scry__doc_tag_fts."""
    _write(project_tree / "agent" / "design" / "tagged.md", DOC_WITH_TAGS)
    surface(conn, project_root=project_tree)
    rows = conn.execute(
        "SELECT doc_id FROM scry__doc_tag_fts WHERE scry__doc_tag_fts MATCH 'identity'"
    ).fetchall()
    assert any(r["doc_id"] == "design.tagged~aaaaaaaa" for r in rows)


def test_seeded_questions_stored_in_join_table(conn, project_tree):
    """seeded_questions are stored as rows in scry__doc_seeded_question."""
    _write(project_tree / "agent" / "design" / "tagged.md", DOC_WITH_TAGS)
    surface(conn, project_root=project_tree)
    questions = [r["question"] for r in conn.execute(
        "SELECT question FROM scry__doc_seeded_question WHERE doc_id = 'design.tagged~aaaaaaaa' ORDER BY ordinal"
    ).fetchall()]
    assert "Why does this exist?" in questions
    assert "How does memory work?" in questions


def test_doc_lacks_tags_column(conn, project_tree):
    """scry__doc no longer has tags or seeded_questions columns."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(scry__doc)").fetchall()}
    assert "tags" not in cols
    assert "seeded_questions" not in cols
    assert "implements" not in cols
    assert "supersedes" not in cols


# ---------------------------------------------------------------------------
# Optional fields: implements, supersedes, depends_on → scry__rel
# ---------------------------------------------------------------------------

DOC_WITH_OPTIONALS = """\
<!-- @scry.entry
id: design.foo~aaaaaaaa
kind: design
summary: foo design
status: active
weight: 0.8
implements:
  - spec.foo~bbbbbbbb
supersedes:
  - design.old~cccccccc
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


def test_implements_supersedes_stored_in_rel(conn, project_tree):
    """implements and supersedes are stored in scry__rel, not in scry__doc columns."""
    _write(project_tree / "agent" / "design" / "foo.md", DOC_WITH_OPTIONALS)
    surface(conn, project_root=project_tree)

    implements = conn.execute(
        "SELECT to_id FROM scry__rel WHERE from_id = 'design.foo~aaaaaaaa' AND predicate = 'implements'"
    ).fetchone()
    assert implements is not None
    assert implements["to_id"] == "spec.foo~bbbbbbbb"

    supersedes = conn.execute(
        "SELECT to_id FROM scry__rel WHERE from_id = 'design.foo~aaaaaaaa' AND predicate = 'supersedes'"
    ).fetchone()
    assert supersedes is not None
    assert supersedes["to_id"] == "design.old~cccccccc"


def test_depends_on_populates_scry_rel(conn, project_tree):
    """depends_on fields are auto-indexed into scry__rel on surface."""
    _write(project_tree / "agent" / "design" / "foo.md", DOC_WITH_OPTIONALS)
    surface(conn, project_root=project_tree)
    rows = conn.execute(
        "SELECT from_id, to_id, predicate FROM scry__rel "
        "WHERE from_id = 'design.foo~aaaaaaaa' AND predicate = 'depends_on'"
    ).fetchall()
    to_ids = {r["to_id"] for r in rows}
    assert "design.dep1~dddddddd" in to_ids
    assert "design.dep2~eeeeeeee" in to_ids


def test_depends_on_cleared_on_update(conn, project_tree):
    """Removing a depends_on entry clears its scry__rel row on re-index."""
    f = project_tree / "agent" / "design" / "foo.md"
    _write(f, DOC_WITH_OPTIONALS)
    surface(conn, project_root=project_tree)
    updated = DOC_WITH_OPTIONALS.replace("  - design.dep2~eeeeeeee\n", "")
    _write(f, updated)
    surface(conn, project_root=project_tree)
    rows = conn.execute(
        "SELECT to_id FROM scry__rel WHERE from_id = 'design.foo~aaaaaaaa' AND predicate = 'depends_on'"
    ).fetchall()
    to_ids = {r["to_id"] for r in rows}
    assert "design.dep1~dddddddd" in to_ids
    assert "design.dep2~eeeeeeee" not in to_ids


def test_depends_on_cycle_produces_warning(conn, project_tree):
    """A depends_on cycle is recorded in scry__warning."""
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
    assert len(warnings) >= 1


def test_depends_on_cleared_on_file_deletion(conn, project_tree):
    """scry__rel rows are cleaned up when the source file is deleted."""
    _write(project_tree / "agent" / "design" / "foo.md", DOC_WITH_OPTIONALS)
    surface(conn, project_root=project_tree)
    handle_file_deletion(conn, "agent/design/foo.md")
    rows = conn.execute(
        "SELECT to_id FROM scry__rel WHERE from_id = 'design.foo~aaaaaaaa'"
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
    before = conn.execute(
        "SELECT id FROM scry__warning WHERE kind = 'depends_on_cycle' AND marker_id = 'design.self~44444444'"
    ).fetchall()
    assert len(before) == 1
    _write(path, fixed_doc)
    surface(conn, project_root=project_tree)
    after = conn.execute(
        "SELECT id FROM scry__warning WHERE kind = 'depends_on_cycle' AND marker_id = 'design.self~44444444'"
    ).fetchall()
    assert len(after) == 0, "stale cycle warning should be cleared after fix"


# ---------------------------------------------------------------------------
# scry__rel replaces doc_relationship — no doc_relationship table
# ---------------------------------------------------------------------------

def test_no_doc_relationship_table(conn):
    """doc_relationship table must not exist in the new schema."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='doc_relationship'"
    ).fetchone()
    assert row is None


# ---------------------------------------------------------------------------
# Code-construct exclusion (CR-1 / FR11.7 proxy tests)
# scry-mcp delegates parsing to scry-parse; these tests verify the behavior
# is preserved end-to-end through the surface/reindex pipeline.
# ---------------------------------------------------------------------------

FENCED_CODE_BLOCK_DOC = """\
<!-- @scry.entry
id: design.real~ffffffff
kind: design
summary: real marker
status: active
weight: 0.5
@scry.entry.end -->

Here is an example in a fenced code block that must NOT be indexed:

```markdown
<!-- @scry.entry
id: design.phantom~aaaaaaaa
kind: design
summary: phantom — must not be indexed
status: active
@scry.entry.end -->
```
"""

INLINE_CODE_DOC = """\
<!-- @scry.entry
id: design.inlinereal~bbbbbbbb
kind: design
summary: inline real marker
status: active
weight: 0.5
@scry.entry.end -->

The marker `<!-- @scry.entry id: design.inlinephantom~cccccccc ... @scry.entry.end -->` in inline code must NOT be indexed.
"""


def test_fenced_code_block_markers_not_indexed(conn, project_tree):
    """Markers inside fenced code blocks are silently ignored (CR-1)."""
    _write(project_tree / "agent" / "design" / "fenced.md", FENCED_CODE_BLOCK_DOC)
    surface(conn, project_root=project_tree)

    real = conn.execute(
        "SELECT id FROM scry__doc WHERE id = 'design.real~ffffffff'"
    ).fetchone()
    assert real is not None, "real marker outside code block must be indexed"

    phantom = conn.execute(
        "SELECT id FROM scry__doc WHERE id = 'design.phantom~aaaaaaaa'"
    ).fetchone()
    assert phantom is None, "phantom marker inside fenced code block must NOT be indexed"


def test_inline_code_markers_not_indexed(conn, project_tree):
    """Markers inside inline code spans are silently ignored (CR-1)."""
    _write(project_tree / "agent" / "design" / "inline.md", INLINE_CODE_DOC)
    surface(conn, project_root=project_tree)

    real = conn.execute(
        "SELECT id FROM scry__doc WHERE id = 'design.inlinereal~bbbbbbbb'"
    ).fetchone()
    assert real is not None, "real marker must be indexed"

    phantom = conn.execute(
        "SELECT id FROM scry__doc WHERE id = 'design.inlinephantom~cccccccc'"
    ).fetchone()
    assert phantom is None, "phantom marker inside inline code must NOT be indexed"


# ---------------------------------------------------------------------------
# Scoped path parameter tests (originator spec: 2026-05-15T09-27-46Z)
# ---------------------------------------------------------------------------

DOC_OUTSIDE = """\
<!-- @scry.entry
id: task.outside~aaaaaaaa
kind: task
summary: outside marker
status: active
weight: 0.5
@scry.entry.end -->
"""

DOC_INSIDE = """\
<!-- @scry.entry
id: task.inside~bbbbbbbb
kind: task
summary: inside marker
status: active
weight: 0.5
@scry.entry.end -->
"""


def test_surface_full_walk_unchanged(conn, project_tree):
    """path=None behaves exactly as before (full corpus walk)."""
    _write(project_tree / "agent" / "tasks" / "ex.md", DOC_BLOCK)
    out = surface(conn, project_root=project_tree, path=None)
    assert out["scope"] is None
    assert out["files_scanned"] >= 1
    rows = conn.execute("SELECT id FROM scry__doc WHERE id = 'task.example~12345678'").fetchall()
    assert len(rows) == 1


def test_surface_single_file(conn, project_tree):
    """path=<file> re-indexes exactly that one file; counts reflect one file."""
    _write(project_tree / "agent" / "tasks" / "inside.md", DOC_INSIDE)
    _write(project_tree / "agent" / "tasks" / "outside.md", DOC_OUTSIDE)
    # First, full surface to populate both.
    surface(conn, project_root=project_tree)
    # Now surface only the inside file.
    out = surface(conn, project_root=project_tree, path="agent/tasks/inside.md")
    assert out["scope"] == "agent/tasks/inside.md"
    assert out["files_scanned"] == 1
    # Both docs still present (scoped surface does not disturb outside doc).
    inside = conn.execute("SELECT id FROM scry__doc WHERE id = 'task.inside~bbbbbbbb'").fetchone()
    outside = conn.execute("SELECT id FROM scry__doc WHERE id = 'task.outside~aaaaaaaa'").fetchone()
    assert inside is not None
    assert outside is not None


def test_surface_directory_recursive(conn, project_tree):
    """path=<dir> re-indexes every file under that directory, recursively."""
    subtree = project_tree / "agent" / "subtree"
    subtree.mkdir(parents=True, exist_ok=True)
    _write(subtree / "a.md", DOC_INSIDE)
    _write(project_tree / "agent" / "tasks" / "b.md", DOC_OUTSIDE)
    out = surface(conn, project_root=project_tree, path="agent/subtree")
    assert out["scope"] == "agent/subtree"
    assert out["files_scanned"] >= 1
    inside = conn.execute("SELECT id FROM scry__doc WHERE id = 'task.inside~bbbbbbbb'").fetchone()
    assert inside is not None


def test_surface_scoped_missing(conn, project_tree):
    """A doc whose file is gone OUTSIDE the scope is NOT flagged_missing;
    one INSIDE the scope IS."""
    inside_path = project_tree / "agent" / "tasks" / "inside.md"
    outside_path = project_tree / "agent" / "tasks" / "outside.md"
    _write(inside_path, DOC_INSIDE)
    _write(outside_path, DOC_OUTSIDE)
    surface(conn, project_root=project_tree)
    # Delete both files.
    inside_path.unlink()
    outside_path.unlink()
    # Scope surface to the directory — both files are in scope.
    out = surface(conn, project_root=project_tree, path="agent/tasks")
    flagged_ids = {f["id"] for f in out["flagged_missing"]}
    assert "task.inside~bbbbbbbb" in flagged_ids
    assert "task.outside~aaaaaaaa" in flagged_ids

    # Now restore only the outside file, surface only a different path.
    _write(outside_path, DOC_OUTSIDE)
    _write(inside_path, DOC_INSIDE)
    surface(conn, project_root=project_tree)
    inside_path.unlink()
    # Surface a sibling directory (no files there) — inside is outside the scope.
    sibling = project_tree / "agent" / "other"
    sibling.mkdir(parents=True, exist_ok=True)
    out = surface(conn, project_root=project_tree, path="agent/other")
    flagged_ids = {f["id"] for f in out["flagged_missing"]}
    assert "task.inside~bbbbbbbb" not in flagged_ids, (
        "doc outside the scoped path must NOT be flagged missing"
    )


def test_surface_scoped_force(conn, project_tree):
    """force=True + path hard-deletes only within the scope."""
    # Put inside doc in its own subtree, outside in a sibling subtree.
    inside_dir = project_tree / "agent" / "inside-subtree"
    outside_dir = project_tree / "agent" / "outside-subtree"
    inside_path = inside_dir / "inside.md"
    outside_path = outside_dir / "outside.md"
    _write(inside_path, DOC_INSIDE)
    _write(outside_path, DOC_OUTSIDE)
    surface(conn, project_root=project_tree)
    # Delete the inside file so it becomes missing.
    inside_path.unlink()
    # Full surface to flag inside as missing (outside is still present).
    surface(conn, project_root=project_tree)
    missing_row = conn.execute(
        "SELECT missing_since FROM scry__doc WHERE id = 'task.inside~bbbbbbbb'"
    ).fetchone()
    assert missing_row is not None and missing_row["missing_since"] is not None
    # Force-delete scoped to the inside subtree only.
    # The directory still exists even though the file inside was deleted.
    out = surface(
        conn, project_root=project_tree,
        path="agent/inside-subtree", force=True,
    )
    deleted_ids = {d["id"] for d in out["force_deleted"]}
    assert "task.inside~bbbbbbbb" in deleted_ids
    # Outside doc must still exist (not in scope).
    outside_row = conn.execute(
        "SELECT id FROM scry__doc WHERE id = 'task.outside~aaaaaaaa'"
    ).fetchone()
    assert outside_row is not None


def test_surface_nonexistent_path(conn, project_tree):
    """A path that does not exist returns a clear error, not a silent no-op."""
    import pytest
    with pytest.raises(ValueError, match="does not exist"):
        surface(conn, project_root=project_tree, path="nonexistent/path/here.md")


# ---------------------------------------------------------------------------
# extras field (scry-spec FR4.B, v1.1.0) — added in scry-mcp v0.17.0
# ---------------------------------------------------------------------------

DOC_WITH_EXTRAS = """\
<!-- @scry.entry
id: task.with-extras~ccddccdd
kind: task
summary: a doc carrying extras
extras:
  cost_usd: 12.5
  tier: gold
  active: true
  retries: 3
  note: null
@scry.entry.end -->
"""


def test_surface_indexes_extras_as_json_text(conn, project_tree):
    """A marker with `extras` produces a JSON-text column populated round-trip."""
    import json as _json
    _write(project_tree / "agent" / "with_extras.md", DOC_WITH_EXTRAS)
    surface(conn, project_root=project_tree)
    row = conn.execute(
        "SELECT extras FROM scry__doc WHERE id = 'task.with-extras~ccddccdd'"
    ).fetchone()
    assert row is not None
    payload = _json.loads(row["extras"])
    assert payload == {
        "cost_usd": 12.5,
        "tier": "gold",
        "active": True,
        "retries": 3,
        "note": None,
    }


def test_surface_extras_absent_leaves_column_null(conn, project_tree):
    """A marker without `extras` stores NULL — column stays sparse."""
    _write(project_tree / "agent" / "tasks" / "ex.md", DOC_BLOCK)
    surface(conn, project_root=project_tree)
    row = conn.execute(
        "SELECT extras FROM scry__doc WHERE id = 'task.example~12345678'"
    ).fetchone()
    assert row is not None
    assert row["extras"] is None


def test_surface_extras_queryable_via_json1(conn, project_tree):
    """JSON1 `json_extract` works on the extras column — FR4.B SHOULD-level indexability."""
    _write(project_tree / "agent" / "with_extras.md", DOC_WITH_EXTRAS)
    surface(conn, project_root=project_tree)
    row = conn.execute(
        "SELECT json_extract(extras, '$.cost_usd') AS cost,"
        "       json_extract(extras, '$.tier')     AS tier,"
        "       json_extract(extras, '$.active')   AS active"
        " FROM scry__doc WHERE id = 'task.with-extras~ccddccdd'"
    ).fetchone()
    assert row["cost"] == 12.5
    assert row["tier"] == "gold"
    # SQLite stores JSON booleans as integers when extracted.
    assert row["active"] == 1
