"""scry_script tests (FR24-FR26)."""
from __future__ import annotations

from pathlib import Path

from scry.service.script import list_scripts, run_script


def test_list_includes_bundled_validate_coverage():
    out = list_scripts()
    names = [s["name"] for s in out["scripts"]]
    assert "validate_coverage" in names


def test_run_script_executes_with_db(conn, monkeypatch, tmp_path: Path):
    # Drop a driver-local script that just queries the DB.
    drivers_dir = tmp_path / "agent" / "drivers" / "@local" / "scry" / "scripts"
    drivers_dir.mkdir(parents=True, exist_ok=True)
    (drivers_dir / "ping.py").write_text(
        'DESCRIPTION = "ping"\n\n'
        "def run(db, params):\n"
        "    n = db.execute(\"SELECT count(*) AS c FROM scry__doc\").fetchone()[\"c\"]\n"
        "    return {\"docs\": n, \"params\": params}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    out = run_script(conn, "ping", params={"hello": "world"}, project_root=tmp_path)
    assert out == {"docs": 0, "params": {"hello": "world"}}


def test_run_script_unknown_returns_error(conn):
    out = run_script(conn, "no_such_script")
    assert "error" in out


def test_validate_coverage_runs_on_empty_db(conn, project_tree):
    out = run_script(conn, "validate_coverage", project_root=project_tree)
    assert out["specs_checked"] == 0
    assert out["covered"] == 0
    assert out["missing"] == []
