"""Undoable adapters around the headless authoring model operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.authoring.program import set_argument, set_unit_field
from src.qt_compat.QtGui import QUndoCommand

if TYPE_CHECKING:
    from .session import EditorSession


class SetNodeArgumentCommand(QUndoCommand):
    """Replace one node argument as a single reversible model mutation."""

    def __init__(
        self,
        session: "EditorSession",
        uid: str,
        name: str,
        value: Any,
    ) -> None:
        super().__init__(f"修改 {name}")
        self._session = session
        self._before = session.program.clone()
        self._after = set_argument(self._before, uid, name, value)

    def redo(self) -> None:
        self._session._apply_program(self._after)

    def undo(self) -> None:
        self._session._apply_program(self._before)


class SetUnitFieldCommand(QUndoCommand):
    """Replace one logical-unit field as a reversible model mutation."""

    def __init__(
        self,
        session: "EditorSession",
        unit_id: str,
        name: str,
        value: Any,
    ) -> None:
        super().__init__(f"修改 {name}")
        self._session = session
        self._before = session.program.clone()
        self._after = set_unit_field(self._before, unit_id, name, value)

    def redo(self) -> None:
        self._session._apply_program(self._after)

    def undo(self) -> None:
        self._session._apply_program(self._before)


__all__ = ["SetNodeArgumentCommand", "SetUnitFieldCommand"]
