"""Graph canvas UI acceptance: mode switching, commands, and diagnostics.

These tests exercise the E5.2 graph workspace (PatternWorkspace Recipe/Graph
modes, GraphCanvas port drag wiring, graph commands, Inspector branch, and
editor integration). They run offscreen; visual acceptance is recorded
separately.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from PyQt5 import sip
from PyQt5.QtCore import Qt

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.graph_commands import (
    AddGraphEdgeCommand,
    AddGraphNodeCommand,
    ExpandToGraphCommand,
    FoldBackToRecipeCommand,
    RemoveGraphEdgeCommand,
    RemoveGraphNodeCommand,
    SetGraphNodePositionCommand,
    SetGraphNodePropertiesCommand,
)
from src.editor.graph_workspace import (
    GraphCanvas,
    _drag_can_connect,
    can_connect,
)
from src.editor.pattern_workspace import PatternWorkspace
from src.pattern import (
    GRAPH_NODE_CATEGORIES,
    BehaviorGraph,
    PatternCompiler,
    PatternDocument,
)


class FakePreviewClient:
    def __init__(self):
        self.is_running = True
        self.commands = []
        self.closed = False

    def start(self):
        return True

    def send_command(self, command, payload=None):
        request_id = f"request-{len(self.commands) + 1}"
        self.commands.append((command, payload or {}))
        return request_id

    def close(self):
        self.closed = True


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def _pattern():
    document = PatternDocument.new("Graph UI Pattern")
    document.shape = replace(document.shape, count=12)
    document.schedule = replace(document.schedule, interval_frames=8)
    document.motion = replace(document.motion, speed=2.5)
    return document


def _window(tmp_path, document=None):
    project = _project(tmp_path)
    if document is not None:
        ResourceStore(project).save(
            document, "game_content/patterns/graph_ui.pystg.json"
        )
    window = EditorMainWindow(project)
    fake = FakePreviewClient()
    window._pattern_preview_client = fake
    return project, window, fake


# --------------------------------------------------------------------------
# Model: position persistence and port rules
# --------------------------------------------------------------------------


def test_graph_node_position_round_trips_through_document():
    document = _pattern()
    document.graph = BehaviorGraph.from_recipe(document)
    shape = next(node for node in document.graph.nodes if node.category == "shape")
    document.graph.set_node_position(shape.id, 123.0, 456.0)

    reloaded = PatternDocument.from_dict(json.loads(json.dumps(document.to_dict())))
    reloaded_shape = next(
        node for node in reloaded.graph.nodes if node.category == "shape"
    )

    assert reloaded_shape.position == (123.0, 456.0)
    assert PatternCompiler().compile(reloaded) == PatternCompiler().compile(document)


def test_from_recipe_layout_assigns_chain_positions():
    graph = BehaviorGraph.from_recipe(_pattern())

    by_category = {node.category: node.position for node in graph.nodes}

    assert all(position is not None for position in by_category.values())
    assert by_category["source"][0] < by_category["shape"][0] < by_category["aim"][0]
    assert by_category["motion"][0] < by_category["modifier"][0]


def test_can_connect_follows_the_port_type_table():
    assert can_connect("source", "shape")
    assert can_connect("shape", "aim")
    assert can_connect("aim", "schedule")
    assert can_connect("schedule", "motion")
    assert can_connect("motion", "modifier")
    assert can_connect("modifier", "modifier")
    assert not can_connect("source", "motion")
    assert not can_connect("shape", "schedule")
    assert not can_connect("aim", "motion")


def test_drag_can_connect_requires_out_to_in_with_matching_type(qapp_session):
    document = _pattern()
    document.graph = BehaviorGraph.from_recipe(document)
    canvas = GraphCanvas()
    canvas.set_graph(document.graph)
    ports = []

    def collect(port):
        ports.append(port)

    for port in canvas.graphics_scene.items():
        if hasattr(port, "kind"):
            ports.append(port)
    out_ports = [port for port in ports if port.kind == "out"]
    in_ports = [port for port in ports if port.kind == "in"]

    shape_out = next(p for p in out_ports if p.port_type == "geometry")
    aim_in = next(p for p in in_ports if p.port_type == "geometry")
    motion_in = next(p for p in in_ports if p.port_type == "schedule")

    assert _drag_can_connect(shape_out, aim_in)
    assert not _drag_can_connect(shape_out, motion_in)
    assert not _drag_can_connect(aim_in, shape_out)
    assert not _drag_can_connect(shape_out, shape_out)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def test_expand_command_is_undoable_and_redoable():
    document = _pattern()
    command = ExpandToGraphCommand(document)
    command.execute()
    assert document.graph is not None
    assert {node.category for node in document.graph.nodes} == {
        "source",
        "shape",
        "aim",
        "schedule",
        "motion",
        "modifier",
    }
    command.undo()
    assert document.graph is None
    command.execute()
    assert document.graph is not None


def test_fold_command_writes_fields_back_and_undo_restores():
    document = _pattern()
    ExpandToGraphCommand(document).execute()
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )
    document.graph.update_node(shape.id, count=7)
    document.graph.update_node(
        next(node for node in document.graph.nodes if node.category == "motion").id,
        speed_expression="burst_index * 3",
    )

    command = FoldBackToRecipeCommand(document)
    command.execute()

    assert document.graph is None
    assert document.shape.count == 7
    assert document.bindings[0].kind == "expression"
    assert document.bindings[0].path == "motion.speed"

    command.undo()
    assert document.graph is not None
    assert document.shape.count == 12


def test_add_and_remove_node_commands_undo():
    document = _pattern()
    ExpandToGraphCommand(document).execute()
    add = AddGraphNodeCommand(document, "shape", "ring")
    add.execute()
    node_id = add._node_id
    assert len(document.graph.nodes) == 7

    remove = RemoveGraphNodeCommand(document, node_id)
    remove.execute()
    assert len(document.graph.nodes) == 6

    remove.undo()
    assert len(document.graph.nodes) == 7
    add.undo()
    assert len(document.graph.nodes) == 6


def test_add_edge_rejects_type_mismatch_and_undo_removes():
    document = _pattern()
    ExpandToGraphCommand(document).execute()
    graph = document.graph
    shape = next(node for node in graph.nodes if node.category == "shape")
    schedule = next(node for node in graph.nodes if node.category == "schedule")
    motion = next(node for node in graph.nodes if node.category == "motion")

    with pytest.raises(ValueError):
        AddGraphEdgeCommand(document, shape.id, schedule.id).execute()

    add = AddGraphEdgeCommand(document, schedule.id, motion.id)
    add.execute()
    assert len(graph.edges) == 6

    edge_id = add._edge_id
    remove = RemoveGraphEdgeCommand(document, edge_id)
    remove.execute()
    assert len(graph.edges) == 5
    remove.undo()
    assert len(graph.edges) == 6
    add.undo()
    assert len(graph.edges) == 5


def test_set_node_properties_command_undo():
    document = _pattern()
    ExpandToGraphCommand(document).execute()
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )

    command = SetGraphNodePropertiesCommand(document, shape.id, {"count": 9})
    command.execute()
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )
    assert shape.properties["count"] == 9

    command.undo()
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )
    assert shape.properties["count"] == 12


def test_set_node_position_command_coalesces():
    document = _pattern()
    ExpandToGraphCommand(document).execute()
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )
    original = shape.position

    first = SetGraphNodePositionCommand(document, shape.id, 10.0, 20.0)
    first.execute()
    second = SetGraphNodePositionCommand(document, shape.id, 30.0, 40.0)
    second.execute()
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )
    assert shape.position == (30.0, 40.0)

    assert first.merge_with(second)
    first.undo()
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )
    assert shape.position == original


# --------------------------------------------------------------------------
# Workspace UI
# --------------------------------------------------------------------------


def test_workspace_mode_switch_placeholder_and_canvas(qapp_session):
    document = _pattern()
    workspace = PatternWorkspace()
    workspace.set_document(document)

    workspace.set_mode("graph")
    assert workspace.stack.currentWidget() is workspace.graph_placeholder

    ExpandToGraphCommand(document).execute()
    workspace.refresh_graph()
    assert workspace.stack.currentWidget() is workspace.graph_canvas
    assert len(workspace.graph_canvas._node_items) == 6
    assert len(workspace.graph_canvas._edge_items) == 5

    workspace.set_mode("recipe")
    assert workspace.stack.currentWidget() is workspace.canvas


def test_workspace_select_node_and_diagnostics_highlight(qapp_session):
    document = _pattern()
    ExpandToGraphCommand(document).execute()
    workspace = PatternWorkspace()
    workspace.set_document(document)
    workspace.set_mode("graph")
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )

    workspace.select_graph_node(shape.id)
    item = workspace.graph_canvas._node_items[shape.id]
    assert item.isSelected()

    workspace.set_graph_diagnostics((shape.id,), ())
    assert item._error
    workspace.clear_graph_diagnostics()
    assert not item._error


def test_rebuild_during_node_mouse_press_does_not_crash(qapp_session):
    """Rebuilding the scene from inside an item event must not raise.

    Regression for ``QGraphicsScene::addItem: item has already been added``
    and ``RuntimeError: wrapped C/C++ object of type GraphNodeItem has been
    deleted`` when a signal handler rebuilds the canvas synchronously.
    """
    from PyQt5.QtTest import QTest

    document = _pattern()
    ExpandToGraphCommand(document).execute()
    canvas = GraphCanvas()
    canvas.set_graph(document.graph)
    canvas.resize(640, 400)
    canvas.show()
    qapp_session.processEvents()
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )
    item = canvas._node_items[shape.id]

    def rebuild_while_selected(_node_id):
        canvas.set_graph(document.graph)

    canvas.nodeSelected.connect(rebuild_while_selected)

    position = canvas.mapFromScene(item.scenePos())
    QTest.mousePress(canvas.viewport(), Qt.LeftButton, pos=position)
    qapp_session.processEvents()
    QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, pos=position)
    qapp_session.processEvents()

    assert len(canvas._node_items) == 6
    canvas.close()


def test_rebuild_during_port_drag_release_does_not_crash(qapp_session):
    """A rebuild triggered by the port-drop edge signal must not crash."""
    from PyQt5.QtTest import QTest

    document = _pattern()
    ExpandToGraphCommand(document).execute()
    canvas = GraphCanvas()
    canvas.set_graph(document.graph)
    canvas.resize(640, 400)
    canvas.show()
    qapp_session.processEvents()
    ports = [
        item
        for item in canvas.graphics_scene.items()
        if hasattr(item, "kind")
    ]
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )
    motion = next(
        node for node in document.graph.nodes if node.category == "motion"
    )
    shape_out = next(
        port for port in ports if port.owner_id == shape.id and port.kind == "out"
    )
    motion_in = next(
        port for port in ports if port.owner_id == motion.id and port.kind == "in"
    )

    def rebuild_on_edge(from_id, to_id):
        canvas.set_graph(document.graph)

    canvas.edgeRequested.connect(rebuild_on_edge)

    start = canvas.mapFromScene(shape_out.scenePos())
    end = canvas.mapFromScene(motion_in.scenePos())
    QTest.mousePress(canvas.viewport(), Qt.LeftButton, pos=start)
    qapp_session.processEvents()
    QTest.mouseMove(canvas.viewport(), pos=end)
    qapp_session.processEvents()
    QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, pos=end)
    qapp_session.processEvents()

    assert len(canvas._node_items) == 6
    assert canvas._drag_target is None
    canvas.close()


def test_node_items_are_added_to_the_scene_exactly_once(qapp_session):
    """Regression: ports are child items and must not be added twice."""
    document = _pattern()
    ExpandToGraphCommand(document).execute()
    canvas = GraphCanvas()
    canvas.set_graph(document.graph)

    scene = canvas.graphics_scene
    counts = {}
    for item in scene.items():
        counts[item] = counts.get(item, 0) + 1
    assert all(count == 1 for count in counts.values())
    assert len(scene.items()) == 6 + 5 + 11  # nodes + edges + ports


def test_inspector_shows_graph_node_properties(qapp_session):
    from src.editor.app import InspectorPanel

    document = _pattern()
    ExpandToGraphCommand(document).execute()
    shape = next(
        node for node in document.graph.nodes if node.category == "shape"
    )
    inspector = InspectorPanel()

    inspector.set_graph_node(shape)
    labels = []
    for index in range(inspector._form.rowCount()):
        for column in (0, 1):
            item = inspector._form.itemAt(index, column)
            if item is not None and item.widget() is not None:
                labels.append(item.widget().text())
    assert "Shape · ring" in labels
    assert "Count" in labels

    inspector.set_graph_node(None)
    assert inspector._form.rowCount() >= 1


# --------------------------------------------------------------------------
# Editor integration
# --------------------------------------------------------------------------


def test_window_expand_fold_handlers_sync_context_and_preview(tmp_path, qapp_session):
    project, window, fake = _window(tmp_path, document=_pattern())
    record = window.resource_browser.index.find(
        "res://game_content/patterns/graph_ui.pystg.json"
    )
    window._resource_activated(record)
    session = window._active_pattern_session
    workspace = window._document_widgets[session.document.id]
    assert isinstance(workspace, PatternWorkspace)

    window._graph_expand_requested()
    assert session.document.graph is not None
    assert session.editor_context.get("graph_mode") is True
    assert workspace.mode() == "graph"
    assert len(workspace.graph_canvas._node_items) == 6
    load_payload = dict(fake.commands[-1][1])
    assert load_payload["document"]["graph"] is not None

    window._graph_fold_requested()
    assert session.document.graph is None
    assert not session.editor_context.get("graph_mode")
    window.close()


def test_window_graph_edits_are_undoable_and_survive_reopen(tmp_path, qapp_session):
    project, window, fake = _window(tmp_path, document=_pattern())
    record = window.resource_browser.index.find(
        "res://game_content/patterns/graph_ui.pystg.json"
    )
    window._resource_activated(record)
    session = window._active_pattern_session
    window._graph_expand_requested()

    shape = next(
        node
        for node in session.document.graph.nodes
        if node.category == "shape"
    )
    window._graph_node_property_requested(shape.id, {"count": 16})
    shape = next(
        node
        for node in session.document.graph.nodes
        if node.category == "shape"
    )
    assert shape.properties["count"] == 16

    session.undo()
    shape = next(
        node
        for node in session.document.graph.nodes
        if node.category == "shape"
    )
    assert shape.properties["count"] == 12
    session.redo()
    shape = next(
        node
        for node in session.document.graph.nodes
        if node.category == "shape"
    )
    assert shape.properties["count"] == 16

    manager = window.document_manager
    path = manager.save(session)
    manager.close(session)
    reopened = manager.open(path)
    reopened_shape = next(
        node
        for node in reopened.document.graph.nodes
        if node.category == "shape"
    )
    assert reopened_shape.properties["count"] == 16
    window.close()


def test_window_invalid_graph_edit_reports_issue_and_keeps_document(tmp_path, qapp_session):
    project, window, fake = _window(tmp_path, document=_pattern())
    record = window.resource_browser.index.find(
        "res://game_content/patterns/graph_ui.pystg.json"
    )
    window._resource_activated(record)
    session = window._active_pattern_session
    window._graph_expand_requested()
    graph = session.document.graph
    shape = next(node for node in graph.nodes if node.category == "shape")
    schedule = next(node for node in graph.nodes if node.category == "schedule")

    issues = []
    window.preview_panel.handle_issue = lambda issue: issues.append(issue)
    window._graph_edge_requested(shape.id, schedule.id)

    assert len(graph.edges) == 5
    assert issues and issues[0]["code"] == "invalid_graph_edit"
    window.close()


def test_graph_diagnostics_are_parsed_into_canvas_highlights(tmp_path, qapp_session):
    project, window, fake = _window(tmp_path, document=_pattern())
    record = window.resource_browser.index.find(
        "res://game_content/patterns/graph_ui.pystg.json"
    )
    window._resource_activated(record)
    session = window._active_pattern_session
    window._graph_expand_requested()
    workspace = window._document_widgets[session.document.id]
    shape = next(
        node for node in session.document.graph.nodes if node.category == "shape"
    )
    motion = next(
        node for node in session.document.graph.nodes if node.category == "motion"
    )
    window._graph_node_property_requested(
        motion.id, {"speed_expression": "frame + __import__('os')"}
    )

    from src.pattern import PatternCompileError, PatternCompiler

    with pytest.raises(PatternCompileError):
        PatternCompiler().compile(session.document, project=project)

    window._apply_graph_diagnostics(
        [
            {
                "code": "invalid_expression",
                "path": f"graph.node:{motion.id}:speed_expression",
            }
        ]
    )
    assert workspace.graph_canvas._node_items[motion.id]._error
    assert not workspace.graph_canvas._node_items[shape.id]._error

    window._apply_graph_diagnostics([])
    window._clear_graph_diagnostics()
    assert not workspace.graph_canvas._node_items[motion.id]._error
    window.close()
