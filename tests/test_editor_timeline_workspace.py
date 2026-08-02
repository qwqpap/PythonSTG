from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QPlainTextEdit, QPushButton

from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.timeline_workspace import (
    CLIP_HEIGHT,
    TRACK_HEADER_WIDTH,
    TRACK_HEIGHT,
    RULER_HEIGHT,
    TimelineClipItem,
)


class FakePreviewClient:
    def __init__(self):
        self.is_running = True
        self.commands = []

    def start(self):
        return True

    def send_command(self, command, payload=None):
        self.commands.append((command, payload or {}))
        return str(len(self.commands))

    def close(self):
        pass


def _window(tmp_path, qapp_session):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window._pattern_preview_client = FakePreviewClient()
    window.resize(1180, 760)
    window.show()
    qapp_session.processEvents()
    return window


def _add_event_clip(window):
    window._timeline_add_track("Event")
    track = window.session.document.tracks[0]
    window.timeline.selected_track_id = track.id
    window.session.editor_context["selected_track_id"] = track.id
    add_clip = window.timeline.findChild(QPushButton, "timelineAddClip")
    add_clip.click()
    return track, track.clips[0]


def test_graphics_timeline_add_duplicate_delete_and_undo(tmp_path, qapp_session):
    window = _window(tmp_path, qapp_session)
    track, clip = _add_event_clip(window)
    qapp_session.processEvents()

    items = [
        item
        for item in window.timeline.view.graphics_scene.items()
        if isinstance(item, TimelineClipItem)
    ]
    assert len(items) == 1
    assert items[0].y() == RULER_HEIGHT + (TRACK_HEIGHT - CLIP_HEIGHT) / 2
    items[0].setSelected(True)
    window.timeline.view.setFocus()
    assert window.timeline.view.hasFocus()

    QTest.keyClick(window.timeline.view, Qt.Key_D, Qt.ControlModifier)
    qapp_session.processEvents()
    assert len(track.clips) == 2
    duplicate = track.clips[1]
    assert duplicate.id != clip.id
    assert duplicate.start_frame == clip.end_frame
    assert window.session.undo()
    assert track.clips == [clip]

    window.timeline.selected_clip_id = clip.id
    window.session.editor_context["selected_clip_id"] = clip.id
    window._refresh()
    qapp_session.processEvents()
    window.timeline.view.setFocus()
    QTest.keyClick(window.timeline.view, Qt.Key_Delete)
    qapp_session.processEvents()
    assert not track.clips
    window.undo()
    assert track.clips == [clip]

    window.session.revert()
    window.close()
    qapp_session.processEvents()


def test_scrubbing_seeks_preview_and_zoom_does_not_mutate_frames(tmp_path, qapp_session):
    window = _window(tmp_path, qapp_session)
    _track, clip = _add_event_clip(window)
    qapp_session.processEvents()
    original = window.session.document.to_dict()
    original_start = clip.start_frame
    original_duration = clip.duration_frames

    zoom_in = window.timeline.findChild(QPushButton, "timelineZoomIn")
    before_zoom = window.timeline.pixels_per_frame
    zoom_in.click()
    qapp_session.processEvents()
    assert window.timeline.pixels_per_frame > before_zoom
    assert window.session.document.to_dict() == original
    assert (clip.start_frame, clip.duration_frames) == (original_start, original_duration)

    frame = 180
    point = window.timeline.view.mapFromScene(
        TRACK_HEADER_WIDTH + frame * window.timeline.pixels_per_frame,
        RULER_HEIGHT / 2,
    )
    QTest.mouseClick(window.timeline.view.viewport(), Qt.LeftButton, pos=point)
    qapp_session.processEvents()
    assert window.timeline.playhead_frame == 180
    assert window._pattern_preview_client.commands[-1] == ("seek", {"frame": 180})

    window.timeline.view.setFocus()
    QTest.keyClick(window.timeline.view, Qt.Key_Home)
    qapp_session.processEvents()
    assert window.timeline.playhead_frame == 0
    assert window._pattern_preview_client.commands[-1] == ("seek", {"frame": 0})

    window.session.revert()
    window.close()
    qapp_session.processEvents()


def test_clip_inspector_payload_edit_uses_command_stack(tmp_path, qapp_session):
    window = _window(tmp_path, qapp_session)
    _track, clip = _add_event_clip(window)
    window._timeline_clip_selected(window.session.document.tracks[0].id, clip.id)
    qapp_session.processEvents()

    payload = window.inspector.findChild(QPlainTextEdit, "timelineClipPayload")
    apply_payload = next(
        button
        for button in window.inspector.findChildren(QPushButton)
        if button.text() == "Apply Payload"
    )
    payload.setPlainText('{"event_type": "boss_phase", "data": {"phase": 2}}')
    apply_payload.click()
    qapp_session.processEvents()

    assert clip.payload == {"event_type": "boss_phase", "data": {"phase": 2}}
    window.undo()
    assert clip.payload == {"event_type": "timeline_event", "data": {}}

    window.session.revert()
    window.close()
    qapp_session.processEvents()


def test_scene_with_tracks_launches_formal_stage_preview_document(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    _add_event_clip(window)

    window.run_preview()

    assert [command for command, _payload in window._pattern_preview_client.commands[-2:]] == [
        "load",
        "play",
    ]
    payload = window._pattern_preview_client.commands[-2][1]["document"]
    assert payload["type"] == "pystg.scene"
    assert payload["tracks"][0]["clips"][0]["kind"] == "Event"

    window.session.revert()
    window.close()
    qapp_session.processEvents()
