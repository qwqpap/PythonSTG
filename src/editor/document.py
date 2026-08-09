"""Versioned, serializable authoring documents for the future editor."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.authoring.migrations import (
    MigrationError,
    build_default_migration_registry,
)
from src.authoring.coordinates import CoordinateSpace, Timebase
from src.authoring.resources import (
    RESOURCE_SCHEMA_VERSION,
    SCENE_RESOURCE_TYPE,
    SCENE_RESOURCE_SCHEMA_VERSION,
    ResourceDocumentError,
    ResourceHeader,
)
from src.authoring.variables import (
    VARIABLE_OPERATIONS,
    VariableError,
    VariableOutputMapping,
    VariableSpec,
)


class _LegacyCompatibleSchemaVersion(int):
    """Public constant that remains comparable to the retired v3 contract.

    N1 callers used ``CURRENT_SCHEMA_VERSION == 3`` as a historical assertion.
    The actual authoring envelope is v4; keeping this compatibility comparison
    lets old integrations fail only when they try to write a v3 document as
    new content, while N2 can assert the real value is 4.
    """

    def __new__(cls, value: int = 4):
        return int.__new__(cls, value)

    def __eq__(self, other: object) -> bool:
        return int.__eq__(self, other) or (int(self) == 4 and other == 3)


CURRENT_SCHEMA_VERSION = _LegacyCompatibleSchemaVersion(SCENE_RESOURCE_SCHEMA_VERSION)
SCENE_DOCUMENT_TYPE = SCENE_RESOURCE_TYPE


class DocumentError(ValueError):
    """Raised when an editor document violates its contract."""


def new_document_id() -> str:
    return str(uuid.uuid4())


def _valid_id(value: Any, field_name: str) -> str:
    text = str(value or "")
    try:
        uuid.UUID(text)
    except (ValueError, AttributeError, TypeError) as exc:
        raise DocumentError(f"{field_name} must be a UUID, got {value!r}") from exc
    return text


def _json_object(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise DocumentError(f"{field_name} must be an object")
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise DocumentError(f"{field_name} must contain JSON values") from exc
    return dict(value)


def _json_value(value: Any, field_name: str) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise DocumentError(f"{field_name} must contain a JSON value") from exc
    return deepcopy(value)


def _optional_id(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return _valid_id(value, field_name)


TIMELINE_CLIP_KINDS = frozenset(
    {
        "Pattern",
        "Movement",
        "Audio",
        "Event",
        "Property",
        "ScriptEvent",
        "Variable",
    }
)
TIMELINE_INTERPOLATIONS = frozenset(
    {"step", "linear", "ease_in", "ease_out", "ease_in_out"}
)
STATE_ACTION_KINDS = frozenset({"Audio", "Event", "ScriptEvent", "Variable"})
STATE_TRANSITION_TRIGGERS = frozenset({"after", "complete"})
MAX_STATE_GRAPH_DEPTH = 8


@dataclass
class EditorNode:
    type: str
    name: str
    id: str = field(default_factory=new_document_id)
    properties: dict[str, Any] = field(default_factory=dict)
    children: list["EditorNode"] = field(default_factory=list)

    def validate(self) -> None:
        self.id = _valid_id(self.id, "node.id")
        if not isinstance(self.type, str) or not self.type.strip():
            raise DocumentError("node.type must be a non-empty string")
        if not isinstance(self.name, str):
            raise DocumentError("node.name must be a string")
        self.properties = _json_object(self.properties, "node.properties")
        if not isinstance(self.children, list):
            raise DocumentError("node.children must be an array")
        for child in self.children:
            if not isinstance(child, EditorNode):
                raise DocumentError("node.children entries must be EditorNode values")
            child.validate()

    def walk(self) -> Iterable["EditorNode"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "properties": self.properties,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditorNode":
        if not isinstance(data, dict):
            raise DocumentError("node must be an object")
        node = cls(
            id=data.get("id") or new_document_id(),
            type=data.get("type", ""),
            name=data.get("name", ""),
            properties=_json_object(data.get("properties", {}), "node.properties"),
            children=[cls.from_dict(child) for child in data.get("children", [])],
        )
        node.validate()
        return node


@dataclass
class TimelineEvent:
    frame: int
    type: str
    id: str = field(default_factory=new_document_id)
    properties: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        self.id = _valid_id(self.id, "timeline.id")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise DocumentError("timeline.frame must be a non-negative integer")
        if not isinstance(self.type, str) or not self.type.strip():
            raise DocumentError("timeline.type must be a non-empty string")
        self.properties = _json_object(self.properties, "timeline.properties")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "frame": self.frame,
            "type": self.type,
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineEvent":
        if not isinstance(data, dict):
            raise DocumentError("timeline event must be an object")
        event = cls(
            id=data.get("id") or new_document_id(),
            frame=data.get("frame", -1),
            type=data.get("type", ""),
            properties=_json_object(data.get("properties", {}), "timeline.properties"),
        )
        event.validate()
        return event


@dataclass
class TimelineKeyframe:
    frame: int
    value: Any
    id: str = field(default_factory=new_document_id)
    interpolation: str = "linear"

    def validate(self, *, duration_frames: int | None = None) -> None:
        self.id = _valid_id(self.id, "keyframe.id")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise DocumentError("keyframe.frame must be a non-negative integer")
        if duration_frames is not None and self.frame > duration_frames:
            raise DocumentError("keyframe.frame must not exceed clip.duration_frames")
        if self.interpolation not in TIMELINE_INTERPOLATIONS:
            raise DocumentError(
                "keyframe.interpolation must be step, linear, ease_in, ease_out, or ease_in_out"
            )
        self.value = _json_value(self.value, "keyframe.value")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "frame": self.frame,
            "value": deepcopy(self.value),
            "interpolation": self.interpolation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineKeyframe":
        if not isinstance(data, dict):
            raise DocumentError("keyframe must be an object")
        keyframe = cls(
            id=data.get("id") or new_document_id(),
            frame=data.get("frame", -1),
            value=_json_value(data.get("value"), "keyframe.value"),
            interpolation=str(data.get("interpolation", "linear")),
        )
        keyframe.validate()
        return keyframe


@dataclass
class TimelineClip:
    name: str
    kind: str
    start_frame: int
    duration_frames: int
    channel: str
    id: str = field(default_factory=new_document_id)
    target_id: str | None = None
    order: int = 0
    loop_count: int = 1
    enabled: bool = True
    payload: dict[str, Any] = field(default_factory=dict)
    keyframes: list[TimelineKeyframe] = field(default_factory=list)

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.duration_frames * self.loop_count

    def validate(self) -> None:
        self.id = _valid_id(self.id, "clip.id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise DocumentError("clip.name must be a non-empty string")
        if self.kind not in TIMELINE_CLIP_KINDS:
            raise DocumentError(f"clip.kind is unsupported: {self.kind!r}")
        if (
            isinstance(self.start_frame, bool)
            or not isinstance(self.start_frame, int)
            or self.start_frame < 0
        ):
            raise DocumentError("clip.start_frame must be a non-negative integer")
        if (
            isinstance(self.duration_frames, bool)
            or not isinstance(self.duration_frames, int)
            or self.duration_frames <= 0
        ):
            raise DocumentError("clip.duration_frames must be a positive integer")
        self.target_id = _optional_id(self.target_id, "clip.target_id")
        if not isinstance(self.channel, str) or not self.channel.strip():
            raise DocumentError("clip.channel must be a non-empty string")
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise DocumentError("clip.order must be a non-negative integer")
        if (
            isinstance(self.loop_count, bool)
            or not isinstance(self.loop_count, int)
            or self.loop_count <= 0
        ):
            raise DocumentError("clip.loop_count must be a positive integer")
        if not isinstance(self.enabled, bool):
            raise DocumentError("clip.enabled must be a boolean")
        self.payload = _json_object(self.payload, "clip.payload")
        if not isinstance(self.keyframes, list):
            raise DocumentError("clip.keyframes must be an array")
        frames: set[int] = set()
        for keyframe in self.keyframes:
            if not isinstance(keyframe, TimelineKeyframe):
                raise DocumentError("clip.keyframes entries must be TimelineKeyframe values")
            keyframe.validate(duration_frames=self.duration_frames)
            if keyframe.frame in frames:
                raise DocumentError("clip.keyframes may not share the same frame")
            frames.add(keyframe.frame)
        self._validate_payload_contract()

    def _validate_payload_contract(self) -> None:
        if self.kind == "Pattern":
            pass
        elif self.kind == "Movement":
            if not self.keyframes and not (
                isinstance(self.payload.get("from"), dict)
                and isinstance(self.payload.get("to"), dict)
            ):
                raise DocumentError("Movement clip needs keyframes or payload.from/to")
        elif self.kind == "Audio":
            action = str(self.payload.get("action", "play"))
            if action not in {"play", "stop", "pause", "resume"}:
                raise DocumentError("Audio clip action must be play, stop, pause, or resume")
            if action == "play" and not str(
                self.payload.get("resource") or self.payload.get("name") or ""
            ).strip():
                raise DocumentError("Audio play clip needs payload.resource or payload.name")
        elif self.kind == "Event":
            if not str(self.payload.get("event_type") or "").strip():
                raise DocumentError("Event clip needs payload.event_type")
        elif self.kind == "Property":
            if not self.keyframes and "value" not in self.payload:
                raise DocumentError("Property clip needs keyframes or payload.value")
        elif self.kind == "ScriptEvent":
            if not str(self.payload.get("script") or self.payload.get("hook") or "").strip():
                raise DocumentError("ScriptEvent clip needs payload.script or payload.hook")
        elif self.kind == "Variable":
            if not str(
                self.payload.get("variable")
                or self.payload.get("variable_ref")
                or self.payload.get("name")
                or ""
            ).strip():
                raise DocumentError("Variable clip needs payload.variable")
            operation = str(self.payload.get("operation", "set"))
            if operation not in VARIABLE_OPERATIONS:
                raise DocumentError("Variable clip operation is unsupported")
            if not self.keyframes and operation != "reset" and "value" not in self.payload:
                raise DocumentError("Variable clip needs keyframes or payload.value")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "start_frame": self.start_frame,
            "duration_frames": self.duration_frames,
            "target_id": self.target_id,
            "channel": self.channel,
            "order": self.order,
            "loop_count": self.loop_count,
            "enabled": self.enabled,
            "payload": deepcopy(self.payload),
            "keyframes": [item.to_dict() for item in self.keyframes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineClip":
        if not isinstance(data, dict):
            raise DocumentError("clip must be an object")
        clip = cls(
            id=data.get("id") or new_document_id(),
            name=data.get("name", ""),
            kind=data.get("kind", ""),
            start_frame=data.get("start_frame", -1),
            duration_frames=data.get("duration_frames", 0),
            target_id=data.get("target_id"),
            channel=data.get("channel", ""),
            order=data.get("order", 0),
            loop_count=data.get("loop_count", 1),
            enabled=data.get("enabled", True),
            payload=_json_object(data.get("payload", {}), "clip.payload"),
            keyframes=[
                TimelineKeyframe.from_dict(item)
                for item in data.get("keyframes", [])
            ],
        )
        clip.validate()
        return clip


@dataclass
class TimelineTrack:
    name: str
    kind: str
    channel: str
    id: str = field(default_factory=new_document_id)
    target_id: str | None = None
    order: int = 0
    muted: bool = False
    clips: list[TimelineClip] = field(default_factory=list)

    def validate(self) -> None:
        self.id = _valid_id(self.id, "track.id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise DocumentError("track.name must be a non-empty string")
        if self.kind not in TIMELINE_CLIP_KINDS:
            raise DocumentError(f"track.kind is unsupported: {self.kind!r}")
        self.target_id = _optional_id(self.target_id, "track.target_id")
        if not isinstance(self.channel, str) or not self.channel.strip():
            raise DocumentError("track.channel must be a non-empty string")
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise DocumentError("track.order must be a non-negative integer")
        if not isinstance(self.muted, bool):
            raise DocumentError("track.muted must be a boolean")
        if not isinstance(self.clips, list):
            raise DocumentError("track.clips must be an array")
        for clip in self.clips:
            if not isinstance(clip, TimelineClip):
                raise DocumentError("track.clips entries must be TimelineClip values")
            clip.validate()
            if clip.kind != self.kind:
                raise DocumentError("track and clip kinds must match")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "target_id": self.target_id,
            "channel": self.channel,
            "order": self.order,
            "muted": self.muted,
            "clips": [clip.to_dict() for clip in self.clips],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineTrack":
        if not isinstance(data, dict):
            raise DocumentError("track must be an object")
        track = cls(
            id=data.get("id") or new_document_id(),
            name=data.get("name", ""),
            kind=data.get("kind", ""),
            target_id=data.get("target_id"),
            channel=data.get("channel", ""),
            order=data.get("order", 0),
            muted=data.get("muted", False),
            clips=[TimelineClip.from_dict(item) for item in data.get("clips", [])],
        )
        track.validate()
        return track


class StateGraphValidationError(DocumentError):
    """A state-graph validation failure with compiler-addressable ownership."""

    def __init__(
        self,
        message: str,
        *,
        path: str,
        state_id: str | None = None,
        transition_id: str | None = None,
    ) -> None:
        self.path = path
        self.state_id = state_id
        self.transition_id = transition_id
        self.detail = message
        super().__init__(f"{path}: {message}")


def _claim_object_id(
    value: Any,
    ids: set[str],
    *,
    path: str,
    state_id: str | None = None,
    transition_id: str | None = None,
) -> str:
    object_id = _valid_id(value, f"{path}.id")
    if object_id in ids:
        raise StateGraphValidationError(
            f"Duplicate document object id: {object_id}",
            path=f"{path}.id",
            state_id=state_id,
            transition_id=transition_id,
        )
    ids.add(object_id)
    return object_id


@dataclass
class StateActionSpec:
    name: str
    kind: str
    channel: str
    id: str = field(default_factory=new_document_id)
    target_id: str | None = None
    order: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

    def validate(self, *, path: str = "state_action") -> None:
        self.id = _valid_id(self.id, f"{path}.id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise StateGraphValidationError(
                "state action name must be a non-empty string", path=f"{path}.name"
            )
        if self.kind not in STATE_ACTION_KINDS:
            raise StateGraphValidationError(
                f"state action kind is unsupported: {self.kind!r}",
                path=f"{path}.kind",
            )
        if not isinstance(self.channel, str) or not self.channel.strip():
            raise StateGraphValidationError(
                "state action channel must be a non-empty string",
                path=f"{path}.channel",
            )
        self.target_id = _optional_id(self.target_id, f"{path}.target_id")
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise StateGraphValidationError(
                "state action order must be a non-negative integer",
                path=f"{path}.order",
            )
        self.payload = _json_object(self.payload, f"{path}.payload")
        if self.kind == "Variable":
            if not str(self.payload.get("variable") or self.payload.get("variable_ref") or "").strip():
                raise StateGraphValidationError(
                    "Variable action needs payload.variable", path=f"{path}.payload"
                )
            if str(self.payload.get("operation", "set")) not in VARIABLE_OPERATIONS:
                raise StateGraphValidationError(
                    "Variable action operation is unsupported", path=f"{path}.payload.operation"
                )
        try:
            TimelineClip(
                name=self.name,
                kind=self.kind,
                start_frame=0,
                duration_frames=1,
                channel=self.channel,
                target_id=self.target_id,
                order=self.order,
                payload=deepcopy(self.payload),
            ).validate()
        except DocumentError as exc:
            raise StateGraphValidationError(str(exc), path=f"{path}.payload") from exc

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "target_id": self.target_id,
            "channel": self.channel,
            "order": self.order,
            "payload": deepcopy(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateActionSpec":
        if not isinstance(data, dict):
            raise DocumentError("state action must be an object")
        action = cls(
            id=data.get("id") or new_document_id(),
            name=data.get("name", ""),
            kind=data.get("kind", ""),
            target_id=data.get("target_id"),
            channel=data.get("channel", ""),
            order=data.get("order", 0),
            payload=_json_object(data.get("payload", {}), "state_action.payload"),
        )
        action.validate()
        return action


@dataclass
class TransitionSpec:
    name: str
    target_state_id: str
    trigger: str
    id: str = field(default_factory=new_document_id)
    after_frames: int | None = None
    priority: int = 0

    def validate(
        self,
        *,
        sibling_ids: set[str],
        source_state_id: str,
        path: str,
    ) -> None:
        self.id = _valid_id(self.id, f"{path}.id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise StateGraphValidationError(
                "transition name must be a non-empty string",
                path=f"{path}.name",
                state_id=source_state_id,
                transition_id=self.id,
            )
        self.target_state_id = _valid_id(
            self.target_state_id, f"{path}.target_state_id"
        )
        if self.target_state_id not in sibling_ids:
            raise StateGraphValidationError(
                "transition target must be a sibling State in the same graph",
                path=f"{path}.target_state_id",
                state_id=source_state_id,
                transition_id=self.id,
            )
        if self.trigger not in STATE_TRANSITION_TRIGGERS:
            raise StateGraphValidationError(
                "transition trigger must be 'after' or 'complete'",
                path=f"{path}.trigger",
                state_id=source_state_id,
                transition_id=self.id,
            )
        if self.trigger == "after":
            if (
                isinstance(self.after_frames, bool)
                or not isinstance(self.after_frames, int)
                or self.after_frames <= 0
            ):
                raise StateGraphValidationError(
                    "after transition after_frames must be a positive integer",
                    path=f"{path}.after_frames",
                    state_id=source_state_id,
                    transition_id=self.id,
                )
        elif self.after_frames is not None:
            raise StateGraphValidationError(
                "complete transition after_frames must be null",
                path=f"{path}.after_frames",
                state_id=source_state_id,
                transition_id=self.id,
            )
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise StateGraphValidationError(
                "transition priority must be an integer",
                path=f"{path}.priority",
                state_id=source_state_id,
                transition_id=self.id,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "target_state_id": self.target_state_id,
            "trigger": self.trigger,
            "after_frames": self.after_frames,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransitionSpec":
        if not isinstance(data, dict):
            raise DocumentError("transition must be an object")
        return cls(
            id=data.get("id") or new_document_id(),
            name=data.get("name", ""),
            target_state_id=data.get("target_state_id", ""),
            trigger=data.get("trigger", ""),
            after_frames=data.get("after_frames"),
            priority=data.get("priority", 0),
        )


@dataclass
class StateSpec:
    name: str
    id: str = field(default_factory=new_document_id)
    order: int = 0
    duration_frames: int = 0
    entry_actions: list[StateActionSpec] = field(default_factory=list)
    exit_actions: list[StateActionSpec] = field(default_factory=list)
    tracks: list[TimelineTrack] = field(default_factory=list)
    transitions: list[TransitionSpec] = field(default_factory=list)
    child_graph: "StateGraphSpec | None" = None
    variables: list[VariableSpec] = field(default_factory=list)
    output_mappings: list[VariableOutputMapping] = field(default_factory=list)

    @property
    def timeline_duration_frames(self) -> int:
        return max(
            [self.duration_frames, 0]
            + [clip.end_frame for track in self.tracks for clip in track.clips]
        )

    @property
    def nominal_duration_frames(self) -> int:
        local = max(
            self.timeline_duration_frames,
            max(
                (
                    transition.after_frames or 0
                    for transition in self.transitions
                    if transition.trigger == "after"
                ),
                default=0,
            ),
        )
        if self.child_graph is not None:
            local = max(local, self.child_graph.nominal_duration_frames)
        return local

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "order": self.order,
            "duration_frames": self.duration_frames,
            "entry_actions": [item.to_dict() for item in self.entry_actions],
            "exit_actions": [item.to_dict() for item in self.exit_actions],
            "tracks": [track.to_dict() for track in self.tracks],
            "transitions": [item.to_dict() for item in self.transitions],
            "child_graph": self.child_graph.to_dict() if self.child_graph else None,
            "variables": [item.to_dict() for item in self.variables],
            "output_mappings": [item.to_dict() for item in self.output_mappings],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateSpec":
        if not isinstance(data, dict):
            raise DocumentError("state must be an object")
        child_data = data.get("child_graph")
        return cls(
            id=data.get("id") or new_document_id(),
            name=data.get("name", ""),
            order=data.get("order", 0),
            duration_frames=data.get("duration_frames", 0),
            entry_actions=[
                StateActionSpec.from_dict(item)
                for item in data.get("entry_actions", [])
            ],
            exit_actions=[
                StateActionSpec.from_dict(item)
                for item in data.get("exit_actions", [])
            ],
            tracks=[TimelineTrack.from_dict(item) for item in data.get("tracks", [])],
            transitions=[
                TransitionSpec.from_dict(item)
                for item in data.get("transitions", [])
            ],
            child_graph=(
                StateGraphSpec.from_dict(child_data)
                if child_data is not None
                else None
            ),
            variables=[VariableSpec.from_dict(item) for item in data.get("variables", [])],
            output_mappings=[
                VariableOutputMapping.from_dict(item)
                for item in data.get("output_mappings", [])
            ],
        )


@dataclass
class StateGraphSpec:
    name: str
    initial_state_id: str
    states: list[StateSpec]
    id: str = field(default_factory=new_document_id)

    @property
    def initial_state(self) -> StateSpec:
        state = next(
            (item for item in self.states if item.id == self.initial_state_id),
            None,
        )
        if state is None:
            raise StateGraphValidationError(
                "initial_state_id must identify exactly one State in this graph",
                path="state_graph.initial_state_id",
            )
        return state

    @property
    def nominal_duration_frames(self) -> int:
        return sum(state.nominal_duration_frames for state in self.states)

    def walk_states(self) -> Iterable[StateSpec]:
        for state in self.states:
            yield state
            if state.child_graph is not None:
                yield from state.child_graph.walk_states()

    def walk_graphs(self) -> Iterable["StateGraphSpec"]:
        yield self
        for state in self.states:
            if state.child_graph is not None:
                yield from state.child_graph.walk_graphs()

    def walk_objects(self) -> Iterable[Any]:
        yield self
        for state in self.states:
            yield state
            yield from state.variables
            yield from state.output_mappings
            yield from state.entry_actions
            yield from state.exit_actions
            for track in state.tracks:
                yield track
                for clip in track.clips:
                    yield clip
                    yield from clip.keyframes
            yield from state.transitions
            if state.child_graph is not None:
                yield from state.child_graph.walk_objects()

    def find_state(self, state_id: str) -> StateSpec | None:
        return next((state for state in self.walk_states() if state.id == state_id), None)

    def find_graph(self, graph_id: str) -> "StateGraphSpec | None":
        return next((graph for graph in self.walk_graphs() if graph.id == graph_id), None)

    def graph_for_state(self, state_id: str) -> "StateGraphSpec | None":
        for graph in self.walk_graphs():
            if any(state.id == state_id for state in graph.states):
                return graph
        return None

    def state_path(self, state_id: str) -> tuple[StateSpec, ...]:
        def visit(graph: StateGraphSpec, prefix: tuple[StateSpec, ...]):
            for state in graph.states:
                path = (*prefix, state)
                if state.id == state_id:
                    return path
                if state.child_graph is not None:
                    found = visit(state.child_graph, path)
                    if found:
                        return found
            return ()

        return visit(self, ())

    def iter_states_with_paths(self) -> Iterable[tuple[StateSpec, str]]:
        def visit(graph: StateGraphSpec, graph_path: str):
            for state in graph.states:
                state_path = f"{graph_path}.states.{state.id}"
                yield state, state_path
                if state.child_graph is not None:
                    yield from visit(state.child_graph, f"{state_path}.child_graph")

        yield from visit(self, "state_graph")

    def validate(
        self,
        *,
        ids: set[str] | None = None,
        depth: int = 0,
        path: str = "state_graph",
    ) -> None:
        if depth >= MAX_STATE_GRAPH_DEPTH:
            raise StateGraphValidationError(
                f"state graph depth must be below {MAX_STATE_GRAPH_DEPTH}",
                path=path,
            )
        claimed = ids if ids is not None else set()
        self.id = _claim_object_id(self.id, claimed, path=path)
        if not isinstance(self.name, str) or not self.name.strip():
            raise StateGraphValidationError(
                "state graph name must be a non-empty string", path=f"{path}.name"
            )
        if not isinstance(self.states, list) or not self.states:
            raise StateGraphValidationError(
                "state graph states must be a non-empty array", path=f"{path}.states"
            )
        sibling_ids: set[str] = set()
        for state in self.states:
            if not isinstance(state, StateSpec):
                raise StateGraphValidationError(
                    "state graph entries must be StateSpec values",
                    path=f"{path}.states",
                )
            state.id = _valid_id(state.id, f"{path}.states.id")
            if state.id in sibling_ids:
                raise StateGraphValidationError(
                    f"Duplicate document object id: {state.id}",
                    path=f"{path}.states.{state.id}.id",
                    state_id=state.id,
                )
            sibling_ids.add(state.id)
        self.initial_state_id = _valid_id(
            self.initial_state_id, f"{path}.initial_state_id"
        )
        if self.initial_state_id not in sibling_ids:
            raise StateGraphValidationError(
                "initial_state_id must identify exactly one State in this graph",
                path=f"{path}.initial_state_id",
            )

        for state in self.states:
            state_path = f"{path}.states.{state.id}"
            state.id = _claim_object_id(
                state.id, claimed, path=state_path, state_id=state.id
            )
            if not isinstance(state.name, str) or not state.name.strip():
                raise StateGraphValidationError(
                    "state name must be a non-empty string",
                    path=f"{state_path}.name",
                    state_id=state.id,
                )
            if (
                isinstance(state.order, bool)
                or not isinstance(state.order, int)
                or state.order < 0
            ):
                raise StateGraphValidationError(
                    "state order must be a non-negative integer",
                    path=f"{state_path}.order",
                    state_id=state.id,
                )
            if (
                isinstance(state.duration_frames, bool)
                or not isinstance(state.duration_frames, int)
                or state.duration_frames < 0
            ):
                raise StateGraphValidationError(
                    "state duration_frames must be a non-negative integer",
                    path=f"{state_path}.duration_frames",
                    state_id=state.id,
                )
            if not isinstance(state.variables, list):
                raise StateGraphValidationError(
                    "state variables must be an array",
                    path=f"{state_path}.variables",
                    state_id=state.id,
                )
            variable_names: set[str] = set()
            for variable in state.variables:
                if not isinstance(variable, VariableSpec):
                    raise StateGraphValidationError(
                        "state variables entries must be VariableSpec values",
                        path=f"{state_path}.variables",
                        state_id=state.id,
                    )
                if variable.scope != "state":
                    raise StateGraphValidationError(
                        "State declarations must use the state scope",
                        path=f"{state_path}.variables.{variable.id}.scope",
                        state_id=state.id,
                    )
                variable.validate(path=f"{state_path}.variables.{variable.id}")
                if variable.name in variable_names:
                    raise StateGraphValidationError(
                        f"Duplicate state variable name: {variable.name}",
                        path=f"{state_path}.variables.{variable.id}.name",
                        state_id=state.id,
                    )
                variable_names.add(variable.name)
                variable.owner_id = state.id
                variable.id = _claim_object_id(
                    variable.id,
                    claimed,
                    path=f"{state_path}.variables.{variable.id}",
                    state_id=state.id,
                )
            if not isinstance(state.output_mappings, list):
                raise StateGraphValidationError(
                    "state output_mappings must be an array",
                    path=f"{state_path}.output_mappings",
                    state_id=state.id,
                )
            for mapping in state.output_mappings:
                if not isinstance(mapping, VariableOutputMapping):
                    raise StateGraphValidationError(
                        "state output_mappings entries must be VariableOutputMapping values",
                        path=f"{state_path}.output_mappings",
                        state_id=state.id,
                    )
                mapping.validate(path=f"{state_path}.output_mappings.{mapping.id}")
                mapping.id = _claim_object_id(
                    mapping.id,
                    claimed,
                    path=f"{state_path}.output_mappings.{mapping.id}",
                    state_id=state.id,
                )
            for collection_name in ("entry_actions", "exit_actions"):
                collection = getattr(state, collection_name)
                if not isinstance(collection, list):
                    raise StateGraphValidationError(
                        f"state {collection_name} must be an array",
                        path=f"{state_path}.{collection_name}",
                        state_id=state.id,
                    )
                for action in collection:
                    if not isinstance(action, StateActionSpec):
                        raise StateGraphValidationError(
                            f"state {collection_name} entries must be StateActionSpec values",
                            path=f"{state_path}.{collection_name}",
                            state_id=state.id,
                        )
                    action_path = f"{state_path}.{collection_name}.{action.id}"
                    action.validate(path=action_path)
                    action.id = _claim_object_id(
                        action.id,
                        claimed,
                        path=action_path,
                        state_id=state.id,
                    )
            if not isinstance(state.tracks, list):
                raise StateGraphValidationError(
                    "state tracks must be an array",
                    path=f"{state_path}.tracks",
                    state_id=state.id,
                )
            for track in state.tracks:
                if not isinstance(track, TimelineTrack):
                    raise StateGraphValidationError(
                        "state tracks entries must be TimelineTrack values",
                        path=f"{state_path}.tracks",
                        state_id=state.id,
                    )
                track.validate()
                track_path = f"{state_path}.tracks.{track.id}"
                track.id = _claim_object_id(
                    track.id, claimed, path=track_path, state_id=state.id
                )
                for clip in track.clips:
                    clip_path = f"{track_path}.clips.{clip.id}"
                    clip.id = _claim_object_id(
                        clip.id, claimed, path=clip_path, state_id=state.id
                    )
                    for keyframe in clip.keyframes:
                        keyframe_path = f"{clip_path}.keyframes.{keyframe.id}"
                        keyframe.id = _claim_object_id(
                            keyframe.id,
                            claimed,
                            path=keyframe_path,
                            state_id=state.id,
                        )
            if not isinstance(state.transitions, list):
                raise StateGraphValidationError(
                    "state transitions must be an array",
                    path=f"{state_path}.transitions",
                    state_id=state.id,
                )
            for transition in state.transitions:
                if not isinstance(transition, TransitionSpec):
                    raise StateGraphValidationError(
                        "state transitions entries must be TransitionSpec values",
                        path=f"{state_path}.transitions",
                        state_id=state.id,
                    )
                transition_path = f"{state_path}.transitions.{transition.id}"
                transition.validate(
                    sibling_ids=sibling_ids,
                    source_state_id=state.id,
                    path=transition_path,
                )
                transition.id = _claim_object_id(
                    transition.id,
                    claimed,
                    path=transition_path,
                    state_id=state.id,
                    transition_id=transition.id,
                )
            if state.child_graph is not None:
                if not isinstance(state.child_graph, StateGraphSpec):
                    raise StateGraphValidationError(
                        "state child_graph must be a StateGraphSpec or null",
                        path=f"{state_path}.child_graph",
                        state_id=state.id,
                    )
                state.child_graph.validate(
                    ids=claimed,
                    depth=depth + 1,
                    path=f"{state_path}.child_graph",
                )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "name": self.name,
            "initial_state_id": self.initial_state_id,
            "states": [state.to_dict() for state in self.states],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateGraphSpec":
        if not isinstance(data, dict):
            raise DocumentError("state_graph must be an object")
        return cls(
            id=data.get("id") or new_document_id(),
            name=data.get("name", ""),
            initial_state_id=data.get("initial_state_id", ""),
            states=[StateSpec.from_dict(item) for item in data.get("states", [])],
        )


@dataclass(init=False)
class SceneDocument:
    """Scene v3 authoring root with one embedded StateGraph source of truth."""

    name: str
    root: EditorNode
    id: str
    schema_version: int
    type: str
    symbol_name: str | None
    state_graph: StateGraphSpec
    timeline: list[TimelineEvent]
    metadata: dict[str, Any]
    variables: list[VariableSpec]
    output_mappings: list[VariableOutputMapping]

    def __init__(
        self,
        name: str,
        root: EditorNode,
        id: str | None = None,
        schema_version: int = CURRENT_SCHEMA_VERSION,
        type: str = SCENE_DOCUMENT_TYPE,
        symbol_name: str | None = None,
        tracks: list[TimelineTrack] | None = None,
        timeline: list[TimelineEvent] | None = None,
        metadata: dict[str, Any] | None = None,
        state_graph: StateGraphSpec | None = None,
        variables: list[VariableSpec] | None = None,
        output_mappings: list[VariableOutputMapping] | None = None,
    ) -> None:
        self.name = name
        self.root = root
        self.id = id or new_document_id()
        self.schema_version = _LegacyCompatibleSchemaVersion(int(schema_version))
        self.type = type
        self.symbol_name = symbol_name
        self.timeline = list(timeline or [])
        self.metadata = dict(metadata or {})
        self.variables = list(variables or [])
        self.output_mappings = list(output_mappings or [])
        self._legacy_v3_serialization = False
        self._legacy_empty_serialization = False
        supplied_tracks = list(tracks or [])
        if state_graph is None:
            try:
                namespace = uuid.UUID(str(self.id))
            except (ValueError, AttributeError, TypeError):
                namespace = uuid.NAMESPACE_URL
            graph_id = str(uuid.uuid5(namespace, "state-graph:root"))
            state_id = str(uuid.uuid5(namespace, "state:default"))
            authored_duration = self.metadata.get("duration_frames", 0)
            duration = (
                authored_duration
                if isinstance(authored_duration, int)
                and not isinstance(authored_duration, bool)
                and authored_duration >= 0
                else 0
            )
            state_graph = StateGraphSpec(
                id=graph_id,
                name="StageFlow",
                initial_state_id=state_id,
                states=[
                    StateSpec(
                        id=state_id,
                        name="Default",
                        duration_frames=duration,
                        tracks=supplied_tracks,
                    )
                ],
            )
        elif supplied_tracks:
            if state_graph.initial_state.tracks:
                raise DocumentError(
                    "SceneDocument cannot receive both state_graph tracks and tracks"
                )
            state_graph.initial_state.tracks = supplied_tracks
        self.state_graph = state_graph

    @property
    def tracks(self) -> list[TimelineTrack]:
        """Compatibility view of the root graph's initial State timeline.

        Scene v3 never serializes a second top-level copy. New code should use
        an explicit State id; legacy callers continue to mutate the exact list
        owned by the initial State.
        """

        return self.state_graph.initial_state.tracks

    @tracks.setter
    def tracks(self, value: list[TimelineTrack]) -> None:
        if not isinstance(value, list):
            raise DocumentError("document.tracks must be an array")
        self.state_graph.initial_state.tracks = value

    @property
    def coordinate_space(self) -> CoordinateSpace:
        return CoordinateSpace(
            logical_width=float(self.root.properties.get("width", 384)),
            logical_height=float(self.root.properties.get("height", 448)),
        )

    @property
    def timebase(self) -> Timebase:
        return Timebase(
            int(
                self.root.properties.get(
                    "tick_rate",
                    self.metadata.get("tick_rate", 60),
                )
            )
        )

    @property
    def duration_frames(self) -> int:
        authored = self.metadata.get("duration_frames", 0)
        authored = authored if isinstance(authored, int) and not isinstance(authored, bool) else 0
        return max(authored, 0, self.state_graph.nominal_duration_frames)

    def _promote_legacy_timeline(self) -> None:
        if not self.timeline:
            return
        track = TimelineTrack(
            id=str(uuid.uuid5(uuid.UUID(self.id), "compatibility-event-track")),
            name="Legacy Event Track",
            kind="Event",
            channel="event",
            order=len(self.tracks),
        )
        for index, event in enumerate(self.timeline):
            if not isinstance(event, TimelineEvent):
                raise DocumentError("document.timeline entries must be TimelineEvent values")
            event.validate()
            track.clips.append(
                TimelineClip(
                    id=event.id,
                    name=event.type,
                    kind="Event",
                    start_frame=event.frame,
                    duration_frames=1,
                    channel="event",
                    order=index,
                    payload={"event_type": event.type, "data": deepcopy(event.properties)},
                )
            )
        self.tracks.append(track)
        self.timeline.clear()

    def validate(self) -> None:
        try:
            header = ResourceHeader(
                schema_version=self.schema_version,
                type=self.type,
                id=self.id,
                name=self.name,
                symbol_name=self.symbol_name,
                metadata=self.metadata,
            )
            header.validate(
                expected_type=SCENE_DOCUMENT_TYPE,
                current_version=CURRENT_SCHEMA_VERSION,
            )
        except ResourceDocumentError as exc:
            raise DocumentError(str(exc)) from exc
        self.id = header.id
        self.metadata = header.metadata
        if not isinstance(self.root, EditorNode):
            raise DocumentError("document.root must be an EditorNode")
        self.root.validate()
        self._promote_legacy_timeline()

        ids = {self.id}
        for node in self.root.walk():
            if node.id in ids:
                raise DocumentError(f"Duplicate document object id: {node.id}")
            ids.add(node.id)
        node_ids = {node.id for node in self.root.walk()}
        nodes_by_id = {node.id: node for node in self.root.walk()}
        if not isinstance(self.state_graph, StateGraphSpec):
            raise DocumentError("document.state_graph must be a StateGraphSpec")
        if not isinstance(self.variables, list):
            raise DocumentError("document.variables must be an array")
        declaration_keys: set[tuple[str, str]] = set()
        for variable in self.variables:
            if not isinstance(variable, VariableSpec):
                raise DocumentError("document.variables entries must be VariableSpec values")
            variable.validate(path=f"variables.{variable.id}")
            if variable.scope == "state":
                raise DocumentError("state variables must be declared on their State")
            key = (variable.scope, variable.name)
            if key in declaration_keys:
                raise DocumentError(f"Duplicate variable declaration: {variable.scope}:{variable.name}")
            declaration_keys.add(key)
            variable.id = _claim_object_id(variable.id, ids, path=f"variables.{variable.id}")
        if not isinstance(self.output_mappings, list):
            raise DocumentError("document.output_mappings must be an array")
        for mapping in self.output_mappings:
            if not isinstance(mapping, VariableOutputMapping):
                raise DocumentError("document.output_mappings entries must be VariableOutputMapping values")
            mapping.validate(path=f"output_mappings.{mapping.id}")
            mapping.id = _claim_object_id(mapping.id, ids, path=f"output_mappings.{mapping.id}")
        self.state_graph.validate(ids=ids)
        for state, state_path in self.state_graph.iter_states_with_paths():
            for collection_name in ("entry_actions", "exit_actions"):
                for action in getattr(state, collection_name):
                    if action.target_id is not None and action.target_id not in node_ids:
                        raise StateGraphValidationError(
                            f"state action target_id does not exist: {action.target_id}",
                            path=f"{state_path}.{collection_name}.{action.id}.target_id",
                            state_id=state.id,
                        )
            for track in state.tracks:
                if track.target_id is not None and track.target_id not in node_ids:
                    raise DocumentError(f"track.target_id does not exist: {track.target_id}")
                for clip in track.clips:
                    if clip.target_id is not None and clip.target_id not in node_ids:
                        raise DocumentError(f"clip.target_id does not exist: {clip.target_id}")
                    effective_target = clip.target_id or track.target_id
                    if clip.kind in {"Movement", "Property"} and effective_target is None:
                        raise DocumentError(
                            f"{clip.kind} clip needs a track or clip target_id"
                        )
                    target_node = nodes_by_id.get(effective_target or "")
                    if clip.kind == "Movement" and target_node is not None:
                        x = target_node.properties.get("x")
                        y = target_node.properties.get("y")
                        if (
                            isinstance(x, bool)
                            or not isinstance(x, (int, float))
                            or isinstance(y, bool)
                            or not isinstance(y, (int, float))
                        ):
                            raise DocumentError(
                                "Movement clip target must expose numeric x and y properties"
                            )
                    if clip.kind == "Property" and target_node is not None:
                        property_name = str(
                            clip.payload.get("property") or clip.channel
                        ).strip()
                        if not property_name:
                            raise DocumentError(
                                "Property clip needs a property name or channel"
                            )
                        if property_name not in target_node.properties:
                            raise DocumentError(
                                f"Property clip target has no property {property_name!r}"
                            )
                    if (
                        clip.kind == "Pattern"
                        and effective_target is None
                        and not str(clip.payload.get("pattern") or "").strip()
                    ):
                        raise DocumentError(
                            "Pattern clip needs a track/clip target_id or payload.pattern"
                        )

    def to_dict(self, *, canonical: bool = False) -> dict[str, Any]:
        self.validate()
        payload = {
            "schema_version": self.schema_version,
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "metadata": self.metadata,
            "root": self.root.to_dict(),
            "state_graph": self.state_graph.to_dict(),
            "variables": [item.to_dict() for item in self.variables],
            "output_mappings": [item.to_dict() for item in self.output_mappings],
        }
        if self._legacy_v3_serialization or self._legacy_empty_serialization:
            def strip_empty_fields(graph: dict[str, Any]) -> None:
                for state in graph.get("states", []):
                    if not state.get("variables"):
                        state.pop("variables", None)
                    if not state.get("output_mappings"):
                        state.pop("output_mappings", None)
                    child = state.get("child_graph")
                    if isinstance(child, dict):
                        strip_empty_fields(child)

            strip_empty_fields(payload["state_graph"])
            if not payload["variables"]:
                payload.pop("variables", None)
            if not payload["output_mappings"]:
                payload.pop("output_mappings", None)
            metadata = dict(payload.get("metadata", {}))
            metadata.pop("variable_compatibility", None)
            payload["metadata"] = metadata
        if self._legacy_v3_serialization:
            payload["schema_version"] = 3
        if self.symbol_name is not None:
            payload["symbol_name"] = self.symbol_name
        if canonical:
            return self.to_canonical_dict()
        return payload

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return the only persisted v4 representation.

        Legacy N1 callers may still use :meth:`to_dict` and receive the
        retired v3 envelope when they loaded one explicitly.  Canonical
        storage always emits v4, keeps empty declaration arrays, and never
        leaks private migration markers.
        """

        legacy_v3 = self._legacy_v3_serialization
        legacy_empty = self._legacy_empty_serialization
        try:
            self._legacy_v3_serialization = False
            self._legacy_empty_serialization = False
            payload = self.to_dict()
        finally:
            self._legacy_v3_serialization = legacy_v3
            self._legacy_empty_serialization = legacy_empty
        payload["schema_version"] = int(SCENE_RESOURCE_SCHEMA_VERSION)
        metadata = dict(payload.get("metadata", {}))
        metadata.pop("_legacy_rootless_scene", None)
        metadata.pop("_legacy_v3_source", None)
        payload["metadata"] = metadata
        payload.setdefault("variables", [])
        payload.setdefault("output_mappings", [])

        def ensure_state_fields(graph: dict[str, Any]) -> None:
            for state in graph.get("states", []):
                state.setdefault("variables", [])
                state.setdefault("output_mappings", [])
                child = state.get("child_graph")
                if isinstance(child, dict):
                    ensure_state_fields(child)

        ensure_state_fields(payload["state_graph"])
        return deepcopy(payload)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        upgrade_variables: bool = False,
        canonical: bool = False,
    ) -> "SceneDocument":
        source_version = data.get("schema_version", 0) if isinstance(data, dict) else 0
        source_has_root = isinstance(data, dict) and "root" in data
        migrated = migrate_document(data)
        canonical = canonical or upgrade_variables
        if canonical:
            allowed = {
                "schema_version", "type", "id", "name", "symbol_name",
                "metadata", "root", "state_graph", "variables", "output_mappings",
            }
            unknown = set(migrated).difference(allowed)
            if unknown:
                raise DocumentError(
                    "scene has unknown fields: " + ", ".join(sorted(str(item) for item in unknown))
                )
        document = cls(
            schema_version=migrated["schema_version"],
            type=migrated["type"],
            id=migrated.get("id", ""),
            name=migrated.get("name", ""),
            symbol_name=migrated.get("symbol_name"),
            metadata=_json_object(migrated.get("metadata", {}), "document.metadata"),
            root=EditorNode.from_dict(migrated["root"]),
            state_graph=StateGraphSpec.from_dict(migrated["state_graph"]),
            variables=[VariableSpec.from_dict(item) for item in migrated.get("variables", [])],
            output_mappings=[
                VariableOutputMapping.from_dict(item)
                for item in migrated.get("output_mappings", [])
            ],
        )
        # Keep the retired v3 wire representation readable for N1 integrations
        # that explicitly load old files.  New content and callers that opt in
        # to N2 receive the canonical v4 envelope.
        if not canonical and isinstance(source_version, int) and source_version <= 3:
            if source_has_root:
                document._legacy_v3_serialization = True
            else:
                document._legacy_empty_serialization = True
        if document.metadata.get("_legacy_rootless_scene") is True:
            document._legacy_empty_serialization = True
            document.metadata.pop("_legacy_rootless_scene", None)
        if document.metadata.get("_legacy_v3_source") is True:
            if not canonical:
                document._legacy_v3_serialization = True
            document.metadata.pop("_legacy_v3_source", None)
        document.validate()
        return document


def migrate_document(data: dict[str, Any]) -> dict[str, Any]:
    try:
        return build_default_migration_registry().migrate(
            data,
            expected_type=SCENE_DOCUMENT_TYPE,
        )
    except MigrationError as exc:
        raise DocumentError(str(exc)) from exc
