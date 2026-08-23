"""The shipped beginner path stays editable and formally runnable."""

from __future__ import annotations

from pathlib import Path

from src.authoring import ResourceStore
from src.authoring.scene.document import SceneDocument
from src.compiler.stage import compile_stage
from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.document_manager import DocumentManager
from src.game.background_render.document import BackgroundDocument
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.events import EventBus
from src.game.stage.context import StageContext
from src.game.stage.program import StageRunner
from src.pattern import PatternDocument


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = "game_content/examples/beginner_path"
PATTERN_PATHS = (
    f"{EXAMPLE}/01_first_pattern.pystg.json",
    f"{EXAMPLE}/02_aimed_fan.pystg.json",
)
BACKGROUND_PATH = f"{EXAMPLE}/tutorial_background.pystg.json"
STAGE_PATHS = (
    f"{EXAMPLE}/03_short_midstage.pystg.json",
    f"{EXAMPLE}/04_two_phase_boss.pystg.json",
)
ALL_RESOURCE_PATHS = (*PATTERN_PATHS, BACKGROUND_PATH, *STAGE_PATHS)


class _Player:
    pos = [0.0, -0.75]


class _BackgroundRenderer:
    def __init__(self):
        self.resources: list[str] = []

    def load_background(self, resource: str) -> bool:
        self.resources.append(resource)
        return True


def _project() -> ProjectContext:
    return ProjectContext(ROOT)


def _runtime_context() -> tuple[StageContext, _BackgroundRenderer]:
    background = _BackgroundRenderer()
    context = StageContext(
        OptimizedBulletPool(max_bullets=4096),
        _Player(),
        background_renderer=background,
        event_bus=EventBus(),
    )
    return context, background


def _script_values(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "script":
                yield child
            yield from _script_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _script_values(child)


def test_beginner_resources_load_round_trip_and_need_no_scripts():
    project = _project()
    store = ResourceStore(project)
    documents = [store.load(path) for path in ALL_RESOURCE_PATHS]

    assert [type(document) for document in documents] == [
        PatternDocument,
        PatternDocument,
        BackgroundDocument,
        SceneDocument,
        SceneDocument,
    ]
    assert [document.to_dict()["metadata"]["tutorial_level"] for document in documents] == [
        1,
        2,
        3,
        3,
        4,
    ]

    for document in documents:
        document.validate()
        payload = document.to_dict()
        assert payload["metadata"]["script_required"] is False
        assert all(value in (None, "") for value in _script_values(payload))
        assert type(document).from_dict(payload).to_dict() == payload

    manager = DocumentManager(project, create_initial_scene=False)
    for path in ALL_RESOURCE_PATHS:
        managed = manager.open(path)
        assert not managed.is_dirty
        assert managed.path == project.resolve(path)


def test_beginner_stages_use_local_resources_and_formal_runtime_transitions():
    project = _project()
    store = ResourceStore(project)
    expected_pattern_refs = {f"res://{path}" for path in PATTERN_PATHS}
    expected_background = f"res://{BACKGROUND_PATH}"

    midstage = store.load(STAGE_PATHS[0])
    boss = store.load(STAGE_PATHS[1])
    for scene in (midstage, boss):
        pattern_refs = {
            node.properties["pattern"]
            for node in scene.root.walk()
            if node.type == "PatternInstance"
        }
        background_refs = {
            clip.payload["resource"]
            for state in scene.state_graph.states
            for track in state.tracks
            for clip in track.clips
            if track.kind == "Background"
        }
        program = compile_stage(project, scene)

        assert pattern_refs == expected_pattern_refs
        assert background_refs == {expected_background}
        assert len(program.patterns) == 2
        assert len(program.reactive_clips) == 2

    mid_program = compile_stage(project, midstage)
    mid_runner = StageRunner(mid_program)
    mid_context, _ = _runtime_context()
    wave_a, wave_b, end = midstage.state_graph.states
    mid_runner.start(mid_context)
    assert mid_runner.current_state_path == (wave_a.id,)
    mid_context.emit_event("encounter.cleared", {"wave": "A"})
    mid_runner.tick(mid_context)
    mid_runner.tick(mid_context)
    assert mid_runner.current_state_path == (wave_b.id,)
    mid_context.emit_event("encounter.cleared", {"wave": "B"})
    mid_runner.tick(mid_context)
    mid_runner.tick(mid_context)
    assert mid_runner.current_state_path == (end.id,)
    assert mid_context.bullet_pool.batch_spawn_calls >= 2

    boss_program = compile_stage(project, boss)
    boss_runner = StageRunner(boss_program)
    boss_context, background = _runtime_context()
    intro, normal, enrage, _end = boss.state_graph.states
    boss_runner.start(boss_context)
    for _ in range(intro.duration_frames):
        boss_runner.tick(boss_context)
    assert boss_runner.current_state_path == (normal.id,)
    boss_context.emit_event("encounter.cleared", {"phase": 1})
    boss_runner.tick(boss_context)
    boss_runner.tick(boss_context)
    assert boss_runner.current_state_path == (enrage.id,)
    boss_runner.tick(boss_context)
    assert boss_context.bullet_pool.batch_spawn_calls >= 2
    assert background.resources[0] == expected_background


def test_editor_open_resource_path_accepts_every_beginner_document(qapp_session):
    window = EditorMainWindow(_project())
    try:
        opened = [
            window.document_service.open_document(path)
            for path in ALL_RESOURCE_PATHS
        ]
        assert all(session is not None for session in opened)
        assert [session.document.name for session in opened] == [
            "练习 1：第一圈星弹",
            "练习 2：追踪渐变扇形",
            "新手练习：雾湖背景",
            "练习 3：两波短道中",
            "练习 4：两阶段 Boss",
        ]
        assert all(not session.is_dirty for session in opened)
    finally:
        window.close()
