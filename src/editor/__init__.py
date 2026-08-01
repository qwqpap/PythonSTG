"""Editor-facing document, storage, and command APIs."""

from .commands import Command, CommandStack, CompositeCommand
from .document import (
    CURRENT_SCHEMA_VERSION,
    DocumentError,
    EditorNode,
    SceneDocument,
    TimelineEvent,
)
from .storage import DocumentStore
from .node_types import (
    NODE_TYPES,
    NODE_TYPE_REGISTRY,
    NodeTypeRegistry,
    NodeTypeSpec,
    PropertySpec,
    ViewportSpec,
    make_default_root,
    make_node,
)
from .scene_commands import (
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
from .pattern_commands import (
    AddTimelineEventCommand,
    PatternMutationError,
    SetPatternPropertyCommand,
    SetTimelineEventPropertyCommand,
    pattern_with_property,
)
from .document_manager import (
    DocumentManager,
    DocumentManagerError,
    ManagedDocument,
    UnsavedDocumentError,
)
from .scene_compile import (
    SceneCompileDiagnostic,
    SceneSpellCompileError,
    SceneSpellPreview,
    compile_simple_spell,
)
from .session import SceneEditorSession

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "Command",
    "CommandStack",
    "CompositeCommand",
    "DocumentError",
    "DocumentStore",
    "EditorNode",
    "SceneDocument",
    "TimelineEvent",
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
    "AddTimelineEventCommand",
    "PatternMutationError",
    "SetPatternPropertyCommand",
    "SetTimelineEventPropertyCommand",
    "pattern_with_property",
    "DocumentManager",
    "DocumentManagerError",
    "ManagedDocument",
    "UnsavedDocumentError",
    "SceneCompileDiagnostic",
    "SceneSpellCompileError",
    "SceneSpellPreview",
    "compile_simple_spell",
]
