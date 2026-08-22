import json
from enum import Enum

from src.qt_compat.QtCore import QProcess

from src.core.project_context import ProjectContext
from src.editor.preview_process import PatternPreviewProcess, _qt_enum_value
from src.authoring.scene.document import SceneDocument, TimelineClip, TimelineTrack
from src.authoring.scene.node_types import make_default_root
from src.pattern import PatternDocument


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(json.dumps({"mapping": {"ball_m": {"red": "orb"}}}), encoding="utf-8")
    return ProjectContext(tmp_path)


def _matching(client, request_id):
    return [
        message
        for message in client.events
        if message.get("request_id") == request_id
        and message.get("event") == "response"
    ]


def test_qprocess_enum_values_support_pyside_and_pyqt_representations():
    class PySideStyleExitStatus(Enum):
        NORMAL = 0

    assert _qt_enum_value(PySideStyleExitStatus.NORMAL) == 0
    assert _qt_enum_value(QProcess.NormalExit) == 0


def test_qprocess_headless_worker_handshake_commands_and_clean_shutdown(tmp_path, qapp_session):
    del qapp_session
    client = PatternPreviewProcess(_project(tmp_path))
    issues = []
    client.protocolError.connect(issues.append)

    assert client.start(headless=True, max_bullets=4096)
    assert client.process is not None
    environment = client.process.processEnvironment()
    assert environment.value("PYTHONIOENCODING") == "utf-8"
    assert environment.value("PYTHONUTF8") == "1"
    assert client.wait_for(lambda: client.ready)
    load_id = client.send_command(
        "load",
        {"document": PatternDocument.new("Subprocess").to_dict()},
    )
    assert client.wait_for(lambda: bool(_matching(client, load_id)))
    assert _matching(client, load_id)[0]["payload"]["ok"] is True

    step_id = client.send_command("step")
    assert client.wait_for(lambda: bool(_matching(client, step_id)))
    stats_id = client.send_command("get-stats")
    assert client.wait_for(lambda: bool(_matching(client, stats_id)))
    stats = _matching(client, stats_id)[0]["payload"]["result"]
    assert stats["frame"] == 1
    assert stats["bullet_count"] == 24
    assert stats["max_bullets"] == 4096
    assert stats["max_bullets"] > 600
    assert issues == []

    client.stop()
    client.stop()
    assert client.wait_for(lambda: not client.is_running)


def test_qprocess_headless_worker_loads_and_steps_stage_program(tmp_path, qapp_session):
    del qapp_session
    project = _project(tmp_path)
    scene = SceneDocument(
        "Subprocess Stage",
        make_default_root("Subprocess Stage"),
        metadata={"duration_frames": 1800},
        tracks=[
            TimelineTrack(
                name="Events",
                kind="Event",
                channel="phase",
                clips=[
                    TimelineClip(
                        name="Start",
                        kind="Event",
                        start_frame=0,
                        duration_frames=1,
                        channel="phase",
                        payload={"event_type": "stage_started", "data": {}},
                    )
                ],
            )
        ],
    )
    client = PatternPreviewProcess(project)
    issues = []
    client.protocolError.connect(issues.append)

    assert client.start(headless=True, max_bullets=64)
    assert client.wait_for(lambda: client.ready)
    load_id = client.send_command("load", {"document": scene.to_dict()})
    assert client.wait_for(lambda: bool(_matching(client, load_id)))
    assert _matching(client, load_id)[0]["payload"]["result"]["mode"] == "stage"

    step_id = client.send_command("step")
    assert client.wait_for(lambda: bool(_matching(client, step_id)))
    stats_id = client.send_command("get-stats")
    assert client.wait_for(lambda: bool(_matching(client, stats_id)))
    stats = _matching(client, stats_id)[0]["payload"]["result"]
    assert stats["mode"] == "stage"
    assert stats["duration_frames"] == 1800
    assert stats["frame"] == 1
    assert stats["trace_events"] == 1
    assert issues == []
    client.stop()


def test_worker_malformed_input_is_reported_without_freezing(tmp_path, qapp_session):
    del qapp_session
    client = PatternPreviewProcess(_project(tmp_path))
    assert client.start(headless=True)
    assert client.wait_for(lambda: client.ready)

    client.send_raw(b"{\n")

    assert client.wait_for(
        lambda: any(message.get("event") == "protocol_error" for message in client.events)
    )
    error = next(message for message in client.events if message.get("event") == "protocol_error")
    assert error["payload"]["code"] == "malformed_json"
    assert client.is_running
    client.stop()


def test_qprocess_crash_emits_actionable_issue_and_cleanup_is_idempotent(tmp_path, qapp_session):
    del qapp_session
    client = PatternPreviewProcess(_project(tmp_path))
    issues = []
    client.protocolError.connect(issues.append)
    assert client.start(headless=True)
    assert client.wait_for(lambda: client.ready)
    assert client.process is not None
    process = client.process

    process.kill()

    assert client.wait_for(lambda: process.state() == QProcess.NotRunning)
    assert client.wait_for(lambda: any(item["code"] == "process_crashed" for item in issues))
    assert client.wait_for(lambda: client.process is None)
    client.close()
    client.close()


def test_formal_worker_requires_hello_before_timeout(tmp_path, qapp_session):
    """A live OS process that never completes the protocol handshake is failed."""

    del qapp_session
    worker = tmp_path / "silent_worker.py"
    worker.write_text(
        "import time\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    client = PatternPreviewProcess(_project(tmp_path), script_path=worker)
    issues = []
    client.protocolError.connect(issues.append)

    try:
        assert client.start(headless=True)
        assert client.wait_for(
            lambda: any(item.get("code") == "hello_timeout" for item in issues),
            timeout_ms=5000,
        )
        assert not client.is_running
        assert client.process is None
    finally:
        client.close()


def test_commands_waiting_for_hello_have_a_hard_queue_limit(tmp_path, qapp_session):
    """A silent worker cannot make pre-ready requests grow without bound."""

    del qapp_session
    worker = tmp_path / "silent_queue_worker.py"
    worker.write_text(
        "import time\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    client = PatternPreviewProcess(_project(tmp_path), script_path=worker)
    issues = []
    client.protocolError.connect(issues.append)

    try:
        assert client.start(headless=True)
        for frame in range(1024):
            try:
                client.send_command("seek", {"frame": frame})
            except RuntimeError:
                break
        assert len(client._queued) <= 256
        assert any(item.get("code") == "request_queue_full" for item in issues)
    finally:
        client.close()


def test_oversized_worker_output_is_bounded_and_reported(tmp_path, qapp_session):
    del qapp_session
    worker = tmp_path / "oversized_worker.py"
    worker.write_text(
        "import sys, time\n"
        "sys.stdout.buffer.write(b'x' * 70000 + b'\\n')\n"
        "sys.stdout.buffer.flush()\n"
        "time.sleep(0.2)\n",
        encoding="utf-8",
    )
    client = PatternPreviewProcess(_project(tmp_path), script_path=worker)
    issues = []
    client.protocolError.connect(issues.append)

    assert client.start(headless=True)
    assert client.wait_for(
        lambda: any(item["code"] == "worker_line_too_long" for item in issues)
    )
    assert len(client._stdout_buffer) <= client.MAX_STDOUT_LINE_BYTES
    client.close()
