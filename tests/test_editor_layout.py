from __future__ import annotations

from pathlib import Path

import pytest

from src.core.project_context import ProjectContext
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtCore import Qt
from src.qt_compat.QtWidgets import QDockWidget


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait\n\n"
        "stage = Stage('stage', 'Stage', body=[Wait(12, uid='wait')])\n",
        encoding="utf-8",
    )
    return root


@pytest.mark.parametrize(("width", "height"), ((1480, 920), (960, 640)))
def test_fixed_layout_remains_operable_at_required_sizes(
    tmp_path, qapp_session, width, height
):
    authoring_root = _project(tmp_path / "authoring")
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(authoring_root)
    window = EditorWindow(session)
    window.resize(width, height)
    window.show()
    qapp_session.processEvents()

    assert window.activity_sidebar.stack.count() == 4
    assert [button.text() for button in window.activity_sidebar.buttons] == [
        "程序",
        "文件",
        "资产",
        "关卡",
    ]
    for index in range(4):
        window.activity_sidebar.show_view(index)
        assert window.activity_sidebar.stack.currentIndex() == index

    assert window.dockWidgetArea(window.inspector_dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert window.dockWidgetArea(window.timeline_dock) == Qt.DockWidgetArea.BottomDockWidgetArea
    assert not bool(
        window.timeline_dock.features() & QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    assert window.tabifiedDockWidgets(window.timeline_dock) == []
    assert window.timeline_dock.isVisible()
    assert not window.output_dock.isVisible()

    window.central_groups.setSizes([3, 2])
    qapp_session.processEvents()
    assert window.editor_group.width() > 0
    assert window.game_group.width() > 0

    window.editor_group.close_group()
    qapp_session.processEvents()
    assert not window.editor_group.isVisible()
    assert not window.show_editor_action.isChecked()
    window.show_editor_action.trigger()
    qapp_session.processEvents()
    assert window.editor_group.isVisible()
    assert window.editor_group.width() > 0

    window.game_group.close_group()
    qapp_session.processEvents()
    assert not window.game_group.isVisible()
    assert not window.show_game_action.isChecked()
    window.show_game_action.trigger()
    qapp_session.processEvents()
    assert window.game_group.isVisible()
    assert window.game_group.width() > 0

    window.output_dock.toggleViewAction().trigger()
    qapp_session.processEvents()
    assert window.output_dock.isVisible()
    assert window.timeline_dock.isVisible()
    window.close()
