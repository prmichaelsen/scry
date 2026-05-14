"""scry_scrub tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scry.service.scrub import _is_agent_path, scrub


# ---------------------------------------------------------------------------
# _is_agent_path unit tests
# ---------------------------------------------------------------------------

def test_is_agent_path_agent_dir():
    assert _is_agent_path("agent/design/foo.md") is True

def test_is_agent_path_agent_root():
    assert _is_agent_path("agent") is True

def test_is_agent_path_agent_md():
    assert _is_agent_path("AGENT.md") is True

def test_is_agent_path_nested_agent_md():
    assert _is_agent_path("src/AGENT.md") is True

def test_is_agent_path_non_agent():
    assert _is_agent_path("src/foo.py") is False

def test_is_agent_path_readme():
    assert _is_agent_path("README.md") is False

def test_is_agent_path_src_agent_like():
    # A file named agent_something.py is NOT under agent/
    assert _is_agent_path("src/agent_utils.py") is False


# ---------------------------------------------------------------------------
# Integration tests (require a real git repo)
# ---------------------------------------------------------------------------

MARKER_BLOCK = """\
<!-- @scry.entry
id: task.example~12345678
kind: task
summary: example
status: active
weight: 0.5
@scry.entry.end -->

Some content here.
"""


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Minimal git repo with one commit on a non-main branch."""
    _git(["git", "init", "-b", "feature"], tmp_path)
    _git(["git", "config", "user.email", "test@test.com"], tmp_path)
    _git(["git", "config", "user.name", "Test"], tmp_path)
    # Initial commit so HEAD exists
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    _git(["git", "add", "README.md"], tmp_path)
    _git(["git", "commit", "-m", "init"], tmp_path)
    return tmp_path


def _add_file(repo: Path, rel: str, content: str) -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(["git", "add", rel], repo)
    return p


def test_default_scrub_skips_agent_files(git_repo):
    """Default: agent/ files are NOT stripped."""
    _add_file(git_repo, "src/module.py", f"# code\n{MARKER_BLOCK}\n")
    _add_file(git_repo, "agent/design/foo.md", MARKER_BLOCK)
    _git(["git", "commit", "-m", "add files"], git_repo)

    result = scrub(project_root=git_repo, include_agent=False)

    assert "error" not in result
    # tracked source file was stripped
    assert "src/module.py" in result["stripped_files"]
    # agent file was skipped
    assert result.get("skipped_agent") and any(
        "agent/design/foo.md" in s for s in result["skipped_agent"]
    )
    # agent/ directory was NOT removed
    assert result["agent_removed"] is False
    assert (git_repo / "agent").is_dir()
    # agent marker file is unchanged
    assert MARKER_BLOCK in (git_repo / "agent" / "design" / "foo.md").read_text()


def test_default_scrub_skips_agent_md(git_repo):
    """Default: AGENT.md is NOT stripped."""
    _add_file(git_repo, "AGENT.md", f"# instructions\n{MARKER_BLOCK}\n")
    _add_file(git_repo, "src/utils.py", f"# util\n{MARKER_BLOCK}\n")
    _git(["git", "commit", "-m", "add files"], git_repo)

    result = scrub(project_root=git_repo, include_agent=False)

    assert "error" not in result
    assert "src/utils.py" in result["stripped_files"]
    assert result.get("skipped_agent") and any(
        "AGENT.md" in s for s in result["skipped_agent"]
    )
    assert MARKER_BLOCK in (git_repo / "AGENT.md").read_text()


def test_include_agent_scrubs_agent_files(git_repo):
    """include_agent=True: agent/ files ARE stripped and agent/ is removed."""
    _add_file(git_repo, "src/module.py", f"# code\n{MARKER_BLOCK}\n")
    _add_file(git_repo, "agent/design/foo.md", MARKER_BLOCK)
    _git(["git", "commit", "-m", "add files"], git_repo)

    result = scrub(project_root=git_repo, include_agent=True)

    assert "error" not in result
    assert "src/module.py" in result["stripped_files"]
    # agent file was scrubbed
    assert "agent/design/foo.md" in result["stripped_files"]
    # agent/ was removed
    assert result["agent_removed"] is True
    assert not result.get("skipped_agent")


def test_scrub_only_tracked_files_no_markers(git_repo):
    """No markers anywhere -> empty stripped_files."""
    _add_file(git_repo, "src/plain.py", "# no markers here\n")
    _git(["git", "commit", "-m", "plain"], git_repo)

    result = scrub(project_root=git_repo, include_agent=False)

    assert "error" not in result
    assert result["stripped_files"] == []


def test_scrub_refuses_main_branch(tmp_path):
    """Refuses to operate on main."""
    _git(["git", "init", "-b", "main"], tmp_path)
    _git(["git", "config", "user.email", "t@t.com"], tmp_path)
    _git(["git", "config", "user.name", "T"], tmp_path)
    (tmp_path / "f.txt").write_text("x")
    _git(["git", "add", "f.txt"], tmp_path)
    _git(["git", "commit", "-m", "init"], tmp_path)

    result = scrub(project_root=tmp_path)

    assert "error" in result
    assert "protected" in result["error"]
