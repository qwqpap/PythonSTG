from __future__ import annotations

import copy
import importlib

import pytest

from src.authoring.dsl import (
    Boss,
    Call,
    CreateLaser,
    Enemy,
    Expr,
    Fire,
    FireCircle,
    Function,
    MoveLinear,
    NonSpell,
    Parallel,
    Parameter,
    Project,
    RawPython,
    Ref,
    RemoveLaser,
    Repeat,
    Return,
    RunBoss,
    RunWave,
    SpawnEnemy,
    SpawnTask,
    Spell,
    Stage,
    Set,
    Task,
    Wait,
    Wave,
    ring_burst,
)
from src.authoring.program import AuthoringProgram, TemplateTarget, make_template_call
from src.authoring.templates import TemplateRegistry, template
from src.compiler.codegen import CodeGenerator
from src.compiler.diagnostics import CompilerError


def complete_program() -> AuthoringProgram:
    units = [
        Project("demo", "Demo", Ref("stage_1"), [Ref("stage_1")]),
        Stage(
            "stage_1",
            "Stage One",
            [
                SpawnTask(Ref("pulse_task"), arguments={"count": 2}, uid="spawn_task"),
                Call(Ref("identity"), [3], uid="call_function"),
                Parallel([[Wait(1, uid="left_wait")], [Wait(2, uid="right_wait")]], uid="parallel"),
                RawPython("self.marker = 'ok'", uid="raw_stage"),
                RunWave(Ref("opening"), uid="run_wave"),
                RunBoss(Ref("demo_boss"), uid="run_boss"),
            ],
            bgm="res://assets/audio/music/00.wav",
            background="res://assets/images/background/bamboo.json",
        ),
        Wave(
            "opening",
            "Opening",
            [
                SpawnEnemy(Ref("fairy"), x=0.25, y=0.8, uid="spawn_enemy"),
                FireCircle(x=0.0, y=0.8, count=8, uid="wave_circle"),
                Wait(2, uid="wave_wait"),
            ],
        ),
        Enemy(
            "fairy",
            "Fairy",
            [
                MoveLinear(0.1, -0.2, duration=3, uid="enemy_move"),
                Fire(angle=-90.0, uid="enemy_fire"),
                CreateLaser(0.0, 0.0, 90.0, 0.1, 0.5, 0.1, 0.05, assign="laser", uid="laser_create"),
                RemoveLaser(Expr("laser"), uid="laser_remove"),
            ],
            sprite="res://assets/sprites/fairy.json",
        ),
        Boss("demo_boss", "Demo Boss", "enemy_fairy", [Ref("nons_1"), Ref("spell_1")]),
        NonSpell("nons_1", body=[Wait(1, uid="nons_wait")]),
        Spell(
            "spell_1",
            "Ring Sign",
            [ring_burst(count=2, interval=1, uid="template_call")],
        ),
        Task(
            "pulse_task",
            "Pulse",
            [Parameter("count", "int", 1)],
            [Repeat(Expr("count"), [Wait(1, uid="task_wait")], uid="task_repeat")],
        ),
        Function(
            "identity",
            "Identity",
            [Parameter("value", "int")],
            [Return(Expr("value"), uid="function_return")],
        ),
        Enemy("orphan", "Not in stage closure"),
    ]
    return AuthoringProgram.from_units(units)


def test_complete_program_generates_fixed_stage_package_and_source_map():
    result = CodeGenerator(complete_program()).generate()

    expected = {
        "__init__.py",
        "entry.py",
        "stages/__init__.py",
        "stages/stage_1/__init__.py",
        "stages/stage_1/_support.py",
        "stages/stage_1/stage.py",
        "stages/stage_1/waves/opening.py",
        "stages/stage_1/enemies/fairy.py",
        "stages/stage_1/bosses/demo_boss.py",
        "stages/stage_1/spells/nons_1.py",
        "stages/stage_1/spells/spell_1.py",
        "stages/stage_1/tasks/pulse_task.py",
        "stages/stage_1/functions/identity.py",
    }
    assert expected <= set(result.modules)
    assert not any("orphan" in path for path in result.modules)
    assert result.manifest == {
        "project_id": "demo",
        "build_hash": result.build_hash,
        "entry_module": "game_content.generated.demo.entry",
        "stages": ["stage_1"],
    }
    assert "class Stage_stage_1(StageScript):" in result.modules["stages/stage_1/stage.py"]
    assert "move_linear(0.1, -0.2, duration=3)" in result.modules["stages/stage_1/enemies/fairy.py"]
    assert "ring_burst" not in result.modules["stages/stage_1/spells/spell_1.py"]
    assert "_pystg_fire_circle(" in result.modules["stages/stage_1/spells/spell_1.py"]
    assert ".fire_circle(" not in result.modules["stages/stage_1/spells/spell_1.py"]
    assert "_pystg_bind_enemy_resources(self)" in result.modules[
        "stages/stage_1/enemies/fairy.py"
    ]
    assert "callback=" not in "\n".join(result.modules.values())
    assert "spawn_emitter" not in "\n".join(result.modules.values())
    assert {item["uid"] for item in result.source_map} >= {
        "parallel",
        "template_call",
        "raw_stage",
        "enemy_move",
    }
    assert not any("__expanded_" in item["uid"] for item in result.source_map)
    for path, source in result.modules.items():
        if path.endswith(".py"):
            compile(source, path, "exec")


def test_codegen_is_byte_deterministic_for_same_semantics():
    first = CodeGenerator(complete_program()).generate()
    second = CodeGenerator(copy.deepcopy(complete_program())).generate()

    assert second.modules == first.modules
    assert second.source_map == first.source_map
    assert second.manifest == first.manifest
    assert second.build_hash == first.build_hash

    reordered = AuthoringProgram.from_units(reversed(complete_program().logical_units()))
    third = CodeGenerator(reordered).generate()
    assert third.modules == first.modules
    assert third.source_map == first.source_map
    assert third.manifest == first.manifest


def test_same_generator_instance_resets_deterministic_helper_state():
    generator = CodeGenerator(complete_program())

    first = generator.generate()
    second = generator.generate()

    assert first.modules == second.modules
    assert first.source_map == second.source_map
    assert first.manifest == second.manifest
    assert first.build_hash == second.build_hash


def test_raw_python_syntax_error_maps_to_author_node():
    program = AuthoringProgram.from_units(
        [
            Project("bad", "Bad", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [RawPython("if:", uid="bad_raw")]),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        CodeGenerator(program).generate()

    assert caught.value.code == "raw_python_syntax"
    assert caught.value.diagnostics[0].uid == "bad_raw"


def test_raw_python_context_syntax_error_maps_to_author_node():
    program = AuthoringProgram.from_units(
        [
            Project("bad_context", "Bad", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [RawPython("break", uid="raw_break")]),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        CodeGenerator(program).generate()

    assert caught.value.code == "raw_python_syntax"
    assert caught.value.diagnostics[0].uid == "raw_break"


def test_raw_python_break_is_valid_inside_generated_loop():
    program = AuthoringProgram.from_units(
        [
            Project("loop_context", "Loop", Ref("stage"), [Ref("stage")]),
            Stage(
                "stage",
                "Stage",
                [Repeat(2, [RawPython("break", uid="raw_break")], uid="repeat")],
            ),
        ]
    )

    result = CodeGenerator(program).generate()

    compile(result.modules["stages/stage/stage.py"], "stage.py", "exec")


def test_project_id_override_cannot_diverge_from_authoring_project():
    with pytest.raises(CompilerError) as caught:
        CodeGenerator(complete_program(), project_id="different")

    assert caught.value.code == "project_id_mismatch"


def test_empty_template_expansion_is_a_valid_mapped_noop():
    @template
    def nothing():
        return []

    registry = TemplateRegistry.with_builtins()
    registry.register(nothing)
    program = AuthoringProgram.from_units(
        [
            Project("empty_template", "Empty", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [nothing(uid="empty_call")]),
        ]
    )

    result = CodeGenerator(program, template_registry=registry).generate()
    stage_source = result.modules["stages/stage/stage.py"]

    compile(stage_source, "stage.py", "exec")
    assert any(item["uid"] == "empty_call" for item in result.source_map)
    assert "pass" in stage_source


def test_template_produced_reference_is_included_in_stage_closure():
    from src.authoring.dsl import RunWave

    @template
    def opening_call():
        return [RunWave(Ref("opening"))]

    registry = TemplateRegistry.with_builtins()
    registry.register(opening_call)
    program = AuthoringProgram.from_units(
        [
            Project("template_ref", "Template Ref", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [opening_call(uid="opening_call")]),
            Wave("opening", "Opening", [Wait(1)]),
        ]
    )

    result = CodeGenerator(program, template_registry=registry).generate()

    assert "stages/stage/waves/opening.py" in result.modules
    assert "from .waves.opening import Wave_opening" in result.modules["stages/stage/stage.py"]
    assert "run_wave(Wave_opening)" in result.modules["stages/stage/stage.py"]


def test_template_produced_stage_reference_is_rejected_before_symbol_generation():
    @template
    def unsupported_stage_value():
        return [Set("other_stage", Ref("stage_b"))]

    registry = TemplateRegistry.with_builtins()
    registry.register(unsupported_stage_value)
    program = AuthoringProgram.from_units(
        [
            Project("stage_ref", "Stage Ref", Ref("stage_a"), [Ref("stage_a"), Ref("stage_b")]),
            Stage("stage_a", "A", [unsupported_stage_value(uid="stage_ref_call")]),
            Stage("stage_b", "B", [Wait(1)]),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        CodeGenerator(program, template_registry=registry)

    assert caught.value.code == "stage_reference_context"
    assert caught.value.diagnostics[0].uid == "stage_ref_call"
    assert caught.value.diagnostics[0].related
    assert "test_compiler_codegen.py" in caught.value.diagnostics[0].related[0].source_path


def test_project_reference_in_runtime_unit_is_rejected_before_stage_closure():
    program = AuthoringProgram.from_units(
        [
            Project("project_ref", "Project", Ref("stage"), [Ref("stage")]),
            Stage(
                "stage",
                "Stage",
                [Set("project_type", Ref("project_ref"), uid="project_ref_node")],
            ),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        CodeGenerator(program)

    assert caught.value.code == "project_reference_context"
    assert caught.value.diagnostics[0].uid == "project_ref_node"


def test_entry_preserves_project_stage_order_and_start_stage():
    program = AuthoringProgram.from_units(
        [
            Project("ordered", "Ordered", Ref("stage_a"), [Ref("stage_b"), Ref("stage_a")]),
            Stage("stage_a", "A", [Wait(1)]),
            Stage("stage_b", "B", [Wait(1)]),
        ]
    )

    result = CodeGenerator(program).generate()
    entry = result.modules["entry.py"]

    assert result.manifest["stages"] == ["stage_b", "stage_a"]
    assert "STAGES: tuple[type[StageScript], ...] = (Stage_stage_b, Stage_stage_a)" in entry
    assert "START_STAGE: type[StageScript] = Stage_stage_a" in entry


def test_missing_template_package_maps_to_call_and_definition():
    call = make_template_call(
        TemplateTarget(
            identity="missing_template_package.burst",
            symbol="burst",
            module="missing_template_package",
            definition_path="templates/missing.py",
        ),
        uid="missing_call",
    )
    program = AuthoringProgram.from_units(
        [
            Project("missing_template", "Missing", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [call]),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        CodeGenerator(program)

    diagnostic = caught.value.diagnostics[0]
    assert caught.value.code == "template_missing"
    assert diagnostic.uid == "missing_call"
    assert diagnostic.related[0].source_path == "templates/missing.py"


def test_template_exception_maps_to_call_and_real_definition():
    @template
    def explode():
        raise RuntimeError("template exploded")

    registry = TemplateRegistry.with_builtins()
    registry.register(explode)
    program = AuthoringProgram.from_units(
        [
            Project("template_error", "Error", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [explode(uid="explode_call")]),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        CodeGenerator(program, template_registry=registry)

    diagnostic = caught.value.diagnostics[0]
    assert caught.value.code == "template_exception"
    assert diagnostic.uid == "explode_call"
    assert diagnostic.related
    assert "test_compiler_codegen.py" in diagnostic.related[0].source_path


def test_nested_template_from_explicit_module_is_registered_and_keeps_outer_source_map(
    tmp_path, monkeypatch
):
    module_name = "nested_template_fixture"
    (tmp_path / f"{module_name}.py").write_text(
        "\n".join(
            (
                "from src.authoring.dsl import Wait",
                "from src.authoring.templates import template",
                "",
                "@template",
                "def inner():",
                "    return [Wait(1)]",
                "",
                "@template",
                "def outer():",
                "    return [inner()]",
                "",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module(module_name)
    program = AuthoringProgram.from_units(
        [
            Project("nested", "Nested", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [module.outer(uid="outer_call")]),
        ]
    )

    result = CodeGenerator(program).generate()

    assert "await _pystg_await(self, self.wait(1))" in result.modules["stages/stage/stage.py"]
    assert {item["uid"] for item in result.source_map} == {"outer_call"}


def test_nested_template_recursion_is_still_rejected(tmp_path, monkeypatch):
    module_name = "recursive_template_fixture"
    (tmp_path / f"{module_name}.py").write_text(
        "\n".join(
            (
                "from src.authoring.templates import template",
                "",
                "@template",
                "def recursive():",
                "    return [recursive()]",
                "",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module(module_name)
    program = AuthoringProgram.from_units(
        [
            Project("recursive", "Recursive", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [module.recursive(uid="recursive_call")]),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        CodeGenerator(program)

    assert caught.value.code == "template_recursion"
    assert caught.value.diagnostics[0].uid == "recursive_call"


def test_template_context_error_maps_call_and_definition_location():
    @template
    def bad_enemy_action():
        return [RunWave(Ref("opening"))]

    registry = TemplateRegistry.with_builtins()
    registry.register(bad_enemy_action)
    program = AuthoringProgram.from_units(
        [
            Project("bad_template", "Bad", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [RunWave(Ref("opening"))]),
            Wave("opening", "Opening", [Wait(1)]),
            Enemy("enemy", "Enemy", [bad_enemy_action(uid="bad_call")]),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        CodeGenerator(program, template_registry=registry)

    diagnostic = caught.value.diagnostics[0]
    assert caught.value.code == "template_result"
    assert diagnostic.code == "illegal_parent"
    assert diagnostic.uid == "bad_call"
    assert diagnostic.related
    assert "test_compiler_codegen.py" in diagnostic.related[0].source_path


def test_template_raw_python_context_error_maps_call_and_definition_location():
    @template
    def bad_raw_python():
        return [RawPython("break")]

    registry = TemplateRegistry.with_builtins()
    registry.register(bad_raw_python)
    program = AuthoringProgram.from_units(
        [
            Project("bad_template_raw", "Bad", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [bad_raw_python(uid="bad_raw_call")]),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        CodeGenerator(program, template_registry=registry).generate()

    diagnostic = caught.value.diagnostics[0]
    assert caught.value.code == "raw_python_syntax"
    assert diagnostic.uid == "bad_raw_call"
    assert diagnostic.related
    assert "test_compiler_codegen.py" in diagnostic.related[0].source_path
