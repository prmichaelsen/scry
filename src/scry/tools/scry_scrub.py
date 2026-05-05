"""scry_scrub MCP tool — produce a clean git branch with markers stripped."""
from __future__ import annotations

from scry.service.scrub import scrub
from scry.tools._common import serialize


async def scry_scrub() -> str:
    """Create a `<branch>--clean` git branch with all @scry.* markers removed
    and the agent/ directory deleted. Refuses to run on main/master or with a
    dirty working tree. Leaves changes unstaged for review.

    Returns JSON describing the new branch and stripped files, or
    {"error": "..."} on rejection.
    """
    return serialize(scrub())
