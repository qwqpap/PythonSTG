"""Qt-free edit coordination over the active managed authoring document."""

from __future__ import annotations

from collections import defaultdict

from src.editor.commands import Command, CompositeCommand
from src.editor.document import SceneDocument
from src.editor.document_manager import DocumentManager, ManagedDocument
from src.editor.node_types import make_node, property_specs
from src.editor.scene_commands import (
    AddNodeCommand,
    AssignResourceCommand,
    MoveNodeCommand,
    RemoveNodeCommand,
    RenameNodeCommand,
    SetNodePropertiesCommand,
    SetNodePropertyCommand,
    find_parent,
)
from src.editor.stage_templates import ApplyStageTemplateCommand

from .errors import IntentRejectedError, IntentRejectionCode
from .intents import (
    AddSceneNodeIntent,
    CreateSimpleSpellIntent,
    CreateStageTemplateIntent,
    EditorIntent,
    MoveSceneNodeIntent,
    RedoIntent,
    RemoveSceneNodeIntent,
    RenameSceneNodeIntent,
    SelectNodeIntent,
    SetNodePropertyIntent,
    SetSceneNodePropertiesIntent,
    SetTimelinePlayheadIntent,
    UndoIntent,
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


class EditorCoordinator:
    """Validate intents, submit Commands, update transient state, return damage."""

    def __init__(self, manager: DocumentManager):
        self.manager = manager
        self._undo_invalidations: dict[str, list[InvalidationSet]] = defaultdict(list)
        self._redo_invalidations: dict[str, list[InvalidationSet]] = defaultdict(list)
        self._last_merge_key: dict[str, tuple[object, ...] | None] = {}

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

    def dispatch(self, intent: EditorIntent) -> InvalidationSet:
        if not isinstance(intent, EditorIntent):
            raise IntentRejectedError(
                IntentRejectionCode.INVALID_INTENT,
                f"Unsupported editor intent: {type(intent).__name__}",
            )
        session = self._session_for(intent.document_id)

        if isinstance(intent, SetNodePropertyIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            if node.properties.get(intent.property_name) == intent.value:
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
                intent.value,
                label=label,
            )
            session.editor_state.selection.node_id = intent.node_id
            return self._submit(session, command, _NODE_PROPERTY_INVALIDATION)

        if isinstance(intent, SetSceneNodePropertiesIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            values = {
                key: value
                for key, value in intent.properties.items()
                if node.properties.get(key) != value
            }
            if not values:
                return EMPTY_INVALIDATION
            session.editor_state.selection.node_id = intent.node_id
            return self._submit(
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
            node.properties.update(intent.properties)
            if not registry.can_parent(parent.type, node.type):
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    f"{node.type} cannot be added under {parent.type}",
                )
            session.editor_state.selection.node_id = node.id
            return self._submit(
                session,
                AddNodeCommand(
                    document.root,
                    parent.id,
                    node,
                    label=f"Add {node.name}",
                ),
                _SCENE_STRUCTURE_INVALIDATION,
            )

        if isinstance(intent, MoveSceneNodeIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            self._require_node(session, intent.parent_id)
            location = find_parent(document.root, node.id)
            if location is not None and location[0].id == intent.parent_id and location[1] == intent.index:
                return EMPTY_INVALIDATION
            session.editor_state.selection.node_id = node.id
            return self._submit(
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

        if isinstance(intent, RemoveSceneNodeIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            location = find_parent(document.root, node.id)
            if location is None:
                raise IntentRejectedError(
                    IntentRejectionCode.INVALID_INTENT,
                    "The scene root cannot be deleted",
                )
            session.editor_state.selection.node_id = location[0].id
            return self._submit(
                session,
                RemoveNodeCommand(document.root, node.id, label=f"Delete {node.name}"),
                _SCENE_STRUCTURE_INVALIDATION,
            )

        if isinstance(intent, RenameSceneNodeIntent):
            document = self._require_scene(session)
            node = self._require_node(session, intent.node_id)
            if node.name == intent.name:
                return EMPTY_INVALIDATION
            session.editor_state.selection.node_id = node.id
            return self._submit(
                session,
                RenameNodeCommand(
                    document.root,
                    node.id,
                    intent.name,
                    label=f"Rename {node.name}",
                ),
                _SCENE_STRUCTURE_INVALIDATION,
            )

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
            session.editor_state.selection.node_id = instance.id
            return self._submit(
                session,
                CompositeCommand("Create simple Spell", commands),
                _SCENE_STRUCTURE_INVALIDATION,
            )

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
            session.editor_state.selection.node_id = document.root.id
            session.editor_state.selection.state_id = document.state_graph.initial_state_id
            return self._submit(session, command, _SCENE_DOCUMENT_INVALIDATION)

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
            if not session.undo():
                return EMPTY_INVALIDATION
            history = self._undo_invalidations[intent.document_id]
            invalidation = history.pop() if history else _NODE_PROPERTY_INVALIDATION
            self._redo_invalidations[intent.document_id].append(invalidation)
            return invalidation

        if isinstance(intent, RedoIntent):
            self._last_merge_key[intent.document_id] = None
            if not session.redo():
                return EMPTY_INVALIDATION
            history = self._redo_invalidations[intent.document_id]
            invalidation = history.pop() if history else _NODE_PROPERTY_INVALIDATION
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
