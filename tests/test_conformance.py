"""B2 spec-conformance harness for scry-mcp.

Spec: spec.scry-conformance-tests~6ced3644

Three required tests (FR3, FR4, FR5):

  test_baseline_kinds_match_spec        — every vendored kind must be indexable;
                                          no unlisted kinds may appear (FR3)
  test_predicates_match_spec            — every vendored predicate must produce a
                                          scry__rel row; no unlisted predicates (FR4)
  test_pinned_version_matches_installed — PINNED_SCRY_SPEC_VERSION must match the
                                          SCRY_SPEC_VERSION constant in markers.py (FR5)

Bonus tests (FR7):
  test_statuses_match_spec              — every vendored status must appear in at
                                          least one fixture

Enums are VENDORED in tests/conformance/ — NOT read dynamically from the
installed package at test time.  Updating the pin requires updating the
fixtures and txt files atomically (see tests/conformance/BUMPING.md).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scry.domain.markers import SCRY_SPEC_VERSION
from scry.service.migration import run_migrations
from scry.service.surface import surface

CONFORMANCE_DIR = Path(__file__).parent / "conformance"
FIXTURES_DIR = CONFORMANCE_DIR / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_db() -> sqlite3.Connection:
    """In-memory DB with full schema migrations applied."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    run_migrations(conn=c)
    return c


def _read_enum(filename: str) -> list[str]:
    """Read a vendored enum file; return non-empty, non-comment lines."""
    path = CONFORMANCE_DIR / filename
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# ---------------------------------------------------------------------------
# FR5 — PINNED_SCRY_SPEC_VERSION matches markers.SCRY_SPEC_VERSION
# ---------------------------------------------------------------------------

def test_pinned_version_matches_installed():
    """FR5: PINNED_SCRY_SPEC_VERSION must equal markers.SCRY_SPEC_VERSION.

    Fails when scry-mcp implements a new scry-spec version but the pin
    file hasn't been updated.  Fix: follow tests/conformance/BUMPING.md.
    """
    pin_file = CONFORMANCE_DIR / "PINNED_SCRY_SPEC_VERSION"
    pin = pin_file.read_text(encoding="utf-8").strip()
    assert pin == SCRY_SPEC_VERSION, (
        f"PINNED_SCRY_SPEC_VERSION={pin!r} differs from "
        f"markers.SCRY_SPEC_VERSION={SCRY_SPEC_VERSION!r}. "
        "Follow tests/conformance/BUMPING.md to update the pin atomically."
    )


# ---------------------------------------------------------------------------
# FR3 — baseline kinds
# ---------------------------------------------------------------------------

def test_baseline_kinds_match_spec():
    """FR3: every vendored kind must be indexable; no unlisted kinds may appear.

    Surfaces tests/conformance/fixtures/kinds/ into a fresh DB and checks:
    - Forward:       each kind in baseline_kinds.txt has at least one indexed doc.
    - Bidirectional: no indexed doc has a kind outside baseline_kinds.txt.
    """
    kinds = _read_enum("baseline_kinds.txt")
    assert kinds, "baseline_kinds.txt is empty — check the conformance dir"

    conn = _fresh_db()
    surface(conn, project_root=FIXTURES_DIR / "kinds")

    indexed = {
        row["kind"]
        for row in conn.execute("SELECT kind FROM scry__doc").fetchall()
    }

    missing = [k for k in kinds if k not in indexed]
    assert not missing, (
        f"Kinds in baseline_kinds.txt with no indexed fixture: {missing}. "
        "Add tests/conformance/fixtures/kinds/<kind>.md for each missing kind."
    )

    extra = [k for k in indexed if k not in kinds]
    assert not extra, (
        f"Fixture kinds not in baseline_kinds.txt: {extra}. "
        "Add to baseline_kinds.txt or remove the fixture."
    )


# ---------------------------------------------------------------------------
# FR4 — predicates
# ---------------------------------------------------------------------------

def test_predicates_match_spec():
    """FR4: every vendored predicate must produce a scry__rel row; none extra.

    Surfaces tests/conformance/fixtures/predicates/ into a fresh DB and checks:
    - Forward:       each predicate in predicates.txt has at least one scry__rel row.
    - Bidirectional: no scry__rel row has a predicate outside predicates.txt.
    """
    predicates = _read_enum("predicates.txt")
    assert predicates, "predicates.txt is empty — check the conformance dir"

    conn = _fresh_db()
    surface(conn, project_root=FIXTURES_DIR / "predicates")

    indexed = {
        row["predicate"]
        for row in conn.execute(
            "SELECT DISTINCT predicate FROM scry__rel"
        ).fetchall()
    }

    missing = [p for p in predicates if p not in indexed]
    assert not missing, (
        f"Predicates in predicates.txt with no scry__rel row: {missing}. "
        "Add tests/conformance/fixtures/predicates/<predicate>.md exercising "
        "each missing predicate."
    )

    extra = [p for p in indexed if p not in predicates]
    assert not extra, (
        f"scry__rel predicates not in predicates.txt: {extra}. "
        "Add to predicates.txt or update the fixture."
    )


# ---------------------------------------------------------------------------
# FR7 (bonus) — statuses
# ---------------------------------------------------------------------------

def test_statuses_match_spec():
    """FR7 bonus: every vendored status must appear in at least one fixture.

    Surfaces tests/conformance/fixtures/statuses/ and checks that each
    status in statuses.txt has at least one indexed doc.  Unknown statuses
    are valid (scry-mcp preserves unknown values), so the bidirectional
    check is omitted for statuses.
    """
    statuses = _read_enum("statuses.txt")
    assert statuses, "statuses.txt is empty — check the conformance dir"

    conn = _fresh_db()
    surface(conn, project_root=FIXTURES_DIR / "statuses")

    indexed = {
        row["status"]
        for row in conn.execute("SELECT status FROM scry__doc").fetchall()
    }

    missing = [s for s in statuses if s not in indexed]
    assert not missing, (
        f"Statuses in statuses.txt with no indexed fixture: {missing}. "
        "Add tests/conformance/fixtures/statuses/<status>.md for each."
    )
