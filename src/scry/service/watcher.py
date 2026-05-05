"""scry watcher daemon — file events → DB writes.

Implements: 150ms debounce, lock-file primary election, cold scan on
promotion, soft/hard delete semantics, binary-file skip.
"""
from __future__ import annotations

import os
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
from scry.service.surface import handle_file_deletion, reindex_file


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
        except Exception:
            # Watcher must never crash; swallow per-event errors.
            pass

    def shutdown(self) -> None:
        with self._lock:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "ScryWatcher") -> None:
        self.watcher = watcher

    def _excluded(self, path: str) -> bool:
        rel_parts = Path(path).parts
        return any(p in EXCLUDED_DIRS or p.startswith(".") for p in rel_parts)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._excluded(event.src_path):
            return
        self.watcher.debounce_modify(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._excluded(event.src_path):
            return
        self.watcher.debounce_modify(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
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

    def start(self, run_cold_scan: bool = True) -> None:
        self.is_primary = self.lock.claim()
        if not self.is_primary:
            return
        if run_cold_scan:
            self.cold_scan()
        self._observer = Observer()
        self._observer.schedule(_Handler(self), str(self.project_root), recursive=True)
        self._observer.daemon = True
        self._observer.start()

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
            surface(conn, project_root=self.project_root, force=False)
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
            return True
        return False
