"""Logical unit lifecycle, reference guards, and merged numeric undo."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.authoring.dsl import Ref, Stage, Wave
from src.authoring.program import (
    ProgramError,
    find_node,
    unit_reference_locations,
)
from src.authoring.python_source import save_python_source
from src.core.project_context import ProjectContext
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtWidgets import QApplication


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Ref, RunWave, Stage, Wait\n\n"
        "stage = Stage(\n"
        "    'stage',\n"
        "    'Stage',\n"
        "    body=[Wait(12, uid='wait'), RunWave(Ref('wave_one'), uid='run_wave')],\n"
        ")\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "wave_one.py").write_text(
        "from src.authoring.dsl import Wave, Wait\n\n"
        "wave_one = Wave('wave_one', 'Wave One', body=[Wait(1, uid='w1')])\n",
        encoding="utf-8",
        newline="\n",
    )
    return root


def _session(tmp_path: Path) -> EditorSession:
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(_project(tmp_path / "authoring"))
    session.select_unit("stage")
    return session


def test_create_unit_stays_in_memory_until_save(tmp_path):
    session = _session(tmp_path)
    root = tmp_path / "authoring"

    session.create_unit(Wave("wave_two", "Wave Two"), register_stage=False)
    wave_file = root / "waves" / "wave_two.py"
    assert not wave_file.exists(), "new units must only exist in memory before save"
    assert session.dirty

    session.undo_stack.undo()
    assert "wave_two" not in {unit.id for unit in session.program.logical_units()}
    session.undo_stack.redo()
    assert "wave_two" in {unit.id for unit in session.program.logical_units()}

    session.save_all()
    assert wave_file.exists()
    reopened = EditorSession(project_context=ProjectContext(tmp_path))
    reopened.open_project(root)
    assert reopened.program.get_unit("wave_two").name == "Wave Two"


def test_duplicate_unit_rewrites_uids_and_keeps_registration_opt_in(tmp_path):
    session = _session(tmp_path)
    before = session.program.get_unit("wave_one")
    inner = before.body[0].uid

    session.duplicate_unit("wave_one", "wave_two", "Wave Two")
    duplicate = session.program.get_unit("wave_two")
    assert duplicate.id == "wave_two"
    assert duplicate.body[0].uid != inner
    project = session.program.get_unit("demo")
    stage_refs = [ref.id for ref in project.metadata["stages"]]
    assert stage_refs == ["stage"], "duplicated stages must opt in explicitly"

    session.save_all()
    duplicate_file = tmp_path / "authoring" / "waves" / "wave_two.py"
    assert duplicate_file.exists()
    reopened = EditorSession(project_context=ProjectContext(tmp_path))
    reopened.open_project(tmp_path / "authoring")
    reopened_duplicate = reopened.program.get_unit("wave_two")
    assert reopened_duplicate.body[0].uid == duplicate.body[0].uid


def test_delete_unit_blocked_by_references_lists_jump_locations(tmp_path, qapp_session):
    session = _session(tmp_path)
    window = EditorWindow(session)
    window.show()
    qapp_session.processEvents()

    locations = unit_reference_locations(session.program, "wave_one")
    assert locations, "the RunWave reference must be discoverable"
    assert any(location.startswith("stage.") for location in locations)

    with pytest.raises(ProgramError, match="referenced"):
        session.delete_unit("wave_one")
    assert session.program.get_unit("wave_one") is not None
    assert session.undo_stack.count() == 0
    window.close()


def test_delete_registered_stage_updates_project_order(tmp_path):
    session = _session(tmp_path)
    session.create_unit(Stage("stage_two", "Stage Two"), register_stage=True)
    project = session.program.get_unit("demo")
    assert [ref.id for ref in project.metadata["stages"]] == ["stage", "stage_two"]

    session.delete_unit("stage")
    project = session.program.get_unit("demo")
    assert [ref.id for ref in project.metadata["stages"]] == ["stage_two"]
    assert project.metadata["start_stage"] == Ref("stage_two")

    session.undo_stack.undo()
    project = session.program.get_unit("demo")
    assert [ref.id for ref in project.metadata["stages"]] == ["stage", "stage_two"]


def test_save_failure_preserves_disk_and_memory(tmp_path, monkeypatch):
    session = _session(tmp_path)
    root = tmp_path / "authoring"
    stage_path = root / "stage.py"
    disk_before = stage_path.read_bytes()
    session.set_node_argument("wait", "frames", 30)
    session.save_all()
    disk_before_second_save = stage_path.read_bytes()

    session.create_unit(Wave("wave_three", "Wave Three"), register_stage=False)
    session.set_node_argument("wait", "frames", 40)
    assert session.dirty

    def failing_save(document, **kwargs):
        if document.unit is not None and document.unit.id == "wave_three":
            raise OSError("simulated disk failure")
        return real_save_python_source(document, **kwargs)

    real_save_python_source = save_python_source
    monkeypatch.setattr(
        "src.editor.session.save_python_source", failing_save, raising=True
    )
    with pytest.raises(OSError):
        session.save_all()

    # The rollback restores the last successful save: frames=30 stays on disk,
    # the failed frames=40 write never lands, and the new unit file never
    # appears half-written.
    assert stage_path.read_bytes() == disk_before_second_save
    assert "frames=30" in stage_path.read_text(encoding="utf-8")
    assert not (root / "waves" / "wave_three.py").exists()
    assert session.program.get_unit("wave_three") is not None
    assert find_node(session.program, "wait")[1].arguments["frames"] == 40
    assert session.dirty


def test_consecutive_numeric_edits_merge_into_one_undoable_action(tmp_path):
    session = _session(tmp_path)
    session.set_node_argument("wait", "frames", 20)
    session.set_node_argument("wait", "frames", 45)

    assert session.undo_stack.count() == 1
    assert find_node(session.program, "wait")[1].arguments["frames"] == 45

    session.undo_stack.undo()
    assert find_node(session.program, "wait")[1].arguments["frames"] == 12
    session.undo_stack.redo()
    assert find_node(session.program, "wait")[1].arguments["frames"] == 45


def test_full_unit_lifecycle_through_the_real_window(tmp_path, qapp_session):
    session = _session(tmp_path)
    window = EditorWindow(session)
    window.show()
    qapp_session.processEvents()

    assert window.new_unit_button.isEnabled()
    assert window.duplicate_unit_button.isEnabled()
    assert window.delete_unit_button.isEnabled()
    assert session.current_unit.kind == "Stage"

    # Display names stay editable at any time; IDs and paths never change.
    session.set_unit_field("wave_one", "name", "第一波")
    assert session.program.get_unit("wave_one").name == "第一波"

    window.close()
