from src.core.project_context import ProjectContext
from src.editor import (
    AddNodeCommand,
    DocumentStore,
    MoveNodeCommand,
    RemoveNodeCommand,
    RenameNodeCommand,
    SceneEditorSession,
    SceneMutationError,
    SetNodePropertyCommand,
    make_node,
)


def _session(tmp_path):
    return SceneEditorSession(DocumentStore(ProjectContext(tmp_path)))


def test_scene_commands_round_trip_through_undo_redo(tmp_path):
    session = _session(tmp_path)
    root = session.document.root
    sprite = make_node("Sprite", name="Player")

    session.apply(AddNodeCommand(root, root.id, sprite))
    session.apply(RenameNodeCommand(root, sprite.id, "Boss"))
    session.apply(SetNodePropertyCommand(root, sprite.id, "x", 128.0))

    assert sprite.name == "Boss"
    assert sprite.properties["x"] == 128.0
    assert session.is_dirty

    assert session.undo()
    assert sprite.properties["x"] == 192.0
    assert session.undo()
    assert sprite.name == "Player"
    assert session.undo()
    assert not root.children
    assert not session.is_dirty

    assert session.redo()
    assert session.redo()
    assert session.redo()
    assert root.children == [sprite]
    assert sprite.name == "Boss"
    assert sprite.properties["x"] == 128.0


def test_move_reparents_and_restores_original_order(tmp_path):
    session = _session(tmp_path)
    root = session.document.root
    left = make_node("Sprite", name="Left")
    right = make_node("EnemySpawner", name="Right")
    child = make_node("SpellCard", name="Child")
    root.children[:] = [left, right]
    left.children.append(child)
    session.replace(session.document)

    session.apply(MoveNodeCommand(root, child.id, right.id, 0))
    assert not left.children
    assert right.children == [child]

    assert session.undo()
    assert left.children == [child]
    assert not right.children

    session.apply(MoveNodeCommand(root, right.id, root.id, 0))
    assert root.children == [right, left]
    assert session.undo()
    assert root.children == [left, right]


def test_move_rejects_cycles_and_root_mutations(tmp_path):
    session = _session(tmp_path)
    root = session.document.root
    parent = make_node("Sprite", name="Parent")
    child = make_node("Sprite", name="Child")
    parent.children.append(child)
    root.children.append(parent)
    session.replace(session.document)

    try:
        session.apply(MoveNodeCommand(root, parent.id, child.id, 0))
    except SceneMutationError:
        pass
    else:
        raise AssertionError("cycle should be rejected")

    try:
        session.apply(RemoveNodeCommand(root, root.id))
    except SceneMutationError:
        pass
    else:
        raise AssertionError("root deletion should be rejected")


def test_session_save_tracks_clean_state(tmp_path):
    session = _session(tmp_path)
    root = session.document.root
    sprite = make_node("Sprite")
    session.apply(AddNodeCommand(root, root.id, sprite))

    path = session.save("game_content/scenes/test.pystg.json")
    assert path.is_file()
    assert not session.is_dirty

    session.apply(SetNodePropertyCommand(root, sprite.id, "visible", False))
    assert session.is_dirty
    session.save()
    assert not session.is_dirty
