"""Typed behavior-graph regression contract.

These tests preserve the shipped authoring and compiler behavior.

Contract notes:
- ``src/pattern/graph.py`` exposes ``GRAPH_NODE_CATEGORIES``, ``BehaviorGraph``,
  ``BehaviorGraphNode``, ``BehaviorGraphEdge``, and ``GraphCompileError``.
- Categories are exactly: source, shape, aim, schedule, motion, modifier,
  condition, event, script.
- Nodes have single typed input/output ports with types:
  ``source: None/"source"``, ``shape: "source"/"geometry"``,
  ``aim: "geometry"/"aim"``, ``schedule: "aim"/"schedule"``,
  ``motion: "schedule"/"motion"``, ``modifier: "motion"/"motion"``,
  ``condition: "event"/"condition"``, ``event: None/"event"``,
  ``script: None/"script"``.
- ``BehaviorGraph()`` / ``add_node(category, node_type, name=None,
  properties=None)`` / ``add_edge(from_id, to_id)`` / ``update_node(node_id,
  **properties)``. ``BehaviorGraph.from_recipe(document)`` derives a graph from
  the same resource (never a second document).
- A graph-mode document (``document.graph = graph``) compiles through the same
  ``PatternCompiler`` and, when the graph is a ``from_recipe`` expansion of
  that document, the resulting ``PatternProgram`` must be field-for-field
  equal to the recipe-mode program (same ``content_hash``).
- Graph validation failures raise ``PatternCompileError`` with diagnostics:
  codes ``port_type_mismatch``, ``graph_cycle``, ``unknown_graph_node_type``,
  and ``missing_graph_connection``.
"""

import json
from dataclasses import replace

import pytest

from src.pattern import (
    GRAPH_NODE_CATEGORIES,
    BehaviorGraph,
    BehaviorGraphEdge,
    BehaviorGraphNode,
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
    PatternProgram,
)


def _recipe():
    document = PatternDocument.new("Ring Recipe")
    document.shape = replace(document.shape, count=12)
    document.aim = replace(document.aim, angle=33.0)
    document.schedule = replace(document.schedule, interval_frames=7, burst_count=2)
    document.motion = replace(document.motion, speed=2.25, spin=45.0)
    document.modifiers = replace(document.modifiers, angle_offset_per_burst=11.25)
    document.seed = 2026
    return document


def test_graph_node_categories_are_exactly_declared():
    assert GRAPH_NODE_CATEGORIES == {
        "source",
        "shape",
        "aim",
        "schedule",
        "motion",
        "modifier",
        "condition",
        "event",
        "script",
    }


def test_every_category_can_add_a_node():
    graph = BehaviorGraph()
    node_types = {
        "source": "bullet",
        "shape": "ring",
        "aim": "fixed",
        "schedule": "interval",
        "motion": "constant",
        "modifier": "angle_offset",
        "condition": "threshold",
        "event": "signal",
        "script": "behavior",
    }
    nodes = {
        category: graph.add_node(category, node_type)
        for category, node_type in node_types.items()
    }

    for category, node in nodes.items():
        assert isinstance(node, BehaviorGraphNode)
        assert node.category == category
        assert node.id

    assert len(graph.nodes) == 9


def test_from_recipe_expansion_compiles_to_an_identical_program():
    document = _recipe()
    graph = BehaviorGraph.from_recipe(document)

    assert isinstance(graph, BehaviorGraph)
    assert document.graph is None

    recipe_program = PatternCompiler().compile(document)
    document.graph = graph
    graph_program = PatternCompiler().compile(document)

    assert isinstance(graph_program, PatternProgram)
    assert graph_program == recipe_program
    assert graph_program.content_hash == recipe_program.content_hash


def test_from_recipe_never_forks_the_resource():
    document = _recipe()
    original_id = document.id
    original_type = document.type

    graph = BehaviorGraph.from_recipe(document)
    document.graph = graph
    payload = document.to_dict()
    reloaded = PatternDocument.from_dict(json.loads(json.dumps(payload)))

    assert reloaded.id == original_id
    assert reloaded.type == original_type
    assert reloaded.graph is not None
    assert PatternCompiler().compile(reloaded) == PatternCompiler().compile(document)


def test_graph_edits_change_the_compiled_program():
    document = _recipe()
    graph = BehaviorGraph.from_recipe(document)
    shape = next(node for node in graph.nodes if node.category == "shape")
    graph.update_node(shape.id, count=8)
    document.graph = graph

    program = PatternCompiler().compile(document)

    assert len(program.templates[0].angle_offsets) == 8


def test_graph_round_trip_preserves_nodes_edges_and_uuids():
    document = _recipe()
    document.graph = BehaviorGraph.from_recipe(document)
    node_ids = {node.id for node in document.graph.nodes}
    edge_ids = {edge.id for edge in document.graph.edges}

    reloaded = PatternDocument.from_dict(json.loads(json.dumps(document.to_dict())))

    assert {node.id for node in reloaded.graph.nodes} == node_ids
    assert {edge.id for edge in reloaded.graph.edges} == edge_ids
    assert isinstance(next(iter(reloaded.graph.edges)), BehaviorGraphEdge)
    assert PatternCompiler().compile(reloaded) == PatternCompiler().compile(document)


def test_port_type_mismatch_is_rejected_with_diagnostic():
    document = _recipe()
    graph = BehaviorGraph()
    source = graph.add_node("source", "bullet")
    motion = graph.add_node("motion", "constant")
    graph.add_edge(source.id, motion.id)
    document.graph = graph

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document)

    assert caught.value.diagnostics[0].code == "port_type_mismatch"
    assert caught.value.diagnostics[0].resource_id == document.id


def test_cycle_is_rejected_with_diagnostic():
    document = _recipe()
    graph = BehaviorGraph.from_recipe(document)
    motion = next(node for node in graph.nodes if node.category == "motion")
    modifier = graph.add_node("modifier", "angle_offset")
    graph.add_edge(motion.id, modifier.id)
    graph.add_edge(modifier.id, modifier.id)
    document.graph = graph

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document)

    assert caught.value.diagnostics[0].code == "graph_cycle"


def test_unknown_node_type_is_rejected_with_diagnostic():
    document = _recipe()
    graph = BehaviorGraph()
    graph.add_node("shape", "no_such_type")
    document.graph = graph

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document)

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "unknown_graph_node_type"
    assert "no_such_type" in diagnostic.message


def test_missing_required_connection_is_rejected_with_diagnostic():
    document = _recipe()
    graph = BehaviorGraph()
    source = graph.add_node("source", "bullet")
    shape = graph.add_node("shape", "ring")
    aim = graph.add_node("aim", "fixed")
    schedule = graph.add_node("schedule", "interval")
    motion = graph.add_node("motion", "constant")
    graph.add_edge(source.id, shape.id)
    graph.add_edge(shape.id, aim.id)
    graph.add_edge(schedule.id, motion.id)
    document.graph = graph

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document)

    assert caught.value.diagnostics[0].code == "missing_graph_connection"


def test_invalid_expression_inside_graph_keeps_diagnostic_path():
    document = _recipe()
    graph = BehaviorGraph.from_recipe(document)
    motion = next(node for node in graph.nodes if node.category == "motion")
    graph.update_node(motion.id, speed_expression="frame + __import__('os')")
    document.graph = graph

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document)

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "invalid_expression"
    assert "speed_expression" in diagnostic.path
