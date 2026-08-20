"""Non-visual state manager for one scene editor document."""

from __future__ import annotations

from pathlib import Path

from .commands import Command, CommandStack
from .document import EditorNode, SceneDocument
from .node_types import make_default_root
from .storage import DocumentStore


class SceneEditorSession:
    def __init__(self, store: DocumentStore):
        self.store = store
        self.document = self.new_document()
        self.path: Path | None = None
        self.commands = CommandStack()
        self._saved_payload = self.document.to_dict()

    @staticmethod
    def new_document(name: str = "Untitled Scene") -> SceneDocument:
        return SceneDocument(
            name=name,
            root=make_default_root(name),
            metadata={"preview_stage": "stage1"},
        )

    @property
    def is_dirty(self) -> bool:
        return self.document.to_dict() != self._saved_payload

    def replace(self, document: SceneDocument, path: str | Path | None = None) -> None:
        self.document = document
        self.path = Path(path).resolve() if path is not None else None
        self.commands.clear()
        self._saved_payload = document.to_dict()

    def reset(self, name: str = "Untitled Scene") -> None:
        self.replace(self.new_document(name))

    def open(self, path: str | Path) -> SceneDocument:
        document = self.store.load(path)
        self.replace(document, self.store.project.resolve(path))
        return document

    def save(self, path: str | Path | None = None) -> Path:
        target = path if path is not None else self.path
        if target is None:
            raise ValueError("A path is required when saving a new scene")
        saved = self.store.save(self.document, target)
        self.path = saved
        self._saved_payload = self.document.to_dict()
        return saved

    def apply(self, command: Command) -> None:
        self.commands.push(command, validate=self.document.validate)

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

    def node(self, node_id: str) -> EditorNode | None:
        return next(
            (node for node in self.document.root.walk() if node.id == node_id),
            None,
        )
