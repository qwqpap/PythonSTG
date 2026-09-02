from __future__ import annotations

import json

from src.authoring.dsl import (
    At,
    Boss,
    Call,
    Expr,
    FireCircle,
    If,
    MoveTo,
    Parallel,
    Parameter,
    PlayDialogue,
    Project,
    RawPython,
    Ref,
    Repeat,
    RunBoss,
    RunWave,
    SpawnTask,
    Spell,
    Stage,
    Task,
    Wait,
    Wave,
    While,
    ring_burst,
)
from src.authoring.program import AuthoringProgram
from src.authoring.python_source import load_python_source
from src.authoring.timeline import Unknown, overlay_trace, project_timeline


def _program(stage, *units):
    return AuthoringProgram.from_units(
        [Project("demo", "Demo", Ref(stage.id), [Ref(stage.id)]), stage, *units]
    )


def test_sequence_at_and_literal_duration_have_exact_edit_contracts():
    stage = Stage(
        "stage",
        "Stage",
        [
            Wait(30, uid="wait"),
            MoveTo(0.0, 0.5, duration=45, uid="move"),
            At(120, [Wait(10, uid="at_wait")], uid="at"),
        ],
    )
    projection = project_timeline(_program(stage), stage)

    assert projection.find("wait").start == 0
    assert projection.find("wait").end == 30
    assert projection.find("wait").editable == "wait"
    assert projection.find("move").start == 30
    assert projection.find("move").end == 75
    assert projection.find("move").editable == "duration"
    assert projection.find("at").start == 75
    assert projection.find("at").end == 130
    assert projection.find("at").editable == "at"
    assert projection.end == 130


def test_repeat_parallel_and_parameterized_spawn_use_real_blocking_rules():
    task = Task(
        "side_task",
        "Side task",
        parameters=[Parameter("bursts", "int", 2)],
        body=[Repeat(Expr("bursts"), [Wait(12, uid="task_wait")], uid="task_repeat")],
    )
    stage = Stage(
        "stage",
        "Stage",
        [
            Repeat(3, [Wait(10, uid="repeat_wait")], uid="repeat"),
            Parallel(
                [[Wait(20, uid="parallel_short")], [Wait(50, uid="parallel_long")]],
                uid="parallel",
            ),
            SpawnTask(
                Ref("side_task"),
                arguments={"bursts": 3},
                uid="spawn",
            ),
            Wait(5, uid="tail"),
        ],
    )
    projection = project_timeline(_program(stage, task), stage)

    assert projection.find("repeat").end == 30
    assert projection.find("parallel").start == 30
    assert projection.find("parallel").end == 80
    assert projection.find("parallel_short").lane != projection.find("parallel_long").lane
    assert projection.find("repeat_wait").parent_uid == "repeat"
    assert projection.find("repeat_wait").lane != projection.find("repeat").lane
    assert projection.find("parallel_short").parent_uid == "parallel"
    assert projection.find("repeat").display == "aggregate"
    assert projection.find("spawn").display == "aggregate"
    assert projection.find("spawn").start == projection.find("spawn").end == 80
    assert projection.find("task_repeat").end == 116
    assert projection.find("tail").start == 80
    assert projection.end == 85


def test_inline_spawn_task_body_does_not_block_the_main_cursor():
    stage = Stage(
        "stage",
        "Stage",
        [
            Wait(10, uid="intro_wait"),
            SpawnTask(
                body=[Wait(40, uid="spawned_wait")],
                uid="inline_spawn",
            ),
            Wait(5, uid="tail"),
        ],
    )
    projection = project_timeline(_program(stage), stage)

    spawn = projection.find("inline_spawn")
    assert spawn.start == projection.find("intro_wait").end == 10
    assert spawn.end == 10
    assert spawn.display == "aggregate"
    spawned_wait = projection.find("spawned_wait")
    assert spawned_wait.start == 10
    assert spawned_wait.end == 50
    assert spawned_wait.lane != spawn.lane
    assert projection.find("tail").start == 10
    assert projection.end == 15


def test_dynamic_control_flow_is_unknown_instead_of_guessed():
    stage = Stage(
        "stage",
        "Stage",
        [
            If(
                Expr("player.power > 2"),
                [Wait(10, uid="then_wait")],
                [Wait(30, uid="else_wait")],
                uid="branch",
            ),
            While(Expr("enemy.alive"), [Wait(5, uid="loop_wait")], uid="loop"),
            RawPython("marker = 1", uid="raw"),
        ],
    )
    projection = project_timeline(_program(stage), stage)

    assert isinstance(projection.find("branch").end, Unknown)
    assert projection.find("then_wait").lane.endswith(":then")
    assert projection.find("else_wait").lane.endswith(":else")
    assert isinstance(projection.find("loop").end, Unknown)
    assert isinstance(projection.find("raw").start, Unknown)
    assert isinstance(projection.end, Unknown)


def test_nodes_after_dynamic_unknown_keep_source_order_without_guessing_frames():
    stage = Stage(
        "stage",
        "Stage",
        [
            RawPython("marker = 1", uid="raw"),
            Wait(10, uid="after_raw_1"),
            Wait(20, uid="after_raw_2"),
        ],
    )
    projection = project_timeline(_program(stage), stage)

    flat = projection.all_intervals()
    order = [interval.uid for interval in flat]
    assert order.index("after_raw_1") < order.index("after_raw_2")
    for uid in ("after_raw_1", "after_raw_2"):
        assert isinstance(projection.find(uid).start, Unknown), uid
        assert isinstance(projection.find(uid).end, Unknown), uid


def test_dynamic_wait_is_not_advertised_as_timeline_editable():
    stage = Stage(
        "stage",
        "Stage",
        [Wait(Expr("dynamic_frames"), uid="dynamic_wait")],
    )

    interval = project_timeline(_program(stage), stage).find("dynamic_wait")

    assert isinstance(interval.end, Unknown)
    assert interval.editable == "none"


def test_zero_duration_action_is_a_milestone_not_a_fake_span():
    stage = Stage("stage", "Stage", [FireCircle(count=12, uid="fire")])

    interval = project_timeline(_program(stage), stage).find("fire")

    assert interval.start == interval.end == 0
    assert interval.display == "milestone"


def test_unresolved_call_reference_projects_unknown_instead_of_raising():
    stage = Stage(
        "stage",
        "Stage",
        [Call(Ref("missing_task"), [3], uid="missing_call")],
    )
    program = _program(stage)
    assert any(item.code == "unresolved_reference" for item in program.validate())

    interval = project_timeline(program, stage).find("missing_call")

    assert interval.kind == "dynamic"
    assert isinstance(interval.end, Unknown)


def test_template_is_one_aggregate_interval_without_virtual_nodes():
    stage = Stage(
        "stage",
        "Stage",
        [ring_burst(count=3, interval=7, bullet_count=8, uid="template_call")],
    )
    projection = project_timeline(_program(stage), stage)
    interval = projection.find("template_call")

    assert interval.kind == "template"
    assert interval.start == 0
    assert interval.end == 21
    assert interval.children == ()
    assert len(projection.all_intervals()) == 1


def test_explicit_project_and_external_templates_are_loaded_without_scanning(
    tmp_path, monkeypatch
):
    package = tmp_path / "project_templates"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "bursts.py").write_text(
        "from src.authoring.dsl import Wait, template\n\n"
        "@template\n"
        "def project_pause(frames: int = 4):\n"
        "    return [Wait(frames), Wait(frames)]\n",
        encoding="utf-8",
    )
    (tmp_path / "external_templates.py").write_text(
        "from src.authoring.dsl import Wait, template\n\n"
        "@template\n"
        "def external_pause(frames: int = 3):\n"
        "    return [Wait(frames)]\n",
        encoding="utf-8",
    )
    source_path = tmp_path / "stage.py"
    source_path.write_text(
        "from src.authoring.dsl import Stage\n"
        "from project_templates.bursts import project_pause\n"
        "from external_templates import external_pause\n\n"
        "stage = Stage(\n"
        "    'stage',\n"
        "    'Stage',\n"
        "    [\n"
        "        project_pause(frames=7, uid='project_call'),\n"
        "        external_pause(frames=5, uid='external_call'),\n"
        "    ],\n"
        ")\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    document = load_python_source(source_path, module_name="authoring_demo.stage")
    assert not document.read_only

    projection = project_timeline(_program(document.unit), document.unit)

    assert projection.find("project_call").kind == "template"
    assert projection.find("project_call").end == 14
    assert projection.find("external_call").kind == "template"
    assert projection.find("external_call").start == 14
    assert projection.find("external_call").end == 19
    assert projection.find("project_call").children == ()


def test_missing_explicit_template_is_dynamic_unknown(tmp_path):
    source_path = tmp_path / "stage.py"
    source_path.write_text(
        "from src.authoring.dsl import Stage\n"
        "from package_that_does_not_exist import missing_template\n\n"
        "stage = Stage('stage', 'Stage', [missing_template(uid='missing_call')])\n",
        encoding="utf-8",
    )
    document = load_python_source(source_path, module_name="authoring_demo.stage")
    assert not document.read_only

    interval = project_timeline(_program(document.unit), document.unit).find("missing_call")

    assert interval.kind == "dynamic"
    assert isinstance(interval.end, Unknown)


def test_referenced_wave_boss_and_dialogue_resource_have_declared_durations(tmp_path):
    dialogue_path = tmp_path / "assets" / "dialogue.json"
    dialogue_path.parent.mkdir()
    dialogue_path.write_text(
        json.dumps(
            [
                {"text": "hello", "duration": 20},
                {"text": "world", "duration": 30},
            ]
        ),
        encoding="utf-8",
    )
    wave = Wave("wave", "Wave", [Wait(40, uid="wave_wait")])
    spell = Spell("spell", "Spell", time_limit=2.0, body=[Wait(10, uid="spell_wait")])
    boss = Boss("boss", "Boss", "sunny", [Ref("spell")])
    stage = Stage(
        "stage",
        "Stage",
        [
            RunWave(Ref("wave"), uid="run_wave"),
            RunBoss(Ref("boss"), uid="run_boss"),
            PlayDialogue(
                "res://assets/dialogue.json",
                initial_delay_frames=5,
                uid="dialogue",
            ),
        ],
    )
    projection = project_timeline(
        _program(stage, wave, spell, boss), stage, project_root=tmp_path
    )

    assert projection.find("run_wave").end == 40
    assert projection.find("wave_wait") is not None
    assert projection.find("run_boss").end == 160
    assert projection.find("dialogue").end == 215
    assert projection.end == 215


def test_trace_overlay_uses_only_the_selected_run_and_aggregates_repeats():
    stage = Stage("stage", "Stage", [Wait(60, uid="wait")])
    projection = project_timeline(_program(stage), stage)
    traced = overlay_trace(
        projection,
        [
            {"run_id": "old", "uid": "wait", "phase": "start", "frame": 999},
            {"run_id": "run", "uid": "wait", "phase": "start", "frame": 4},
            {"run_id": "run", "uid": "wait", "phase": "start", "frame": 8},
            {"run_id": "run", "uid": "wait", "phase": "end", "frame": 70},
            {
                "run_id": "run",
                "kind": "metrics",
                "frame": 60,
                "emitted": 24,
                "live": 96,
                "lasers": 2,
            },
        ],
        "run",
    )

    assert traced.trace_run_id == "run"
    assert traced.find("wait").start == 0
    assert traced.find("wait").end == 60
    assert traced.find("wait").observed_start == 4
    assert traced.find("wait").observed_end == 70
    assert traced.end == 60
    assert traced.observed_end == 70
    assert traced.metrics[0].emitted == 24
    assert traced.metrics[0].live == 96
    assert traced.metrics[0].lasers == 2


def test_trace_records_actual_if_branch_without_overwriting_static_unknown():
    stage = Stage(
        "stage",
        "Stage",
        [
            If(
                Expr("difficulty > 1"),
                [Wait(10, uid="then_wait")],
                [Wait(20, uid="else_wait")],
                uid="branch",
            )
        ],
    )
    projection = project_timeline(_program(stage), stage)
    traced = overlay_trace(
        projection,
        [
            {"uid": "branch", "phase": "start", "frame": 0},
            {"uid": "then_wait", "phase": "start", "frame": 0},
            {"uid": "then_wait", "phase": "end", "frame": 10},
            {"uid": "branch", "phase": "end", "frame": 10},
        ],
        "run",
    )

    branch = traced.find("branch")
    assert isinstance(branch.end, Unknown)
    assert branch.observed_start == 0
    assert branch.observed_end == 10
    assert branch.observed_branch == "then"
    assert branch.display == "unknown"
