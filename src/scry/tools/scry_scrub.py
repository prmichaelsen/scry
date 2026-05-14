"""scry_scrub MCP tool — produce a clean git branch with markers stripped."""
from __future__ import annotations

from scry.service.scrub import scrub
from scry.tools._common import serialize


async def scry_scrub(include_agent: bool = False) -> str:
    """Create a clean PR branch with all @scry.* markers stripped.

    By default, files inside agent/** and any AGENT.md are excluded from
    scrubbing — their markers are left intact. Only tracked files outside
    the agent workspace are cleaned. This matches the common workflow:
    agent/ is gitignored (or excluded via .git/info/exclude), so only the
    tracked source files need clean markers for PR submission.

    Set include_agent=true to restore the prior behavior: scrub everything
    and remove the agent/ directory entirely.

    Creates {branch}--clean from current HEAD. Does not stage or commit —
    leaves unstaged changes for the user.

    Fails if on main/master or if working tree is dirty.
    """
    return serialize(scrub(include_agent=include_agent))
