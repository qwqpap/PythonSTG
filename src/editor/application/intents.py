"""Typed, Qt-free edit requests consumed by :class:`EditorCoordinator`."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TypeAlias


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]


class FrozenJsonObject(Mapping[str, JsonValue]):
    """Small recursively immutable mapping used by frozen intent snapshots."""

    def __init__(self, values: Mapping[str, JsonValue]):
        self.__values = dict(values)

    def __getitem__(self, key: str) -> JsonValue:
        return self.__values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.__values)

    def __len__(self) -> int:
        return len(self.__values)


def _snapshot_json(value: object, *, field_name: str = "value") -> JsonValue:
    _validate_json_value(value, field_name=field_name)
    if isinstance(value, Mapping):
        return FrozenJsonObject(
            {
                str(key): _snapshot_json(item, field_name=field_name)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_snapshot_json(item, field_name=field_name) for item in value)
    return value


def thaw_json(value: JsonValue) -> object:
    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


def thaw_json_object(value: Mapping[str, JsonValue]) -> dict[str, object]:
    return {str(key): thaw_json(item) for key, item in value.items()}


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
    if isinstance(value, Mapping):
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
        object.__setattr__(self, "value", _snapshot_json(self.value))


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
    properties: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        super().__post_init__()
        _required_text("parent_id", self.parent_id)
        _required_text("node_type", self.node_type)
        _required_text("name", self.name)
        object.__setattr__(
            self,
            "properties",
            _snapshot_json(self.properties, field_name="properties"),
        )


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
    properties: Mapping[str, JsonValue]
    coalesce: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        _required_text("node_id", self.node_id)
        object.__setattr__(
            self,
            "properties",
            _snapshot_json(self.properties, field_name="properties"),
        )
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


class TimelineAction(Enum):
    ADD_TRACK = auto()
    SELECT_TRACK = auto()
    SET_REACTIVE_NAVIGATION = auto()
    SET_TRACK_PROPERTIES = auto()
    REMOVE_TRACK = auto()
    MOVE_TRACK = auto()
    ADD_CLIP = auto()
    ADD_KEYFRAME = auto()
    REMOVE_KEYFRAME = auto()
    SET_KEYFRAME_PROPERTIES = auto()
    MOVE_CLIP = auto()
    DUPLICATE_CLIP = auto()
    REMOVE_CLIP = auto()
    SELECT_CLIP = auto()
    SET_CLIP_PROPERTIES = auto()
    SET_ZOOM = auto()


@dataclass(frozen=True)
class TimelineIntent(EditorIntent):
    action: TimelineAction
    target_id: str = ""
    related_id: str = ""
    values: Mapping[str, JsonValue] = field(default_factory=dict)
    frame: int = 0
    amount: int = 0
    coalesce: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.action, TimelineAction):
            raise TypeError("action must be TimelineAction")
        if not isinstance(self.target_id, str) or not isinstance(self.related_id, str):
            raise TypeError("timeline target ids must be str")
        object.__setattr__(
            self, "values", _snapshot_json(self.values, field_name="values")
        )
        for field_name in ("frame", "amount"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be int")
        if not isinstance(self.coalesce, bool):
            raise TypeError("coalesce must be bool")


class PatternAction(Enum):
    SET_PROPERTIES = auto()
    SET_MODE = auto()
    SET_LEVEL = auto()
    SET_BINDING = auto()
    REMOVE_BINDING = auto()
    SET_SOURCE_PATH = auto()
    EXPAND_GRAPH = auto()
    FOLD_GRAPH = auto()
    SELECT_GRAPH_NODE = auto()
    SET_GRAPH_NODE_PROPERTIES = auto()
    MOVE_GRAPH_NODE = auto()
    ADD_GRAPH_NODE = auto()
    ADD_GRAPH_EDGE = auto()
    REMOVE_GRAPH_NODE = auto()
    REMOVE_GRAPH_EDGE = auto()
    APPLY_TEMPLATE = auto()
    SET_PRESET_PARAMETER = auto()
    SET_PRESET_SLOT = auto()
    MIGRATE_PRESET = auto()
    MATERIALIZE_PRESET = auto()
    SET_PLAYER_POSITION = auto()


@dataclass(frozen=True)
class PatternIntent(EditorIntent):
    action: PatternAction
    target_id: str = ""
    related_id: str = ""
    values: Mapping[str, JsonValue] = field(default_factory=dict)
    value: JsonValue = None
    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.action, PatternAction):
            raise TypeError("action must be PatternAction")
        if not isinstance(self.target_id, str) or not isinstance(self.related_id, str):
            raise TypeError("pattern target ids must be str")
        object.__setattr__(
            self, "values", _snapshot_json(self.values, field_name="values")
        )
        object.__setattr__(self, "value", _snapshot_json(self.value))
        if not isinstance(self.x, float) or not isinstance(self.y, float):
            raise TypeError("x and y must be float")


class AuthoringAction(Enum):
    SELECT_STATE = auto()
    ADD_VARIABLE = auto()
    REMOVE_VARIABLE = auto()
    SET_VARIABLE = auto()
    SELECT_BINDING = auto()
    SET_OUTPUT_MAPPINGS = auto()
    ADD_STATE = auto()
    RENAME_STATE = auto()
    DUPLICATE_STATE = auto()
    REMOVE_STATE = auto()
    MOVE_STATE = auto()
    ADD_TRANSITION = auto()
    SET_TRANSITION = auto()
    REMOVE_TRANSITION = auto()


@dataclass(frozen=True)
class AuthoringIntent(EditorIntent):
    action: AuthoringAction
    target_id: str = ""
    related_id: str = ""
    values: Mapping[str, JsonValue] = field(default_factory=dict)
    items: tuple[Mapping[str, JsonValue], ...] = field(default_factory=tuple)
    amount: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.action, AuthoringAction):
            raise TypeError("action must be AuthoringAction")
        if not isinstance(self.target_id, str) or not isinstance(self.related_id, str):
            raise TypeError("authoring target ids must be str")
        object.__setattr__(
            self, "values", _snapshot_json(self.values, field_name="values")
        )
        frozen_items = _snapshot_json(self.items, field_name="items")
        if not isinstance(frozen_items, tuple):
            raise TypeError("items must be a tuple of mappings")
        object.__setattr__(self, "items", frozen_items)
        if not isinstance(self.amount, int) or isinstance(self.amount, bool):
            raise TypeError("amount must be int")


class UIDocumentAction(Enum):
    SELECT_NODE = auto()
    ADD_NODE = auto()
    REMOVE_NODE = auto()
    SET_NODE_PROPERTIES = auto()
    SET_VIEWPORT = auto()


@dataclass(frozen=True)
class UIDocumentIntent(EditorIntent):
    action: UIDocumentAction
    target_id: str = ""
    parent_id: str = ""
    node_type: str = ""
    name: str = ""
    values: Mapping[str, JsonValue] = field(default_factory=dict)
    width: int = 0
    height: int = 0
    coalesce: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.action, UIDocumentAction):
            raise TypeError("action must be UIDocumentAction")
        for value in (self.target_id, self.parent_id, self.node_type, self.name):
            if not isinstance(value, str):
                raise TypeError("UI intent text fields must be str")
        object.__setattr__(
            self, "values", _snapshot_json(self.values, field_name="values")
        )
        for field_name in ("width", "height"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be int")
        if not isinstance(self.coalesce, bool):
            raise TypeError("coalesce must be bool")


class BackgroundAction(Enum):
    SELECT_LAYER = auto()
    SET_PROPERTY = auto()
    ADD_LAYER = auto()
    REMOVE_LAYER = auto()
    SET_BINDING = auto()


@dataclass(frozen=True)
class BackgroundIntent(EditorIntent):
    action: BackgroundAction
    target: str = ""
    value: JsonValue = None
    index: int = 0
    expression: str = ""
    coalesce: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.action, BackgroundAction):
            raise TypeError("action must be BackgroundAction")
        if not isinstance(self.target, str) or not isinstance(self.expression, str):
            raise TypeError("background target and expression must be str")
        object.__setattr__(self, "value", _snapshot_json(self.value))
        if not isinstance(self.index, int) or isinstance(self.index, bool):
            raise TypeError("index must be int")
        if not isinstance(self.coalesce, bool):
            raise TypeError("coalesce must be bool")


__all__ = [
    "AddSceneNodeIntent",
    "AuthoringAction",
    "AuthoringIntent",
    "BackgroundAction",
    "BackgroundIntent",
    "CreateSimpleSpellIntent",
    "CreateStageTemplateIntent",
    "EditorIntent",
    "FrozenJsonObject",
    "JsonScalar",
    "JsonValue",
    "MoveSceneNodeIntent",
    "PatternAction",
    "PatternIntent",
    "RedoIntent",
    "RemoveSceneNodeIntent",
    "RenameSceneNodeIntent",
    "SelectNodeIntent",
    "SetNodePropertyIntent",
    "SetSceneNodePropertiesIntent",
    "SetTimelinePlayheadIntent",
    "TimelineAction",
    "TimelineIntent",
    "UIDocumentAction",
    "UIDocumentIntent",
    "UndoIntent",
    "thaw_json",
    "thaw_json_object",
]
