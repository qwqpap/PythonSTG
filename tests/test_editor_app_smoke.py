import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLineEdit

from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow, build_preview_command
from src.editor.node_types import make_node
from src.editor.session import SceneEditorSession


def _app():
    return QApplication.instance() or QApplication([])


def test_editor_window_wires_tree_inspector_viewport_and_undo(tmp_path):
    app = _app()
    window = EditorMainWindow(ProjectContext(tmp_path))

    root_item = window.tree.topLevelItem(0)
    assert root_item.text(1) == "SceneRoot"
    assert window.inspector.widget().findChild(QLineEdit, "inspectorName") is not None

    window.add_node("Sprite")
    sprite_id = window._selected_id
    assert window.tree.topLevelItem(0).childCount() == 1
    assert sprite_id in window.viewport._items
    assert window.inspector._node_id == sprite_id

    window.add_node("EnemySpawner")
    spawner_id = window._selected_id
    assert window.session.node(sprite_id).children[0].id == spawner_id
    assert window.inspector._node_id == spawner_id
    window.undo()
    assert window.session.node(spawner_id) is None
    assert window._selected_id == window.session.document.root.id
    window._selected_id = sprite_id
    window._refresh()

    window._selected_id = window.session.document.root.id
    window.add_node("SpellCard")
    spell_id = window._selected_id
    window.indent_selected()
    assert window.session.node(sprite_id).children[0].id == spell_id
    window.outdent_selected()
    assert window.session.document.root.children[1].id == spell_id
    window.undo()
    window.undo()
    window.undo()
    assert window.session.node(spell_id) is None
    window._selected_id = sprite_id
    window._refresh()

    window.set_node_property(sprite_id, "x", 128.0)
    assert window.session.node(sprite_id).properties["x"] == 128.0
    assert window.session.is_dirty
    window.undo()
    assert window.session.node(sprite_id).properties["x"] == 192.0
    window.undo()
    assert window.tree.topLevelItem(0).childCount() == 0
    assert not window.session.is_dirty

    window.close()
    app.processEvents()


def test_preview_command_uses_real_runtime_and_spell_preview(tmp_path):
    project = ProjectContext(tmp_path)
    session_document = SceneEditorSession.new_document()
    arguments, label = build_preview_command(project, session_document, None)
    assert Path(arguments[0]).name == "main.py"
    assert "--stage=stage1" in arguments
    assert label == "runtime preview: stage1"

    script = tmp_path / "spell.py"
    script.write_text("class Demo: pass\n", encoding="utf-8")
    spell = make_node("SpellCard")
    spell.properties["script"] = "spell.py"
    spell.properties["class_name"] = "Demo"
    arguments, label = build_preview_command(project, session_document, spell)

    assert Path(arguments[0]).name == "preview_spell.py"
    assert arguments[-2:] == ["--spell", "Demo"]
    assert label == "spell preview: spell.py"
