"""M6 workspace regression: opening UI/background documents in the editor.

These tests preserve the M6 editor panels:
opening a UI document must not crash Qt inside the tab-switch signal slot
(regression: 0xC0000409 during a synchronous tree/scene rebuild), and the
background layer summary must populate.
"""

import json
from pathlib import Path

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.game.background_render.document import BackgroundDocument
from src.ui.document import UIDocument, UIDocumentNode

REPOSITORY = Path(__file__).resolve().parents[1]


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}), encoding="utf-8"
    )
    return ProjectContext(tmp_path)


def _ui_document():
    document = UIDocument.new("HUD")
    root = UIDocumentNode(node_type="panel", name="root")
    title = UIDocumentNode(
        node_type="text", name="title", text="Hi", y=4.0
    )
    root.add_child(title)
    document.root = root
    return document


def _background_document():
    payload = json.loads(
        (REPOSITORY / "assets" / "images" / "background" / "lake.json").read_text(
            encoding="utf-8"
        )
    )
    return BackgroundDocument.from_legacy(payload)


def test_ui_document_opens_inside_tab_switch_without_crashing(
    tmp_path, qapp_session
):
    """Regression: opening a UI tab rebuilds tree/canvas without crashing Qt."""
    project = _project(tmp_path)
    ResourceStore(project).save(
        _ui_document(), "game_content/ui/hud.pystg.json"
    )

    window = EditorMainWindow(project)
    window.document_service.open_document(tmp_path / "game_content/ui/hud.pystg.json")
    qapp_session.processEvents()

    from src.editor.panels.ui_workspace import UIWorkspace

    workspace = window.central_tabs.currentWidget()
    assert isinstance(workspace, UIWorkspace)
    assert workspace.tree.topLevelItemCount() > 0
    window.close()
    qapp_session.processEvents()


def test_ui_node_edits_undo_redo_through_the_window(tmp_path, qapp_session):
    project = _project(tmp_path)
    document = _ui_document()
    ResourceStore(project).save(document, "game_content/ui/hud.pystg.json")

    window = EditorMainWindow(project)
    window.document_service.open_document(tmp_path / "game_content/ui/hud.pystg.json")
    qapp_session.processEvents()

    node_id = document.root.children[0].id
    window.ui_document_service.ui_node_selected(node_id)
    window.ui_document_service.ui_node_property_requested(node_id, {"y": 40.0})
    assert window.session.document.root.children[0].y == 40.0
    window.undo()
    assert window.session.document.root.children[0].y == 4.0
    window.redo()
    assert window.session.document.root.children[0].y == 40.0
    window.close()
    qapp_session.processEvents()


def test_background_document_opens_with_layer_summary(tmp_path, qapp_session):
    project = _project(tmp_path)
    ResourceStore(project).save(
        _background_document(), "game_content/backgrounds/lake.pystg.json"
    )

    window = EditorMainWindow(project)
    window.document_service.open_document(tmp_path / "game_content/backgrounds/lake.pystg.json")
    qapp_session.processEvents()

    from src.editor.panels.ui_workspace import BackgroundWorkspace

    workspace = window.central_tabs.currentWidget()
    assert isinstance(workspace, BackgroundWorkspace)
    assert workspace.layers.count() > 0
    window.close()
    qapp_session.processEvents()
