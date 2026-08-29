"""Undoable adapters around the headless authoring model operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from src.authoring.program import (
    AuthoringProgram,
    DropPlacement,
    Node,
    ProgramError,
    LogicalUnit,
    create_unit,
    delete_node,
    delete_unit,
    duplicate_node,
    duplicate_unit,
    find_node,
    insert_new_node,
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
        redo_unit_id: str | None | object = _KEEP_SELECTION,
        undo_unit_id: str | None | object = _KEEP_SELECTION,
    ) -> None:
        super().__init__(text)
        self._session = session
        self._before = session.program.clone()
        self._after = transform(self._before)
        self._redo_uid, self._undo_uid = redo_uid, undo_uid
        self._redo_unit_id, self._undo_unit_id = redo_unit_id, undo_unit_id

    def _apply(
        self,
        program: AuthoringProgram,
        uid: str | None | object,
        unit_id: str | None | object,
    ) -> None:
        self._session._apply_program(program)
        if unit_id is not _KEEP_SELECTION and unit_id is not None:
            self._session.select_unit(unit_id)
        elif uid is not _KEEP_SELECTION:
            self._session.select_node(uid)

    def redo(self) -> None:
        self._apply(self._after, self._redo_uid, self._redo_unit_id)

    def undo(self) -> None:
        self._apply(self._before, self._undo_uid, self._undo_unit_id)

class SetNodeArgumentCommand(_ProgramCommand):
    """One argument edit; consecutive numeric edits merge into one user action."""

    _MERGE_ID = 0x5341

    def __init__(self, session: "EditorSession", uid: str, name: str, value: Any) -> None:
        super().__init__(session, f"修改 {name}", lambda program: set_argument(program, uid, name, value))
        self._target_uid, self._field = uid, name
        self._mergeable = isinstance(value, (int, float)) and not isinstance(value, bool)

    def id(self) -> int:
        return self._MERGE_ID if self._mergeable else -1

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, SetNodeArgumentCommand):
            return False
        if not (self._mergeable and other._mergeable):
            return False
        if other._target_uid != self._target_uid or other._field != self._field:
            return False
        self._after = other._after
        self.setText(other.text())
        return True

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
        target_slot: str | None = None,
    ) -> None:
        placement = DropPlacement(placement)
        unit = find_node(session.program, target_uid)[0]
        super().__init__(
            session, f"插入 {node.kind}",
            lambda program: insert_new_node(
                program, unit.id, node, target_uid, placement, target_slot=target_slot
            ),
            redo_uid=node.uid, undo_uid=session.current_node_uid,
        )

class AppendNodeCommand(_ProgramCommand):
    def __init__(self, session: "EditorSession", unit_id: str, node: Node) -> None:
        super().__init__(
            session, f"添加 {node.kind}",
            lambda program: insert_new_node(program, unit_id, node), redo_uid=node.uid,
            undo_uid=session.current_node_uid,
        )


class DeleteNodeCommand(_ProgramCommand):
    def __init__(self, session: "EditorSession", uid: str) -> None:
        _unit, node, _location = find_node(session.program, uid)
        super().__init__(
            session, f"删除 {node.kind}", lambda program: delete_node(program, uid), redo_uid=None,
            undo_uid=uid,
        )


class DuplicateNodeCommand(_ProgramCommand):
    """Copy a node subtree; the fresh clone is selected once it exists."""

    def __init__(self, session: "EditorSession", uid: str) -> None:
        unit, node, location = find_node(session.program, uid)
        self._unit_id = unit.id
        self._parent_uid, self._slot, self._index = location.parent_uid, location.slot, location.index
        super().__init__(
            session, f"复制 {node.kind}", lambda program: duplicate_node(program, uid),
            undo_uid=uid,
        )

    def redo(self) -> None:
        self._session._apply_program(self._after)
        owner = self._session.program.get_unit(self._unit_id)
        values = (
            owner.body
            if self._parent_uid is None
            else find_node(self._session.program, self._parent_uid)[1].children[self._slot]
        )
        self._session.select_node(values[self._index + 1].uid)


class CreateUnitCommand(_ProgramCommand):
    def __init__(
        self,
        session: "EditorSession",
        unit: LogicalUnit,
        *,
        register_stage: bool = True,
    ) -> None:
        super().__init__(
            session,
            f"新建 {unit.kind} {unit.id}",
            lambda program: create_unit(program, unit, register_stage=register_stage),
            redo_unit_id=unit.id,
            undo_unit_id=session.current_unit_id,
        )


class DuplicateUnitCommand(_ProgramCommand):
    def __init__(
        self,
        session: "EditorSession",
        source_id: str,
        new_id: str,
        new_name: str,
        *,
        register_stage: bool = False,
    ) -> None:
        super().__init__(
            session,
            f"复制 {source_id} 为 {new_id}",
            lambda program: duplicate_unit(
                program, source_id, new_id, new_name, register_stage=register_stage
            ),
            redo_unit_id=new_id,
            undo_unit_id=source_id,
        )


class DeleteUnitCommand(_ProgramCommand):
    def __init__(
        self,
        session: "EditorSession",
        unit_id: str,
        *,
        replacement_start_stage: str | None = None,
    ) -> None:
        fallback = next(
            (unit.id for unit in session.program.logical_units() if unit.id != unit_id),
            None,
        )
        super().__init__(
            session,
            f"删除 {unit_id}",
            lambda program: delete_unit(
                program,
                unit_id,
                replacement_start_stage=replacement_start_stage,
            ),
            redo_uid=None,
            redo_unit_id=fallback,
            undo_unit_id=unit_id,
        )


__all__ = [
    "AppendNodeCommand",
    "DeleteNodeCommand",
    "DuplicateNodeCommand",
    "CreateUnitCommand",
    "DuplicateUnitCommand",
    "DeleteUnitCommand",
    "InsertNodeCommand",
    "MoveNodeCommand",
    "SetNodeArgumentCommand",
    "SetUnitFieldCommand",
]
