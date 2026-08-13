import copy

import pytest

from src.pattern import (
    PatternDocument,
    PresetDescriptor,
    PresetDiagnosticError,
    PresetInstance,
    PresetMigration,
    PresetParameter,
    PresetRegistry,
)


def _descriptor(version: str, parameter_id: str) -> PresetDescriptor:
    return PresetDescriptor(
        preset_id="project.pattern.spiral",
        version=version,
        display_name="Spiral",
        template=PatternDocument.new("Spiral template").to_dict(),
        parameters=(
            PresetParameter(parameter_id, "float", 1.0, "motion.speed", 0.0, 20.0),
        ),
        internal_nodes=({"id": "motion", "kind": "motion", "label": "Motion"},),
    )


def test_migration_preview_is_transactional_and_reports_a_stable_diff() -> None:
    old = _descriptor("1.0.0", "velocity")
    new = _descriptor("2.0.0", "speed")
    migration = PresetMigration(
        preset_id=old.preset_id,
        from_version="1.0.0",
        to_version="2.0.0",
        parameter_renames={"velocity": "speed"},
    )
    assert PresetMigration.from_dict(migration.to_dict()) == migration
    registry = PresetRegistry((old, new), (migration,))
    instance = PresetInstance.new(old, parameters={"velocity": 3.5})
    original = copy.deepcopy(instance.to_dict())

    preview = registry.preview_migration(instance, "2.0.0")

    assert instance.to_dict() == original
    assert preview.instance.version == "2.0.0"
    assert preview.instance.parameters == {"speed": 3.5}
    assert preview.diff == (
        {"kind": "rename_parameter", "from": "velocity", "to": "speed"},
        {"kind": "change_version", "from": "1.0.0", "to": "2.0.0"},
    )


def test_migration_failure_preserves_original_data_and_path() -> None:
    old = _descriptor("1.0.0", "velocity")
    new = _descriptor("2.0.0", "speed")
    migration = PresetMigration(
        preset_id=old.preset_id,
        from_version="1.0.0",
        to_version="2.0.0",
        parameter_renames={"missing": "speed"},
    )
    registry = PresetRegistry((old, new), (migration,))
    instance = PresetInstance.new(old, parameters={"velocity": 3.5})
    original = copy.deepcopy(instance.to_dict())

    with pytest.raises(PresetDiagnosticError) as caught:
        registry.preview_migration(instance, "2.0.0")

    assert caught.value.code == "migration_source_missing"
    assert caught.value.path == "migrations[1.0.0->2.0.0].parameters.missing"
    assert instance.to_dict() == original


def test_migration_cycles_are_rejected_at_registration() -> None:
    one = _descriptor("1.0.0", "speed")
    two = _descriptor("2.0.0", "speed")
    migrations = (
        PresetMigration(one.preset_id, "1.0.0", "2.0.0"),
        PresetMigration(one.preset_id, "2.0.0", "1.0.0"),
    )

    with pytest.raises(PresetDiagnosticError) as caught:
        PresetRegistry((one, two), migrations)

    assert caught.value.code == "migration_cycle"
    assert caught.value.path == "migrations"
