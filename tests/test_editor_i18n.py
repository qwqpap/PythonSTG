"""Runtime language switching for the Qt authoring workbench."""

import pytest

from src.qt_compat.QtWidgets import QComboBox, QLabel, QPushButton
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
    assert window.state_graph_dock.windowTitle() == "关卡流程"
    assert window.variables_dock.windowTitle() == "变量"
    assert window.bottom_tabs.tabText(0) == "输出"
    assert window.language_menu.title() == "语言(&L)"
    assert window.action_language_chinese.isChecked()
    # The author-facing controls carry task language only; the view mode is
    # internal state and no longer has a widget of its own to translate.
    assert pattern.fold_button.text() == "返回调整参数"
    assert pattern.mode() == "recipe"
    assert pattern.level_picker.itemText(0) == "调整参数"
    shape_kind = window.inspector.findChild(QComboBox, "patternProperty_shape_kind")
    aim_mode = window.inspector.findChild(QComboBox, "patternProperty_aim_mode")
    assert shape_kind.currentText() == "圆形"
    assert shape_kind.currentData() == "ring"
    assert aim_mode.currentText() == "固定方向"
    assert aim_mode.currentData() == "fixed"
    assert "L1" not in pattern.level_picker.itemText(0)
    assert window.timeline.kind_picker.itemText(0) == "弹幕"
    # The display label changes, but the command still receives the internal
    # timeline kind expected by the document model.
    assert window.timeline.kind_picker.currentData() == "Pattern"
    launch = window.preview_panel.findChild(QPushButton, "previewLaunch")
    assert launch is not None
    assert launch.text() == "启动预览"
    assert pattern.source_summary.text() == "当前没有脚本扩展，此弹幕使用编辑器的标准行为。"
    assert pattern.template_picker.itemText(0).endswith("· 基础")
    assert pattern.level_picker.itemText(0) == "调整参数"
    assert window.session.document.to_dict() == before
    # Pattern authoring must not spend compact-window space on disabled Scene
    # tools.  The Inspector remains available for precise parameter edits.
    assert not window.scene_dock.isVisibleTo(window)
    assert not window.state_graph_dock.isVisibleTo(window)
    assert not window.variables_dock.isVisibleTo(window)
    assert window.inspector_dock.isVisibleTo(window)

    window.set_language(LANGUAGE_ENGLISH)
    qapp_session.processEvents()
    assert window.action_new.text() == "New Scene"
    assert window.scene_dock.windowTitle() == "Scene"
    assert window.bottom_tabs.tabText(0) == "Output"
    assert pattern.fold_button.text() == "Back to Parameters"
    assert window.timeline.kind_picker.itemText(0) == "Pattern"
    assert window.session.document.to_dict() == before

    window.close()
    window.deleteLater()
    qapp_session.processEvents()


def test_pattern_preset_uses_task_labels_instead_of_internal_parameter_ids(
    tmp_path, qapp_session
):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.set_language(LANGUAGE_CHINESE)
    window.new_pattern()
    pattern = window.central_tabs.currentWidget()
    descriptor = next(
        item for item in window._preset_library.presets if item.display_name == "双螺旋"
    )
    pattern.set_preset_expansion(descriptor, (), {})

    labels = {
        label.objectName(): label.text()
        for label in pattern.findChildren(QLabel)
        if label.objectName().startswith("presetParameterLabel_")
    }
    assert labels == {
        "presetParameterLabel_count": "每轮子弹数",
        "presetParameterLabel_speed": "子弹速度",
        "presetParameterLabel_interval": "发射间隔（帧）",
        "presetParameterLabel_bursts": "发射轮数",
    }
    assert "版本" not in pattern.preset_summary.text()
    window.close()


def test_chinese_scene_menu_and_generated_flow_hide_internal_node_terms(
    tmp_path, qapp_session
):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.set_language(LANGUAGE_CHINESE)
    qapp_session.processEvents()

    menu_texts = {
        action.text()
        for action in window._node_add_menu.actions()
        if action.text()
    }
    assert {"关卡", "精灵", "敌人生成器", "脚本符卡", "符卡", "发射器", "弹幕实例"} <= menu_texts
    assert not {
        "Stage",
        "Sprite",
        "Enemy Spawner",
        "Spell Card",
        "Spell",
        "Emitter",
        "Pattern Instance",
    } & menu_texts

    window.create_simple_spell_flow()
    qapp_session.processEvents()
    names = []
    item = window.tree.topLevelItem(0)
    while item is not None:
        names.append(item.text(0))
        item = item.child(0) if item.childCount() else None
    assert names == ["未命名场景", "关卡", "Boss", "符卡", "发射器", "弹幕实例"]
    assert window.action_undo.text() == "撤销 创建简单符卡"
    assert "已创建关卡、Boss、符卡、发射器和弹幕实例" in window.output.toPlainText()

    viewport = window.central_tabs.currentWidget()
    assert {item.node_type for item in viewport._items.values()} == {"Boss", "Emitter"}
    positions = {item.node_type: item.pos() for item in viewport._items.values()}
    assert positions["Boss"] != positions["Emitter"]
    window.close()


def test_chinese_stage_template_localizes_defaults_but_preserves_runtime_kinds(
    tmp_path, qapp_session
):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.set_language(LANGUAGE_CHINESE)
    window.create_stage_template("two_phase_boss")
    qapp_session.processEvents()

    document = window.session.document
    assert document.name == "两阶段 Boss"
    assert [state.name for state in document.state_graph.states] == [
        "登场",
        "通常阶段",
        "强化阶段",
        "结束",
    ]
    intro = document.state_graph.states[0]
    assert [track.name for track in intro.tracks] == ["背景", "背景音乐"]
    assert [track.kind for track in intro.tracks] == ["Background", "Audio"]
    assert intro.tracks[1].clips[0].name == "关卡背景音乐"
    assert window.action_undo.text() == "撤销 创建两阶段 Boss 模板"
    assert "Move/resize timeline clip" not in window.action_undo.text()
    window.close()


def test_chinese_dynamic_change_picker_hides_internal_paths_but_preserves_data(
    qapp_session,
):
    from src.editor.pattern_workspace import PatternWorkspace

    workspace = PatternWorkspace()
    manager = LanguageManager(language=LANGUAGE_CHINESE)
    workspace.set_language_manager(manager)

    assert workspace.binding_path.currentText() == "每轮子弹数"
    assert workspace.binding_path.currentData() == "shape.count"
    assert workspace.binding_kind.currentText() == "固定值"
    assert workspace.binding_kind.currentData() == "constant"
    assert "shape.count" not in {
        workspace.binding_path.itemText(index)
        for index in range(workspace.binding_path.count())
    }
    workspace.close()
