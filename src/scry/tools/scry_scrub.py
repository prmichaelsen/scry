"""scry_scrub MCP tool — produce a clean git branch with markers stripped."""
from __future__ import annotations

from scry.service.scrub import scrub
from scry.tools._common import serialize


async def scry_scrub() -> str:
    """Create a clean PR branch with all @scry.* markers stripped and agent/
    directory removed. For submitting code review without exposing agent
    infrastructure.

    Creates {branch}--clean from current HEAD. Does not stage or commit —
    leaves unstaged changes for the user.

    Fails if on main/master or if working tree is dirty.
    """
    return serialize(scrub())
