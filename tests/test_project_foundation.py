from pathlib import Path

import pytest

from src.core.engine_session import EngineSession
from src.core.project_context import ProjectContext, ProjectContextError
from src.resource.service import ResourceService


def _project(tmp_path: Path) -> ProjectContext:
    (tmp_path / "assets").mkdir()
    (tmp_path / "game_content").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    return ProjectContext.discover(tmp_path)


def test_project_context_discovers_root_and_rejects_outside_paths(tmp_path):
    project = _project(tmp_path)
    nested = tmp_path / "game_content" / "stages"
    nested.mkdir(parents=True)

    assert ProjectContext.discover(nested).root == tmp_path.resolve()
    assert project.resolve("assets") == (tmp_path / "assets").resolve()
    with pytest.raises(ProjectContextError):
        project.relative(tmp_path.parent / "outside.json")


def test_resource_service_owns_runtime_and_lazy_editor_models(tmp_path):
    project = _project(tmp_path)
    service = ResourceService(project)

    assert service.textures.asset_root == project.assets
    assert service._editor is None
    assert service.editor.asset_root == project.assets
    assert service._editor is service.editor
    with pytest.raises(ValueError):
        service.asset_path(project.root.parent / "outside.png")


class _Fake:
    def __init__(self, label, calls):
        self.label = label
        self.calls = calls

    def cleanup(self):
        self.calls.append(f"{self.label}.cleanup")

    def stop(self):
        self.calls.append(f"{self.label}.stop")

    def stop_bgm(self, fade_ms):
        self.calls.append(f"{self.label}.stop_bgm:{fade_ms}")

    def set_stage_bank(self, value):
        self.calls.append(f"{self.label}.stage_bank:{value}")

    def clear_all(self):
        self.calls.append(f"{self.label}.clear_all")


def test_engine_session_cleanup_is_ordered_and_idempotent(tmp_path):
    project = _project(tmp_path)
    calls = []
    fake = lambda label: _Fake(label, calls)
    session = EngineSession(
        project=project,
        emoji_system=fake("emoji"),
        audio_manager=fake("audio"),
        renderer=fake("renderer"),
        item_renderer=fake("item"),
        ui_renderer=fake("ui"),
        dialog_renderer=fake("dialog"),
        loading_renderer=fake("loading"),
        pause_renderer=fake("pause"),
        continue_renderer=fake("continue"),
        staff_roll_renderer=fake("staff"),
        spell_declaration_renderer=fake("spell"),
        texture_assets=fake("textures"),
        background_renderer=fake("background"),
    )

    assert session.close() == ()
    assert calls == [
        "emoji.stop",
        "audio.stop_bgm:0",
        "audio.stage_bank:None",
        "renderer.cleanup",
        "item.cleanup",
        "ui.cleanup",
        "dialog.cleanup",
        "loading.cleanup",
        "pause.cleanup",
        "continue.cleanup",
        "staff.cleanup",
        "spell.cleanup",
        "background.cleanup",
        "textures.clear_all",
    ]
    session.close()
    assert len(calls) == 14
