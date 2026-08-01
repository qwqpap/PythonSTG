"""Undo/redo command contract shared by editor panels."""

from __future__ import annotations

from typing import Protocol


class Command(Protocol):
    label: str

    def execute(self) -> None: ...

    def undo(self) -> None: ...


class CommandStack:
    def __init__(self, limit: int = 256):
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.limit = limit
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str | None:
        return self._undo[-1].label if self._undo else None

    @property
    def redo_label(self) -> str | None:
        return self._redo[-1].label if self._redo else None

    def push(self, command: Command) -> None:
        command.execute()
        self._undo.append(command)
        del self._undo[:-self.limit]
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        command = self._undo.pop()
        command.undo()
        self._redo.append(command)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        command = self._redo.pop()
        command.execute()
        self._undo.append(command)
        return True

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
