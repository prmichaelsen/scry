"""scry_surface — batch re-index of project files.

Also exposes shared upsert helpers used by the watcher daemon.
"""
from __future__ import annotations

import hashlib
import json
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

# ---------------------------------------------------------------------------
# scry__file exclusions
# ---------------------------------------------------------------------------

_FILE_EXCLUDED_EXTENSIONS = frozenset({
    ".jsonl", ".lock", ".timestamp", ".pyc", ".png", ".jpg", ".jpeg",
    ".webp", ".svg", ".so", ".pyi", ".f90", ".ipynb", ".parquet",
    # JSON files are rarely useful for FTS — package manifests, API
    # responses, and lock files dominate; exclude to control DB size.
    ".json",
})

_FILE_EXCLUDED_PATH_SEGMENTS = frozenset({
    "node_modules", ".venv", ".git", "agent/drivers", "dist", "build", "__pycache__",
    # Ephemeral wake artifacts (system prompts, wakes/) change every session
    # and balloon scry__file without any search value.
    "agent/runtime/wakes",
})

_FILE_EXCLUDED_FILENAMES = frozenset({
    "LICENSE", "COPYING", "NOTICE",
    # Dependency lock files: large, machine-generated, no search value.
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "bun.lockb",
    "Cargo.lock",
    "poetry.lock",
    "Gemfile.lock",
    "composer.lock",
    "pdm.lock",
    "uv.lock",
})

# 128 KB — enough to index any real source file; prevents lock files,
# minified JS, and generated TypeScript declarations from inflating
# the DB. (Was 1 MB; dropped because 74 MB DB corruption correlated
# with unbounded body storage on large symlinked projects.)
_FILE_MAX_BYTES = 128 * 1024   # 128 KB
_FILE_MAX_LINE_CHARS = 10_000


def _should_index_body(path: Path, rel_path: str, body: str) -> bool:
    """Return True if this file's body should be indexed in scry__file."""
    # Extension exclusion
    if path.suffix.lower() in _FILE_EXCLUDED_EXTENSIONS:
        return False
    # Filename exclusion (exact + prefix match for LICENSE.txt etc.)
    stem = path.stem
    if stem in _FILE_EXCLUDED_FILENAMES or path.name in _FILE_EXCLUDED_FILENAMES:
        return False
    # Path-segment exclusion
    norm = rel_path.replace("\\", "/")
    for seg in _FILE_EXCLUDED_PATH_SEGMENTS:
        if norm.startswith(seg + "/") or f"/{seg}/" in norm:
            return False
    # Size cap
    if len(body.encode("utf-8", errors="replace")) > _FILE_MAX_BYTES:
        return False
    # Long-line heuristic
    if any(len(line) > _FILE_MAX_LINE_CHARS for line in body.splitlines()):
        return False
    return True


def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:16]


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
    gi = dirpath / ".gitignore"
    if not gi.is_file():
        return None
    try:
        import pathspec
        return pathspec.PathSpec.from_lines("gitwildmatch", gi.read_text(errors="replace").splitlines())
    except ImportError:
        return None
    except Exception:
        return None


def _is_gitignored(path: Path, gitignore_specs: "dict[Path, Any]") -> bool:
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


def _split_ref(ref: str) -> tuple[str, str]:
    """Split 'target_id#fragment' into (target_id, fragment_or_empty).

    Fragment includes the leading '#', e.g. '#FR3'.
    Returns ('target_id', '') for refs without a fragment.
    """
    if "#" in ref:
        idx = ref.index("#")
        return ref[:idx], ref[idx:]
    return ref, ""


# ---------------------------------------------------------------------------
# Relationship sync (scry__rel)
# ---------------------------------------------------------------------------

def _sync_rel_predicate(
    conn: sqlite3.Connection,
    marker_id: str,
    predicate: str,
    targets: list[str],
) -> list[str]:
    """Replace scry__rel rows for (marker_id, predicate) with the given targets.

    Returns warning messages for self-loops and cycles (depends_on only).
    """
    conn.execute(
        "DELETE FROM scry__rel WHERE from_id = ? AND predicate = ?",
        (marker_id, predicate),
    )
    warnings: list[str] = []
    for target in targets:
        if target == marker_id:
            warnings.append(f"self-loop in {predicate} ignored: {marker_id}")
            continue
        if predicate == "depends_on":
            cycle = conn.execute(
                """
                WITH RECURSIVE reachable(node) AS (
                  SELECT to_id FROM scry__rel WHERE from_id = ? AND predicate = 'depends_on'
                  UNION
                  SELECT r2.to_id FROM scry__rel r2
                  JOIN reachable rc ON r2.from_id = rc.node
                  WHERE r2.predicate = 'depends_on'
                )
                SELECT 1 FROM reachable WHERE node = ? LIMIT 1
                """,
                (target, marker_id),
            ).fetchone()
            if cycle is not None:
                warnings.append(
                    f"cycle in depends_on ignored: {marker_id} -> {target} would form a cycle"
                )
                continue
        conn.execute(
            "INSERT OR IGNORE INTO scry__rel(from_id, to_id, predicate, fragment) VALUES (?, ?, ?, '')",
            (marker_id, target, predicate),
        )
    return warnings


def _sync_relationships(conn: sqlite3.Connection, marker: DocMarker) -> list[str]:
    """Sync scry__rel rows for all relationship fields in the marker."""
    warnings = _sync_rel_predicate(conn, marker.id, "depends_on", marker.depends_on)
    _sync_rel_predicate(conn, marker.id, "implements", marker.implements)
    _sync_rel_predicate(conn, marker.id, "supersedes", marker.supersedes)
    return warnings


# ---------------------------------------------------------------------------
# upsert_doc
# ---------------------------------------------------------------------------

def upsert_doc(conn: sqlite3.Connection, marker: DocMarker, rel_path: str) -> None:
    h = content_hash(marker.raw_body)
    row = conn.execute(
        "SELECT content_hash, current_path FROM scry__doc WHERE id = ?", (marker.id,)
    ).fetchone()
    ephemeral = _is_ephemeral(rel_path)

    if row is not None and row["content_hash"] == h and row["current_path"] == rel_path:
        return

    summary = marker.summary or ""
    kind = marker.kind or "internal"
    status = marker.status or "active"
    weight = marker.weight if marker.weight is not None else 0.5
    # Serialize extras to compact JSON-text; NULL when absent so the column
    # stays sparse and JSON1 predicates short-circuit on missing data.
    extras_json = json.dumps(marker.extras, separators=(",", ":")) if marker.extras else None

    if row is None:
        conn.execute(
            """
            INSERT INTO scry__doc(id, kind, summary, rationale, applies, status, weight,
                                  current_path, content_hash, ephemeral, missing_since, extras,
                                  created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                marker.id, kind, summary, marker.rationale, marker.applies,
                status, weight, rel_path, h, ephemeral, extras_json, _now(), _now(),
            ),
        )
    else:
        conn.execute(
            """
            UPDATE scry__doc SET kind = ?, summary = ?, rationale = ?, applies = ?,
                                 status = ?, weight = ?, current_path = ?, content_hash = ?,
                                 ephemeral = ?, missing_since = NULL, extras = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                kind, summary, marker.rationale, marker.applies,
                status, weight, rel_path, h, ephemeral, extras_json, _now(), marker.id,
            ),
        )

    # Sync tags join table.
    conn.execute("DELETE FROM scry__doc_tag WHERE doc_id = ?", (marker.id,))
    conn.execute("DELETE FROM scry__doc_tag_fts WHERE doc_id = ?", (marker.id,))
    for tag in marker.tags:
        conn.execute(
            "INSERT OR IGNORE INTO scry__doc_tag(doc_id, tag) VALUES (?, ?)",
            (marker.id, tag),
        )
        conn.execute(
            "INSERT INTO scry__doc_tag_fts(tag, doc_id) VALUES (?, ?)",
            (tag, marker.id),
        )

    # Sync seeded_questions join table.
    conn.execute("DELETE FROM scry__doc_seeded_question WHERE doc_id = ?", (marker.id,))
    conn.execute("DELETE FROM scry__doc_seeded_question_fts WHERE doc_id = ?", (marker.id,))
    for ordinal, question in enumerate(marker.seeded_questions):
        conn.execute(
            "INSERT INTO scry__doc_seeded_question(doc_id, ordinal, question) VALUES (?, ?, ?)",
            (marker.id, ordinal, question),
        )
        conn.execute(
            "INSERT INTO scry__doc_seeded_question_fts(question, doc_id) VALUES (?, ?)",
            (question, marker.id),
        )

    # Sync relationships.
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


# ---------------------------------------------------------------------------
# upsert_anchor
# ---------------------------------------------------------------------------

def upsert_anchor(
    conn: sqlite3.Connection,
    marker: AnchorMarker,
    doc_id: str | None,
    rel_path: str,
) -> None:
    """Upsert an @scry.anchor marker.

    marker.name is the full 'name~hash' anchor identifier, stored as `id`.
    doc_id is the FK to the owning doc (nullable — files without a doc marker
    still get their anchors indexed, just without a FK).
    """
    h = content_hash(marker.raw_body)
    row = conn.execute(
        "SELECT content_hash, doc_id FROM scry__anchor WHERE id = ?", (marker.name,)
    ).fetchone()
    if row is not None and row["content_hash"] == h and row["doc_id"] == doc_id:
        return

    if row is None:
        conn.execute(
            """
            INSERT INTO scry__anchor(id, doc_id, description, content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (marker.name, doc_id, marker.description, h, _now(), _now()),
        )
    else:
        conn.execute(
            """
            UPDATE scry__anchor SET doc_id = ?, description = ?, content_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (doc_id, marker.description, h, _now(), marker.name),
        )

    # Sync seeded_questions join table.
    conn.execute("DELETE FROM scry__anchor_seeded_question WHERE anchor_id = ?", (marker.name,))
    for ordinal, question in enumerate(marker.seeded_questions):
        conn.execute(
            "INSERT INTO scry__anchor_seeded_question(anchor_id, ordinal, question) VALUES (?, ?, ?)",
            (marker.name, ordinal, question),
        )


# ---------------------------------------------------------------------------
# upsert_bind
# ---------------------------------------------------------------------------

def upsert_bind(
    conn: sqlite3.Connection,
    marker: BindMarker,
    source_doc_id: str | None,
    rel_path: str,
) -> None:
    """Upsert a @scry.bind marker record.

    Uniqueness key: (source_local_id, target_id, target_fragment).
    Comma-expanded binds share the same source_local_id but have distinct targets.
    """
    target_id, target_fragment = _split_ref(marker.ref)
    h = content_hash(marker.raw_body)
    row = conn.execute(
        """
        SELECT content_hash, source_doc_id FROM scry__bind
        WHERE source_local_id = ? AND target_id = ? AND target_fragment = ?
        """,
        (marker.local_id, target_id, target_fragment),
    ).fetchone()
    if row is not None and row["content_hash"] == h and row["source_doc_id"] == source_doc_id:
        return

    if row is None:
        conn.execute(
            """
            INSERT INTO scry__bind(source_doc_id, source_local_id, target_id, target_fragment,
                                   comment, content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source_doc_id, marker.local_id, target_id, target_fragment,
             marker.comment, h, _now(), _now()),
        )
    else:
        conn.execute(
            """
            UPDATE scry__bind SET source_doc_id = ?, comment = ?, content_hash = ?, updated_at = ?
            WHERE source_local_id = ? AND target_id = ? AND target_fragment = ?
            """,
            (source_doc_id, marker.comment, h, _now(),
             marker.local_id, target_id, target_fragment),
        )


# ---------------------------------------------------------------------------
# upsert_file
# ---------------------------------------------------------------------------

def upsert_file(
    conn: sqlite3.Connection,
    abs_path: Path,
    project_root: Path,
    first_doc_id: str | None,
    body: str,
) -> bool:
    """Upsert a file body into scry__file if it passes exclusion checks.

    Returns True if the row was written (new or updated), False if skipped.
    """
    rel_path = str(abs_path.relative_to(project_root))
    if not _should_index_body(abs_path, rel_path, body):
        return False

    h = _body_hash(body)
    row = conn.execute(
        "SELECT content_hash, doc_id FROM scry__file WHERE path = ?", (rel_path,)
    ).fetchone()
    if row is not None and row["content_hash"] == h and row["doc_id"] == first_doc_id:
        return False

    now = _now()
    if row is None:
        conn.execute(
            """
            INSERT INTO scry__file(path, doc_id, body, content_hash, last_modified)
            VALUES (?, ?, ?, ?, ?)
            """,
            (rel_path, first_doc_id, body, h, now),
        )
    else:
        conn.execute(
            """
            UPDATE scry__file SET doc_id = ?, body = ?, content_hash = ?, last_modified = ?
            WHERE path = ?
            """,
            (first_doc_id, body, h, now, rel_path),
        )
    return True


# ---------------------------------------------------------------------------
# Warning helpers
# ---------------------------------------------------------------------------

def _record_warnings(conn: sqlite3.Connection, parsed: ParseResult, rel_path: str) -> int:
    """Replace prior misplaced_doc warnings for rel_path and emit fresh ones."""
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


# ---------------------------------------------------------------------------
# reindex_file
# ---------------------------------------------------------------------------

def reindex_file(conn: sqlite3.Connection, abs_path: Path, project_root: Path) -> ParseResult:
    """Parse a single file and upsert its markers.

    Associates anchors and binds with the first doc found in the same file
    (or None if the file has no doc marker).  Clears stale anchor/bind rows
    that previously came from this file's docs but no longer appear.
    """
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

    # The first doc in the file owns anchors and binds.
    first_doc_id: str | None = parsed.docs[0].id if parsed.docs else None

    # Index file body (skipped for binary-ish / excluded files).
    upsert_file(conn, abs_path, project_root, first_doc_id, content)

    # Clean stale anchors that were previously owned by this file's doc(s).
    current_doc_ids = {d.id for d in parsed.docs}
    seen_anchor_ids = {m.name for m in parsed.anchors}
    if current_doc_ids:
        placeholders = ",".join("?" * len(current_doc_ids))
        existing_anchors = {
            r["id"]
            for r in conn.execute(
                f"SELECT id FROM scry__anchor WHERE doc_id IN ({placeholders})",
                tuple(current_doc_ids),
            ).fetchall()
        }
        for stale_id in existing_anchors - seen_anchor_ids:
            conn.execute("DELETE FROM scry__anchor WHERE id = ?", (stale_id,))

    for a in parsed.anchors:
        upsert_anchor(conn, a, first_doc_id, rel_path)

    # Clean stale binds for the source doc.
    seen_bind_keys = {(_split_ref(m.ref)[0], _split_ref(m.ref)[1]) for m in parsed.binds}
    if first_doc_id is not None:
        existing_binds = {
            (r["target_id"], r["target_fragment"])
            for r in conn.execute(
                "SELECT target_id, target_fragment FROM scry__bind WHERE source_doc_id = ?",
                (first_doc_id,),
            ).fetchall()
        }
        for stale_tid, stale_frag in existing_binds - seen_bind_keys:
            conn.execute(
                "DELETE FROM scry__bind WHERE source_doc_id = ? AND target_id = ? AND target_fragment = ?",
                (first_doc_id, stale_tid, stale_frag),
            )

    for bind in parsed.binds:
        upsert_bind(conn, bind, first_doc_id, rel_path)

    _record_warnings(conn, parsed, rel_path)
    conn.commit()
    return parsed


# ---------------------------------------------------------------------------
# File/subtree deletion handlers
# ---------------------------------------------------------------------------

def handle_file_deletion(conn: sqlite3.Connection, rel_path: str) -> None:
    """Soft-delete docs; hard-delete anchors/binds/relationships/file for a removed file."""
    now = _now()
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
    if doc_ids:
        placeholders = ",".join("?" * len(doc_ids))
        conn.execute(f"DELETE FROM scry__anchor WHERE doc_id IN ({placeholders})", tuple(doc_ids))
        conn.execute(f"DELETE FROM scry__bind WHERE source_doc_id IN ({placeholders})", tuple(doc_ids))
        for doc_id in doc_ids:
            conn.execute("DELETE FROM scry__rel WHERE from_id = ?", (doc_id,))
    conn.execute("DELETE FROM scry__warning WHERE file_path = ?", (rel_path,))
    # Hard-delete the file body row — it's derivable from disk; no value in orphan.
    conn.execute("DELETE FROM scry__file WHERE path = ?", (rel_path,))
    conn.commit()


def handle_subtree_deletion(conn: sqlite3.Connection, prefix: str) -> None:
    """Soft-delete docs; hard-delete anchors/binds/file-rows for a removed subtree."""
    now = _now()
    doc_ids = [
        r["id"] for r in conn.execute(
            "SELECT id FROM scry__doc WHERE current_path LIKE ?", (prefix + "%",)
        ).fetchall()
    ]
    conn.execute(
        "UPDATE scry__doc SET missing_since = COALESCE(missing_since, ?) WHERE current_path LIKE ?",
        (now, prefix + "%"),
    )
    if doc_ids:
        placeholders = ",".join("?" * len(doc_ids))
        conn.execute(f"DELETE FROM scry__anchor WHERE doc_id IN ({placeholders})", tuple(doc_ids))
        conn.execute(f"DELETE FROM scry__bind WHERE source_doc_id IN ({placeholders})", tuple(doc_ids))
    conn.execute("DELETE FROM scry__warning WHERE file_path LIKE ?", (prefix + "%",))
    conn.execute("DELETE FROM scry__file WHERE path LIKE ?", (prefix + "%",))
    conn.commit()


# ---------------------------------------------------------------------------
# surface
# ---------------------------------------------------------------------------

def surface(
    conn: sqlite3.Connection,
    project_root: Path | None = None,
    force: bool = False,
    path: str | None = None,
) -> dict[str, Any]:
    """Walk the project (or a scoped path), reindex files, then flag/cleanup missing rows.

    Args:
        conn: Open SQLite connection.
        project_root: Project root override (defaults to config value).
        force: If True, hard-deletes records whose files no longer exist
               (within the scope when path is set).
        path: Optional scope — relative to project root.
              None  → full corpus walk (existing behaviour).
              <file> → re-index exactly that one file.
              <dir>  → re-index every file under that directory, recursively.
              Raises ValueError if path does not exist on disk.
    """
    root = project_root or get_project_root()

    # Validate and resolve scoped path.
    scope_is_file: bool | None = None
    abs_scope: Path | None = None
    if path is not None:
        abs_scope = root / path
        if not abs_scope.exists():
            raise ValueError(f"path does not exist: {path!r}")
        scope_is_file = abs_scope.is_file()

    visited_paths: set[str] = set()
    counts = {"files_scanned": 0, "markers_indexed": 0}

    if path is None:
        # Full walk: warnings are derived state — wipe and rebuild from scratch.
        conn.execute("DELETE FROM scry__warning")
        files_iter: Iterable[Path] = _walk_project(root)
    elif scope_is_file:
        # Single file: _record_warnings in reindex_file handles per-file cleanup.
        files_iter = [abs_scope]  # type: ignore[assignment]
    else:
        # Directory subtree.
        assert abs_scope is not None
        files_iter = _walk_project(abs_scope)

    for fp in files_iter:
        rel = str(fp.relative_to(root))
        visited_paths.add(rel)
        counts["files_scanned"] += 1
        parsed = reindex_file(conn, fp, root)
        counts["markers_indexed"] += (
            len(parsed.docs) + len(parsed.anchors) + len(parsed.binds)
        )

    # Flag any DB record whose current_path is not on disk.
    # When path is set, only consider docs within the scope.
    flagged = []
    if path is None:
        candidate_rows = conn.execute(
            "SELECT id, current_path FROM scry__doc WHERE current_path IS NOT NULL"
        ).fetchall()
    elif scope_is_file:
        candidate_rows = conn.execute(
            "SELECT id, current_path FROM scry__doc WHERE current_path = ?",
            (path,),
        ).fetchall()
    else:
        # Directory: match exact path (unlikely) or anything under it.
        candidate_rows = conn.execute(
            "SELECT id, current_path FROM scry__doc "
            "WHERE current_path = ? OR current_path LIKE ?",
            (path, path + "/%"),
        ).fetchall()

    for r in candidate_rows:
        cp = r["current_path"]
        if cp and cp not in visited_paths:
            conn.execute(
                "UPDATE scry__doc SET missing_since = COALESCE(missing_since, ?) WHERE id = ?",
                (_now(), r["id"]),
            )
            flagged.append({"table": "scry__doc", "id": r["id"], "path": cp})

    deleted: list[dict[str, Any]] = []
    if force:
        if path is None:
            force_rows = conn.execute(
                "SELECT id FROM scry__doc WHERE missing_since IS NOT NULL"
            ).fetchall()
        elif scope_is_file:
            force_rows = conn.execute(
                "SELECT id FROM scry__doc WHERE missing_since IS NOT NULL AND current_path = ?",
                (path,),
            ).fetchall()
        else:
            force_rows = conn.execute(
                "SELECT id FROM scry__doc "
                "WHERE missing_since IS NOT NULL AND (current_path = ? OR current_path LIKE ?)",
                (path, path + "/%"),
            ).fetchall()
        for r in force_rows:
            conn.execute("DELETE FROM scry__doc WHERE id = ?", (r["id"],))
            deleted.append({"table": "scry__doc", "id": r["id"]})

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
        "scope": path,
        "files_scanned": counts["files_scanned"],
        "markers_indexed": counts["markers_indexed"],
        "flagged_missing": flagged,
        "force_deleted": deleted,
        "warnings": {"counts": warning_counts, "sample": sample, "hint": "query scry__warning for the full list"},
        "force": force,
    }
