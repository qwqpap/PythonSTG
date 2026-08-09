"""N1 contract: Scene v3 owns one recursive, versioned StateGraphSpec."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor import (
    CURRENT_SCHEMA_VERSION,
    MAX_STATE_GRAPH_DEPTH,
    DocumentError,
    SceneDocument,
    SceneEditorSession,
    StateActionSpec,
    StateGraphSpec,
    StateSpec,
    TimelineClip,
    TimelineTrack,
    TransitionSpec,
)


REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURES = REPOSITORY / "docs" / "schemas" / "fixtures"
SCHEMA = REPOSITORY / "docs" / "schemas" / "pystg-scene-v3.schema.json"


def _uuid() -> str:
    return str(uuid.uuid4())


def _event_action(event_type: str) -> StateActionSpec:
    return StateActionSpec(
        name=event_type,
        kind="Event",
        channel="state",
        payload={"event_type": event_type, "data": {}},
    )


def _state(name: str, *, duration: int = 60) -> StateSpec:
    return StateSpec(name=name, duration_frames=duration)


def test_scene_v2_fixture_migrates_losslessly_to_canonical_v3_fixture():
    source = json.loads(
        (FIXTURES / "scene-v2.pystg.json").read_text(encoding="utf-8")
    )
    expected = json.loads(
        (FIXTURES / "scene-v3.pystg.json").read_text(encoding="utf-8")
    )

    first = SceneDocument.from_dict(source)
    second = SceneDocument.from_dict(source)

    assert first.schema_version == CURRENT_SCHEMA_VERSION == 3
    assert first.to_dict() == second.to_dict() == expected
    assert "tracks" not in first.to_dict()
    assert first.tracks is first.state_graph.initial_state.tracks
    assert first.tracks[0].to_dict() == source["tracks"][0]
    assert first.tracks[0].id == source["tracks"][0]["id"]
    assert first.tracks[0].clips[0].id == source["tracks"][0]["clips"][0]["id"]


def test_scene_v3_fixture_matches_schema_and_round_trips_through_store(tmp_path):
    payload = json.loads(
        (FIXTURES / "scene-v3.pystg.json").read_text(encoding="utf-8")
    )
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

    store = ResourceStore(ProjectContext(tmp_path))
    document = store.registry.load(payload)
    saved = store.save(document, "game_content/scenes/state_graph.pystg.json")
    reopened = store.load(saved)

    assert reopened.to_dict() == payload
    assert reopened.state_graph.initial_state.id == payload["state_graph"][
        "initial_state_id"
    ]


def test_state_graph_round_trip_preserves_nested_timeline_actions_and_ids():
    scene = SceneEditorSession.new_document("Nested Stage")
    intro = _state("Intro", duration=120)
    intro.entry_actions.append(_event_action("intro.entered"))
    intro.exit_actions.append(_event_action("intro.exited"))
    intro.tracks.append(
        TimelineTrack(
            name="Cues",
            kind="Event",
            channel="stage",
            clips=[
                TimelineClip(
                    name="Cue",
                    kind="Event",
                    start_frame=30,
                    duration_frames=1,
                    channel="stage",
                    payload={"event_type": "intro.cue", "data": {"value": 7}},
                )
            ],
        )
    )
    phase_a = _state("Phase A", duration=90)
    phase_b = _state("Phase B", duration=90)
    phase_a.transitions.append(
        TransitionSpec(
            name="Next phase",
            target_state_id=phase_b.id,
            trigger="after",
            after_frames=90,
        )
    )
    boss = _state("Boss", duration=0)
    boss.child_graph = StateGraphSpec(
        name="PhaseFlow",
        initial_state_id=phase_a.id,
        states=[phase_a, phase_b],
    )
    intro.transitions.append(
        TransitionSpec(
            name="Start boss",
            target_state_id=boss.id,
            trigger="after",
            after_frames=120,
        )
    )
    scene.state_graph = StateGraphSpec(
        name="StageFlow",
        initial_state_id=intro.id,
        states=[intro, boss],
    )

    payload = scene.to_dict()
    reopened = SceneDocument.from_dict(payload)

    assert reopened.to_dict() == payload
    reopened_intro = reopened.state_graph.find_state(intro.id)
    reopened_phase_a = reopened.state_graph.find_state(phase_a.id)
    assert reopened_phase_a.id == phase_a.id
    assert reopened_phase_a.name == "Phase A"
    assert reopened_intro.tracks[0].id == intro.tracks[0].id
    assert reopened_intro.tracks[0].clips[0].id == intro.tracks[0].clips[0].id
    ids = [item.id for item in reopened.state_graph.walk_objects()]
    assert len(ids) == len(set(ids))


def test_state_graph_rejects_invalid_initial_cross_level_transition_and_duplicate_id():
    scene = SceneEditorSession.new_document("Invalid Graph")
    first = _state("First")
    second = _state("Second")
    child = _state("Child")
    second.child_graph = StateGraphSpec(
        name="PhaseFlow",
        initial_state_id=child.id,
        states=[child],
    )
    scene.state_graph = StateGraphSpec(
        name="StageFlow",
        initial_state_id=_uuid(),
        states=[first, second],
    )
    with pytest.raises(DocumentError, match="initial_state_id"):
        scene.validate()

    scene.state_graph.initial_state_id = first.id
    first.transitions.append(
        TransitionSpec(
            name="Illegal cross-level edge",
            target_state_id=child.id,
            trigger="after",
            after_frames=1,
        )
    )
    with pytest.raises(DocumentError, match="same graph|sibling"):
        scene.validate()

    first.transitions.clear()
    child.id = first.id
    second.child_graph.initial_state_id = child.id
    with pytest.raises(DocumentError, match="Duplicate document object id"):
        scene.validate()


def test_transition_trigger_contract_and_finite_depth_are_validated():
    scene = SceneEditorSession.new_document("Transition Contract")
    first = _state("First")
    second = _state("Second")
    scene.state_graph = StateGraphSpec(
        name="StageFlow",
        initial_state_id=first.id,
        states=[first, second],
    )
    first.transitions.append(
        TransitionSpec(
            name="Bad delay",
            target_state_id=second.id,
            trigger="after",
            after_frames=0,
        )
    )
    with pytest.raises(DocumentError, match="after_frames"):
        scene.validate()

    first.transitions[0] = TransitionSpec(
        name="Bad complete payload",
        target_state_id=second.id,
        trigger="complete",
        after_frames=1,
    )
    with pytest.raises(DocumentError, match="after_frames"):
        scene.validate()

    root = _state("Depth 0")
    scene.state_graph = StateGraphSpec(
        name="StageFlow",
        initial_state_id=root.id,
        states=[root],
    )
    cursor = root
    for depth in range(MAX_STATE_GRAPH_DEPTH):
        child = _state(f"Depth {depth + 1}")
        cursor.child_graph = StateGraphSpec(
            name="PhaseFlow",
            initial_state_id=child.id,
            states=[child],
        )
        cursor = child
    with pytest.raises(DocumentError, match="depth"):
        scene.validate()


def test_unknown_future_scene_version_is_rejected_without_mutating_payload():
    payload = json.loads(
        (FIXTURES / "scene-v3.pystg.json").read_text(encoding="utf-8")
    )
    future = deepcopy(payload)
    future["schema_version"] = CURRENT_SCHEMA_VERSION + 1
    before = deepcopy(future)

    with pytest.raises(DocumentError, match="newer"):
        SceneDocument.from_dict(future)

    assert future == before
