"""Compile a SceneDocument timeline into the formal StageProgram runtime."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.authoring import ResourceStore
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.core.project_context import ProjectContext, ProjectContextError
from src.game.stage.program import (
    PatternSchedule,
    StageAction,
    StageAutomation,
    StageKeyframe,
    StageNode,
    StageProgram,
)
from src.pattern import (
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
)

from .document import EditorNode, SceneDocument, TimelineClip, TimelineTrack
from .node_types import NODE_TYPE_REGISTRY
from .pattern_commands import pattern_with_property


STAGE_PROGRAM_VERSION = 1


@dataclass(frozen=True)
class StageCompileDiagnostic:
    severity: str
    code: str
    resource_id: str
    track_id: str | None
    clip_id: str | None
    node_id: str | None
    path: str
    message: str
    referenced_path: str | None = None


class StageCompileError(ValueError):
    def __init__(self, diagnostics: tuple[StageCompileDiagnostic, ...]):
        self.diagnostics = diagnostics
        super().__init__(
            "; ".join(f"{item.path}: {item.message}" for item in diagnostics)
            or "stage compilation failed"
        )


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _failure(
    scene: SceneDocument,
    code: str,
    path: str,
    message: str,
    *,
    track: TimelineTrack | None = None,
    clip: TimelineClip | None = None,
    node: EditorNode | None = None,
    referenced_path: str | None = None,
) -> StageCompileError:
    return StageCompileError(
        (
            StageCompileDiagnostic(
                severity="error",
                code=code,
                resource_id=scene.id,
                track_id=track.id if track is not None else None,
                clip_id=clip.id if clip is not None else None,
                node_id=node.id if node is not None else None,
                path=path,
                message=message,
                referenced_path=referenced_path,
            ),
        )
    )


def _node_maps(
    root: EditorNode,
) -> tuple[dict[str, EditorNode], dict[str, EditorNode | None]]:
    nodes: dict[str, EditorNode] = {}
    parents: dict[str, EditorNode | None] = {}

    def visit(node: EditorNode, parent: EditorNode | None) -> None:
        nodes[node.id] = node
        parents[node.id] = parent
        for child in node.children:
            visit(child, node)

    visit(root, None)
    return nodes, parents


def _position_node(
    target: EditorNode | None,
    parents: dict[str, EditorNode | None],
) -> EditorNode | None:
    node = target
    while node is not None:
        if node.type == "Emitter" or (
            "x" in node.properties and "y" in node.properties
        ):
            return node
        node = parents.get(node.id)
    return None


def _pattern_resource(target: EditorNode | None, clip: TimelineClip) -> str:
    explicit = str(clip.payload.get("pattern") or "").strip()
    if explicit:
        return explicit
    if target is not None and target.type == "PatternInstance":
        return str(target.properties.get("pattern") or "").strip()
    if target is not None:
        instance = next(
            (
                node
                for node in target.walk()
                if node.type == "PatternInstance"
                and bool(node.properties.get("enabled", True))
                and str(node.properties.get("pattern") or "").strip()
            ),
            None,
        )
        if instance is not None:
            return str(instance.properties["pattern"]).strip()
    return ""


def _load_pattern(
    project: ProjectContext,
    store: ResourceStore,
    scene: SceneDocument,
    track: TimelineTrack,
    clip: TimelineClip,
    target: EditorNode | None,
) -> tuple[str, PatternDocument]:
    value = _pattern_resource(target, clip)
    if not value:
        raise _failure(
            scene,
            "missing_pattern_resource",
            f"tracks.{track.id}.clips.{clip.id}.payload.pattern",
            "Assign a Pattern resource on the clip or target PatternInstance.",
            track=track,
            clip=clip,
            node=target,
        )
    try:
        reference = ResourceReference.parse(value)
        if reference.subresource is not None:
            raise ResourceDocumentError(
                "PatternDocument references cannot contain fragments"
            )
        source = reference.resolve(project, must_exist=True)
        document = store.load(source)
        if not isinstance(document, PatternDocument):
            raise ResourceDocumentError(
                f"Referenced resource is {getattr(document, 'type', type(document).__name__)!r}, not pystg.pattern"
            )
    except (OSError, ValueError, ResourceDocumentError, ProjectContextError) as exc:
        raise _failure(
            scene,
            "invalid_pattern_resource",
            f"tracks.{track.id}.clips.{clip.id}.payload.pattern",
            str(exc),
            track=track,
            clip=clip,
            node=target,
        ) from exc
    return reference.uri, document


def _movement_value(scene: SceneDocument, value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("Movement keyframe value must be an object with x/y")
    x = value.get("x")
    y = value.get("y")
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError("Movement keyframe x must be numeric")
    if isinstance(y, bool) or not isinstance(y, (int, float)):
        raise ValueError("Movement keyframe y must be numeric")
    runtime_x, runtime_y = scene.coordinate_space.authoring_to_runtime(float(x), float(y))
    return {"x": runtime_x, "y": runtime_y}


def _compile_automation(
    scene: SceneDocument,
    track: TimelineTrack,
    clip: TimelineClip,
    target_id: str,
) -> StageAutomation:
    try:
        if clip.keyframes:
            values = [
                StageKeyframe(
                    frame=item.frame,
                    value_json=_json(
                        _movement_value(scene, item.value)
                        if clip.kind == "Movement"
                        else deepcopy(item.value)
                    ),
                    interpolation=item.interpolation,
                )
                for item in sorted(clip.keyframes, key=lambda value: value.frame)
            ]
        elif clip.kind == "Movement":
            values = [
                StageKeyframe(
                    0,
                    _json(_movement_value(scene, clip.payload["from"])),
                    str(clip.payload.get("interpolation", "linear")),
                ),
                StageKeyframe(
                    clip.duration_frames,
                    _json(_movement_value(scene, clip.payload["to"])),
                    "linear",
                ),
            ]
        else:
            values = [
                StageKeyframe(
                    0,
                    _json(deepcopy(clip.payload["value"])),
                    "step",
                )
            ]
    except (KeyError, TypeError, ValueError) as exc:
        raise _failure(
            scene,
            "invalid_automation",
            f"tracks.{track.id}.clips.{clip.id}",
            str(exc),
            track=track,
            clip=clip,
        ) from exc

    property_name = (
        "position"
        if clip.kind == "Movement"
        else str(clip.payload.get("property") or clip.channel).strip()
    )
    if not property_name:
        raise _failure(
            scene,
            "missing_property",
            f"tracks.{track.id}.clips.{clip.id}.payload.property",
            "Property clip needs payload.property or a non-empty channel.",
            track=track,
            clip=clip,
        )
    return StageAutomation(
        track_id=track.id,
        clip_id=clip.id,
        kind=clip.kind,
        target_id=target_id,
        channel=clip.channel or track.channel,
        property_name=property_name,
        start_frame=clip.start_frame,
        duration_frames=clip.duration_frames,
        loop_count=clip.loop_count,
        track_order=track.order,
        clip_order=clip.order,
        keyframes=tuple(values),
    )


def compile_stage(
    project: ProjectContext,
    scene: SceneDocument,
    *,
    pattern_compiler: PatternCompiler | None = None,
    sprite_index_resolver=None,
) -> StageProgram:
    """Compile one authored Scene and its referenced Patterns without codegen."""

    try:
        scene.validate()
        NODE_TYPE_REGISTRY.validate_tree(scene.root)
    except Exception as exc:
        raise _failure(
            scene,
            "invalid_scene",
            "scene",
            str(exc),
        ) from exc
    if scene.timebase.tick_rate != 60:
        raise _failure(
            scene,
            "unsupported_tick_rate",
            "root.properties.tick_rate",
            "StageProgram v1 requires the formal 60 Hz pattern runtime.",
        )

    nodes, parents = _node_maps(scene.root)
    runtime_nodes: list[StageNode] = []
    for node in scene.root.walk():
        properties = deepcopy(node.properties)
        if "x" in properties and "y" in properties:
            try:
                properties["x"], properties["y"] = scene.coordinate_space.authoring_to_runtime(
                    float(properties["x"]), float(properties["y"])
                )
            except (TypeError, ValueError) as exc:
                raise _failure(
                    scene,
                    "invalid_node_position",
                    f"nodes.{node.id}.properties",
                    str(exc),
                    node=node,
                ) from exc
        try:
            properties_json = _json(properties)
        except (TypeError, ValueError) as exc:
            raise _failure(
                scene,
                "invalid_node_properties",
                f"nodes.{node.id}.properties",
                str(exc),
                node=node,
            ) from exc
        runtime_nodes.append(
            StageNode(node.id, node.type, node.name, properties_json)
        )

    compiler = pattern_compiler or PatternCompiler()
    store = ResourceStore(project)
    patterns: list[PatternSchedule] = []
    automations: list[StageAutomation] = []
    actions: list[StageAction] = []
    dependency_hashes: list[str] = []

    ordered_tracks = sorted(scene.tracks, key=lambda item: (item.order, item.id))
    for track in ordered_tracks:
        if track.muted:
            continue
        for clip in sorted(track.clips, key=lambda item: (item.order, item.id)):
            if not clip.enabled:
                continue
            target_id = clip.target_id or track.target_id
            target = nodes.get(target_id or "")
            if clip.kind in {"Movement", "Property"}:
                if target_id is None or target is None:
                    raise _failure(
                        scene,
                        "missing_target",
                        f"tracks.{track.id}.clips.{clip.id}.target_id",
                        f"{clip.kind} clip target does not exist.",
                        track=track,
                        clip=clip,
                    )
                automations.append(
                    _compile_automation(scene, track, clip, target_id)
                )
                continue

            if clip.kind == "Pattern":
                resource_uri, document = _load_pattern(
                    project, store, scene, track, clip, target
                )
                position_node = _position_node(target, parents)
                if position_node is not None:
                    try:
                        x = float(position_node.properties.get("x", 192.0))
                        y = float(position_node.properties.get("y", 224.0))
                        runtime_x, runtime_y = scene.coordinate_space.authoring_to_runtime(x, y)
                        document = pattern_with_property(document, "shape.origin_x", runtime_x)
                        document = pattern_with_property(document, "shape.origin_y", runtime_y)
                    except (TypeError, ValueError) as exc:
                        raise _failure(
                            scene,
                            "invalid_emitter_position",
                            f"nodes.{position_node.id}.properties",
                            str(exc),
                            track=track,
                            clip=clip,
                            node=position_node,
                        ) from exc
                try:
                    program = compiler.compile(
                        document,
                        project=project,
                        sprite_index_resolver=sprite_index_resolver,
                    )
                except PatternCompileError as exc:
                    diagnostics = tuple(
                        StageCompileDiagnostic(
                            severity=item.severity,
                            code=item.code,
                            resource_id=scene.id,
                            track_id=track.id,
                            clip_id=clip.id,
                            node_id=target_id,
                            path=f"tracks.{track.id}.clips.{clip.id}.payload.pattern",
                            referenced_path=item.path,
                            message=item.message,
                        )
                        for item in exc.diagnostics
                    )
                    raise StageCompileError(diagnostics) from exc
                dependency_hashes.append(program.content_hash)
                patterns.append(
                    PatternSchedule(
                        track_id=track.id,
                        clip_id=clip.id,
                        target_id=target_id,
                        position_target_id=(position_node.id if position_node else target_id),
                        channel=clip.channel or track.channel,
                        start_frame=clip.start_frame,
                        duration_frames=clip.duration_frames,
                        loop_count=clip.loop_count,
                        track_order=track.order,
                        clip_order=clip.order,
                        resource_uri=resource_uri,
                        base_origin=program.origin,
                        program=program,
                    )
                )
                continue

            if clip.kind in {"Audio", "Event", "ScriptEvent"}:
                try:
                    payload_json = _json(deepcopy(clip.payload))
                except (TypeError, ValueError) as exc:
                    raise _failure(
                        scene,
                        "invalid_action_payload",
                        f"tracks.{track.id}.clips.{clip.id}.payload",
                        str(exc),
                        track=track,
                        clip=clip,
                    ) from exc
                for loop_index in range(clip.loop_count):
                    actions.append(
                        StageAction(
                            frame=clip.start_frame + loop_index * clip.duration_frames,
                            track_id=track.id,
                            clip_id=clip.id,
                            kind=clip.kind,
                            target_id=target_id,
                            channel=clip.channel or track.channel,
                            track_order=track.order,
                            clip_order=clip.order,
                            payload_json=payload_json,
                        )
                    )

    duration = scene.duration_frames
    canonical = _json(scene.to_dict())
    identity = "\0".join(
        (
            f"stage-program-v{STAGE_PROGRAM_VERSION}",
            canonical,
            *sorted(dependency_hashes),
        )
    )
    content_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return StageProgram(
        resource_id=scene.id,
        schema_version=scene.schema_version,
        content_hash=content_hash,
        name=scene.name,
        tick_rate=scene.timebase.tick_rate,
        duration_frames=duration,
        nodes=tuple(runtime_nodes),
        patterns=tuple(
            sorted(
                patterns,
                key=lambda item: (item.start_frame, *item.order_key),
            )
        ),
        automations=tuple(
            sorted(
                automations,
                key=lambda item: (item.start_frame, *item.order_key),
            )
        ),
        actions=tuple(
            sorted(
                actions,
                key=lambda item: (item.frame, *item.order_key),
            )
        ),
    )


__all__ = [
    "STAGE_PROGRAM_VERSION",
    "StageCompileDiagnostic",
    "StageCompileError",
    "compile_stage",
]
