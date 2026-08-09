"""N2.0 structural contract for typed variable declarations."""

from __future__ import annotations

import copy
import json

import pytest

from src.authoring.variables import (
    DEFAULT_VARIABLE_TYPES,
    VariableError,
    VariableOutputMapping,
    VariableRef,
    VariableSpec,
    VariableTypeError,
)
from src.editor import SceneEditorSession, SceneDocument


def test_builtin_types_and_complex_use_explicit_json_values() -> None:
    values = {
        "bool": True,
        "int": 4,
        "float": 1.5,
        "string": "hello",
        "vector2": {"x": 1.0, "y": -2.0},
        "color": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0},
        "resource": "res://game_content/patterns/a.pystg.json",
        "complex": {"real": 0.2, "imag": -0.5},
    }
    for type_id, value in values.items():
        spec = VariableSpec(f"value_{type_id}", type_id, value)
        round_trip = VariableSpec.from_dict(json.loads(json.dumps(spec.to_dict())))
        assert round_trip.to_dict() == spec.to_dict()

    with pytest.raises(VariableTypeError):
        VariableSpec("bad", "complex", 1 + 2j).validate()


def test_variable_ref_and_output_mapping_are_typed_and_portable() -> None:
    mapping = VariableOutputMapping(
        source=VariableRef("emitter.generated", scope="behavior", type="int"),
        target=VariableRef("state.generated", scope="state", type="int"),
        operation="set",
    )
    restored = VariableOutputMapping.from_dict(json.loads(json.dumps(mapping.to_dict())))
    assert restored.to_dict() == mapping.to_dict()

    with pytest.raises(VariableError):
        VariableRef("not a path").validate()


def test_scene_declarations_round_trip_without_runtime_values() -> None:
    scene = SceneEditorSession.new_document("Variables")
    scene.variables.append(
        VariableSpec(
            "difficulty.rank",
            "float",
            1.0,
            scope="stage",
            writable_by=("safe_action",),
        )
    )
    state = scene.state_graph.initial_state
    state.variables.append(
        VariableSpec(
            "phase.enrage",
            "bool",
            False,
            scope="state",
            writable_by=("timeline",),
            animatable=True,
        )
    )
    payload = json.loads(json.dumps(scene.to_dict()))
    restored = SceneDocument.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.variables[0].name == "difficulty.rank"
    assert restored.state_graph.initial_state.variables[0].scope == "state"


def test_registry_keeps_json_only_defaults() -> None:
    assert set(DEFAULT_VARIABLE_TYPES) >= {
        "bool", "int", "float", "string", "vector2", "color", "resource", "complex"
    }
    with pytest.raises(VariableTypeError):
        DEFAULT_VARIABLE_TYPES.normalize("vector2", {"x": 1.0})


def test_registry_custom_type_uses_its_declared_normalizer() -> None:
    from src.authoring.variables import VariableTypeRegistry

    registry = VariableTypeRegistry()
    registry.register(
        "percent",
        display_name="Percent",
        json_shape="number",
        normalizer=lambda value, path: round(float(value), 2),
    )

    assert registry.get("percent").normalize(0.126) == 0.13
    assert registry.normalize("percent", 0.126) == 0.13


def test_scene_v3_to_v4_migration_adds_empty_declarations_without_touching_tracks() -> None:
    source = {
        "schema_version": 3,
        "type": "pystg.scene",
        "id": "b88e1d39-dc9d-4fc9-8fb7-9023b17dba30",
        "name": "Legacy",
        "metadata": {"duration_frames": 4},
        "root": {
            "id": "f330ee96-e0b4-45f4-a0a6-0ba7c90131ef",
            "type": "SceneRoot",
            "name": "Legacy",
            "properties": {},
            "children": [],
        },
        "state_graph": {
            "id": "e0f36a27-e0c4-5a99-b044-ad01a3ebfceb",
            "name": "StageFlow",
            "initial_state_id": "d71b4d73-9ecd-5707-a48b-2cbc0c9ca03e",
            "states": [{
                "id": "d71b4d73-9ecd-5707-a48b-2cbc0c9ca03e",
                "name": "Default",
                "order": 0,
                "duration_frames": 4,
                "entry_actions": [],
                "exit_actions": [],
                "tracks": [],
                "transitions": [],
                "child_graph": None,
            }],
        },
    }
    document = SceneDocument.from_dict(source)
    assert document.schema_version == 4
    assert document.variables == []
    assert document.state_graph.initial_state.variables == []
    assert document.metadata["variable_compatibility"] == "legacy_last_wins"
    assert document.state_graph.initial_state.duration_frames == 4
