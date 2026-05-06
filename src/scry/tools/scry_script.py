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
    """Run validation or transformation scripts with DB access.

    Actions:
      list — discover available scripts (bundled + project-local)
      run  — execute a named script

    Args:
        action: "list" or "run"
        script: script name (required for action="run")
        params: arbitrary params passed to the script (optional)

    Scripts have read-write DB access. They return structured JSON.
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
