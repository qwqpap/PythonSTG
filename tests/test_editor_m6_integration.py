"""Phase 6 gate acceptance: UI and background share the editor infrastructure.

These tests lock the M6 gate: UI and background documents open, edit, Undo/
Redo, save, and reopen through the same DocumentManager/ResourceStore/
registry channels. Do not edit, skip, or xfail them.
"""

import json
from pathlib import Path

import pytest

from src.authoring import ResourceStore, build_default_resource_type_registry
from src.core.project_context import ProjectContext
from src.editor.document_manager import DocumentManager
from src.authoring.commands.ui import SetUINodePropertyCommand
from src.game.background_render.data_driven_background import DataDrivenBackground
from src.game.background_render.document import BackgroundDocument
from src.ui.document import UIDocument, UIDocumentNode

REPOSITORY = Path(__file__).resolve().parents[1]


class _DummyCamera:
    def __init__(self):
        self.z_near = 0.01
        self.z_far = 10.0
        self.fog_start = 0.0
        self.fog_end = 10.0
        self.fog_color = (0.0, 0.0, 0.0, 1.0)
        self.fog_enabled = False


class _DummyRenderer:
    def __init__(self):
        self.camera = _DummyCamera()

    def load_texture(self, path: str) -> bool:
        return True

    def set_camera(self, eye, at, up, fovy):
        self.camera.eye = eye
        self.camera.at = at
        self.camera.up = up
        self.camera.fovy = fovy

    def set_fog(self, color, start, end, enabled):
        self.camera.fog_color = color
        self.camera.fog_start = start
        self.camera.fog_end = end
        self.camera.fog_enabled = enabled


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def _ui_document():
    document = UIDocument.new("Gate HUD")
    root = UIDocumentNode(node_type="panel", name="root")
    title = UIDocumentNode(
        node_type="text", name="title", text="Title", y=4.0
    )
    root.add_child(title)
    document.root = root
    return document


def _background_document():
    path = REPOSITORY / "assets" / "images" / "background" / "lake.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return BackgroundDocument.from_legacy(payload)


# --------------------------------------------------------------------------
# Shared infrastructure
# --------------------------------------------------------------------------


def test_ui_and_background_share_the_typed_registry(tmp_path):
    registry = build_default_resource_type_registry()

    ui = registry.load(_ui_document().to_dict())
    background = registry.load(_background_document().to_dict())

    assert isinstance(ui, UIDocument)
    assert isinstance(background, BackgroundDocument)


def test_ui_and_background_save_and_reload_through_resource_store(tmp_path):
    project = _project(tmp_path)
    store = ResourceStore(project)
    store.save(_ui_document(), "game_content/ui/hud.pystg.json")
    store.save(
        _background_document(), "game_content/backgrounds/lake.pystg.json"
    )

    ui = store.load("game_content/ui/hud.pystg.json")
    background = store.load("game_content/backgrounds/lake.pystg.json")

    assert isinstance(ui, UIDocument)
    assert isinstance(background, BackgroundDocument)


# --------------------------------------------------------------------------
# Editor document channels
# --------------------------------------------------------------------------


def test_ui_document_opens_edits_undo_redo_and_reopens(tmp_path):
    project = _project(tmp_path)
    store = ResourceStore(project)
    store.save(_ui_document(), "game_content/ui/hud.pystg.json")

    manager = DocumentManager(project, create_initial_scene=False)
    session = manager.open("game_content/ui/hud.pystg.json")
    assert isinstance(session.document, UIDocument)

    node_id = session.document.root.children[0].id
    session.apply(
        SetUINodePropertyCommand(session.document, node_id, {"y": 40.0})
    )
    assert session.document.root.children[0].y == 40.0
    assert session.undo()
    assert session.document.root.children[0].y == 4.0
    assert session.redo()
    assert session.document.root.children[0].y == 40.0

    path = manager.save(session)
    manager.close(session)
    reopened = manager.open(path)
    assert isinstance(reopened.document, UIDocument)
    assert reopened.document.root.children[0].y == 40.0
    assert reopened.document.root.children[0].id == node_id


def test_background_document_opens_and_survives_reopen(tmp_path):
    project = _project(tmp_path)
    store = ResourceStore(project)
    store.save(
        _background_document(), "game_content/backgrounds/lake.pystg.json"
    )

    manager = DocumentManager(project, create_initial_scene=False)
    session = manager.open("game_content/backgrounds/lake.pystg.json")
    assert isinstance(session.document, BackgroundDocument)

    path = manager.save(session)
    manager.close(session)
    reopened = manager.open(path)
    assert isinstance(reopened.document, BackgroundDocument)
    assert reopened.document.body["layers"] == session.document.body["layers"]


def test_shipped_background_imports_and_renders_through_editor_path(tmp_path):
    project = _project(tmp_path)
    store = ResourceStore(project)
    document = _background_document()
    store.save(document, "game_content/backgrounds/lake.pystg.json")

    loaded = store.load("game_content/backgrounds/lake.pystg.json")

    background = DataDrivenBackground(_DummyRenderer())
    assert background.load_from_dict(
        loaded.to_dict(), str(REPOSITORY / "assets" / "images" / "background"), announce=False
    )
    background.render()
    assert background.get_render_quads()


def test_ui_document_renders_through_the_editor_path(tmp_path):
    project = _project(tmp_path)
    store = ResourceStore(project)
    store.save(_ui_document(), "game_content/ui/hud.pystg.json")

    loaded = store.load("game_content/ui/hud.pystg.json")

    elements = loaded.get_render_elements()
    assert elements
    assert elements[0]["type"] == "text"
