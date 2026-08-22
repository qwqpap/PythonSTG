"""N6 progressive-authoring automation and real-study evidence contract."""

from __future__ import annotations

import json

import pytest

from src.qt_compat.QtWidgets import QDoubleSpinBox, QMenu, QPushButton

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow

from src.authoring.commands.base import CommandStack
from src.authoring.commands.graph import ExpandToGraphCommand
from src.authoring.commands.pattern import (
    RemovePatternBindingCommand,
    SetPatternBindingCommand,
)
from src.editor.progressive_authoring import (
    AUTHORING_LEVELS,
    available_levels,
    level_snapshot,
)
from src.pattern import BindingSpec, PatternCompiler, PatternDocument
from src.editor.panels.pattern_workspace import PatternWorkspace
from src.authoring.commands.preset import ApplyPresetCommand
from src.pattern import PresetLibrary, PresetResolver


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def test_progressive_levels_share_one_resource_and_one_runtime_identity():
    document = PatternDocument.new("Progressive")
    resource_id = document.id
    baseline = PatternCompiler().compile(document)

    assert [item.id for item in AUTHORING_LEVELS] == ["l0", "l1", "l2", "l3", "l4"]
    assert available_levels(document, has_preset=False) == ("l1", "l2", "l3", "l4")
    assert {
        level_snapshot(document, level)["resource_id"]
        for level in ("l1", "l2", "l3", "l4")
    } == {resource_id}
    assert PatternCompiler().compile(document) == baseline


def test_l2_binding_and_l3_expand_are_continuous_undoable_edits():
    document = PatternDocument.new("Continuous")
    stack = CommandStack()
    stack.push(
        SetPatternBindingCommand(
            document,
            BindingSpec("motion.speed", "expression", "2 + burst_index"),
        )
    )
    bound_program = PatternCompiler().compile(document)
    assert bound_program.bindings[0].target_path == "motion.speed"

    stack.push(ExpandToGraphCommand(document))
    assert document.graph is not None
    assert document.id == bound_program.resource_id
    graph_program = PatternCompiler().compile(document)
    assert graph_program.resource_id == bound_program.resource_id
    assert graph_program.bindings == bound_program.bindings
    assert stack.undo()
    assert document.graph is None
    assert document.bindings[0].kind == "expression"

    stack.push(RemovePatternBindingCommand(document, "motion.speed"))
    assert document.bindings == ()
    assert stack.undo()
    assert document.bindings[0].value == "2 + burst_index"


def test_real_usability_report_schema_requires_five_independent_beginners(tmp_path):
    from tools.verify_n6_usability import UsabilityReportError, validate_report

    report = {
        "study": "pystg-n6",
        "maintainer_coaching": False,
        "participants": [
            {
                "id": f"p{index}",
                "prior_pystg_experience": False,
                "pattern_minutes": 9 if index < 4 else 12,
                "midstage_minutes": 25 if index < 4 else 35,
                "boss_minutes": 55 if index < 4 else 70,
                "completed_pattern": True,
                "completed_midstage": True,
                "completed_boss_background_event": index < 4,
                "wrote_script": False,
                "help_requests": index,
                "failure_points": [],
            }
            for index in range(5)
        ],
    }
    result = validate_report(report)
    assert result["passed"]
    assert result["thresholds"] == {
        "pattern_10m": 4,
        "midstage_30m": 4,
        "boss_60m": 4,
    }

    report["participants"] = report["participants"][:4]
    with pytest.raises(UsabilityReportError) as error:
        validate_report(report)
    assert error.value.path == "participants"


def test_n6_usability_claim_and_report_must_agree():
    """The roadmap may claim N6.4 only when a validating report backs it.

    Asserting that ``reports/n6_usability.json`` is absent would make this gate
    self-defeating: the day a genuine study is checked in, the suite would fail
    for the wrong reason and the honest move would be to delete the test.  What
    must hold in both worlds is that the claim and the evidence agree.
    """

    from tools.verify_n6_usability import validate_report

    report_path = ROOT / "reports" / "n6_usability.json"
    todo = (ROOT / "docs" / "EDITOR_IMPLEMENTATION_TODO.md").read_text(encoding="utf-8")
    row = next(line for line in todo.splitlines() if line.startswith("| N6.4 "))
    claimed = "`[x]`" in row

    if not report_path.exists():
        assert not claimed, "N6.4 is checked off with no reports/n6_usability.json"
        return

    # A checked-in report is held to the real schema and thresholds; an invalid
    # one raises out of validate_report and fails this gate.
    result = validate_report(json.loads(report_path.read_text(encoding="utf-8")))
    assert result["passed"], result
    assert claimed, "a passing usability report exists but N6.4 is still unchecked"


def test_level_ui_exposes_exact_preset_parameter_and_binding_controls(
    qapp_session,
):
    library = PresetLibrary.load(
        ROOT / "game_content" / "presets" / "builtin_patterns.pystg.json"
    )
    resolver = PresetResolver(library.presets)
    descriptor = next(item for item in library.presets if item.display_name == "双螺旋")
    document = PatternDocument.new("Levels")
    ApplyPresetCommand(document, resolver, descriptor).execute()
    instance = resolver.instance_from_document(document)
    workspace = PatternWorkspace()
    workspace.set_document(document)
    workspace.set_preset_expansion(
        descriptor,
        resolver.expand_virtual(instance),
        dict(instance.parameters),
    )

    workspace.set_authoring_level("l0")
    assert workspace.stack.currentWidget() is workspace.preset_view
    assert workspace.findChild(QDoubleSpinBox, "presetParameter_speed") is not None
    workspace.set_authoring_level("l2")
    assert workspace.stack.currentWidget() is workspace.advanced_view
    assert workspace.findChild(QPushButton, "patternApplyBinding") is not None
    workspace.set_authoring_level("l4")
    assert workspace.stack.currentWidget() is workspace.source_view
    assert not workspace.open_source.isEnabled()
    # Navigation itself is read-only; the linked instance remains attached.
    assert resolver.instance_from_document(document) == instance
    workspace.close()


def test_editor_level_navigation_expands_once_and_returns_without_duplication(
    tmp_path, qapp_session
):
    project = ProjectContext(tmp_path)
    path = ResourceStore(project).save(
        PatternDocument.new("Progressive Window"),
        "game_content/patterns/progressive.pystg.json",
    )
    window = EditorMainWindow(project)
    window.document_service.open_document(path)
    session = window._active_pattern_session
    workspace = window.central_tabs.currentWidget()

    window.pattern_service.pattern_level_requested("l3")
    first_graph = session.document.graph
    assert first_graph is not None
    node_ids = tuple(node.id for node in first_graph.nodes)
    window.pattern_service.pattern_level_requested("l2")
    assert session.document.graph is first_graph
    window.pattern_service.pattern_level_requested("l3")
    assert tuple(node.id for node in session.document.graph.nodes) == node_ids
    assert workspace.authoring_level() == "l3"
    assert session.undo()
    assert session.document.graph is None
    session.revert()
    window.close()


def test_scene_add_menu_exposes_both_beginner_skeletons_and_each_is_one_undo(
    tmp_path, qapp_session
):
    window = EditorMainWindow(ProjectContext(tmp_path))
    action_names = {action.objectName() for action in window._node_add_menu.actions()}
    assert "addMidstageSkeleton" in action_names
    assert "addTwoPhaseBossSkeleton" in action_names

    before = window.session.document.to_dict()
    window.scene_edit_service.create_stage_template("midstage")
    assert [state.name for state in window.session.document.state_graph.states] == [
        "Wave A", "Wave B", "End"
    ]
    assert window.session.undo()
    assert window.session.document.to_dict() == before
    window.session.revert()
    window.close()


def test_document_switch_hides_irrelevant_pattern_sidebars_and_restores_scene_layout(
    tmp_path, qapp_session
):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.show()
    window.pattern_service.new_pattern()
    qapp_session.processEvents()
    assert not window.scene_dock.isVisibleTo(window)
    assert not window.state_graph_dock.isVisibleTo(window)
    assert not window.variables_dock.isVisibleTo(window)
    assert window.inspector_dock.isVisibleTo(window)

    scene_widget = window._document_widgets[next(iter(window.document_manager)).document.id]
    window.central_tabs.setCurrentWidget(scene_widget)
    qapp_session.processEvents()
    assert window.scene_dock.isVisibleTo(window)
    assert window.inspector_dock.isVisibleTo(window)
    assert window.scene_dock in window.tabifiedDockWidgets(window.state_graph_dock)
    assert window.inspector_dock in window.tabifiedDockWidgets(window.variables_dock)
    window.close()
