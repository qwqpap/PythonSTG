from __future__ import annotations

import importlib
import json
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

from src.authoring.program import find_node
from src.authoring.python_source import load_authoring_project
from src.authoring.timeline import Unknown, project_timeline
from src.compiler.content_entry import load_content_entry
from src.compiler.package_builder import PackageBuilder
from src.compiler.practice import PRACTICE_STAGE_ID
from src.core.project_context import ProjectContext
from src.editor.preview import PreviewHost, PreviewOwner, PreviewTarget
from src.editor.session import EditorSession
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage import StageManager


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "game_content" / "authoring" / "code_editor_demo"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


@contextmanager
def _built_example(tmp_path: Path):
    source = load_authoring_project(EXAMPLE)
    output_root = tmp_path / "generated"
    target = PackageBuilder(
        output_root,
        project_root=ROOT,
        source_root=EXAMPLE,
    ).build(source.program)
    sys.path.insert(0, str(output_root))
    importlib.invalidate_caches()
    previous = ProjectContext._current
    ProjectContext.set_current(ProjectContext(ROOT))
    try:
        entry = importlib.import_module("code_editor_demo.entry")
        yield source, target, entry
    finally:
        ProjectContext._current = previous
        sys.path.remove(str(output_root))
        for name in list(sys.modules):
            if name == "code_editor_demo" or name.startswith("code_editor_demo."):
                sys.modules.pop(name, None)
        importlib.invalidate_caches()


def test_complete_example_has_the_fixed_scope_and_static_dynamic_timeline():
    source = load_authoring_project(EXAMPLE)
    assert source.diagnostics == ()
    units = source.program.logical_units()
    kinds = [unit.kind for unit in units]
    assert kinds.count("Project") == 1
    assert kinds.count("Stage") == 1
    assert kinds.count("Wave") == 2
    assert kinds.count("Enemy") == 2
    assert kinds.count("Boss") == 1
    assert kinds.count("NonSpell") == 1
    assert kinds.count("Spell") == 1
    assert kinds.count("Task") == 1

    task = source.program.get_unit("support_burst")
    assert [parameter.name for parameter in task.parameters] == ["bursts", "interval"]
    ring = find_node(source.program, "ring_template_call")[1]
    assert ring.kind == "TemplateCall"
    assert "ring_burst(" in (EXAMPLE / "enemies" / "ring_fairy.py").read_text(
        encoding="utf-8"
    )

    projection = project_timeline(
        source.program,
        "demo_stage",
        project_root=ROOT,
    )
    assert projection.find("stage_parallel_intro").kind == "parallel"
    assert projection.find("stage_intro_wait").end == 30
    assert isinstance(projection.find("spell_raw_python").end, Unknown)
    enemy_projection = project_timeline(source.program, "ring_fairy", project_root=ROOT)
    assert enemy_projection.find("ring_template_call").kind == "template"


def test_complete_example_edits_saves_and_reopens_through_one_session(tmp_path):
    copied = tmp_path / "code_editor_demo"
    shutil.copytree(EXAMPLE, copied)
    session = EditorSession(project_context=ProjectContext(ROOT))
    session.open_project(copied)
    session.select_node("stage_intro_wait")
    session.set_node_argument("stage_intro_wait", "frames", 48)
    assert session.undo_stack.count() == 1
    session.save_all()
    session.close_project()
    session.open_project(copied)

    assert find_node(session.program, "stage_intro_wait")[1].arguments["frames"] == 48
    assert "ring_burst(" in (copied / "enemies" / "ring_fairy.py").read_text(
        encoding="utf-8"
    )


def test_complete_example_build_is_deterministic_and_assets_are_references(tmp_path):
    source = load_authoring_project(EXAMPLE)
    first = PackageBuilder(
        tmp_path / "first",
        project_root=ROOT,
        source_root=EXAMPLE,
    ).build(source.program)
    second = PackageBuilder(
        tmp_path / "second",
        project_root=ROOT,
        source_root=EXAMPLE,
    ).build(source.program)

    assert _snapshot(first) == _snapshot(second)
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    source_map = json.loads((first / "source_map.json").read_text(encoding="utf-8"))
    assert manifest["stages"] == ["demo_stage"]
    assert manifest["entry_module"] == "game_content.generated.code_editor_demo.entry"
    assert any(item["uid"] == "spell_raw_python" for item in source_map)
    generated_python = "\n".join(
        path.read_text(encoding="utf-8") for path in first.rglob("*.py")
    )
    for resource in (
        "res://assets/audio/music/00.wav",
        "res://assets/audio/se/se_alert.wav",
        "res://game_content/authoring/code_editor_demo/assets/background/demo.json",
        "res://game_content/authoring/code_editor_demo/assets/dialogue/intro.json",
    ):
        assert resource in generated_python
    assert not list(first.rglob("*.wav"))
    assert not list(first.rglob("*.png"))
    assert not list(first.rglob("demo.json"))


class _Player:
    pos = (0.0, -0.8)


class _ResourceBank:
    def has_bgm(self, _name):
        return False

    def load_bgm(self, _name, path):
        return Path(path).is_file()

    def has_se(self, _name):
        return False

    def load_se(self, _name, path):
        return Path(path).is_file()


class _Audio:
    def __init__(self):
        self.stage_bank = None

    def set_stage_bank(self, value):
        self.stage_bank = _ResourceBank() if value is not None else None

    def play_bgm(self, *_args, **_kwargs):
        return True

    def play_se(self, *_args, **_kwargs):
        return True

    def play_danmaku_se(self, *_args, **_kwargs):
        return True

    def stop_bgm(self, *_args, **_kwargs):
        return None

    def pause_bgm(self):
        return None

    def unpause_bgm(self):
        return None


def test_existing_stage_manager_runs_the_complete_example_to_dialogue_end(
    tmp_path, capsys
):
    with _built_example(tmp_path) as (_source, _target, entry):
        registry = load_content_entry(entry)
        pool = OptimizedBulletPool(max_bullets=4096)
        player = _Player()
        manager = StageManager()
        manager.bind_engine(pool, player, audio_manager=_Audio())
        manager.load_stage(registry.get_stage())
        trace = []
        for _frame in range(2500):
            manager.update(1 / 60, pool, player)
            events, _dropped = manager.drain_authoring_trace()
            trace.extend(events)
            if manager.is_finished and not manager.coroutines:
                break

    capsys.readouterr()
    assert manager.is_finished
    assert any(
        item["uid"] == "stage_dialogue" and item["phase"] == "end" for item in trace
    )
    assert any(item["uid"] == "spell_raw_python" for item in trace)
    assert pool.batch_spawn_calls > 0
    assert pool.emitter_callbacks == {}


def test_project_stage_and_spell_preview_targets_build_from_the_complete_example(
    tmp_path, qapp_session, monkeypatch
):
    session = EditorSession(project_context=ProjectContext(ROOT))
    session.open_project(EXAMPLE)
    builder = PackageBuilder(
        tmp_path / "preview_generated",
        project_root=ROOT,
        source_root=EXAMPLE,
    )
    owner = PreviewOwner(session, PreviewHost(), builder=builder)
    launched = []

    def record_launch(spec):
        launched.append(spec)
        return True

    monkeypatch.setattr(owner, "_launch", record_launch)
    assert owner.run(PreviewTarget("project"))
    assert owner.run(PreviewTarget("stage", "demo_stage"))
    assert owner.run(PreviewTarget("spell", "demo_spell"))

    assert [spec.target.kind for spec in launched] == ["project", "stage", "spell"]
    assert launched[0].stage_id is None
    assert launched[1].stage_id == "demo_stage"
    assert launched[2].stage_id == PRACTICE_STAGE_ID
    assert launched[0].seed == launched[1].seed == launched[2].seed == 1337


def test_handwritten_default_entry_still_registers_stage1_through_stage3():
    entry = importlib.import_module("game_content.entry")
    registry = load_content_entry(entry)
    assert tuple(registry.stage_by_id) == ("stage1", "stage2", "stage3")
