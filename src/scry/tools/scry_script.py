"""scry_script MCP tool — discover and execute project validation scripts."""
from __future__ import annotations

from typing import Any

from scry.config import get_db
from scry.service.script import list_scripts, run_script
from scry.tools._common import serialize


async def scry_script(
    action: str,
    script: str | None = None,
    params: dict[str, Any] | None = None,
) -> str:
    """Discover or run scry scripts.

    Args:
        action: 'list' to enumerate available scripts, 'run' to execute one.
        script: Required when action='run'. Script name (file stem).
        params: Optional dict passed to the script's `run(db, params)` callable.

    Returns JSON. On 'list': {"scripts": [{"name", "description", "path"}, ...]}.
    On 'run': whatever the script returns (must be a JSON-serializable dict).
    """
    if action == "list":
        return serialize(list_scripts())
    if action == "run":
        if not script:
            return serialize({"error": "action='run' requires `script` argument"})
        conn = get_db()
        try:
            return serialize(run_script(conn, script, params or {}))
        finally:
            conn.close()
    return serialize({"error": f"unknown action {action!r} (expected 'list' or 'run')"})
