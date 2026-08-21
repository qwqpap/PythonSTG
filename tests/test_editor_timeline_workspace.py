from src.qt_compat.QtCore import QPoint, QPointF, Qt
from src.qt_compat.QtGui import QMouseEvent, QWheelEvent
from src.qt_compat.QtWidgets import QApplication
from src.qt_compat.QtTest import QTest
from src.qt_compat.QtWidgets import QPlainTextEdit, QPushButton, QTableWidget
from src.qt_compat.QtWidgets import QGraphicsItem

from src.core.project_context import ProjectContext
from src.editor import TimelineClip, TimelineKeyframe, TimelineTrack, make_node
from src.editor.app import EditorMainWindow, SceneViewport
from src.authoring.commands.timeline import AddClipCommand, AddTrackCommand
from src.editor.panels.timeline_workspace import (
    CLIP_HEIGHT,
    TRACK_HEADER_WIDTH,
    TRACK_HEIGHT,
    RULER_HEIGHT,
    TimelineClipItem,
    TimelineEditor,
    TimelineKeyframeItem,
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
    window.session.editor_state.selection.track_id = track.id
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
    window.session.editor_state.selection.clip_id = clip.id
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
    window.resize(960, 640)
    qapp_session.processEvents()
    assert window.bottom_dock.height() >= 210
    assert window.timeline.view.viewport().height() >= 40
    window._active_stage_session = window.session
    window._preview_mode = "stage"
    window._preview_loaded_resource_id = window.session.document.id
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
    state = payload["state_graph"]["states"][0]
    assert state["tracks"][0]["clips"][0]["kind"] == "Event"

    window.session.revert()
    window.close()
    qapp_session.processEvents()


def test_runtime_statistics_drive_playhead_active_clip_and_pose_without_seek_or_dirty(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    track, clip = _add_event_clip(window)
    qapp_session.processEvents()
    window._active_stage_session = window.session
    window._preview_mode = "stage"
    window._preview_loaded_resource_id = window.session.document.id
    window._preview_state = "playing"
    window._pattern_preview_client.commands.clear()
    before_document = window.session.document.to_dict()
    before_dirty = window.session.is_dirty

    window._handle_pattern_preview_event(
        {
            "event": "statistics",
            "payload": {
                "mode": "stage",
                "resource_id": window.session.document.id,
                "state": "playing",
                "frame": 24,
                "active_clips": [clip.id],
                "node_state": {},
            },
        }
    )
    qapp_session.processEvents()

    assert window.timeline.playhead_frame == 24
    assert window.runtime_overlay is not None
    assert window.runtime_overlay.frame == 24
    assert window.session.editor_state.timeline.playhead_frame == 0
    assert window._pattern_preview_client.commands == []
    assert window.session.document.to_dict() == before_document
    assert window.session.is_dirty is before_dirty
    clip_item = next(
        item
        for item in window.timeline.view.graphics_scene.items()
        if isinstance(item, TimelineClipItem) and item.clip_id == clip.id
    )
    assert clip_item.active is True
    window._handle_pattern_preview_event(
        {
            "event": "status",
            "payload": {
                "mode": "stage",
                "resource_id": window.session.document.id,
                "state": "stopped",
                "frame": 0,
            },
        }
    )
    assert window.timeline.playhead_frame == 0

    del clip_item
    window.session.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()


def test_scene_viewport_runtime_pose_is_read_only_and_restores_authoring_position(
    tmp_path, qapp_session
):
    from src.editor.session import SceneEditorSession

    document = SceneEditorSession.new_document()
    sprite = make_node("Sprite")
    document.root.children.append(sprite)
    before = document.to_dict()
    viewport = SceneViewport(ProjectContext(tmp_path))
    viewport.resize(500, 500)
    viewport.show()
    viewport.rebuild(document)
    sprite_item = viewport._items[sprite.id]

    viewport.set_runtime_state({sprite.id: {"x": 0.5, "y": -0.5}})
    assert sprite_item._runtime_pose is True
    assert not (
        sprite_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    )
    assert (sprite_item.x(), sprite_item.y()) == (288.0, 336.0)
    assert document.to_dict() == before

    viewport.clear_runtime_state()
    assert sprite_item._runtime_pose is False
    assert sprite_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    assert (sprite_item.x(), sprite_item.y()) == (
        float(sprite.properties["x"]),
        float(sprite.properties["y"]),
    )
    assert document.to_dict() == before
    del sprite_item
    viewport.close()
    viewport.deleteLater()
    qapp_session.processEvents()


def test_stage_preview_feedback_is_owned_by_loaded_scene_and_does_not_cross_tabs(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    _track, _clip = _add_event_clip(window)
    owner = window.session
    window._active_stage_session = owner
    window._preview_mode = "stage"
    window._preview_loaded_resource_id = owner.document.id
    window.new_scene()
    current = window.session
    window.timeline.set_playhead(6, emit=False)

    window._handle_pattern_preview_event(
        {
            "event": "statistics",
            "payload": {
                "mode": "stage",
                "resource_id": owner.document.id,
                "state": "playing",
                "frame": 120,
                "active_clips": [],
                "node_state": {},
            },
        }
    )

    assert window.session is current
    assert window.timeline.playhead_frame == 6
    assert current.editor_state.timeline.playhead_frame != 120
    owner.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()


def test_stage_runtime_feedback_moves_boss_in_owner_viewport_while_other_tab_is_active(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    owner = window.session
    boss = make_node("Boss", name="Moving Boss")
    boss.properties.update({"x": 192.0, "y": 112.0})
    owner.document.root.children.append(boss)
    window._refresh()
    owner_viewport = window._document_widgets[owner.document.id]
    assert isinstance(owner_viewport, SceneViewport)

    # Switch the shared editor to another scene while the owner preview keeps
    # running.  Pose feedback must still be retained by the owner document,
    # while the other scene's timeline remains untouched.
    window._active_stage_session = owner
    window._preview_mode = "stage"
    window._preview_loaded_resource_id = owner.document.id
    window.new_scene()
    current = window.session
    window.timeline.set_playhead(7, emit=False)
    window._handle_pattern_preview_event(
        {
            "event": "statistics",
            "payload": {
                "mode": "stage",
                "resource_id": owner.document.id,
                "state": "playing",
                "frame": 42,
                "active_clips": [],
                "node_state": {boss.id: {"x": 0.5, "y": -0.5}},
            },
        }
    )
    qapp_session.processEvents()

    assert current is window.session
    assert window.timeline.playhead_frame == 7
    assert window.runtime_overlay is not None
    assert window.runtime_overlay.document_id == owner.document.id
    assert window.runtime_overlay.frame == 42
    item = owner_viewport._items[boss.id]
    assert item._runtime_pose is True
    assert (item.x(), item.y()) == (288.0, 336.0)

    owner.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()


def test_stage_hot_reload_restores_playhead_and_previous_play_state(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    _add_event_clip(window)
    window._active_stage_session = window.session
    window._preview_mode = "stage"
    window._preview_loaded_resource_id = window.session.document.id

    window._preview_state = "playing"
    window.timeline.set_playhead(0, emit=False)
    window._pattern_preview_client.commands.clear()
    window._sync_active_stage_preview()
    assert [command for command, _payload in window._pattern_preview_client.commands] == [
        "load",
        "seek",
        "play",
    ]
    assert window._pattern_preview_client.commands[1] == ("seek", {"frame": 0})

    window._preview_state = "paused"
    window.timeline.set_playhead(90, emit=False)
    window._pattern_preview_client.commands.clear()
    window._sync_active_stage_preview()
    assert window._pattern_preview_client.commands[1:] == [("seek", {"frame": 90})]

    window.session.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()


def test_loop_span_keyframe_drag_and_compact_two_row_toolbar(qapp_session):
    editor = TimelineEditor()
    track = TimelineTrack(
        name="Muted",
        kind="Property",
        channel="background",
        muted=True,
        clips=[
            TimelineClip(
                name="Looped",
                kind="Property",
                start_frame=12,
                duration_frames=60,
                loop_count=3,
                channel="background",
                enabled=False,
                payload={"value": "#171a24"},
                keyframes=[TimelineKeyframe(0, "#000000"), TimelineKeyframe(60, "#ffffff")],
            )
        ],
    )
    from src.editor.session import SceneEditorSession

    document = SceneEditorSession.new_document()
    document.tracks = [track]
    editor.resize(700, 360)
    editor.show()
    editor.set_document(document)
    qapp_session.processEvents()

    clip_item = next(
        item
        for item in editor.view.graphics_scene.items()
        if isinstance(item, TimelineClipItem)
    )
    assert clip_item.boundingRect().width() == 60 * 3 * editor.pixels_per_frame
    assert clip_item.track_muted is True
    assert clip_item.enabled is False
    editor.set_active_clips([track.clips[0].id])
    assert clip_item.active is True

    markers = [
        item
        for item in editor.view.graphics_scene.items()
        if isinstance(item, TimelineKeyframeItem)
    ]
    assert len(markers) == 2
    moved = next(item for item in markers if item.frame == 0)
    events = []
    editor.keyframeGeometryRequested.connect(
        lambda clip_id, keyframe_id, frame: events.append((clip_id, keyframe_id, frame))
    )
    moved.setPos(37 * editor.pixels_per_frame, 7)
    moved._commit_position()
    assert events[-1] == (track.clips[0].id, moved.keyframe_id, 36)

    add_track = editor.findChild(QPushButton, "timelineAddTrack")
    add_clip = editor.findChild(QPushButton, "timelineAddClip")
    assert add_clip.y() > add_track.y()
    assert add_clip.geometry().right() <= editor.width()
    del moved, markers, clip_item
    editor.close()
    editor.deleteLater()
    qapp_session.processEvents()


def test_clip_supports_real_mouse_move_and_both_edge_trims(qapp_session):
    from src.editor.session import SceneEditorSession

    editor = TimelineEditor()
    track = TimelineTrack(
        name="Pattern",
        kind="Pattern",
        channel="main",
        clips=[TimelineClip(name="Ring", kind="Pattern", start_frame=60, duration_frames=120, channel="main")],
    )
    document = SceneEditorSession.new_document()
    document.tracks = [track]
    editor.resize(900, 360)
    editor.show()
    editor.set_zoom(1.0)
    editor.set_document(document)
    qapp_session.processEvents()
    events = []
    editor.clipGeometryRequested.connect(
        lambda clip_id, start, duration: events.append((clip_id, start, duration))
    )

    def current_item():
        return next(
            item
            for item in editor.view.graphics_scene.items()
            if isinstance(item, TimelineClipItem)
        )

    def drag(start, end):
        QTest.mousePress(editor.view.viewport(), Qt.LeftButton, pos=start)
        QApplication.sendEvent(
            editor.view.viewport(),
            QMouseEvent(
                QMouseEvent.MouseMove,
                end,
                editor.view.viewport().mapToGlobal(end),
                Qt.NoButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )
        qapp_session.processEvents()
        QTest.mouseRelease(editor.view.viewport(), Qt.LeftButton, pos=end)
        qapp_session.processEvents()

    item = current_item()
    center = editor.view.mapFromScene(item.scenePos() + QPointF(40, CLIP_HEIGHT / 2))
    moved = center + QPoint(30, 0)
    drag(center, moved)
    assert events[-1][1:] == (90, 120)
    # Mirror the editor command/rebuild that consumes the request in the main
    # window before beginning the next independent gesture.
    track.clips[0].start_frame = 90
    editor.set_document(document)
    qapp_session.processEvents()

    item = current_item()
    right = editor.view.mapFromScene(
        item.scenePos() + QPointF(item.boundingRect().width() - 2, CLIP_HEIGHT / 2)
    )
    drag(right, right + QPoint(30, 0))
    assert events[-1][1:] == (90, 150)
    track.clips[0].duration_frames = 150
    editor.set_document(document)
    qapp_session.processEvents()

    item = current_item()
    left = editor.view.mapFromScene(item.scenePos() + QPointF(2, CLIP_HEIGHT / 2))
    drag(left, left + QPoint(30, 0))
    assert events[-1][1:] == (120, 120)

    editor.close()
    editor.deleteLater()
    qapp_session.processEvents()


def test_ctrl_wheel_zooms_without_mutating_document(qapp_session):
    from src.editor.session import SceneEditorSession

    editor = TimelineEditor()
    document = SceneEditorSession.new_document()
    editor.resize(700, 320)
    editor.show()
    editor.set_document(document)
    before = document.to_dict()
    before_zoom = editor.pixels_per_frame
    local = QPointF(300, 160)
    event = QWheelEvent(
        local,
        editor.view.viewport().mapToGlobal(local.toPoint()),
        QPoint(),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.ControlModifier,
        Qt.NoScrollPhase,
        False,
    )
    editor.view.wheelEvent(event)
    qapp_session.processEvents()

    assert editor.pixels_per_frame > before_zoom
    assert document.to_dict() == before
    editor.close()
    editor.deleteLater()
    qapp_session.processEvents()


def test_shift_wheel_pans_timeline_horizontally(qapp_session):
    from src.editor.session import SceneEditorSession

    editor = TimelineEditor()
    document = SceneEditorSession.new_document()
    editor.resize(700, 320)
    editor.show()
    editor.set_document(document)
    qapp_session.processEvents()
    scroll_bar = editor.view.horizontalScrollBar()
    scroll_bar.setValue(scroll_bar.minimum())
    before = scroll_bar.value()
    local = QPointF(300, 160)
    event = QWheelEvent(
        local,
        editor.view.viewport().mapToGlobal(local.toPoint()),
        QPoint(),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.ShiftModifier,
        Qt.NoScrollPhase,
        False,
    )
    editor.view.wheelEvent(event)
    qapp_session.processEvents()

    assert scroll_bar.value() > before
    editor.close()
    editor.deleteLater()
    qapp_session.processEvents()


def test_keyframe_inspector_table_edit_is_undoable(tmp_path, qapp_session):
    window = _window(tmp_path, qapp_session)
    document = window.session.document
    track = TimelineTrack(
        name="Background",
        kind="Property",
        channel="background",
        target_id=document.root.id,
    )
    clip = TimelineClip(
        name="Tint",
        kind="Property",
        start_frame=0,
        duration_frames=60,
        channel="background",
        target_id=document.root.id,
        payload={"value": "#171a24"},
        keyframes=[TimelineKeyframe(0, "#171a24")],
    )
    window.session.apply(AddTrackCommand(document, track))
    window.session.apply(AddClipCommand(document, track.id, clip))
    window._refresh()
    window._timeline_clip_selected(track.id, clip.id)
    qapp_session.processEvents()
    table = window.inspector.findChild(QTableWidget, "timelineKeyframeTable")

    table.item(0, 0).setText("24")
    qapp_session.processEvents()

    assert clip.keyframes[0].frame == 24
    assert window.session.undo()
    assert clip.keyframes[0].frame == 0
    del table
    window.session.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()
