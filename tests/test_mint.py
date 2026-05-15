"""scry_mint tests (FR17, FR18, FR19) — scry-spec v1.0."""
from __future__ import annotations

import re

from scry.service.mint import mint, VALID_KINDS, _check_collisions


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


# ---------------------------------------------------------------------------
# Collision detection tests (tier-1 / tier-2)
# ---------------------------------------------------------------------------


def test_mint_no_collisions_when_db_empty(conn):
    """No collision keys returned when DB is empty."""
    out = mint(conn, "entry", "design.auth-flow")
    assert "tier1_collisions" not in out
    assert "tier2_neighbors" not in out


def test_mint_tier1_collision_same_prefix(conn):
    """tier1_collisions returned when same prefix~hash already exists."""
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status, summary) "
        "VALUES ('design.auth-flow~a1b2c3d4', 'design', 'active', 'existing auth design')"
    )
    conn.commit()
    out = mint(conn, "entry", "design.auth-flow")
    assert "tier1_collisions" in out
    assert len(out["tier1_collisions"]) == 1
    assert out["tier1_collisions"][0]["id"] == "design.auth-flow~a1b2c3d4"
    assert out["tier1_collisions"][0]["summary"] == "existing auth design"


def test_mint_tier2_neighbor_same_family(conn):
    """tier2_neighbors returned for markers in same kind+first-segment family."""
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status, summary) "
        "VALUES ('design.auth-check~b2c3d4e5', 'design', 'active', 'auth check pattern')"
    )
    conn.commit()
    # prefix "design.auth-flow" → first seg "auth" → family "design.auth%"
    # "design.auth-check~..." is a tier-2 neighbor (different suffix, same family)
    out = mint(conn, "entry", "design.auth-flow")
    assert "tier2_neighbors" in out
    ids = [n["id"] for n in out["tier2_neighbors"]]
    assert "design.auth-check~b2c3d4e5" in ids


def test_mint_tier1_excluded_from_tier2(conn):
    """tier1_collisions and tier2_neighbors are disjoint sets."""
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status, summary) "
        "VALUES ('design.auth-flow~a1b2c3d4', 'design', 'active', 'same prefix')"
    )
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status, summary) "
        "VALUES ('design.auth-check~b2c3d4e5', 'design', 'active', 'family neighbor')"
    )
    conn.commit()
    out = mint(conn, "entry", "design.auth-flow")
    tier1_ids = {c["id"] for c in out.get("tier1_collisions", [])}
    tier2_ids = {n["id"] for n in out.get("tier2_neighbors", [])}
    assert tier1_ids.isdisjoint(tier2_ids), "tier-1 and tier-2 must be disjoint"


def test_mint_bind_no_collision_check(conn):
    """bind minting never returns collision keys (file-scoped, no global check)."""
    out = mint(conn, "bind", "validate-jwt")
    assert "tier1_collisions" not in out
    assert "tier2_neighbors" not in out


def test_mint_anchor_tier1_collision(conn):
    """Collision detection works for anchor kind too."""
    # Insert a doc first so the anchor FK can reference it
    conn.execute(
        "INSERT INTO scry__doc(id, kind, status) VALUES ('task.owner~deadbeef','task','active')"
    )
    conn.execute(
        "INSERT INTO scry__anchor(id, doc_id, description) "
        "VALUES ('auth-check~f1e2d3c4', 'task.owner~deadbeef', 'JWT check point')"
    )
    conn.commit()
    out = mint(conn, "anchor", "auth-check")
    assert "tier1_collisions" in out
    assert out["tier1_collisions"][0]["id"] == "auth-check~f1e2d3c4"


def test_check_collisions_direct_empty(conn):
    """_check_collisions returns empty lists on empty DB."""
    tier1, tier2 = _check_collisions(conn, "entry", "design.auth")
    assert tier1 == []
    assert tier2 == []


def test_check_collisions_bind_returns_empty(conn):
    """_check_collisions always returns ([], []) for bind."""
    tier1, tier2 = _check_collisions(conn, "bind", "impl-x")
    assert tier1 == []
    assert tier2 == []
