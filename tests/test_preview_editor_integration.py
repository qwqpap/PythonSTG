import json

from src.qt_compat.QtWidgets import QLabel, QLineEdit

from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.preview import PREVIEW_MODE_FORMAL, PREVIEW_MODE_UNLOADED
from src.pattern import PatternDocument


class FakePreviewClient:
    def __init__(self):
        self.is_running = True
        self.commands = []
        self.closed = False
        self.stop_calls = 0

    def start(self):
        return True

    def send_command(self, command, payload=None):
        request_id = f"request-{len(self.commands) + 1}"
        self.commands.append((request_id, command, payload or {}))
        return request_id

    def close(self):
        self.closed = True
        self.is_running = False

    def stop(self, timeout_ms=1500):
        del timeout_ms
        self.stop_calls += 1
        self.is_running = False


def _window(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(json.dumps({"mapping": {"ball_m": {"red": "orb"}}}), encoding="utf-8")
    pattern = tmp_path / "assets" / "patterns" / "ring.pystg.json"
    pattern.parent.mkdir(parents=True)
    pattern.write_text(json.dumps(PatternDocument.new("Editor Ring").to_dict()), encoding="utf-8")
    window = EditorMainWindow(ProjectContext(tmp_path))
    fake = FakePreviewClient()
    window._pattern_preview_client = fake
    return window, fake


def _active_pattern_editor(window, object_name):
    for index in range(window.inspector._form.count()):
        widget = window.inspector._form.itemAt(index).widget()
        if widget is not None and widget.objectName() == object_name:
            return widget
    raise AssertionError(f"active Inspector editor not found: {object_name}")


def test_pattern_asset_opens_preview_panel_and_live_inspector(tmp_path, qapp_session):
    del qapp_session
    window, fake = _window(tmp_path)
    record = window.resource_browser.index.find("res://assets/patterns/ring.pystg.json")

    window.workbench_service.resource_activated(record)

    assert window.bottom_tabs.currentWidget() is window.preview_panel
    assert window.preview_panel.resource_label.text() == "res://assets/patterns/ring.pystg.json"
    assert window.inspector.findChild(QLabel, "inspectorPatternTitle").text() == "Pattern Preview: Editor Ring"
    assert window.inspector.findChild(QLineEdit, "patternProperty_shape_count").text() == "24"
    assert [command for _, command, _ in fake.commands[:2]] == ["load", "play"]
    window.close()


def test_inspector_change_reloads_and_failed_response_reverts_local_document(tmp_path, qapp_session):
    window, fake = _window(tmp_path)
    record = window.resource_browser.index.find("res://assets/patterns/ring.pystg.json")
    window.workbench_service.resource_activated(record)

    count_editor = _active_pattern_editor(window, "patternProperty_shape_count")
    count_editor.setText("7")
    count_editor.editingFinished.emit()
    request_id, command, payload = fake.commands[-1]
    assert command == "set-property"
    assert payload == {"path": "shape.count", "value": 7}
    window.preview_service._handle_pattern_preview_event(
        {
            "protocol_version": 1,
            "request_id": request_id,
            "event": "response",
            "payload": {"ok": True, "command": command},
        }
    )
    assert window._active_pattern_document.shape.count == 7

    count_editor = _active_pattern_editor(window, "patternProperty_shape_count")
    count_editor.setText("0")
    count_editor.editingFinished.emit()
    failed_id, command, _ = fake.commands[-1]
    window.preview_service._handle_pattern_preview_event(
        {
            "protocol_version": 1,
            "request_id": failed_id,
            "event": "response",
            "payload": {
                "ok": False,
                "command": command,
                "error": {"message": "shape.count must be in 1..4096"},
            },
        }
    )

    assert window._active_pattern_document.shape.count == 7
    qapp_session.sendPostedEvents()
    qapp_session.processEvents()
    assert _active_pattern_editor(window, "patternProperty_shape_count").text() == "7"
    assert "1..4096" in window.preview_panel.error_label.text()
    window.close()


def test_preview_panel_displays_runtime_stats_and_errors(tmp_path, qapp_session):
    del qapp_session
    window, _fake = _window(tmp_path)
    assert window._preview_session.start_formal(
        document_id=window.session.document.id,
        resource_id=f"unsaved://{window.session.document.id}",
    )
    window.preview_service._handle_pattern_preview_event(
        {
            "protocol_version": 1,
            "request_id": None,
            "event": "statistics",
            "payload": {
                "state": "playing",
                "frame": 120,
                "bullet_count": 345,
                "seed": 99,
                "update_ms": 0.75,
                "render_ms": 1.25,
                "gizmos": True,
                "last_error": None,
            },
        }
    )
    window.preview_service._handle_pattern_preview_event(
        {
            "protocol_version": 1,
            "request_id": "bad",
            "event": "compile_error",
            "payload": {
                "diagnostics": [{"path": "shape.count", "message": "must be positive"}],
                "active_program_preserved": True,
            },
        }
    )

    assert window.preview_panel.stats_labels["frame"].text() == "120"
    assert window.preview_panel.stats_labels["bullet_count"].text() == "345"
    assert window.preview_panel.stats_labels["update_ms"].text() == "0.750 ms"
    assert "Last valid program" in window.preview_panel.error_label.text()
    window.close()


def test_preview_panel_reports_starting_and_stopped_process_states(tmp_path, qapp_session):
    del qapp_session
    window, _fake = _window(tmp_path)

    window.preview_panel.set_running(True)
    assert window.preview_panel.status_label.text() == "Starting preview process…"

    window.preview_panel.set_running(False)
    assert window.preview_panel.status_label.text() == "Preview process is stopped"
    window.close()


def test_preview_stop_button_stops_the_preview_session_process(tmp_path, qapp_session):
    window, fake = _window(tmp_path)
    owner = window.session
    assert window._preview_session.start_formal(
        document_id=owner.document.id,
        resource_id=f"unsaved://{owner.document.id}",
    )
    assert window._preview_session.mode == PREVIEW_MODE_FORMAL

    window.preview_service.send_pattern_preview_command("stop", {})
    qapp_session.processEvents()

    assert fake.stop_calls == 1
    assert not fake.is_running
    assert window._preview_session.mode == PREVIEW_MODE_UNLOADED
    assert window._preview_session.active_document_id is None
    window.close()


def test_closing_preview_owner_stops_process_and_releases_identity(
    tmp_path, qapp_session
):
    window, fake = _window(tmp_path)
    owner = window.session
    assert window._preview_session.start_formal(
        document_id=owner.document.id,
        resource_id=f"unsaved://{owner.document.id}",
    )

    window.document_service.close_active_document()
    qapp_session.processEvents()

    assert owner not in window.document_manager.documents
    assert fake.stop_calls == 1
    assert not fake.is_running
    assert window._preview_session.mode == PREVIEW_MODE_UNLOADED
    assert window._preview_session.active_document_id is None
    window.close()


def test_stage_feedback_must_match_preview_session_document_identity(
    tmp_path, qapp_session
):
    window, fake = _window(tmp_path)
    owner = window.session
    assert window._preview_session.start_formal(
        document_id=owner.document.id,
        resource_id=f"unsaved://{owner.document.id}",
    )

    def feedback(frame):
        window.preview_service._handle_pattern_preview_event(
            {
                "protocol_version": 1,
                "request_id": None,
                "event": "statistics",
                "payload": {
                    "mode": "stage",
                    "state": "playing",
                    "resource_id": owner.document.id,
                    "frame": frame,
                    "active_clip_ids": [],
                    "state_path": [],
                    "variable_snapshot": {},
                    "reactive_overlay": {},
                },
            }
        )

    feedback(12)
    assert window.runtime_overlay is not None
    assert window.runtime_overlay.frame == 12

    # Rebinding the formal session to another document invalidates all feedback
    # carrying the old owner's resource id, even if stale window fields still
    # point at that owner.
    assert window._preview_session.start_formal(
        document_id="different-document",
        resource_id="res://different",
    )
    assert fake.is_running
    feedback(99)
    qapp_session.processEvents()

    assert window.runtime_overlay is None or window.runtime_overlay.frame == 12
    window.close()
