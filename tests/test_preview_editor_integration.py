import json

from src.qt_compat.QtWidgets import QLabel, QLineEdit

from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.pattern import PatternDocument


class FakePreviewClient:
    def __init__(self):
        self.is_running = True
        self.commands = []
        self.closed = False

    def start(self):
        return True

    def send_command(self, command, payload=None):
        request_id = f"request-{len(self.commands) + 1}"
        self.commands.append((request_id, command, payload or {}))
        return request_id

    def close(self):
        self.closed = True


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

    window._resource_activated(record)

    assert window.bottom_tabs.currentWidget() is window.preview_panel
    assert window.preview_panel.resource_label.text() == "res://assets/patterns/ring.pystg.json"
    assert window.inspector.findChild(QLabel, "inspectorPatternTitle").text() == "Pattern Preview: Editor Ring"
    assert window.inspector.findChild(QLineEdit, "patternProperty_shape_count").text() == "24"
    assert [command for _, command, _ in fake.commands[:2]] == ["load", "play"]
    window.close()


def test_inspector_change_reloads_and_failed_response_reverts_local_document(tmp_path, qapp_session):
    window, fake = _window(tmp_path)
    record = window.resource_browser.index.find("res://assets/patterns/ring.pystg.json")
    window._resource_activated(record)

    count_editor = _active_pattern_editor(window, "patternProperty_shape_count")
    count_editor.setText("7")
    count_editor.editingFinished.emit()
    request_id, command, payload = fake.commands[-1]
    assert command == "set-property"
    assert payload == {"path": "shape.count", "value": 7}
    window._handle_pattern_preview_event(
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
    window._handle_pattern_preview_event(
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
    window._handle_pattern_preview_event(
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
    window._handle_pattern_preview_event(
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
