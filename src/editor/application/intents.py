"""Typed, Qt-free edit requests consumed by :class:`EditorCoordinator`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | tuple["JsonValue", ...] | dict[str, "JsonValue"]


def _required_text(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_json_value(value: object, *, field_name: str = "value") -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_value(item, field_name=field_name)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} mapping keys must be str")
            _validate_json_value(item, field_name=field_name)
        return
    raise TypeError(f"{field_name} must be a JSON-compatible value")


@dataclass(frozen=True)
class EditorIntent:
    """Base value for one request against a stable open document identity."""

    document_id: str

    def __post_init__(self) -> None:
        _required_text("document_id", self.document_id)


@dataclass(frozen=True)
class SetNodePropertyIntent(EditorIntent):
    node_id: str
    property_name: str
    value: JsonValue

    def __post_init__(self) -> None:
        super().__post_init__()
        _required_text("node_id", self.node_id)
        _required_text("property_name", self.property_name)
        _validate_json_value(self.value)


@dataclass(frozen=True)
class SelectNodeIntent(EditorIntent):
    node_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        _required_text("node_id", self.node_id)


@dataclass(frozen=True)
class SetTimelinePlayheadIntent(EditorIntent):
    frame: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.frame, int) or isinstance(self.frame, bool):
            raise TypeError("frame must be int")
        if self.frame < 0:
            raise ValueError("frame must be non-negative")


@dataclass(frozen=True)
class UndoIntent(EditorIntent):
    pass


@dataclass(frozen=True)
class RedoIntent(EditorIntent):
    pass


@dataclass(frozen=True)
class AddSceneNodeIntent(EditorIntent):
    parent_id: str
    node_type: str
    name: str
    properties: dict[str, JsonValue]

    def __post_init__(self) -> None:
        super().__post_init__()
        _required_text("parent_id", self.parent_id)
        _required_text("node_type", self.node_type)
        _required_text("name", self.name)
        _validate_json_value(self.properties, field_name="properties")


@dataclass(frozen=True)
class MoveSceneNodeIntent(EditorIntent):
    node_id: str
    parent_id: str
    index: int

    def __post_init__(self) -> None:
        super().__post_init__()
        _required_text("node_id", self.node_id)
        _required_text("parent_id", self.parent_id)
        if not isinstance(self.index, int) or isinstance(self.index, bool):
            raise TypeError("index must be int")
        if self.index < 0:
            raise ValueError("index must be non-negative")


@dataclass(frozen=True)
class RemoveSceneNodeIntent(EditorIntent):
    node_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        _required_text("node_id", self.node_id)


@dataclass(frozen=True)
class RenameSceneNodeIntent(EditorIntent):
    node_id: str
    name: str

    def __post_init__(self) -> None:
        super().__post_init__()
        _required_text("node_id", self.node_id)
        _required_text("name", self.name)


@dataclass(frozen=True)
class SetSceneNodePropertiesIntent(EditorIntent):
    node_id: str
    properties: dict[str, JsonValue]
    coalesce: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        _required_text("node_id", self.node_id)
        _validate_json_value(self.properties, field_name="properties")
        if not isinstance(self.coalesce, bool):
            raise TypeError("coalesce must be bool")


@dataclass(frozen=True)
class CreateSimpleSpellIntent(EditorIntent):
    stage_name: str
    boss_name: str
    spell_name: str
    emitter_name: str
    instance_name: str
    pattern_resource: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        for field_name in (
            "stage_name",
            "boss_name",
            "spell_name",
            "emitter_name",
            "instance_name",
        ):
            _required_text(field_name, getattr(self, field_name))
        if not isinstance(self.pattern_resource, str):
            raise TypeError("pattern_resource must be str")


@dataclass(frozen=True)
class CreateStageTemplateIntent(EditorIntent):
    kind: str
    pattern_resource: str
    background_resource: str
    audio_resource: str
    language: str

    def __post_init__(self) -> None:
        super().__post_init__()
        for field_name in (
            "kind",
            "pattern_resource",
            "background_resource",
            "audio_resource",
            "language",
        ):
            _required_text(field_name, getattr(self, field_name))


__all__ = [
    "AddSceneNodeIntent",
    "CreateSimpleSpellIntent",
    "CreateStageTemplateIntent",
    "EditorIntent",
    "JsonScalar",
    "JsonValue",
    "MoveSceneNodeIntent",
    "RedoIntent",
    "RemoveSceneNodeIntent",
    "RenameSceneNodeIntent",
    "SelectNodeIntent",
    "SetNodePropertyIntent",
    "SetSceneNodePropertiesIntent",
    "SetTimelinePlayheadIntent",
    "UndoIntent",
]
