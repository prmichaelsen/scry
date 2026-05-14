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


def test_mint_rejects_dotted_bind_prefix(conn):
    out = mint(conn, "bind", "spec.auth")
    assert "error" in out
    assert "must not contain dots" in out["error"]


def test_mint_rejects_undotted_entry_prefix(conn):
    out = mint(conn, "entry", "design")
    assert "error" in out
    assert "must contain a dot" in out["error"]


def test_mint_anchor_format(conn):
    out = mint(conn, "anchor", "auth-check")
    assert re.match(r"^auth-check~[0-9a-f]{8}$", out["id"])


def test_mint_bind_format(conn):
    """bind minting returns a valid {name}~{hash} local-id."""
    out = mint(conn, "bind", "validate-jwt")
    assert "id" in out
    assert re.match(r"^validate-jwt~[0-9a-f]{8}$", out["id"])
    assert "schema" in out
    assert "marker_line" in out["schema"]
    assert "@scry.bind" in out["schema"]["marker_line"]


def test_mint_bind_schema_includes_block_form(conn):
    """Bind schema includes block-form markers."""
    out = mint(conn, "bind", "impl-x")
    schema = out["schema"]
    assert "marker_block_open" in schema
    assert "marker_block_close" in schema
    assert "@scry.bind.end" in schema["marker_block_close"]


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


def test_mint_legacy_impl_kind_rejected(conn):
    """scry-spec v1.0: 'impl' is no longer a valid mint kind (replaced by 'bind')."""
    out = mint(conn, "impl", "validate-jwt")
    assert "error" in out


def test_mint_legacy_test_kind_rejected(conn):
    """scry-spec v1.0: 'test' is no longer a valid mint kind (replaced by 'bind')."""
    out = mint(conn, "test", "jwt-expiry")
    assert "error" in out


def test_valid_kinds_are_v1_only(conn):
    """VALID_KINDS must only contain scry-spec v1.0 kinds."""
    assert "doc" not in VALID_KINDS
    assert "file" not in VALID_KINDS
    assert "impl" not in VALID_KINDS
    assert "test" not in VALID_KINDS
    assert "entry" in VALID_KINDS
    assert "anchor" in VALID_KINDS
    assert "bind" in VALID_KINDS


def test_mint_entry_status_hint_mentions_deprecated(conn):
    """Entry schema should mention 'deprecated' as a baseline status (v1.0)."""
    out = mint(conn, "entry", "design.x")
    status_hint = out["schema"]["fields"]["status"]
    assert "deprecated" in status_hint
