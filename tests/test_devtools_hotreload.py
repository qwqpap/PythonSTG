import os

from src.devtools.hotreload import HotReloadManager


def test_hot_reload_debounces_and_invokes_callback(tmp_path):
    watched = tmp_path / "config.json"
    watched.write_text("old", encoding="utf-8")
    calls = []
    manager = HotReloadManager(tmp_path, debounce_seconds=0.5)
    manager.watch_file("config.json", lambda path: calls.append(path.read_text(encoding="utf-8")))

    watched.write_text("new value", encoding="utf-8")
    os.utime(watched, ns=(2_000_000_000, 2_000_000_000))

    assert manager.poll(now=1.0) == []
    assert manager.poll(now=1.2) == []
    events = manager.poll(now=1.6)

    assert calls == ["new value"]
    assert len(events) == 1
    assert events[0].ok


def test_hot_reload_keeps_old_snapshot_when_callback_fails(tmp_path):
    watched = tmp_path / "config.json"
    watched.write_text("old", encoding="utf-8")
    manager = HotReloadManager(tmp_path, debounce_seconds=0.0)
    attempts = []

    def fail_once(path):
        attempts.append(path.read_text(encoding="utf-8"))
        if len(attempts) == 1:
            raise ValueError("bad config")
        return "ok"

    manager.watch_file("config.json", fail_once)
    watched.write_text("bad config", encoding="utf-8")
    os.utime(watched, ns=(2_000_000_000, 2_000_000_000))

    assert manager.poll(now=1.0) == []
    assert not manager.poll(now=1.1)[0].ok
    watched.write_text("fixed", encoding="utf-8")
    os.utime(watched, ns=(3_000_000_000, 3_000_000_000))
    assert manager.poll(now=2.0) == []
    event = manager.poll(now=2.1)[0]

    assert event.ok
    assert attempts == ["bad config", "fixed"]
