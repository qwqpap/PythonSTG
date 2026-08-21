"""Undo/redo command contract shared by editor panels.

The stack deliberately owns interaction-sized history rather than widget
events.  A spinbox drag can therefore coalesce many values into one command,
and a multi-field operation can be committed as one transaction.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable, ClassVar, Iterator, Protocol


class Command(Protocol):
    label: str

    def execute(self) -> None: ...

    def undo(self) -> None: ...


class MergeableCommand:
    """Coalesce consecutive edits of one target into a single undo step.

    A spinbox drag or gizmo move emits a command per value.  Recording each one
    would make Undo walk back through the drag frame by frame, so the stack asks
    the previous command to absorb the next one.  Absorbing means adopting the
    later command's value while keeping this command's original undo snapshot:
    one drag, one Undo, and the value the author released on.

    A subclass declares what it edits rather than reimplementing the rule:

    ``merge_owner``
        Attributes naming the document or tree the edit belongs to, compared by
        identity.  Two separately loaded documents never coalesce.
    ``merge_identity``
        Attributes identifying the edited target within that owner (node id,
        property path), compared by value.
    ``merge_same_keys``
        Mapping attributes that must carry the same key set.  A later edit that
        touches a different set of fields is a different operation.
    ``merge_values``
        Attributes carrying the edited value, adopted from the later command.
    """

    merge_owner: ClassVar[tuple[str, ...]] = ()
    merge_identity: ClassVar[tuple[str, ...]] = ()
    merge_same_keys: ClassVar[tuple[str, ...]] = ()
    merge_values: ClassVar[tuple[str, ...]] = ()
    _merge_type: ClassVar[type | None] = None

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # The declaring class decides what may merge, not the runtime class, so a
        # subclass that only specialises behaviour still coalesces with its base.
        if any(
            name in vars(cls)
            for name in ("merge_owner", "merge_identity", "merge_values")
        ):
            cls._merge_type = cls

    def merge_with(self, other: object) -> bool:
        if not isinstance(other, self._merge_type or type(self)):
            return False
        if any(
            getattr(self, name) is not getattr(other, name)
            for name in self.merge_owner
        ):
            return False
        if any(
            getattr(self, name) != getattr(other, name)
            for name in self.merge_identity
        ):
            return False
        if any(
            set(getattr(self, name)) != set(getattr(other, name))
            for name in self.merge_same_keys
        ):
            return False
        for name in self.merge_values:
            setattr(self, name, deepcopy(getattr(other, name)))
        return True


@dataclass
class CompositeCommand:
    """A transaction that replays commands in order and undoes in reverse."""

    label: str
    commands: list[Command] = field(default_factory=list)

    def execute(self) -> None:
        for command in self.commands:
            command.execute()

    def undo(self) -> None:
        for command in reversed(self.commands):
            command.undo()


@dataclass
class _Transaction:
    label: str
    commands: list[Command] = field(default_factory=list)


class CommandStack:
    def __init__(self, limit: int = 256):
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.limit = limit
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._transaction: _Transaction | None = None

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

    @property
    def in_transaction(self) -> bool:
        return self._transaction is not None

    def _append_history(self, command: Command) -> None:
        self._undo.append(command)
        del self._undo[:-self.limit]
        self._redo.clear()

    @staticmethod
    def _try_merge(previous: Command, command: Command) -> bool:
        merge = getattr(previous, "merge_with", None)
        return bool(merge(command)) if callable(merge) else False

    def push(
        self,
        command: Command,
        *,
        coalesce: bool = False,
        validate: Callable[[], None] | None = None,
    ) -> None:
        """Execute and record a command, rolling it back if validation fails."""

        command.execute()
        try:
            if validate is not None:
                validate()
        except Exception:
            command.undo()
            raise

        if self._transaction is not None:
            commands = self._transaction.commands
            if coalesce and commands and self._try_merge(commands[-1], command):
                return
            commands.append(command)
            return

        if coalesce and self._undo and self._try_merge(self._undo[-1], command):
            self._redo.clear()
            return
        self._append_history(command)

    def begin_transaction(self, label: str) -> None:
        if self._transaction is not None:
            raise RuntimeError("nested command transactions are not supported")
        if not str(label).strip():
            raise ValueError("transaction label must be non-empty")
        self._transaction = _Transaction(str(label))

    def end_transaction(self) -> bool:
        transaction = self._transaction
        if transaction is None:
            raise RuntimeError("no command transaction is active")
        self._transaction = None
        if not transaction.commands:
            return False
        command: Command
        if len(transaction.commands) == 1:
            command = transaction.commands[0]
            command.label = transaction.label
        else:
            command = CompositeCommand(transaction.label, transaction.commands)
        self._append_history(command)
        return True

    def cancel_transaction(self) -> None:
        transaction = self._transaction
        if transaction is None:
            raise RuntimeError("no command transaction is active")
        self._transaction = None
        for command in reversed(transaction.commands):
            command.undo()

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        self.begin_transaction(label)
        try:
            yield
        except Exception:
            self.cancel_transaction()
            raise
        else:
            self.end_transaction()

    def undo(self) -> bool:
        if self._transaction is not None:
            raise RuntimeError("cannot undo during a command transaction")
        if not self._undo:
            return False
        command = self._undo.pop()
        command.undo()
        self._redo.append(command)
        return True

    def redo(self) -> bool:
        if self._transaction is not None:
            raise RuntimeError("cannot redo during a command transaction")
        if not self._redo:
            return False
        command = self._redo.pop()
        command.execute()
        self._undo.append(command)
        return True

    def clear(self) -> None:
        if self._transaction is not None:
            self.cancel_transaction()
        self._undo.clear()
        self._redo.clear()
