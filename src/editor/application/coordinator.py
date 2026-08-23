"""Qt-free edit coordination over the active managed authoring document."""

from __future__ import annotations

from collections import defaultdict

from src.pattern import BindingSpec, PatternDocument, PresetResolver
from src.authoring.variables import VariableOutputMapping, VariableSpec
from src.game.background_render.document import BackgroundDocument
from src.ui.document import UIDocument, UIDocumentNode
from src.authoring.commands.background import (
    AddBackgroundLayerCommand,
    RemoveBackgroundLayerCommand,
    SetBackgroundBindingCommand,
    SetBackgroundPropertyCommand,
)
from src.authoring.commands.state_graph import (
    AddStateCommand,
    AddTransitionCommand,
    DuplicateStateCommand,
    MoveStateCommand,
    RemoveStateCommand,
    RemoveTransitionCommand,
    RenameStateCommand,
    SetTransitionPropertiesCommand,
)
from src.authoring.commands.base import Command, CompositeCommand
from src.authoring.scene.document import (
    EditorNode,
    SceneDocument,
    StateSpec,
    TimelineClip,
    TimelineKeyframe,
    TimelineTrack,
    TransitionSpec,
)
from src.editor.document_manager import DocumentManager, ManagedDocument
from src.authoring.scene.node_types import make_node, property_specs
from src.authoring.commands.scene import (
    AddNodeCommand,
    AssignResourceCommand,
    MoveNodeCommand,
    RemoveNodeCommand,
    RenameNodeCommand,
    SetNodePropertiesCommand,
    SetNodePropertyCommand,
    find_parent,
)
from src.authoring.commands.stage_template import ApplyStageTemplateCommand
from src.authoring.commands.graph import (
    AddGraphEdgeCommand,
    AddGraphNodeCommand,
    ExpandToGraphCommand,
    FoldBackToRecipeCommand,
    RemoveGraphEdgeCommand,
    RemoveGraphNodeCommand,
    SetGraphNodePositionCommand,
    SetGraphNodePropertiesCommand,
)
from src.authoring.commands.pattern import (
    RemovePatternBindingCommand,
    SetPatternBindingCommand,
    SetPatternPropertyCommand,
)
from src.authoring.commands.preset import (
    ApplyPresetCommand,
    ApplyPresetMigrationCommand,
    MaterializePresetCommand,
    SetPresetOverrideCommand,
    SetPresetSlotOverrideCommand,
)
from src.editor.progressive_authoring import authoring_level
from src.authoring.commands.timeline import (
    AddClipCommand,
    AddKeyframeCommand,
    AddTrackCommand,
    MoveResizeClipCommand,
    MoveTrackCommand,
    RemoveClipCommand,
    RemoveKeyframeCommand,
    RemoveTrackCommand,
    SetClipPropertiesCommand,
    SetKeyframePropertiesCommand,
    SetTrackPropertiesCommand,
    clone_clip_with_new_ids,
    find_clip,
    require_track,
    timeline_tracks,
)
from src.authoring.commands.ui import (
    AddUINodeCommand,
    RemoveUINodeCommand,
    SetUINodePropertyCommand,
)
from src.authoring.commands.variables import (
    AddOutputMappingCommand,
    AddVariableCommand,
    RemoveOutputMappingCommand,
    RemoveVariableCommand,
    SetOutputMappingPropertiesCommand,
    SetVariablePropertiesCommand,
)

from .errors import IntentRejectedError, IntentRejectionCode
from .intents import (
    AddSceneNodeIntent,
    AuthoringAction,
    AuthoringIntent,
    BackgroundAction,
    BackgroundIntent,
    CreateSimpleSpellIntent,
    CreateStageTemplateIntent,
    EditorIntent,
    MoveSceneNodeIntent,
    PatternAction,
    PatternIntent,
    RedoIntent,
    RemoveSceneNodeIntent,
    RenameSceneNodeIntent,
    SelectNodeIntent,
    SetNodePropertyIntent,
    SetSceneNodePropertiesIntent,
    SetTimelinePlayheadIntent,
    TimelineAction,
    TimelineIntent,
    UIDocumentAction,
    UIDocumentIntent,
    UndoIntent,
    thaw_json,
    thaw_json_object,
)
from .invalidation import EMPTY_INVALIDATION, InvalidationScope, InvalidationSet


_NODE_PROPERTY_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.SCENE_CANVAS,
        InvalidationScope.INSPECTOR,
        InvalidationScope.ACTIONS,
        InvalidationScope.TITLE,
    )
)

_SCENE_STRUCTURE_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.SCENE_TREE,
        InvalidationScope.SCENE_CANVAS,
        InvalidationScope.INSPECTOR,
        InvalidationScope.ACTIONS,
        InvalidationScope.TITLE,
    )
)

_SCENE_DOCUMENT_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.SCENE_TREE,
        InvalidationScope.SCENE_CANVAS,
        InvalidationScope.INSPECTOR,
        InvalidationScope.TIMELINE,
        InvalidationScope.STATE_GRAPH,
        InvalidationScope.VARIABLES,
        InvalidationScope.ACTIONS,
        InvalidationScope.TITLE,
    )
)

_TIMELINE_MUTATION_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.TIMELINE,
        InvalidationScope.INSPECTOR,
        InvalidationScope.ACTIONS,
        InvalidationScope.TITLE,
    )
)

_TIMELINE_SELECTION_INVALIDATION = InvalidationSet(
    (InvalidationScope.TIMELINE, InvalidationScope.INSPECTOR)
)

_PATTERN_MUTATION_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.PATTERN,
        InvalidationScope.INSPECTOR,
        InvalidationScope.ACTIONS,
        InvalidationScope.TITLE,
    )
)

_PATTERN_VIEW_INVALIDATION = InvalidationSet(
    (InvalidationScope.PATTERN, InvalidationScope.INSPECTOR)
)

_PATTERN_SELECTION_INVALIDATION = InvalidationSet(
    (InvalidationScope.INSPECTOR,)
)

_UI_MUTATION_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.UI_CANVAS,
        InvalidationScope.INSPECTOR,
        InvalidationScope.ACTIONS,
        InvalidationScope.TITLE,
    )
)

_BACKGROUND_MUTATION_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.BACKGROUND,
        InvalidationScope.INSPECTOR,
        InvalidationScope.ACTIONS,
        InvalidationScope.TITLE,
    )
)

_STATE_GRAPH_MUTATION_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.STATE_GRAPH,
        InvalidationScope.TIMELINE,
        InvalidationScope.VARIABLES,
        InvalidationScope.INSPECTOR,
        InvalidationScope.ACTIONS,
        InvalidationScope.TITLE,
    )
)

_STATE_SELECTION_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.STATE_GRAPH,
        InvalidationScope.TIMELINE,
        InvalidationScope.VARIABLES,
        InvalidationScope.INSPECTOR,
    )
)

_VARIABLE_MUTATION_INVALIDATION = InvalidationSet(
    (
        InvalidationScope.VARIABLES,
        InvalidationScope.INSPECTOR,
        InvalidationScope.ACTIONS,
        InvalidationScope.TITLE,
    )
)


class EditorCoordinator:
    """Validate intents, submit Commands, update transient state, return damage."""

    def __init__(
        self,
        manager: DocumentManager,
        *,
        preset_resolver: PresetResolver | None = None,
    ):
        self.manager = manager
        self.preset_resolver = preset_resolver
        self._undo_invalidations: dict[str, list[InvalidationSet]] = defaultdict(list)
        self._redo_invalidations: dict[str, list[InvalidationSet]] = defaultdict(list)
        self._last_merge_key: dict[str, tuple[object, ...] | None] = {}

    def reset_document_history(self, document_id: str) -> None:
        self._undo_invalidations.pop(document_id, None)
        self._redo_invalidations.pop(document_id, None)
        self._last_merge_key.pop(document_id, None)

    def _session_for(self, document_id: str) -> ManagedDocument:
        session = next(
            (item for item in self.manager if item.document.id == document_id),
            None,
        )
        if session is None:
            raise IntentRejectedError(
                IntentRejectionCode.DOCUMENT_NOT_OPEN,
                f"Document is not open: {document_id}",
            )
        if self.manager.active is not session:
            raise IntentRejectedError(
                IntentRejectionCode.INACTIVE_DOCUMENT,
                f"Document is not active: {document_id}",
            )
        return session

    def _record_mutation(
        self,
        session: ManagedDocument,
        invalidation: InvalidationSet,
    ) -> None:
        document_id = session.document.id
        self._undo_invalidations[document_id].append(invalidation)
        self._redo_invalidations[document_id].clear()

    def _submit(
        self,
        session: ManagedDocument,
        command: Command,
        invalidation: InvalidationSet,
        *,
        coalesce: bool = False,
        merge_key: tuple[object, ...] | None = None,
    ) -> InvalidationSet:
        document_id = session.document.id
        previous_key = self._last_merge_key.get(document_id)
        session.apply(command, coalesce=coalesce)
        if coalesce and merge_key is not None and previous_key == merge_key:
            history = self._undo_invalidations[document_id]
            if history:
                history[-1] = history[-1].union(invalidation)
            else:
                self._record_mutation(session, invalidation)
        else:
            self._record_mutation(session, invalidation)
        self._last_merge_key[document_id] = merge_key if coalesce else None
        return invalidation

    @staticmethod
    def _require_scene(session: ManagedDocument) -> SceneDocument:
        if not isinstance(session.document, SceneDocument):
            raise IntentRejectedError(
                IntentRejectionCode.INVALID_INTENT,
                "Intent requires an active Scene document",
            )
        return session.document

    @staticmethod
    def _require_node(session: ManagedDocument, node_id: str):
        node = session.node(node_id)
        if node is None:
            raise IntentRejectedError(
                IntentRejectionCode.TARGET_NOT_FOUND,
                f"Scene node does not exist: {node_id}",
            )
        return node

    @staticmethod
    def _timeline_default_target(
        session: ManagedDocument,
        kind: str,
    ) -> EditorNode | None:
        document = session.document
        if not isinstance(document, SceneDocument):
            return None
        selected = session.node(session.editor_state.selection.node_id)
        if kind == "Pattern":
            if selected is not None and selected.type == "PatternInstance":
                return selected
            return next(
                (node for node in document.root.walk() if node.type == "PatternInstance"),
                None,
            )
        if kind == "Movement":
            if (
                selected is not None
                and isinstance(selected.properties.get("x"), (int, float))
                and not isinstance(selected.properties.get("x"), bool)
                and isinstance(selected.properties.get("y"), (int, float))
                and not isinstance(selected.properties.get("y"), bool)
            ):
                return selected
            return next(
                (node for node in document.root.walk() if node.type in {"Emitter", "Boss"}),
                None,
            )
        if kind == "Property":
            if selected is not None and "enabled" in selected.properties:
                return selected
            return next(
                (node for node in document.root.walk() if "enabled" in node.properties),
                None,
            )
        return None

    def _dispatch_timeline(
        self,
        session: ManagedDocument,
        intent: TimelineIntent,
    ) -> InvalidationSet:
        document = self._require_scene(session)
        action = intent.action
        selection = session.editor_state.selection

        if action is TimelineAction.ADD_TRACK:
            kind = intent.target_id
            target = self._timeline_default_target(session, kind)
            if kind in {"Pattern", "Movement", "Property"} and target is None:
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"Create or select a compatible target before adding a {kind} track",
                )
            channels = {
                "Pattern": "danmaku",
                "Movement": "position",
                "Audio": "bgm",
                "Background": "background",
                "Event": "event",
                "Property": "enabled",
                "ScriptEvent": "script",
                "Reactive": "reaction",
            }
            if kind not in channels:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    f"Unknown timeline track kind: {kind}",
                )
            state_id = str(selection.state_id or document.state_graph.initial_state_id)
            track = TimelineTrack(
                name=f"{kind} Track",
                kind=kind,
                channel=channels[kind],
                target_id=target.id if target is not None else None,
                order=len(timeline_tracks(document, state_id)),
            )
            result = self._submit(
                session,
                AddTrackCommand(document, track, state_id=state_id, label=f"Add {kind} track"),
                _TIMELINE_MUTATION_INVALIDATION,
            )
            selection.track_id = track.id
            selection.clip_id = None
            return result

        if action is TimelineAction.SELECT_TRACK:
            track = require_track(document, intent.target_id)
            selection.track_id = track.id
            selection.clip_id = None
            return _TIMELINE_SELECTION_INVALIDATION

        if action is TimelineAction.SET_REACTIVE_NAVIGATION:
            session.editor_state.timeline.reactive_navigation = (
                intent.target_id,
                intent.related_id,
            )
            return InvalidationSet((InvalidationScope.TIMELINE,))

        if action is TimelineAction.SET_TRACK_PROPERTIES:
            require_track(document, intent.target_id)
            result = self._submit(
                session,
                SetTrackPropertiesCommand(
                    document,
                    intent.target_id,
                    thaw_json_object(intent.values),
                ),
                _TIMELINE_MUTATION_INVALIDATION,
                coalesce=intent.coalesce,
                merge_key=("track-properties", intent.target_id, tuple(sorted(intent.values))),
            )
            selection.track_id = intent.target_id
            selection.clip_id = None
            return result

        if action is TimelineAction.REMOVE_TRACK:
            require_track(document, intent.target_id)
            result = self._submit(
                session,
                RemoveTrackCommand(document, intent.target_id),
                _TIMELINE_MUTATION_INVALIDATION,
            )
            selection.track_id = None
            selection.clip_id = None
            return result

        if action is TimelineAction.MOVE_TRACK:
            track = require_track(document, intent.target_id)
            state_id = str(selection.state_id or document.state_graph.initial_state_id)
            tracks = timeline_tracks(document, state_id)
            current = tracks.index(track)
            target_index = max(0, min(current + intent.amount, len(tracks) - 1))
            if target_index == current:
                return EMPTY_INVALIDATION
            result = self._submit(
                session,
                MoveTrackCommand(document, intent.target_id, target_index),
                _TIMELINE_MUTATION_INVALIDATION,
            )
            selection.track_id = intent.target_id
            return result

        if action is TimelineAction.ADD_CLIP:
            track = require_track(document, intent.target_id)
            start = intent.frame
            target_id = track.target_id
            duration = 1
            payload: dict[str, object] = {}
            keyframes: list[TimelineKeyframe] = []
            if track.kind == "Pattern":
                duration = document.timebase.tick_rate * 10
                if target_id is None:
                    raise IntentRejectedError(
                        IntentRejectionCode.TARGET_NOT_FOUND,
                        "Pattern track needs a PatternInstance target",
                    )
            elif track.kind == "Movement":
                duration = document.timebase.tick_rate * 2
                node = session.node(target_id)
                if node is None:
                    raise IntentRejectedError(
                        IntentRejectionCode.TARGET_NOT_FOUND,
                        "Movement track needs a Scene node target",
                    )
                x = float(node.properties.get("x", 192.0))
                y = float(node.properties.get("y", 224.0))
                keyframes = [
                    TimelineKeyframe(0, {"x": x, "y": y}),
                    TimelineKeyframe(
                        duration,
                        {"x": min(384.0, x + 64.0), "y": y},
                        interpolation="ease_in_out",
                    ),
                ]
            elif track.kind == "Audio":
                duration = max(document.timebase.tick_rate * 30, document.duration_frames)
                payload = {"action": "play", "name": "bgm", "loops": -1}
            elif track.kind == "Background":
                payload = {
                    "resource": "res://game_content/backgrounds/default.pystg.json",
                    "fade_frames": 30,
                }
            elif track.kind == "Event":
                payload = {"event_type": "timeline_event", "data": {}}
            elif track.kind == "Property":
                node = session.node(target_id)
                if node is None:
                    raise IntentRejectedError(
                        IntentRejectionCode.TARGET_NOT_FOUND,
                        "Property track needs a Scene node target",
                    )
                payload = {
                    "property": track.channel,
                    "value": node.properties.get(track.channel, True),
                }
            elif track.kind == "ScriptEvent":
                payload = {"hook": "on_timeline_event", "data": {}}
            elif track.kind == "Reactive":
                duration = document.timebase.tick_rate * 10
                payload = {
                    "activation": {"kind": "on_event", "event_type": "boss.hit"},
                    "reaction": {
                        "id": f"reaction-{track.id[:8]}",
                        "event_type": "boss.hit",
                        "action": "reaction.action",
                        "once_per_scope": False,
                    },
                }
            clip = TimelineClip(
                name=f"{track.kind} Clip",
                kind=track.kind,
                start_frame=start,
                duration_frames=duration,
                target_id=target_id,
                channel=track.channel,
                order=len(track.clips),
                payload=payload,
                keyframes=keyframes,
            )
            result = self._submit(
                session,
                AddClipCommand(document, track.id, clip, label=f"Add {track.kind} clip"),
                _TIMELINE_MUTATION_INVALIDATION,
            )
            selection.track_id = track.id
            selection.clip_id = clip.id
            return result

        if action is TimelineAction.ADD_KEYFRAME:
            found = find_clip(document, intent.target_id)
            if found is None:
                raise IntentRejectedError(IntentRejectionCode.TARGET_NOT_FOUND, "Clip not found")
            track, clip, _index = found
            if clip.kind not in {"Movement", "Property"}:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    "Only Movement and Property clips support keyframes",
                )
            relative = max(0, intent.frame - clip.start_frame)
            local = min(
                clip.duration_frames,
                relative % clip.duration_frames if clip.loop_count > 1 else relative,
            )
            if any(item.frame == local for item in clip.keyframes):
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    f"A keyframe already exists at local frame {local}",
                )
            target = session.node(clip.target_id or track.target_id)
            if clip.kind == "Movement":
                value = {
                    "x": float(target.properties.get("x", 192.0)) if target else 192.0,
                    "y": float(target.properties.get("y", 224.0)) if target else 224.0,
                }
            else:
                value = clip.payload.get("value")
                if clip.keyframes:
                    previous = [item for item in clip.keyframes if item.frame < local]
                    value = (previous[-1] if previous else clip.keyframes[0]).value
            result = self._submit(
                session,
                AddKeyframeCommand(document, clip.id, TimelineKeyframe(local, value)),
                _TIMELINE_MUTATION_INVALIDATION,
            )
            selection.clip_id = clip.id
            return result

        if action is TimelineAction.REMOVE_KEYFRAME:
            found = find_clip(document, intent.target_id)
            if found is None or not found[1].keyframes:
                return EMPTY_INVALIDATION
            clip = found[1]
            relative = max(0, intent.frame - clip.start_frame)
            local = min(
                clip.duration_frames,
                relative % clip.duration_frames if clip.loop_count > 1 else relative,
            )
            keyframe = min(clip.keyframes, key=lambda item: abs(item.frame - local))
            if abs(keyframe.frame - local) > intent.amount:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    "Move the playhead onto a keyframe before deleting it",
                )
            result = self._submit(
                session,
                RemoveKeyframeCommand(document, clip.id, keyframe.id),
                _TIMELINE_MUTATION_INVALIDATION,
            )
            selection.clip_id = clip.id
            return result

        if action is TimelineAction.SET_KEYFRAME_PROPERTIES:
            result = self._submit(
                session,
                SetKeyframePropertiesCommand(
                    document,
                    intent.target_id,
                    intent.related_id,
                    thaw_json_object(intent.values),
                ),
                _TIMELINE_MUTATION_INVALIDATION,
                coalesce=intent.coalesce,
                merge_key=(
                    "keyframe-properties",
                    intent.target_id,
                    intent.related_id,
                    tuple(sorted(intent.values)),
                ),
            )
            selection.clip_id = intent.target_id
            return result

        if action is TimelineAction.MOVE_CLIP:
            result = self._submit(
                session,
                MoveResizeClipCommand(document, intent.target_id, intent.frame, intent.amount),
                _TIMELINE_MUTATION_INVALIDATION,
                coalesce=intent.coalesce,
                merge_key=("clip-geometry", intent.target_id),
            )
            selection.clip_id = intent.target_id
            return result

        if action is TimelineAction.DUPLICATE_CLIP:
            found = find_clip(document, intent.target_id)
            if found is None:
                raise IntentRejectedError(IntentRejectionCode.TARGET_NOT_FOUND, "Clip not found")
            track, clip, index = found
            duplicate = clone_clip_with_new_ids(clip)
            duplicate.start_frame = clip.end_frame
            result = self._submit(
                session,
                AddClipCommand(
                    document,
                    track.id,
                    duplicate,
                    index=index + 1,
                    label=f"Duplicate {clip.name}",
                ),
                _TIMELINE_MUTATION_INVALIDATION,
            )
            selection.clip_id = duplicate.id
            return result

        if action is TimelineAction.REMOVE_CLIP:
            if find_clip(document, intent.target_id) is None:
                raise IntentRejectedError(IntentRejectionCode.TARGET_NOT_FOUND, "Clip not found")
            result = self._submit(
                session,
                RemoveClipCommand(document, intent.target_id, label="Delete timeline clip"),
                _TIMELINE_MUTATION_INVALIDATION,
            )
            selection.clip_id = None
            return result

        if action is TimelineAction.SELECT_CLIP:
            found = find_clip(document, intent.related_id)
            if found is None:
                raise IntentRejectedError(IntentRejectionCode.TARGET_NOT_FOUND, "Clip not found")
            selection.track_id = intent.target_id
            selection.clip_id = intent.related_id
            return _TIMELINE_SELECTION_INVALIDATION

        if action is TimelineAction.SET_CLIP_PROPERTIES:
            if find_clip(document, intent.target_id) is None:
                raise IntentRejectedError(IntentRejectionCode.TARGET_NOT_FOUND, "Clip not found")
            result = self._submit(
                session,
                SetClipPropertiesCommand(
                    document,
                    intent.target_id,
                    thaw_json_object(intent.values),
                    label="Edit timeline clip",
                ),
                _TIMELINE_MUTATION_INVALIDATION,
                coalesce=intent.coalesce,
                merge_key=("clip-properties", intent.target_id, tuple(sorted(intent.values))),
            )
            selection.clip_id = intent.target_id
            return result

        if action is TimelineAction.SET_ZOOM:
            value = intent.values.get("zoom")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise IntentRejectedError(IntentRejectionCode.INVALID_INTENT, "zoom must be numeric")
            session.editor_state.timeline.zoom = float(value)
            return InvalidationSet((InvalidationScope.TIMELINE,))

        raise IntentRejectedError(IntentRejectionCode.INVALID_INTENT, "Unsupported timeline action")

    @staticmethod
    def _require_pattern(session: ManagedDocument) -> PatternDocument:
        if not isinstance(session.document, PatternDocument):
            raise IntentRejectedError(
                IntentRejectionCode.INVALID_INTENT,
                "Intent requires an active Pattern document",
            )
        return session.document

    def _require_preset_resolver(self) -> PresetResolver:
        if self.preset_resolver is None:
            raise IntentRejectedError(
                IntentRejectionCode.INVALID_INTENT,
                "Pattern preset resolver is unavailable",
            )
        return self.preset_resolver

    def _dispatch_pattern(
        self,
        session: ManagedDocument,
        intent: PatternIntent,
    ) -> InvalidationSet:
        document = self._require_pattern(session)
        action = intent.action
        state = session.editor_state

        if action is PatternAction.SET_PROPERTIES:
            commands = [
                SetPatternPropertyCommand(
                    document,
                    path,
                    thaw_json(value),
                    label=f"Set {path}",
                )
                for path, value in intent.values.items()
            ]
            if not commands:
                return EMPTY_INVALIDATION
            command: Command = (
                commands[0]
                if len(commands) == 1
                else CompositeCommand(intent.target_id or "Edit Pattern", commands)
            )
            if len(commands) == 1 and intent.target_id:
                command.label = intent.target_id
            return self._submit(session, command, _PATTERN_MUTATION_INVALIDATION)

        if action is PatternAction.SET_MODE:
            mode = intent.target_id
            if mode not in {"preset", "recipe", "graph"}:
                raise IntentRejectedError(IntentRejectionCode.INVALID_INTENT, "Unknown pattern mode")
            state.pattern.preset_mode = mode == "preset"
            state.pattern.graph_mode = mode == "graph"
            if mode == "graph":
                state.pattern.authoring_level = "l3"
            else:
                state.selection.graph_node_id = None
                state.pattern.authoring_level = "l0" if mode == "preset" else "l1"
            return _PATTERN_VIEW_INVALIDATION

        if action is PatternAction.SET_LEVEL:
            level = authoring_level(intent.target_id)
            state.pattern.authoring_level = level.id
            state.pattern.preset_mode = level.id == "l0"
            state.pattern.graph_mode = level.id == "l3"
            if level.id == "l3" and document.graph is None:
                result = self._submit(
                    session,
                    ExpandToGraphCommand(document),
                    _PATTERN_MUTATION_INVALIDATION,
                )
                state.pattern.graph_mode = True
                return result
            return _PATTERN_VIEW_INVALIDATION

        if action is PatternAction.SET_BINDING:
            return self._submit(
                session,
                SetPatternBindingCommand(
                    document,
                    BindingSpec(
                        intent.target_id,
                        intent.related_id,
                        thaw_json(intent.value),
                    ),
                ),
                _PATTERN_MUTATION_INVALIDATION,
            )

        if action is PatternAction.REMOVE_BINDING:
            return self._submit(
                session,
                RemovePatternBindingCommand(document, intent.target_id),
                _PATTERN_MUTATION_INVALIDATION,
            )

        if action is PatternAction.SET_SOURCE_PATH:
            path = self.manager.project.resolve(intent.target_id, must_exist=True)
            state.pattern.runtime_source_path = str(path)
            return InvalidationSet((InvalidationScope.PATTERN,))

        if action is PatternAction.EXPAND_GRAPH:
            result = self._submit(
                session,
                ExpandToGraphCommand(document),
                _PATTERN_MUTATION_INVALIDATION,
            )
            state.pattern.graph_mode = True
            state.pattern.authoring_level = "l3"
            return result

        if action is PatternAction.FOLD_GRAPH:
            result = self._submit(
                session,
                FoldBackToRecipeCommand(document),
                _PATTERN_MUTATION_INVALIDATION,
            )
            state.pattern.graph_mode = False
            state.pattern.authoring_level = "l1"
            state.selection.graph_node_id = None
            return result

        if action is PatternAction.SELECT_GRAPH_NODE:
            if document.graph is None or not any(
                node.id == intent.target_id for node in document.graph.nodes
            ):
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"Graph node does not exist: {intent.target_id}",
                )
            state.selection.graph_node_id = intent.target_id
            # The live QGraphicsItem already owns visual selection.  Rebinding
            # the whole Pattern canvas here deletes that item during its mouse
            # press, so a drag can never reach mouse release.  Only the
            # Inspector depends on this view-state change.
            return _PATTERN_SELECTION_INVALIDATION

        if action is PatternAction.SET_GRAPH_NODE_PROPERTIES:
            return self._submit(
                session,
                SetGraphNodePropertiesCommand(
                    document,
                    intent.target_id,
                    thaw_json_object(intent.values),
                ),
                _PATTERN_MUTATION_INVALIDATION,
            )

        if action is PatternAction.MOVE_GRAPH_NODE:
            return self._submit(
                session,
                SetGraphNodePositionCommand(document, intent.target_id, intent.x, intent.y),
                _PATTERN_MUTATION_INVALIDATION,
                coalesce=True,
                merge_key=("graph-position", intent.target_id),
            )

        if action is PatternAction.ADD_GRAPH_NODE:
            return self._submit(
                session,
                AddGraphNodeCommand(
                    document,
                    intent.target_id,
                    intent.related_id,
                    label=f"Add {intent.target_id} node",
                ),
                _PATTERN_MUTATION_INVALIDATION,
            )

        if action is PatternAction.ADD_GRAPH_EDGE:
            return self._submit(
                session,
                AddGraphEdgeCommand(document, intent.target_id, intent.related_id),
                _PATTERN_MUTATION_INVALIDATION,
            )

        if action is PatternAction.REMOVE_GRAPH_NODE:
            return self._submit(
                session,
                RemoveGraphNodeCommand(document, intent.target_id),
                _PATTERN_MUTATION_INVALIDATION,
            )

        if action is PatternAction.REMOVE_GRAPH_EDGE:
            return self._submit(
                session,
                RemoveGraphEdgeCommand(document, intent.target_id),
                _PATTERN_MUTATION_INVALIDATION,
            )

        if action is PatternAction.APPLY_TEMPLATE:
            template = intent.target_id
            if "@" in template:
                resolver = self._require_preset_resolver()
                preset_id, version = template.rsplit("@", 1)
                descriptor = resolver.registry.resolve(preset_id, version)
                result = self._submit(
                    session,
                    ApplyPresetCommand(document, resolver, descriptor),
                    _PATTERN_MUTATION_INVALIDATION,
                )
                state.pattern.preset_mode = True
                state.pattern.graph_mode = False
                state.pattern.authoring_level = "l1"
                return result
            templates = {
                "starter_ring": {
                    "shape.kind": "ring", "shape.count": 24,
                    "aim.mode": "fixed", "aim.angle": 270.0,
                    "schedule.interval_frames": 12, "schedule.burst_count": 8,
                    "schedule.loop_count": None, "motion.speed": 2.0,
                    "motion.max_lifetime": 5.0,
                },
                "aimed_arc": {
                    "shape.kind": "arc", "shape.count": 12,
                    "shape.angle_span": 60.0, "aim.mode": "player",
                    "schedule.interval_frames": 24, "schedule.burst_count": 4,
                    "motion.speed": 2.5,
                },
                "spiral": {
                    "shape.kind": "spiral", "shape.count": 18,
                    "aim.mode": "fixed", "schedule.interval_frames": 8,
                    "schedule.burst_count": 24,
                    "modifiers.angle_offset_per_burst": 11.0,
                    "motion.speed": 2.0,
                },
            }
            values = templates.get(template)
            if values is None:
                raise IntentRejectedError(IntentRejectionCode.INVALID_INTENT, "Unknown template")
            commands = [
                SetPatternPropertyCommand(document, path, value, label=f"Set {path}")
                for path, value in values.items()
            ]
            return self._submit(
                session,
                CompositeCommand(f"Apply {template.replace('_', ' ')} template", commands),
                _PATTERN_MUTATION_INVALIDATION,
            )

        if action is PatternAction.SET_PRESET_PARAMETER:
            resolver = self._require_preset_resolver()
            result = self._submit(
                session,
                SetPresetOverrideCommand(
                    document,
                    resolver,
                    intent.target_id,
                    thaw_json(intent.value),
                ),
                _PATTERN_MUTATION_INVALIDATION,
            )
            state.pattern.preset_mode = True
            state.pattern.authoring_level = "l1"
            return result

        if action is PatternAction.SET_PRESET_SLOT:
            resolver = self._require_preset_resolver()
            result = self._submit(
                session,
                SetPresetSlotOverrideCommand(
                    document,
                    resolver,
                    intent.target_id,
                    thaw_json(intent.value),
                ),
                _PATTERN_MUTATION_INVALIDATION,
            )
            state.pattern.preset_mode = True
            state.pattern.authoring_level = "l1"
            return result

        if action is PatternAction.MIGRATE_PRESET:
            resolver = self._require_preset_resolver()
            instance = resolver.instance_from_document(document)
            if instance is None:
                return EMPTY_INVALIDATION
            preview = resolver.registry.preview_migration(instance, intent.target_id)
            result = self._submit(
                session,
                ApplyPresetMigrationCommand(document, resolver, preview),
                _PATTERN_MUTATION_INVALIDATION,
            )
            state.pattern.preset_mode = True
            state.pattern.authoring_level = "l1"
            return result

        if action is PatternAction.MATERIALIZE_PRESET:
            resolver = self._require_preset_resolver()
            result = self._submit(
                session,
                MaterializePresetCommand(document, resolver),
                _PATTERN_MUTATION_INVALIDATION,
            )
            state.pattern.preset_mode = False
            state.pattern.graph_mode = False
            state.pattern.authoring_level = "l1"
            return result

        if action is PatternAction.SET_PLAYER_POSITION:
            state.pattern.player_position = (intent.x, intent.y)
            return InvalidationSet((InvalidationScope.PATTERN,))

        raise IntentRejectedError(IntentRejectionCode.INVALID_INTENT, "Unsupported pattern action")

    @staticmethod
    def _require_ui(session: ManagedDocument) -> UIDocument:
        if not isinstance(session.document, UIDocument):
            raise IntentRejectedError(
                IntentRejectionCode.INVALID_INTENT,
                "Intent requires an active UI document",
            )
        return session.document

    @staticmethod
    def _find_ui_node(root: UIDocumentNode, node_id: str) -> UIDocumentNode | None:
        return next(
            (node for node, _depth in root.walk() if node.id == node_id),
            None,
        )

    def _dispatch_ui(
        self,
        session: ManagedDocument,
        intent: UIDocumentIntent,
    ) -> InvalidationSet:
        document = self._require_ui(session)
        action = intent.action

        if action is UIDocumentAction.SELECT_NODE:
            if self._find_ui_node(document.root, intent.target_id) is None:
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"UI node does not exist: {intent.target_id}",
                )
            session.editor_state.selection.ui_node_id = intent.target_id
            return InvalidationSet(
                (InvalidationScope.UI_CANVAS, InvalidationScope.INSPECTOR)
            )

        if action is UIDocumentAction.ADD_NODE:
            parent_id = intent.parent_id or document.root.id
            if self._find_ui_node(document.root, parent_id) is None:
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"UI parent does not exist: {parent_id}",
                )
            if intent.node_type not in {
                "text", "rect", "bar", "image", "panel",
                "container_h", "container_v", "container_grid",
            }:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    f"Unknown UI node type: {intent.node_type}",
                )
            node = UIDocumentNode(
                node_type=intent.node_type,
                name=intent.name or f"New {intent.node_type}",
                width=96.0,
                height=32.0,
            )
            if intent.node_type == "text":
                node.text = node.name
            elif intent.node_type == "image":
                node.width = 64.0
                node.height = 64.0
            result = self._submit(
                session,
                AddUINodeCommand(document, parent_id, node),
                _UI_MUTATION_INVALIDATION,
            )
            session.editor_state.selection.ui_node_id = node.id
            return result

        if action is UIDocumentAction.REMOVE_NODE:
            if intent.target_id == document.root.id:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    "UI root node cannot be removed",
                )
            if self._find_ui_node(document.root, intent.target_id) is None:
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"UI node does not exist: {intent.target_id}",
                )
            result = self._submit(
                session,
                RemoveUINodeCommand(document, intent.target_id),
                _UI_MUTATION_INVALIDATION,
            )
            session.editor_state.selection.ui_node_id = document.root.id
            return result

        if action is UIDocumentAction.SET_NODE_PROPERTIES:
            if self._find_ui_node(document.root, intent.target_id) is None:
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"UI node does not exist: {intent.target_id}",
                )
            return self._submit(
                session,
                SetUINodePropertyCommand(
                    document,
                    intent.target_id,
                    thaw_json_object(intent.values),
                ),
                _UI_MUTATION_INVALIDATION,
                coalesce=intent.coalesce,
                merge_key=("ui-properties", intent.target_id, tuple(sorted(intent.values))),
            )

        if action is UIDocumentAction.SET_VIEWPORT:
            if intent.width <= 0 or intent.height <= 0:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    "UI viewport dimensions must be positive",
                )
            session.editor_state.ui_viewport = (intent.width, intent.height)
            return InvalidationSet((InvalidationScope.UI_CANVAS,))

        raise IntentRejectedError(IntentRejectionCode.INVALID_INTENT, "Unsupported UI action")

    @staticmethod
    def _require_background(session: ManagedDocument) -> BackgroundDocument:
        if not isinstance(session.document, BackgroundDocument):
            raise IntentRejectedError(
                IntentRejectionCode.INVALID_INTENT,
                "Intent requires an active Background document",
            )
        return session.document

    def _dispatch_background(
        self,
        session: ManagedDocument,
        intent: BackgroundIntent,
    ) -> InvalidationSet:
        document = self._require_background(session)
        action = intent.action

        if action is BackgroundAction.SELECT_LAYER:
            layers = document.body.get("layers") or []
            if not isinstance(layers, list) or not 0 <= intent.index < len(layers):
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"Background layer does not exist: {intent.index}",
                )
            session.editor_state.background_selected_layer = intent.index
            return InvalidationSet(
                (InvalidationScope.BACKGROUND, InvalidationScope.INSPECTOR)
            )

        if action is BackgroundAction.SET_PROPERTY:
            return self._submit(
                session,
                SetBackgroundPropertyCommand(
                    document,
                    intent.target,
                    thaw_json(intent.value),
                ),
                _BACKGROUND_MUTATION_INVALIDATION,
                coalesce=intent.coalesce,
                merge_key=("background-property", intent.target),
            )

        if action is BackgroundAction.ADD_LAYER:
            textures = document.body.get("textures") or {}
            texture = next(iter(textures), None)
            layers = document.body.get("layers") or []
            layer = {
                "name": f"Layer {len(layers) + 1}",
                "texture": texture,
                "z_order": len(layers),
                "z_depth": 0.0,
                "blend_mode": "normal",
                "alpha": 1.0,
                "scroll_multiplier": 1.0,
                "tile": {"x_range": [-1, 1], "y_range": [-1, 1], "size": 1.0},
                "variants": [],
                "enabled": True,
                "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0},
            }
            return self._submit(
                session,
                AddBackgroundLayerCommand(document, layer),
                _BACKGROUND_MUTATION_INVALIDATION,
            )

        if action is BackgroundAction.REMOVE_LAYER:
            return self._submit(
                session,
                RemoveBackgroundLayerCommand(document, intent.index),
                _BACKGROUND_MUTATION_INVALIDATION,
            )

        if action is BackgroundAction.SET_BINDING:
            return self._submit(
                session,
                SetBackgroundBindingCommand(
                    document,
                    intent.target.strip(),
                    intent.expression.strip(),
                ),
                _BACKGROUND_MUTATION_INVALIDATION,
            )

        raise IntentRejectedError(
            IntentRejectionCode.INVALID_INTENT,
            "Unsupported background action",
        )

    @staticmethod
    def _mapping_collection(document: SceneDocument, state_id: str | None):
        if state_id:
            state = document.state_graph.find_state(state_id)
            if state is None:
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"State does not exist: {state_id}",
                )
            return state.output_mappings
        return document.output_mappings

    def _dispatch_authoring(
        self,
        session: ManagedDocument,
        intent: AuthoringIntent,
    ) -> InvalidationSet:
        document = self._require_scene(session)
        action = intent.action
        selection = session.editor_state.selection

        if action is AuthoringAction.SELECT_STATE:
            state = document.state_graph.find_state(intent.target_id)
            if state is None:
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"State does not exist: {intent.target_id}",
                )
            previous = selection.state_id
            playheads = session.editor_state.timeline.playheads_by_state
            if previous:
                playheads[previous] = intent.amount
            selection.state_id = state.id
            selection.track_id = None
            selection.clip_id = None
            session.editor_state.timeline.playhead_frame = playheads.get(state.id, 0)
            return _STATE_SELECTION_INVALIDATION

        if action is AuthoringAction.ADD_VARIABLE:
            scope = str(intent.values.get("scope") or "stage")
            variable = VariableSpec(
                name=str(intent.values.get("name") or "Variable"),
                type=str(intent.values.get("type") or "float"),
                default=thaw_json(intent.values.get("default")),
                scope=scope,
                writable_by=("timeline",) if scope == "state" else (),
                animatable=scope == "state",
            )
            state_id = (
                str(selection.state_id or document.state_graph.initial_state_id)
                if scope == "state"
                else None
            )
            return self._submit(
                session,
                AddVariableCommand(document, variable, state_id=state_id),
                _VARIABLE_MUTATION_INVALIDATION,
            )

        if action is AuthoringAction.REMOVE_VARIABLE:
            return self._submit(
                session,
                RemoveVariableCommand(document, intent.target_id),
                _VARIABLE_MUTATION_INVALIDATION,
            )

        if action is AuthoringAction.SET_VARIABLE:
            return self._submit(
                session,
                SetVariablePropertiesCommand(
                    document,
                    intent.target_id,
                    thaw_json_object(intent.values),
                ),
                _VARIABLE_MUTATION_INVALIDATION,
                coalesce=True,
                merge_key=("variable-properties", intent.target_id, tuple(sorted(intent.values))),
            )

        if action is AuthoringAction.SELECT_BINDING:
            selection.binding_id = intent.target_id or None
            selection.binding_candidate_ids = tuple(
                str(item.get("id") or "") for item in intent.items if item.get("id")
            )
            return InvalidationSet((InvalidationScope.VARIABLES, InvalidationScope.INSPECTOR))

        if action is AuthoringAction.SET_OUTPUT_MAPPINGS:
            state_id = intent.target_id or None
            existing = tuple(self._mapping_collection(document, state_id))
            requested = tuple(
                VariableOutputMapping.from_dict(thaw_json_object(item))
                for item in intent.items
            )
            old_by_id = {item.id: item for item in existing}
            new_by_id = {item.id: item for item in requested}
            commands: list[Command] = []
            for mapping_id in sorted(set(old_by_id).difference(new_by_id)):
                commands.append(RemoveOutputMappingCommand(document, mapping_id))
            for mapping_id in sorted(set(new_by_id).difference(old_by_id)):
                commands.append(
                    AddOutputMappingCommand(
                        document,
                        new_by_id[mapping_id],
                        state_id=state_id,
                    )
                )
            for mapping_id in sorted(set(old_by_id).intersection(new_by_id)):
                old = old_by_id[mapping_id]
                new = new_by_id[mapping_id]
                if old.to_dict() != new.to_dict():
                    commands.append(
                        SetOutputMappingPropertiesCommand(
                            document,
                            mapping_id,
                            {
                                "source": new.source.to_dict(),
                                "target": new.target.to_dict(),
                                "operation": new.operation,
                            },
                        )
                    )
            if not commands:
                return EMPTY_INVALIDATION
            return self._submit(
                session,
                CompositeCommand("Edit output mappings", commands),
                _VARIABLE_MUTATION_INVALIDATION,
            )

        if action is AuthoringAction.ADD_STATE:
            graph = document.state_graph.find_graph(intent.target_id)
            if graph is None:
                raise IntentRejectedError(IntentRejectionCode.TARGET_NOT_FOUND, "Graph not found")
            state = StateSpec(
                name=f"State {len(graph.states) + 1}",
                order=len(graph.states),
                duration_frames=60,
            )
            result = self._submit(
                session,
                AddStateCommand(document, graph.id, state),
                _STATE_GRAPH_MUTATION_INVALIDATION,
            )
            selection.state_id = state.id
            selection.track_id = None
            selection.clip_id = None
            return result

        if action is AuthoringAction.RENAME_STATE:
            result = self._submit(
                session,
                RenameStateCommand(document, intent.target_id, str(intent.values.get("name") or "")),
                _STATE_GRAPH_MUTATION_INVALIDATION,
                coalesce=True,
                merge_key=("state-name", intent.target_id),
            )
            selection.state_id = intent.target_id
            return result

        if action is AuthoringAction.DUPLICATE_STATE:
            command = DuplicateStateCommand(document, intent.target_id)
            result = self._submit(session, command, _STATE_GRAPH_MUTATION_INVALIDATION)
            if command.duplicated_state is not None:
                selection.state_id = command.duplicated_state.id
            selection.track_id = None
            selection.clip_id = None
            return result

        if action is AuthoringAction.REMOVE_STATE:
            graph = document.state_graph.graph_for_state(intent.target_id)
            if graph is None:
                raise IntentRejectedError(IntentRejectionCode.TARGET_NOT_FOUND, "State not found")
            result = self._submit(
                session,
                RemoveStateCommand(document, intent.target_id),
                _STATE_GRAPH_MUTATION_INVALIDATION,
            )
            selection.state_id = graph.initial_state_id
            selection.track_id = None
            selection.clip_id = None
            return result

        if action is AuthoringAction.MOVE_STATE:
            graph = document.state_graph.graph_for_state(intent.target_id)
            state = document.state_graph.find_state(intent.target_id)
            if graph is None or state is None:
                raise IntentRejectedError(IntentRejectionCode.TARGET_NOT_FOUND, "State not found")
            current = graph.states.index(state)
            target = max(0, min(current + intent.amount, len(graph.states) - 1))
            if target == current:
                return EMPTY_INVALIDATION
            result = self._submit(
                session,
                MoveStateCommand(document, intent.target_id, target),
                _STATE_GRAPH_MUTATION_INVALIDATION,
            )
            selection.state_id = intent.target_id
            return result

        if action is AuthoringAction.ADD_TRANSITION:
            target = document.state_graph.find_state(intent.related_id)
            if target is None:
                raise IntentRejectedError(IntentRejectionCode.TARGET_NOT_FOUND, "Target state not found")
            trigger = str(intent.values.get("trigger") or "after")
            after = intent.values.get("after_frames")
            transition = TransitionSpec(
                name=f"To {target.name}",
                target_state_id=target.id,
                trigger=trigger,
                after_frames=(int(after) if trigger == "after" and after is not None else None),
            )
            result = self._submit(
                session,
                AddTransitionCommand(document, intent.target_id, transition),
                _STATE_GRAPH_MUTATION_INVALIDATION,
            )
            selection.state_id = intent.target_id
            return result

        if action is AuthoringAction.SET_TRANSITION:
            return self._submit(
                session,
                SetTransitionPropertiesCommand(
                    document,
                    intent.target_id,
                    thaw_json_object(intent.values),
                ),
                _STATE_GRAPH_MUTATION_INVALIDATION,
                coalesce=True,
                merge_key=("transition-properties", intent.target_id, tuple(sorted(intent.values))),
            )

        if action is AuthoringAction.REMOVE_TRANSITION:
            return self._submit(
                session,
                RemoveTransitionCommand(document, intent.target_id),
                _STATE_GRAPH_MUTATION_INVALIDATION,
            )

        raise IntentRejectedError(IntentRejectionCode.INVALID_INTENT, "Unsupported authoring action")

    def dispatch(self, intent: EditorIntent) -> InvalidationSet:
        if not isinstance(intent, EditorIntent):
            raise IntentRejectedError(
                IntentRejectionCode.INVALID_INTENT,
                f"Unsupported editor intent: {type(intent).__name__}",
            )
        session = self._session_for(intent.document_id)

        if isinstance(intent, TimelineIntent):
            return self._dispatch_timeline(session, intent)

        if isinstance(intent, PatternIntent):
            return self._dispatch_pattern(session, intent)

        if isinstance(intent, UIDocumentIntent):
            return self._dispatch_ui(session, intent)

        if isinstance(intent, BackgroundIntent):
            return self._dispatch_background(session, intent)

        if isinstance(intent, AuthoringIntent):
            return self._dispatch_authoring(session, intent)

        if isinstance(intent, SetNodePropertyIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            property_value = thaw_json(intent.value)
            if node.properties.get(intent.property_name) == property_value:
                return EMPTY_INVALIDATION
            spec = next(
                (
                    item
                    for item in property_specs(node.type)
                    if item.key == intent.property_name
                ),
                None,
            )
            command_type = (
                AssignResourceCommand
                if spec is not None and spec.resource_types
                else SetNodePropertyCommand
            )
            label = (
                f"Assign {intent.property_name}"
                if command_type is AssignResourceCommand
                else f"Set {intent.property_name}"
            )
            command = command_type(
                document.root,
                intent.node_id,
                intent.property_name,
                property_value,
                label=label,
            )
            result = self._submit(session, command, _NODE_PROPERTY_INVALIDATION)
            session.editor_state.selection.node_id = intent.node_id
            return result

        if isinstance(intent, SetSceneNodePropertiesIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            values = {
                key: value
                for key, value in thaw_json_object(intent.properties).items()
                if node.properties.get(key) != value
            }
            if not values:
                return EMPTY_INVALIDATION
            result = self._submit(
                session,
                SetNodePropertiesCommand(
                    document.root,
                    intent.node_id,
                    values,
                    label=f"Edit {node.name}",
                ),
                _NODE_PROPERTY_INVALIDATION,
                coalesce=intent.coalesce,
                merge_key=("scene-properties", intent.node_id, tuple(sorted(values))),
            )
            session.editor_state.selection.node_id = intent.node_id
            return result

        if isinstance(intent, AddSceneNodeIntent):
            document = self._require_scene(session)
            parent = self._require_node(session, intent.parent_id)
            registry = session.node_registry
            spec = registry.get(intent.node_type) if registry is not None else None
            if spec is None:
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"Unknown node type: {intent.node_type}",
                )
            node = make_node(intent.node_type, name=intent.name)
            node.properties.update(thaw_json_object(intent.properties))
            if not registry.can_parent(parent.type, node.type):
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    f"{node.type} cannot be added under {parent.type}",
                )
            result = self._submit(
                session,
                AddNodeCommand(
                    document.root,
                    parent.id,
                    node,
                    label=f"Add {node.name}",
                ),
                _SCENE_STRUCTURE_INVALIDATION,
            )
            session.editor_state.selection.node_id = node.id
            return result

        if isinstance(intent, MoveSceneNodeIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            self._require_node(session, intent.parent_id)
            location = find_parent(document.root, node.id)
            if location is not None and location[0].id == intent.parent_id and location[1] == intent.index:
                return EMPTY_INVALIDATION
            result = self._submit(
                session,
                MoveNodeCommand(
                    document.root,
                    node.id,
                    intent.parent_id,
                    intent.index,
                    label=f"Move {node.name}",
                ),
                _SCENE_STRUCTURE_INVALIDATION,
            )
            session.editor_state.selection.node_id = node.id
            return result

        if isinstance(intent, RemoveSceneNodeIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            location = find_parent(document.root, node.id)
            if location is None:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    "The scene root cannot be deleted",
                )
            result = self._submit(
                session,
                RemoveNodeCommand(document.root, node.id, label=f"Delete {node.name}"),
                _SCENE_STRUCTURE_INVALIDATION,
            )
            session.editor_state.selection.node_id = location[0].id
            return result

        if isinstance(intent, RenameSceneNodeIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            if node.name == intent.name:
                return EMPTY_INVALIDATION
            result = self._submit(
                session,
                RenameNodeCommand(
                    document.root,
                    node.id,
                    intent.name,
                    label=f"Rename {node.name}",
                ),
                _SCENE_STRUCTURE_INVALIDATION,
            )
            session.editor_state.selection.node_id = node.id
            return result

        if isinstance(intent, CreateSimpleSpellIntent):
            document = self._require_scene(session)
            root = document.root
            stage = next((node for node in root.children if node.type == "Stage"), None)
            commands: list[Command] = []
            if stage is None:
                stage = make_node("Stage", name=intent.stage_name)
                commands.append(AddNodeCommand(root, root.id, stage))
            boss = make_node("Boss", name=intent.boss_name)
            spell = make_node("Spell", name=intent.spell_name)
            emitter = make_node("Emitter", name=intent.emitter_name)
            emitter.properties["y"] = 320.0
            instance = make_node("PatternInstance", name=intent.instance_name)
            commands.extend(
                (
                    AddNodeCommand(root, stage.id, boss),
                    AddNodeCommand(root, boss.id, spell),
                    AddNodeCommand(root, spell.id, emitter),
                    AddNodeCommand(root, emitter.id, instance),
                )
            )
            if intent.pattern_resource:
                commands.append(
                    AssignResourceCommand(
                        root,
                        instance.id,
                        "pattern",
                        intent.pattern_resource,
                        label="Assign Pattern resource",
                    )
                )
            result = self._submit(
                session,
                CompositeCommand("Create simple Spell", commands),
                _SCENE_STRUCTURE_INVALIDATION,
            )
            session.editor_state.selection.node_id = instance.id
            return result

        if isinstance(intent, CreateStageTemplateIntent):
            document = self._require_scene(session)
            command = ApplyStageTemplateCommand(
                document,
                intent.kind,
                intent.pattern_resource,
                intent.background_resource,
                audio_resource=intent.audio_resource,
                language=intent.language,
                label=(
                    "Create midstage skeleton"
                    if intent.kind == "midstage"
                    else "Create two-phase Boss skeleton"
                ),
            )
            result = self._submit(session, command, _SCENE_DOCUMENT_INVALIDATION)
            # A template is a task starting point, not a request to inspect the
            # technical SceneRoot.  Land on the authored Boss/enemy anchor so
            # the Inspector and beginner phase guide both have an actionable
            # target immediately after creation.
            author_target = next(
                (node for node in document.root.walk() if node.type == "Boss"),
                document.root,
            )
            session.editor_state.selection.node_id = author_target.id
            session.editor_state.selection.state_id = document.state_graph.initial_state_id
            return result

        if isinstance(intent, SelectNodeIntent):
            if session.node(intent.node_id) is None:
                raise IntentRejectedError(
                    IntentRejectionCode.TARGET_NOT_FOUND,
                    f"Scene node does not exist: {intent.node_id}",
                )
            session.editor_state.selection.node_id = intent.node_id
            session.editor_state.selection.clip_id = None
            return InvalidationSet(
                (
                    InvalidationScope.SCENE_TREE,
                    InvalidationScope.SCENE_CANVAS,
                    InvalidationScope.INSPECTOR,
                )
            )

        if isinstance(intent, SetTimelinePlayheadIntent):
            session.editor_state.timeline.playhead_frame = intent.frame
            return InvalidationSet((InvalidationScope.TIMELINE,))

        if isinstance(intent, UndoIntent):
            self._last_merge_key[intent.document_id] = None
            history = self._undo_invalidations[intent.document_id]
            if not session.commands.can_undo:
                return EMPTY_INVALIDATION
            if not history:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    "Undo history contains a mutation that bypassed EditorCoordinator",
                )
            if not session.undo():
                return EMPTY_INVALIDATION
            invalidation = history.pop()
            self._redo_invalidations[intent.document_id].append(invalidation)
            return invalidation

        if isinstance(intent, RedoIntent):
            self._last_merge_key[intent.document_id] = None
            history = self._redo_invalidations[intent.document_id]
            if not session.commands.can_redo:
                return EMPTY_INVALIDATION
            if not history:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    "Redo history contains a mutation that bypassed EditorCoordinator",
                )
            if not session.redo():
                return EMPTY_INVALIDATION
            invalidation = history.pop()
            self._undo_invalidations[intent.document_id].append(invalidation)
            return invalidation

        raise IntentRejectedError(
            IntentRejectionCode.INVALID_INTENT,
            f"Unsupported editor intent: {type(intent).__name__}",
        )

    def route_overlay(self, document_id: str) -> InvalidationSet:
        self._session_for(document_id)
        return InvalidationSet((InvalidationScope.OVERLAY,))


__all__ = ["EditorCoordinator"]
