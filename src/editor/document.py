"""Versioned, serializable authoring documents for the future editor."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable


CURRENT_SCHEMA_VERSION = 1
SCENE_DOCUMENT_TYPE = "pystg.scene"


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
    timeline: list[TimelineEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        self.id = _valid_id(self.id, "document.id")
        if self.schema_version != CURRENT_SCHEMA_VERSION:
            raise DocumentError(
                f"Unsupported schema_version {self.schema_version}; "
                f"expected {CURRENT_SCHEMA_VERSION}"
            )
        if self.type != SCENE_DOCUMENT_TYPE:
            raise DocumentError(f"Unsupported document type: {self.type!r}")
        if not isinstance(self.name, str) or not self.name.strip():
            raise DocumentError("document.name must be a non-empty string")
        if not isinstance(self.root, EditorNode):
            raise DocumentError("document.root must be an EditorNode")
        self.root.validate()
        self.metadata = _json_object(self.metadata, "document.metadata")

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
        return {
            "schema_version": self.schema_version,
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "metadata": self.metadata,
            "root": self.root.to_dict(),
            "timeline": [event.to_dict() for event in self.timeline],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneDocument":
        migrated = migrate_document(data)
        document = cls(
            schema_version=migrated["schema_version"],
            type=migrated["type"],
            id=migrated["id"],
            name=migrated["name"],
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
    if not isinstance(data, dict):
        raise DocumentError("document must be an object")
    version = data.get("schema_version", 0)
    if isinstance(version, bool) or not isinstance(version, int):
        raise DocumentError("schema_version must be an integer")
    if version > CURRENT_SCHEMA_VERSION:
        raise DocumentError(
            f"Document schema {version} is newer than supported "
            f"{CURRENT_SCHEMA_VERSION}"
        )

    migrated = dict(data)
    if version == 0:
        migrated = _migrate_v0_to_v1(migrated)
        version = 1
    if version != CURRENT_SCHEMA_VERSION:
        raise DocumentError(f"No migration path from schema_version {version}")
    return migrated


def _migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    root = data.get("root")
    if root is None:
        root = {
            "type": "Stage",
            "name": data.get("name", "Scene"),
            "properties": {},
            "children": data.get("nodes", []),
        }
    return {
        "schema_version": 1,
        "type": SCENE_DOCUMENT_TYPE,
        "id": data.get("id") or new_document_id(),
        "name": data.get("name", "Scene"),
        "metadata": data.get("metadata", {}),
        "root": root,
        "timeline": data.get("timeline", []),
    }
