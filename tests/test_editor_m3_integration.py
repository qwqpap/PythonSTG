import json

from src.qt_compat.QtCore import QUrl
from src.qt_compat.QtWidgets import QFileDialog

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.panels.pattern_workspace import PatternWorkspace
from src.compiler.scene_spell import SceneSpellCompileError, compile_simple_spell
from src.pattern import BulletSpec, PatternDocument


class FakePreviewClient:
    def __init__(self):
        self.is_running = True
        self.commands = []
        self.closed = False

    def start(self):
        return True

    def send_command(self, command, payload=None):
        request_id = f"request-{len(self.commands) + 1}"
        self.commands.append((command, payload or {}))
        return request_id

    def close(self):
        self.closed = True


def _window(tmp_path):
    project = ProjectContext(tmp_path)
    atlas = tmp_path / "assets" / "bullets.json"
    atlas.parent.mkdir(parents=True)
    atlas.write_text(
        json.dumps({"sprites": {"orb": {"rect": [0, 0, 8, 8]}}}),
        encoding="utf-8",
    )
    pattern = PatternDocument.new("M3 Ring")
    pattern.bullet = BulletSpec(resource="res://assets/bullets.json#orb")
    ResourceStore(project).save(
        pattern,
        "game_content/patterns/m3_ring.pystg.json",
    )
    window = EditorMainWindow(project)
    fake = FakePreviewClient()
    window._pattern_preview_client = fake
    return window, fake


def test_document_tabs_preserve_selection_context_savepoints_and_history(tmp_path, qapp_session):
    window, _fake = _window(tmp_path)
    scene = window.session
    window.add_node("Emitter")
    emitter_id = window._selected_id
    scene.editor_state.timeline.zoom = 1.5

    record = window.resource_browser.index.find(
        "res://game_content/patterns/m3_ring.pystg.json"
    )
    window._resource_activated(record)
    pattern = window.session

    assert len(window.document_manager) == 2
    assert isinstance(window.central_tabs.currentWidget(), PatternWorkspace)
    assert pattern is not scene
    window._pattern_property_requested("shape.count", 36)
    assert pattern.document.shape.count == 36
    assert pattern.is_dirty
    assert scene.editor_state.selection.node_id == emitter_id
    assert scene.editor_state.timeline.zoom == 1.5

    scene_widget = window._document_widgets[scene.document.id]
    window.central_tabs.setCurrentWidget(scene_widget)
    assert window.session is scene
    assert window._selected_id == emitter_id
    assert scene.commands.can_undo

    pattern_widget = window._document_widgets[pattern.document.id]
    window.central_tabs.setCurrentWidget(pattern_widget)
    window.undo()
    assert pattern.document.shape.count == 24
    assert not pattern.is_dirty
    assert scene.commands.can_undo
    window.close()
    qapp_session.processEvents()


def test_pattern_workspace_template_gizmos_and_bullet_picker_are_undoable(tmp_path, qapp_session):
    window, fake = _window(tmp_path)
    window.new_pattern()
    session = window.session
    workspace = window.central_tabs.currentWidget()
    assert isinstance(workspace, PatternWorkspace)
    assert workspace.bullet_picker.count() >= 2

    window._apply_pattern_template("aimed_arc")
    assert session.document.shape.kind == "arc"
    assert session.document.aim.mode == "player"
    window.undo()
    assert session.document.shape.kind == "ring"
    assert session.document.aim.mode == "fixed"

    window._pattern_origin_requested(0.25, 0.5)
    assert session.document.shape.origin_x == 0.25
    assert session.document.shape.origin_y == 0.5
    window.undo()
    assert session.document.shape.origin_x == 0.0
    assert session.document.shape.origin_y == 0.65

    window._pattern_player_requested(-0.2, -0.7)
    assert session.editor_state.pattern.player_position == (-0.2, -0.7)
    assert fake.commands[-1] == (
        "set-player-position",
        {"x": -0.2, "y": -0.7},
    )
    window.close()
    qapp_session.processEvents()


def test_simple_spell_creation_assignment_undo_and_formal_preview(tmp_path, qapp_session):
    window, fake = _window(tmp_path)
    pattern_record = window.resource_browser.index.find(
        "res://game_content/patterns/m3_ring.pystg.json"
    )
    window.create_simple_spell_flow()

    root = window.session.document.root
    stage = root.children[0]
    boss = stage.children[0]
    spell = boss.children[0]
    emitter = spell.children[0]
    instance = emitter.children[0]
    assert [stage.type, boss.type, spell.type, emitter.type, instance.type] == [
        "Stage",
        "Boss",
        "Spell",
        "Emitter",
        "PatternInstance",
    ]
    assert instance.properties["pattern"] == ""

    # Resource assignment is its own command, not only an incidental part of
    # the creation transaction.
    window.set_node_property(instance.id, "pattern", pattern_record.resource_value)
    assert instance.properties["pattern"] == pattern_record.resource_value
    window.undo()
    assert instance.properties["pattern"] == ""
    window.redo()
    assert instance.properties["pattern"] == pattern_record.resource_value

    compiled = compile_simple_spell(window.project, window.session.document, spell.id)
    assert compiled.pattern_instance_id == instance.id
    window._selected_id = spell.id
    window.run_preview()
    assert [command for command, _payload in fake.commands[-2:]] == ["load", "play"]
    assert "document" in fake.commands[-2][1]

    window.undo()
    assert instance.properties["pattern"] == ""
    window.undo()
    assert not root.children
    window.redo()
    assert root.children[0].children[0].children[0].type == "Spell"
    window.redo()
    assert instance.properties["pattern"] == pattern_record.resource_value
    window.close()
    qapp_session.processEvents()


def test_pattern_workspace_remains_usable_at_supported_narrow_size(
    tmp_path,
    qapp_session,
):
    window, _fake = _window(tmp_path)
    window.resize(960, 640)
    window.show()
    window.new_pattern()
    qapp_session.processEvents()

    workspace = window.central_tabs.currentWidget()
    assert isinstance(workspace, PatternWorkspace)
    assign = workspace.findChild(object, "patternAssignBullet")
    apply_template = workspace.findChild(object, "patternApplyTemplate")
    assert assign is not None
    assert apply_template is not None
    assert not workspace.bullet_picker.geometry().intersects(assign.geometry())
    assert not workspace.template_picker.geometry().intersects(apply_template.geometry())
    assert workspace.bullet_picker.geometry().bottom() < workspace.template_picker.geometry().top()
    assert workspace.canvas.height() >= 120
    assert 160 <= window.bottom_dock.height() <= 260

    window.close()
    qapp_session.processEvents()


def test_scene_diagnostic_link_reselects_failing_node(tmp_path, qapp_session):
    window, _fake = _window(tmp_path)
    window.create_simple_spell_flow()
    scene = window.session
    spell = scene.document.root.children[0].children[0].children[0]
    instance = spell.children[0].children[0]

    try:
        compile_simple_spell(window.project, scene.document, spell.id)
    except SceneSpellCompileError as error:
        window._log_scene_diagnostics(error)
    else:
        raise AssertionError("missing Pattern resource should fail")

    window._diagnostic_link_clicked(
        QUrl(f"pystg-node:{scene.document.id}:{instance.id}")
    )
    assert window.session is scene
    assert window._selected_id == instance.id
    assert "missing_pattern_resource" in window.output.toPlainText()
    window.close()
    qapp_session.processEvents()


def test_clean_no_code_ring_flow_saves_reopens_and_formally_previews(
    tmp_path,
    qapp_session,
    monkeypatch,
):
    window, fake = _window(tmp_path)
    window.new_pattern()
    session = window.session
    window._apply_pattern_properties(
        {
            "shape.kind": "ring",
            "shape.count": 32,
            "motion.speed": 3.0,
            "schedule.interval_frames": 10,
            "aim.mode": "player",
            "bullet.resource": "res://assets/bullets.json#orb",
        },
        "Author no-code ring",
    )
    target = tmp_path / "game_content" / "patterns" / "created_ring.pystg.json"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target), "PySTG Resources"),
    )

    assert window.save_scene()
    assert not session.is_dirty
    document_id = session.document.id
    tab = window._document_widgets[document_id]
    window._close_central_tab(window.central_tabs.indexOf(tab))

    reopened = window._open_document(str(target))
    assert reopened.document.shape.count == 32
    assert reopened.document.motion.speed == 3.0
    assert reopened.document.schedule.interval_frames == 10
    assert reopened.document.aim.mode == "player"
    assert reopened.document.bullet.resource == "res://assets/bullets.json#orb"
    window.run_preview()
    assert [command for command, _payload in fake.commands[-2:]] == ["load", "play"]
    assert fake.commands[-2][1]["document"]["shape"]["count"] == 32
    window.close()
    qapp_session.processEvents()
