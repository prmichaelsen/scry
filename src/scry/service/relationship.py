"""scry__rel inserts with cycle detection for depends_on (FR28).

Not exposed as an MCP tool — `scry_sql` is read-only and the 5 minted tools
do not cover relationship writes. Validation scripts (`scry_script`) call
this helper when they need to assert/persist edges.
"""
from __future__ import annotations

import sqlite3

SUPPORTED_PREDICATES = {"depends_on", "implements", "supersedes"}


def add_relationship(
    conn: sqlite3.Connection,
    from_id: str,
    to_id: str,
    relationship: str = "depends_on",
) -> dict:
    if relationship not in SUPPORTED_PREDICATES:
        return {"error": f"unsupported relationship {relationship!r}; use one of {sorted(SUPPORTED_PREDICATES)}"}
    if from_id == to_id:
        return {"error": "self-loops are not allowed"}

    # Cycle detection only applies to depends_on (implements/supersedes are acyclic by semantics).
    if relationship == "depends_on":
        cycle = conn.execute(
            """
            WITH RECURSIVE reachable(node) AS (
              SELECT to_id FROM scry__rel WHERE from_id = ? AND predicate = 'depends_on'
              UNION
              SELECT sr.to_id FROM scry__rel sr
              JOIN reachable r ON sr.from_id = r.node
              WHERE sr.predicate = 'depends_on'
            )
            SELECT 1 FROM reachable WHERE node = ? LIMIT 1
            """,
            (to_id, from_id),
        ).fetchone()
        if cycle is not None:
            return {"error": f"cycle detected: {to_id} already reaches {from_id}"}

    try:
        conn.execute(
            "INSERT OR IGNORE INTO scry__rel(from_id, to_id, predicate) VALUES (?, ?, ?)",
            (from_id, to_id, relationship),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        return {"error": str(e)}
    return {"ok": True, "from_id": from_id, "to_id": to_id, "relationship": relationship}
