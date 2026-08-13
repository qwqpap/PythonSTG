from pathlib import Path

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.commands import CommandStack
from src.editor.pattern_workspace import PatternWorkspace
from src.editor.preset_commands import (
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
        window._open_document(path)
        qapp_session.processEvents()
        workspace = window.central_tabs.currentWidget()
        assert isinstance(workspace, PatternWorkspace)
        descriptor = next(item for item in LIBRARY.presets if item.display_name == "扇形扫射")

        window._apply_pattern_template(f"{descriptor.preset_id}@{descriptor.version}")
        qapp_session.processEvents()
        assert window._preset_resolver.instance_from_document(window.session.document) is not None
        assert workspace.mode_switch.findData("preset") >= 0
        assert window.session.is_dirty

        window._preset_materialize_requested()
        assert window._preset_resolver.instance_from_document(window.session.document) is None
        assert window.undo()
        assert window._preset_resolver.instance_from_document(window.session.document) is not None
        assert window.redo()
        assert window._preset_resolver.instance_from_document(window.session.document) is None
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
