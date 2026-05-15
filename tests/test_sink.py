"""scry_sink tests — service layer and MCP tool (elicitation gating)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scry.service.sink import SINK_TABLES, get_counts, sink
from scry.service.surface import surface


class _WrappedConn:
    """Thin test-only wrapper around sqlite3.Connection.

    - no-op close() so the fixture connection isn't closed mid-test
    - optional fail_on_delete_n: raise on the N-th DELETE to test atomicity
    """

    def __init__(self, inner: sqlite3.Connection, fail_on_delete_n: int | None = None):
        self._inner = inner
        self._fail_on = fail_on_delete_n
        self._delete_count = 0

    def execute(self, sql: str, *args, **kwargs):
        if self._fail_on and sql.strip().upper().startswith("DELETE"):
            self._delete_count += 1
            if self._delete_count == self._fail_on:
                raise sqlite3.OperationalError("simulated mid-sink failure")
        return self._inner.execute(sql, *args, **kwargs)

    def commit(self):
        return self._inner.commit()

    def rollback(self):
        return self._inner.rollback()

    def close(self):
        pass  # no-op: let the test fixture handle cleanup

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DOC_BLOCK = """\
<!-- @scry.entry
id: task.sink-test~aabbccdd
kind: task
summary: sink test doc
status: active
weight: 0.5
@scry.entry.end -->
"""


def _populate(conn: sqlite3.Connection) -> None:
    """Insert one row into each sink-affected table."""
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status, current_path) VALUES ('task.sink-test~aabbccdd','task','active','agent/tasks/sink.md')"
    )
    conn.execute(
        "INSERT INTO scry__doc_tag(doc_id, tag) VALUES ('task.sink-test~aabbccdd','topic:test')"
    )
    conn.execute(
        "INSERT INTO scry__doc_seeded_question(doc_id, ordinal, question) VALUES ('task.sink-test~aabbccdd',0,'What does this test?')"
    )
    conn.execute(
        "INSERT INTO scry__rel(from_id, to_id, predicate, fragment) "
        "VALUES ('task.sink-test~aabbccdd','task.other~eeeeeeee','depends_on','')"
    )
    conn.execute(
        "INSERT INTO scry__bind(source_doc_id, source_local_id, target_id, target_fragment) "
        "VALUES ('task.sink-test~aabbccdd', 'impl~11223344', 'spec.x~yz', '#FR1')"
    )
    conn.execute(
        "INSERT INTO scry__anchor(id, doc_id) VALUES ('test-anchor~11223344','task.sink-test~aabbccdd')"
    )
    conn.execute(
        "INSERT INTO scry__anchor_seeded_question(anchor_id, ordinal, question) VALUES ('test-anchor~11223344',0,'Where is this?')"
    )
    conn.execute(
        "INSERT INTO scry__warning(kind, marker_kind, marker_id, file_path, message) "
        "VALUES ('misplaced_doc','doc','task.sink-test~aabbccdd','agent/tasks/sink.md','test warning')"
    )
    conn.execute(
        "INSERT INTO scry__file(path, doc_id, body) "
        "VALUES ('agent/tasks/sink.md','task.sink-test~aabbccdd','body content')"
    )
    conn.commit()


def _all_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return get_counts(conn)


# ---------------------------------------------------------------------------
# Test 1: sink truncates all tables
# ---------------------------------------------------------------------------

def test_sink_truncates_all_tables(conn):
    _populate(conn)
    # Verify populated
    for table in SINK_TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count >= 1, f"expected at least 1 row in {table} before sink"

    result = sink(conn)

    # All tables should be empty
    for table in SINK_TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count == 0, f"expected 0 rows in {table} after sink, got {count}"

    # Result should carry pre-deletion counts
    assert result["cleared"]["scry__doc"] >= 1
    assert result["cleared"]["scry__anchor"] >= 1
    assert result["cleared"]["scry__bind"] >= 1
    assert result["cleared"]["scry__rel"] >= 1
    assert result["cleared"]["scry__warning"] >= 1


# ---------------------------------------------------------------------------
# Test 2: sink preserves schema
# ---------------------------------------------------------------------------

def test_sink_preserves_schema(conn):
    _populate(conn)
    sink(conn)

    # All sink tables still exist
    for table in SINK_TABLES:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        assert row is not None, f"table {table} should still exist after sink"

    # FTS virtual tables still exist
    for fts_table in ("scry__doc_fts", "scry__anchor_fts", "scry__bind_fts",
                       "scry__doc_tag_fts", "scry__doc_seeded_question_fts",
                       "scry__file_fts"):
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (fts_table,)
        ).fetchone()
        assert row is not None, f"FTS table {fts_table} should still exist after sink"


# ---------------------------------------------------------------------------
# Test 3: sink is atomic
# ---------------------------------------------------------------------------

def test_sink_atomic(conn):
    _populate(conn)
    counts_before = _all_counts(conn)

    failing = _WrappedConn(conn, fail_on_delete_n=3)

    with pytest.raises(sqlite3.OperationalError, match="simulated mid-sink failure"):
        sink(failing)

    counts_after = _all_counts(conn)
    for table in SINK_TABLES:
        assert counts_after[table] == counts_before[table], \
            f"expected {table} to be unchanged after aborted sink"


# ---------------------------------------------------------------------------
# Test 4: then_surface re-populates DB from disk
# ---------------------------------------------------------------------------

def test_sink_then_surface(conn, project_tree):
    """sink(conn, then_surface=True) clears the DB then re-indexes from disk markers."""
    f = project_tree / "agent" / "tasks" / "sink-test.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(DOC_BLOCK, encoding="utf-8")

    surface(conn, project_root=project_tree)
    assert conn.execute("SELECT COUNT(*) FROM scry__doc").fetchone()[0] >= 1

    result = sink(conn, then_surface=True, project_root=project_tree)

    assert "surface" in result, "then_surface=True should include surface results"
    assert result["surface"]["markers_indexed"] >= 1

    row = conn.execute(
        "SELECT id FROM scry__doc WHERE id = 'task.sink-test~aabbccdd'"
    ).fetchone()
    assert row is not None, "DB should be re-populated from disk after sink(then_surface=True)"


# ---------------------------------------------------------------------------
# Test 5: scry_sink tool fails closed when elicitation not accepted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sink_requires_elicitation(conn):
    """scry_sink does not delete data when elicitation returns declined/cancelled."""
    import json

    from mcp.server.elicitation import DeclinedElicitation
    from scry.tools.scry_sink import scry_sink

    _populate(conn)
    counts_before = _all_counts(conn)

    mock_ctx = MagicMock()
    mock_ctx.elicit = AsyncMock(return_value=DeclinedElicitation())

    wrapped = _WrappedConn(conn)

    with patch("scry.tools.scry_sink.get_db", return_value=wrapped):
        result_str = await scry_sink(ctx=mock_ctx, then_surface=False)

    result = json.loads(result_str)
    assert result["status"] == "cancelled", f"expected cancelled, got {result}"

    counts_after = _all_counts(conn)
    for table in SINK_TABLES:
        assert counts_after[table] == counts_before[table], \
            f"{table}: expected {counts_before[table]} rows (unchanged), got {counts_after[table]}"
