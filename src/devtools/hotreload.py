"""Small polling-based hot reload manager.

The game loop already owns timing and threading, so this watcher deliberately
does not spawn background threads.  Call ``poll()`` once per frame in developer
mode and it will debounce changed files before invoking reload callbacks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ReloadCallback = Callable[[Path], object]


@dataclass(frozen=True)
class FileSnapshot:
    exists: bool
    mtime_ns: int = 0
    size: int = 0

    @classmethod
    def capture(cls, path: Path) -> "FileSnapshot":
        try:
            stat = path.stat()
        except FileNotFoundError:
            return cls(False)
        return cls(True, stat.st_mtime_ns, stat.st_size)


@dataclass
class ReloadEvent:
    path: Path
    ok: bool
    message: str
    result: object = None


@dataclass
class _Watch:
    path: Path
    callback: ReloadCallback
    label: str
    snapshot: FileSnapshot
    pending_since: float | None = None
    pending_snapshot: FileSnapshot | None = None


class HotReloadManager:
    def __init__(self, root: Path | str = ".", debounce_seconds: float = 0.20):
        self.root = Path(root).resolve()
        self.debounce_seconds = debounce_seconds
        self._watches: dict[Path, _Watch] = {}

    def watch_file(self, path: Path | str, callback: ReloadCallback, label: str = "") -> None:
        resolved = self._resolve(path)
        self._watches[resolved] = _Watch(
            path=resolved,
            callback=callback,
            label=label or resolved.name,
            snapshot=FileSnapshot.capture(resolved),
        )

    def watch_files(self, paths: list[Path | str], callback: ReloadCallback, label: str = "") -> None:
        for path in paths:
            self.watch_file(path, callback, label)

    def poll(self, now: float | None = None) -> list[ReloadEvent]:
        now = time.monotonic() if now is None else now
        events: list[ReloadEvent] = []
        for watch in list(self._watches.values()):
            current = FileSnapshot.capture(watch.path)
            if current != watch.snapshot and current != watch.pending_snapshot:
                watch.pending_since = now
                watch.pending_snapshot = current
                continue

            if watch.pending_since is None or watch.pending_snapshot is None:
                continue
            if now - watch.pending_since < self.debounce_seconds:
                continue

            events.append(self._reload(watch))
        return events

    def _reload(self, watch: _Watch) -> ReloadEvent:
        assert watch.pending_snapshot is not None
        pending = watch.pending_snapshot
        watch.pending_since = None
        watch.pending_snapshot = None

        if not pending.exists:
            watch.snapshot = pending
            return ReloadEvent(watch.path, False, f"{watch.label}: file is missing")

        try:
            result = watch.callback(watch.path)
        except Exception as exc:
            # Keep the old snapshot so saving a fixed file retriggers reload.
            return ReloadEvent(watch.path, False, f"{watch.label}: reload failed: {exc}")

        watch.snapshot = pending
        return ReloadEvent(watch.path, True, f"{watch.label}: reloaded", result)

    def _resolve(self, path: Path | str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        return p.resolve()
