"""Compile a SceneDocument timeline into the formal StageProgram runtime."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.authoring import ResourceStore
from src.authoring.variables import (
    VARIABLE_OPERATIONS,
    VariableError,
    VariableOutputMapping,
    VariableRef,
    VariableSpec,
)
from src.core.project_context import ProjectContext
from src.game.stage.program import (
    PatternSchedule,
    StageAction,
    StageAutomation,
    StageKeyframe,
    StageNode,
    StageProgram,
    StageState,
    StageStateGraph,
    StageTransition,
    StageVariableAutomation,
)
from src.game.reactions import ActivationRule, ReactionSpec, ReactiveClip
from src.pattern import (
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
)

from .document import (
    EditorNode,
    SceneDocument,
    StateActionSpec,
    StateGraphSpec,
    StateGraphValidationError,
    StateSpec,
    TimelineClip,
    TimelineTrack,
)
from .node_types import NODE_TYPE_REGISTRY
from .pattern_resolve import (
    PatternResolveError,
    apply_spawn_origin,
    load_pattern_document,
    node_maps,
    spawn_origin_node,
)


STAGE_PROGRAM_VERSION = 3


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
    state_id: str | None = None
    transition_id: str | None = None


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
    state: StateSpec | None = None,
    transition_id: str | None = None,
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
                state_id=state.id if state is not None else None,
                transition_id=transition_id,
            ),
        )
    )


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
    state: StateSpec,
    state_path: str,
) -> tuple[str, PatternDocument]:
    value = _pattern_resource(target, clip)
    if not value:
        raise _failure(
            scene,
            "missing_pattern_resource",
            f"{state_path}.tracks.{track.id}.clips.{clip.id}.payload.pattern",
            "Assign a Pattern resource on the clip or target PatternInstance.",
            track=track,
            clip=clip,
            node=target,
            state=state,
        )
    try:
        return load_pattern_document(project, store, value)
    except PatternResolveError as exc:
        raise _failure(
            scene,
            "invalid_pattern_resource",
            f"{state_path}.tracks.{track.id}.clips.{clip.id}.payload.pattern",
            str(exc),
            track=track,
            clip=clip,
            node=target,
            state=state,
        ) from exc


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
    state: StateSpec,
    state_path: str,
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
            f"{state_path}.tracks.{track.id}.clips.{clip.id}",
            str(exc),
            track=track,
            clip=clip,
            state=state,
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
            f"{state_path}.tracks.{track.id}.clips.{clip.id}.payload.property",
            "Property clip needs payload.property or a non-empty channel.",
            track=track,
            clip=clip,
            state=state,
        )
    return StageAutomation(
        state_id=state.id,
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


def _variable_ref_from_payload(payload: dict[str, Any], *, path: str) -> VariableRef:
    raw = payload.get("variable_ref", payload.get("variable"))
    if raw is None:
        raw = payload.get("name")
    try:
        return VariableRef.from_dict(raw)
    except VariableError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def _compile_variable_automation(
    scene: SceneDocument,
    track: TimelineTrack,
    clip: TimelineClip,
    state: StateSpec,
    state_path: str,
) -> StageVariableAutomation:
    path = f"{state_path}.tracks.{track.id}.clips.{clip.id}"
    try:
        reference = _variable_ref_from_payload(clip.payload, path=f"{path}.payload.variable")
        declared = [
            item for item in _all_variable_specs(scene)
            if item.name == reference.name
            and (reference.scope is None or item.scope == reference.scope)
            and (reference.owner_id is None or item.owner_id in (None, reference.owner_id))
        ]
        if len(declared) == 1 and reference.scope is None:
            reference.scope = declared[0].scope
        operation = str(clip.payload.get("operation", "set"))
        if operation not in VARIABLE_OPERATIONS:
            raise ValueError(f"unsupported variable operation {operation!r}")
        if clip.keyframes:
            values = [
                StageKeyframe(
                    frame=item.frame,
                    value_json=_json(deepcopy(item.value)),
                    interpolation=item.interpolation,
                )
                for item in sorted(clip.keyframes, key=lambda value: value.frame)
            ]
        elif operation == "reset":
            values = [StageKeyframe(0, _json(None), "step")]
        else:
            values = [StageKeyframe(0, _json(deepcopy(clip.payload.get("value"))), "step")]
    except (TypeError, ValueError, VariableError) as exc:
        raise _failure(
            scene,
            "invalid_variable_automation",
            path,
            str(exc),
            track=track,
            clip=clip,
            state=state,
        ) from exc
    return StageVariableAutomation(
        state_id=state.id,
        track_id=track.id,
        clip_id=clip.id,
        variable_name=reference.name,
        variable_scope=reference.scope,
        owner_id=(
            reference.owner_id
            or (declared[0].owner_id if len(declared) == 1 else None)
            or (
                state.id
                if reference.scope == "state"
                else clip.id
                if reference.scope in {"clip", "reaction", "behavior"}
                else None
            )
        ),
        operation=operation,
        start_frame=clip.start_frame,
        duration_frames=clip.duration_frames,
        loop_count=clip.loop_count,
        track_order=track.order,
        clip_order=clip.order,
        keyframes=tuple(values),
        reducer=str(clip.payload.get("reducer")) if clip.payload.get("reducer") else None,
    )


def _all_variable_specs(scene: SceneDocument) -> tuple[VariableSpec, ...]:
    values = list(scene.variables)
    for state in scene.state_graph.walk_states():
        values.extend(state.variables)
    return tuple(values)


def _all_output_mappings(scene: SceneDocument) -> tuple[VariableOutputMapping, ...]:
    values = list(scene.output_mappings)
    for state in scene.state_graph.walk_states():
        values.extend(state.output_mappings)
    return tuple(values)


def _state_action_writes(scene: SceneDocument) -> tuple[StageAction, ...]:
    values: list[StageAction] = []
    for state in scene.state_graph.walk_states():
        for action in (*state.entry_actions, *state.exit_actions):
            values.append(_compile_state_action(state, action))
    return tuple(values)


def _variable_spec_for(
    specs: tuple[VariableSpec, ...],
    reference: VariableRef,
) -> VariableSpec | None:
    """Resolve a reference to exactly one spec, or None if it stays ambiguous."""

    candidates = _variable_candidates(specs, reference)
    return candidates[0] if len(candidates) == 1 else None


def _variable_candidates(
    specs: tuple[VariableSpec, ...], reference: VariableRef,
) -> list[VariableSpec]:
    candidates = [item for item in specs if item.name == reference.name]
    if reference.scope is not None:
        candidates = [item for item in candidates if item.scope == reference.scope]
    if reference.owner_id is not None:
        candidates = [
            item for item in candidates
            if item.owner_id in (None, reference.owner_id)
        ]
        exact = [item for item in candidates if item.owner_id == reference.owner_id]
        if exact:
            candidates = exact
    return candidates


def _variable_conflict_diagnostics(
    scene: SceneDocument,
    specs: tuple[VariableSpec, ...],
    variable_automations: tuple[StageVariableAutomation, ...],
    actions: tuple[StageAction, ...],
    mappings: tuple[VariableOutputMapping, ...] = (),
) -> tuple[StageCompileDiagnostic, ...]:
    diagnostics: list[StageCompileDiagnostic] = []
    legacy_keys = {
        str(item) for item in scene.metadata.get("legacy_variable_keys", [])
        if isinstance(item, str)
    }
    groups: dict[
        tuple[str, str, str, str],
        list[tuple[int, int, str, str, str | None, str]],
    ] = {}
    for item in variable_automations:
        reference = item.ref
        spec = _variable_spec_for(specs, reference)
        path = f"states.{item.state_id}.tracks.{item.track_id}.clips.{item.clip_id}.payload.variable"
        if spec is None:
            candidates = _variable_candidates(specs, reference)
            reason = (
                f"Variable {reference.name!r} is ambiguous; specify scope and owner"
                if candidates else f"Variable {reference.name!r} is not declared"
            )
            diagnostics.append(
                StageCompileDiagnostic(
                    "error", "unknown_variable", scene.id, item.track_id, item.clip_id,
                    None, path, reason, state_id=item.state_id,
                )
            )
            continue
        if "timeline" not in spec.writable_by or not spec.animatable:
            diagnostics.append(
                StageCompileDiagnostic(
                    "error", "variable_write_forbidden", scene.id, item.track_id, item.clip_id,
                    None, path, f"Timeline cannot write non-animatable or unauthorized variable {spec.name!r}", state_id=item.state_id,
                )
            )
        owner = item.owner_id or spec.owner_id or (
            spec.scope if spec.scope in {"project", "stage", "engine_snapshot"} else item.state_id
        )
        key = (spec.scope, spec.name, str(owner), item.state_id)
        groups.setdefault(key, []).append(
            (
                item.start_frame,
                item.end_frame,
                f"timeline:{item.clip_id}",
                f"states.{item.state_id}.tracks.{item.track_id}.clips.{item.clip_id}",
                item.reducer or spec.reducer,
                spec.type,
            )
        )
    for action in actions:
        if action.kind != "Variable":
            continue
        payload = action.payload
        path = f"states.{action.state_id}.actions.{action.clip_id}.payload.variable"
        try:
            ref = _variable_ref_from_payload(payload, path=f"states.{action.state_id}.actions.{action.clip_id}")
        except ValueError as exc:
            # The clip path raises for the same malformed payload.  Dropping the
            # action silently would compile a stage that quietly omits the write
            # the author asked for, with nothing pointing at the cause.
            diagnostics.append(StageCompileDiagnostic("error", "invalid_variable_automation", scene.id, action.track_id, action.clip_id, None, path, str(exc), state_id=action.state_id))
            continue
        spec = _variable_spec_for(specs, ref)
        if spec is None:
            candidates = _variable_candidates(specs, ref)
            reason = (
                f"Variable {ref.name!r} is ambiguous; specify scope and owner"
                if candidates else f"Variable {ref.name!r} is not declared"
            )
            diagnostics.append(StageCompileDiagnostic("error", "unknown_variable", scene.id, action.track_id, action.clip_id, None, path, reason, state_id=action.state_id))
            continue
        if "safe_action" not in spec.writable_by:
            diagnostics.append(StageCompileDiagnostic("error", "variable_write_forbidden", scene.id, action.track_id, action.clip_id, None, path, f"Safe Action cannot write {spec.name!r}", state_id=action.state_id))
        owner = spec.owner_id or (spec.scope if spec.scope in {"project", "stage", "engine_snapshot"} else action.state_id)
        key = (spec.scope, spec.name, str(owner), action.state_id)
        groups.setdefault(key, []).append(
            (
                action.frame,
                action.frame + 1,
                f"safe_action:{action.clip_id}",
                f"states.{action.state_id}.actions.{action.clip_id}",
                spec.reducer,
                spec.type,
            )
        )
    supported_reducers = {
        "override": {"bool", "int", "float", "string", "vector2", "color", "resource", "complex"},
        "add": {"int", "float", "vector2", "complex"},
        "multiply": {"int", "float", "vector2", "complex"},
        "blend": {"int", "float", "vector2", "complex"},
    }
    for (scope, name, owner, state_id), writes in groups.items():
        legacy_owner = "" if scope in {"project", "stage", "engine_snapshot"} else owner
        legacy_key = f"{scope}:{name}@{legacy_owner}"
        for index, left in enumerate(writes):
            for right in writes[index + 1 :]:
                if left[1] <= right[0] or right[1] <= left[0]:
                    continue
                reducer = left[4] or right[4]
                if (
                    scene.metadata.get("variable_compatibility") == "legacy_last_wins"
                    and legacy_key in legacy_keys
                ):
                    continue
                if reducer in supported_reducers and left[4] in {None, reducer} and right[4] in {None, reducer}:
                    if left[5] in supported_reducers[reducer]:
                        continue
                    message = f"reducer={reducer} is not supported for type={left[5]}"
                else:
                    message = "no compatible reducer was declared"
                diagnostics.append(
                    StageCompileDiagnostic(
                        "error", "variable_write_conflict", scene.id, None, None, None,
                        f"states.{state_id}.variables.{name}",
                        (
                            f"Multiple writers overlap for scope={scope} variable={name!r} owner={owner} "
                            f"intervals=[{left[0]},{left[1]})/{right[0]},{right[1]}) "
                            f"writers={left[2]} ({left[3]}) and {right[2]} ({right[3]}): {message}"
                        ),
                        state_id=state_id,
                    )
                )
                break
            else:
                continue
            break
    for mapping in mappings:
        source = mapping.source
        target = mapping.target
        if not isinstance(source, VariableRef) or not isinstance(target, VariableRef):
            continue
        source_spec = _variable_spec_for(specs, source)
        target_spec = _variable_spec_for(specs, target)
        path = f"output_mappings.{mapping.id}"
        if source_spec is None:
            source_candidates = _variable_candidates(specs, source)
            diagnostics.append(StageCompileDiagnostic("error", "unknown_variable", scene.id, None, None, None, f"{path}.source", f"Variable {source.name!r} is {'ambiguous; specify scope and owner' if source_candidates else 'not declared'}"))
        elif source_spec.scope != "behavior" or not source_spec.behavior_output:
            diagnostics.append(StageCompileDiagnostic("error", "invalid_behavior_output", scene.id, None, None, None, f"{path}.source", f"writer=behavior scope={source_spec.scope} variable={source.name!r} owner={source.owner_id}: not a declared Behavior output"))
        if source_spec is not None and source.type is not None and source.type != source_spec.type:
            diagnostics.append(StageCompileDiagnostic("error", "variable_type_mismatch", scene.id, None, None, None, f"{path}.source.type", f"writer=behavior scope={source_spec.scope} variable={source.name!r} owner={source_spec.owner_id}: declared type is {source_spec.type}, reference requested {source.type}"))
        if target_spec is None:
            target_candidates = _variable_candidates(specs, target)
            diagnostics.append(StageCompileDiagnostic("error", "unknown_variable", scene.id, None, None, None, f"{path}.target", f"Variable {target.name!r} is {'ambiguous; specify scope and owner' if target_candidates else 'not declared'}"))
        else:
            if target_spec.scope == "engine_snapshot":
                diagnostics.append(StageCompileDiagnostic("error", "variable_write_forbidden", scene.id, None, None, None, f"{path}.target", f"writer=behavior scope=engine_snapshot variable={target.name!r} owner={target.owner_id}: Engine Snapshot is read-only"))
            elif "behavior" not in target_spec.writable_by:
                diagnostics.append(StageCompileDiagnostic("error", "variable_write_forbidden", scene.id, None, None, None, f"{path}.target", f"writer=behavior scope={target_spec.scope} variable={target.name!r} owner={target.owner_id}: Behavior output cannot write"))
            if source_spec is not None and source_spec.type != target_spec.type:
                diagnostics.append(StageCompileDiagnostic("error", "variable_type_mismatch", scene.id, None, None, None, f"{path}", f"writer=behavior source={source.name}:{source_spec.type} target={target.name}:{target_spec.type}: types are incompatible"))
            if target.type is not None and target.type != target_spec.type:
                diagnostics.append(StageCompileDiagnostic("error", "variable_type_mismatch", scene.id, None, None, None, f"{path}.target.type", f"writer=behavior scope={target_spec.scope} variable={target.name!r} owner={target_spec.owner_id}: declared type is {target_spec.type}, reference requested {target.type}"))
            if mapping.operation == "toggle" and target_spec.type != "bool":
                diagnostics.append(StageCompileDiagnostic("error", "variable_operation_invalid", scene.id, None, None, None, f"{path}.operation", f"writer=behavior scope={target_spec.scope} variable={target.name!r}: toggle requires bool"))
            if mapping.operation == "add" and target_spec.type not in {"int", "float", "vector2", "complex"}:
                diagnostics.append(StageCompileDiagnostic("error", "variable_operation_invalid", scene.id, None, None, None, f"{path}.operation", f"writer=behavior scope={target_spec.scope} variable={target.name!r}: add is unsupported for {target_spec.type}"))
            if target_spec.scope in {"clip", "reaction", "behavior"} and not target.owner_id:
                diagnostics.append(StageCompileDiagnostic("error", "missing_variable_owner", scene.id, None, None, None, f"{path}.target.owner_id", f"writer=behavior scope={target_spec.scope} variable={target.name!r} requires an owner"))
    return tuple(diagnostics)


def _compile_state_action(
    state: StateSpec,
    action: StateActionSpec,
) -> StageAction:
    return StageAction(
        state_id=state.id,
        frame=0,
        track_id=state.id,
        clip_id=action.id,
        kind=action.kind,
        target_id=action.target_id,
        channel=action.channel,
        track_order=action.order,
        clip_order=action.order,
        payload_json=_json(deepcopy(action.payload)),
    )


def _compile_reactive_clip(
    scene: SceneDocument,
    track: TimelineTrack,
    clip: TimelineClip,
    state: StateSpec,
    state_path: str,
) -> ReactiveClip:
    path = f"{state_path}.tracks.{track.id}.clips.{clip.id}.payload"
    try:
        reaction_payload = clip.payload.get("reaction")
        reaction = ReactionSpec.from_dict(reaction_payload)
        activation_payload = clip.payload.get("activation")
        activation = (
            ActivationRule.from_dict(activation_payload)
            if activation_payload is not None
            else None
        )
        owner_id = clip.payload.get("owner_id")
        scope = str(clip.payload.get("scope", "state"))
        return ReactiveClip(
            clip.id,
            reaction,
            state_id=state.id,
            start_frame=clip.start_frame,
            end_frame=clip.end_frame,
            owner_id=owner_id,
            activation=activation,
            scope=scope,
        )
    except (TypeError, ValueError) as exc:
        detail = str(exc)
        field_path = path
        if "activation" in detail:
            field_path = f"{path}.activation"
        elif "reaction" in detail or "event" in detail or "action" in detail:
            field_path = f"{path}.reaction"
        raise _failure(
            scene,
            "invalid_reactive_clip",
            field_path,
            detail,
            track=track,
            clip=clip,
            state=state,
        ) from exc


def _compile_state_graph(graph: StateGraphSpec) -> StageStateGraph:
    runtime_states: list[StageState] = []
    for state in sorted(graph.states, key=lambda item: (item.order, item.id)):
        runtime_states.append(
            StageState(
                state_id=state.id,
                name=state.name,
                duration_frames=state.timeline_duration_frames,
                entry_actions=tuple(
                    _compile_state_action(state, item)
                    for item in sorted(
                        state.entry_actions, key=lambda value: (value.order, value.id)
                    )
                ),
                exit_actions=tuple(
                    _compile_state_action(state, item)
                    for item in sorted(
                        state.exit_actions, key=lambda value: (value.order, value.id)
                    )
                ),
                transitions=tuple(
                    StageTransition(
                        transition_id=item.id,
                        source_state_id=state.id,
                        target_state_id=item.target_state_id,
                        trigger=item.trigger,
                        after_frames=item.after_frames,
                        priority=item.priority,
                        order=index,
                    )
                    for index, item in enumerate(state.transitions)
                ),
                child_graph=(
                    _compile_state_graph(state.child_graph)
                    if state.child_graph is not None
                    else None
                ),
            )
        )
    return StageStateGraph(
        graph_id=graph.id,
        name=graph.name,
        initial_state_id=graph.initial_state_id,
        states=tuple(runtime_states),
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
    except StateGraphValidationError as exc:
        state = scene.state_graph.find_state(exc.state_id or "")
        raise _failure(
            scene,
            "invalid_state_graph",
            exc.path,
            exc.detail,
            state=state,
            transition_id=exc.transition_id,
        ) from exc
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
            "StageProgram v2 requires the formal 60 Hz pattern runtime.",
        )

    nodes, parents = node_maps(scene.root)
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
    variable_automations: list[StageVariableAutomation] = []
    actions: list[StageAction] = []
    reactive_clips: list[ReactiveClip] = []
    automatic_audio_stops: list[StageAction] = []
    dependency_hashes: list[str] = []

    ordered_tracks = [
        (state_index, state, state_path, track)
        for state_index, (state, state_path) in enumerate(
            scene.state_graph.iter_states_with_paths()
        )
        for track in state.tracks
    ]
    ordered_tracks.sort(key=lambda item: (item[0], item[3].order, item[3].id))
    for _state_index, state, state_path, track in ordered_tracks:
        if track.muted:
            continue
        for clip in sorted(track.clips, key=lambda item: (item.order, item.id)):
            if not clip.enabled:
                continue
            target_id = clip.target_id or track.target_id
            target = nodes.get(target_id or "")
            if clip.kind == "Variable" or any(
                key in clip.payload for key in ("variable", "variable_ref")
            ):
                variable_automations.append(
                    _compile_variable_automation(
                        scene, track, clip, state, state_path
                    )
                )
                continue
            if clip.kind in {"Movement", "Property"}:
                if target_id is None or target is None:
                    raise _failure(
                        scene,
                        "missing_target",
                        f"{state_path}.tracks.{track.id}.clips.{clip.id}.target_id",
                        f"{clip.kind} clip target does not exist.",
                        track=track,
                        clip=clip,
                        state=state,
                    )
                automations.append(
                    _compile_automation(
                        scene,
                        track,
                        clip,
                        target_id,
                        state,
                        state_path,
                    )
                )
                continue

            if clip.kind == "Pattern":
                resource_uri, document = _load_pattern(
                    project,
                    store,
                    scene,
                    track,
                    clip,
                    target,
                    state,
                    state_path,
                )
                position_node = spawn_origin_node(target, parents)
                if position_node is not None:
                    try:
                        document = apply_spawn_origin(scene, document, position_node)
                    except PatternResolveError as exc:
                        raise _failure(
                            scene,
                            "invalid_emitter_position",
                            f"nodes.{position_node.id}.properties",
                            str(exc),
                            track=track,
                            clip=clip,
                            node=position_node,
                            state=state,
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
                            path=(
                                f"{state_path}.tracks.{track.id}.clips."
                                f"{clip.id}.payload.pattern"
                            ),
                            referenced_path=item.path,
                            message=item.message,
                            state_id=state.id,
                        )
                        for item in exc.diagnostics
                    )
                    raise StageCompileError(diagnostics) from exc
                dependency_hashes.append(program.content_hash)
                patterns.append(
                    PatternSchedule(
                        state_id=state.id,
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

            if clip.kind == "Reactive":
                reactive_clips.append(
                    _compile_reactive_clip(scene, track, clip, state, state_path)
                )
                continue

            if clip.kind in {"Audio", "Background", "Event", "ScriptEvent"}:
                try:
                    payload_json = _json(deepcopy(clip.payload))
                except (TypeError, ValueError) as exc:
                    raise _failure(
                        scene,
                        "invalid_action_payload",
                        f"{state_path}.tracks.{track.id}.clips.{clip.id}.payload",
                        str(exc),
                        track=track,
                        clip=clip,
                        state=state,
                    ) from exc
                for loop_index in range(clip.loop_count):
                    actions.append(
                        StageAction(
                            state_id=state.id,
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
                if (
                    clip.kind == "Audio"
                    and str(clip.payload.get("action", "play")) == "play"
                    and str(clip.payload.get("bus") or clip.channel or track.channel).lower()
                    == "bgm"
                    and clip.duration_frames > 1
                    and bool(clip.payload.get("auto_stop", True))
                ):
                    automatic_audio_stops.append(
                        StageAction(
                            state_id=state.id,
                            frame=clip.end_frame,
                            track_id=track.id,
                            clip_id=clip.id,
                            kind="Audio",
                            target_id=target_id,
                            channel=clip.channel or track.channel,
                            track_order=track.order,
                            clip_order=clip.order,
                            payload_json=_json(
                                {
                                    "action": "stop",
                                    "bus": str(
                                        clip.payload.get("bus")
                                        or clip.channel
                                        or track.channel
                                    ).lower(),
                                    "fade_ms": int(clip.payload.get("end_fade_ms", 0)),
                                    "automatic": True,
                                }
                            ),
                        )
                    )

    duration = scene.duration_frames
    explicit_audio_stops = {
        (
            item.state_id,
            item.frame,
            str(item.payload.get("bus") or item.channel or "se").lower(),
        )
        for item in actions
        if item.kind == "Audio" and item.payload.get("action") == "stop"
    }
    actions.extend(
        item
        for item in automatic_audio_stops
        if (
            item.state_id,
            item.frame,
            str(item.payload.get("bus") or item.channel or "se").lower(),
        )
        not in explicit_audio_stops
    )
    variable_specs = _all_variable_specs(scene)
    variable_diagnostics = _variable_conflict_diagnostics(
        scene,
        variable_specs,
        tuple(variable_automations),
        tuple(actions) + _state_action_writes(scene),
        _all_output_mappings(scene),
    )
    if variable_diagnostics:
        raise StageCompileError(variable_diagnostics)
    canonical = _json(scene.to_canonical_dict())
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
                key=lambda item: (item.state_id, item.start_frame, *item.order_key),
            )
        ),
        automations=tuple(
            sorted(
                automations,
                key=lambda item: (item.state_id, item.start_frame, *item.order_key),
            )
        ),
        actions=tuple(
            sorted(
                actions,
                key=lambda item: (item.state_id, item.frame, *item.order_key),
            )
        ),
        state_graph=_compile_state_graph(scene.state_graph),
        variable_specs=variable_specs,
        variable_automations=tuple(
            sorted(
                variable_automations,
                key=lambda item: (item.state_id, item.start_frame, *item.order_key),
            )
        ),
        output_mappings=_all_output_mappings(scene),
        replay_seed=(
            int(scene.metadata.get("seed", 0))
            if isinstance(scene.metadata.get("seed", 0), int)
            and not isinstance(scene.metadata.get("seed", 0), bool)
            else 0
        ),
        reactive_clips=tuple(
            sorted(
                reactive_clips,
                key=lambda item: (
                    item.state_id or "",
                    item.start_frame,
                    item.clip_id,
                ),
            )
        ),
    )


__all__ = [
    "STAGE_PROGRAM_VERSION",
    "StageCompileDiagnostic",
    "StageCompileError",
    "compile_stage",
]
