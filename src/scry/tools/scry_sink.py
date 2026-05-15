"""scry_sink MCP tool — lower the index back to disk-only state."""
from __future__ import annotations

import sqlite3
from typing import Any

from pydantic import BaseModel

from mcp.server.fastmcp import Context

from scry.config import get_db
from scry.service.sink import get_counts, sink
from scry.tools._common import serialize


class _SinkConfirmation(BaseModel):
    """Elicitation schema: user must set proceed=True to confirm the sink."""
    proceed: bool


def _elicitation_message(counts: dict[str, int]) -> str:
    """Format the elicitation prompt with live row counts."""
    return (
        "Sink will clear:\n"
        f"  - {counts['scry__doc']} docs\n"
        f"  - {counts['scry__anchor']} anchors\n"
        f"  - {counts['scry__bind']} binds\n"
        f"  - {counts['doc_relationship']} relationships\n"
        f"  - {counts['scry__warning']} warnings\n"
        "Disk markers remain intact. Proceed?"
    )


async def _run(
    conn: sqlite3.Connection,
    ctx: Any,
    then_surface: bool,
) -> str:
    """Elicit confirmation then execute sink. Separated for testability."""
    counts = get_counts(conn)
    message = _elicitation_message(counts)

    try:
        result = await ctx.elicit(message, _SinkConfirmation)
    except Exception as exc:
        return serialize({
            "status": "aborted",
            "reason": f"elicitation unavailable: {exc}",
            "counts": counts,
        })

    if result.action != "accept" or not result.data.proceed:
        return serialize({
            "status": "cancelled",
            "reason": f"user {result.action}d",
            "counts": counts,
        })

    sink_result = sink(conn, then_surface=then_surface)
    response: dict[str, Any] = {"status": "ok", "cleared": sink_result["cleared"]}
    if then_surface and "surface" in sink_result:
        surface_result = sink_result["surface"]
        response["reindexed"] = {
            "files_scanned": surface_result["files_scanned"],
            "markers_indexed": surface_result["markers_indexed"],
        }
    return serialize(response)


async def scry_sink(ctx: Context, then_surface: bool = False) -> str:
    """Lower the index back to disk-only state. The DB forgets; the disk remembers.

    Truncates all five scry index tables (scry__doc, scry__anchor, scry__bind,
    doc_relationship, scry__warning) in a single atomic transaction. Schema is
    preserved; FTS tables update via existing triggers; the migration table is
    not touched.  Disk markers are never modified.

    Requires protocol-level user confirmation via MCP elicitation before
    executing — the operation will not proceed if the confirmation is declined,
    cancelled, or unavailable.

    Args:
        then_surface: If True, immediately runs scry_surface after the sink to
                      rebuild the index from disk markers in a single call.
                      Equivalent to "reset + reindex."

    Returns JSON with pre-deletion counts and operation result.
    """
    conn = get_db()
    try:
        return await _run(conn, ctx, then_surface)
    finally:
        conn.close()
