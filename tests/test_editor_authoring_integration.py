"""Cross-domain editor authoring and formal-preview integration regressions.

These tests exercise public behavior across the scene, UI, background,
preview, and plugin boundaries:

* formal StageRunner statistics move the owner viewport and timeline;
* the Qt host remains a foreign-window host, not a gameplay renderer;
* UI resize, scene-tree mutation, resource drop, and Undo/Redo are real edits;
* background transform gizmos report move/scale/rotation and use commands;
* UI/background previews call the formal renderer path;
* frame-driven background bindings are observable and reversible; and
* closing the editor deactivates SDK plugins.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.authoring import ResourceStore, build_default_resource_type_registry
from src.authoring.resources import BACKGROUND_RESOURCE_TYPE, UI_RESOURCE_TYPE
from src.core.project_context import ProjectContext
from src.editor import TimelineClip, TimelineKeyframe, TimelineTrack, make_node
from src.editor.app import EditorMainWindow
from src.editor.preview_process import PatternPreviewProcess
from src.editor.runtime_preview import RuntimePreviewHost
from src.editor.session import SceneEditorSession
from src.editor.panels.ui_workspace import BackgroundCanvas, UICanvas
from src.game.background_render.document import BackgroundDocument
from src.ui.document import UIDocument, UIDocumentNode

from src.qt_compat.QtCore import QPointF, Qt


REPOSITORY = Path(__file__).resolve().parents[1]


def _project(tmp_path: Path) -> ProjectContext:
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True, exist_ok=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def _ui_document() -> tuple[UIDocument, UIDocumentNode, UIDocumentNode]:
    document = UIDocument.new("Luna HUD")
    root = UIDocumentNode(
        node_type="panel",
        name="root",
        width=384.0,
        height=448.0,
    )
    title = UIDocumentNode(
        node_type="text",
        name="title",
        x=12.0,
        y=16.0,
        width=120.0,
        height=24.0,
        text="Luna",
    )
    image = UIDocumentNode(
        node_type="image",
        name="portrait",
        x=32.0,
        y=64.0,
        width=48.0,
        height=48.0,
        texture="",
    )
    root.add_child(title)
    root.add_child(image)
    document.root = root
    document.validate()
    return document, title, image


def _background_document() -> BackgroundDocument:
    return BackgroundDocument.from_legacy(
        {
            "name": "Luna Background",
            "description": "acceptance fixture",
            "textures": {"sky": {"path": "sky.png"}},
            "camera": {
                "eye": [0.0, 0.0, 1.0],
                "at": [0.0, 0.0, 0.0],
                "up": [0.0, 1.0, 0.0],
                "fovy": 0.8,
                "z_near": 0.1,
                "z_far": 10.0,
            },
            "fog": {"enabled": False, "color": [0, 0, 0, 255], "start": 0.0, "end": 10.0},
            "scroll": {"base_speed": 0.0, "direction": [0.0, 1.0]},
            "layers": [
                {
                    "name": "sky",
                    "texture": "sky",
                    "z_order": 0,
                    "z_depth": 0.0,
                    "blend_mode": "normal",
                    "alpha": 1.0,
                    "scroll_multiplier": 1.0,
                    "tile": {"x_range": [0, 1], "y_range": [0, 1], "size": 1.0},
                    "variants": [],
                    "enabled": True,
                    "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0},
                }
            ],
        }
    )


def _moving_scene():
    scene = SceneEditorSession.new_document("Luna Moving Stage")
    boss = make_node("Boss", name="Moving Boss")
    boss.properties.update({"x": 192.0, "y": 112.0})
    scene.root.children.append(boss)
    track = TimelineTrack(
        name="Boss Movement",
        kind="Movement",
        channel="position",
        target_id=boss.id,
    )
    clip = TimelineClip(
        name="Move",
        kind="Movement",
        start_frame=0,
        duration_frames=30,
        channel="position",
        target_id=boss.id,
        keyframes=[
            TimelineKeyframe(0, {"x": 192.0, "y": 112.0}),
            TimelineKeyframe(30, {"x": 288.0, "y": 112.0}),
        ],
    )
    track.clips.append(clip)
    scene.tracks.append(track)
    scene.validate()
    return scene, boss, clip


def _matching(client: PatternPreviewProcess, request_id: str, event: str) -> list[dict]:
    return [
        message
        for message in client.events
        if message.get("event") == event and message.get("request_id") == request_id
    ]


class _MouseEvent:
    def __init__(self, point: QPointF, button=Qt.LeftButton):
        self._point = point
        self._button = button

    def pos(self):
        return self._point

    def button(self):
        return self._button

    def accept(self):
        pass


class _BackgroundRenderer:
    class Camera:
        z_near = 0.1
        z_far = 10.0

    def __init__(self):
        self.camera = self.Camera()
        self.loaded: list[str] = []

    def load_texture(self, path: str) -> bool:
        self.loaded.append(path)
        return True

    def set_camera(self, eye, at, up, fovy):
        self.camera.eye = tuple(eye)
        self.camera.at = tuple(at)
        self.camera.up = tuple(up)
        self.camera.fovy = fovy

    def set_fog(self, color, start, end, enabled):
        self.camera.fog_color = tuple(color)
        self.camera.fog_start = start
        self.camera.fog_end = end
        self.camera.fog_enabled = enabled


def test_formal_preview_host_is_foreign_window_only() -> None:
    source = (REPOSITORY / "src" / "editor" / "runtime_preview.py").read_text(
        encoding="utf-8"
    )
    worker = (REPOSITORY / "tools" / "preview_pattern.py").read_text(encoding="utf-8")

    assert "QWindow.fromWinId" in source
    assert "QWidget.createWindowContainer" in source
    assert "QPainter(" not in source
    assert "import glfw" in worker
    assert "import moderngl" in worker
    assert "OptimizedBulletPool(max_bullets=max_bullets" in worker
    assert "StageRunner" in worker

    host = RuntimePreviewHost()
    assert host.objectName() == "runtimePreviewHost"
    assert host.is_attached is False
    host.detach()


def test_formal_stage_trace_moves_owner_overlay_and_timeline(
    tmp_path: Path, qapp_session
) -> None:
    project = _project(tmp_path)
    scene, boss, clip = _moving_scene()
    path = ResourceStore(project).save(scene, "game_content/stages/moving.pystg.json")

    window = EditorMainWindow(project)
    client = PatternPreviewProcess(project)
    try:
        window.document_service.open_document(path)
        qapp_session.processEvents()
        owner = window.session
        before = owner.document.to_dict()
        owner_viewport = window._document_widgets[owner.document.id]
        item = owner_viewport._items[boss.id]
        authored_position = (item.x(), item.y())

        assert client.start(headless=True, max_bullets=2048)
        assert client.wait_for(lambda: client.ready)
        load_id = client.send_command("load", {"document": scene.to_dict()})
        assert client.wait_for(lambda: bool(_matching(client, load_id, "response")))
        assert _matching(client, load_id, "response")[0]["payload"]["ok"] is True

        seek_id = client.send_command("seek", {"frame": 15})
        assert client.wait_for(lambda: bool(_matching(client, seek_id, "statistics")))
        stats = _matching(client, seek_id, "statistics")[-1]["payload"]
        assert stats["mode"] == "stage"
        assert stats["frame"] == 15
        assert clip.id in stats["active_clips"]
        assert stats["node_state"][boss.id] != {}

        window._active_stage_session = owner
        window._preview_mode = "stage"
        window._preview_loaded_resource_id = owner.document.id
        window.preview_service._handle_pattern_preview_event({"event": "statistics", "payload": stats})
        qapp_session.processEvents()

        assert window.timeline.playhead_frame == 15
        assert window.runtime_overlay is not None
        assert window.runtime_overlay.document_id == owner.document.id
        assert window.runtime_overlay.frame == 15
        item = owner_viewport._items[boss.id]
        assert item._runtime_pose is True
        assert (item.x(), item.y()) != authored_position
        assert owner.document.to_dict() == before
        assert owner.is_dirty is False

        stop_id = client.send_command("stop")
        assert client.wait_for(lambda: bool(_matching(client, stop_id, "statistics")))
        stopped = _matching(client, stop_id, "statistics")[-1]["payload"]
        window.preview_service._handle_pattern_preview_event({"event": "statistics", "payload": stopped})
        qapp_session.processEvents()
        assert window.timeline.playhead_frame == 0
        assert owner_viewport._items[boss.id]._runtime_pose is False
        assert owner.document.to_dict() == before
    finally:
        client.stop()
        window.close()
        qapp_session.processEvents()


def test_ui_canvas_resize_is_a_geometry_commit(qapp_session) -> None:
    del qapp_session
    canvas = UICanvas()
    document, _title, child = _ui_document()
    canvas.set_document(document, (384, 448))
    item = canvas.item_for_node(child.id)
    assert item is not None
    committed: list[tuple] = []
    canvas.nodeGeometryCommitted.connect(lambda *args: committed.append(args))

    original_width = float(child.width)
    original_height = float(child.height)
    corner = item.rect().bottomRight()
    item.mousePressEvent(_MouseEvent(corner))
    item.mouseMoveEvent(
        _MouseEvent(QPointF(corner.x() + 20.0, corner.y() + 12.0))
    )
    item.mouseReleaseEvent(
        _MouseEvent(QPointF(corner.x() + 20.0, corner.y() + 12.0))
    )

    assert len(committed) == 1
    assert child.width == original_width
    assert child.height == original_height
    assert committed[0][0] == child.id
    assert committed[0][3] > original_width
    assert committed[0][4] > original_height
    canvas.close()


def test_ui_window_mutation_resource_drop_and_undo_redo(tmp_path: Path, qapp_session) -> None:
    project = _project(tmp_path)
    document, title, image = _ui_document()
    path = ResourceStore(project).save(document, "game_content/ui/hud.pystg.json")
    window = EditorMainWindow(project)
    try:
        window.document_service.open_document(path)
        qapp_session.processEvents()
        workspace = window.central_tabs.currentWidget()
        loaded = window.session.document
        loaded_root = loaded.root
        loaded_title = next(node for node, _depth in loaded_root.walk() if node.name == "title")
        loaded_image = next(node for node, _depth in loaded_root.walk() if node.name == "portrait")

        workspace.nodeCreateRequested.emit(loaded_root.id, "text", "Added")
        qapp_session.processEvents()
        added = next(node for node, _depth in loaded_root.walk() if node.name == "Added")
        assert added.id != loaded_root.id
        window.undo()
        assert all(node.id != added.id for node, _depth in loaded_root.walk())
        window.redo()
        assert any(node.id == added.id for node, _depth in loaded_root.walk())

        workspace.canvas.resourceDropped.emit(loaded_image.id, "res://assets/images/ui.png")
        qapp_session.processEvents()
        assert loaded_image.texture == "res://assets/images/ui.png"
        window.undo()
        assert loaded_image.texture == ""
        window.redo()
        assert loaded_image.texture == "res://assets/images/ui.png"

        workspace.nodeRemoveRequested.emit(loaded_title.id)
        qapp_session.processEvents()
        assert all(node.id != loaded_title.id for node, _depth in loaded_root.walk())
        window.undo()
        assert any(node.id == loaded_title.id for node, _depth in loaded_root.walk())
        window.redo()
        assert all(node.id != loaded_title.id for node, _depth in loaded_root.walk())
    finally:
        window.close()
        qapp_session.processEvents()


def test_ui_formal_preview_delegates_to_renderer() -> None:
    document, _title, _image = _ui_document()
    registry = build_default_resource_type_registry()
    spec = registry[UI_RESOURCE_TYPE]
    compiled = spec.compiler(document, viewport_width=640, viewport_height=360)

    class Recorder:
        def __init__(self):
            self.elements = None

        def render_hud(self, payload):
            self.elements = payload.get_render_elements()

    renderer = Recorder()
    result = spec.preview_handler(compiled, renderer=renderer)
    assert result == renderer.elements
    assert result
    assert all("position" in element for element in result)


def test_background_canvas_gizmo_reports_move_scale_and_rotation(qapp_session) -> None:
    del qapp_session
    canvas = BackgroundCanvas()
    document = _background_document()
    canvas.set_document(document)
    events: list[tuple] = []
    canvas.layerTransformCommitted.connect(lambda *args: events.append(args))
    item = canvas._items[0]

    events.clear()
    item.setPos(0.25, -0.1)
    item.setScale(1.5)
    item.setRotation(27.0)

    assert events
    assert any(event[1] == pytest.approx(0.25) for event in events)
    assert any(event[3] == pytest.approx(1.5) for event in events)
    assert events[-1][4] == pytest.approx(27.0)
    canvas.close()


def test_background_transform_command_undo_redo_preserves_all_components(
    tmp_path: Path, qapp_session
) -> None:
    project = _project(tmp_path)
    document = _background_document()
    path = ResourceStore(project).save(document, "game_content/backgrounds/luna.pystg.json")
    from src.authoring.commands.background import SetBackgroundPropertyCommand
    from src.editor.document_manager import DocumentManager

    manager = DocumentManager(project, create_initial_scene=False)
    session = manager.open(path)
    canvas = BackgroundCanvas()
    canvas.set_document(session.document)

    def apply_transform(index, x, y, scale, rotation):
        session.apply(
            SetBackgroundPropertyCommand(
                session.document,
                f"layers.{int(index)}.transform",
                {
                    "x": float(x),
                    "y": float(y),
                    "scale": float(scale),
                    "rotation": float(rotation),
                },
            )
        )

    canvas.layerTransformCommitted.connect(apply_transform)
    canvas.layerTransformCommitted.emit(0, 0.25, -0.1, 1.5, 27.0)
    transform = session.document.body["layers"][0]["transform"]
    assert transform == {
        "x": pytest.approx(0.25),
        "y": pytest.approx(-0.1),
        "scale": pytest.approx(1.5),
        "rotation": pytest.approx(27.0),
    }
    assert session.undo()
    assert session.document.body["layers"][0]["transform"] == {
        "x": 0.0,
        "y": 0.0,
        "scale": 1.0,
        "rotation": 0.0,
    }
    assert session.redo()
    assert session.document.body["layers"][0]["transform"]["rotation"] == pytest.approx(27.0)
    canvas.close()
    qapp_session.processEvents()


def test_background_binding_is_undoable_and_changes_formal_quads(
    tmp_path: Path, qapp_session
) -> None:
    project = _project(tmp_path)
    document = _background_document()
    path = ResourceStore(project).save(document, "game_content/backgrounds/luna.pystg.json")
    window = EditorMainWindow(project)
    try:
        window.document_service.open_document(path)
        qapp_session.processEvents()
        workspace = window.central_tabs.currentWidget()
        workspace.binding_target.setText("layers.0.transform.x")
        workspace.binding_expression.setText("frame * 0.01")
        workspace.bindingRequested.emit(
            "layers.0.transform.x", "frame * 0.01"
        )
        qapp_session.processEvents()
        assert window.session.document.body["bindings"]["layers.0.transform.x"] == "frame * 0.01"
        assert workspace.bindings.count() == 1
        window.undo()
        assert not window.session.document.body.get("bindings")
        window.redo()
        assert window.session.document.body["bindings"]["layers.0.transform.x"] == "frame * 0.01"
    finally:
        window.close()
        qapp_session.processEvents()

    document.body["bindings"] = {"layers.0.transform.x": "frame * 0.01"}
    document.validate()
    registry = build_default_resource_type_registry()
    spec = registry[BACKGROUND_RESOURCE_TYPE]
    compiled = spec.compiler(document)
    renderer = _BackgroundRenderer()
    before = document.to_dict()
    frame0 = spec.preview_handler(
        compiled, renderer=renderer, base_dir=str(tmp_path), frame=0
    )
    frame30 = spec.preview_handler(
        compiled, renderer=renderer, base_dir=str(tmp_path), frame=30
    )
    assert frame0 and frame30
    assert frame0[0]["v0"] != frame30[0]["v0"]
    assert document.to_dict() == before


def test_editor_close_deactivates_sdk_plugins(tmp_path: Path, qapp_session) -> None:
    window = EditorMainWindow(_project(tmp_path))
    called: list[bool] = []
    window.plugin_registry.sdk.deactivate_all = lambda: called.append(True)
    window.close()
    qapp_session.processEvents()
    assert called == [True]
