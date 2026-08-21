"""Editor-facing document, storage, and command APIs."""

from src.authoring.commands.base import Command, CommandStack, CompositeCommand
from src.authoring.scene.document import (
    CURRENT_SCHEMA_VERSION,
    MAX_STATE_GRAPH_DEPTH,
    DocumentError,
    EditorNode,
    SceneDocument,
    StateActionSpec,
    StateGraphSpec,
    StateGraphValidationError,
    StateSpec,
    TimelineClip,
    TimelineEvent,
    TimelineKeyframe,
    TimelineTrack,
    TransitionSpec,
)
from .storage import DocumentStore
from src.authoring.scene.node_types import (
    NODE_TYPES,
    NODE_TYPE_REGISTRY,
    NodeTypeRegistry,
    NodeTypeSpec,
    PropertySpec,
    ViewportSpec,
    make_default_root,
    make_node,
)
from src.authoring.commands.scene import (
    AddNodeCommand,
    AssignResourceCommand,
    MoveNodeCommand,
    RemoveNodeCommand,
    RenameNodeCommand,
    SceneMutationError,
    SetNodePropertiesCommand,
    SetNodePropertyCommand,
    find_node,
    find_parent,
)
from src.authoring.commands.pattern import (
    PatternMutationError,
    SetPatternPropertyCommand,
    pattern_with_property,
)
from .document_manager import (
    DocumentManager,
    DocumentManagerError,
    ManagedDocument,
    UnsavedDocumentError,
)
from src.compiler.scene_spell import (
    SceneCompileDiagnostic,
    SceneSpellCompileError,
    SceneSpellPreview,
    compile_simple_spell,
)
from src.authoring.commands.timeline import (
    AddClipCommand,
    AddKeyframeCommand,
    AddTrackCommand,
    MoveTrackCommand,
    MoveResizeClipCommand,
    RemoveClipCommand,
    RemoveKeyframeCommand,
    RemoveTrackCommand,
    SetClipPropertiesCommand,
    SetKeyframePropertiesCommand,
    SetTrackPropertiesCommand,
    TimelineMutationError,
    clone_clip_with_new_ids,
    find_clip,
    find_track,
    timeline_tracks,
)
from .session import SceneEditorSession
from src.authoring.commands.variables import (
    AddOutputMappingCommand,
    AddVariableCommand,
    RemoveOutputMappingCommand,
    RemoveVariableCommand,
    SetOutputMappingPropertiesCommand,
    SetVariablePropertiesCommand,
    VariableMutationError,
    compatible_variable_bindings,
    find_mapping,
    find_variable,
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
    StateGraphMutationError,
    clone_state_with_new_ids,
    find_graph,
    find_state as find_graph_state,
    find_transition,
    graph_for_state,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "MAX_STATE_GRAPH_DEPTH",
    "Command",
    "CommandStack",
    "CompositeCommand",
    "DocumentError",
    "DocumentStore",
    "EditorNode",
    "SceneDocument",
    "StateActionSpec",
    "StateGraphSpec",
    "StateGraphValidationError",
    "StateSpec",
    "TimelineClip",
    "TimelineEvent",
    "TimelineKeyframe",
    "TimelineTrack",
    "TransitionSpec",
    "NODE_TYPES",
    "NODE_TYPE_REGISTRY",
    "NodeTypeRegistry",
    "NodeTypeSpec",
    "PropertySpec",
    "ViewportSpec",
    "make_default_root",
    "make_node",
    "AddNodeCommand",
    "AssignResourceCommand",
    "MoveNodeCommand",
    "RemoveNodeCommand",
    "RenameNodeCommand",
    "SceneMutationError",
    "SetNodePropertiesCommand",
    "SetNodePropertyCommand",
    "find_node",
    "find_parent",
    "SceneEditorSession",
    "AddOutputMappingCommand",
    "AddVariableCommand",
    "RemoveOutputMappingCommand",
    "RemoveVariableCommand",
    "SetOutputMappingPropertiesCommand",
    "SetVariablePropertiesCommand",
    "VariableMutationError",
    "compatible_variable_bindings",
    "find_mapping",
    "find_variable",
    "PatternMutationError",
    "SetPatternPropertyCommand",
    "pattern_with_property",
    "DocumentManager",
    "DocumentManagerError",
    "ManagedDocument",
    "UnsavedDocumentError",
    "SceneCompileDiagnostic",
    "SceneSpellCompileError",
    "SceneSpellPreview",
    "compile_simple_spell",
    "AddClipCommand",
    "AddKeyframeCommand",
    "AddTrackCommand",
    "MoveTrackCommand",
    "MoveResizeClipCommand",
    "RemoveClipCommand",
    "RemoveKeyframeCommand",
    "RemoveTrackCommand",
    "SetClipPropertiesCommand",
    "SetKeyframePropertiesCommand",
    "SetTrackPropertiesCommand",
    "TimelineMutationError",
    "clone_clip_with_new_ids",
    "find_clip",
    "find_track",
    "timeline_tracks",
    "AddStateCommand",
    "AddTransitionCommand",
    "DuplicateStateCommand",
    "MoveStateCommand",
    "RemoveStateCommand",
    "RemoveTransitionCommand",
    "RenameStateCommand",
    "SetTransitionPropertiesCommand",
    "StateGraphMutationError",
    "clone_state_with_new_ids",
    "find_graph",
    "find_graph_state",
    "find_transition",
    "graph_for_state",
]


# Contribution inversion (EDITOR_ARCHITECTURE.md §6/§8): install this editor's Qt
# workspaces into the headless authoring registry's editor-factory slots.  The
# factories import Qt lazily, so importing ``src.editor`` stays Qt-free; only
# actually building a workspace pulls in :mod:`src.editor.panels.ui_workspace`.
from src.authoring.registry import register_editor_factory as _register_editor_factory
from src.authoring.resources import (
    BACKGROUND_RESOURCE_TYPE as _BACKGROUND_RESOURCE_TYPE,
    UI_RESOURCE_TYPE as _UI_RESOURCE_TYPE,
)


def _make_ui_workspace(*args, **kwargs):
    from src.editor.panels.ui_workspace import UIWorkspace

    return UIWorkspace(*args, **kwargs)


def _make_background_workspace(*args, **kwargs):
    from src.editor.panels.ui_workspace import BackgroundWorkspace

    return BackgroundWorkspace(*args, **kwargs)


_register_editor_factory(_UI_RESOURCE_TYPE, _make_ui_workspace)
_register_editor_factory(_BACKGROUND_RESOURCE_TYPE, _make_background_workspace)
