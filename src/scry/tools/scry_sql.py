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
      scry__doc        — knowledge graph entries (@scry.entry markers)
                         columns: id, kind, status, weight, summary, rationale, applies,
                                  current_path, ephemeral, missing_since, content_hash,
                                  created_at, updated_at
      scry__doc_tag    — tags as a join table: doc_id, tag
      scry__doc_seeded_question — seeded questions: doc_id, ordinal, question
      scry__anchor     — named code location bookmarks: id, doc_id, description,
                         content_hash, created_at, updated_at
      scry__anchor_seeded_question — anchor seeded questions: anchor_id, ordinal, question
      scry__bind       — binding markers (@scry.bind): id, source_doc_id, source_local_id,
                         target_id, target_fragment, comment, content_hash, created_at,
                         updated_at
      scry__rel        — typed edges between docs: from_id, to_id, predicate (depends_on|implements|supersedes), fragment
      scry__file       — universal file body index: path, doc_id, body, content_hash,
                         last_modified
      scry__bind_fts   — full-text search over bindings (source_local_id, target_id, comment)
      scry__warning    — lint-style warnings: id, kind, marker_kind, marker_id, file_path,
                         message, detected_at (kinds: misplaced_doc, depends_on_cycle)
      scry__doc_fts    — full-text search over docs (id, summary, rationale, applies, current_path)
      scry__doc_tag_fts — full-text search over tags (tag, doc_id UNINDEXED)
      scry__doc_seeded_question_fts — full-text search over seeded questions (question, doc_id UNINDEXED)
      scry__anchor_fts — full-text search over anchors (id, description)
      scry__file_fts   — full-text search over file bodies (path, body); prefer scry_grep tool

    Returns JSON: {"results": [...], "row_count": N}
    """
    conn = get_db()
    try:
        return serialize(run_query(conn, query))
    finally:
        conn.close()
