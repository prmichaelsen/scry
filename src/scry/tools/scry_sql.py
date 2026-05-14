"""scry_sql MCP tool — read-only SQL gateway."""
from __future__ import annotations

from scry.config import get_db
from scry.service.query import run_query
from scry.tools._common import serialize


async def scry_sql(query: str) -> str:
    """Execute a read-only SQL query against the scry project database.
    Use this to discover project state, search docs, check coverage, inspect anchors.

    Supports SELECT and WITH (CTE) queries only. All mutator keywords
    (INSERT, UPDATE, DELETE, DROP, etc.) are blocked.

    Key tables:
      scry__doc        — knowledge graph entries (@scry.entry markers: designs, specs, tasks, lessons, etc.)
      scry__anchor     — named code location bookmarks with descriptions and seeded questions
      scry__impl       — implementation markers linking source code to requirement refs (DR/FR)
      scry__test       — test markers linking test files to test requirement refs (UT/ST/ET)
      doc_relationship — typed edges between docs (depends_on only)
      scry__warning    — lint-style warnings (e.g. misplaced_doc)
      scry__doc_fts    — full-text search over docs (summary, tags, rationale, applies, seeded_questions)
      scry__anchor_fts — full-text search over anchors (name, description, seeded_questions)
      migration        — applied schema migrations

    Returns JSON: {"results": [...], "row_count": N}
    """
    conn = get_db()
    try:
        return serialize(run_query(conn, query))
    finally:
        conn.close()
