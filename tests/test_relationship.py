"""doc_relationship cycle detection (FR28)."""
from __future__ import annotations

from scry.service.relationship import add_relationship


def test_relationship_inserts(conn):
    out = add_relationship(conn, "a", "b")
    assert out.get("ok") is True


def test_relationship_rejects_self_loop(conn):
    out = add_relationship(conn, "a", "a")
    assert "error" in out


def test_relationship_rejects_cycle(conn):
    add_relationship(conn, "a", "b")
    add_relationship(conn, "b", "c")
    out = add_relationship(conn, "c", "a")
    assert "error" in out
    row = conn.execute(
        "SELECT 1 FROM doc_relationship WHERE from_id='c' AND to_id='a'"
    ).fetchone()
    assert row is None


def test_relationship_rejects_unknown_type(conn):
    out = add_relationship(conn, "a", "b", relationship="cousin_of")
    assert "error" in out
