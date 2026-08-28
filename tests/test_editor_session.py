from __future__ import annotations

from pathlib import Path

from src.core.project_context import ProjectContext
from src.editor.session import EditorSession


def _write_project(root: Path, *, frames: int = 30) -> Path:
    (root / "stages").mkdir(parents=True)
    (root / "project.py").write_text(
        "\n".join(
            (
                "from src.authoring.dsl import Project, Ref",
                "",
                "project = Project(",
                "    id='demo',",
                "    name='Demo',",
                "    start_stage=Ref('stage'),",
                "    stages=[Ref('stage')],",
                ")",
                "",
            )
        ),
        encoding="utf-8",
    )
    _write_stage(root, frames=frames)
    return root


def _write_stage(root: Path, *, frames: int) -> None:
    (root / "stages" / "stage.py").write_text(
        "\n".join(
            (
                "from src.authoring.dsl import Stage, Wait",
                "",
                "stage = Stage(",
                "    id='stage',",
                "    name='Stage',",
                f"    body=[Wait(frames={frames}, uid='wait')],",
                ")",
                "",
            )
        ),
        encoding="utf-8",
    )


def test_open_edit_undo_redo_save_and_reopen(tmp_path, qapp_session):
    root = _write_project(tmp_path / "authoring")
    session = EditorSession(project_context=ProjectContext(Path.cwd()))

    session.open_project(root)
    session.select_unit("stage")
    session.select_node("wait")
    assert session.current_node.arguments["frames"] == 30
    assert session.undo_stack.count() == 0

    session.set_node_argument("wait", "frames", 45)
    assert session.current_node.arguments["frames"] == 45
    assert session.dirty
    assert session.undo_stack.count() == 1

    session.undo_stack.undo()
    assert session.current_node.arguments["frames"] == 30
    assert not session.dirty

    session.undo_stack.redo()
    assert session.current_node.arguments["frames"] == 45
    assert session.save_all() == (Path("stages/stage.py"),)
    assert not session.dirty

    reopened = EditorSession(project_context=ProjectContext(Path.cwd()))
    reopened.open_project(root)
    reopened.select_node("wait")
    assert reopened.current_node.arguments["frames"] == 45


def test_session_owns_build_preview_and_selection_state(tmp_path, qapp_session):
    root = _write_project(tmp_path / "authoring")
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(root)

    assert session.build_state == "idle"
    assert session.preview_state == "stopped"
    assert session.current_unit.kind == "Project"

    session.select_source(Path("stages/stage.py"))
    assert session.current_unit_id == "stage"
    assert session.current_document.path == root / "stages" / "stage.py"
    assert "Stage(" in session.source_text
