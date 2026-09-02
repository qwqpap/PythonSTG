from __future__ import annotations

import sys
from pathlib import Path

from src.compiler.package_builder import PreparedBuild
from src.core.project_context import ProjectContext
from src.editor.preview import PreviewHost, PreviewOwner, PreviewTarget
from src.editor.session import EditorSession
from src.qt_compat.QtCore import QProcess


def _write_project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('preview_demo', 'Demo', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait\n\n"
        "stage = Stage('stage', 'Stage', [Wait(12, uid='wait')])\n",
        encoding="utf-8",
    )
    (root / "spell.py").write_text(
        "from src.authoring.dsl import Spell, Wait\n\n"
        "spell = Spell('spell', 'Spell', body=[Wait(30, uid='spell_wait')])\n",
        encoding="utf-8",
    )
    return root


class _Builder:
    def __init__(self, tmp_path: Path, *, error: Exception | None = None):
        self.tmp_path = tmp_path
        self.error = error
        self.prepared_program = None
        self.published = False

    def prepare(self, program):
        if self.error is not None:
            raise self.error
        self.prepared_program = program.clone()
        temp = self.tmp_path / "_pystg_build_preview_demo_token"
        target = self.tmp_path / "preview_demo"
        temp.mkdir(exist_ok=True)
        (temp / "entry.py").write_text("# generated\n", encoding="utf-8")
        return PreparedBuild(
            project_id="preview_demo",
            temp_dir=temp,
            target_dir=target,
            manifest={},
            source_map=[],
            build_hash="abc123",
        )

    def publish(self, prepared):
        self.published = True
        prepared.target_dir.mkdir(exist_ok=True)
        (prepared.target_dir / "entry.py").write_text("# generated\n", encoding="utf-8")
        return prepared.target_dir


def _session(tmp_path: Path):
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(_write_project(tmp_path / "authoring"))
    return session


def test_run_auto_saves_then_prepares_publishes_and_launches(
    tmp_path, qapp_session, monkeypatch
):
    session = _session(tmp_path)
    session.select_node("wait")
    session.set_node_argument("wait", "frames", 24)
    builder = _Builder(tmp_path / "generated")
    (tmp_path / "generated").mkdir()
    owner = PreviewOwner(session, PreviewHost(), builder=builder)
    launched = []

    def launch(spec):
        launched.append(spec)
        session.set_preview_state("starting")
        return True

    monkeypatch.setattr(owner, "_launch", launch)
    assert owner.run(PreviewTarget("stage", "stage"))
    assert "Wait(frames=24" in (session.source_project.root / "stage.py").read_text(
        encoding="utf-8"
    )
    assert builder.prepared_program.get_unit("stage").body[0].arguments["frames"] == 24
    assert builder.published
    assert launched[0].stage_id == "stage"
    assert launched[0].seed == 1337
    assert session.build_state == "ready"


def test_prepare_failure_keeps_the_old_process_running(tmp_path, qapp_session):
    session = _session(tmp_path)
    host = PreviewHost()
    owner = PreviewOwner(
        session,
        host,
        builder=_Builder(tmp_path, error=RuntimeError("bad build")),
    )
    process = QProcess(owner)
    process.setProgram(sys.executable)
    process.setArguments(["-c", "import time; time.sleep(60)"])
    process.start()
    assert process.waitForStarted(3000)
    owner.process = process
    session.set_preview_state("running")
    assert not owner.run(PreviewTarget("project"))
    assert owner.process is process
    assert process.state() != QProcess.ProcessState.NotRunning
    assert session.build_state == "error"
    process.kill()
    process.waitForFinished(3000)


def test_edit_marks_running_preview_stale_without_relaunch(tmp_path, qapp_session):
    session = _session(tmp_path)
    owner = PreviewOwner(session, PreviewHost())
    process = QProcess(owner)
    process.setProgram(sys.executable)
    process.setArguments(["-c", "import time; time.sleep(60)"])
    process.start()
    assert process.waitForStarted(3000)
    owner.process = process
    session.set_preview_state("running")
    pid = process.processId()
    session.select_node("wait")
    session.set_node_argument("wait", "frames", 30)
    assert session.preview_state == "stale"
    assert process.processId() == pid
    process.kill()
    process.waitForFinished(3000)


def test_stop_terminates_a_nonresponsive_child(tmp_path, qapp_session, monkeypatch):
    session = _session(tmp_path)
    owner = PreviewOwner(session, PreviewHost())
    process = QProcess(owner)
    process.setProgram(sys.executable)
    process.setArguments(["-c", "import time; time.sleep(60)"])
    process.start()
    assert process.waitForStarted(3000)
    owner.process = process
    monkeypatch.setattr(owner, "_send", lambda *_args, **_kwargs: None)
    owner.stop()
    assert process.state() == QProcess.ProcessState.NotRunning
    assert owner.process is None
    assert session.preview_state == "stopped"


def test_session_log_and_trace_are_hard_bounded(tmp_path, qapp_session):
    session = _session(tmp_path)
    for index in range(700):
        session.append_run_log(f"line {index}")
    session.append_trace({"uid": str(index), "phase": "start", "frame": index} for index in range(5000))
    assert len(session.run_log) == 512
    assert session.run_log[0] == "line 188"
    assert len(session.trace_events) == 4096
    assert session.trace_events[0]["uid"] == "904"


def test_spell_target_builds_the_real_practice_stage_and_stays_visible(
    tmp_path, qapp_session, monkeypatch
):
    from src.compiler.practice import PRACTICE_STAGE_ID
    from src.editor.window import EditorWindow

    session = _session(tmp_path)
    window = EditorWindow(session)
    builder = _Builder(tmp_path / "generated")
    (tmp_path / "generated").mkdir()
    owner = PreviewOwner(session, window.preview_host, builder=builder)
    launched = []
    monkeypatch.setattr(owner, "_launch", lambda spec: launched.append(spec) or True)

    assert owner.run(PreviewTarget("spell", "spell"))
    qapp_session.processEvents()
    assert builder.prepared_program.get_unit(PRACTICE_STAGE_ID).kind == "Stage"
    assert launched[0].stage_id == PRACTICE_STAGE_ID
    assert session.preview_target == ("spell", "spell")
    assert "Spell 练习场" in window.preview_target_label.text()
    assert "spell" in window.preview_target_label.text()
    assert window.build_status_label.text() == "构建：成功"
    window.close()


def test_preview_error_is_visible_and_selects_its_author_node(
    tmp_path, qapp_session
):
    from src.editor.window import EditorWindow

    session = _session(tmp_path)
    window = EditorWindow(session)
    window.show()
    qapp_session.processEvents()
    owner = window.preview_owner
    session.select_unit("spell")
    owner._handle_event(
        {
            "event": "error",
            "payload": {
                "code": "runtime_error",
                "message": "authoring node spell_wait: ValueError: bad expression",
            },
            "run_id": "test",
        }
    )
    qapp_session.processEvents()

    assert session.preview_state == "error"
    assert "bad expression" in session.preview_error
    assert session.current_node_uid == "spell_wait"
    assert window.preview_error_label.isVisible()
    assert "spell_wait" in window.preview_error_label.text()
    assert "bad expression" in window.preview_error_label.text()
    window.close()


def test_restart_starting_state_discards_old_trace_for_the_same_run(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    owner = PreviewOwner(session, PreviewHost())
    session.reset_trace("same-run")
    session.append_trace(
        [{"uid": "wait", "phase": "end", "frame": 99}],
        run_id="same-run",
    )

    owner._handle_event(
        {
            "event": "state",
            "payload": {"state": "starting"},
            "run_id": "same-run",
        }
    )

    assert session.trace_run_id == "same-run"
    assert tuple(session.trace_events) == ()
