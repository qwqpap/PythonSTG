"""N4.2 timeline slot, inspector, overlay, and navigation contracts."""

from copy import deepcopy

from src.qt_compat.QtCore import QPointF, Qt
from src.qt_compat.QtTest import QTest
from src.qt_compat.QtWidgets import QComboBox, QLabel

from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession, TimelineClip, TimelineTrack
from src.editor.app import EditorMainWindow
from src.editor.panels.timeline_workspace import CLIP_HEIGHT, TimelineClipItem, TimelineEditor


def _reactive_clip():
    return TimelineClip(
        name="Fake hit",
        kind="Reactive",
        start_frame=12,
        duration_frames=60,
        channel="reaction",
        payload={
            "activation": {"kind": "on_event", "event_type": "boss.hit"},
            "reaction": {
                "id": "fake-overload",
                "event_type": "boss.hit",
                "action": "spawn-overload",
                "once_per_scope": False,
            },
            "owner_id": "boss.fake",
        },
    )


def test_timeline_reactive_slot_has_context_badge_and_read_only_overlay(qapp_session):
    document = SceneEditorSession.new_document("Reactive editor")
    track = TimelineTrack(name="Hooks", kind="Reactive", channel="reaction", clips=[_reactive_clip()])
    document.tracks = [track]
    before = deepcopy(document.to_dict())

    editor = TimelineEditor()
    editor.resize(720, 360)
    editor.show()
    editor.set_document(document)
    qapp_session.processEvents()

    picker = editor.findChild(QComboBox, "timelineKindPicker")
    assert picker.findData("Reactive") >= 0
    item = next(
        value
        for value in editor.view.graphics_scene.items()
        if isinstance(value, TimelineClipItem)
    )
    assert item.kind == "Reactive"
    assert item.activation["kind"] == "on_event"

    editor.set_reactive_overlay(
        {
            "active_instances": [{"clip_id": track.clips[0].id, "instance_id": "runtime#1"}],
            "trace": [],
            "diagnostics": [{"clip_id": track.clips[0].id, "reason": "frame_instance_budget"}],
        }
    )
    assert item.active is True
    assert item.conflicts == ("frame_instance_budget",)
    assert document.to_dict() == before
    editor.close()


def test_editor_adds_reactive_track_clip_through_command_stack(tmp_path, qapp_session):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.resize(900, 650)
    window.show()
    qapp_session.processEvents()
    window._timeline_add_track("Reactive")
    track = window.session.document.tracks[0]
    window.timeline.selected_track_id = track.id
    window._timeline_add_clip(track.id)
    assert track.kind == "Reactive"
    assert track.clips[0].payload["activation"]["kind"] == "on_event"
    assert track.clips[0].payload["reaction"]["id"]
    assert window.session.undo()
    assert track.clips == []
    assert window.session.redo()
    assert len(track.clips) == 1
    window.session.revert()
    window.close()
    qapp_session.processEvents()


def test_reactive_clip_inspector_exposes_activation_reaction_and_owner(tmp_path, qapp_session):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.show()
    qapp_session.processEvents()
    track = TimelineTrack(name="Hooks", kind="Reactive", channel="reaction", clips=[_reactive_clip()])
    window.session.document.tracks = [track]
    window._refresh()
    window._timeline_clip_selected(track.id, track.clips[0].id)
    qapp_session.processEvents()
    assert window.inspector.findChild(QLabel, "timelineReactiveActivation").text() == "on_event"
    assert window.inspector.findChild(QLabel, "timelineReactiveReaction").text() == "fake-overload"
    assert window.inspector.findChild(QLabel, "timelineReactiveOwner").text() == "boss.fake"
    window.session.revert()
    window.close()
    qapp_session.processEvents()


def test_default_reactive_clip_actually_arms_on_the_formal_runtime(tmp_path, qapp_session):
    """The clip the editor authors by default must fire, not merely validate.

    The runtime evaluates arming on the frame boundary after a clip starts, so a
    one-frame default window would compile and validate while never reacting to
    anything.
    """

    from src.compiler.stage import compile_stage
    from src.game.bullet.optimized_pool import OptimizedBulletPool
    from src.game.events import EventBus
    from src.game.stage.context import StageContext
    from src.game.stage.program import StageRunner

    class _Player:
        pos = [0.0, -0.75]

    window = EditorMainWindow(ProjectContext(tmp_path))
    window.show()
    qapp_session.processEvents()
    window._timeline_add_track("Reactive")
    track = window.session.document.tracks[0]
    window.timeline.selected_track_id = track.id
    window._timeline_add_clip(track.id)
    clip = track.clips[0]

    program = compile_stage(ProjectContext(tmp_path), window.session.document)
    assert len(program.reactive_clips) == 1
    bus = EventBus()
    context = StageContext(OptimizedBulletPool(max_bullets=64), _Player(), event_bus=bus)
    fired = []

    def action(event, scope):
        fired.append(event.type)
        for _ in range(4):
            yield scope.wait(1)

    context.register_reaction_action(clip.payload["reaction"]["action"], action)
    runner = StageRunner(program)
    runner.start(context)
    bus.emit(clip.payload["activation"]["event_type"], {}, source="boss")
    runner.tick(context)

    assert fired == ["boss.hit"]
    overlay = runner.reactive_overlay
    assert [item["clip_id"] for item in overlay["active_instances"]] == [clip.id]
    assert overlay["trace"]

    window.session.revert()
    window.close()
    qapp_session.processEvents()


def test_double_clicking_a_reactive_slot_navigates_to_its_local_view(tmp_path, qapp_session):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.resize(1000, 700)
    window.show()
    qapp_session.processEvents()
    plain = TimelineClip(
        name="Fan",
        kind="Pattern",
        start_frame=12,
        duration_frames=60,
        channel="pattern",
        payload={"pattern": "ring"},
    )
    reactive = _reactive_clip()
    window.session.document.tracks = [
        TimelineTrack(name="Body", kind="Pattern", channel="pattern", clips=[plain]),
        TimelineTrack(name="Hooks", kind="Reactive", channel="reaction", clips=[reactive]),
    ]
    window._refresh()
    window.timeline.set_zoom(1.0)
    qapp_session.processEvents()

    def double_click(clip_id):
        # Look the item up fresh each time: selecting a clip rebuilds the
        # scene, so a wrapper cached before the first gesture would hand back a
        # position the live scene no longer uses.
        item = next(
            value
            for value in window.timeline.view.graphics_scene.items()
            if isinstance(value, TimelineClipItem) and value.clip_id == clip_id
        )
        viewport = window.timeline.view.viewport()
        point = window.timeline.view.mapFromScene(
            item.scenePos() + QPointF(20, CLIP_HEIGHT / 2)
        )
        # QTest.mouseDClick posts the double-click event alone.  A real double
        # click arrives as click, double-click, release, and the graphics scene
        # needs that trailing release to let go of its mouse grabber -- without
        # it every later click in this test would land on the first clip.
        QTest.mouseClick(viewport, Qt.LeftButton, pos=point)
        QTest.mouseDClick(viewport, Qt.LeftButton, pos=point)
        QTest.mouseRelease(viewport, Qt.LeftButton, pos=point)
        qapp_session.processEvents()

    # A non-reactive clip has no local behaviour view, so entering it must not
    # invent a navigation target.
    double_click(plain.id)
    assert window.session.editor_state.timeline.reactive_navigation is None

    double_click(reactive.id)
    assert window.session.editor_state.timeline.reactive_navigation == (
        "reaction",
        reactive.id,
    )
    # Navigating is a read of the document, never a write to it.
    assert window.session.document.tracks[1].clips[0].payload == reactive.payload
    window.session.revert()
    window.close()
    qapp_session.processEvents()
