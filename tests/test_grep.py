"""Tests for scry_grep / scry__file indexing."""
from __future__ import annotations

from pathlib import Path

import pytest

from scry.service.grep import grep
from scry.service.surface import (
    handle_file_deletion,
    reindex_file,
    surface,
    upsert_file,
    _should_index_body,
)


DOC_BLOCK = """\
<!-- @scry.entry
id: design.grep-test~aabbccdd
kind: design
summary: grep test document
status: active
weight: 0.7
@scry.entry.end -->

This document discusses the concept of autopoiesis in biological systems.
Maturana and Varela first described autopoietic organization in 1972.
"""

PLAIN_FILE = "This file has no marker. It mentions autopoiesis and cognitive science.\n"


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# scry__file body exclusion heuristics
# ---------------------------------------------------------------------------

def test_exclusion_extension(tmp_path):
    p = tmp_path / "data.jsonl"
    assert _should_index_body(p, "data.jsonl", "content") is False


def test_exclusion_png(tmp_path):
    p = tmp_path / "icon.png"
    assert _should_index_body(p, "icon.png", "content") is False


def test_exclusion_license_filename(tmp_path):
    p = tmp_path / "LICENSE"
    assert _should_index_body(p, "LICENSE", "copyright foo") is False


def test_exclusion_license_ext(tmp_path):
    p = tmp_path / "LICENSE.txt"
    assert _should_index_body(p, "LICENSE.txt", "copyright foo") is False


def test_exclusion_node_modules(tmp_path):
    p = tmp_path / "node_modules" / "foo.js"
    assert _should_index_body(p, "node_modules/foo.js", "content") is False


def test_exclusion_size_cap(tmp_path):
    p = tmp_path / "big.txt"
    # Body just over 1 MB
    body = "x" * (1024 * 1024 + 1)
    assert _should_index_body(p, "big.txt", body) is False


def test_exclusion_long_line(tmp_path):
    p = tmp_path / "minified.js"
    body = "a" * 10_001 + "\n"
    assert _should_index_body(p, "minified.js", body) is False


def test_included_python_file(tmp_path):
    p = tmp_path / "agent" / "design" / "foo.py"
    body = "def hello(): pass\n"
    assert _should_index_body(p, "agent/design/foo.py", body) is True


def test_included_markdown(tmp_path):
    p = tmp_path / "agent" / "design" / "design.foo~abcd.md"
    body = "# title\ncontent here\n"
    assert _should_index_body(p, "agent/design/design.foo~abcd.md", body) is True


# ---------------------------------------------------------------------------
# upsert_file / scry__file indexing
# ---------------------------------------------------------------------------

def test_upsert_file_indexes_body(conn, project_tree):
    f = project_tree / "agent" / "design" / "test.md"
    _write(f, DOC_BLOCK)
    reindex_file(conn, f, project_tree)

    row = conn.execute(
        "SELECT path, body FROM scry__file WHERE path = 'agent/design/test.md'"
    ).fetchone()
    assert row is not None
    assert "autopoiesis" in row["body"]


def test_upsert_file_links_doc_id(conn, project_tree):
    f = project_tree / "agent" / "design" / "test.md"
    _write(f, DOC_BLOCK)
    reindex_file(conn, f, project_tree)

    row = conn.execute(
        "SELECT doc_id FROM scry__file WHERE path = 'agent/design/test.md'"
    ).fetchone()
    assert row is not None
    assert row["doc_id"] == "design.grep-test~aabbccdd"


def test_upsert_file_null_doc_id_for_unmarked(conn, project_tree):
    f = project_tree / "agent" / "tasks" / "plain.md"
    _write(f, PLAIN_FILE)
    reindex_file(conn, f, project_tree)

    row = conn.execute(
        "SELECT doc_id FROM scry__file WHERE path = 'agent/tasks/plain.md'"
    ).fetchone()
    assert row is not None
    assert row["doc_id"] is None


def test_upsert_file_excluded_extension_not_indexed(conn, project_tree):
    f = project_tree / "agent" / "data.jsonl"
    _write(f, '{"id":"x"}\n')
    reindex_file(conn, f, project_tree)

    row = conn.execute("SELECT path FROM scry__file WHERE path = 'agent/data.jsonl'").fetchone()
    assert row is None


def test_file_body_dedup_no_rewrite_on_same_content(conn, project_tree):
    f = project_tree / "agent" / "design" / "test.md"
    _write(f, DOC_BLOCK)
    reindex_file(conn, f, project_tree)

    before = conn.execute(
        "SELECT last_modified FROM scry__file WHERE path = 'agent/design/test.md'"
    ).fetchone()["last_modified"]

    # Re-index without changing content — should not update last_modified.
    reindex_file(conn, f, project_tree)
    after = conn.execute(
        "SELECT last_modified FROM scry__file WHERE path = 'agent/design/test.md'"
    ).fetchone()["last_modified"]

    assert before == after


def test_handle_file_deletion_removes_file_row(conn, project_tree):
    f = project_tree / "agent" / "design" / "test.md"
    _write(f, DOC_BLOCK)
    reindex_file(conn, f, project_tree)

    # Confirm it's indexed.
    assert conn.execute("SELECT path FROM scry__file WHERE path='agent/design/test.md'").fetchone()

    handle_file_deletion(conn, "agent/design/test.md")

    assert conn.execute("SELECT path FROM scry__file WHERE path='agent/design/test.md'").fetchone() is None


def test_surface_indexes_file_bodies(conn, project_tree):
    f = project_tree / "agent" / "design" / "test.md"
    _write(f, DOC_BLOCK)
    surface(conn, project_root=project_tree)

    row = conn.execute("SELECT path FROM scry__file WHERE path='agent/design/test.md'").fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# scry__file_fts search via grep service
# ---------------------------------------------------------------------------

def test_grep_basic_match(conn, project_tree):
    f = project_tree / "agent" / "design" / "test.md"
    _write(f, DOC_BLOCK)
    reindex_file(conn, f, project_tree)

    result = grep(conn, "autopoiesis")
    assert result["total_matches"] >= 1
    paths = [h["path"] for h in result["hits"]]
    assert "agent/design/test.md" in paths


def test_grep_no_match_returns_empty(conn, project_tree):
    f = project_tree / "agent" / "design" / "test.md"
    _write(f, DOC_BLOCK)
    reindex_file(conn, f, project_tree)

    result = grep(conn, "xyzzy_nonexistent_token_qqqq")
    assert result["total_matches"] == 0
    assert result["hits"] == []


def test_grep_snippet_has_mark_tags(conn, project_tree):
    f = project_tree / "agent" / "design" / "test.md"
    _write(f, DOC_BLOCK)
    reindex_file(conn, f, project_tree)

    result = grep(conn, "Maturana")
    hits = [h for h in result["hits"] if h["path"] == "agent/design/test.md"]
    assert hits
    assert "<mark>" in hits[0]["snippet"]


def test_grep_one_hit_per_file(conn, project_tree):
    f = project_tree / "agent" / "design" / "test.md"
    # Body has "autopoiesis" twice — still one hit per file (path is PK)
    body = "autopoiesis first mention. autopoiesis second mention.\n"
    _write(f, body)
    reindex_file(conn, f, project_tree)

    result = grep(conn, "autopoiesis")
    hits = [h for h in result["hits"] if h["path"] == "agent/design/test.md"]
    assert len(hits) == 1


def test_grep_path_glob_filter(conn, project_tree):
    f1 = project_tree / "agent" / "design" / "foo.md"
    f2 = project_tree / "agent" / "tasks" / "bar.md"
    _write(f1, "The word autopoiesis appears here.\n")
    _write(f2, "The word autopoiesis appears here too.\n")
    reindex_file(conn, f1, project_tree)
    reindex_file(conn, f2, project_tree)

    result = grep(conn, "autopoiesis", path_glob="agent/design/*")
    paths = [h["path"] for h in result["hits"]]
    assert "agent/design/foo.md" in paths
    assert "agent/tasks/bar.md" not in paths


def test_grep_kind_filter_excludes_unmatched(conn, project_tree):
    marked = project_tree / "agent" / "design" / "foo.md"
    unmarked = project_tree / "agent" / "tasks" / "bar.md"
    _write(marked, DOC_BLOCK)  # kind=design
    _write(unmarked, PLAIN_FILE)  # no doc marker
    reindex_file(conn, marked, project_tree)
    reindex_file(conn, unmarked, project_tree)

    result = grep(conn, "autopoiesis", kind="design")
    paths = [h["path"] for h in result["hits"]]
    # Unmarked file has no doc, excluded by kind filter
    assert "agent/tasks/plain.md" not in paths
    assert "agent/design/foo.md" in paths


def test_grep_empty_query_returns_empty(conn, project_tree):
    result = grep(conn, "")
    assert result["hits"] == []
    assert result["total_matches"] == 0


def test_grep_limit(conn, project_tree):
    for i in range(5):
        f = project_tree / "agent" / f"file{i}.md"
        _write(f, f"The keyword autopoiesis in file {i}.\n")
        reindex_file(conn, f, project_tree)

    result = grep(conn, "autopoiesis", limit=2)
    assert len(result["hits"]) <= 2
    assert result["total_matches"] >= 2


def test_sink_clears_scry_file(conn, project_tree):
    from scry.service.sink import sink

    f = project_tree / "agent" / "design" / "test.md"
    _write(f, DOC_BLOCK)
    surface(conn, project_root=project_tree)
    assert conn.execute("SELECT COUNT(*) FROM scry__file").fetchone()[0] >= 1

    sink(conn)
    assert conn.execute("SELECT COUNT(*) FROM scry__file").fetchone()[0] == 0
