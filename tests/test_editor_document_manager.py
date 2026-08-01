from pathlib import Path

import pytest

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor import (
    AddNodeCommand,
    DocumentManager,
    DocumentManagerError,
    SetNodePropertiesCommand,
    SetNodePropertyCommand,
    SetPatternPropertyCommand,
    UnsavedDocumentError,
    make_node,
)
from src.editor.document import SceneDocument
from src.pattern import PatternDocument


def test_manager_owns_independent_documents_savepoints_and_context(tmp_path):
    project = ProjectContext(tmp_path)
    manager = DocumentManager(project)
    scene = manager.active
    assert scene is not None
    scene.selected_resource = "res://assets/player.png"
    scene.editor_context["zoom"] = 1.75

    pattern = manager.new_pattern("Ring")
    pattern.apply(SetPatternPropertyCommand(pattern.document, "shape.count", 48))
    pattern.selected_resource = "res://assets/bullets.json#ball"
    assert pattern.is_dirty
    assert pattern.commands.can_undo
    assert not scene.is_dirty
    assert not scene.commands.can_undo

    saved = manager.save(pattern, "game_content/patterns/ring.pystg.json")
    assert saved.is_file()
    assert not pattern.is_dirty
    assert scene.selected_resource == "res://assets/player.png"
    assert scene.editor_context["zoom"] == 1.75

    manager.activate(scene)
    assert manager.active is scene
    manager.activate(pattern)
    assert manager.active is pattern


def test_open_deduplicates_paths_and_registry_loads_scene_documents(tmp_path):
    project = ProjectContext(tmp_path)
    manager = DocumentManager(project, create_initial_scene=False)
    scene = manager.new_scene("Stage")
    path = manager.save(scene, "game_content/scenes/stage.pystg.json")
    manager.close(scene)

    opened = manager.open(path)
    assert isinstance(opened.document, SceneDocument)
    assert manager.open(Path(path)) is opened
    assert len(manager) == 1

    loaded = ResourceStore(project).load(path)
    assert isinstance(loaded, SceneDocument)


def test_close_and_revert_require_explicit_unsaved_decision(tmp_path):
    manager = DocumentManager(ProjectContext(tmp_path), create_initial_scene=False)
    pattern = manager.new_pattern()
    pattern.apply(SetPatternPropertyCommand(pattern.document, "motion.speed", 3.5))

    with pytest.raises(UnsavedDocumentError):
        manager.close(pattern)

    pattern.revert()
    assert pattern.document.motion.speed == 2.0
    assert not pattern.is_dirty
    assert not pattern.commands.can_undo
    manager.close(pattern)
    assert manager.active is None


def test_save_as_rejects_another_open_document_path(tmp_path):
    manager = DocumentManager(ProjectContext(tmp_path), create_initial_scene=False)
    first = manager.new_pattern("One")
    manager.save(first, "game_content/patterns/one.pystg.json")
    second = manager.new_pattern("Two")

    with pytest.raises(DocumentManagerError, match="already open"):
        manager.save(second, first.path)


def test_transactions_and_continuous_edits_form_interaction_sized_history(tmp_path):
    manager = DocumentManager(ProjectContext(tmp_path))
    session = manager.active
    root = session.document.root
    emitter = make_node("Emitter")
    session.apply(AddNodeCommand(root, root.id, emitter))

    session.commands.begin_transaction("Move emitter")
    session.apply(
        SetNodePropertyCommand(root, emitter.id, "x", 100.0),
        coalesce=True,
    )
    session.apply(
        SetNodePropertyCommand(root, emitter.id, "x", 120.0),
        coalesce=True,
    )
    session.apply(
        SetNodePropertyCommand(root, emitter.id, "y", 80.0),
        coalesce=True,
    )
    assert session.commands.end_transaction()

    assert (emitter.properties["x"], emitter.properties["y"]) == (120.0, 80.0)
    assert session.undo()
    assert (emitter.properties["x"], emitter.properties["y"]) == (192.0, 224.0)
    assert session.redo()
    assert (emitter.properties["x"], emitter.properties["y"]) == (120.0, 80.0)

    session.apply(
        SetNodePropertiesCommand(root, emitter.id, {"x": 140.0, "y": 90.0}),
        coalesce=True,
    )
    session.apply(
        SetNodePropertiesCommand(root, emitter.id, {"x": 160.0, "y": 110.0}),
        coalesce=True,
    )
    assert session.undo()
    assert (emitter.properties["x"], emitter.properties["y"]) == (120.0, 80.0)


def test_invalid_command_rolls_back_before_entering_history(tmp_path):
    manager = DocumentManager(ProjectContext(tmp_path), create_initial_scene=False)
    pattern = manager.new_pattern()

    with pytest.raises(ValueError):
        pattern.apply(SetPatternPropertyCommand(pattern.document, "shape.count", 0))

    assert pattern.document.shape.count == 24
    assert not pattern.commands.can_undo
    assert not pattern.is_dirty
