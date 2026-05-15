"""scry__rel cycle detection and relationship management (FR28)."""
from __future__ import annotations

from scry.service.relationship import add_relationship


def _insert_doc(conn, doc_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO scry__doc(id, kind, status) VALUES (?, 'design', 'active')",
        (doc_id,),
    )
    conn.commit()


def test_relationship_inserts(conn):
    _insert_doc(conn, "a")
    _insert_doc(conn, "b")
    out = add_relationship(conn, "a", "b")
    assert out.get("ok") is True
    row = conn.execute(
        "SELECT 1 FROM scry__rel WHERE from_id='a' AND to_id='b' AND predicate='depends_on'"
    ).fetchone()
    assert row is not None


def test_relationship_rejects_self_loop(conn):
    _insert_doc(conn, "a")
    out = add_relationship(conn, "a", "a")
    assert "error" in out


def test_relationship_rejects_cycle(conn):
    _insert_doc(conn, "a")
    _insert_doc(conn, "b")
    _insert_doc(conn, "c")
    add_relationship(conn, "a", "b")
    add_relationship(conn, "b", "c")
    out = add_relationship(conn, "c", "a")
    assert "error" in out
    row = conn.execute(
        "SELECT 1 FROM scry__rel WHERE from_id='c' AND to_id='a' AND predicate='depends_on'"
    ).fetchone()
    assert row is None


def test_relationship_rejects_unknown_type(conn):
    _insert_doc(conn, "a")
    _insert_doc(conn, "b")
    out = add_relationship(conn, "a", "b", relationship="cousin_of")
    assert "error" in out


def test_implements_no_cycle_check(conn):
    """implements does not undergo cycle detection."""
    _insert_doc(conn, "a")
    _insert_doc(conn, "b")
    add_relationship(conn, "a", "b", relationship="implements")
    # Adding b implements a should not be rejected (no cycle check for implements).
    out = add_relationship(conn, "b", "a", relationship="implements")
    assert out.get("ok") is True


def test_supersedes_stored(conn):
    """supersedes predicate is stored correctly."""
    _insert_doc(conn, "a")
    _insert_doc(conn, "b")
    out = add_relationship(conn, "a", "b", relationship="supersedes")
    assert out.get("ok") is True
    row = conn.execute(
        "SELECT 1 FROM scry__rel WHERE from_id='a' AND to_id='b' AND predicate='supersedes'"
    ).fetchone()
    assert row is not None
