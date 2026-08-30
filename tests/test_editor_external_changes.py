from __future__ import annotations

from pathlib import Path

import pytest

from src.authoring.python_source import ExternalChange, SourceConflictError, SourceSaveError
from src.core.project_context import ProjectContext
from src.editor.session import EditorSession


def _project(root: Path, *, frames: int = 10) -> Path:
    root.mkdir()
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project(id='demo', name='Demo', start_stage=Ref('stage'), stages=[Ref('stage')])\n",
        encoding="utf-8",
    )
    _write_stage(root, frames)
    (root / "wave.py").write_text(
        "from src.authoring.dsl import Wave\n\n"
        "wave = Wave('wave', 'Wave')\n",
        encoding="utf-8",
    )
    return root


def _write_stage(root: Path, frames: int) -> None:
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait\n\n"
        f"stage = Stage(id='stage', name='Stage', body=[Wait({frames}, uid='wait')])\n",
        encoding="utf-8",
    )


def _session(root: Path) -> EditorSession:
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(root)
    session.select_node("wait")
    return session


def test_clean_external_change_reloads_supported_source(tmp_path, qapp_session):
    root = _project(tmp_path / "authoring")
    session = _session(root)

    _write_stage(root, 20)
    assert session.check_external_changes() == ExternalChange.RELOADED
    assert session.current_node is None
    session.select_node("wait")
    assert session.current_node.arguments["frames"] == 20
    assert session.undo_stack.count() == 0
    assert not session.dirty


def test_dirty_external_change_freezes_save_until_explicit_reload(tmp_path, qapp_session):
    root = _project(tmp_path / "authoring")
    session = _session(root)
    session.set_node_argument("wait", "frames", 15)

    _write_stage(root, 30)
    assert session.check_external_changes() == ExternalChange.CONFLICT
    assert session.has_conflict
    with pytest.raises(SourceConflictError):
        session.save_all()

    assert session.resolve_external_changes("reload") == ExternalChange.RELOADED
    session.select_node("wait")
    assert session.current_node.arguments["frames"] == 30
    assert session.undo_stack.count() == 0
    assert not session.has_conflict
    assert not session.dirty


def test_keep_memory_requires_explicit_choice_then_overwrites_atomically(tmp_path, qapp_session):
    root = _project(tmp_path / "authoring")
    session = _session(root)
    session.set_node_argument("wait", "frames", 25)

    _write_stage(root, 40)
    assert session.check_external_changes() == ExternalChange.CONFLICT
    assert session.resolve_external_changes("keep") == ExternalChange.CONFLICT
    assert session.dirty
    assert session.can_edit
    session.set_node_argument("wait", "frames", 26)
    session.save_all()

    reopened = _session(root)
    assert reopened.current_node.arguments["frames"] == 26


def test_unsupported_python_is_read_only_and_never_overwritten(tmp_path, qapp_session):
    root = tmp_path / "unsupported"
    root.mkdir()
    path = root / "bad.py"
    raw = b"from src.authoring.dsl import Stage\nfor item in range(3):\n    pass\n"
    path.write_bytes(raw)
    session = EditorSession(project_context=ProjectContext(Path.cwd()))

    session.open_project(root)
    session.select_source("bad.py")

    assert session.current_document.read_only
    assert not session.can_edit
    assert session.source_text.encode("utf-8") == raw
    assert session.save_all() == ()
    assert path.read_bytes() == raw
    with pytest.raises(SourceSaveError):
        session.current_document.mark_dirty()


def test_explicit_reload_of_deleted_source_becomes_read_only(tmp_path, qapp_session):
    root = _project(tmp_path / "authoring")
    session = _session(root)
    session.set_node_argument("wait", "frames", 15)
    (root / "stage.py").unlink()

    assert session.check_external_changes() == ExternalChange.CONFLICT
    assert session.resolve_external_changes("reload") == ExternalChange.RELOADED

    session.select_source("stage.py")
    assert session.current_document.read_only
    assert not session.can_edit
    assert session.undo_stack.count() == 0


def test_external_change_to_tombstoned_unit_requires_keep_or_reload(
    tmp_path, qapp_session
):
    root = _project(tmp_path / "authoring")
    wave_path = root / "wave.py"
    session = _session(root)
    session.delete_unit("wave")
    wave_path.write_text(
        "from src.authoring.dsl import Wave\n\n"
        "wave = Wave('wave', 'External Wave')\n",
        encoding="utf-8",
    )

    assert session.check_external_changes() == ExternalChange.CONFLICT
    with pytest.raises(SourceConflictError):
        session.save_all()
    assert session.resolve_external_changes("reload") == ExternalChange.RELOADED
    assert session.program.get_unit("wave").name == "External Wave"
    assert wave_path.exists()
    assert session.undo_stack.count() == 0

    session.delete_unit("wave")
    wave_path.write_text(
        "from src.authoring.dsl import Wave\n\n"
        "wave = Wave('wave', 'External Again')\n",
        encoding="utf-8",
    )
    assert session.check_external_changes() == ExternalChange.CONFLICT
    assert session.resolve_external_changes("keep") == ExternalChange.CONFLICT
    session.save_all()
    assert not wave_path.exists()
    assert all(unit.id != "wave" for unit in session.program.logical_units())
