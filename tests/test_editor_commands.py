from __future__ import annotations

from pathlib import Path

import pytest

from src.authoring.program import ProgramError
from src.core.project_context import ProjectContext
from src.editor.session import EditorSession


def _project(root: Path) -> Path:
    root.mkdir()
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project(id='demo', name='Demo', start_stage=Ref('stage'), stages=[Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait\n\n"
        "stage = Stage(id='stage', name='Stage', body=[Wait(10, uid='wait')])\n",
        encoding="utf-8",
    )
    return root


def test_every_mutation_uses_the_session_single_undo_stack(tmp_path, qapp_session):
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(_project(tmp_path / "authoring"))

    stack = session.undo_stack
    session.set_unit_field("stage", "name", "新名称")
    session.set_node_argument("wait", "frames", 20)

    assert session.undo_stack is stack
    assert stack.count() == 2
    assert session.program.get_unit("stage").name == "新名称"
    assert session.program.get_unit("stage").body[0].arguments["frames"] == 20

    stack.undo()
    stack.undo()
    assert session.program.get_unit("stage").name == "Stage"
    assert session.program.get_unit("stage").body[0].arguments["frames"] == 10
    stack.redo()
    stack.redo()
    assert session.program.get_unit("stage").name == "新名称"
    assert session.program.get_unit("stage").body[0].arguments["frames"] == 20


def test_invalid_command_never_enters_undo_history(tmp_path, qapp_session):
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(_project(tmp_path / "authoring"))

    with pytest.raises(ProgramError):
        session.set_node_argument("wait", "missing", 1)

    assert session.undo_stack.count() == 0
    assert not session.dirty
