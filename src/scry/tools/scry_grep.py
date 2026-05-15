"""scry_grep MCP tool — full-text search over indexed file bodies."""
from __future__ import annotations

from scry.config import get_db
from scry.service.grep import grep
from scry.tools._common import serialize


async def scry_grep(
    query: str,
    kind: str | None = None,
    status: str | None = None,
    path_glob: str | None = None,
    limit: int = 20,
) -> str:
    """Full-text search over all indexed file bodies (scry__file_fts).

    Complements scry_sql: use this when you want broad full-text search
    across file content, not just curated marker fields.

    Returns one hit per file (highest BM25-ranked match).

    Args:
        query:     FTS5 query string — plain words, phrases ("foo bar"),
                   boolean (foo AND bar, foo OR bar, NOT foo). Accepts
                   standard FTS5 syntax.
        kind:      Optional: filter to files whose associated doc has this
                   kind (e.g. 'design', 'lesson', 'pattern'). Files without
                   a doc marker are excluded when this filter is set.
        status:    Optional: filter by doc status (e.g. 'active', 'draft').
                   Files without a doc marker are excluded when set.
        path_glob: Optional: GLOB pattern on file path, e.g.
                   'agent/design/*' or '*.py'. Applied before FTS.
        limit:     Max number of results to return (default 20).

    Returns JSON:
      {
        "hits": [
          {
            "path": "agent/design/...",
            "doc_id": "design.foo~abcd1234" | null,
            "snippet": "...text with <mark>matches</mark> highlighted...",
            "score": 12.4,
            "match_count": 3
          }
        ],
        "total_matches": 47,
        "query": "...",
        "filters_applied": { "kind": null, "status": null, "path_glob": null }
      }

    Tips:
      - Combine with scry_sql: get doc IDs from scry_grep, then JOIN to
        scry__doc_tag or scry__doc for richer metadata.
      - Use path_glob to scope to a subtree: 'agent/design/*'
      - scry__file is populated during scry_surface; call that first if
        results are empty on a fresh DB.
    """
    conn = get_db()
    try:
        return serialize(grep(conn, query, kind=kind, status=status, path_glob=path_glob, limit=limit))
    finally:
        conn.close()
