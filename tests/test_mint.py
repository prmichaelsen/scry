"""scry_mint tests (FR17, FR18, FR19)."""
from __future__ import annotations

import re

from scry.service.mint import mint


def test_mint_doc_returns_id_and_schema(conn):
    out = mint(conn, "doc", "design.auth")
    assert "id" in out
    assert re.match(r"^design\.auth~[0-9a-f]{8}$", out["id"])
    assert "schema" in out
    assert "marker_open" in out["schema"]
    assert "fields" in out["schema"]


def test_mint_doc_no_collision(conn):
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status) VALUES ('design.auth~a1b2c3d4', 'design', 'active')"
    )
    out = mint(conn, "doc", "design.auth")
    assert out["id"] != "design.auth~a1b2c3d4"


def test_mint_rejects_dotted_impl_prefix(conn):
    out = mint(conn, "impl", "spec.auth")
    assert "error" in out
    assert "must not contain dots" in out["error"]


def test_mint_rejects_undotted_doc_prefix(conn):
    out = mint(conn, "doc", "design")
    assert "error" in out
    assert "must contain a dot" in out["error"]


def test_mint_anchor_format(conn):
    out = mint(conn, "anchor", "auth-check")
    assert re.match(r"^auth-check~[0-9a-f]{8}$", out["id"])


def test_mint_unknown_kind(conn):
    out = mint(conn, "thing", "x")
    assert "error" in out
