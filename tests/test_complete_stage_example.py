"""The shipped complete-stage example stays editable and formally runnable."""

from __future__ import annotations

from pathlib import Path

from src.authoring import ResourceStore
from src.authoring.scene.document import SceneDocument
from src.compiler.stage import compile_stage
from src.core.project_context import ProjectContext
from src.game.background_render.document import BackgroundDocument
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.events import EventBus
from src.game.stage.context import StageContext
from src.game.stage.program import StageRunner
from src.pattern import PatternDocument


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = "game_content/examples/mist_lake_boss"
SCENE_PATH = f"{EXAMPLE}/stage.pystg.json"
PATTERN_PATHS = (
    f"{EXAMPLE}/moon_ring.pystg.json",
    f"{EXAMPLE}/purple_tide.pystg.json",
)
BACKGROUND_PATH = f"{EXAMPLE}/background.pystg.json"


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


def test_complete_stage_resources_load_round_trip_and_reference_real_assets():
    store = ResourceStore(_project())
    scene = store.load(SCENE_PATH)
    patterns = tuple(store.load(path) for path in PATTERN_PATHS)
    background = store.load(BACKGROUND_PATH)

    assert isinstance(scene, SceneDocument)
    assert [state.name for state in scene.state_graph.states] == [
        "登场：湖面点灯",
        "通常：月轮灯阵",
        "强化：紫潮追猎",
        "结束：雾散",
    ]
    assert all(isinstance(pattern, PatternDocument) for pattern in patterns)
    assert isinstance(background, BackgroundDocument)

    pattern_refs = {
        node.properties["pattern"]
        for node in scene.root.walk()
        if node.type == "PatternInstance"
    }
    assert pattern_refs == {f"res://{path}" for path in PATTERN_PATHS}
    assert SceneDocument.from_dict(
        scene.to_canonical_dict(), canonical=True
    ).to_canonical_dict() == scene.to_canonical_dict()

    background_dir = ROOT / "assets" / "images" / "background"
    for texture in background.body["textures"].values():
        assert (background_dir / texture["path"]).is_file()


def test_complete_stage_compiles_and_reactive_clear_enters_enrage():
    project = _project()
    scene = ResourceStore(project).load(SCENE_PATH)
    program = compile_stage(project, scene)

    assert len(program.patterns) == 2
    assert len(program.reactive_clips) == 2
    assert {action.kind for action in program.actions} >= {
        "Audio",
        "Background",
        "Event",
    }

    background = _BackgroundRenderer()
    context = StageContext(
        OptimizedBulletPool(max_bullets=4096),
        _Player(),
        background_renderer=background,
        event_bus=EventBus(),
    )
    runner = StageRunner(program)
    runner.start(context)

    intro, normal, enrage, _end = scene.state_graph.states
    assert runner.current_state_path == (intro.id,)
    for _ in range(intro.duration_frames):
        runner.tick(context)
    assert runner.current_state_path == (normal.id,)

    runner.tick(context)
    assert runner.read_variable("boss.phase") == 1
    context.emit_event("encounter.cleared", {"source": "example-test"})
    runner.tick(context)
    runner.tick(context)
    assert runner.current_state_path == (enrage.id,)
    runner.tick(context)
    assert runner.read_variable("boss.phase") == 2
    assert runner.read_variable("boss.rage") is True
    assert background.resources[0] == (
        "res://game_content/examples/mist_lake_boss/background.pystg.json"
    )
