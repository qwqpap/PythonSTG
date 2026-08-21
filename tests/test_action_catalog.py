"""N6 action-catalog contract: typed candidates, stable filtering and dispatch."""

from dataclasses import dataclass

import pytest

from src.editor.action_catalog import (
    ActionCatalog,
    ActionCatalogError,
    ActionDescriptor,
    ActionExecutor,
    ActionQuery,
    build_editor_action_catalog,
)
from src.authoring.commands.base import CommandStack
from src.authoring.scene.node_types import build_default_node_type_registry
from src.pattern.graph import NODE_TYPES, PORT_TYPES


def _descriptor(action_id: str, title: str, **values) -> ActionDescriptor:
    return ActionDescriptor(
        id=action_id,
        title=title,
        contexts=values.pop("contexts", ("graph",)),
        command_id=values.pop("command_id", "create"),
        **values,
    )


def test_catalog_rejects_duplicate_ids_with_a_stable_diagnostic_path():
    first = _descriptor("action.test.one", "One")
    with pytest.raises(ActionCatalogError) as error:
        ActionCatalog((first, first))

    assert error.value.path == "actions['action.test.one'].id"
    assert "duplicates" in error.value.message


def test_results_are_deterministic_and_explain_source_and_context():
    catalog = ActionCatalog(
        (
            _descriptor("action.zulu", "same", source="plugin"),
            _descriptor("action.alpha", "Same", source="builtin"),
            _descriptor("action.beta", "Beta", source="project"),
        )
    )

    matches = catalog.search(ActionQuery(context="graph"))

    assert [match.descriptor.id for match in matches] == [
        "action.beta",
        "action.alpha",
        "action.zulu",
    ]
    assert "source=project" in matches[0].reason
    assert "context=graph" in matches[0].reason


def test_graph_candidates_come_from_formal_node_and_port_descriptors():
    catalog = build_editor_action_catalog()
    actions = {
        (match.descriptor.payload["category"], match.descriptor.payload["node_type"]):
        match.descriptor
        for match in catalog.search(ActionQuery(context="graph"))
        if match.descriptor.command_id == "add_graph_node"
    }

    assert set(actions) == {
        (category, node_type)
        for category, node_types in NODE_TYPES.items()
        for node_type in node_types
    }
    for (category, _node_type), descriptor in actions.items():
        input_type, output_type = PORT_TYPES[category]
        assert descriptor.input_types == (() if input_type is None else (input_type,))
        assert descriptor.output_type == output_type


def test_dragged_geometry_port_only_returns_nodes_accepting_geometry():
    catalog = build_editor_action_catalog()

    matches = catalog.search(ActionQuery(context="graph", input_type="geometry"))

    assert matches
    assert {match.descriptor.payload["category"] for match in matches} == {"aim"}
    assert all("geometry" in match.descriptor.input_types for match in matches)


def test_contexts_and_scene_parent_constraints_remove_invalid_candidates():
    catalog = build_editor_action_catalog(
        node_registry=build_default_node_type_registry()
    )

    timeline = catalog.search(ActionQuery(context="timeline"))
    assert timeline
    assert {match.descriptor.command_id for match in timeline} == {
        "add_timeline_track",
        "add_timeline_clip",
    }

    scene = catalog.search(ActionQuery(context="scene", parent_type="Boss"))
    node_types = {match.descriptor.payload["node_type"] for match in scene}
    assert "Spell" in node_types
    assert "Stage" not in node_types
    assert "SceneRoot" not in node_types


def test_phrase_search_is_literal_and_has_no_natural_language_generator():
    catalog = build_editor_action_catalog()

    assert catalog.search(
        ActionQuery(context="graph", text="每 0.1 秒发射 32 发圆形弹幕")
    ) == ()


@dataclass
class _AppendCommand:
    target: list[str]
    value: str
    label: str = "append"

    def execute(self) -> None:
        self.target.append(self.value)

    def undo(self) -> None:
        assert self.target.pop() == self.value


def test_executor_drives_a_real_command_stack_and_reports_missing_handler_path():
    created: list[str] = []
    stack = CommandStack()
    descriptor = _descriptor("action.test.create", "Create")
    executor = ActionExecutor()
    executor.register(
        "create", lambda action: stack.push(_AppendCommand(created, action.id))
    )

    executor.execute(descriptor)
    assert created == [descriptor.id]
    assert stack.undo()
    assert created == []

    missing = _descriptor(
        "action.test.missing", "Missing", command_id="not_registered"
    )
    with pytest.raises(ActionCatalogError) as error:
        executor.execute(missing)
    assert error.value.path == "actions['action.test.missing'].command_id"
