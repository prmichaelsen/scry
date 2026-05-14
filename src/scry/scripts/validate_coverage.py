r"""Validate that every active spec FR has at least one @scry.bind marker.

Output shape:
  {
    "covered": <int>,
    "missing": ["<spec_id>#<FR>", ...],
    "specs_checked": <int>,
  }

Heuristic: walks `scry__doc` rows where kind='spec' and status='active'.
For each, scans the spec's `current_path` content for FR identifiers
(`FR\d+`) and confirms a matching `scry__bind.ref` exists.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

DESCRIPTION = "Check bind coverage for all active specs"

_FR_RE = re.compile(r"\bFR\d+\b")


def run(db: sqlite3.Connection, params: dict) -> dict:
    project_root = Path(params.get("project_root", ".")).resolve()
    specs = db.execute(
        "SELECT id, current_path FROM scry__doc WHERE kind = 'spec' AND status = 'active'"
    ).fetchall()
    missing: list[str] = []
    covered = 0
    for s in specs:
        spec_id = s["id"]
        path = s["current_path"]
        if not path:
            continue
        full = project_root / path
        if not full.is_file():
            continue
        text = full.read_text(encoding="utf-8", errors="replace")
        for fr in sorted(set(_FR_RE.findall(text))):
            ref = f"{spec_id}#{fr}"
            row = db.execute(
                "SELECT 1 FROM scry__bind WHERE ref = ? LIMIT 1", (ref,)
            ).fetchone()
            if row is None:
                missing.append(ref)
            else:
                covered += 1
    return {
        "covered": covered,
        "missing": missing,
        "specs_checked": len(specs),
    }
