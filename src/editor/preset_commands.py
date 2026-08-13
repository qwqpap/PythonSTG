"""Undoable edits for linked preset-backed Pattern documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.pattern import (
    PatternDocument,
    PresetDescriptor,
    PresetInstance,
    PresetMigrationPreview,
    PresetResolver,
)

from .pattern_commands import PatternMutationError, _copy_pattern


def _snapshot(document: PatternDocument) -> PatternDocument:
    return PatternDocument.from_dict(document.to_dict())


@dataclass
class ApplyPresetCommand:
    document: PatternDocument
    resolver: PresetResolver
    descriptor: PresetDescriptor
    label: str = "Apply preset"
    _previous: PatternDocument | None = field(default=None, init=False, repr=False)
    _applied: PatternDocument | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if self._previous is None:
            self._previous = _snapshot(self.document)
            instance = PresetInstance.new(
                self.descriptor, instance_id=self.document.id
            )
            self._applied = self.resolver.resolve(instance).document
        _copy_pattern(self.document, self._applied)

    def undo(self) -> None:
        if self._previous is None:
            raise PatternMutationError(
                "Cannot undo preset application before execution"
            )
        _copy_pattern(self.document, self._previous)


@dataclass
class SetPresetOverrideCommand:
    document: PatternDocument
    resolver: PresetResolver
    parameter_id: str
    value: Any
    label: str = "Set preset parameter"
    _previous: PatternDocument | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        instance = self.resolver.instance_from_document(self.document)
        if instance is None:
            raise PatternMutationError("Pattern is not linked to a preset")
        if self._previous is None:
            self._previous = _snapshot(self.document)
        parameters = dict(instance.parameters)
        parameters[self.parameter_id] = self.value
        updated = PresetInstance(
            id=instance.id,
            preset_id=instance.preset_id,
            version=instance.version,
            parameters=parameters,
            slot_overrides=dict(instance.slot_overrides),
        )
        _copy_pattern(self.document, self.resolver.resolve(updated).document)

    def undo(self) -> None:
        if self._previous is None:
            raise PatternMutationError("Cannot undo a preset edit that was not executed")
        _copy_pattern(self.document, self._previous)


@dataclass
class SetPresetSlotOverrideCommand:
    document: PatternDocument
    resolver: PresetResolver
    slot_id: str
    value: Any
    label: str = "Set preset slot"
    _previous: PatternDocument | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        instance = self.resolver.instance_from_document(self.document)
        if instance is None:
            raise PatternMutationError("Pattern is not linked to a preset")
        if self._previous is None:
            self._previous = _snapshot(self.document)
        slots = dict(instance.slot_overrides)
        slots[self.slot_id] = self.value
        updated = PresetInstance(
            id=instance.id,
            preset_id=instance.preset_id,
            version=instance.version,
            parameters=dict(instance.parameters),
            slot_overrides=slots,
        )
        _copy_pattern(self.document, self.resolver.resolve(updated).document)

    def undo(self) -> None:
        if self._previous is None:
            raise PatternMutationError("Cannot undo a preset edit that was not executed")
        _copy_pattern(self.document, self._previous)


@dataclass
class MaterializePresetCommand:
    document: PatternDocument
    resolver: PresetResolver
    label: str = "Materialize preset locally"
    _previous: PatternDocument | None = field(default=None, init=False, repr=False)
    _materialized: PatternDocument | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if self._previous is None:
            self._previous = _snapshot(self.document)
            self._materialized = self.resolver.materialize(self.document)
        if self._materialized is None:
            raise PatternMutationError("Materialization was not prepared")
        _copy_pattern(self.document, self._materialized)

    def undo(self) -> None:
        if self._previous is None:
            raise PatternMutationError("Cannot undo materialization before execution")
        _copy_pattern(self.document, self._previous)


@dataclass
class ApplyPresetMigrationCommand:
    document: PatternDocument
    resolver: PresetResolver
    preview: PresetMigrationPreview
    label: str = "Migrate preset version"
    _previous: PatternDocument | None = field(default=None, init=False, repr=False)
    _migrated: PatternDocument | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        current = self.resolver.instance_from_document(self.document)
        if current is None or current.to_dict() != self.preview.original.to_dict():
            raise PatternMutationError("Preset changed after migration preview; preview again")
        if self._previous is None:
            self._previous = _snapshot(self.document)
            self._migrated = self.resolver.resolve(self.preview.instance).document
        _copy_pattern(self.document, self._migrated)

    def undo(self) -> None:
        if self._previous is None:
            raise PatternMutationError("Cannot undo migration before execution")
        _copy_pattern(self.document, self._previous)
