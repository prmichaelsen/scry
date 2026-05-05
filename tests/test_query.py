"""scry_sql tests (FR15, FR16)."""
from __future__ import annotations

from scry.service.query import run_query, validate_query


def test_select_passes():
    assert validate_query("SELECT 1") is None
    assert validate_query("WITH x AS (SELECT 1) SELECT * FROM x") is None


def test_mutators_rejected():
    for q in (
        "DELETE FROM scry__doc",
        "INSERT INTO scry__doc VALUES (1)",
        "UPDATE scry__doc SET id=1",
        "DROP TABLE x",
        "CREATE TABLE x (id INT)",
        "PRAGMA foreign_keys=ON",
        "ALTER TABLE x ADD COLUMN y",
    ):
        assert validate_query(q) is not None, f"should reject: {q}"


def test_comments_dont_smuggle_mutators():
    # Inline comment containing DELETE — should still pass when the actual statement is SELECT.
    assert validate_query("SELECT 1 -- DELETE FROM x") is None
    # Block comment hiding a mutator with a SELECT prefix shouldn't open a DELETE.
    assert validate_query("SELECT /* DELETE FROM x */ 1") is None


def test_run_query_returns_results(conn):
    out = run_query(conn, "SELECT 1 AS x, 'hi' AS y")
    assert out["row_count"] == 1
    assert out["results"][0]["x"] == 1
    assert out["results"][0]["y"] == "hi"


def test_run_query_blocks_mutator(conn):
    out = run_query(conn, "DELETE FROM scry__doc")
    assert "error" in out


def test_empty_query_rejected():
    assert validate_query("") is not None
    assert validate_query("   ") is not None
