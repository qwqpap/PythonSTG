import ast
from dataclasses import dataclass

import pytest

from src.core.project_context import ProjectContext
from src.editor.commands import CommandStack
from src.editor.document import DocumentError, EditorNode, SceneDocument, TimelineEvent
from src.editor.spell_codegen import build_spellcard_code
from src.editor.storage import DocumentStore


def test_scene_document_atomic_round_trip_and_migration(tmp_path):
    project = ProjectContext(tmp_path)
    store = DocumentStore(project)
    scene = SceneDocument(
        name="Stage Test",
        root=EditorNode(
            type="Stage",
            name="Root",
            children=[EditorNode(type="EnemySpawn", name="Fairy")],
        ),
        timeline=[TimelineEvent(frame=120, type="Spawn", properties={"count": 3})],
    )

    path = store.save(scene, "game_content/scenes/stage_test.pystg.json")
    loaded = store.load(path)

    assert loaded.to_dict() == scene.to_dict()
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))

    legacy = SceneDocument.from_dict({
        "name": "Legacy",
        "nodes": [{"type": "Wave", "name": "Opening", "children": []}],
    })
    assert legacy.schema_version == 1
    assert legacy.root.children[0].type == "Wave"


def test_scene_document_rejects_duplicate_ids_and_future_schema():
    child = EditorNode(type="Wave", name="A")
    scene = SceneDocument(
        name="Bad",
        root=EditorNode(type="Stage", name="Root", children=[child]),
        timeline=[TimelineEvent(id=child.id, frame=1, type="Spawn")],
    )
    with pytest.raises(DocumentError, match="Duplicate"):
        scene.validate()
    with pytest.raises(DocumentError, match="newer"):
        SceneDocument.from_dict({"schema_version": 99})


@dataclass
class _SetValue:
    target: dict
    value: int
    label: str = "Set value"
    previous: int = 0

    def execute(self):
        self.previous = self.target["value"]
        self.target["value"] = self.value

    def undo(self):
        self.target["value"] = self.previous


def test_command_stack_undo_redo():
    target = {"value": 1}
    stack = CommandStack()
    stack.push(_SetValue(target, 2))
    assert target["value"] == 2
    assert stack.undo()
    assert target["value"] == 1
    assert stack.redo()
    assert target["value"] == 2


@dataclass
class _Pattern:
    name: str = "Ring"
    pattern_type: str = "circle"
    count: int = 12
    speed: float = 2.0
    speed_var: float = 0.0
    angle: float = 0.0
    angle_spread: float = 360.0
    bullet_type: str = "ball_m"
    color: str = "red"
    interval: int = 5


@dataclass
class _Spell:
    name: str = "测试「符卡」"
    hp: int = 1500
    time_limit: int = 60
    bonus: int = 1000000
    boss_x: float = 0.0
    boss_y: float = 0.5
    patterns: dict = None

    def __post_init__(self):
        self.patterns = {"ring": _Pattern()}


def test_spell_editor_codegen_uses_current_async_api():
    source = build_spellcard_code(_Spell())
    tree = ast.parse(source)
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert isinstance(methods["setup"], ast.AsyncFunctionDef)
    assert isinstance(methods["run"], ast.AsyncFunctionDef)
    assert "yield from" not in source
    compile(source, "<generated-spell>", "exec")
