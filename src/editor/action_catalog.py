"""Typed, deterministic action catalog for contextual authoring search."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from src.pattern.graph import NODE_TYPES as GRAPH_NODE_TYPES
from src.pattern.graph import PORT_TYPES as GRAPH_PORT_TYPES


_CONTEXTS = frozenset({"graph", "timeline", "scene", "inspector", "preset"})
_SOURCES = frozenset({"builtin", "project", "plugin"})


class ActionCatalogError(ValueError):
    """A stable, path-addressed catalog diagnostic."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


@dataclass(frozen=True)
class ActionDescriptor:
    id: str
    title: str
    contexts: tuple[str, ...]
    command_id: str
    input_types: tuple[str, ...] = ()
    output_type: str | None = None
    capabilities: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    source: str = "builtin"
    help_text: str = ""
    performance_hint: str = ""
    allowed_parent_types: tuple[str, ...] | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def validate(self, path: str = "action") -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]+", self.id):
            raise ActionCatalogError(f"{path}.id", "must be a stable namespaced id")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ActionCatalogError(f"{path}.title", "must be non-empty")
        if not self.contexts or set(self.contexts).difference(_CONTEXTS):
            raise ActionCatalogError(f"{path}.contexts", "contains unsupported values")
        if not isinstance(self.command_id, str) or not self.command_id.strip():
            raise ActionCatalogError(f"{path}.command_id", "must be non-empty")
        if self.source not in _SOURCES:
            raise ActionCatalogError(f"{path}.source", "is unsupported")
        if not isinstance(self.payload, Mapping):
            raise ActionCatalogError(f"{path}.payload", "must be an object")

    @property
    def search_text(self) -> str:
        return " ".join((self.title, *self.aliases, *self.tags, self.id)).casefold()


@dataclass(frozen=True)
class ActionQuery:
    context: str
    text: str = ""
    input_type: str | None = None
    parent_type: str | None = None
    timeline_kind: str | None = None
    required_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionMatch:
    descriptor: ActionDescriptor
    reason: str


class ActionCatalog:
    def __init__(self, descriptors: Iterable[ActionDescriptor] = ()):
        self._descriptors: dict[str, ActionDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: ActionDescriptor) -> None:
        descriptor.validate(f"actions[{descriptor.id!r}]")
        if descriptor.id in self._descriptors:
            raise ActionCatalogError(
                f"actions[{descriptor.id!r}].id", "duplicates an existing action id"
            )
        self._descriptors[descriptor.id] = descriptor

    @property
    def descriptors(self) -> tuple[ActionDescriptor, ...]:
        return tuple(self._descriptors.values())

    def search(self, query: ActionQuery) -> tuple[ActionMatch, ...]:
        if query.context not in _CONTEXTS:
            raise ActionCatalogError("query.context", "is unsupported")
        words = tuple(word for word in query.text.casefold().split() if word)
        required = set(query.required_capabilities)
        matches: list[tuple[tuple[int, str, str], ActionMatch]] = []
        for descriptor in self._descriptors.values():
            if query.context not in descriptor.contexts:
                continue
            if query.input_type is not None and query.input_type not in descriptor.input_types:
                continue
            if (
                query.parent_type is not None
                and descriptor.allowed_parent_types is not None
                and query.parent_type not in descriptor.allowed_parent_types
            ):
                continue
            if (
                query.timeline_kind is not None
                and descriptor.command_id == "add_timeline_clip"
                and descriptor.payload.get("kind") != query.timeline_kind
            ):
                continue
            if not required.issubset(descriptor.capabilities):
                continue
            if not all(word in descriptor.search_text for word in words):
                continue
            exact = 0 if query.text and query.text.casefold() == descriptor.title.casefold() else 1
            matches.append(
                (
                    (exact, descriptor.title.casefold(), descriptor.id),
                    ActionMatch(
                        descriptor,
                        f"context={query.context}; input={query.input_type or 'none'}; "
                        f"parent={query.parent_type or 'none'}; source={descriptor.source}",
                    ),
                )
            )
        return tuple(match for _key, match in sorted(matches, key=lambda item: item[0]))


def build_editor_action_catalog(*, presets=(), node_registry=None) -> ActionCatalog:
    descriptors: list[ActionDescriptor] = []
    for preset in presets:
        descriptors.append(
            ActionDescriptor(
                id=f"action.preset.{preset.preset_id}",
                title=preset.display_name,
                contexts=("preset", "graph"),
                command_id="apply_preset",
                aliases=(preset.preset_id,),
                tags=(preset.category, "弹幕", "preset"),
                source="builtin",
                help_text=preset.description,
                performance_hint=f"max {preset.budget.get('max_bullets_total', 0)} bullets",
                payload={"preset_id": preset.preset_id, "version": preset.version},
            )
        )
    graph_titles = {
        ("source", "bullet"): "子弹源",
        ("shape", "ring"): "圆形点集",
        ("shape", "arc"): "扇形点集",
        ("shape", "spiral"): "螺旋点集",
        ("shape", "line"): "线形点集",
        ("shape", "random"): "随机点集",
        ("shape", "flower"): "花形点集",
        ("aim", "fixed"): "固定瞄准",
        ("aim", "player"): "自机狙",
        ("schedule", "interval"): "等待时间",
        ("motion", "constant"): "匀速运动",
        ("modifier", "angle_offset"): "旋转修饰",
        ("condition", "threshold"): "阈值条件",
        ("event", "signal"): "事件信号",
        ("script", "behavior"): "脚本扩展",
    }
    for category in sorted(GRAPH_NODE_TYPES):
        input_type, output_type = GRAPH_PORT_TYPES[category]
        for node_type in sorted(GRAPH_NODE_TYPES[category]):
            descriptors.append(
                ActionDescriptor(
                    id=f"action.graph.{category}.{node_type}",
                    title=graph_titles.get((category, node_type), node_type),
                    contexts=("graph",),
                    command_id="add_graph_node",
                    input_types=() if input_type is None else (input_type,),
                    output_type=output_type,
                    aliases=(category, node_type),
                    tags=("节点",),
                    payload={"category": category, "node_type": node_type},
                )
            )
    for kind in (
        "Pattern", "Movement", "Audio", "Background", "Event", "Property",
        "ScriptEvent", "Reactive",
    ):
        descriptors.append(
            ActionDescriptor(
                id=f"action.timeline.track.{kind.casefold()}",
                title=f"{kind} 轨道",
                contexts=("timeline",),
                command_id="add_timeline_track",
                aliases=(kind, "轨道"),
                tags=("timeline",),
                payload={"kind": kind},
            )
        )
        descriptors.append(
            ActionDescriptor(
                id=f"action.timeline.clip.{kind.casefold()}",
                title=f"{kind} 片段",
                contexts=("timeline",),
                command_id="add_timeline_clip",
                input_types=(kind,),
                aliases=(kind, "片段"),
                tags=("timeline",),
                payload={"kind": kind},
            )
        )
    if node_registry is not None:
        for type_name in node_registry:
            spec = node_registry[type_name]
            if not spec.allowed_parents:
                continue
            descriptors.append(
                ActionDescriptor(
                    id=f"action.scene.node.{type_name.casefold()}",
                    title=f"创建 {spec.display_name}",
                    contexts=("scene",),
                    command_id="add_scene_node",
                    aliases=(type_name, spec.display_name),
                    tags=("对象", "节点"),
                    allowed_parent_types=spec.allowed_parents,
                    payload={"node_type": type_name},
                )
            )
    return ActionCatalog(descriptors)


class ActionExecutor:
    """Dispatch catalog commands to registered editor handlers."""

    def __init__(self):
        self._handlers: dict[str, Callable[[ActionDescriptor], Any]] = {}

    def register(self, command_id: str, handler: Callable[[ActionDescriptor], Any]) -> None:
        if command_id in self._handlers:
            raise ValueError(f"duplicate action command handler: {command_id}")
        self._handlers[command_id] = handler

    def execute(self, descriptor: ActionDescriptor) -> Any:
        try:
            handler = self._handlers[descriptor.command_id]
        except KeyError as exc:
            raise ActionCatalogError(
                f"actions[{descriptor.id!r}].command_id",
                f"unresolved action command: {descriptor.command_id}",
            ) from exc
        return handler(descriptor)
