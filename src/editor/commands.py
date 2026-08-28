"""Undoable adapters around the headless authoring model operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.authoring.program import (
    AuthoringProgram,
    DropPlacement,
    Node,
    ProgramError,
    find_node,
    insert_node,
    move_node,
    set_argument,
    set_unit_field,
)
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


class MoveNodeCommand(QUndoCommand):
    """Apply exactly one Before/After/Child/Wrap move."""

    def __init__(
        self,
        session: "EditorSession",
        uid: str,
        target_uid: str,
        placement: DropPlacement | str,
        *,
        target_slot: str | None = None,
    ) -> None:
        placement = DropPlacement(placement)
        super().__init__(f"移动节点：{placement.value}")
        self._session = session
        self._before = session.program.clone()
        self._after = move_node(
            self._before,
            uid,
            target_uid,
            placement,
            target_slot=target_slot,
        )

    def redo(self) -> None:
        self._session._apply_program(self._after)

    def undo(self) -> None:
        self._session._apply_program(self._before)


class InsertNodeCommand(QUndoCommand):
    """Insert one new node relative to an existing visible node."""

    def __init__(
        self,
        session: "EditorSession",
        target_uid: str,
        placement: DropPlacement | str,
        node: Node,
    ) -> None:
        placement = DropPlacement(placement)
        super().__init__(f"插入 {node.kind}")
        self._session = session
        self._before = session.program.clone()
        self._after = _insert_relative(self._before, target_uid, placement, node)

    def redo(self) -> None:
        self._session._apply_program(self._after)

    def undo(self) -> None:
        self._session._apply_program(self._before)


def _insert_relative(
    program: AuthoringProgram,
    target_uid: str,
    placement: DropPlacement,
    node: Node,
) -> AuthoringProgram:
    unit, target, location = find_node(program, target_uid)
    if placement in {DropPlacement.BEFORE, DropPlacement.AFTER}:
        offset = 0 if placement == DropPlacement.BEFORE else 1
        return insert_node(
            program,
            unit.id,
            location.parent_uid,
            location.slot,
            location.index + offset,
            node,
        )
    if placement == DropPlacement.CHILD:
        slots = tuple(target.children)
        if not slots:
            raise ProgramError("invalid_insert", f"{target.kind} does not accept child nodes")
        slot = "body" if "body" in slots else slots[0]
        return insert_node(program, unit.id, target.uid, slot, len(target.children[slot]), node)
    raise ProgramError("invalid_insert", "new resource actions cannot implicitly wrap code")


__all__ = [
    "InsertNodeCommand",
    "MoveNodeCommand",
    "SetNodeArgumentCommand",
    "SetUnitFieldCommand",
]
