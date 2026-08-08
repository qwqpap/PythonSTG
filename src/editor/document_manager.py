"""Multi-document ownership, savepoints, and per-document editor state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from src.authoring import ResourceStore
from src.authoring.resources import (
    BACKGROUND_RESOURCE_TYPE,
    PATTERN_RESOURCE_TYPE,
    SCENE_RESOURCE_TYPE,
    UI_RESOURCE_TYPE,
)
from src.core.project_context import ProjectContext
from src.pattern import PatternDocument

from .commands import Command, CommandStack
from .document import EditorNode, SceneDocument
from .session import SceneEditorSession


SUPPORTED_DOCUMENT_TYPES = (
    SCENE_RESOURCE_TYPE,
    PATTERN_RESOURCE_TYPE,
    UI_RESOURCE_TYPE,
    BACKGROUND_RESOURCE_TYPE,
)

class DocumentManagerError(ValueError):
    """Raised when a document lifecycle operation cannot be completed."""


class UnsavedDocumentError(DocumentManagerError):
    """Raised when closing a dirty document without an explicit decision."""


def _clone_document(document: Any) -> Any:
    loader = getattr(type(document), "from_dict", None)
    if not callable(loader):
        raise DocumentManagerError(
            f"Document type {type(document).__name__} cannot be cloned"
        )
    return loader(deepcopy(document.to_dict()))


@dataclass
class ManagedDocument:
    store: ResourceStore
    document: SceneDocument | PatternDocument
    path: Path | None = None
    node_registry: Any | None = field(default=None, repr=False)
    commands: CommandStack = field(default_factory=CommandStack)
    selected_id: str | None = None
    selected_resource: str | None = None
    editor_context: dict[str, Any] = field(default_factory=dict)
    _saved_payload: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.document.type not in SUPPORTED_DOCUMENT_TYPES:
            raise DocumentManagerError(
                f"No M3 editor context for resource type {self.document.type!r}"
            )
        if self.path is not None:
            self.path = self.store.project.resolve(self.path)
        if self.selected_id is None:
            self.selected_id = self.default_selection
        self._saved_payload = deepcopy(self.document.to_dict())

    @property
    def default_selection(self) -> str:
        if isinstance(self.document, SceneDocument):
            return self.document.root.id
        return self.document.id

    @property
    def is_dirty(self) -> bool:
        return self.document.to_dict() != self._saved_payload

    @property
    def display_name(self) -> str:
        return self.path.name if self.path is not None else self.document.name

    @property
    def resource_uri(self) -> str | None:
        if self.path is None:
            return None
        return f"res://{self.store.project.relative(self.path).as_posix()}"

    def node(self, node_id: str | None) -> EditorNode | None:
        if not isinstance(self.document, SceneDocument) or node_id is None:
            return None
        return next((node for node in self.document.root.walk() if node.id == node_id), None)

    def replace(
        self,
        document: SceneDocument | PatternDocument,
        path: str | Path | None = None,
    ) -> None:
        if document.type not in SUPPORTED_DOCUMENT_TYPES:
            raise DocumentManagerError(f"Unsupported document type: {document.type!r}")
        self.document = document
        self.path = self.store.project.resolve(path) if path is not None else None
        self.commands.clear()
        self._saved_payload = deepcopy(document.to_dict())
        self.selected_id = self.default_selection
        self.selected_resource = None
        self.editor_context.clear()

    def reset(self, name: str | None = None) -> None:
        """Backward-compatible reset for integrations that held one session."""

        if isinstance(self.document, SceneDocument):
            replacement = SceneEditorSession.new_document(name or "Untitled Scene")
        else:
            replacement = PatternDocument.new(name or "New Pattern")
        self.replace(replacement)

    def apply(self, command: Command, *, coalesce: bool = False) -> None:
        self.commands.push(command, coalesce=coalesce, validate=self._validate)

    def _validate(self) -> None:
        self.document.validate()
        if isinstance(self.document, SceneDocument):
            registry = self.node_registry
            if registry is None:
                from .node_types import NODE_TYPE_REGISTRY

                registry = NODE_TYPE_REGISTRY
            registry.validate_tree(self.document.root)

    def undo(self) -> bool:
        changed = self.commands.undo()
        if changed:
            self.document.validate()
        return changed

    def redo(self) -> bool:
        changed = self.commands.redo()
        if changed:
            self.document.validate()
        return changed

    def save(self, path: str | Path | None = None) -> Path:
        target = path if path is not None else self.path
        if target is None:
            raise DocumentManagerError("A path is required when saving a new document")
        saved = self.store.save(self.document, target)
        self.path = saved.resolve()
        self._saved_payload = deepcopy(self.document.to_dict())
        return self.path

    def revert(self) -> None:
        if self.path is not None:
            replacement = self.store.load(self.path)
        else:
            replacement = _clone_document_from_payload(self.document, self._saved_payload)
        if replacement.type != self.document.type:
            raise DocumentManagerError("Reverted resource changed document type")
        self.document = replacement
        self.commands.clear()
        self._saved_payload = deepcopy(replacement.to_dict())
        if self.node(self.selected_id) is None:
            self.selected_id = self.default_selection


def _clone_document_from_payload(document: Any, payload: dict[str, Any]) -> Any:
    loader = getattr(type(document), "from_dict", None)
    if not callable(loader):
        raise DocumentManagerError("Document does not provide from_dict")
    return loader(deepcopy(payload))


class DocumentManager:
    def __init__(
        self,
        project: ProjectContext,
        *,
        create_initial_scene: bool = True,
        registry: Any | None = None,
        node_registry: Any | None = None,
    ):
        self.project = project
        self.store = ResourceStore(project, registry=registry)
        self.node_registry = node_registry
        self._documents: list[ManagedDocument] = []
        self._active_index = -1
        if create_initial_scene:
            self.new_scene()

    def __iter__(self) -> Iterator[ManagedDocument]:
        return iter(self._documents)

    def __len__(self) -> int:
        return len(self._documents)

    @property
    def documents(self) -> tuple[ManagedDocument, ...]:
        return tuple(self._documents)

    @property
    def active_index(self) -> int:
        return self._active_index

    @property
    def active(self) -> ManagedDocument | None:
        if 0 <= self._active_index < len(self._documents):
            return self._documents[self._active_index]
        return None

    def activate(self, target: int | ManagedDocument) -> ManagedDocument:
        index = target if isinstance(target, int) else self._documents.index(target)
        if not 0 <= index < len(self._documents):
            raise IndexError("document index out of range")
        self._active_index = index
        return self._documents[index]

    def add(
        self,
        document: SceneDocument | PatternDocument,
        path: str | Path | None = None,
    ) -> ManagedDocument:
        session = ManagedDocument(
            self.store,
            document,
            Path(path) if path else None,
            node_registry=self.node_registry,
        )
        self._documents.append(session)
        self._active_index = len(self._documents) - 1
        return session

    def new_scene(self, name: str = "Untitled Scene") -> ManagedDocument:
        return self.add(SceneEditorSession.new_document(name))

    def new_pattern(self, name: str = "New Pattern") -> ManagedDocument:
        return self.add(PatternDocument.new(name))

    def find_path(self, path: str | Path) -> ManagedDocument | None:
        resolved = self.project.resolve(path)
        key = str(resolved).casefold()
        return next(
            (
                session
                for session in self._documents
                if session.path is not None and str(session.path).casefold() == key
            ),
            None,
        )

    def open(self, path: str | Path) -> ManagedDocument:
        existing = self.find_path(path)
        if existing is not None:
            return self.activate(existing)
        resolved = self.project.resolve(path)
        document = self.store.load(resolved)
        from src.game.background_render.document import BackgroundDocument
        from src.ui.document import UIDocument

        if not isinstance(
            document,
            (SceneDocument, PatternDocument, UIDocument, BackgroundDocument),
        ):
            raise DocumentManagerError(
                f"No editor context for {getattr(document, 'type', type(document).__name__)!r}"
            )
        return self.add(document, resolved)

    def close(self, target: int | ManagedDocument, *, discard: bool = False) -> ManagedDocument:
        index = target if isinstance(target, int) else self._documents.index(target)
        session = self._documents[index]
        if session.is_dirty and not discard:
            raise UnsavedDocumentError(f"Document has unsaved changes: {session.display_name}")
        removed = self._documents.pop(index)
        if not self._documents:
            self._active_index = -1
        elif self._active_index > index:
            self._active_index -= 1
        elif self._active_index >= len(self._documents):
            self._active_index = len(self._documents) - 1
        return removed

    def save(self, target: ManagedDocument | None = None, path: str | Path | None = None) -> Path:
        session = target or self.active
        if session is None:
            raise DocumentManagerError("No active document")
        if path is not None:
            collision = self.find_path(path)
            if collision is not None and collision is not session:
                raise DocumentManagerError(
                    f"Resource is already open in another tab: {collision.display_name}"
                )
        return session.save(path)

    def revert(self, target: ManagedDocument | None = None) -> None:
        session = target or self.active
        if session is None:
            raise DocumentManagerError("No active document")
        session.revert()
