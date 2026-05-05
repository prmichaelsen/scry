"""Marker parser tests (FR1-FR7)."""
from __future__ import annotations

from scry.domain.markers import (
    parse_markers,
    strip_markers_from_content,
    content_hash,
)
from scry.util.comments import strip_comment_prefix


DOC_HTML = """\
<!-- @scry.doc
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
@scry.doc.end -->
"""

FILE_PYTHON = """\
# @scry.file
# id: file.auth-mid~e5f6a7b8
# kind: middleware
# summary: jwt validator
# status: active
# weight: 0.7
# tags: ["scope:auth"]
# rationale: required
# applies: routes
# seeded_questions: [q1]
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

LINE_MARKERS = """\
# @scry.impl validate-jwt~a1b2c3d4 spec.auth~xyz#FR3
# @scry.test jwt-expiry~b2c3d4e5 spec.auth~xyz#UT1
"""


def test_parse_doc_block_extracts_all_fields():
    r = parse_markers(DOC_HTML)
    assert len(r.docs) == 1
    d = r.docs[0]
    assert d.id == "design.auth-flow~a1b2c3d4"
    assert d.kind == "design"
    assert d.status == "active"
    assert d.weight == 0.85
    assert "JWT auth middleware" in d.summary
    assert "Missing causes auth bypass" in d.rationale
    assert d.applies == "modifying auth"
    assert "How does refresh work" in d.seeded_questions


def test_parse_file_block_freeform_kind():
    r = parse_markers(FILE_PYTHON)
    assert len(r.files) == 1
    f = r.files[0]
    assert f.id == "file.auth-mid~e5f6a7b8"
    assert f.kind == "middleware"


def test_parse_anchor_block():
    r = parse_markers(ANCHOR_HTML)
    assert len(r.anchors) == 1
    a = r.anchors[0]
    assert a.name == "auth-check~f1e2d3c4"
    assert "JWT validation point" in a.description
    assert "expired" in a.seeded_questions


def test_parse_line_markers():
    r = parse_markers(LINE_MARKERS)
    assert len(r.impls) == 1
    assert r.impls[0].id == "validate-jwt~a1b2c3d4"
    assert r.impls[0].ref == "spec.auth~xyz#FR3"
    assert len(r.tests) == 1
    assert r.tests[0].id == "jwt-expiry~b2c3d4e5"
    assert r.tests[0].ref == "spec.auth~xyz#UT1"


def test_positional_exclusion_skips_impl_inside_doc():
    content = (
        DOC_HTML.replace("@scry.doc.end", "@scry.impl foo~12345678 spec.x~abc#FR1\n@scry.doc.end")
    )
    r = parse_markers(content)
    assert len(r.impls) == 0
    assert len(r.docs) == 1


def test_includes_impl_after_closed_doc():
    content = DOC_HTML + "\n# @scry.impl bar~b2345678 spec.x~abc#FR2\n"
    r = parse_markers(content)
    assert len(r.impls) == 1
    assert r.impls[0].id == "bar~b2345678"


def test_strip_comment_prefix_jsdoc():
    body = " * id: foo\n * key: bar\n"
    cleaned = strip_comment_prefix(body)
    assert "id: foo" in cleaned
    assert " * " not in cleaned


def test_strip_comment_prefix_python():
    body = "# id: foo\n# key: bar\n"
    cleaned = strip_comment_prefix(body)
    assert cleaned.startswith("id: foo")


def test_strip_markers_from_content_removes_block_and_line():
    src = DOC_HTML + LINE_MARKERS
    out = strip_markers_from_content(src)
    assert "@scry." not in out


def test_content_hash_stable_and_truncated():
    h = content_hash("hello world")
    assert len(h) == 16
    assert h == content_hash("hello world")
    assert h != content_hash("hello world!")
