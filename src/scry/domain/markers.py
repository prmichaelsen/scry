"""Marker types, parser adapter, and stripping helpers.

Block markers (`@scry.entry`, `@scry.anchor`) span multiple lines between an
open token and a `.end` close token.  `@scry.bind` is a line or block marker
that declares a relationship from a local source to a target artifact or anchor.

**Parsing is delegated to `scry-parse`** (the scry-spec v1.0 reference parser).
This module adapts scry-parse's output into scry-mcp's local storage types
(`DocMarker`, `AnchorMarker`, `BindMarker`) which carry the `raw_body` field
used for change-detection hashing.

**Stripping** (`strip_markers_from_content`) is implemented locally because
scry-parse does not expose a strip API.  It relies on simple regex scanning
of the open/close sentinels and does not need to parse YAML bodies.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

import yaml
from scry_parse import BASELINE_STATUSES

# ---------------------------------------------------------------------------
# Exported constants
# ---------------------------------------------------------------------------

BLOCK_KINDS: tuple[str, ...] = ("entry", "anchor")

# scry-spec v1.0 baseline kinds (scry-mcp extends with "clarification").
# Unknown kinds are preserved as-is per FR8 — these are only for UI hints.
DOC_KIND_VALUES = (
    # Documentation/Knowledge
    "design", "pattern", "spec", "lesson", "internal",
    # Work Management
    "task", "milestone",
    # Analysis/Outputs
    "report", "audit", "research",
    # Implementation
    "code",
    # ACP extension — preserved as-is (not coerced)
    "clarification",
)

# Sourced from scry-parse (single source of truth for v1.0 baseline statuses).
STATUS_VALUES: tuple[str, ...] = BASELINE_STATUSES


# ---------------------------------------------------------------------------
# Storage dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DocMarker:
    id: str
    kind: str
    summary: str | None = None
    status: str | None = None
    weight: float | None = None
    tags: list[str] = field(default_factory=list)
    rationale: str | None = None
    applies: str | None = None
    seeded_questions: list[str] = field(default_factory=list)
    # Truly-optional spec fields (scry-spec v1.0 FR_OPT1–FR_OPT3)
    # All three are arrays per scry-parse >=1.0.6 (implements/supersedes changed
    # from str to list[str] in 1.0.6 to support multiple targets).
    depends_on: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    raw_body: str = ""
    span: tuple[int, int] = (0, 0)


@dataclass
class AnchorMarker:
    name: str
    description: str | None = None
    seeded_questions: list[str] = field(default_factory=list)
    raw_body: str = ""
    span: tuple[int, int] = (0, 0)


@dataclass
class BindMarker:
    local_id: str
    ref: str
    comment: str | None = None
    raw_body: str = ""


@dataclass
class ParseResult:
    docs: list[DocMarker] = field(default_factory=list)
    anchors: list[AnchorMarker] = field(default_factory=list)
    binds: list[BindMarker] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def content_hash(raw_body: str) -> str:
    return hashlib.sha256(raw_body.encode()).hexdigest()[:16]


def _coerce_list_field(value: Any) -> list[str]:
    """Coerce scry-parse relationship field to list[str].

    scry-parse <=1.0.5 returns str for implements/supersedes; >=1.0.6 returns list[str].
    This shim handles both so scry-mcp works across the version boundary.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    return []


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


# ---------------------------------------------------------------------------
# Parser adapter (delegates to scry-parse)
# ---------------------------------------------------------------------------

def parse_markers(content: str, file: str = "") -> ParseResult:
    """Parse @scry.* markers using scry-parse (scry-spec v1.0).

    Returns a `ParseResult` with `DocMarker` / `AnchorMarker` / `BindMarker`
    instances that include the `raw_body` field used for content-change
    detection hashing.
    """
    from scry_parse import parse_markers as _sp_parse

    sp_result = _sp_parse(content, file=file)
    raw_lines = content.splitlines(keepends=True)

    def _raw_body_from_span(span: tuple[int, int]) -> str:
        """Extract source lines for a 1-indexed inclusive span."""
        start, end = span
        return "".join(raw_lines[start - 1:end])

    docs: list[DocMarker] = []
    for e in sp_result.entries:
        raw = _raw_body_from_span(e.span)
        docs.append(DocMarker(
            id=e.id,
            kind=e.kind,
            summary=_coerce_text(e.summary),
            status=_coerce_text(e.status),
            weight=e.weight,
            tags=list(e.tags) if e.tags else [],
            rationale=_coerce_text(e.rationale),
            applies=_coerce_text(e.applies),
            seeded_questions=list(e.seeded_questions) if e.seeded_questions else [],
            depends_on=list(e.depends_on) if e.depends_on else [],
            implements=_coerce_list_field(e.implements),
            supersedes=_coerce_list_field(e.supersedes),
            raw_body=raw,
            span=e.span,
        ))

    anchors: list[AnchorMarker] = []
    for a in sp_result.anchors:
        raw = _raw_body_from_span(a.span)
        anchors.append(AnchorMarker(
            name=a.name,
            description=_coerce_text(a.description),
            seeded_questions=list(a.seeded_questions) if a.seeded_questions else [],
            raw_body=raw,
            span=a.span,
        ))

    binds: list[BindMarker] = []
    for b in sp_result.bindings:
        # Block form has a span; single-line form has span=None with offset.
        if b.span is not None:
            raw = _raw_body_from_span(b.span)
        else:
            idx = b.offset - 1  # offset is 1-indexed
            raw = raw_lines[idx] if 0 <= idx < len(raw_lines) else ""
        binds.append(BindMarker(
            local_id=b.local_id,
            ref=b.ref,
            comment=b.comment,
            raw_body=raw,
        ))

    return ParseResult(docs=docs, anchors=anchors, binds=binds)


# ---------------------------------------------------------------------------
# Strip infrastructure (local — scry-parse has no strip API)
# ---------------------------------------------------------------------------

_OPEN_RE = re.compile(r"@scry\.(entry|anchor)(?!\.end)\b")
_CLOSE_RE = re.compile(r"@scry\.(entry|anchor)\.end\b")
_BIND_OPEN_RE = re.compile(r"@scry\.bind\b(?!\.end)")
_BIND_END_RE = re.compile(r"@scry\.bind\.end\b")


def _line_spans(content: str) -> list[tuple[int, int, str]]:
    """Return list of (start_offset, end_offset_exclusive, line_text) for each line."""
    out: list[tuple[int, int, str]] = []
    pos = 0
    for line in content.splitlines(keepends=True):
        out.append((pos, pos + len(line), line))
        pos += len(line)
    return out


def _find_blocks(lines: list[tuple[int, int, str]]) -> list[dict]:
    """Find declarative block marker spans (entry, anchor) by sentinel scanning.

    Each block is a dict with: kind, span (start_offset, end_offset).
    Used only by strip_markers_from_content — not for parsing.
    """
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line_text = lines[i][2]
        m = _OPEN_RE.search(line_text)
        if not m:
            i += 1
            continue
        kind = m.group(1)
        j = i + 1
        close_idx = None
        while j < len(lines):
            cm = _CLOSE_RE.search(lines[j][2])
            if cm and cm.group(1) == kind:
                close_idx = j
                break
            j += 1
        if close_idx is None:
            i += 1
            continue
        blocks.append({
            "kind": kind,
            "span": (lines[i][0], lines[close_idx][1]),
        })
        i = close_idx + 1
    return blocks


def _inside_any_span(offset: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= offset < e for s, e in spans)


def _find_bind_spans_for_scrub(
    lines: list[tuple[int, int, str]],
    block_spans: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Locate all @scry.bind line/block spans for stripping purposes."""
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        line_start, line_end, line_text = lines[i]
        if _inside_any_span(line_start, block_spans):
            i += 1
            continue
        m = _BIND_OPEN_RE.search(line_text)
        if not m:
            i += 1
            continue
        # Forward scan.
        j = i + 1
        is_block = False
        while j < len(lines):
            next_start, _next_end, next_text = lines[j]
            if _BIND_END_RE.search(next_text):
                is_block = True
                break
            if _BIND_OPEN_RE.search(next_text) and not _inside_any_span(next_start, block_spans):
                break
            j += 1
        if is_block:
            spans.append((lines[i][0], lines[j][1]))
            i = j + 1
        else:
            spans.append((lines[i][0], lines[i][1]))
            i += 1
    return spans


def strip_markers_from_content(content: str) -> str:
    """Remove every scry marker (block + bind) from content.

    Used by `scry_scrub` to produce a clean branch.
    """
    if "@scry." not in content:
        return content
    lines = _line_spans(content)
    decl_blocks = _find_blocks(lines)
    decl_spans = [b["span"] for b in decl_blocks]
    bind_spans = _find_bind_spans_for_scrub(lines, decl_spans)

    all_spans = decl_spans + bind_spans

    # Remove all lines whose span is fully covered by any marker span.
    keep: list[str] = []
    for s, e, txt in lines:
        if any(bs <= s and e <= be for bs, be in all_spans):
            continue
        keep.append(txt)
    return "".join(keep)
