"""doc_relationship inserts with cycle detection (FR28).

Not exposed as an MCP tool — `scry_sql` is read-only and the 5 minted tools
do not cover relationship writes. Validation scripts (`scry_script`) call
this helper when they need to assert/persist edges.
"""
from __future__ import annotations

import sqlite3


def add_relationship(
    conn: sqlite3.Connection,
    from_id: str,
    to_id: str,
    relationship: str = "depends_on",
) -> dict:
    if relationship != "depends_on":
        return {"error": f"unsupported relationship {relationship!r}"}
    if from_id == to_id:
        return {"error": "self-loops are not allowed"}
    # Cycle detection: would inserting (from_id -> to_id) create a path back to from_id?
    # Find all reachable nodes starting from to_id; if from_id is among them, reject.
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
        (to_id, from_id),
    ).fetchone()
    if cycle is not None:
        return {"error": f"cycle detected: {to_id} already reaches {from_id}"}
    try:
        conn.execute(
            "INSERT OR IGNORE INTO doc_relationship(from_id, to_id, relationship) VALUES (?, ?, ?)",
            (from_id, to_id, relationship),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        return {"error": str(e)}
    return {"ok": True, "from_id": from_id, "to_id": to_id, "relationship": relationship}
