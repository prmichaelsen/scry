"""scry_scrub — strip @scry.* markers and produce a clean git branch."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from scry.config import get_project_root
from scry.domain.markers import strip_markers_from_content


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=str(cwd), capture_output=True, text=True, check=False,
    )


def scrub(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or get_project_root()

    branch_proc = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    if branch_proc.returncode != 0:
        return {"error": f"git error: {branch_proc.stderr.strip()}"}
    branch = branch_proc.stdout.strip()
    if branch in ("main", "master"):
        return {"error": f"refusing to scrub on protected branch {branch!r}"}

    status_proc = _run(["git", "status", "--porcelain"], root)
    if status_proc.returncode != 0:
        return {"error": f"git status failed: {status_proc.stderr.strip()}"}
    if status_proc.stdout.strip():
        return {"error": "working tree not clean — commit or stash before scrub"}

    clean_branch = f"{branch}--clean"
    create = _run(["git", "checkout", "-B", clean_branch], root)
    if create.returncode != 0:
        return {"error": f"failed to create clean branch: {create.stderr.strip()}"}

    grep = _run(["git", "grep", "-l", "@scry."], root)
    files: list[str] = []
    if grep.returncode == 0:
        files = [line for line in grep.stdout.splitlines() if line.strip()]

    stripped_files: list[str] = []
    for rel in files:
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        cleaned = strip_markers_from_content(text)
        if cleaned != text:
            path.write_text(cleaned, encoding="utf-8")
            stripped_files.append(rel)

    agent_dir = root / "agent"
    removed_agent = False
    if agent_dir.is_dir():
        rm = _run(["git", "rm", "-rf", "agent"], root)
        if rm.returncode == 0:
            removed_agent = True
        else:
            shutil.rmtree(agent_dir, ignore_errors=True)
            removed_agent = not agent_dir.exists()

    return {
        "branch": clean_branch,
        "stripped_files": stripped_files,
        "agent_removed": removed_agent,
        "note": "changes left unstaged; review and commit manually",
    }
