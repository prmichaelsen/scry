"""scry_mint — collision-free ID minting + marker schema."""
from __future__ import annotations

import re
import secrets
import sqlite3
from typing import Any

VALID_KINDS = ("doc", "file", "anchor", "impl", "test")

_TABLE = {
    "doc": "scry__doc",
    "file": "scry__file",
    "anchor": "scry__anchor",
    "impl": "scry__impl",
    "test": "scry__test",
}

_PRIMARY_KEY_COL = {
    "doc": "id",
    "file": "id",
    "anchor": "name",
    "impl": "id",
    "test": "id",
}

_PREFIX_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_prefix(kind: str, prefix: str) -> str | None:
    if not _PREFIX_RE.match(prefix):
        return f"prefix must match [A-Za-z0-9._-]+ (got {prefix!r})"
    has_dot = "." in prefix
    if kind in ("doc", "file") and not has_dot:
        return f"{kind} prefix must contain a dot (got {prefix!r})"
    if kind in ("anchor", "impl", "test") and has_dot:
        return f"{kind} prefix must not contain dots (got {prefix!r})"
    return None


def _exists(conn: sqlite3.Connection, kind: str, ident: str) -> bool:
    table = _TABLE[kind]
    col = _PRIMARY_KEY_COL[kind]
    row = conn.execute(f"SELECT 1 FROM {table} WHERE {col} = ? LIMIT 1", (ident,)).fetchone()
    return row is not None


def _generate(prefix: str) -> str:
    return f"{prefix}~{secrets.token_hex(4)}"


def _marker_schema(kind: str, ident: str) -> dict[str, Any]:
    if kind == "doc":
        return {
            "marker_open": f"<!-- @scry.doc",
            "marker_close": "@scry.doc.end -->",
            "fields": {
                "id": ident,
                "kind": "one of: design, spec, task, milestone, clarification, pattern, internal",
                "summary": "1-2 sentence description (use `>` for folded scalar)",
                "status": "one of: draft, active, approved, stale, complete",
                "weight": "0.0-1.0 importance score",
                "tags": "YAML list, e.g. [\"scope:auth\", \"topic:security\"]",
                "rationale": "why this doc matters (folded scalar OK)",
                "applies": "comma-separated triggers (when to read this)",
                "seeded_questions": "YAML list of starter questions",
            },
            "suggested_path": f"agent/docs/{ident}.md",
        }
    if kind == "file":
        return {
            "marker_open": "<!-- @scry.file",
            "marker_close": "@scry.file.end -->",
            "fields": {
                "id": ident,
                "kind": "freeform string describing the file role",
                "summary": "what this file does",
                "status": "one of: draft, active, approved, stale, complete",
                "weight": "0.0-1.0 importance score",
                "tags": "YAML list",
                "rationale": "why callers should know about this file",
                "applies": "when to consult this file",
                "seeded_questions": "YAML list",
            },
            "suggested_path": f"src/{ident.split('~')[0].split('.')[-1]}.py",
        }
    if kind == "anchor":
        return {
            "marker_open": f"<!-- @scry.anchor {ident}",
            "marker_close": "@scry.anchor.end -->",
            "fields": {
                "description": "what this code location represents",
                "seeded_questions": "YAML list",
            },
        }
    if kind == "impl":
        return {
            "marker_line": f"# @scry.impl {ident} <ref>",
            "fields": {
                "id": ident,
                "ref": "spec or design reference, e.g. spec.auth~xyz#FR3",
            },
        }
    if kind == "test":
        return {
            "marker_line": f"# @scry.test {ident} <ref>",
            "fields": {
                "id": ident,
                "ref": "spec or design reference, e.g. spec.auth~xyz#UT1",
            },
        }
    return {}


def mint(conn: sqlite3.Connection, kind: str, prefix: str) -> dict[str, Any]:
    if kind not in VALID_KINDS:
        return {"error": f"invalid kind {kind!r} (expected one of {VALID_KINDS})"}
    err = _validate_prefix(kind, prefix)
    if err:
        return {"error": err}
    for _ in range(8):
        ident = _generate(prefix)
        if not _exists(conn, kind, ident):
            return {"id": ident, "schema": _marker_schema(kind, ident)}
    return {"error": "failed to mint a unique id after 8 attempts"}
