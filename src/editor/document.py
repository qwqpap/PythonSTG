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


CURRENT_SCHEMA_VERSION = SCENE_RESOURCE_SCHEMA_VERSION
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
    {"Pattern", "Movement", "Audio", "Event", "Property", "ScriptEvent"}
)
TIMELINE_INTERPOLATIONS = frozenset(
    {"step", "linear", "ease_in", "ease_out", "ease_in_out"}
)


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


@dataclass
class SceneDocument:
    name: str
    root: EditorNode
    id: str = field(default_factory=new_document_id)
    schema_version: int = CURRENT_SCHEMA_VERSION
    type: str = SCENE_DOCUMENT_TYPE
    symbol_name: str | None = None
    tracks: list[TimelineTrack] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict)

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
        return max(
            [authored, 0]
            + [clip.end_frame for track in self.tracks for clip in track.clips]
        )

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
        for track in self.tracks:
            if not isinstance(track, TimelineTrack):
                raise DocumentError("document.tracks entries must be TimelineTrack values")
            track.validate()
            if track.id in ids:
                raise DocumentError(f"Duplicate document object id: {track.id}")
            ids.add(track.id)
            if track.target_id is not None and track.target_id not in node_ids:
                raise DocumentError(f"track.target_id does not exist: {track.target_id}")
            for clip in track.clips:
                if clip.id in ids:
                    raise DocumentError(f"Duplicate document object id: {clip.id}")
                ids.add(clip.id)
                if clip.target_id is not None and clip.target_id not in node_ids:
                    raise DocumentError(f"clip.target_id does not exist: {clip.target_id}")
                effective_target = clip.target_id or track.target_id
                if clip.kind in {"Movement", "Property"} and effective_target is None:
                    raise DocumentError(f"{clip.kind} clip needs a track or clip target_id")
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
                        raise DocumentError("Property clip needs a property name or channel")
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
                for keyframe in clip.keyframes:
                    if keyframe.id in ids:
                        raise DocumentError(f"Duplicate document object id: {keyframe.id}")
                    ids.add(keyframe.id)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = {
            "schema_version": self.schema_version,
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "metadata": self.metadata,
            "root": self.root.to_dict(),
            "tracks": [track.to_dict() for track in self.tracks],
        }
        if self.symbol_name is not None:
            payload["symbol_name"] = self.symbol_name
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneDocument":
        migrated = migrate_document(data)
        document = cls(
            schema_version=migrated["schema_version"],
            type=migrated["type"],
            id=migrated.get("id", ""),
            name=migrated.get("name", ""),
            symbol_name=migrated.get("symbol_name"),
            metadata=_json_object(migrated.get("metadata", {}), "document.metadata"),
            root=EditorNode.from_dict(migrated["root"]),
            tracks=[TimelineTrack.from_dict(item) for item in migrated.get("tracks", [])],
        )
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
