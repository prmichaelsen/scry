"""MCP server connection smoke test — verifies the server completes the
initialize handshake within a tight deadline.

This test exists specifically to catch the regression where a blocking
cold scan in watcher.start() prevented mcp.run() from accepting any
connections until the scan finished (30+ s on large projects), causing
every client to time out.

The test starts `python -m scry` in a subprocess, sends the MCP
initialize request, and asserts a valid response arrives within 5 s.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


INITIALIZE_REQUEST = json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "pytest-handshake-smoke", "version": "1.0"},
    },
}) + "\n"

HANDSHAKE_TIMEOUT_S = 5


def _make_project(tmp_path: Path) -> Path:
    """Scaffold a minimal scry project in tmp_path."""
    project = tmp_path / "project"
    db_dir = project / ".scry" / "data"
    db_dir.mkdir(parents=True)
    # One marker file so the cold scan has something to index.
    (project / "README.md").write_text(
        "<!-- @scry.entry\n"
        "id: task.handshake-smoke~aaaaaaaa\n"
        "kind: task\n"
        "summary: smoke\n"
        "status: draft\n"
        "weight: 0.1\n"
        "@scry.entry.end -->\n",
        encoding="utf-8",
    )
    # Pre-apply schema so the server doesn't have to wait on first-run migration.
    from scry.service.migration import run_migrations
    conn = sqlite3.connect(str(db_dir / "project.db"))
    conn.row_factory = sqlite3.Row
    run_migrations(conn=conn)
    conn.close()
    return project


def test_mcp_initialize_handshake_completes_within_deadline(tmp_path: Path) -> None:
    """Server must return an initialize response before HANDSHAKE_TIMEOUT_S."""
    project = _make_project(tmp_path)

    proc = subprocess.Popen(
        [sys.executable, "-m", "scry"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(project),
    )
    try:
        stdout, _stderr = proc.communicate(
            input=INITIALIZE_REQUEST.encode(),
            timeout=HANDSHAKE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise AssertionError(
            f"MCP initialize handshake timed out after {HANDSHAKE_TIMEOUT_S}s — "
            "server likely blocked before mcp.run() (cold-scan regression?)"
        )
    finally:
        if proc.poll() is None:
            proc.kill()

    # Parse first line of stdout as JSON.
    lines = stdout.decode(errors="replace").strip().splitlines()
    assert lines, "Server produced no stdout"
    response = json.loads(lines[0])
    assert response.get("id") == 1, f"Unexpected response: {response}"
    result = response.get("result", {})
    server_info = result.get("serverInfo", {})
    assert server_info.get("name") == "scry", f"Unexpected serverInfo: {server_info}"


def test_server_instructions_carry_canonical_minimal_form() -> None:
    """Server instructions must embed scry-spec v1.1.2 Canonical
    Minimal Form (D1-D5 + spec pointer) in marker-bearing modes."""
    from scry.server import _build_instructions

    instructions = _build_instructions("inline")

    for marker in ("D1.", "D2.", "D3.", "D4.", "D5."):
        assert marker in instructions, (
            f"instructions missing discipline marker {marker!r} — "
            "scry-spec v1.1.2 Canonical Minimal Form regression."
        )
    # Spec-pointer line — the phrase wraps across a newline in the
    # canonical text, so normalize whitespace before matching.
    normalized = " ".join(instructions.split())
    assert "Recommended Operating Discipline" in normalized, (
        "instructions missing spec-pointer line referencing "
        "the 'Recommended Operating Discipline' section."
    )
    assert "scry-spec" in normalized, (
        "instructions missing 'scry-spec' reference in the "
        "spec-pointer line."
    )


def test_mcp_initialize_returns_canonical_minimal_form_instructions(
    tmp_path: Path,
) -> None:
    """The MCP `initialize` response's `instructions` field must carry
    D1-D5. Wire-level guard for the Canonical Minimal Form."""
    project = _make_project(tmp_path)

    proc = subprocess.Popen(
        [sys.executable, "-m", "scry"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(project),
    )
    try:
        stdout, _stderr = proc.communicate(
            input=INITIALIZE_REQUEST.encode(),
            timeout=HANDSHAKE_TIMEOUT_S,
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

    lines = stdout.decode(errors="replace").strip().splitlines()
    assert lines, "Server produced no stdout"
    response = json.loads(lines[0])
    result = response.get("result", {})
    instructions = result.get("instructions") or ""
    for marker in ("D1.", "D2.", "D3.", "D4.", "D5."):
        assert marker in instructions, (
            f"MCP initialize response missing discipline marker "
            f"{marker!r} in `instructions` field — "
            f"got: {instructions[:200]!r}"
        )
