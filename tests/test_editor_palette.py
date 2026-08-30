"""Node palette behaviour: search, compatibility, references, templates, undo."""

from __future__ import annotations

import sys
from pathlib import Path

from src.authoring import dsl
from src.authoring.program import DropPlacement, find_node, node_from_palette
from src.core.project_context import ProjectContext
from src.editor.node_palette import PALETTE_ENTRIES, PROTOTYPE_MIME, NodePalette
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtCore import Qt
from src.qt_compat.QtWidgets import QApplication, QSpinBox


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from math import sin\n"
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


def _select_palette_entry(window: EditorWindow, kind: str) -> None:
    palette = window.node_palette
    role = int(Qt.ItemDataRole.UserRole)

    def walk(item):
        yield item
        for index in range(item.childCount()):
            yield from walk(item.child(index))

    for top in range(palette.tree.topLevelItemCount()):
        for item in walk(palette.tree.topLevelItem(top)):
            if item.data(0, role) == kind and not item.isDisabled():
                palette.tree.setCurrentItem(item)
                return
    raise AssertionError(f"palette entry {kind!r} not selectable")


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

    requested = []
    palette.create_reference_requested.disconnect(window._offer_unit_creation)
    palette.create_reference_requested.connect(requested.append)
    assert palette.create_reference_button.isVisible()
    assert "新建" in palette.create_reference_button.text()
    palette.create_reference_button.click()
    assert requested and "Wave" in requested[-1]

    window.close()


def test_templates_stay_aggregated_template_calls(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    templates = session.palette_templates
    assert templates, "the local @template must appear in the palette context"
    local = next(target for target in templates if target.symbol == "pause")
    assert local.identity.endswith(".pause")
    assert all(target.identity != "math.sin" for target in templates)

    session.select_node("wait")
    QApplication.processEvents()
    node = window.insert_palette_node(
        f"template:{local.identity}", DropPlacement.AFTER, target_uid="wait"
    )
    assert node is not None and node.kind == "TemplateCall"
    assert node.arguments["frames"] == 5
    stage_after = session.program.get_unit("stage")
    assert stage_after.body[1].kind == "TemplateCall"
    QApplication.processEvents()
    frames = window.inspector.findChild(QSpinBox, "argument_frames")
    assert frames is not None
    frames.setValue(7)
    frames.editingFinished.emit()
    assert session.current_node.arguments["frames"] == 7
    session.save_all()
    reopened = EditorSession(project_context=ProjectContext(tmp_path))
    reopened.open_project(tmp_path / "authoring")
    template_call = next(
        item
        for item in reopened.program.get_unit("stage").body
        if item.kind == "TemplateCall"
    )
    assert template_call.arguments["frames"] == 7
    window.close()


def test_explicitly_imported_decorated_template_appears_in_palette(
    tmp_path, qapp_session, monkeypatch
):
    module = tmp_path / "palette_template_pack.py"
    module.write_text(
        "from src.authoring.dsl import Wait, template\n\n"
        "raise RuntimeError('palette discovery must not execute this module')\n\n"
        "@template\n"
        "def burst(frames: int = 2, /):\n"
        "    return [Wait(frames)]\n",
        encoding="utf-8",
    )
    root = _project(tmp_path / "authoring")
    stage_path = root / "stage.py"
    stage_path.write_text(
        "from palette_template_pack import burst\n" + stage_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(root)
    targets = session.palette_templates
    assert "palette_template_pack" not in sys.modules
    target = next(target for target in targets if target.symbol == "burst")
    prototype = node_from_palette(
        "TemplateCall",
        session.program,
        "Stage",
        template_target=target,
    )
    assert prototype.positional_arguments == (2,)
    assert prototype.arguments == {}


def test_palette_selection_change_neither_reenters_nor_clones_the_program(
    tmp_path, qapp_session
):
    """Regression: selecting a palette entry must stay instant and safe.

    The old implementation validated every palette entry by cloning and fully
    revalidating the program, and rebuilds re-entered the window's refresh path
    through itemSelectionChanged during clear() -- freezing for seconds and
    crashing Qt's selection model under repeated interaction.
    """

    window = _window(tmp_path)
    session = window.session

    calls = {"refresh": 0}
    original_refresh = window.refresh_selection

    def counting_refresh():
        calls["refresh"] += 1
        original_refresh()

    window.refresh_selection = counting_refresh
    window.node_palette.current_changed.connect(counting_refresh)

    clones = {"n": 0}
    original_clone = type(session.program).clone

    def counting_clone(self):
        clones["n"] += 1
        return original_clone(self)

    type(session.program).clone = counting_clone
    try:
        _select_palette_entry(window, "Repeat")
        qapp_session.processEvents()
        calls["refresh"] = 0
        clones["n"] = 0

        # A palette selection change: the tree may emit once, the window must
        # not loop, and no program clone may happen anywhere in the path.
        _select_palette_entry(window, "At")
        qapp_session.processEvents()
    finally:
        type(session.program).clone = original_clone

    assert calls["refresh"] <= 2, "selection change must not cascade refreshes"
    assert clones["n"] == 0, "compatibility checks must not clone the program"

    # Mode switches land in the same budget: one bounded refresh, no cascade.
    calls["refresh"] = 0
    window.insert_mode_buttons[DropPlacement.CHILD].click()
    qapp_session.processEvents()
    assert calls["refresh"] <= 2
    window.close()
