"""marker_mode off: tool registration + server instructions."""
from __future__ import annotations

from scry.server import _build_instructions
from scry.tools import register_tools


class _FakeMCP:
    """Records the functions passed to mcp.tool()(fn)."""

    def __init__(self) -> None:
        self.registered: list[str] = []

    def tool(self):
        def decorator(fn):
            self.registered.append(fn.__name__)
            return fn

        return decorator


def _register(marker_mode: str) -> list[str]:
    mcp = _FakeMCP()
    register_tools(mcp, marker_mode=marker_mode)  # type: ignore[arg-type]
    return mcp.registered


def test_off_mode_registers_only_grep_surface_health() -> None:
    assert set(_register("off")) == {"scry_grep", "scry_surface", "scry_db_health"}


def test_off_mode_omits_marker_tools() -> None:
    registered = set(_register("off"))
    for omitted in (
        "scry_sql",
        "scry_mint",
        "scry_mint_with_check",
        "scry_sink",
        "scry_scrub",
        "scry_script",
    ):
        assert omitted not in registered


def test_inline_mode_registers_full_toolset() -> None:
    registered = set(_register("inline"))
    for tool in (
        "scry_sql",
        "scry_mint",
        "scry_mint_with_check",
        "scry_surface",
        "scry_sink",
        "scry_scrub",
        "scry_script",
        "scry_grep",
        "scry_db_health",
    ):
        assert tool in registered


def test_off_mode_instructions_omit_marker_discipline() -> None:
    text = _build_instructions("off")
    for marker in ("D1.", "D2.", "D3.", "D4.", "D5."):
        assert marker not in text
    assert "scry_sql" not in text
    assert "scry_mint" not in text
    assert "scry_grep" in text


def test_inline_mode_instructions_carry_discipline() -> None:
    text = _build_instructions("inline")
    for marker in ("D1.", "D2.", "D3.", "D4.", "D5."):
        assert marker in text
