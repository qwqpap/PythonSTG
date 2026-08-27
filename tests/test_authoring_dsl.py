import ast
import inspect
from pathlib import Path

from src.authoring import dsl
from src.authoring.dsl import (
    CreateLaser,
    Expr,
    Fire,
    FireArc,
    FireAtPlayer,
    FireCircle,
    MoveTo,
    PlaySE,
    RUNTIME_DEFAULT,
    RawPython,
    Ref,
    Repeat,
    SpawnTask,
    Wait,
)
from src.authoring.program import ACTION_NODE_KINDS, CONTROL_NODE_KINDS, Node


def test_public_dsl_contains_every_fixed_logical_unit_and_node():
    assert set(dsl.UNIT_CONSTRUCTORS) == {
        "Project",
        "Stage",
        "Wave",
        "Enemy",
        "Boss",
        "Spell",
        "NonSpell",
        "Task",
        "Function",
    }
    assert ACTION_NODE_KINDS | CONTROL_NODE_KINDS <= set(dsl.NODE_CONSTRUCTORS)
    assert all(inspect.signature(value) for value in dsl.PUBLIC_CONSTRUCTORS.values())


def test_runtime_mirrored_signatures_keep_public_names_and_defaults():
    assert list(inspect.signature(MoveTo).parameters)[:3] == ["x", "y", "duration"]
    assert inspect.signature(MoveTo).parameters["duration"].default == 60
    assert list(inspect.signature(PlaySE).parameters)[:3] == ["name", "volume", "min_interval"]
    assert inspect.signature(PlaySE).parameters["min_interval"].default == 0.0
    assert list(inspect.signature(CreateLaser).parameters)[:7] == [
        "x",
        "y",
        "angle",
        "l1",
        "l2",
        "l3",
        "width",
    ]
    assert inspect.signature(Fire).parameters["x"].default is RUNTIME_DEFAULT
    assert list(inspect.signature(FireCircle).parameters)[:6] == [
        "x",
        "y",
        "count",
        "speed",
        "start_angle",
        "play_sound",
    ]
    assert list(inspect.signature(FireArc).parameters)[:7] == [
        "x",
        "y",
        "count",
        "speed",
        "center_angle",
        "arc_angle",
        "play_sound",
    ]
    assert list(inspect.signature(FireAtPlayer).parameters)[:5] == [
        "x",
        "y",
        "speed",
        "offset_angle",
        "play_sound",
    ]


def test_context_dependent_runtime_defaults_remain_omitted_but_explicit_values_survive():
    omitted = FireCircle()
    explicit = FireCircle(count=36, x=0.0, y=0.5)

    assert "count" not in omitted.arguments
    assert "x" not in omitted.arguments
    assert explicit.arguments["count"] == 36
    assert explicit.arguments["x"] == 0.0
    assert explicit.arguments["y"] == 0.5


def test_control_and_value_constructors_create_plain_headless_nodes():
    node = Repeat(Expr("count"), [Wait(6)], uid="repeat")
    spawned = SpawnTask(Ref("task_1"), arguments={"count": 3})
    raw = RawPython("value = max(1, count)")

    assert isinstance(node, Node)
    assert node.children["body"][0].kind == "Wait"
    assert spawned.arguments["task"] == Ref("task_1")
    assert raw.arguments["source"].startswith("value")


def test_authoring_core_import_graph_has_no_qt_editor_or_renderer_dependency():
    root = Path(__file__).resolve().parents[1]
    forbidden = ("src.editor", "src.render", "PySide", "qt_compat")
    for name in ("program.py", "dsl.py", "python_source.py", "templates.py"):
        tree = ast.parse((root / "src" / "authoring" / name).read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        assert not any(value.startswith(forbidden) for value in imports)
