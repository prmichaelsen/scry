"""Comment-prefix stripping via context inference (FR6).

Algorithm:
  1. Scan body lines for the first one whose non-key portion is purely
     whitespace + comment characters (`# / * -`).
  2. That portion is the inferred prefix.
  3. Strip the prefix from every line that starts with it; lines that
     don't (and aren't blank) are preserved as-is so YAML parsing can
     still handle indented continuations.
"""
from __future__ import annotations

import re

_KEY_RE = re.compile(r"^(.*?)([A-Za-z_][A-Za-z0-9_\-]*\s*:)")
_PREFIX_VALID = re.compile(r"^[\s#/*\->]*$")


def strip_comment_prefix(body: str) -> str:
    lines = body.splitlines()
    prefix = _infer_prefix(lines)
    if not prefix:
        return body
    out: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            out.append(line[len(prefix):])
        elif line.strip() == "":
            out.append("")
        else:
            stripped_prefix = prefix.rstrip()
            if stripped_prefix and line.startswith(stripped_prefix):
                out.append(line[len(stripped_prefix):].lstrip(" "))
            else:
                out.append(line)
    return "\n".join(out)


def _infer_prefix(lines: list[str]) -> str:
    for line in lines:
        m = _KEY_RE.match(line)
        if not m:
            continue
        candidate = m.group(1)
        if _PREFIX_VALID.match(candidate):
            return candidate
    return ""
