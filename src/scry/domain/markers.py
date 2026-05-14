"""Marker parsing: dataclasses, regex, parser, and stripping helpers.

Block markers (`@scry.entry`, `@scry.anchor`) span multiple lines between an
open token and a `.end` close token. The open and close tokens may be embedded
inside any host-language comment syntax — comment prefixes are inferred from
the YAML body via :func:`strip_comment_prefix`.

`@scry.entry` is the canonical block marker for knowledge-graph entries
(designs, specs, tasks, milestones, patterns, lessons, etc.). `@scry.anchor`
marks named code locations. Legacy `@scry.doc` and `@scry.file` markers are
no longer recognized per scry-spec v1.0.

`@scry.bind` (FR2) declares a relationship from a local source to a target
artifact or anchor. Two forms:

  Single-line: ``@scry.bind {local-id} {ref} [{comment}]``
  Block:       ``@scry.bind {local-id} {ref}``
               ``{multi-line free-form comment}``
               ``@scry.bind.end``

Positional exclusion (FR3): bind markers whose offset falls inside a
declarative block marker span are excluded from indexing.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import yaml

from scry.util.comments import strip_comment_prefix

BLOCK_KINDS: tuple[str, ...] = ("entry", "anchor")

# scry-spec v1.0 baseline kinds.  Custom kinds (e.g. "clarification") are
# preserved as-is per FR8 — never silently rewrite.
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

# scry-spec v1.0 baseline status values.  Custom statuses are preserved
# as-is per FR9 — never silently rewrite.
STATUS_VALUES = ("draft", "active", "deprecated")

_OPEN_RE = re.compile(r"@scry\.(entry|anchor)(?!\.end)\b([^\n]*)")
_CLOSE_RE = re.compile(r"@scry\.(entry|anchor)\.end\b")
_BIND_OPEN_RE = re.compile(r"@scry\.bind\s+(\S+)\s+(\S+)(.*)?")
_BIND_END_RE = re.compile(r"@scry\.bind\.end\b")


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
class AnchorMarker:
    name: str
    description: str | None = None
    seeded_questions: str | None = None
    raw_body: str = ""
    span: tuple[int, int] = (0, 0)


@dataclass
class BindMarker:
    """A @scry.bind marker (FR2): relates a local source to a target ref."""
    local_id: str
    ref: str
    comment: str | None = None
    raw_body: str = ""
    offset: int = 0


@dataclass
class ParseResult:
    docs: list[DocMarker] = field(default_factory=list)
    anchors: list[AnchorMarker] = field(default_factory=list)
    binds: list[BindMarker] = field(default_factory=list)


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
    """Find declarative block marker spans (entry, anchor).

    Each block is a dict with: kind, name (anchor only), body_text,
    span (start_offset, end_offset).
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


def _expand_bind_refs(ref: str) -> list[str]:
    """Expand comma-separated loose anchors in a binding ref (FR2).

    Only applies to artifact-refs (contains ``.`` before ``~``) with a
    ``#{anchor1},{anchor2},...`` suffix. Strict anchor-ids and single-anchor
    refs are returned as-is.

    Example: ``spec.auth~xyz#FR1,FR2,FR3`` → three refs, one per anchor.
    """
    hash_idx = ref.find('#')
    if hash_idx < 0:
        return [ref]
    artifact_part = ref[:hash_idx]
    anchor_part = ref[hash_idx + 1:]
    # Artifact-ref: must have a dot before the tilde (disambiguation rule FR2).
    tilde_idx = artifact_part.find('~')
    if tilde_idx < 0 or '.' not in artifact_part[:tilde_idx]:
        # Strict anchor-id — no comma expansion.
        return [ref]
    anchors = [a.strip() for a in anchor_part.split(',') if a.strip()]
    if len(anchors) <= 1:
        return [ref]
    return [f"{artifact_part}#{a}" for a in anchors]


def _find_binds(
    lines: list[tuple[int, int, str]],
    block_spans: list[tuple[int, int]],
) -> list[BindMarker]:
    """Parse @scry.bind markers per FR2, applying positional exclusion (FR3).

    Implements the deterministic forward-scan disambiguation algorithm:
    - Scan forward from each candidate opening line.
    - If @scry.bind.end is found first → block form.
    - If another @scry.bind opening or EOF is found first → single-line form.
    """
    binds: list[BindMarker] = []
    i = 0
    while i < len(lines):
        line_start, line_end, line_text = lines[i]

        # FR3: positional exclusion — skip bind markers inside declarative spans.
        if _inside_any_span(line_start, block_spans):
            i += 1
            continue

        m = _BIND_OPEN_RE.search(line_text)
        if not m:
            i += 1
            continue

        local_id = m.group(1)
        ref = m.group(2)
        trailing = m.group(3).strip() if m.group(3) else None
        trailing = trailing or None  # normalize empty string → None

        # Deterministic forward scan to determine form.
        j = i + 1
        is_block = False
        body_line_texts: list[str] = []

        while j < len(lines):
            next_start, _next_end, next_text = lines[j]
            if _BIND_END_RE.search(next_text):
                is_block = True
                break
            # If we hit another (non-excluded) bind opening, prev was single-line.
            if _BIND_OPEN_RE.search(next_text) and not _inside_any_span(next_start, block_spans):
                break
            body_line_texts.append(next_text)
            j += 1
        # j is now at: .end line (block), next bind (single-line), or past-EOF (single-line)

        if is_block:
            # FR2 mutual exclusion: inline comment + block body is an error.
            # Skip the malformed binding silently per spec discretion.
            if trailing:
                i = j + 1
                continue
            # Extract and prefix-strip the block body.
            raw_block_lines = [lines[k][2] for k in range(i, j + 1)]
            raw_body = "".join(raw_block_lines)
            body_text = "".join(body_line_texts)
            stripped_body = strip_comment_prefix(body_text).strip() if body_text.strip() else None
            comment = stripped_body if stripped_body else None
            for expanded_ref in _expand_bind_refs(ref):
                binds.append(BindMarker(
                    local_id=local_id,
                    ref=expanded_ref,
                    comment=comment,
                    raw_body=raw_body,
                    offset=line_start,
                ))
            i = j + 1
        else:
            # Single-line form.
            for expanded_ref in _expand_bind_refs(ref):
                binds.append(BindMarker(
                    local_id=local_id,
                    ref=expanded_ref,
                    comment=trailing,
                    raw_body=line_text,
                    offset=line_start,
                ))
            i += 1

    return binds


def _parse_yaml_body(raw_body: str) -> dict[str, Any]:
    cleaned = strip_comment_prefix(raw_body)
    # Strip any bind markers that landed inside the body.  They are excluded
    # from the marker index by FR3; here we also drop them from the YAML
    # text so they don't break safe_load.
    cleaned = _BIND_OPEN_RE.sub("", cleaned)
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

        if kind == "entry":
            # FR8: preserve original kind value as-is — NEVER silently rewrite.
            doc_kind = _coerce_text(data.get("kind")) or "internal"
            result.docs.append(DocMarker(kind=doc_kind, **common))

    # @scry.bind markers — apply positional exclusion (FR3).
    result.binds = _find_binds(lines, block_spans)

    return result


def _inside_any_span(offset: int, spans: Iterable[tuple[int, int]]) -> bool:
    for s, e in spans:
        if s <= offset < e:
            return True
    return False


def _find_bind_spans_for_scrub(
    lines: list[tuple[int, int, str]],
    block_spans: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Return (start_offset, end_offset) spans for all bind markers (for scrubbing).

    Single-line binds → span covers just that line.
    Block-form binds  → span covers from open line to .end line inclusive.
    Respects positional exclusion (FR3).
    """
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
