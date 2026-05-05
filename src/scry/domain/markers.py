"""Marker parsing: dataclasses, regex, parser, and stripping helpers.

Block markers (`@scry.doc`, `@scry.file`, `@scry.anchor`) span multiple lines
between an open token and a `.end` close token. The open and close tokens may
be embedded inside any host-language comment syntax — comment prefixes are
inferred from the YAML body via :func:`strip_comment_prefix`.

Line markers (`@scry.impl`, `@scry.test`) are single-line and follow the form
``@scry.<kind> <id> <ref>``.

Positional exclusion (FR7): line markers whose start offset falls inside a
block marker's open/close span are dropped — they are treated as text inside
a doc body, not real markers.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import yaml

from scry.util.comments import strip_comment_prefix

BLOCK_KINDS: tuple[str, ...] = ("doc", "file", "anchor")
LINE_KINDS: tuple[str, ...] = ("impl", "test")

DOC_KIND_VALUES = ("design", "spec", "task", "milestone", "clarification", "pattern", "internal")
STATUS_VALUES = ("draft", "active", "approved", "stale", "complete")

_OPEN_RE = re.compile(r"@scry\.(doc|file|anchor)(?!\.end)\b([^\n]*)")
_CLOSE_RE = re.compile(r"@scry\.(doc|file|anchor)\.end\b")
_LINE_RE = re.compile(r"@scry\.(impl|test)\s+(\S+)\s+(\S+)")


@dataclass
class DocMarker:
    id: str
    kind: str
    summary: str | None = None
    status: str | None = None
    weight: float | None = None
    tags: str | None = None
    rationale: str | None = None
    applies: str | None = None
    seeded_questions: str | None = None
    raw_body: str = ""
    span: tuple[int, int] = (0, 0)


@dataclass
class FileMarker:
    id: str
    kind: str | None = None
    summary: str | None = None
    status: str | None = None
    weight: float | None = None
    tags: str | None = None
    rationale: str | None = None
    applies: str | None = None
    seeded_questions: str | None = None
    raw_body: str = ""
    span: tuple[int, int] = (0, 0)


@dataclass
class AnchorMarker:
    name: str
    description: str | None = None
    seeded_questions: str | None = None
    raw_body: str = ""
    span: tuple[int, int] = (0, 0)


@dataclass
class ImplMarker:
    id: str
    ref: str
    raw_body: str = ""
    offset: int = 0


@dataclass
class TestMarker:
    id: str
    ref: str
    raw_body: str = ""
    offset: int = 0


@dataclass
class ParseResult:
    docs: list[DocMarker] = field(default_factory=list)
    files: list[FileMarker] = field(default_factory=list)
    anchors: list[AnchorMarker] = field(default_factory=list)
    impls: list[ImplMarker] = field(default_factory=list)
    tests: list[TestMarker] = field(default_factory=list)


def content_hash(raw_body: str) -> str:
    return hashlib.sha256(raw_body.encode()).hexdigest()[:16]


def _line_spans(content: str) -> list[tuple[int, int, str]]:
    """Return list of (start_offset, end_offset_exclusive, line_text) for each line."""
    out: list[tuple[int, int, str]] = []
    pos = 0
    for line in content.splitlines(keepends=True):
        out.append((pos, pos + len(line), line))
        pos += len(line)
    return out


def _find_blocks(lines: list[tuple[int, int, str]]) -> list[dict]:
    """Find block marker spans. Each block is a dict with kind, name (anchor only),
    body_text, span (start_offset, end_offset)."""
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line_text = lines[i][2]
        m = _OPEN_RE.search(line_text)
        if not m:
            i += 1
            continue
        kind = m.group(1)
        rest = m.group(2)
        # Find matching close on a subsequent line.
        j = i + 1
        close_idx = None
        while j < len(lines):
            cm = _CLOSE_RE.search(lines[j][2])
            if cm and cm.group(1) == kind:
                close_idx = j
                break
            j += 1
        if close_idx is None:
            # Unterminated block — skip the open.
            i += 1
            continue
        # Build raw body from lines (i+1 .. close_idx-1) without the open/close lines.
        body_lines = [lines[k][2] for k in range(i + 1, close_idx)]
        raw_body = "".join(body_lines).rstrip("\n")
        anchor_name: str | None = None
        if kind == "anchor":
            # Open line tail expected: " name~hash" possibly followed by other tokens.
            anchor_name = rest.strip().split()[0] if rest.strip() else None
        blocks.append({
            "kind": kind,
            "name": anchor_name,
            "raw_body": raw_body,
            "span": (lines[i][0], lines[close_idx][1]),
        })
        i = close_idx + 1
    return blocks


def _parse_yaml_body(raw_body: str) -> dict[str, Any]:
    cleaned = strip_comment_prefix(raw_body)
    # Strip any line markers that landed inside the body. They are excluded
    # from the marker index by FR7; here we also drop them from the YAML
    # text so they don't break safe_load.
    cleaned = _LINE_RE.sub("", cleaned)
    try:
        data = yaml.safe_load(cleaned) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        # Serialize lists as YAML flow style (e.g. tags, seeded_questions).
        return yaml.safe_dump(list(value), default_flow_style=True).strip()
    return str(value)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_markers(content: str) -> ParseResult:
    """Parse all scry markers from a file's content."""
    result = ParseResult()
    if "@scry." not in content:
        return result

    lines = _line_spans(content)
    blocks = _find_blocks(lines)
    block_spans = [b["span"] for b in blocks]

    for b in blocks:
        kind = b["kind"]
        raw = b["raw_body"]
        span = b["span"]
        if kind == "anchor":
            data = _parse_yaml_body(raw)
            name = b["name"]
            if not name:
                continue
            result.anchors.append(AnchorMarker(
                name=name,
                description=_coerce_text(data.get("description")),
                seeded_questions=_coerce_text(data.get("seeded_questions")),
                raw_body=raw,
                span=span,
            ))
            continue

        data = _parse_yaml_body(raw)
        marker_id = data.get("id")
        if not isinstance(marker_id, str) or not marker_id:
            continue

        common = dict(
            id=marker_id,
            summary=_coerce_text(data.get("summary")),
            status=_coerce_text(data.get("status")),
            weight=_coerce_float(data.get("weight")),
            tags=_coerce_text(data.get("tags")),
            rationale=_coerce_text(data.get("rationale")),
            applies=_coerce_text(data.get("applies")),
            seeded_questions=_coerce_text(data.get("seeded_questions")),
            raw_body=raw,
            span=span,
        )

        if kind == "doc":
            doc_kind = _coerce_text(data.get("kind")) or "internal"
            if doc_kind not in DOC_KIND_VALUES:
                doc_kind = "internal"
            result.docs.append(DocMarker(kind=doc_kind, **common))
        elif kind == "file":
            file_kind = _coerce_text(data.get("kind"))
            result.files.append(FileMarker(kind=file_kind, **common))

    # Line markers — apply positional exclusion.
    for m in _LINE_RE.finditer(content):
        kind, ident, ref = m.group(1), m.group(2), m.group(3)
        offset = m.start()
        if _inside_any_span(offset, block_spans):
            continue
        raw = m.group(0)
        if kind == "impl":
            result.impls.append(ImplMarker(id=ident, ref=ref, raw_body=raw, offset=offset))
        else:
            result.tests.append(TestMarker(id=ident, ref=ref, raw_body=raw, offset=offset))

    return result


def _inside_any_span(offset: int, spans: Iterable[tuple[int, int]]) -> bool:
    for s, e in spans:
        if s <= offset < e:
            return True
    return False


def strip_markers_from_content(content: str) -> str:
    """Remove every scry marker (block + line) from content.

    Used by `scry_scrub` to produce a clean branch.
    """
    if "@scry." not in content:
        return content
    lines = _line_spans(content)
    blocks = _find_blocks(lines)
    spans = [b["span"] for b in blocks]
    # Remove blocks line-by-line by deleting any line whose span overlaps a block.
    keep: list[str] = []
    for s, e, txt in lines:
        if any(bs <= s and e <= be for bs, be in spans):
            continue
        keep.append(txt)
    out = "".join(keep)
    # Strip any remaining line markers.
    out = _LINE_RE.sub("", out)
    return out
