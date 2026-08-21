"""N6 contextual-search contract across Graph, Timeline and Scene authoring."""

import json

from src.qt_compat.QtCore import Qt
from src.qt_compat.QtTest import QTest

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.action_catalog import ActionQuery, build_editor_action_catalog
from src.editor.action_search import ActionSearchDialog
from src.editor.app import EditorMainWindow, SceneViewport
from src.editor.graph_commands import ExpandToGraphCommand
from src.editor.graph_workspace import GraphCanvas
from src.editor.node_types import build_default_node_type_registry
from src.editor.panels.pattern_workspace import PatternWorkspace
from src.editor.panels.timeline_workspace import TimelineGraphicsView
from src.editor.i18n import LANGUAGE_CHINESE, LanguageManager
from src.pattern import BehaviorGraph, PatternDocument


class _FakePreviewClient:
    is_running = True

    def __init__(self):
        self.commands = []

    def start(self):
        return True

    def send_command(self, command, payload=None):
        self.commands.append((command, payload or {}))
        return str(len(self.commands))

    def close(self):
        pass


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def _window(tmp_path, qapp_session):
    window = EditorMainWindow(_project(tmp_path))
    window._pattern_preview_client = _FakePreviewClient()
    window.resize(1180, 760)
    window.show()
    qapp_session.processEvents()
    return window


def test_dialog_filters_typed_results_and_enter_returns_descriptor(qapp_session):
    dialog = ActionSearchDialog(
        build_editor_action_catalog(),
        ActionQuery(context="graph", input_type="geometry"),
    )
    chosen = []
    dialog.actionChosen.connect(chosen.append)
    dialog.show()
    qapp_session.processEvents()

    assert dialog.results.count() == 2
    assert all(
        match.descriptor.payload["category"] == "aim"
        for match in dialog._matches
    )
    dialog.search.setText("自机狙")
    QTest.keyClick(dialog.search, Qt.Key_Return)
    qapp_session.processEvents()

    assert len(chosen) == 1
    assert chosen[0].payload == {"category": "aim", "node_type": "player"}


def test_dialog_empty_state_explains_how_to_recover(qapp_session):
    dialog = ActionSearchDialog(
        build_editor_action_catalog(),
        ActionQuery(context="graph", input_type="no-such-port"),
    )

    assert dialog.results.count() == 0
    assert dialog.empty_state.isVisibleTo(dialog)
    assert "compatible" in dialog.empty_state.text()


def test_dialog_translates_timeline_results_and_budget_without_changing_payload(
    qapp_session
):
    manager = LanguageManager(language=LANGUAGE_CHINESE)
    catalog = build_editor_action_catalog()
    dialog = ActionSearchDialog(
        catalog,
        ActionQuery(context="timeline"),
        language_manager=manager,
    )
    texts = [dialog.results.item(index).text() for index in range(dialog.results.count())]
    assert "弹幕轨道" in texts
    descriptor = next(
        match.descriptor
        for match in dialog._matches
        if match.descriptor.id == "action.timeline.track.pattern"
    )
    assert descriptor.payload["kind"] == "Pattern"


def test_space_tap_opens_search_and_restores_pan_mode(qapp_session, tmp_path):
    graph = GraphCanvas()
    timeline = TimelineGraphicsView()
    scene = SceneViewport(
        _project(tmp_path), node_registry=build_default_node_type_registry()
    )
    for view in (graph, timeline, scene):
        requested = []
        view.actionSearchRequested.connect(requested.append)
        original_mode = view.dragMode()
        view.show()
        view.setFocus()
        QTest.keyClick(view, Qt.Key_Space)
        qapp_session.processEvents()
        assert requested == [None]
        assert view.dragMode() == original_mode
        view.close()


def test_releasing_graph_output_in_empty_space_requests_typed_search(qapp_session):
    document = PatternDocument.new("Typed Search")
    document.graph = BehaviorGraph.from_recipe(document)
    canvas = GraphCanvas()
    canvas.set_graph(document.graph)
    source = next(node for node in document.graph.nodes if node.category == "source")
    source_port = next(
        item
        for item in canvas.graphics_scene.items()
        if getattr(item, "owner_id", None) == source.id
        and getattr(item, "kind", None) == "out"
    )
    requested = []
    canvas.actionSearchRequested.connect(requested.append)

    canvas._port_drag_started(source_port, source_port.scenePos())
    canvas._port_drag_released(source_port)

    assert requested == ["source"]


def test_graph_search_executes_real_command_and_undo(tmp_path, qapp_session):
    project = _project(tmp_path)
    document = PatternDocument.new("Search Pattern")
    ResourceStore(project).save(
        document, "game_content/patterns/search.pystg.json"
    )
    window = EditorMainWindow(project)
    window._pattern_preview_client = _FakePreviewClient()
    record = window.resource_browser.index.find(
        "res://game_content/patterns/search.pystg.json"
    )
    window._resource_activated(record)
    session = window._active_pattern_session
    ExpandToGraphCommand(session.document).execute()
    session.editor_state.pattern.graph_mode = True
    session.editor_state.pattern.authoring_level = "l3"
    window._refresh()
    before = len(session.document.graph.nodes)
    action = next(
        match.descriptor
        for match in window.action_catalog.search(ActionQuery(context="graph"))
        if match.descriptor.id == "action.graph.shape.arc"
    )

    window._execute_action(action)
    assert len(session.document.graph.nodes) == before + 1
    assert any(
        node.category == "shape" and node.node_type == "arc"
        for node in session.document.graph.nodes
    )
    assert session.undo()
    assert len(session.document.graph.nodes) == before
    window.close()


def test_scene_and_timeline_search_create_through_command_stack(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    session = window.session
    stage_action = next(
        match.descriptor
        for match in window.action_catalog.search(
            ActionQuery(context="scene", parent_type="SceneRoot")
        )
        if match.descriptor.payload.get("node_type") == "Stage"
    )
    window._execute_action(stage_action)
    assert any(node.type == "Stage" for node in session.document.root.children)
    assert session.undo()
    assert not session.document.root.children

    track_action = next(
        match.descriptor
        for match in window.action_catalog.search(ActionQuery(context="timeline"))
        if match.descriptor.id == "action.timeline.track.event"
    )
    window._execute_action(track_action)
    state = session.document.state_graph.find_state(
        session.document.state_graph.initial_state_id
    )
    assert [track.kind for track in state.tracks] == ["Event"]
    assert session.undo()
    assert state.tracks == []
    window.close()


def test_window_space_uses_selected_parent_and_selected_track_context(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    window._open_scene_action_search()
    assert window._action_search_dialog.query.parent_type == "SceneRoot"
    window._action_search_dialog.close()

    window._timeline_add_track("Event")
    track = window.session.document.state_graph.find_state(
        window.session.document.state_graph.initial_state_id
    ).tracks[0]
    window.timeline.selected_track_id = track.id
    window._open_action_search("timeline")
    dialog = window._action_search_dialog
    clip_matches = [
        match.descriptor
        for match in dialog._matches
        if match.descriptor.command_id == "add_timeline_clip"
    ]
    assert [item.payload["kind"] for item in clip_matches] == ["Event"]
    dialog.close()
    window.session.revert()
    window.close()
