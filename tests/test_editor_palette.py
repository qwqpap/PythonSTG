"""Node palette behaviour: search, compatibility, references, templates, undo."""

from __future__ import annotations

from pathlib import Path

from src.authoring import dsl
from src.authoring.program import DropPlacement, find_node, node_from_palette
from src.core.project_context import ProjectContext
from src.editor.node_palette import PALETTE_ENTRIES, PROTOTYPE_MIME, NodePalette
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtCore import Qt
from src.qt_compat.QtWidgets import QApplication


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Parallel, Stage, Wait, template\n\n"
        "@template\n"
        "def pause(frames: int = 5):\n"
        "    return [Wait(frames)]\n\n"
        "stage = Stage('stage', 'Stage', body=[Wait(1, uid='wait'), Parallel([[]], uid='par')])\n",
        encoding="utf-8",
    )
    return root


def _window(tmp_path: Path) -> EditorWindow:
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(_project(tmp_path / "authoring"))
    session.select_unit("stage")
    window = EditorWindow(session)
    window.show()
    QApplication.processEvents()
    window.inspector_dock.hide()
    window.timeline_dock.hide()
    QApplication.processEvents()
    return window


def _items(palette: NodePalette):
    def walk(item):
        yield item
        for index in range(item.childCount()):
            yield from walk(item.child(index))

    for top in range(palette.tree.topLevelItemCount()):
        yield from walk(palette.tree.topLevelItem(top))


def test_palette_covers_every_public_node_kind():
    covered = {entry.kind for entry in PALETTE_ENTRIES}
    assert covered == set(dsl.NODE_CONSTRUCTORS)


def test_palette_search_filters_and_defaults_filter_incompatible(tmp_path, qapp_session):
    window = _window(tmp_path)
    palette = window.node_palette
    session = window.session

    # Repeat is legal in a Stage body and needs no reference target, so the
    # search must find it by its Chinese label and keep it enabled.
    session.select_node("wait")
    QApplication.processEvents()
    palette.search.setText("重复")
    QApplication.processEvents()
    visible = [item for item in _items(palette) if item.parent() is not None]
    assert visible, "重复 must match the Chinese label of the Repeat node"
    assert all("重复" in item.text(0) for item in visible)
    assert all(not item.isDisabled() for item in visible)
    palette.search.setText("")
    QApplication.processEvents()

    # Movement actions are illegal in a Stage: the default compatibility filter
    # hides them, and 显示全部 reveals them grayed out with the exact reason.
    incompatible = [
        item
        for item in _items(palette)
        if item.parent() is not None and "移动到" in item.text(0)
    ]
    assert incompatible == []
    palette.show_all.setChecked(True)
    QApplication.processEvents()
    grayed = [
        item
        for item in _items(palette)
        if item.parent() is not None and "移动到" in item.text(0)
    ]
    assert grayed and all(item.isDisabled() and item.toolTip(0) for item in grayed)
    window.close()


def test_palette_double_click_and_toolbar_add_share_one_undo_stack(
    tmp_path, qapp_session
):
    window = _window(tmp_path)
    session = window.session
    palette = window.node_palette

    session.select_node("wait")
    QApplication.processEvents()
    palette.insert_requested.emit("Repeat")
    QApplication.processEvents()
    container = session.current_node_uid
    assert container is not None
    assert session.program.get_unit("stage").body[1].kind == "Repeat"
    assert session.undo_stack.count() == 1

    session.undo_stack.undo()
    assert [node.kind for node in session.program.get_unit("stage").body] == [
        "Wait",
        "Parallel",
    ]
    session.undo_stack.redo()
    assert container is not None
    window.close()


def test_palette_remember_keeps_recent_entries_session_only(tmp_path, qapp_session):
    window = _window(tmp_path)
    palette = window.node_palette
    session = window.session

    session.select_node("wait")
    QApplication.processEvents()
    window.insert_palette_node("At", DropPlacement.AFTER, target_uid="wait")
    assert "At" in palette._recent

    reopened = EditorSession(project_context=ProjectContext(tmp_path))
    reopened.open_project(tmp_path / "authoring")
    reopened.select_unit("stage")
    other = NodePalette()
    other.set_context(reopened.program, "stage", None, DropPlacement.AFTER)
    assert other._recent == []
    other.close()
    window.close()


def test_reference_nodes_require_explicit_existing_targets(tmp_path, qapp_session):
    window = _window(tmp_path)
    palette = window.node_palette

    compatibility = palette.compatibility(palette.entry("RunWave"))
    assert not compatibility[0]
    assert "Wave" in compatibility[1]

    window.close()


def test_templates_stay_aggregated_template_calls(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    templates = session.palette_templates
    assert templates, "the local @template must appear in the palette context"
    local = next(target for target in templates if target.symbol == "pause")
    assert local.identity.endswith(".pause")

    session.select_node("wait")
    QApplication.processEvents()
    node = window.insert_palette_node(
        f"template:{local.identity}", DropPlacement.AFTER, target_uid="wait"
    )
    assert node is not None and node.kind == "TemplateCall"
    stage_after = session.program.get_unit("stage")
    assert stage_after.body[1].kind == "TemplateCall"
    window.close()
