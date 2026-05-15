"""scry_grep service — full-text search over indexed file bodies."""
from __future__ import annotations

import sqlite3
from typing import Any


def grep(
    conn: sqlite3.Connection,
    query: str,
    kind: str | None = None,
    status: str | None = None,
    path_glob: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Full-text search over scry__file_fts.

    Returns one hit per file (scry__file has path as PK, so FTS also has
    one row per file).  Filters by doc kind/status require the file to have
    an associated doc (null doc_id excluded when filters are applied).

    bm25() and snippet() require the FTS table to be the driving table in
    the FROM clause — do not join FROM scry__file.

    Args:
        query:     FTS5 query string (plain words, phrases, boolean operators).
        kind:      Optional doc kind filter (e.g. 'design', 'lesson').
        status:    Optional doc status filter (e.g. 'active', 'draft').
        path_glob: Optional GLOB pattern on path (e.g. 'agent/design/*').
        limit:     Max hits returned.

    Returns dict with keys: hits, total_matches, query, filters_applied.
    """
    if not query or not query.strip():
        return {
            "hits": [],
            "total_matches": 0,
            "query": query,
            "filters_applied": {"kind": kind, "status": status, "path_glob": path_glob},
        }

    # Extra WHERE clauses for the joined scry__file table.
    extra_where: list[str] = []
    extra_params: list[Any] = []

    if path_glob is not None:
        extra_where.append("f.path GLOB ?")
        extra_params.append(path_glob)

    # Doc-field filters: JOIN scry__doc and add conditions.
    doc_join = ""
    doc_where: list[str] = []
    doc_params: list[Any] = []

    if kind is not None or status is not None:
        doc_join = "LEFT JOIN scry__doc d ON d.id = f.doc_id"
        doc_where.append("f.doc_id IS NOT NULL")  # exclude unmarked files
        if kind is not None:
            doc_where.append("d.kind = ?")
            doc_params.append(kind)
        if status is not None:
            doc_where.append("d.status = ?")
            doc_params.append(status)

    all_extra = extra_where + doc_where
    all_extra_params = extra_params + doc_params

    extra_sql = (" AND " + " AND ".join(all_extra)) if all_extra else ""

    # snippet() column index: 0=path, 1=body
    hits_sql = f"""
        SELECT
            f.path,
            f.doc_id,
            bm25(scry__file_fts) AS score,
            snippet(scry__file_fts, 1, '<mark>', '</mark>', '...', 20) AS snippet_text
        FROM scry__file_fts
        JOIN scry__file f ON scry__file_fts.rowid = f.rowid
        {doc_join}
        WHERE scry__file_fts MATCH ?{extra_sql}
        ORDER BY score ASC
        LIMIT ?
    """
    hit_params: list[Any] = [query] + all_extra_params + [limit]

    try:
        rows = conn.execute(hits_sql, hit_params).fetchall()
    except Exception:
        rows = []

    hits = [
        {
            "path": r["path"],
            "doc_id": r["doc_id"],
            "snippet": r["snippet_text"],
            "score": abs(r["score"]) if r["score"] is not None else 0.0,
        }
        for r in rows
    ]

    # Total count (pre-limit).
    count_sql = f"""
        SELECT COUNT(*) AS n
        FROM scry__file_fts
        JOIN scry__file f ON scry__file_fts.rowid = f.rowid
        {doc_join}
        WHERE scry__file_fts MATCH ?{extra_sql}
    """
    count_params: list[Any] = [query] + all_extra_params
    try:
        total = conn.execute(count_sql, count_params).fetchone()["n"]
    except Exception:
        total = len(hits)

    return {
        "hits": hits,
        "total_matches": total,
        "query": query,
        "filters_applied": {"kind": kind, "status": status, "path_glob": path_glob},
    }
