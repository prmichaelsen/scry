"""scry_mint — collision-free ID minting + marker schema + collision detection."""
from __future__ import annotations

import re
import secrets
import sqlite3
from typing import Any

VALID_KINDS = ("entry", "anchor", "bind")

_TABLE = {
    "entry": "scry__doc",
    "anchor": "scry__anchor",
    # bind: local_id is file-scoped; no global collision check needed
}

_PRIMARY_KEY_COL = {
    "entry": "id",
    "anchor": "name",
}

# Summary column name per table (for collision warnings)
_SUMMARY_COL = {
    "entry": "summary",
    "anchor": "description",
}

_PREFIX_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_prefix(kind: str, prefix: str) -> str | None:
    if not _PREFIX_RE.match(prefix):
        return f"prefix must match [A-Za-z0-9._-]+ (got {prefix!r})"
    has_dot = "." in prefix
    if kind == "entry" and not has_dot:
        return f"{kind} prefix must contain a dot (got {prefix!r})"
    if kind in ("anchor", "bind") and has_dot:
        return f"{kind} prefix must not contain dots (got {prefix!r})"
    return None


def _exists(conn: sqlite3.Connection, kind: str, ident: str) -> bool:
    if kind == "bind":
        # local_id is file-scoped (FR2) — no global uniqueness check.
        return False
    table = _TABLE[kind]
    col = _PRIMARY_KEY_COL[kind]
    row = conn.execute(f"SELECT 1 FROM {table} WHERE {col} = ? LIMIT 1", (ident,)).fetchone()
    return row is not None


def _generate(prefix: str) -> str:
    return f"{prefix}~{secrets.token_hex(4)}"


def _marker_schema(kind: str, ident: str) -> dict[str, Any]:
    if kind == "entry":
        return {
            "marker_open": "<!-- @scry.entry",
            "marker_close": "@scry.entry.end -->",
            "fields": {
                "id": ident,
                "kind": (
                    "one of: design, pattern, spec, lesson, internal, "
                    "task, milestone, report, audit, research, code"
                ),
                "summary": "1-2 sentence description (use `>` for folded scalar)",
                "status": "one of: draft, active, deprecated (custom values allowed)",
                "weight": "0.0-1.0 importance score",
                "tags": "YAML list, e.g. [\"scope:auth\", \"topic:security\"]",
                "rationale": "why this doc matters (folded scalar OK)",
                "applies": "comma-separated triggers (when to read this)",
                "seeded_questions": "YAML list of starter questions",
            },
            "suggested_path": f"agent/docs/{ident}.md",
        }
    if kind == "anchor":
        return {
            "marker_open": f"<!-- @scry.anchor {ident}",
            "marker_close": "@scry.anchor.end -->",
            "fields": {
                "description": "what this code location represents (required, non-empty)",
                "seeded_questions": "YAML list (required, empty allowed)",
            },
        }
    if kind == "bind":
        return {
            "marker_line": f"# @scry.bind {ident} <ref> [comment]",
            "marker_block_open": f"# @scry.bind {ident} <ref>",
            "marker_block_close": "# @scry.bind.end",
            "fields": {
                "local-id": ident,
                "ref": (
                    "binding target — artifact-ref ({id} or {id}#{loose-anchor}) "
                    "or anchor-id ({name}~{hash}). "
                    "E.g. spec.auth~xyz#FR3, design.arch~abcd1234#DR2, token-val~feedcafe"
                ),
                "comment": "(optional) free-form context about this binding",
            },
            "note": (
                "local_id is file-scoped; the same id can appear in different files. "
                "Single-line form for short comments; block form for multi-line commentary."
            ),
        }
    return {}


def _check_collisions(
    conn: sqlite3.Connection, kind: str, prefix: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return (tier1_collisions, tier2_neighbors) for a given prefix.

    Tier-1: existing markers whose ID starts with exactly this prefix~.
    Tier-2: existing markers in the same kind+first-segment "family" (informational).

    bind markers are file-scoped; collision check not meaningful.
    """
    if kind == "bind" or kind not in _TABLE:
        return [], []

    table = _TABLE[kind]
    col = _PRIMARY_KEY_COL[kind]
    summary_col = _SUMMARY_COL[kind]

    # Tier-1: same prefix (design.auth-flow → id LIKE 'design.auth-flow~%')
    tier1_rows = conn.execute(
        f"SELECT {col}, {summary_col} FROM {table} WHERE {col} LIKE ? ORDER BY {col} LIMIT 10",
        (f"{prefix}~%",),
    ).fetchall()
    tier1 = [{"id": r[0], "summary": r[1] or ""} for r in tier1_rows]

    # Tier-2: family-slug neighbors — same kind + first segment of name part.
    # "design.auth-flow" → kind_prefix="design", first_seg="auth" → pattern="design.auth%"
    # "auth-check" (anchor) → first_seg="auth" → pattern="auth%"
    if "." in prefix:
        kind_prefix, name_part = prefix.split(".", 1)
        first_seg = name_part.split("-")[0]
        family_pattern = f"{kind_prefix}.{first_seg}%"
    else:
        first_seg = prefix.split("-")[0]
        family_pattern = f"{first_seg}%"

    tier2_rows = conn.execute(
        f"SELECT {col}, {summary_col} FROM {table} "
        f"WHERE {col} LIKE ? AND {col} NOT LIKE ? "
        f"ORDER BY {col} LIMIT 10",
        (f"{family_pattern}~%", f"{prefix}~%"),
    ).fetchall()
    tier2 = [{"id": r[0], "summary": r[1] or ""} for r in tier2_rows]

    return tier1, tier2


def mint(conn: sqlite3.Connection, kind: str, prefix: str) -> dict[str, Any]:
    if kind not in VALID_KINDS:
        return {"error": f"invalid kind {kind!r} (expected one of {VALID_KINDS})"}
    err = _validate_prefix(kind, prefix)
    if err:
        return {"error": err}
    for _ in range(8):
        ident = _generate(prefix)
        if not _exists(conn, kind, ident):
            result: dict[str, Any] = {"id": ident, "schema": _marker_schema(kind, ident)}
            tier1, tier2 = _check_collisions(conn, kind, prefix)
            if tier1:
                result["tier1_collisions"] = tier1
            if tier2:
                result["tier2_neighbors"] = tier2
            return result
    return {"error": "failed to mint a unique id after 8 attempts"}
