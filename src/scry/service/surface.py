"""scry_surface — batch re-index of project files.

Also exposes shared upsert helpers used by the watcher daemon.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scry.config import BINARY_SNIFF_BYTES, EXCLUDED_DIRS, get_project_root
from scry.domain.markers import (
    AnchorMarker,
    DocMarker,
    FileMarker,
    ImplMarker,
    ParseResult,
    TestMarker,
    content_hash,
    parse_markers,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(BINARY_SNIFF_BYTES)
    except OSError:
        return True
    return b"\x00" in chunk


def _walk_project(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for fn in filenames:
            yield Path(dirpath) / fn


def _is_ephemeral(rel_path: str) -> int:
    return 1 if rel_path.endswith(".scratch.md") else 0


def _under_agent(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/")
    return norm == "agent" or norm.startswith("agent/")


def _record_warnings(conn: sqlite3.Connection, parsed, rel_path: str) -> int:
    """Replace any prior warnings for `rel_path` with the current state.

    Rule: docs belong inside `agent/`; files describe non-agent source.
    Misplaced markers are still indexed, just flagged.
    """
    conn.execute("DELETE FROM scry__warning WHERE file_path = ?", (rel_path,))
    in_agent = _under_agent(rel_path)
    n = 0
    if not in_agent:
        for d in parsed.docs:
            conn.execute(
                """
                INSERT INTO scry__warning(kind, marker_kind, marker_id, file_path, message)
                VALUES ('misplaced_doc', 'doc', ?, ?, ?)
                """,
                (d.id, rel_path, f"@scry.doc {d.id!r} found outside agent/. Move to agent/."),
            )
            n += 1
    if in_agent:
        for f in parsed.files:
            conn.execute(
                """
                INSERT INTO scry__warning(kind, marker_kind, marker_id, file_path, message)
                VALUES ('misplaced_file', 'file', ?, ?, ?)
                """,
                (f.id, rel_path, f"@scry.file {f.id!r} found inside agent/. File markers describe non-agent source."),
            )
            n += 1
    return n


def upsert_doc(conn: sqlite3.Connection, marker: DocMarker, rel_path: str) -> None:
    h = content_hash(marker.raw_body)
    row = conn.execute(
        "SELECT content_hash FROM scry__doc WHERE id = ?", (marker.id,)
    ).fetchone()
    ephemeral = _is_ephemeral(rel_path)
    if row is not None and row["content_hash"] == h and _path_unchanged(conn, "scry__doc", marker.id, rel_path):
        return
    if row is None:
        conn.execute(
            """
            INSERT INTO scry__doc(id, current_path, summary, kind, weight, status, tags,
                                  rationale, applies, seeded_questions, ephemeral, missing_since,
                                  content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                marker.id, rel_path, marker.summary, marker.kind, marker.weight, marker.status,
                marker.tags, marker.rationale, marker.applies, marker.seeded_questions,
                ephemeral, h, _now(), _now(),
            ),
        )
    else:
        conn.execute(
            """
            UPDATE scry__doc SET current_path = ?, summary = ?, kind = ?, weight = ?, status = ?,
                                 tags = ?, rationale = ?, applies = ?, seeded_questions = ?,
                                 ephemeral = ?, missing_since = NULL, content_hash = ?,
                                 updated_at = ?
            WHERE id = ?
            """,
            (
                rel_path, marker.summary, marker.kind, marker.weight, marker.status,
                marker.tags, marker.rationale, marker.applies, marker.seeded_questions,
                ephemeral, h, _now(), marker.id,
            ),
        )


def upsert_file(conn: sqlite3.Connection, marker: FileMarker, rel_path: str) -> None:
    h = content_hash(marker.raw_body)
    row = conn.execute(
        "SELECT content_hash FROM scry__file WHERE id = ?", (marker.id,)
    ).fetchone()
    ephemeral = _is_ephemeral(rel_path)
    if row is not None and row["content_hash"] == h and _path_unchanged(conn, "scry__file", marker.id, rel_path):
        return
    if row is None:
        conn.execute(
            """
            INSERT INTO scry__file(id, current_path, summary, kind, weight, status, tags,
                                   rationale, applies, seeded_questions, ephemeral, missing_since,
                                   content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                marker.id, rel_path, marker.summary, marker.kind, marker.weight, marker.status,
                marker.tags, marker.rationale, marker.applies, marker.seeded_questions,
                ephemeral, h, _now(), _now(),
            ),
        )
    else:
        conn.execute(
            """
            UPDATE scry__file SET current_path = ?, summary = ?, kind = ?, weight = ?, status = ?,
                                  tags = ?, rationale = ?, applies = ?, seeded_questions = ?,
                                  ephemeral = ?, missing_since = NULL, content_hash = ?,
                                  updated_at = ?
            WHERE id = ?
            """,
            (
                rel_path, marker.summary, marker.kind, marker.weight, marker.status,
                marker.tags, marker.rationale, marker.applies, marker.seeded_questions,
                ephemeral, h, _now(), marker.id,
            ),
        )


def upsert_anchor(conn: sqlite3.Connection, marker: AnchorMarker, rel_path: str) -> None:
    h = content_hash(marker.raw_body)
    row = conn.execute(
        "SELECT content_hash, current_path FROM scry__anchor WHERE name = ?", (marker.name,)
    ).fetchone()
    if row is not None and row["content_hash"] == h and row["current_path"] == rel_path:
        return
    if row is None:
        conn.execute(
            """
            INSERT INTO scry__anchor(name, description, seeded_questions, current_path,
                                     content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                marker.name, marker.description, marker.seeded_questions,
                rel_path, h, _now(), _now(),
            ),
        )
    else:
        conn.execute(
            """
            UPDATE scry__anchor SET description = ?, seeded_questions = ?, current_path = ?,
                                    content_hash = ?, updated_at = ?
            WHERE name = ?
            """,
            (marker.description, marker.seeded_questions, rel_path, h, _now(), marker.name),
        )


def upsert_impl(conn: sqlite3.Connection, marker: ImplMarker, rel_path: str) -> None:
    h = content_hash(marker.raw_body)
    row = conn.execute(
        "SELECT content_hash, ref, file_path FROM scry__impl WHERE id = ?", (marker.id,)
    ).fetchone()
    if row is not None and row["content_hash"] == h and row["ref"] == marker.ref and row["file_path"] == rel_path:
        return
    if row is None:
        conn.execute(
            """
            INSERT INTO scry__impl(id, ref, file_path, content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (marker.id, marker.ref, rel_path, h, _now(), _now()),
        )
    else:
        conn.execute(
            """
            UPDATE scry__impl SET ref = ?, file_path = ?, content_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (marker.ref, rel_path, h, _now(), marker.id),
        )


def upsert_test(conn: sqlite3.Connection, marker: TestMarker, rel_path: str) -> None:
    h = content_hash(marker.raw_body)
    row = conn.execute(
        "SELECT content_hash, ref, file_path FROM scry__test WHERE id = ?", (marker.id,)
    ).fetchone()
    if row is not None and row["content_hash"] == h and row["ref"] == marker.ref and row["file_path"] == rel_path:
        return
    if row is None:
        conn.execute(
            """
            INSERT INTO scry__test(id, ref, file_path, content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (marker.id, marker.ref, rel_path, h, _now(), _now()),
        )
    else:
        conn.execute(
            """
            UPDATE scry__test SET ref = ?, file_path = ?, content_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (marker.ref, rel_path, h, _now(), marker.id),
        )


def _path_unchanged(conn: sqlite3.Connection, table: str, ident: str, rel_path: str) -> bool:
    row = conn.execute(f"SELECT current_path FROM {table} WHERE id = ?", (ident,)).fetchone()
    return row is not None and row["current_path"] == rel_path


def reindex_file(conn: sqlite3.Connection, abs_path: Path, project_root: Path) -> ParseResult:
    """Parse a single file and upsert its markers. Also clear stale impl/test/anchor
    rows that previously came from this path but no longer do."""
    rel_path = str(abs_path.relative_to(project_root))
    if _is_binary(abs_path):
        return ParseResult()
    try:
        content = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ParseResult()
    parsed = parse_markers(content)

    for d in parsed.docs:
        upsert_doc(conn, d, rel_path)
    for f in parsed.files:
        upsert_file(conn, f, rel_path)
    for a in parsed.anchors:
        upsert_anchor(conn, a, rel_path)

    # Hard-delete impl/test rows that previously belonged to this file but were not seen this pass.
    seen_impl_ids = {m.id for m in parsed.impls}
    seen_test_ids = {m.id for m in parsed.tests}
    seen_anchor_names = {m.name for m in parsed.anchors}

    existing_impls = {r["id"] for r in conn.execute(
        "SELECT id FROM scry__impl WHERE file_path = ?", (rel_path,)
    ).fetchall()}
    for stale_id in existing_impls - seen_impl_ids:
        conn.execute("DELETE FROM scry__impl WHERE id = ?", (stale_id,))

    existing_tests = {r["id"] for r in conn.execute(
        "SELECT id FROM scry__test WHERE file_path = ?", (rel_path,)
    ).fetchall()}
    for stale_id in existing_tests - seen_test_ids:
        conn.execute("DELETE FROM scry__test WHERE id = ?", (stale_id,))

    existing_anchors = {r["name"] for r in conn.execute(
        "SELECT name FROM scry__anchor WHERE current_path = ?", (rel_path,)
    ).fetchall()}
    for stale_name in existing_anchors - seen_anchor_names:
        conn.execute("DELETE FROM scry__anchor WHERE name = ?", (stale_name,))

    for impl in parsed.impls:
        upsert_impl(conn, impl, rel_path)
    for test in parsed.tests:
        upsert_test(conn, test, rel_path)

    _record_warnings(conn, parsed, rel_path)

    conn.commit()
    return parsed


def handle_file_deletion(conn: sqlite3.Connection, rel_path: str) -> None:
    """Soft-delete docs/files; hard-delete anchors/impls/tests for a removed file."""
    now = _now()
    conn.execute(
        "UPDATE scry__doc SET missing_since = ? WHERE current_path = ? AND missing_since IS NULL",
        (now, rel_path),
    )
    conn.execute(
        "UPDATE scry__file SET missing_since = ? WHERE current_path = ? AND missing_since IS NULL",
        (now, rel_path),
    )
    conn.execute("DELETE FROM scry__anchor WHERE current_path = ?", (rel_path,))
    conn.execute("DELETE FROM scry__impl WHERE file_path = ?", (rel_path,))
    conn.execute("DELETE FROM scry__test WHERE file_path = ?", (rel_path,))
    conn.execute("DELETE FROM scry__warning WHERE file_path = ?", (rel_path,))
    conn.commit()


def surface(
    conn: sqlite3.Connection,
    project_root: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Walk the project, reindex every file, then flag/cleanup missing rows."""
    root = project_root or get_project_root()
    visited_paths: set[str] = set()
    counts = {"files_scanned": 0, "markers_indexed": 0}

    # Warnings are derived state — wipe and rebuild from the live walk.
    conn.execute("DELETE FROM scry__warning")

    for path in _walk_project(root):
        rel = str(path.relative_to(root))
        visited_paths.add(rel)
        counts["files_scanned"] += 1
        parsed = reindex_file(conn, path, root)
        counts["markers_indexed"] += (
            len(parsed.docs) + len(parsed.files) + len(parsed.anchors)
            + len(parsed.impls) + len(parsed.tests)
        )

    # Flag any DB record whose current_path is not on disk.
    flagged = []
    for table in ("scry__doc", "scry__file"):
        rows = conn.execute(
            f"SELECT id, current_path FROM {table} WHERE current_path IS NOT NULL"
        ).fetchall()
        for r in rows:
            cp = r["current_path"]
            if cp and cp not in visited_paths:
                conn.execute(
                    f"UPDATE {table} SET missing_since = COALESCE(missing_since, ?) WHERE id = ?",
                    (_now(), r["id"]),
                )
                flagged.append({"table": table, "id": r["id"], "path": cp})

    deleted: list[dict[str, Any]] = []
    if force:
        for table in ("scry__doc", "scry__file"):
            rows = conn.execute(
                f"SELECT id FROM {table} WHERE missing_since IS NOT NULL"
            ).fetchall()
            for r in rows:
                conn.execute(f"DELETE FROM {table} WHERE id = ?", (r["id"],))
                deleted.append({"table": table, "id": r["id"]})
        # Anchors/impls/tests for missing paths can also be cleared.
        for table, col in (("scry__anchor", "current_path"), ("scry__impl", "file_path"), ("scry__test", "file_path")):
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {col} IS NOT NULL"
            ).fetchall()
            for r in rows:
                cp = r[col]
                if cp not in visited_paths:
                    key_col = "name" if table == "scry__anchor" else "id"
                    conn.execute(f"DELETE FROM {table} WHERE {key_col} = ?", (r[key_col],))
                    deleted.append({"table": table, key_col: r[key_col]})
    conn.commit()

    warnings = conn.execute(
        "SELECT kind, COUNT(*) AS n FROM scry__warning GROUP BY kind"
    ).fetchall()
    warning_counts = {r["kind"]: r["n"] for r in warnings}
    sample = [
        dict(r) for r in conn.execute(
            "SELECT kind, marker_id, file_path, message FROM scry__warning LIMIT 10"
        ).fetchall()
    ]

    return {
        "files_scanned": counts["files_scanned"],
        "markers_indexed": counts["markers_indexed"],
        "flagged_missing": flagged,
        "force_deleted": deleted,
        "warnings": {"counts": warning_counts, "sample": sample, "hint": "query scry__warning for the full list"},
        "force": force,
    }
