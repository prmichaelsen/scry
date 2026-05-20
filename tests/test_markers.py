"""Marker parser tests (FR1-FR7) — scry-spec v1.0."""
from __future__ import annotations

from scry.domain.markers import (
    parse_markers,
    strip_markers_from_content,
    content_hash,
    DOC_KIND_VALUES,
    STATUS_VALUES,
)
from scry.util.comments import strip_comment_prefix


ENTRY_HTML = """\
<!-- @scry.entry
id: design.auth-flow~a1b2c3d4
kind: design
summary: >
  JWT auth middleware
status: active
weight: 0.85
tags: ["scope:auth"]
rationale: >
  Missing causes auth bypass
applies: modifying auth
seeded_questions:
  - How does refresh work?
@scry.entry.end -->
"""

# Legacy markers — must NOT be parsed per scry-spec v1.0
LEGACY_DOC_HTML = """\
<!-- @scry.doc
id: design.auth-flow~a1b2c3d4
kind: design
summary: JWT auth middleware
@scry.doc.end -->
"""

LEGACY_FILE_PYTHON = """\
# @scry.file
# id: file.auth-mid~e5f6a7b8
# kind: middleware
# summary: jwt validator
# @scry.file.end
"""

ANCHOR_HTML = """\
<!-- @scry.anchor auth-check~f1e2d3c4
description: >
  JWT validation point
seeded_questions:
  - What if expired?
@scry.anchor.end -->
"""

BIND_SINGLE_LINE = """\
# @scry.bind validate-jwt~a1b2c3d4 spec.auth~xyz#FR3
# @scry.bind jwt-expiry~b2c3d4e5 spec.auth~xyz#UT1 tests token expiry
"""

BIND_WITH_COMMENT = """\
# @scry.bind validate-jwt~a1b2c3d4 spec.auth~xyz#FR3 partial impl, OAuth pending
"""

BIND_BLOCK = """\
# @scry.bind validate-jwt~a1b2c3d4 spec.auth~xyz#FR3
# Partial implementation. Currently handles:
#   - JWT signature validation
#   - Token expiry checks
# @scry.bind.end
"""


def test_parse_entry_block_extracts_all_fields():
    r = parse_markers(ENTRY_HTML)
    assert len(r.docs) == 1
    d = r.docs[0]
    assert d.id == "design.auth-flow~a1b2c3d4"
    assert d.kind == "design"
    assert d.status == "active"
    assert d.weight == 0.85
    assert "JWT auth middleware" in d.summary
    assert "Missing causes auth bypass" in d.rationale
    assert d.applies == "modifying auth"
    assert any("How does refresh work" in q for q in d.seeded_questions)


def test_legacy_doc_marker_not_parsed():
    """scry-spec v1.0: @scry.doc is no longer recognized."""
    r = parse_markers(LEGACY_DOC_HTML)
    assert len(r.docs) == 0


def test_legacy_file_marker_not_parsed():
    """scry-spec v1.0: @scry.file is no longer recognized."""
    r = parse_markers(LEGACY_FILE_PYTHON)
    assert len(r.docs) == 0


def test_parse_anchor_block():
    r = parse_markers(ANCHOR_HTML)
    assert len(r.anchors) == 1
    a = r.anchors[0]
    assert a.name == "auth-check~f1e2d3c4"
    assert "JWT validation point" in a.description
    assert any("expired" in q for q in a.seeded_questions)


# ---------------------------------------------------------------------------
# @scry.bind tests (FR2, FR3)
# ---------------------------------------------------------------------------

def test_parse_bind_single_line_no_comment():
    r = parse_markers("# @scry.bind validate-jwt~a1b2c3d4 spec.auth~xyz#FR3\n")
    assert len(r.binds) == 1
    b = r.binds[0]
    assert b.local_id == "validate-jwt~a1b2c3d4"
    assert b.ref == "spec.auth~xyz#FR3"
    assert b.comment is None


def test_parse_bind_single_line_with_comment():
    r = parse_markers(BIND_WITH_COMMENT)
    assert len(r.binds) == 1
    b = r.binds[0]
    assert b.local_id == "validate-jwt~a1b2c3d4"
    assert b.ref == "spec.auth~xyz#FR3"
    assert b.comment == "partial impl, OAuth pending"


def test_parse_bind_multiple_single_line():
    r = parse_markers(BIND_SINGLE_LINE)
    assert len(r.binds) == 2
    assert r.binds[0].local_id == "validate-jwt~a1b2c3d4"
    assert r.binds[0].ref == "spec.auth~xyz#FR3"
    assert r.binds[0].comment is None
    assert r.binds[1].local_id == "jwt-expiry~b2c3d4e5"
    assert r.binds[1].ref == "spec.auth~xyz#UT1"
    assert r.binds[1].comment == "tests token expiry"


def test_parse_bind_block_form():
    """FR2: block form captures multi-line body as comment."""
    r = parse_markers(BIND_BLOCK)
    assert len(r.binds) == 1
    b = r.binds[0]
    assert b.local_id == "validate-jwt~a1b2c3d4"
    assert b.ref == "spec.auth~xyz#FR3"
    assert b.comment is not None
    assert "Partial implementation" in b.comment
    assert "JWT signature validation" in b.comment
    assert "Token expiry checks" in b.comment


def test_parse_bind_block_form_mutual_exclusion():
    """FR2: block form with inline comment — spec says MAY accept-and-discard or reject.

    scry-parse chooses accept-and-discard: treats it as block form, uses the
    inline comment from the open line, ignores the block body.  Both behaviors
    are spec-conformant (the MUST NOT is against producing TWO records, not one).
    """
    content = (
        "# @scry.bind validate-jwt~a1b2c3d4 spec.auth~xyz#FR3 inline comment here\n"
        "# body line\n"
        "# @scry.bind.end\n"
    )
    r = parse_markers(content)
    # scry-parse (accept-and-discard): one binding, comment from open line
    assert len(r.binds) == 1
    assert r.binds[0].local_id == "validate-jwt~a1b2c3d4"
    assert r.binds[0].ref == "spec.auth~xyz#FR3"
    assert r.binds[0].comment == "inline comment here"


def test_positional_exclusion_skips_bind_inside_entry():
    """FR3: bind markers inside declarative blocks are excluded."""
    content = (
        ENTRY_HTML.replace(
            "@scry.entry.end",
            "# @scry.bind foo~12345678 spec.x~abc#FR1\n@scry.entry.end",
        )
    )
    r = parse_markers(content)
    assert len(r.binds) == 0
    assert len(r.docs) == 1


def test_includes_bind_after_closed_entry():
    content = ENTRY_HTML + "\n# @scry.bind bar~b2345678 spec.x~abc#FR2\n"
    r = parse_markers(content)
    assert len(r.binds) == 1
    assert r.binds[0].local_id == "bar~b2345678"


def test_doc_kind_values_v1_baseline():
    """v1.0 baseline kinds include lesson, report, audit, research, code."""
    for kind in ("design", "pattern", "spec", "lesson", "internal",
                 "task", "milestone", "report", "audit", "research", "code"):
        assert kind in DOC_KIND_VALUES, f"{kind!r} missing from DOC_KIND_VALUES"


def test_status_values_v1_baseline():
    """v1.0 baseline statuses are draft, active, deprecated."""
    assert "draft" in STATUS_VALUES
    assert "active" in STATUS_VALUES
    assert "deprecated" in STATUS_VALUES
    # old values should NOT be in the baseline
    assert "approved" not in STATUS_VALUES
    assert "stale" not in STATUS_VALUES
    assert "complete" not in STATUS_VALUES


def test_entry_unknown_kind_preserved_as_is():
    """FR8: unknown kinds MUST be preserved as-is, not coerced to 'internal'."""
    content = """\
<!-- @scry.entry
id: misc.thing~a1b2c3d4
kind: unknownkind
summary: test
status: active
@scry.entry.end -->
"""
    r = parse_markers(content)
    assert len(r.docs) == 1
    assert r.docs[0].kind == "unknownkind"


def test_entry_custom_status_preserved_as_is():
    """FR9: custom status values MUST be preserved as-is."""
    content = """\
<!-- @scry.entry
id: task.thing~a1b2c3d4
kind: task
summary: test
status: completed
@scry.entry.end -->
"""
    r = parse_markers(content)
    assert len(r.docs) == 1
    assert r.docs[0].status == "completed"


def test_entry_lesson_kind_accepted():
    content = """\
<!-- @scry.entry
id: lesson.thing~a1b2c3d4
kind: lesson
summary: learned something
status: active
@scry.entry.end -->
"""
    r = parse_markers(content)
    assert len(r.docs) == 1
    assert r.docs[0].kind == "lesson"


def test_strip_comment_prefix_jsdoc():
    body = " * id: foo\n * key: bar\n"
    cleaned = strip_comment_prefix(body)
    assert "id: foo" in cleaned
    assert " * " not in cleaned


def test_strip_comment_prefix_python():
    body = "# id: foo\n# key: bar\n"
    cleaned = strip_comment_prefix(body)
    assert cleaned.startswith("id: foo")


def test_strip_markers_from_content_removes_block_and_bind():
    src = ENTRY_HTML + BIND_SINGLE_LINE
    out = strip_markers_from_content(src)
    assert "@scry." not in out


def test_strip_markers_from_content_removes_bind_block():
    src = BIND_BLOCK + "some code\n"
    out = strip_markers_from_content(src)
    assert "@scry." not in out
    assert "some code" in out


def test_content_hash_stable_and_truncated():
    h = content_hash("hello world")
    assert len(h) == 16
    assert h == content_hash("hello world")
    assert h != content_hash("hello world!")


# ---------------------------------------------------------------------------
# extras field (scry-spec FR4.B, v1.1.0)
# ---------------------------------------------------------------------------

ENTRY_WITH_EXTRAS = """\
<!-- @scry.entry
id: design.cost-snap~aabbccdd
kind: design
summary: cost snapshot doc
extras:
  cost_usd: 1.25
  vendor: openai
  active: true
  retries: 3
  note: null
@scry.entry.end -->
"""

ENTRY_WITHOUT_EXTRAS = """\
<!-- @scry.entry
id: design.no-extras~bbccddee
kind: design
summary: nothing extra here
@scry.entry.end -->
"""


def test_parser_adapter_propagates_extras():
    r = parse_markers(ENTRY_WITH_EXTRAS, file="x.md")
    assert len(r.docs) == 1
    e = r.docs[0]
    assert e.extras == {
        "cost_usd": 1.25,
        "vendor": "openai",
        "active": True,
        "retries": 3,
        "note": None,
    }


def test_parser_adapter_empty_extras_is_empty_dict():
    r = parse_markers(ENTRY_WITHOUT_EXTRAS, file="x.md")
    assert len(r.docs) == 1
    e = r.docs[0]
    assert e.extras == {}
