"""Runtime language switching for the Qt authoring workbench."""

import pytest

from src.qt_compat.QtWidgets import QPushButton
from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.i18n import (
    LANGUAGE_CHINESE,
    LANGUAGE_ENGLISH,
    LanguageManager,
)


def test_language_manager_accepts_only_supported_languages(qapp_session):
    manager = LanguageManager()
    assert manager.language == LANGUAGE_ENGLISH
    assert manager.translate("New Scene") == "New Scene"

    manager.set_language(LANGUAGE_CHINESE)
    assert manager.translate("New Scene") == "新建场景"
    assert manager.translate("New Scene") == "新建场景"
    manager.toggle()
    assert manager.language == LANGUAGE_ENGLISH

    with pytest.raises(ValueError):
        manager.set_language("fr")


def test_editor_language_switch_retranslates_shell_and_preserves_document(
    tmp_path, qapp_session
):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.new_pattern()
    qapp_session.processEvents()

    pattern = window.central_tabs.currentWidget()
    before = window.session.document.to_dict()

    window.set_language(LANGUAGE_CHINESE)
    qapp_session.processEvents()

    assert window.action_new.text() == "新建场景"
    assert window.scene_dock.windowTitle() == "场景"
    assert window.inspector_dock.windowTitle() == "检查器"
    assert window.bottom_tabs.tabText(0) == "输出"
    assert window.language_menu.title() == "语言(&L)"
    assert window.action_language_chinese.isChecked()
    assert pattern.mode_switch.itemText(0) == "配方"
    assert pattern.mode_switch.currentData() == "recipe"
    assert window.timeline.kind_picker.itemText(0) == "弹幕"
    # The display label changes, but the command still receives the internal
    # timeline kind expected by the document model.
    assert window.timeline.kind_picker.currentData() == "Pattern"
    launch = window.preview_panel.findChild(QPushButton, "previewLaunch")
    assert launch is not None
    assert launch.text() == "启动预览"
    assert window.session.document.to_dict() == before

    window.set_language(LANGUAGE_ENGLISH)
    qapp_session.processEvents()
    assert window.action_new.text() == "New Scene"
    assert window.scene_dock.windowTitle() == "Scene"
    assert window.bottom_tabs.tabText(0) == "Output"
    assert pattern.mode_switch.itemText(0) == "Recipe"
    assert window.timeline.kind_picker.itemText(0) == "Pattern"
    assert window.session.document.to_dict() == before

    window.close()
    window.deleteLater()
    qapp_session.processEvents()
