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
    BindMarker,
    DocMarker,
    ParseResult,
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


def _load_gitignore_spec(dirpath: Path) -> "Any | None":
    """Load .gitignore from dirpath and return a pathspec.PathSpec, or None if unavailable."""
    gi = dirpath / ".gitignore"
    if not gi.is_file():
        return None
    try:
        import pathspec  # optional dep; skipped if not installed
        return pathspec.PathSpec.from_lines("gitwildmatch", gi.read_text(errors="replace").splitlines())
    except ImportError:
        return None
    except Exception:
        return None


def _is_gitignored(path: Path, gitignore_specs: "dict[Path, Any]") -> bool:
    """Return True if path is matched by any applicable ancestor .gitignore spec.

    Uses resolved (real) paths when computing relative paths so that files inside
    symlinked directories are checked against THEIR project's gitignore, not the
    linking project's gitignore. This prevents the linking project's '.gitignore'
    entry for 'agent/projects/' from suppressing files inside linked projects.
    """
    real_path = path.resolve()
    for real_dir, spec in gitignore_specs.items():
        if spec is None:
            continue
        try:
            rel = real_path.relative_to(real_dir)
        except ValueError:
            continue
        if spec.match_file(str(rel)):
            return True
    return False


def _walk_project(root: Path) -> Iterable[Path]:
    """Walk project tree following symlinks with cycle detection and .gitignore filtering."""
    visited: set[Path] = set()
    gitignore_specs: dict[Path, Any] = {}

    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        dp = Path(dirpath)
        real = dp.resolve()
        if real in visited:
            dirnames[:] = []
            continue
        visited.add(real)

        spec = _load_gitignore_spec(dp)
        if spec is not None:
            gitignore_specs[real] = spec

        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDED_DIRS
            and not d.startswith(".")
            and (
                (dp / d).is_symlink()
                or not _is_gitignored(dp / d, gitignore_specs)
            )
        ]

        for fn in filenames:
            fp = dp / fn
            if not _is_gitignored(fp, gitignore_specs):
                yield fp


def _is_ephemeral(rel_path: str) -> int:
    return 1 if rel_path.endswith(".scratch.md") else 0


def _under_agent(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/")
    return norm == "agent" or norm.startswith("agent/")


def _record_warnings(conn: sqlite3.Connection, parsed, rel_path: str) -> int:
    """Replace prior misplaced_doc warnings for `rel_path` and emit fresh ones.

    Only clears 'misplaced_doc' kind — other warning kinds (e.g. depends_on_cycle)
    are written by upsert_doc and must not be clobbered here.
    """
    conn.execute(
        "DELETE FROM scry__warning WHERE file_path = ? AND kind = 'misplaced_doc'",
        (rel_path,),
    )
    in_agent = _under_agent(rel_path)
    n = 0
    if not in_agent:
        for d in parsed.docs:
            conn.execute(
                """
                INSERT INTO scry__warning(kind, marker_kind, marker_id, file_path, message)
                VALUES ('misplaced_doc', 'doc', ?, ?, ?)
                """,
                (d.id, rel_path, f"@scry.entry {d.id!r} found outside agent/. Move to agent/."),
            )
            n += 1
    return n


def _sync_relationships(conn: sqlite3.Connection, marker: DocMarker) -> list[str]:
    """Sync doc_relationship rows for marker.depends_on. Returns warning messages for cycles."""
    # Clear stale relationship rows for this doc.
    conn.execute(
        "DELETE FROM doc_relationship WHERE from_id = ? AND relationship = 'depends_on'",
        (marker.id,),
    )
    warnings: list[str] = []
    for dep_id in marker.depends_on:
        if dep_id == marker.id:
            warnings.append(f"self-loop in depends_on ignored: {marker.id}")
            continue
        # Cycle check: would inserting (marker.id -> dep_id) form a cycle?
        cycle = conn.execute(
            """
            WITH RECURSIVE reachable(node) AS (
              SELECT to_id FROM doc_relationship WHERE from_id = ?
              UNION
              SELECT dr.to_id FROM doc_relationship dr
              JOIN reachable r ON dr.from_id = r.node
            )
            SELECT 1 FROM reachable WHERE node = ? LIMIT 1
            """,
            (dep_id, marker.id),
        ).fetchone()
        if cycle is not None:
            warnings.append(
                f"cycle in depends_on ignored: {marker.id} -> {dep_id} would form a cycle"
            )
            continue
        conn.execute(
            "INSERT OR IGNORE INTO doc_relationship(from_id, to_id, relationship) VALUES (?, ?, 'depends_on')",
            (marker.id, dep_id),
        )
    return warnings


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
                                  rationale, applies, seeded_questions, implements, supersedes,
                                  ephemeral, missing_since, content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                marker.id, rel_path, marker.summary, marker.kind, marker.weight, marker.status,
                marker.tags, marker.rationale, marker.applies, marker.seeded_questions,
                marker.implements, marker.supersedes,
                ephemeral, h, _now(), _now(),
            ),
        )
    else:
        conn.execute(
            """
            UPDATE scry__doc SET current_path = ?, summary = ?, kind = ?, weight = ?, status = ?,
                                 tags = ?, rationale = ?, applies = ?, seeded_questions = ?,
                                 implements = ?, supersedes = ?,
                                 ephemeral = ?, missing_since = NULL, content_hash = ?,
                                 updated_at = ?
            WHERE id = ?
            """,
            (
                rel_path, marker.summary, marker.kind, marker.weight, marker.status,
                marker.tags, marker.rationale, marker.applies, marker.seeded_questions,
                marker.implements, marker.supersedes,
                ephemeral, h, _now(), marker.id,
            ),
        )
    # Sync depends_on into doc_relationship; record cycle warnings.
    # Clear stale cycle warnings for this marker before re-inserting.
    conn.execute(
        "DELETE FROM scry__warning WHERE kind = 'depends_on_cycle' AND marker_id = ?",
        (marker.id,),
    )
    cycle_warnings = _sync_relationships(conn, marker)
    for msg in cycle_warnings:
        conn.execute(
            """
            INSERT INTO scry__warning(kind, marker_kind, marker_id, file_path, message)
            VALUES ('depends_on_cycle', 'doc', ?, ?, ?)
            """,
            (marker.id, rel_path, msg),
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


def upsert_bind(conn: sqlite3.Connection, marker: BindMarker, rel_path: str) -> None:
    """Upsert a @scry.bind marker record.

    The uniqueness key is (local_id, ref, file_path): comma-expanded binds share
    the same local_id but have distinct refs, and all must be stored independently.
    """
    h = content_hash(marker.raw_body)
    row = conn.execute(
        "SELECT content_hash FROM scry__bind WHERE local_id = ? AND ref = ? AND file_path = ?",
        (marker.local_id, marker.ref, rel_path),
    ).fetchone()
    if row is not None and row["content_hash"] == h:
        return
    if row is None:
        conn.execute(
            """
            INSERT INTO scry__bind(local_id, ref, comment, file_path, content_hash,
                                   created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (marker.local_id, marker.ref, marker.comment, rel_path, h, _now(), _now()),
        )
    else:
        conn.execute(
            """
            UPDATE scry__bind SET comment = ?, content_hash = ?, updated_at = ?
            WHERE local_id = ? AND ref = ? AND file_path = ?
            """,
            (marker.comment, h, _now(), marker.local_id, marker.ref, rel_path),
        )


def _path_unchanged(conn: sqlite3.Connection, table: str, ident: str, rel_path: str) -> bool:
    row = conn.execute(f"SELECT current_path FROM {table} WHERE id = ?", (ident,)).fetchone()
    return row is not None and row["current_path"] == rel_path


def reindex_file(conn: sqlite3.Connection, abs_path: Path, project_root: Path) -> ParseResult:
    """Parse a single file and upsert its markers. Also clear stale bind/anchor
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
    for a in parsed.anchors:
        upsert_anchor(conn, a, rel_path)

    # Hard-delete bind rows that previously belonged to this file but were not seen this pass.
    # Use (local_id, ref) pairs as the key since comma expansion produces multiple rows per local_id.
    seen_bind_keys = {(m.local_id, m.ref) for m in parsed.binds}
    seen_anchor_names = {m.name for m in parsed.anchors}

    existing_binds = {(r["local_id"], r["ref"]) for r in conn.execute(
        "SELECT local_id, ref FROM scry__bind WHERE file_path = ?", (rel_path,)
    ).fetchall()}
    for stale_local_id, stale_ref in existing_binds - seen_bind_keys:
        conn.execute(
            "DELETE FROM scry__bind WHERE local_id = ? AND ref = ? AND file_path = ?",
            (stale_local_id, stale_ref, rel_path),
        )

    existing_anchors = {r["name"] for r in conn.execute(
        "SELECT name FROM scry__anchor WHERE current_path = ?", (rel_path,)
    ).fetchall()}
    for stale_name in existing_anchors - seen_anchor_names:
        conn.execute("DELETE FROM scry__anchor WHERE name = ?", (stale_name,))

    for bind in parsed.binds:
        upsert_bind(conn, bind, rel_path)

    _record_warnings(conn, parsed, rel_path)

    conn.commit()
    return parsed


def handle_file_deletion(conn: sqlite3.Connection, rel_path: str) -> None:
    """Soft-delete docs; hard-delete anchors/binds/relationships for a removed file."""
    now = _now()
    # Collect doc IDs for this path before soft-deleting (for relationship cleanup).
    doc_ids = [
        r["id"] for r in conn.execute(
            "SELECT id FROM scry__doc WHERE current_path = ? AND missing_since IS NULL",
            (rel_path,),
        ).fetchall()
    ]
    conn.execute(
        "UPDATE scry__doc SET missing_since = ? WHERE current_path = ? AND missing_since IS NULL",
        (now, rel_path),
    )
    conn.execute("DELETE FROM scry__anchor WHERE current_path = ?", (rel_path,))
    conn.execute("DELETE FROM scry__bind WHERE file_path = ?", (rel_path,))
    conn.execute("DELETE FROM scry__warning WHERE file_path = ?", (rel_path,))
    for doc_id in doc_ids:
        conn.execute(
            "DELETE FROM doc_relationship WHERE from_id = ? AND relationship = 'depends_on'",
            (doc_id,),
        )
    conn.commit()


def handle_subtree_deletion(conn: sqlite3.Connection, prefix: str) -> None:
    """Soft-delete docs; hard-delete anchors/binds for a removed subtree."""
    now = _now()
    conn.execute(
        "UPDATE scry__doc SET missing_since = COALESCE(missing_since, ?) WHERE current_path LIKE ?",
        (now, prefix + "%"),
    )
    conn.execute("DELETE FROM scry__anchor WHERE current_path LIKE ?", (prefix + "%",))
    conn.execute("DELETE FROM scry__bind WHERE file_path LIKE ?", (prefix + "%",))
    conn.execute("DELETE FROM scry__warning WHERE file_path LIKE ?", (prefix + "%",))
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
            len(parsed.docs) + len(parsed.anchors) + len(parsed.binds)
        )

    # Flag any DB record whose current_path is not on disk.
    flagged = []
    for table in ("scry__doc",):
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
        for table in ("scry__doc",):
            rows = conn.execute(
                f"SELECT id FROM {table} WHERE missing_since IS NOT NULL"
            ).fetchall()
            for r in rows:
                conn.execute(f"DELETE FROM {table} WHERE id = ?", (r["id"],))
                deleted.append({"table": table, "id": r["id"]})
        # Anchors/binds for missing paths can also be cleared.
        for table, col in (
            ("scry__anchor", "current_path"),
            ("scry__bind", "file_path"),
        ):
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {col} IS NOT NULL"
            ).fetchall()
            for r in rows:
                cp = r[col]
                if cp not in visited_paths:
                    key_col = "name" if table == "scry__anchor" else "local_id"
                    conn.execute(
                        f"DELETE FROM {table} WHERE {key_col} = ? AND {col} = ?",
                        (r[key_col], cp),
                    )
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
