import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.qt_compat.QtCore import QPointF, Qt
from src.qt_compat.QtGui import QColor, QDropEvent, QPixmap
from src.qt_compat.QtWidgets import QApplication, QLabel

from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow, NodeGraphicsItem, SceneViewport
from src.editor.asset_index import AssetRecord
from src.authoring.scene.node_types import make_node
from src.editor.resource_browser import (
    RECORD_ROLE,
    RESOURCE_MIME_TYPE,
    AssetFilterProxyModel,
    AssetListModel,
)
from src.editor.workbench import EditorPlugin


def _app():
    return QApplication.instance() or QApplication([])


def test_asset_list_model_filters_and_exports_drag_payload(tmp_path):
    app = _app()
    records = (
        AssetRecord(
            uri="res://assets/a.png",
            path=tmp_path / "assets" / "a.png",
            project_path="assets/a.png",
            kind="image",
            name="a.png",
        ),
        AssetRecord(
            uri="res://game_content/demo.py",
            path=tmp_path / "game_content" / "demo.py",
            project_path="game_content/demo.py",
            kind="script",
            name="demo.py",
        ),
    )
    model = AssetListModel(records)
    proxy = AssetFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_kind("script")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 0), RECORD_ROLE).name == "demo.py"
    proxy.set_kind("all")
    proxy.set_query("assets/")
    assert proxy.rowCount() == 1

    mime = model.mimeData([model.index(0, 0)])
    assert mime.hasFormat(RESOURCE_MIME_TYPE)
    payload = json.loads(bytes(mime.data(RESOURCE_MIME_TYPE)).decode("utf-8"))
    assert payload["resource_value"] == "res://assets/a.png"
    app.processEvents()


def test_scene_viewport_accepts_resource_mime_drop(tmp_path):
    app = _app()
    record = AssetRecord(
        uri="res://assets/orb.png",
        path=tmp_path / "assets" / "orb.png",
        project_path="assets/orb.png",
        kind="image",
        name="orb.png",
    )
    model = AssetListModel((record,))
    mime = model.mimeData([model.index(0, 0)])
    event = QDropEvent(
        QPointF(40, 50),
        Qt.CopyAction,
        mime,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    viewport = SceneViewport(ProjectContext(tmp_path))
    assert viewport.runtime_position(192.0, 224.0) == (0.0, 0.0)
    dropped = []
    viewport.resourceDropped.connect(
        lambda payload, x, y: dropped.append((payload, x, y))
    )

    viewport.dropEvent(event)

    assert event.isAccepted()
    assert dropped[0][0]["resource_value"] == "res://assets/orb.png"
    assert dropped[0][0]["kind"] == "image"
    viewport.close()
    app.processEvents()


def test_workbench_contains_assets_and_assigns_resources(tmp_path):
    app = _app()
    image = tmp_path / "assets" / "images" / "orb.png"
    image.parent.mkdir(parents=True)
    pixmap = QPixmap(12, 10)
    pixmap.fill(QColor("#ff00ff"))
    assert pixmap.save(str(image))

    window = EditorMainWindow(ProjectContext(tmp_path))
    assert [
        window.bottom_tabs.tabText(index)
        for index in range(window.bottom_tabs.count())
    ] == ["Output", "Timeline", "Preview", "Assets"]
    assert window.findChild(QLabel, "assetSummary").text() == "1 resources"
    assert window.findChild(
        type(window.action_run),
        "pluginAction_bullet_aliases",
    ) is not None

    record = window.resource_browser.index.find("res://assets/images/orb.png")
    window.workbench_service.resource_activated(record)
    sprite = window.session.node(window._selected_id)
    assert sprite.type == "Sprite"
    assert sprite.properties["texture"] == "res://assets/images/orb.png"

    window.workbench_service.resource_dropped(
        {
            "kind": "image",
            "name": "orb.png",
            "resource_value": "res://assets/images/orb.png",
        },
        123.0,
        234.0,
    )
    dropped = window.session.node(window._selected_id)
    assert dropped.properties["x"] == 123.0
    assert dropped.properties["y"] == 234.0

    central = EditorPlugin(
        id="bullet_aliases",
        title="Bullet Aliases",
        description="test",
        mode="central",
        factory=lambda: QLabel("embedded"),
    )
    window.plugin_registry._plugins["bullet_aliases"] = central
    window.workbench_service.open_plugin("bullet_aliases")
    assert window.central_tabs.count() == 2
    assert window.central_tabs.currentWidget().text() == "embedded"
    window.document_service.close_central_tab(1)
    assert window.central_tabs.count() == 1

    window.session.reset()
    window.close()
    app.processEvents()


def test_sprite_preview_supports_json_subresource(tmp_path):
    app = _app()
    atlas = tmp_path / "assets" / "atlas.png"
    atlas.parent.mkdir(parents=True)
    source = QPixmap(32, 16)
    source.fill(QColor("#00ff00"))
    assert source.save(str(atlas))
    config = atlas.with_suffix(".json")
    config.write_text(
        json.dumps(
            {
                "__image_filename": "atlas.png",
                "sprites": {"left": {"rect": [0, 0, 16, 16]}},
            }
        ),
        encoding="utf-8",
    )
    node = make_node("Sprite")
    node.properties["texture"] = "res://assets/atlas.json#left"

    preview = NodeGraphicsItem._load_pixmap(node, ProjectContext(tmp_path))

    assert not preview.isNull()
    assert preview.width() == 64
    assert preview.height() == 64
    app.processEvents()
