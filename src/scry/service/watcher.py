"""scry watcher daemon — file events → DB writes.

Implements: 150ms debounce, lock-file primary election, cold scan on
promotion, soft/hard delete semantics, binary-file skip, symlink-target
observers (DR11).
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from scry.config import (
    DEBOUNCE_MS,
    EXCLUDED_DIRS,
    get_db,
    get_db_path,
    get_lock_path,
    get_project_root,
)
from scry.service.surface import handle_file_deletion, handle_subtree_deletion, reindex_file


class LockFile:
    """PID-based primary election. Single in-process, multi-session safe."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def claim(self) -> bool:
        my_pid = os.getpid()
        if self.path.exists():
            try:
                holder = int(self.path.read_text().strip() or "0")
            except (OSError, ValueError):
                holder = 0
            if holder and holder != my_pid and _pid_alive(holder):
                return False
        self.path.write_text(str(my_pid))
        return True

    def release(self) -> None:
        try:
            if self.path.exists() and int(self.path.read_text().strip() or "0") == os.getpid():
                self.path.unlink()
        except (OSError, ValueError):
            pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


class _Debouncer:
    """Per-path delayed callback. Resets the timer when the same path fires again."""

    def __init__(self, delay_ms: int, callback) -> None:
        self.delay = delay_ms / 1000.0
        self.callback = callback
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def trigger(self, key: str, *args) -> None:
        with self._lock:
            existing = self._timers.get(key)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(self.delay, self._fire, args=(key, args))
            self._timers[key] = timer
            timer.daemon = True
            timer.start()

    def _fire(self, key: str, args: tuple) -> None:
        with self._lock:
            self._timers.pop(key, None)
        try:
            self.callback(*args)
        except Exception as exc:
            # Watcher must never crash; log and swallow per-event errors.
            print(f"[scry watcher] error processing {key!r}: {exc}", file=sys.stderr)

    def shutdown(self) -> None:
        with self._lock:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "ScryWatcher") -> None:
        self.watcher = watcher

    def _excluded(self, path: str) -> bool:
        try:
            rel = Path(path).relative_to(self.watcher.project_root)
        except ValueError:
            return True  # outside project root — exclude
        return any(p in EXCLUDED_DIRS or p.startswith(".") for p in rel.parts)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._excluded(event.src_path):
            return
        self.watcher.debounce_modify(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if self._excluded(event.src_path):
            return
        if event.is_directory:
            # New directory created — check if it's a symlink to a directory
            # (watchdog fires on_created with is_directory=True for dir symlinks on Linux)
            self.watcher._schedule_for_symlink(event.src_path)
            return
        # Check if a newly created file is actually a directory symlink
        # (some platforms report symlinks as files)
        p = Path(event.src_path)
        if p.is_symlink() and p.is_dir():
            self.watcher._schedule_for_symlink(event.src_path)
            return
        self.watcher.debounce_modify(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            # May be a tracked symlink directory being removed
            self.watcher._unschedule_for_symlink(event.src_path)
            return
        # Check if the deleted path was a tracked symlink
        if event.src_path in self.watcher._symlink_observers:
            self.watcher._unschedule_for_symlink(event.src_path)
            return
        self.watcher.debounce_delete(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if hasattr(event, "src_path") and event.src_path:
            self.watcher.debounce_delete(event.src_path)
        if hasattr(event, "dest_path") and event.dest_path:
            self.watcher.debounce_modify(event.dest_path)


class ScryWatcher:
    def __init__(
        self,
        project_root: Optional[Path] = None,
        db_path: Optional[Path] = None,
        debounce_ms: int = DEBOUNCE_MS,
    ) -> None:
        self.project_root = project_root or get_project_root()
        self.db_path = db_path or get_db_path()
        self.lock = LockFile(get_lock_path())
        self.is_primary = False
        self._observer: Optional[Observer] = None
        self._debouncer = _Debouncer(debounce_ms, self._process_modify)
        self._delete_debouncer = _Debouncer(debounce_ms, self._process_delete)
        self._stopped = False
        # DR11: symlink observers — maps symlink_abs_path -> (resolved_target_str, Observer)
        self._symlink_observers: dict[str, tuple[str, Observer]] = {}
        # Background cold-scan thread (set by start(); join in tests to await completion)
        self.cold_scan_thread: Optional[threading.Thread] = None

    def start(self, run_cold_scan: bool = True) -> None:
        self.is_primary = self.lock.claim()
        if not self.is_primary:
            return
        self._observer = Observer()
        self._observer.schedule(_Handler(self), str(self.project_root), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        # DR11: schedule observers for any existing symlinks under agent/projects/
        self._setup_existing_symlink_observers()
        if run_cold_scan:
            # Run cold scan in a background thread so the MCP server can start
            # accepting connections immediately. Large projects (many symlinked
            # sub-projects + scry__file body indexing) can take 30+ seconds to
            # scan, which would otherwise exceed the MCP handshake timeout.
            t = threading.Thread(target=self.cold_scan, daemon=True, name="scry-cold-scan")
            t.start()
            self.cold_scan_thread = t

    def _setup_existing_symlink_observers(self) -> None:
        """DR11: At startup, schedule observers for any existing directory symlinks."""
        projects_dir = self.project_root / "agent" / "projects"
        if not projects_dir.is_dir():
            return
        for entry in projects_dir.iterdir():
            if entry.is_symlink() and entry.is_dir():
                self._schedule_for_symlink(str(entry))

    def _schedule_for_symlink(self, symlink_path: str) -> None:
        """DR11: Schedule a watchdog Observer for a directory symlink's resolved target."""
        if symlink_path in self._symlink_observers:
            return  # already watching
        p = Path(symlink_path)
        if not p.is_symlink() or not p.is_dir():
            return
        try:
            real_target = str(p.resolve())
        except OSError:
            return
        obs = Observer()
        obs.schedule(_Handler(self), real_target, recursive=True)
        obs.daemon = True
        obs.start()
        self._symlink_observers[symlink_path] = (real_target, obs)

    def _unschedule_for_symlink(self, symlink_path: str) -> None:
        """DR11: Stop observer for a deleted symlink and flush its DB rows."""
        entry = self._symlink_observers.pop(symlink_path, None)
        if entry is None:
            return
        _resolved_target, obs = entry
        obs.stop()
        try:
            obs.join(timeout=2)
        except RuntimeError:
            pass
        # Compute the relative prefix this symlink had in the DB
        try:
            rel_prefix = str(Path(symlink_path).relative_to(self.project_root)) + "/"
        except ValueError:
            return
        conn = get_db(self.db_path)
        try:
            handle_subtree_deletion(conn, rel_prefix)
        finally:
            conn.close()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._observer is not None:
            self._observer.stop()
            try:
                self._observer.join(timeout=2)
            except RuntimeError:
                pass
            self._observer = None
        # Stop all symlink observers
        for _key, (_target, obs) in list(self._symlink_observers.items()):
            obs.stop()
            try:
                obs.join(timeout=2)
            except RuntimeError:
                pass
        self._symlink_observers.clear()
        self._debouncer.shutdown()
        self._delete_debouncer.shutdown()
        if self.is_primary:
            self.lock.release()
            self.is_primary = False

    def debounce_modify(self, abs_path: str) -> None:
        if not self.is_primary:
            return
        self._debouncer.trigger(abs_path, abs_path)

    def debounce_delete(self, abs_path: str) -> None:
        if not self.is_primary:
            return
        self._delete_debouncer.trigger(abs_path, abs_path)

    def cold_scan(self) -> None:
        from scry.service.surface import surface
        conn = get_db(self.db_path)
        try:
            before = conn.execute(
                "SELECT COUNT(*) AS n FROM scry__doc WHERE missing_since IS NULL"
            ).fetchone()["n"]
            result = surface(conn, project_root=self.project_root, force=False)
            after = conn.execute(
                "SELECT COUNT(*) AS n FROM scry__doc WHERE missing_since IS NULL"
            ).fetchone()["n"]
            delta = after - before
            flagged = len(result.get("flagged_missing", []))
            if delta > 0 or flagged > 0:
                print(
                    f"[scry watcher] cold scan: {result['files_scanned']} files scanned, "
                    f"{result['markers_indexed']} markers indexed "
                    f"(+{delta} net-new docs, {flagged} flagged missing)",
                    file=sys.stderr,
                )
                if delta > 5:
                    print(
                        f"[scry watcher] WARNING: {delta} markers were on disk but not indexed "
                        "— watcher may have been offline or drift occurred. "
                        "Run scry_surface to rebuild if counts seem wrong.",
                        file=sys.stderr,
                    )
        finally:
            conn.close()

    def _process_modify(self, abs_path: str) -> None:
        path = Path(abs_path)
        if not path.exists() or not path.is_file():
            return
        conn = get_db(self.db_path)
        try:
            reindex_file(conn, path, self.project_root)
        finally:
            conn.close()

    def _process_delete(self, abs_path: str) -> None:
        try:
            rel = str(Path(abs_path).relative_to(self.project_root))
        except ValueError:
            return
        conn = get_db(self.db_path)
        try:
            handle_file_deletion(conn, rel)
        finally:
            conn.close()

    def try_promote(self) -> bool:
        """Re-attempt primary claim. Run cold scan if newly promoted."""
        if self.is_primary:
            return True
        if self.lock.claim():
            self.is_primary = True
            self.cold_scan()
            if self._observer is None:
                self._observer = Observer()
                self._observer.schedule(_Handler(self), str(self.project_root), recursive=True)
                self._observer.daemon = True
                self._observer.start()
            self._setup_existing_symlink_observers()
            return True
        return False
