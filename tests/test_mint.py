"""scry_mint tests (FR17, FR18, FR19) — scry-spec v1.0."""
from __future__ import annotations

import re

from scry.service.mint import mint, VALID_KINDS


def test_mint_entry_returns_id_and_schema(conn):
    out = mint(conn, "entry", "design.auth")
    assert "id" in out
    assert re.match(r"^design\.auth~[0-9a-f]{8}$", out["id"])
    assert "schema" in out
    assert "marker_open" in out["schema"]
    assert "fields" in out["schema"]
    assert "@scry.entry" in out["schema"]["marker_open"]


def test_mint_entry_no_collision(conn):
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status) VALUES ('design.auth~a1b2c3d4', 'design', 'active')"
    )
    out = mint(conn, "entry", "design.auth")
    assert out["id"] != "design.auth~a1b2c3d4"


def test_mint_rejects_dotted_impl_prefix(conn):
    out = mint(conn, "impl", "spec.auth")
    assert "error" in out
    assert "must not contain dots" in out["error"]


def test_mint_rejects_undotted_entry_prefix(conn):
    out = mint(conn, "entry", "design")
    assert "error" in out
    assert "must contain a dot" in out["error"]


def test_mint_anchor_format(conn):
    out = mint(conn, "anchor", "auth-check")
    assert re.match(r"^auth-check~[0-9a-f]{8}$", out["id"])


def test_mint_unknown_kind(conn):
    out = mint(conn, "thing", "x")
    assert "error" in out


def test_mint_legacy_doc_kind_rejected(conn):
    """scry-spec v1.0: 'doc' is no longer a valid mint kind."""
    out = mint(conn, "doc", "design.auth")
    assert "error" in out


def test_mint_legacy_file_kind_rejected(conn):
    """scry-spec v1.0: 'file' is no longer a valid mint kind."""
    out = mint(conn, "file", "file.auth")
    assert "error" in out


def test_valid_kinds_are_v1_only(conn):
    """VALID_KINDS must only contain scry-spec v1.0 kinds."""
    assert "doc" not in VALID_KINDS
    assert "file" not in VALID_KINDS
    assert "entry" in VALID_KINDS
    assert "anchor" in VALID_KINDS
