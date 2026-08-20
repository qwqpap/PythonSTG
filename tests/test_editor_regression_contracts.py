"""Editor/runtime regression contracts across expressions, authoring, and SDKs.

The suite exercises observable runtime behavior, error boundaries, lifecycle
cleanup, registry integration, recovery, and distribution boundaries. It does
not perform native visual acceptance.
"""

from __future__ import annotations

import importlib
import json
import math
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from src.qt_compat.QtWidgets import QGraphicsItem

from src.authoring.registry import (
    ResourceTypeRegistry,
    ResourceTypeSpec,
    build_default_resource_type_registry,
)
from src.authoring.resources import (
    BACKGROUND_RESOURCE_TYPE,
    UI_RESOURCE_TYPE,
    ResourceDocumentError,
    ResourceHeader,
)
from src.authoring.storage import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.graph_commands import (
    AddGraphEdgeCommand,
    AddGraphNodeCommand,
    RemoveGraphEdgeCommand,
    RemoveGraphNodeCommand,
    SetGraphNodePositionCommand,
)
from src.editor.node_types import NodeTypeRegistry, NodeTypeSpec
from src.editor.plugin_sdk import (
    PLUGIN_API_VERSION,
    PluginManifest,
    PluginRegistry,
)
from src.game.adapters import (
    EventAdapter,
    LocalIPCAdapter,
    UDPAdapter,
    WebSocketAdapter,
)
from src.game.background_render.document import (
    BackgroundDocument,
    BackgroundDocumentError,
)
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.events import Event, EventBus, EventBusError
from src.game.stage.context import StageContext
from src.pattern import (
    BindingSpec,
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
    PatternDocumentError,
    PatternRunner,
    PatternRunnerState,
    PatternRuntimeError,
    ScriptBehavior,
    ScriptContext,
)
from src.pattern.bindings import BindingError
from src.pattern.compiler import BINDABLE_TARGETS
from src.pattern.expressions import (
    CompiledExpression,
    ExpressionError,
    compile_expression,
    evaluate_node,
)
from src.pattern.graph import (
    BehaviorGraph,
    BehaviorGraphEdge,
    BehaviorGraphNode,
    GraphDocumentError,
)
from src.ui.document import UICompileError, UIDocument, UIDocumentNode


REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# M5: expressions, bindings, graph equivalence, and ScriptBehavior lifecycle


@pytest.mark.parametrize(
    "source",
    ("min()", "max()", "abs()", "abs(1, 2)", "clamp(1, 2)"),
)
def test_expression_function_arity_is_rejected_at_compile_time(source: str) -> None:
    with pytest.raises(ExpressionError):
        compile_expression(source)


@pytest.mark.parametrize("source", ("10 ** 10000", "(-1) ** 0.5"))
def test_constant_non_finite_or_invalid_math_is_rejected_at_compile_time(
    source: str,
) -> None:
    with pytest.raises(ExpressionError):
        compile_expression(source)


def test_compiled_expression_json_round_trip_is_lossless() -> None:
    compiled = compile_expression("clamp(frame * 0.5, 0, 10)")
    payload = json.loads(json.dumps(compiled.to_dict()))

    reloaded = CompiledExpression.from_dict(payload)

    assert reloaded == compiled
    assert reloaded.eval({"frame": 8}) == pytest.approx(4.0)


@pytest.mark.parametrize(
    "node",
    ((), ("num",), ("bin", "add"), ("call", "abs", ()), ("unknown", 1)),
)
def test_malformed_compiled_expression_never_leaks_builtin_exceptions(node) -> None:
    with pytest.raises(ExpressionError):
        evaluate_node(node, {})


def test_runtime_math_failures_are_expression_errors() -> None:
    compiled = compile_expression("(-1) ** frame")

    with pytest.raises(ExpressionError):
        compiled.eval({"frame": 0.5})


@pytest.mark.parametrize(
    "path",
    ("motion..speed", ".motion.speed", "motion.speed.", "motion speed"),
)
def test_binding_paths_are_well_formed_dotted_paths(path: str) -> None:
    with pytest.raises(BindingError):
        BindingSpec(path=path, kind="constant", value=1.0).validate()


def test_duplicate_binding_targets_are_rejected_with_a_structured_diagnostic() -> None:
    document = PatternDocument.new("duplicate binding")
    document.bindings = (
        BindingSpec("motion.speed", "constant", 1.0),
        BindingSpec("motion.speed", "expression", "2 + frame"),
    )

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document)

    assert caught.value.diagnostics[0].code == "duplicate_binding_target"
    assert "motion.speed" in caught.value.diagnostics[0].path


class _DummyPlayer:
    def __init__(self, x: float = 0.0, y: float = -0.8):
        self.pos = [x, y]


def _base_binding_document(*, shape_kind: str = "ring") -> PatternDocument:
    document = PatternDocument.new("binding parity")
    document.shape = replace(
        document.shape,
        kind=shape_kind,
        count=3,
        origin_x=0.0,
        origin_y=0.0,
        angle_span=270.0,
        line_length=0.4,
        line_angle=0.0,
    )
    document.schedule = replace(
        document.schedule,
        delay_frames=0,
        interval_frames=2,
        burst_count=2,
        loop_count=1,
    )
    document.motion = replace(
        document.motion,
        speed=1.0,
        friction=0.0,
        spin=0.0,
        time_scale=1.0,
        max_lifetime=8.0,
        render_scale=1.0,
        bounce_x=False,
        bounce_y=False,
    )
    return document


def _set_document_property(
    document: PatternDocument, path: str, value
) -> PatternDocument:
    payload = document.to_dict()
    section, key = path.split(".", 1)
    payload[section][key] = value
    return PatternDocument.from_dict(payload)


def _runtime_snapshot(document: PatternDocument, *, frames: int = 24):
    pool = OptimizedBulletPool(max_bullets=4096)
    context = StageContext(pool, _DummyPlayer())
    runner = PatternRunner(PatternCompiler().compile(document), owner_tag=7801)
    runner.start(context)
    events = []
    for _ in range(frames):
        result = runner.tick(context)
        if result.event is not None:
            event = result.event
            events.append(
                (
                    event.frame,
                    event.burst_index,
                    tuple(tuple(float(v) for v in p) for p in event.positions),
                    tuple(float(v) for v in event.angles),
                    tuple(float(v) for v in event.speeds),
                )
            )
    alive = np.flatnonzero(pool.data["alive"])
    fields = {}
    for name in (
        "pos",
        "speed",
        "friction",
        "time_scale",
        "max_lifetime",
        "render_scale",
        "angular_vel",
        "flags",
    ):
        fields[name] = np.asarray(pool.data[name][alive]).tolist()
    return events, fields


BINDING_CASES = (
    ("shape.count", 5, "ring"),
    ("shape.origin_x", 0.25, "ring"),
    ("shape.origin_y", -0.25, "ring"),
    ("shape.angle_span", 180.0, "arc"),
    ("shape.line_length", 0.9, "line"),
    ("shape.line_angle", 35.0, "line"),
    ("aim.angle", 25.0, "ring"),
    ("schedule.delay_frames", 2, "ring"),
    ("schedule.interval_frames", 3, "ring"),
    ("schedule.burst_count", 3, "ring"),
    ("schedule.loop_count", 2, "ring"),
    ("motion.speed", 2.25, "ring"),
    ("motion.friction", 0.2, "ring"),
    ("motion.spin", 45.0, "ring"),
    ("motion.time_scale", 0.5, "ring"),
    ("motion.max_lifetime", 2.0, "ring"),
    ("motion.render_scale", 1.5, "ring"),
    ("motion.bounce_x", True, "ring"),
    ("motion.bounce_y", True, "ring"),
    ("modifiers.angle_offset_per_burst", 12.0, "ring"),
    ("modifiers.speed_offset_per_burst", 0.15, "ring"),
    ("modifiers.random_speed_variation", 0.2, "random"),
)


def test_binding_behavior_matrix_covers_every_declared_target() -> None:
    assert {path for path, _value, _shape in BINDING_CASES} == set(
        BINDABLE_TARGETS
    )


@pytest.mark.parametrize("path,value,shape_kind", BINDING_CASES)
def test_constant_binding_matches_direct_property_runtime_behavior(
    path: str, value, shape_kind: str
) -> None:
    base = _base_binding_document(shape_kind=shape_kind)
    direct = _set_document_property(base, path, value)
    bound = PatternDocument.from_dict(base.to_dict())
    bound.bindings = (BindingSpec(path=path, kind="constant", value=value),)

    base_snapshot = _runtime_snapshot(base)
    direct_snapshot = _runtime_snapshot(direct)
    assert direct_snapshot != base_snapshot, f"acceptance case for {path} is not observable"
    assert _runtime_snapshot(bound) == direct_snapshot


def test_dynamic_non_speed_bindings_are_evaluated_per_emission() -> None:
    document = _base_binding_document()
    document.shape = replace(document.shape, count=1)
    document.bindings = (
        BindingSpec(
            "motion.friction",
            "expression",
            "0.1 + burst_index * 0.2",
        ),
    )

    _events, fields = _runtime_snapshot(document, frames=4)

    assert fields["friction"] == pytest.approx([0.1, 0.3])


def test_dynamic_shape_count_changes_batch_size_without_per_bullet_callbacks() -> None:
    document = _base_binding_document()
    document.bindings = (
        BindingSpec("shape.count", "expression", "2 + burst_index"),
    )
    pool = OptimizedBulletPool(max_bullets=64)
    context = StageContext(pool, _DummyPlayer())
    runner = PatternRunner(PatternCompiler().compile(document), owner_tag=7802)
    runner.start(context)

    events = [runner.tick(context).event, runner.tick(context).event, runner.tick(context).event]
    events = [event for event in events if event is not None]

    assert [len(event.indices) for event in events] == [2, 3]
    assert pool.batch_spawn_calls == 2
    assert not pool.emitter_callbacks
    assert not pool.death_handlers


def test_recipe_to_graph_preserves_every_binding_and_program_field() -> None:
    document = _base_binding_document()
    document.bindings = tuple(
        BindingSpec(path, "constant", value)
        for path, value, _shape_kind in BINDING_CASES
    )
    recipe_program = PatternCompiler().compile(document)

    document.graph = BehaviorGraph.from_recipe(document)
    graph_program = PatternCompiler().compile(document)

    assert graph_program == recipe_program
    reloaded = PatternDocument.from_dict(
        json.loads(json.dumps(document.to_dict()))
    )
    assert PatternCompiler().compile(reloaded) == recipe_program


def test_graph_nodes_are_deeply_immutable() -> None:
    document = _base_binding_document()
    graph = BehaviorGraph.from_recipe(document)
    node = graph.nodes[0]

    with pytest.raises(TypeError):
        node.properties["audit_mutation"] = True


def test_graph_mutation_api_rejects_unknown_category_and_node_type() -> None:
    graph = BehaviorGraph()

    with pytest.raises(GraphDocumentError):
        graph.add_node("unknown", "thing")
    with pytest.raises(GraphDocumentError):
        graph.add_node("shape", "unknown_shape")


def test_graph_document_validation_rejects_invalid_identity_ports_and_coordinates() -> None:
    document = _base_binding_document()
    graph = BehaviorGraph.from_recipe(document)
    first, second = graph.nodes[:2]
    duplicate = replace(second, id=first.id)
    bad_edge = replace(graph.edges[0], from_port="not-an-output")
    bad_position = replace(graph.nodes[2], position=(math.nan, math.inf))
    graph.nodes = (first, duplicate, bad_position, *graph.nodes[3:])
    graph.edges = (bad_edge, *graph.edges[1:])
    document.graph = graph

    with pytest.raises((PatternDocumentError, GraphDocumentError)):
        document.validate()


def test_graph_validation_rejects_fan_in_fan_out_and_orphan_semantic_nodes() -> None:
    document = _base_binding_document()
    graph = BehaviorGraph.from_recipe(document)
    by_category = {node.category: node for node in graph.nodes}
    orphan = BehaviorGraphNode(
        id="0f65209f-1317-457d-b43b-dfb6a266dd1d",
        category="modifier",
        node_type="angle_offset",
        name="orphan",
        properties={},
    )
    duplicate_out = BehaviorGraphEdge(
        id="5199cc23-4477-43ba-9056-4f786d4c56d1",
        from_node=by_category["motion"].id,
        from_port="out",
        to_node=orphan.id,
        to_port="in",
    )
    duplicate_in = BehaviorGraphEdge(
        id="f5d3c2f9-bc46-441d-904f-491ee5dce8a8",
        from_node=by_category["modifier"].id,
        from_port="out",
        to_node=orphan.id,
        to_port="in",
    )
    graph.nodes = (*graph.nodes, orphan)
    graph.edges = (*graph.edges, duplicate_out, duplicate_in)
    document.graph = graph

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document)

    assert caught.value.diagnostics[0].code in {
        "multiple_graph_inputs",
        "multiple_graph_outputs",
        "orphan_graph_node",
    }


def test_graph_add_node_and_edge_redo_preserves_stable_ids() -> None:
    document = _base_binding_document()
    document.graph = BehaviorGraph.from_recipe(document)
    add_node = AddGraphNodeCommand(document, "modifier", "angle_offset")
    add_node.execute()
    node_id = document.graph.nodes[-1].id
    add_node.undo()
    add_node.execute()
    assert document.graph.nodes[-1].id == node_id

    motion = next(node for node in document.graph.nodes if node.category == "motion")
    target = document.graph.nodes[-1]
    add_edge = AddGraphEdgeCommand(document, motion.id, target.id)
    add_edge.execute()
    edge_id = document.graph.edges[-1].id
    add_edge.undo()
    add_edge.execute()
    assert document.graph.edges[-1].id == edge_id


def test_graph_remove_move_and_invalid_connect_rollback_preserve_identity() -> None:
    document = _base_binding_document()
    document.graph = BehaviorGraph.from_recipe(document)
    graph = document.graph
    assert graph is not None
    motion = next(node for node in graph.nodes if node.category == "motion")
    modifier = next(node for node in graph.nodes if node.category == "modifier")
    original_position = motion.position

    move = SetGraphNodePositionCommand(document, motion.id, 123.0, 456.0)
    move.execute()
    assert next(node for node in graph.nodes if node.id == motion.id).position == (
        123.0,
        456.0,
    )
    move.undo()
    assert next(node for node in graph.nodes if node.id == motion.id).position == original_position

    edge = next(
        edge
        for edge in graph.edges
        if edge.from_node == motion.id and edge.to_node == modifier.id
    )
    remove_edge = RemoveGraphEdgeCommand(document, edge.id)
    remove_edge.execute()
    assert edge.id not in {item.id for item in graph.edges}
    remove_edge.undo()
    assert edge.id in {item.id for item in graph.edges}

    remove_node = RemoveGraphNodeCommand(document, modifier.id)
    remove_node.execute()
    assert modifier.id not in {node.id for node in graph.nodes}
    remove_node.undo()
    assert modifier.id in {node.id for node in graph.nodes}
    assert edge.id in {item.id for item in graph.edges}

    before = document.to_dict()
    with pytest.raises(ValueError):
        AddGraphEdgeCommand(document, motion.id, motion.id).execute()
    assert document.to_dict() == before


def test_graph_validation_rejects_duplicate_edge_ids() -> None:
    document = _base_binding_document()
    graph = BehaviorGraph.from_recipe(document)
    graph.edges = (*graph.edges, replace(graph.edges[0], id=graph.edges[1].id))
    document.graph = graph

    with pytest.raises(GraphDocumentError) as caught:
        document.validate()
    assert "duplicate edge UUID" in str(caught.value)


def test_graph_compile_rejects_cycles_with_structured_diagnostic() -> None:
    document = _base_binding_document()
    graph = BehaviorGraph.from_recipe(document)
    modifier = next(node for node in graph.nodes if node.category == "modifier")
    second_modifier = replace(
        modifier,
        id="0c9d8e7f-6a5b-4c3d-92e1-f0a9b8c7d6e5",
        name="modifier-cycle",
    )
    graph.nodes = (*graph.nodes, second_modifier)
    graph.edges = (
        *graph.edges,
        BehaviorGraphEdge(
            id="e1f6a7b8-c9d0-41e2-83f4-5a6b7c8d9e01",
            from_node=modifier.id,
            from_port="out",
            to_node=second_modifier.id,
            to_port="in",
        ),
        BehaviorGraphEdge(
            id="f2a7b8c9-d0e1-42f3-94a5-6b7c8d9e0f12",
            from_node=second_modifier.id,
            from_port="out",
            to_node=modifier.id,
            to_port="in",
        ),
    )
    document.graph = graph

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document)
    assert caught.value.diagnostics[0].code == "graph_cycle"


class _RecordingScriptContext(ScriptContext):
    def __init__(self):
        super().__init__(OptimizedBulletPool(max_bullets=64), _DummyPlayer())
        self.events = []

    def emit_event(self, event_type, data):
        self.events.append((event_type, data))
        return len(self.events) - 1


def _scripted_document(tmp_path: Path, source: str) -> tuple[PatternDocument, ProjectContext]:
    scripts = tmp_path / "game_content" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "gate_script.py").write_text(source, encoding="utf-8")
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True, exist_ok=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    document = _base_binding_document()
    document.script = ScriptBehavior(
        resource_uri="res://game_content/scripts/gate_script.py"
    )
    return document, ProjectContext(tmp_path)


def test_script_top_level_import_failure_is_a_compile_diagnostic(tmp_path) -> None:
    document, project = _scripted_document(
        tmp_path, 'raise RuntimeError("top-level boom")\n'
    )

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=project)

    assert caught.value.diagnostics[0].code == "script_import_error"


def test_script_start_failure_is_structured_and_sets_error_state(tmp_path) -> None:
    document, project = _scripted_document(
        tmp_path,
        'def start(ctx):\n    raise RuntimeError("start boom")\n',
    )
    runner = PatternRunner(
        PatternCompiler().compile(document, project=project), owner_tag=7803
    )

    with pytest.raises(PatternRuntimeError, match="start boom"):
        runner.start(_RecordingScriptContext())

    assert runner.state == PatternRunnerState.ERROR


def test_paused_or_stopped_runner_never_calls_script_update(tmp_path) -> None:
    document, project = _scripted_document(
        tmp_path,
        'def update(ctx, frame):\n    ctx.emit_event("update", frame)\n',
    )
    context = _RecordingScriptContext()
    runner = PatternRunner(
        PatternCompiler().compile(document, project=project), owner_tag=7804
    )
    runner.start(context)
    runner.pause()
    runner.tick(context)
    runner.stop(context)
    runner.tick(context)

    assert context.events == []


def test_repeated_start_is_idempotent_for_script_hooks(tmp_path) -> None:
    document, project = _scripted_document(
        tmp_path,
        'def load(ctx):\n    ctx.emit_event("load", None)\n'
        'def start(ctx):\n    ctx.emit_event("start", None)\n',
    )
    context = _RecordingScriptContext()
    runner = PatternRunner(
        PatternCompiler().compile(document, project=project), owner_tag=7805
    )
    runner.start(context)
    runner.start(context, reset=False)

    assert [kind for kind, _ in context.events] == ["load", "start"]


def test_stop_hook_failure_still_cleans_up_runner(tmp_path) -> None:
    document, project = _scripted_document(
        tmp_path,
        'def stop(ctx):\n    raise RuntimeError("stop boom")\n',
    )
    context = _RecordingScriptContext()
    runner = PatternRunner(
        PatternCompiler().compile(document, project=project), owner_tag=7806
    )
    runner.start(context)

    with pytest.raises(PatternRuntimeError, match="stop boom"):
        runner.stop(context)

    assert runner.state == PatternRunnerState.STOPPED
    assert runner.frame == 0


# ---------------------------------------------------------------------------
# M6: UI/background validation, runtime parity, and editor contribution wiring


def _ui_document_with_child(**changes) -> tuple[UIDocument, UIDocumentNode]:
    root = UIDocumentNode(node_type="node", name="root")
    child = UIDocumentNode(
        node_type="text",
        name="label",
        x=10.0,
        y=20.0,
        width=100.0,
        height=30.0,
        text="gate",
    )
    for key, value in changes.items():
        setattr(child, key, value)
    root.add_child(child)
    document = UIDocument(
        ResourceHeader(type=UI_RESOURCE_TYPE, name="Gate UI"), root
    )
    return document, child


def test_ui_geometry_bindings_apply_before_layout_at_requested_viewport() -> None:
    document, child = _ui_document_with_child(
        anchors=(False, True, True, False),
        bindings={"x": "5", "width": "value * 2"},
    )

    elements = document.get_render_elements(
        viewport_width=640,
        viewport_height=360,
        value=80,
        frame=30,
    )

    assert elements[0]["position"] == pytest.approx((640 - 160 - 5, 20))
    assert elements[0]["width"] == pytest.approx(160)


def test_ui_binding_builtin_failure_is_always_structured() -> None:
    document, child = _ui_document_with_child(bindings={"alpha": "min()"})

    with pytest.raises(UICompileError) as caught:
        document.get_render_elements()

    assert caught.value.diagnostics[0].code == "invalid_binding"
    assert "alpha" in caught.value.diagnostics[0].path


@pytest.mark.parametrize(
    "mutator",
    (
        lambda document, child: setattr(document.header, "type", "wrong.type"),
        lambda document, child: setattr(child, "id", "not-a-uuid"),
        lambda document, child: setattr(child, "anchors", (True, False)),
        lambda document, child: setattr(child, "margins", (0.0, math.nan, 0.0, 0.0)),
        lambda document, child: setattr(child, "style", "C:/outside/theme.json"),
        lambda document, child: setattr(child, "width", -1.0),
        lambda document, child: setattr(child, "bindings", {"not_a_property": "1"}),
    ),
)
def test_ui_document_rejects_invalid_headers_identity_layout_and_bindings(
    mutator,
) -> None:
    document, child = _ui_document_with_child()
    mutator(document, child)

    with pytest.raises(UICompileError):
        document.validate()


def _background_document(body: dict) -> BackgroundDocument:
    return BackgroundDocument(
        ResourceHeader(type=BACKGROUND_RESOURCE_TYPE, name="Gate Background"),
        body,
    )


@pytest.mark.parametrize(
    "body",
    (
        {"unknown": True},
        {"textures": {}, "camera": {"eye": [math.nan, 0, 0]}, "layers": []},
        {
            "textures": {"known": {"path": "known.png"}},
            "layers": [
                {
                    "name": "bad-alpha",
                    "texture": "known",
                    "alpha": "opaque",
                    "tile": {},
                }
            ],
        },
        {
            "textures": {"known": {"path": "known.png"}},
            "layers": [
                {"name": "missing-texture", "texture": "absent", "tile": {}}
            ],
        },
    ),
)
def test_background_document_rejects_unknown_nonfinite_and_broken_references(
    body: dict,
) -> None:
    with pytest.raises(BackgroundDocumentError):
        _background_document(body).validate()


def test_ui_and_background_registry_entries_are_full_runtime_contributions() -> None:
    registry = build_default_resource_type_registry()

    for resource_type in (UI_RESOURCE_TYPE, BACKGROUND_RESOURCE_TYPE):
        spec = registry[resource_type]
        assert callable(spec.editor_factory)
        assert callable(spec.compiler)
        assert callable(spec.preview_handler)


def test_ui_canvas_exposes_undoable_gizmo_and_resource_drop_contracts(
    qapp_session,
) -> None:
    module = importlib.import_module("src.editor.ui_workspace")
    canvas = module.UICanvas()
    document, child = _ui_document_with_child()
    canvas.set_document(document, (384, 448))

    assert hasattr(canvas, "nodeGeometryCommitted")
    assert hasattr(canvas, "resourceDropped")
    item = canvas.item_for_node(child.id)
    assert item is not None
    movable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    selectable = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    assert bool(item.flags() & movable)
    assert bool(item.flags() & selectable)


def test_ui_canvas_gizmo_commits_geometry_back_to_document(qapp_session) -> None:
    module = importlib.import_module("src.editor.ui_workspace")
    canvas = module.UICanvas()
    document, child = _ui_document_with_child()
    canvas.set_document(document, (384, 448))
    item = canvas.item_for_node(child.id)
    assert item is not None
    committed = []
    canvas.nodeGeometryCommitted.connect(lambda *args: committed.append(args))

    item.setPos(7.0, 9.0)
    qapp_session.processEvents()

    assert committed, "moving a UI item must create an undoable geometry commit"
    node_id, x, y, width, height = committed[-1]
    assert node_id == child.id
    assert child.x == pytest.approx(x)
    assert child.y == pytest.approx(y)
    assert child.width == pytest.approx(width)
    assert child.height == pytest.approx(height)


def test_background_edit_command_round_trips_through_undo() -> None:
    module = importlib.import_module("src.editor.background_commands")
    command_type = module.SetBackgroundPropertyCommand
    document = _background_document(
        {
            "textures": {},
            "camera": {"fovy": 45.0},
            "fog": {},
            "scroll": {},
            "layers": [],
        }
    )
    command = command_type(document, "camera.fovy", 60.0)

    command.execute()
    assert document.body["camera"]["fovy"] == pytest.approx(60.0)
    command.undo()
    assert document.body["camera"]["fovy"] == pytest.approx(45.0)


# ---------------------------------------------------------------------------
# M7: typed events, adapter shutdown, real plugin contributions, hardening


@pytest.mark.parametrize(
    "kwargs",
    (
        {"type": "", "source": "runtime", "frame": 0, "payload": None},
        {"type": "ok", "source": "", "frame": 0, "payload": None},
        {"type": "ok", "source": "runtime", "frame": -1, "payload": None},
        {"type": "ok", "source": "runtime", "frame": 0, "payload": object()},
    ),
)
def test_event_constructor_enforces_typed_json_contract(kwargs) -> None:
    with pytest.raises(EventBusError):
        Event(**kwargs)


def test_event_bus_rejects_invalid_subscription_and_payload() -> None:
    bus = EventBus()

    with pytest.raises(EventBusError):
        bus.subscribe("", lambda event: None)
    with pytest.raises(EventBusError):
        bus.emit("bad.payload", object(), source="gate")


def test_event_bus_is_safe_under_concurrent_adapter_emission() -> None:
    bus = EventBus(max_queue=10_000)
    received = []
    bus.subscribe("parallel", lambda event: received.append(event.payload))
    threads = [
        threading.Thread(
            target=lambda offset=index: [
                bus.emit("parallel", offset * 500 + item, source="worker")
                for item in range(500)
            ]
        )
        for index in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert bus.pending == 4_000
    assert bus.dispatch() == 4_000
    assert sorted(received) == list(range(4_000))


def test_event_bus_fifo_subscriber_order_error_isolation_overflow_and_close() -> None:
    bus = EventBus(max_queue=2)
    trace = []

    bus.subscribe("ordered", lambda event: trace.append(("typed-1", event.payload)))

    def fail(_event):
        raise RuntimeError("isolated handler")

    bus.subscribe("ordered", fail)
    bus.subscribe("ordered", lambda event: trace.append(("typed-2", event.payload)))
    bus.subscribe("*", lambda event: trace.append(("wildcard", event.payload)))

    first = bus.emit("ordered", 1, source="gate")
    bus.tick()
    second = bus.emit("ordered", 2, source="gate")
    third = bus.emit("ordered", 3, source="gate")
    assert first.frame == 0
    assert second.frame == 1
    assert third.frame == 1
    assert bus.pending == 2
    assert bus.dropped == 1

    assert bus.dispatch() == 2
    assert trace == [
        ("typed-1", 2),
        ("typed-2", 2),
        ("wildcard", 2),
        ("typed-1", 3),
        ("typed-2", 3),
        ("wildcard", 3),
    ]
    assert len(bus.errors) == 2
    assert all(isinstance(error, RuntimeError) for _event, error in bus.errors)

    bus.close()
    bus.close()
    assert bus.dispatch() == 0
    with pytest.raises(EventBusError):
        bus.emit("ordered", 4, source="gate")


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def test_udp_bind_failure_reports_unhealthy_and_releases_resources() -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    blocker.bind(("127.0.0.1", 0))
    adapter = UDPAdapter("127.0.0.1", blocker.getsockname()[1])
    try:
        adapter.start(EventBus())
        health = adapter.health()
        assert health["ok"] is False
        assert health["running"] is False
        assert health["last_error"]
    finally:
        adapter.stop()
        blocker.close()


def test_udp_stop_joins_thread_and_clears_bus_reference() -> None:
    adapter = UDPAdapter("127.0.0.1", 0)
    adapter.start(EventBus())
    assert adapter.health()["running"] is True

    adapter.stop()

    assert adapter.health()["running"] is False
    assert not any(
        thread.name == "pystg-udp-adapter" and thread.is_alive()
        for thread in threading.enumerate()
    )
    assert adapter._bus is None


def test_udp_handles_closed_bus_without_uncaught_thread_failure() -> None:
    bus = EventBus()
    adapter = UDPAdapter("127.0.0.1", 0)
    adapter.start(bus)
    bus.close()
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender.sendto(b'{"event": "after-close"}', ("127.0.0.1", adapter.bound_port))
        assert _wait_until(lambda: adapter.health()["running"] is False)
        assert adapter.health()["errors"] >= 1
    finally:
        sender.close()
        adapter.stop()


def test_real_local_ipc_and_websocket_adapter_types_exist() -> None:
    module = importlib.import_module("src.game.adapters")

    for name in ("LocalIPCAdapter", "WebSocketAdapter"):
        adapter_type = getattr(module, name, None)
        assert adapter_type is not None, f"missing {name}"
        assert issubclass(adapter_type, EventAdapter)


def test_local_ipc_adapter_routes_real_wire_payload_and_stops_cleanly() -> None:
    bus = EventBus()
    received = []
    bus.subscribe("adapter.local_ipc", lambda event: received.append(event))
    adapter = LocalIPCAdapter(port=0)
    adapter.start(bus)
    try:
        assert adapter.health()["ok"] is True
        adapter.push({"action": "set_node_position", "x": 0.5})
        assert _wait_until(lambda: bus.pending == 1)
        assert bus.dispatch() == 1
        assert received[0].source == "local_ipc"
        assert received[0].payload == {"action": "set_node_position", "x": 0.5}
    finally:
        adapter.stop()
        adapter.stop()
    assert adapter.health()["running"] is False
    assert adapter._bus is None
    assert adapter._thread is None


def test_websocket_adapter_routes_real_json_message_and_stops_cleanly() -> None:
    from websockets.sync.client import connect

    bus = EventBus()
    received = []
    bus.subscribe("adapter.websocket", lambda event: received.append(event))
    adapter = WebSocketAdapter(port=0)
    adapter.start(bus)
    try:
        assert adapter.health()["ok"] is True
        with connect(f"ws://127.0.0.1:{adapter.bound_port}") as client:
            client.send(json.dumps({"phase": 2}))
        assert _wait_until(lambda: bus.pending == 1)
        assert bus.dispatch() == 1
        assert received[0].source == "websocket"
        assert received[0].payload == {"phase": 2}
    finally:
        adapter.stop()
        adapter.stop()
    assert adapter.health()["running"] is False
    assert adapter._bus is None


def test_authored_routing_uses_local_ipc_adapter_not_a_test_list() -> None:
    bus = EventBus()
    context = StageContext(OptimizedBulletPool(max_bullets=16), _DummyPlayer())
    context.bind_event_bus(bus)
    adapter = LocalIPCAdapter(port=0)
    adapter.start(bus)
    try:
        adapter.push(
            {
                "action": "set_node_position",
                "node_id": "boss-wire",
                "x": 0.75,
                "y": -0.25,
            }
        )
        assert _wait_until(lambda: bus.pending == 1)
        bus.dispatch()
    finally:
        adapter.stop()
    assert context._authored_node_positions["boss-wire"] == pytest.approx(
        (0.75, -0.25)
    )


def test_external_event_routes_into_authored_stage_state() -> None:
    bus = EventBus()
    context = StageContext(OptimizedBulletPool(max_bullets=16), _DummyPlayer())
    context.bind_event_bus(bus)

    bus.emit(
        "scene.action",
        {
            "action": "set_node_position",
            "node_id": "boss-1",
            "x": 0.25,
            "y": -0.5,
        },
        source="adapter.loopback",
    )
    bus.dispatch()

    assert context._authored_node_positions["boss-1"] == pytest.approx((0.25, -0.5))


def test_plugin_manifest_is_deeply_immutable() -> None:
    manifest = PluginManifest(
        id="immutable",
        name="Immutable",
        version="1.0.0",
        api_version=PLUGIN_API_VERSION,
        contributions={"commands": ["immutable.run"]},
    )

    with pytest.raises((TypeError, AttributeError)):
        manifest.contributions["commands"].append("mutated")
    with pytest.raises(TypeError):
        manifest.contributions["commands"] = ("mutated",)


def test_plugin_activation_registers_real_core_contributions(tmp_path) -> None:
    project = ProjectContext(tmp_path)
    resource_types = ResourceTypeRegistry()
    node_types = NodeTypeRegistry()
    calls = []

    def activate(context):
        context.register_resource_type(
            ResourceTypeSpec("pystg.sample", "Sample", "sample")
        )
        context.register_node_type(
            NodeTypeSpec("SampleNode", "Sample Node", "#ffffff", ())
        )
        context.register_inspector_editor("SampleNode", lambda: "inspector")
        context.register_command("sample.run", lambda: calls.append("ran"))
        context.register_adapter("sample.loopback", lambda: "adapter")

    manifest = PluginManifest(
        id="sample",
        name="Sample",
        version="1.0.0",
        api_version=PLUGIN_API_VERSION,
        contributions={
            "resource_types": ["pystg.sample"],
            "node_types": ["SampleNode"],
            "inspector_editors": ["SampleNode"],
            "commands": ["sample.run"],
            "adapters": ["sample.loopback"],
        },
        activation=activate,
    )
    registry = PluginRegistry(
        project,
        resource_types=resource_types,
        node_types=node_types,
    )
    registry.register(manifest)
    registry.activate("sample")

    assert "pystg.sample" in resource_types
    assert "SampleNode" in node_types
    assert callable(registry.inspector_editor("SampleNode"))
    registry.command("sample.run")()
    assert calls == ["ran"]
    assert registry.adapter_factory("sample.loopback")() == "adapter"


def test_failed_plugin_activation_rolls_back_partial_contributions(tmp_path) -> None:
    registry = PluginRegistry(
        ProjectContext(tmp_path),
        resource_types=ResourceTypeRegistry(),
        node_types=NodeTypeRegistry(),
    )

    def activate(context):
        context.register_command("broken.partial", lambda: None)
        raise RuntimeError("activation failed")

    registry.register(
        PluginManifest(
            id="broken",
            name="Broken",
            version="1.0.0",
            api_version=PLUGIN_API_VERSION,
            contributions={"commands": ["broken.partial"]},
            activation=activate,
        )
    )
    registry.activate("broken")

    assert registry.state("broken") == "failed"
    with pytest.raises(KeyError):
        registry.command("broken.partial")


def test_plugin_deactivation_removes_owned_runtime_contributions_and_runs_cleanup(
    tmp_path,
) -> None:
    registry = PluginRegistry(
        ProjectContext(tmp_path),
        resource_types=ResourceTypeRegistry(),
        node_types=NodeTypeRegistry(),
    )
    cleaned = []

    def activate(context):
        context.register_command("owned.command", lambda: "ok")
        context.register_compiler("pystg.owned", lambda payload: payload)
        context.register_preview_handler("pystg.owned", lambda payload: payload)
        context.register_adapter("owned.adapter", lambda: "adapter")
        context.on_deactivate(lambda: cleaned.append("cleanup"))

    registry.register(
        PluginManifest(
            id="owned",
            name="Owned",
            version="1.0.0",
            api_version=PLUGIN_API_VERSION,
            contributions={
                "commands": ["owned.command"],
                "compilers": ["pystg.owned"],
                "preview_handlers": ["pystg.owned"],
                "adapters": ["owned.adapter"],
            },
            activation=activate,
        )
    )
    registry.activate("owned")
    assert registry.command("owned.command")() == "ok"
    assert registry.compiler("pystg.owned")({"compiled": True}) == {"compiled": True}
    assert registry.preview_handler("pystg.owned")({"preview": True}) == {"preview": True}
    assert registry.adapter_factory("owned.adapter")() == "adapter"

    registry.deactivate("owned")

    assert registry.state("owned") == "inactive"
    assert cleaned == ["cleanup"]
    for lookup, key in (
        (registry.command, "owned.command"),
        (registry.compiler, "pystg.owned"),
        (registry.preview_handler, "pystg.owned"),
        (registry.adapter_factory, "owned.adapter"),
    ):
        with pytest.raises(KeyError):
            lookup(key)


def _editor_project(tmp_path: Path) -> ProjectContext:
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True, exist_ok=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    (tmp_path / "game_content" / "patterns").mkdir(parents=True, exist_ok=True)
    return ProjectContext(tmp_path)


def test_editor_shell_uses_the_m7_plugin_registry(tmp_path, qapp_session) -> None:
    from src.editor.app import EditorMainWindow

    window = EditorMainWindow(_editor_project(tmp_path))
    try:
        sdk_registries = [
            value
            for value in vars(window).values()
            if isinstance(value, PluginRegistry)
        ]
        assert sdk_registries, "EditorMainWindow does not own the M7 PluginRegistry"
    finally:
        window.close()


def test_corrupt_resource_load_is_structured_and_non_destructive(tmp_path) -> None:
    project = ProjectContext(tmp_path)
    target = tmp_path / "bad.pystg.json"
    original = b'{"broken": '
    target.write_bytes(original)

    with pytest.raises(ResourceDocumentError) as caught:
        ResourceStore(project).load(target)

    assert str(target) in str(caught.value)
    assert "line" in str(caught.value).lower()
    assert target.read_bytes() == original


def test_editor_autosave_and_recovery_are_connected_to_document_sessions(
    tmp_path, qapp_session
) -> None:
    from src.editor.app import EditorMainWindow

    project = _editor_project(tmp_path)
    target = tmp_path / "game_content" / "patterns" / "recover.pystg.json"
    store = ResourceStore(project)
    store.save(PatternDocument.new("Recover me"), target)
    window = EditorMainWindow(project)
    try:
        session = window._open_document(target)
        session.document.motion = replace(session.document.motion, speed=3.5)
        written = window.autosave_open_documents()
        sidecar = target.with_suffix(target.suffix + ".autosave.json")
        assert sidecar in written
        assert sidecar.is_file()
        candidates = window.find_recovery_candidates()
        assert any(candidate.original_path == target for candidate in candidates)
        assert any(candidate.autosave_path == sidecar for candidate in candidates)
    finally:
        window.close()


def test_recovery_rejects_sidecar_identity_or_type_mismatch_without_overwrite(
    tmp_path,
) -> None:
    project = ProjectContext(tmp_path)
    target = tmp_path / "game_content" / "patterns" / "identity.pystg.json"
    store = ResourceStore(project)
    original = PatternDocument.new("Original")
    store.save(original, target)
    original_bytes = target.read_bytes()

    # A sidecar from a different document must never be applied to this source.
    other = PatternDocument.new("Other")
    store.autosave(other, target)
    with pytest.raises(ResourceDocumentError, match="identity/type"):
        store.recover_autosave(target)
    assert target.read_bytes() == original_bytes

    sidecar = target.with_suffix(target.suffix + ".autosave.json")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["type"] = "pystg.ui"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ResourceDocumentError):
        store.recover_autosave(target)
    assert target.read_bytes() == original_bytes


def test_workspace_layout_uses_validated_project_relative_document_paths(
    tmp_path, qapp_session
) -> None:
    from src.editor.app import EditorMainWindow

    project = _editor_project(tmp_path)
    target = tmp_path / "game_content" / "patterns" / "layout.pystg.json"
    ResourceStore(project).save(PatternDocument.new("Layout"), target)
    window = EditorMainWindow(project)
    try:
        window._open_document(target)
        layout_path = tmp_path / "layout.json"
        window.save_layout(layout_path)
        payload = json.loads(layout_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] >= 1
        assert payload["open_documents"] == [
            "res://game_content/patterns/layout.pystg.json"
        ]

        layout_path.write_text(
            json.dumps({"schema_version": 1, "open_documents": "not-an-array"}),
            encoding="utf-8",
        )
        with pytest.raises((ResourceDocumentError, ValueError)):
            window.restore_layout(layout_path)
    finally:
        window.close()


def test_public_editor_uses_pyside6_not_pyqt5() -> None:
    source_files = [
        path
        for root in (REPO_ROOT / "src", REPO_ROOT / "tools")
        for path in root.rglob("*.py")
    ]
    violations = [
        str(path.relative_to(REPO_ROOT))
        for path in source_files
        if "PyQt5" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert not violations, "PyQt5 imports remain: " + ", ".join(violations)
    assert "PySide6" in pyproject
    assert "PyQt5" not in pyproject
