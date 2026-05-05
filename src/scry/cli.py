"""scry CLI dispatcher (installed by the `scry-mcp` distribution).

  scry            run the MCP server (default; what Claude calls)
  scry init       scaffold an `agent/` tree + driver dirs in CWD
  scry surface    one-shot batch reindex (no server, no watcher)
  scry version    print the package version
  scry --help
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scry import __version__


def _cmd_serve() -> int:
    from scry.server import run_server
    run_server()
    return 0


_LOCAL_GITIGNORE = """\
# scry runtime + cache — fully reconstructable from disk, do not commit.
data/
runtime/
"""


def _cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path).resolve()
    namespace = args.namespace
    target.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    preserved: list[str] = []

    def ensure_dir(p: Path, label: str | None = None) -> None:
        rel = label or (str(p.relative_to(target)) + "/")
        if p.exists():
            preserved.append(rel)
        else:
            p.mkdir(parents=True)
            created.append(rel)

    agent = target / "agent"
    ensure_dir(agent, "agent/")
    driver = agent / "drivers" / f"@{namespace}" / "scry"
    ensure_dir(driver / "data")
    ensure_dir(driver / "runtime")
    ensure_dir(driver / "scripts")

    # Local .gitignore inside the driver dir — keeps scry's gitignore
    # concerns self-contained instead of polluting the project root.
    local_gi = driver / ".gitignore"
    if local_gi.exists():
        preserved.append(str(local_gi.relative_to(target)))
    else:
        local_gi.write_text(_LOCAL_GITIGNORE, encoding="utf-8")
        created.append(str(local_gi.relative_to(target)))

    print(f"Initialized scry in {target}")
    print(f"  namespace: @{namespace}")
    if (agent / "commands").is_dir() or (agent / "progress.yaml").is_file():
        print("  detected: ACP project (agent/ tree preserved)")
    if created:
        print("  created:")
        for c in created:
            print(f"    + {c}")
    if preserved:
        print("  already present:")
        for p in preserved:
            print(f"    · {p}")
    print()
    print("Optional: add `*.scratch.md` to your project .gitignore to honor")
    print("the ephemeral-doc convention (filename → ephemeral=1 in cache).")
    print()
    print("Add this to your MCP client config:")
    print(json.dumps({
        "mcpServers": {
            "scry": {"command": "scry"}
        }
    }, indent=2))
    return 0


def _cmd_surface(args: argparse.Namespace) -> int:
    from scry.config import get_db, get_project_root
    from scry.service.migration import run_migrations
    from scry.service.surface import surface

    root = get_project_root()
    conn = get_db()
    try:
        run_migrations(conn=conn)
        result = surface(conn, project_root=root, force=args.force)
    finally:
        conn.close()
    print(json.dumps(result, indent=2, default=str))
    return 0


def _cmd_version() -> int:
    print(__version__)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scry",
        description="Marker-indexed SQL cache MCP server (scry-mcp package).",
    )
    parser.add_argument("--version", action="version", version=f"scry {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Scaffold an agent/ tree in the current project.")
    p_init.add_argument("path", nargs="?", default=".", help="Project directory (default: cwd).")
    p_init.add_argument("--namespace", default="local", help="Driver namespace (default: local).")

    p_surface = sub.add_parser("surface", help="One-shot batch reindex of the project tree.")
    p_surface.add_argument("--force", action="store_true", help="Hard-delete records whose source file is gone.")

    sub.add_parser("serve", help="Run the MCP server (default if no subcommand given).")
    sub.add_parser("version", help="Print the package version.")

    args = parser.parse_args(argv)
    if args.command is None or args.command == "serve":
        return _cmd_serve()
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "surface":
        return _cmd_surface(args)
    if args.command == "version":
        return _cmd_version()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
