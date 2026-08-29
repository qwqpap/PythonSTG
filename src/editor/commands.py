"""Undoable adapters around the headless authoring model operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from src.authoring.program import (
    AuthoringProgram,
    DropPlacement,
    Node,
    ProgramError,
    delete_node,
    find_node,
    insert_node,
    move_node,
    set_argument,
    set_unit_field,
)
from src.qt_compat.QtGui import QUndoCommand

if TYPE_CHECKING:
    from .session import EditorSession


_KEEP_SELECTION = object()


class _ProgramCommand(QUndoCommand):
    def __init__(
        self,
        session: "EditorSession",
        text: str,
        transform: Callable[[AuthoringProgram], AuthoringProgram],
        *,
        redo_uid: str | None | object = _KEEP_SELECTION,
        undo_uid: str | None | object = _KEEP_SELECTION,
    ) -> None:
        super().__init__(text)
        self._session = session
        self._before = session.program.clone()
        self._after = transform(self._before)
        self._redo_uid, self._undo_uid = redo_uid, undo_uid

    def _apply(self, program: AuthoringProgram, uid: str | None | object) -> None:
        self._session._apply_program(program)
        if uid is not _KEEP_SELECTION:
            self._session.select_node(uid)

    def redo(self) -> None:
        self._apply(self._after, self._redo_uid)

    def undo(self) -> None:
        self._apply(self._before, self._undo_uid)

class SetNodeArgumentCommand(_ProgramCommand):
    def __init__(self, session: "EditorSession", uid: str, name: str, value: Any) -> None:
        super().__init__(session, f"修改 {name}", lambda program: set_argument(program, uid, name, value))

class SetUnitFieldCommand(_ProgramCommand):
    def __init__(self, session: "EditorSession", unit_id: str, name: str, value: Any) -> None:
        super().__init__(session, f"修改 {name}", lambda program: set_unit_field(program, unit_id, name, value))

class MoveNodeCommand(_ProgramCommand):
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
        super().__init__(
            session,
            f"移动节点：{placement.value}",
            lambda program: move_node(program, uid, target_uid, placement, target_slot=target_slot),
        )

class InsertNodeCommand(_ProgramCommand):
    def __init__(
        self,
        session: "EditorSession",
        target_uid: str,
        placement: DropPlacement | str,
        node: Node,
    ) -> None:
        placement = DropPlacement(placement)
        super().__init__(
            session, f"插入 {node.kind}",
            lambda program: _insert_relative(program, target_uid, placement, node),
            redo_uid=node.uid, undo_uid=session.current_node_uid,
        )

class AppendNodeCommand(_ProgramCommand):
    def __init__(self, session: "EditorSession", unit_id: str, node: Node) -> None:
        def append(program: AuthoringProgram) -> AuthoringProgram:
            unit = program.get_unit(unit_id)
            return insert_node(program, unit_id, None, "body", len(unit.body), node)

        super().__init__(
            session, f"添加 {node.kind}", append, redo_uid=node.uid,
            undo_uid=session.current_node_uid,
        )


class DeleteNodeCommand(_ProgramCommand):
    def __init__(self, session: "EditorSession", uid: str) -> None:
        _unit, node, _location = find_node(session.program, uid)
        super().__init__(
            session, f"删除 {node.kind}", lambda program: delete_node(program, uid), redo_uid=None,
            undo_uid=uid,
        )


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
    "AppendNodeCommand",
    "DeleteNodeCommand",
    "InsertNodeCommand",
    "MoveNodeCommand",
    "SetNodeArgumentCommand",
    "SetUnitFieldCommand",
]
