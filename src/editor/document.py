"""Versioned, serializable authoring documents for the future editor."""

from __future__ import annotations

import json
import uuid
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
    ResourceDocumentError,
    ResourceHeader,
)


CURRENT_SCHEMA_VERSION = RESOURCE_SCHEMA_VERSION
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
class SceneDocument:
    name: str
    root: EditorNode
    id: str = field(default_factory=new_document_id)
    schema_version: int = CURRENT_SCHEMA_VERSION
    type: str = SCENE_DOCUMENT_TYPE
    symbol_name: str | None = None
    timeline: list[TimelineEvent] = field(default_factory=list)
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

        ids = {self.id}
        for node in self.root.walk():
            if node.id in ids:
                raise DocumentError(f"Duplicate document object id: {node.id}")
            ids.add(node.id)
        for event in self.timeline:
            if not isinstance(event, TimelineEvent):
                raise DocumentError("document.timeline entries must be TimelineEvent values")
            event.validate()
            if event.id in ids:
                raise DocumentError(f"Duplicate document object id: {event.id}")
            ids.add(event.id)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = {
            "schema_version": self.schema_version,
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "metadata": self.metadata,
            "root": self.root.to_dict(),
            "timeline": [event.to_dict() for event in self.timeline],
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
            timeline=[
                TimelineEvent.from_dict(event)
                for event in migrated.get("timeline", [])
            ],
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
