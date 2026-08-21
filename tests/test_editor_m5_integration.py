"""Phase 5 gate acceptance: one resource across recipe, curves, graph, script.

These tests are the completion gate for the M5 phase gate and must pass
exactly as written. Do not edit, skip, or xfail them; implement the contracts
they assert instead.

Gate requirements covered:
- The same saved resource progresses from recipe to curves/expressions to
  graph and optional script without format forking.
- Common graph motion stays on data-oriented runtime paths.
- Invalid graphs/expressions cannot crash the editor or corrupt the resource.
"""

import json
from dataclasses import replace

import pytest

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.document_manager import DocumentManager
from src.authoring.commands.pattern import SetPatternPropertyCommand
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.pattern import (
    GRAPH_NODE_CATEGORIES,
    BehaviorGraph,
    BindingSpec,
    CurveDocument,
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
    ScriptBehavior,
)
from src.pattern.curves import CurveKeyframe
from src.preview import PatternPreviewController, PreviewCommandError, PreviewState


class DummyPlayer:
    def __init__(self, x=0.0, y=-0.8):
        self.pos = [x, y]


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def _recipe():
    document = PatternDocument.new("Evolved Pattern")
    document.shape = replace(document.shape, count=12)
    document.schedule = replace(document.schedule, interval_frames=8, burst_count=2)
    document.motion = replace(document.motion, speed=2.0)
    return document


def _save_curve(project, name="ramp", keyframes=((0, 1.0), (10, 3.0))):
    curve = CurveDocument.new(
        name.title(),
        keyframes=tuple(CurveKeyframe(frame, value) for frame, value in keyframes),
        interpolation="linear",
    )
    ResourceStore(project).save(curve, f"game_content/curves/{name}.pystg.json")
    return f"res://game_content/curves/{name}.pystg.json"


def _save_script(project, name="controller.py"):
    scripts = project.root / "game_content" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / name).write_text(
        "def start(ctx):\n    ctx.emit_event('script_start', {})\n",
        encoding="utf-8",
    )
    return f"res://game_content/scripts/{name}"


# --------------------------------------------------------------------------
# Gate: one resource, four modes, no forking
# --------------------------------------------------------------------------


def test_single_resource_progresses_recipe_curve_graph_script(tmp_path):
    project = _project(tmp_path)
    document = _recipe()
    original_id = document.id
    compiler = PatternCompiler()

    recipe_program = compiler.compile(document)
    assert recipe_program.bindings == ()

    document.bindings = (
        BindingSpec(
            path="motion.speed",
            kind="curve",
            value=_save_curve(project),
        ),
    )
    bound_program = compiler.compile(document, project=project)
    assert bound_program.bindings

    document.graph = BehaviorGraph.from_recipe(document)
    graph_program = compiler.compile(document, project=project)
    assert graph_program == bound_program

    document.script = ScriptBehavior(resource_uri=_save_script(project))
    script_program = compiler.compile(document, project=project)
    assert script_program.script is not None

    path = "game_content/patterns/evolved.pystg.json"
    ResourceStore(project).save(document, path)
    reloaded = ResourceStore(project).load(path)

    assert isinstance(reloaded, PatternDocument)
    assert reloaded.id == original_id
    assert reloaded.bindings == document.bindings
    assert reloaded.graph is not None
    assert reloaded.script == document.script
    assert compiler.compile(reloaded, project=project) == script_program


def test_graph_mode_motion_stays_on_data_oriented_path(tmp_path):
    project = _project(tmp_path)
    document = _recipe()
    document.bindings = (
        BindingSpec(path="motion.speed", kind="curve", value=_save_curve(project)),
    )
    document.graph = BehaviorGraph.from_recipe(document)

    program = PatternCompiler().compile(document, project=project)
    pool = OptimizedBulletPool(max_bullets=512)
    context = StageContext(pool, DummyPlayer())
    from src.pattern import PatternRunner

    runner = PatternRunner(program, owner_tag=7001)
    runner.start(context)
    runner.advance(context, 9)
    spawned = pool.batch_spawn_calls

    assert spawned == 2
    assert not pool.emitter_callbacks
    assert not pool.death_handlers
    assert len({entry.target_path for entry in program.bindings}) == 1


# --------------------------------------------------------------------------
# Gate: invalid input cannot crash or corrupt
# --------------------------------------------------------------------------


def test_preview_keeps_last_valid_program_after_invalid_expression(tmp_path):
    pool = OptimizedBulletPool(max_bullets=256)
    controller = PatternPreviewController(pool, project=_project(tmp_path))
    document = _recipe()
    document.bindings = (
        BindingSpec(path="motion.speed", kind="constant", value=2.0),
    )
    controller.load(document)
    controller.play()
    controller.update()
    old_program = controller.program
    old_frame = controller.frame

    with pytest.raises(PreviewCommandError):
        controller.set_property(
            "bindings",
            [
                {"path": "motion.speed", "kind": "expression", "value": "frame +"},
            ],
        )

    assert controller.program is old_program
    assert controller.frame == old_frame
    assert controller.state == PreviewState.PLAYING
    stats = controller.get_stats(emit=False)
    assert stats["reload_ok"] is False
    assert any(event.event == "compile_error" for event in controller.drain_events())

    controller.set_property(
        "bindings",
        [
            {"path": "motion.speed", "kind": "expression", "value": "frame / 60.0"},
        ],
    )
    assert controller.get_stats(emit=False)["reload_ok"] is True


def test_invalid_graph_cannot_crash_or_corrupt_the_document(tmp_path):
    project = _project(tmp_path)
    document = _recipe()
    document.graph = BehaviorGraph()
    document.graph.add_node("shape", "no_such_type")

    with pytest.raises(PatternCompileError):
        PatternCompiler().compile(document)

    document.graph = None
    repaired = PatternCompiler().compile(document)
    assert repaired.templates[0].count == 12

    payload = json.loads(json.dumps(document.to_dict()))
    assert PatternDocument.from_dict(payload).id == document.id


def test_document_manager_opens_graph_mode_pattern_and_undo_redoes_bindings(tmp_path):
    project = _project(tmp_path)
    document = _recipe()
    document.bindings = (
        BindingSpec(path="motion.speed", kind="constant", value=2.0),
    )
    ResourceStore(project).save(document, "game_content/patterns/graphy.pystg.json")

    manager = DocumentManager(project, create_initial_scene=False)
    session = manager.open("game_content/patterns/graphy.pystg.json")

    edited = [
        {"path": "motion.speed", "kind": "expression", "value": "burst_index * 2"},
    ]
    expected = (
        BindingSpec(path="motion.speed", kind="expression", value="burst_index * 2"),
    )
    session.apply(SetPatternPropertyCommand(session.document, "bindings", edited))
    assert session.document.bindings == expected
    assert session.undo()
    assert session.document.bindings == document.bindings
    assert session.redo()
    assert session.document.bindings == expected

    manager.save(session)
    manager.close(session)
    reopened = manager.open("game_content/patterns/graphy.pystg.json")
    assert reopened.document.bindings == expected
    PatternCompiler().compile(reopened.document, project=project)


def test_graph_mode_document_round_trips_through_store(tmp_path):
    project = _project(tmp_path)
    document = _recipe()
    document.graph = BehaviorGraph.from_recipe(document)
    path = "game_content/patterns/workspace.pystg.json"
    ResourceStore(project).save(document, path)

    first = ResourceStore(project).load(path)
    assert first.graph is not None
    assert {node.category for node in first.graph.nodes} <= set(GRAPH_NODE_CATEGORIES)

    second = ResourceStore(project).load(path)
    assert {
        node.id for node in first.graph.nodes
    } == {node.id for node in second.graph.nodes}
