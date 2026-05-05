"""scry_script — discover and execute project validation scripts."""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
import traceback
from pathlib import Path
from typing import Any

from scry.config import get_driver_scripts_dir, get_project_root


def _bundled_scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts"


def _script_dirs(project_root: Path | None = None) -> list[Path]:
    return [
        _bundled_scripts_dir(),
        get_driver_scripts_dir(project_root),
    ]


def _iter_script_files(project_root: Path | None = None):
    seen: set[str] = set()
    for d in _script_dirs(project_root):
        if not d.is_dir():
            continue
        for entry in sorted(d.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix != ".py":
                continue
            if entry.name == "__init__.py":
                continue
            name = entry.stem
            if name in seen:
                continue
            seen.add(name)
            yield name, entry


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"scry_script_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load script {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def list_scripts(project_root: Path | None = None) -> dict[str, Any]:
    items = []
    for name, path in _iter_script_files(project_root):
        try:
            module = _load_module(name, path)
            description = getattr(module, "DESCRIPTION", None)
            run_fn = getattr(module, "run", None)
            doc = getattr(run_fn, "__doc__", None) if run_fn else None
            items.append({
                "name": name,
                "description": description or (doc.strip().splitlines()[0] if doc else None),
                "path": str(path),
            })
        except Exception as e:
            items.append({"name": name, "error": str(e), "path": str(path)})
    return {"scripts": items}


def run_script(
    conn: sqlite3.Connection,
    script: str,
    params: dict[str, Any] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    target: Path | None = None
    for name, path in _iter_script_files(project_root):
        if name == script:
            target = path
            break
    if target is None:
        return {"error": f"script {script!r} not found"}
    try:
        module = _load_module(script, target)
    except Exception as e:
        return {"error": f"failed to load {script}: {e}", "traceback": traceback.format_exc()}
    run_fn = getattr(module, "run", None)
    if not callable(run_fn):
        return {"error": f"script {script!r} does not export `run`"}
    try:
        result = run_fn(conn, params or {})
    except Exception as e:
        return {"error": f"{script} raised: {e}", "traceback": traceback.format_exc()}
    if not isinstance(result, dict):
        return {"result": result}
    return result
