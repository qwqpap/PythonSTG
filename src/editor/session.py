"""Compatibility factory for seeding a blank scene document.

ER7 collapsed the second ``open``/``save``/Undo lifecycle this module used to
own into :class:`~src.editor.document_manager.ManagedDocument`, the single owner
of a document's :class:`CommandStack` and savepoints.  The only surviving member
is the ``new_document`` factory that :class:`DocumentManager` (and a handful of
legacy tests) call to build a fresh :class:`SceneDocument`.
"""

from __future__ import annotations

from src.authoring.scene.document import SceneDocument
from src.authoring.scene.node_types import make_default_root


class SceneEditorSession:
    """Legacy namespace retained solely for the ``new_document`` factory.

    The instance lifecycle (``open``/``save``/``apply``/``undo``/``redo``/
    ``replace``) this class used to provide is gone; :class:`ManagedDocument`
    owns it now.  Constructing an instance is intentionally unsupported.
    """

    @staticmethod
    def new_document(name: str = "Untitled Scene") -> SceneDocument:
        return SceneDocument(
            name=name,
            root=make_default_root(name),
            metadata={"preview_stage": "stage1"},
        )
