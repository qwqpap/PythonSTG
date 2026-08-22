from pathlib import Path

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.authoring.commands.base import CommandStack
from src.editor.panels.pattern_workspace import PatternWorkspace, PresetReactionSlotEditor
from src.authoring.commands.preset import (
    ApplyPresetMigrationCommand,
    ApplyPresetCommand,
    MaterializePresetCommand,
    SetPresetOverrideCommand,
)
from src.pattern import PatternCompiler, PatternDocument, PresetLibrary, PresetResolver
from src.pattern import PresetMigration, PresetRegistry


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = PresetLibrary.load(
    ROOT / "game_content" / "presets" / "builtin_patterns.pystg.json"
)


def _resolver():
    return PresetResolver(LIBRARY.presets)


def test_apply_override_materialize_is_one_undoable_authoring_chain() -> None:
    resolver = _resolver()
    descriptor = next(item for item in LIBRARY.presets if item.display_name == "双螺旋")
    document = PatternDocument.new("Local")
    before = document.to_dict()
    stack = CommandStack()

    stack.push(ApplyPresetCommand(document, resolver, descriptor))
    linked = resolver.instance_from_document(document)
    assert linked is not None
    assert document.id == before["id"]

    stack.push(SetPresetOverrideCommand(document, resolver, "count", 20))
    assert document.shape.count == 20
    assert resolver.instance_from_document(document).parameters["count"] == 20

    stack.push(MaterializePresetCommand(document, resolver))
    assert resolver.instance_from_document(document) is None
    assert document.header.metadata["materialized_from_preset"] == {
        "preset_id": descriptor.preset_id,
        "version": descriptor.version,
    }
    local_program = PatternCompiler().compile(document)

    assert stack.undo()
    assert resolver.instance_from_document(document).parameters["count"] == 20
    assert stack.redo()
    assert PatternCompiler().compile(document) == local_program

    assert stack.undo()
    assert stack.undo()
    assert document.shape.count == descriptor.parameters[0].default
    assert stack.undo()
    assert document.to_dict() == before


def test_virtual_workspace_is_read_only_and_uses_stable_instance_ids(qapp_session) -> None:
    resolver = _resolver()
    descriptor = next(item for item in LIBRARY.presets if item.display_name == "圆形开花")
    document = PatternDocument.new("Linked")
    ApplyPresetCommand(document, resolver, descriptor).execute()
    instance = resolver.instance_from_document(document)
    before = document.to_dict()
    nodes = resolver.expand_virtual(instance)
    workspace = PatternWorkspace()
    try:
        workspace.set_document(document)
        workspace.set_available_presets(LIBRARY.presets)
        workspace.set_preset_expansion(descriptor, nodes)
        workspace.set_mode("preset", emit=False)
        qapp_session.processEvents()

        assert workspace.mode() == "preset"
        assert workspace.stack.currentWidget() is workspace.preset_view
        assert workspace.preset_nodes.count() == len(descriptor.internal_nodes)
        assert workspace.virtual_preset_nodes == nodes
        assert document.to_dict() == before
        assert document.graph is None
    finally:
        workspace.close()


def test_window_applies_builtin_preset_and_undo_redoes_materialization(
    tmp_path: Path, qapp_session
) -> None:
    project = ProjectContext(tmp_path)
    path = ResourceStore(project).save(PatternDocument.new("Window Preset"), "patterns/window.pystg.json")
    window = EditorMainWindow(project)
    try:
        window.document_service.open_document(path)
        qapp_session.processEvents()
        workspace = window.central_tabs.currentWidget()
        assert isinstance(workspace, PatternWorkspace)
        descriptor = next(item for item in LIBRARY.presets if item.display_name == "扇形扫射")

        window.pattern_service.apply_pattern_template(f"{descriptor.preset_id}@{descriptor.version}")
        qapp_session.processEvents()
        assert window._preset_resolver.instance_from_document(window.session.document) is not None
        assert "preset" in workspace.available_modes()
        assert window.session.is_dirty

        window.pattern_service.preset_materialize_requested()
        assert window._preset_resolver.instance_from_document(window.session.document) is None
        assert window.undo()
        assert window._preset_resolver.instance_from_document(window.session.document) is not None
        assert window.redo()
        assert window._preset_resolver.instance_from_document(window.session.document) is None
    finally:
        window.close()
        qapp_session.processEvents()


def _versioned_pair():
    """Build a 1.0.0 -> 2.0.0 preset pair joined by one parameter rename."""

    base = next(item for item in LIBRARY.presets if item.display_name == "圆形开花")
    payload = base.to_dict()
    payload["version"] = "2.0.0"
    payload["parameters"][0]["id"] = "bullet_count"
    newer = type(base).from_dict(payload)
    migration = PresetMigration(
        base.preset_id,
        "1.0.0",
        "2.0.0",
        parameter_renames={"count": "bullet_count"},
    )
    resolver = PresetResolver((base, newer))
    resolver.registry = PresetRegistry((base, newer), (migration,))
    return base, resolver


def test_preset_slot_editor_writes_one_undoable_slot_override(
    tmp_path: Path, qapp_session
) -> None:
    project = ProjectContext(tmp_path)
    path = ResourceStore(project).save(
        PatternDocument.new("Slot"), "patterns/slot.pystg.json"
    )
    window = EditorMainWindow(project)
    try:
        window.document_service.open_document(path)
        qapp_session.processEvents()
        descriptor = next(
            item for item in LIBRARY.presets if item.display_name == "圆形开花"
        )
        window.pattern_service.apply_pattern_template(f"{descriptor.preset_id}@{descriptor.version}")
        qapp_session.processEvents()
        slot = descriptor.slots[0]

        def slot_editor():
            # Applying a command rebuilds the preset form, so the previous
            # editor widget is already scheduled for deletion by now.
            found = window.central_tabs.currentWidget().findChild(
                PresetReactionSlotEditor, f"presetSlot_{slot.id}"
            )
            assert found is not None
            return found

        editor = slot_editor()
        assert editor.enabled.isChecked() is False
        assert editor.count.isEnabled() is False

        editor.enabled.setChecked(True)
        qapp_session.processEvents()
        instance = window._preset_resolver.instance_from_document(
            window.session.document
        )
        assert instance.slot_overrides[slot.id]["action"] == "split"

        editor = slot_editor()
        assert editor.enabled.isChecked() is True
        editor.count.setValue(9)
        editor.count.editingFinished.emit()
        qapp_session.processEvents()
        instance = window._preset_resolver.instance_from_document(
            window.session.document
        )
        assert instance.slot_overrides[slot.id]["count"] == 9

        assert window.undo()
        instance = window._preset_resolver.instance_from_document(
            window.session.document
        )
        assert instance.slot_overrides[slot.id]["count"] == 6
        assert window.undo()
        instance = window._preset_resolver.instance_from_document(
            window.session.document
        )
        assert slot.id not in instance.slot_overrides
    finally:
        window.close()
        qapp_session.processEvents()


def test_preset_migration_button_only_offers_reachable_versions(
    tmp_path: Path, qapp_session
) -> None:
    base, resolver = _versioned_pair()
    project = ProjectContext(tmp_path)
    path = ResourceStore(project).save(
        PatternDocument.new("Migrate"), "patterns/migrate.pystg.json"
    )
    window = EditorMainWindow(project)
    try:
        window._preset_resolver = resolver
        window.document_service.open_document(path)
        qapp_session.processEvents()
        window.pattern_service.apply_pattern_template(f"{base.preset_id}@1.0.0")
        window.pattern_service.preset_parameter_requested("count", 48)
        qapp_session.processEvents()

        workspace = window.central_tabs.currentWidget()
        assert workspace.preset_version.text().endswith("1.0.0")
        assert [
            workspace.preset_migrate_target.itemData(index)
            for index in range(workspace.preset_migrate_target.count())
        ] == ["2.0.0"]
        assert workspace.preset_migrate_button.isEnabled()

        workspace.preset_migrate_button.click()
        qapp_session.processEvents()
        migrated = resolver.instance_from_document(window.session.document)
        assert migrated.version == "2.0.0"
        assert migrated.parameters == {"bullet_count": 48}

        # 2.0.0 is the end of the chain, so the control retires itself rather
        # than offering a target the preview would reject.
        workspace = window.central_tabs.currentWidget()
        assert workspace.preset_migrate_target.count() == 0
        assert workspace.preset_migrate_button.isEnabled() is False

        assert window.undo()
        assert resolver.instance_from_document(window.session.document).version == "1.0.0"
    finally:
        window.close()
        qapp_session.processEvents()


def test_migration_preview_confirmation_is_one_undoable_command() -> None:
    base = next(item for item in LIBRARY.presets if item.display_name == "圆形开花")
    payload = base.to_dict()
    payload["version"] = "2.0.0"
    payload["parameters"][0]["id"] = "bullet_count"
    newer = type(base).from_dict(payload)
    migration = PresetMigration(
        base.preset_id,
        "1.0.0",
        "2.0.0",
        parameter_renames={"count": "bullet_count"},
    )
    registry = PresetRegistry((base, newer), (migration,))
    resolver = PresetResolver((base, newer))
    resolver.registry = registry
    document = PatternDocument.new("Migrate")
    stack = CommandStack()
    stack.push(ApplyPresetCommand(document, resolver, base))
    stack.push(SetPresetOverrideCommand(document, resolver, "count", 48))
    preview = registry.preview_migration(resolver.instance_from_document(document), "2.0.0")
    before = document.to_dict()

    stack.push(ApplyPresetMigrationCommand(document, resolver, preview))
    migrated = resolver.instance_from_document(document)
    assert migrated.version == "2.0.0"
    assert migrated.parameters == {"bullet_count": 48}
    assert stack.undo()
    assert document.to_dict() == before
    assert stack.redo()
    assert resolver.instance_from_document(document).version == "2.0.0"
