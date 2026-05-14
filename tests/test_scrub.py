"""scry_scrub tests — default excludes agent/ and AGENT.md; --include-agent restores."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scry.service.scrub import _is_agent_path, scrub


# ---------------------------------------------------------------------------
# _is_agent_path unit tests
# ---------------------------------------------------------------------------

class TestIsAgentPath:
    def test_agent_dir_top_level(self):
        assert _is_agent_path("agent/design/foo.md") is True

    def test_agent_dir_nested(self):
        assert _is_agent_path("agent/runtime/tracks/main/inbox/msg.md") is True

    def test_agent_md_any_location(self):
        assert _is_agent_path("AGENT.md") is True
        assert _is_agent_path("subdir/AGENT.md") is True

    def test_non_agent_path(self):
        assert _is_agent_path("src/foo.py") is False
        assert _is_agent_path("README.md") is False
        assert _is_agent_path("docs/agent-notes.md") is False  # contains "agent" but not a dir component

    def test_agent_not_in_name_only(self):
        # A file called "agent.py" at root is NOT an agent path
        assert _is_agent_path("agent.py") is False


# ---------------------------------------------------------------------------
# Helpers for git-repo tests
# ---------------------------------------------------------------------------

MARKER_BLOCK = """\
<!-- @scry.doc
id: design.test~aabbccdd
kind: design
summary: test doc
status: active
weight: 0.5
@scry.doc.end -->

# Content after marker
"""

PLAIN_CONTENT = "# No markers here\n"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        check=True,
    )


def _init_repo(path: Path) -> None:
    """Create a minimal git repo with an initial commit on a non-protected branch."""
    _git(["init", "-b", "feature"], path)
    _git(["config", "user.email", "test@example.com"], path)
    _git(["config", "user.name", "Test"], path)
    readme = path / "README.md"
    readme.write_text("# test\n", encoding="utf-8")
    _git(["add", "README.md"], path)
    _git(["commit", "-m", "init"], path)


def _write_and_commit(repo: Path, rel: str, content: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(["add", rel], repo)
    _git(["commit", "-m", f"add {rel}"], repo)


# ---------------------------------------------------------------------------
# Integration tests (require git)
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_repo(tmp_path)
    return tmp_path


class TestScrubDefaultExcludesAgent:
    def test_skips_agent_dir_files(self, repo: Path):
        _write_and_commit(repo, "agent/design/foo.md", MARKER_BLOCK)
        _write_and_commit(repo, "src/bar.py", MARKER_BLOCK)

        result = scrub(project_root=repo)

        assert "error" not in result, result.get("error")
        # src/bar.py should be stripped (it's tracked, not agent/)
        assert "src/bar.py" in result["stripped_files"]
        # agent/design/foo.md should NOT be stripped
        assert "agent/design/foo.md" not in result["stripped_files"]
        # agent/ should NOT be removed
        assert result["agent_removed"] is False
        # skipped_agent should report the exclusion
        assert "agent/design/foo.md" in result.get("skipped_agent", [])

    def test_skips_agent_md(self, repo: Path):
        _write_and_commit(repo, "AGENT.md", MARKER_BLOCK)
        _write_and_commit(repo, "docs/guide.md", MARKER_BLOCK)

        result = scrub(project_root=repo)

        assert "error" not in result, result.get("error")
        assert "docs/guide.md" in result["stripped_files"]
        assert "AGENT.md" not in result["stripped_files"]
        assert "AGENT.md" in result.get("skipped_agent", [])

    def test_no_skipped_when_no_agent_files(self, repo: Path):
        _write_and_commit(repo, "src/util.py", MARKER_BLOCK)

        result = scrub(project_root=repo)

        assert "error" not in result, result.get("error")
        assert "src/util.py" in result["stripped_files"]
        assert "skipped_agent" not in result


class TestScrubIncludeAgent:
    def test_scrubs_agent_files_when_flag_set(self, repo: Path):
        _write_and_commit(repo, "agent/design/foo.md", MARKER_BLOCK)
        _write_and_commit(repo, "src/bar.py", MARKER_BLOCK)

        result = scrub(project_root=repo, include_agent=True)

        assert "error" not in result, result.get("error")
        assert "src/bar.py" in result["stripped_files"]
        # agent/ is removed, so the individual file won't be in stripped_files
        # but agent_removed should be True
        assert result["agent_removed"] is True
        assert "skipped_agent" not in result

    def test_scrubs_agent_md_when_flag_set(self, repo: Path):
        _write_and_commit(repo, "AGENT.md", MARKER_BLOCK)

        result = scrub(project_root=repo, include_agent=True)

        assert "error" not in result, result.get("error")
        assert "AGENT.md" in result["stripped_files"]

    def test_no_skipped_hint_when_include_agent(self, repo: Path):
        _write_and_commit(repo, "agent/design/foo.md", MARKER_BLOCK)

        result = scrub(project_root=repo, include_agent=True)

        assert "skipped_agent" not in result
        assert "hint" not in result


class TestScrubErrorCases:
    def test_refuses_main_branch(self, tmp_path: Path):
        _init_repo(tmp_path)
        # Re-init on main
        _git(["checkout", "-b", "main"], tmp_path)
        result = scrub(project_root=tmp_path)
        assert "error" in result
        assert "main" in result["error"]

    def test_refuses_dirty_tree(self, repo: Path):
        dirty = repo / "dirty.md"
        dirty.write_text("uncommitted\n", encoding="utf-8")
        result = scrub(project_root=repo)
        assert "error" in result
        assert "clean" in result["error"]
