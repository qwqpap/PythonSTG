from __future__ import annotations

from pathlib import Path

import pytest

from src.authoring.program import DropPlacement, ProgramError, find_node
from src.core.project_context import ProjectContext
from src.editor.program_tree import NODE_MIME, ProgramTree
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtCore import QMimeData, QPoint
from src.qt_compat.QtWidgets import QMenu


class _DropPosition:
    def __init__(self, point: QPoint) -> None:
        self._point = point

    def toPoint(self) -> QPoint:
        return self._point


class _DropEvent:
    def __init__(self, point: QPoint, source_uid: str) -> None:
        self._position = _DropPosition(point)
        self._mime = QMimeData()
        self._mime.setData(NODE_MIME, source_uid.encode("utf-8"))
        self.accepted = False

    def position(self) -> _DropPosition:
        return self._position

    def mimeData(self) -> QMimeData:
        return self._mime

    def acceptProposedAction(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.accepted = False


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Repeat, Stage, Wait\n\n"
        "stage = Stage(\n"
        "    'stage',\n"
        "    'Stage',\n"
        "    body=[\n"
        "        Repeat(2, body=[Wait(1, uid='inner')], uid='container'),\n"
        "        Repeat(1, body=[], uid='wrapper'),\n"
        "        Wait(2, uid='a'),\n"
        "        Wait(3, uid='b'),\n"
        "    ],\n"
        ")\n",
        encoding="utf-8",
    )
    return root


def _click_palette_action(window: EditorWindow, button, label: str) -> None:
    button.click()
    menu = window._node_menu
    assert isinstance(menu, QMenu) and menu.isVisible()
    for category in menu.actions():
        submenu = category.menu()
        for action in submenu.actions() if submenu is not None else ():
            if action.text() == label:
                action.trigger()
                return
    raise AssertionError(f"palette action {label!r} was not shown")


def _session(tmp_path: Path) -> EditorSession:
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(_project(tmp_path / "authoring"))
    session.select_unit("stage")
    return session


@pytest.mark.parametrize(
    ("source", "target", "placement", "top_level", "child_uids"),
    (
        ("b", "a", DropPlacement.BEFORE, ["container", "wrapper", "b", "a"], []),
        ("a", "b", DropPlacement.AFTER, ["container", "wrapper", "b", "a"], []),
        ("a", "container", DropPlacement.CHILD, ["container", "wrapper", "b"], ["inner", "a"]),
        ("wrapper", "a", DropPlacement.WRAP, ["container", "wrapper", "b"], ["a"]),
    ),
)
def test_each_drop_placement_emits_one_undoable_command(
    tmp_path,
    qapp_session,
    source,
    target,
    placement,
    top_level,
    child_uids,
):
    session = _session(tmp_path)
    before = session.program.semantic_data()
    tree = ProgramTree()
    tree.resize(480, 360)
    tree.set_unit(session.current_unit)
    tree.expandAll()
    tree.show()
    qapp_session.processEvents()
    tree.move_requested.connect(session.move_node)

    target_item = tree.item_for_uid(target)
    rect = tree.visualItemRect(target_item)
    if placement == DropPlacement.BEFORE:
        point = QPoint(rect.center().x(), rect.top() + 1)
    elif placement == DropPlacement.AFTER:
        point = QPoint(rect.center().x(), rect.bottom() - 1)
    elif placement == DropPlacement.CHILD:
        point = QPoint(rect.left() + 1, rect.center().y())
    else:
        point = QPoint(rect.right() - 1, rect.center().y())
    event = _DropEvent(point, source)
    tree.dropEvent(event)

    assert event.accepted
    assert session.undo_stack.count() == 1
    assert [node.uid for node in session.program.get_unit("stage").body] == top_level
    if child_uids:
        parent_uid = "container" if placement == DropPlacement.CHILD else "wrapper"
        parent = find_node(session.program, parent_uid)[1]
        assert [node.uid for node in parent.children["body"]] == child_uids

    after = session.program.semantic_data()
    session.undo_stack.undo()
    assert session.program.semantic_data() == before
    session.undo_stack.redo()
    assert session.program.semantic_data() == after
    tree.close()


def test_tree_computes_four_unambiguous_drop_zones(tmp_path, qapp_session):
    session = _session(tmp_path)
    tree = ProgramTree()
    tree.resize(480, 360)
    tree.set_unit(session.current_unit)
    tree.expandAll()
    tree.show()
    qapp_session.processEvents()
    item = tree.item_for_uid("container")
    rect = tree.visualItemRect(item)

    assert (
        tree.placement_for_item(item, QPoint(rect.center().x(), rect.top() + 1))
        == DropPlacement.BEFORE
    )
    assert (
        tree.placement_for_item(item, QPoint(rect.center().x(), rect.bottom() - 1))
        == DropPlacement.AFTER
    )
    assert (
        tree.placement_for_item(item, QPoint(rect.left() + 1, rect.center().y()))
        == DropPlacement.CHILD
    )
    assert (
        tree.placement_for_item(item, QPoint(rect.right() - 1, rect.center().y()))
        == DropPlacement.WRAP
    )
    tree.close()


def test_template_call_stays_aggregated_through_tree_edit_save_and_reopen(
    tmp_path, qapp_session
):
    root = tmp_path / "authoring"
    root.mkdir()
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait, template\n\n"
        "@template\n"
        "def local_pause(frames: int = 3):\n"
        "    return [Wait(frames)]\n\n"
        "stage = Stage('stage', 'Stage', body=[local_pause(frames=4), Wait(1, uid='tail')])\n",
        encoding="utf-8",
    )
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(root)
    stage = session.program.get_unit("stage")
    call_uid = stage.body[0].uid
    assert stage.body[0].kind == "TemplateCall"

    session.move_node("tail", call_uid, DropPlacement.BEFORE)
    assert [node.kind for node in session.program.get_unit("stage").body] == [
        "Wait",
        "TemplateCall",
    ]
    session.save_all()

    reopened = EditorSession(project_context=ProjectContext(tmp_path))
    reopened.open_project(root)
    assert [node.kind for node in reopened.program.get_unit("stage").body] == [
        "Wait",
        "TemplateCall",
    ]


def test_visible_toolbar_adds_root_and_child_nodes_and_deletes_with_undo(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    window = EditorWindow(session)
    window.show()
    qapp_session.processEvents()

    assert window.add_after_button.isVisible()
    assert window.add_after_button.isEnabled()
    assert not window.add_child_button.isEnabled()
    assert not window.delete_node_button.isEnabled()

    _click_palette_action(window, window.add_after_button, "等待")
    appended_uid = session.current_node_uid
    assert appended_uid is not None
    assert session.program.get_unit("stage").body[-1].uid == appended_uid

    session.select_node("container")
    qapp_session.processEvents()
    assert window.add_child_button.isEnabled()
    _click_palette_action(window, window.add_child_button, "等待")
    child_uid = session.current_node_uid
    assert child_uid is not None
    container = find_node(session.program, "container")[1]
    assert [node.uid for node in container.children["body"]] == ["inner", child_uid]

    window.delete_node_button.click()
    qapp_session.processEvents()
    with pytest.raises(ProgramError, match="unknown node"):
        find_node(session.program, child_uid)
    session.undo_stack.undo()
    assert find_node(session.program, child_uid)[1].kind == "Wait"
    assert session.current_node_uid == child_uid
    window.close()


def test_empty_unit_can_add_its_first_node(tmp_path, qapp_session):
    root = _project(tmp_path / "authoring")
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage\n\n"
        "stage = Stage('stage', 'Empty Stage', body=[])\n",
        encoding="utf-8",
    )
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(root)
    session.select_unit("stage")
    window = EditorWindow(session)

    window.show()
    _click_palette_action(window, window.add_after_button, "等待")

    node_uid = session.current_node_uid
    assert node_uid is not None
    assert [item.uid for item in session.program.get_unit("stage").body] == [node_uid]
    session.undo_stack.undo()
    assert session.program.get_unit("stage").body == []
    session.undo_stack.redo()
    session.save_all()
    reopened = EditorSession(project_context=ProjectContext(tmp_path))
    reopened.open_project(root)
    assert [item.uid for item in reopened.program.get_unit("stage").body] == [node_uid]
    window.close()
