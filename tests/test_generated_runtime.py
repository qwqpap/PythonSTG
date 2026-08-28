from __future__ import annotations

import importlib
import json
import random
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from src.authoring.dsl import (
    Boss,
    Call,
    Enemy,
    Expr,
    FireArc,
    FireCircle,
    Function,
    NonSpell,
    Parallel,
    Parameter,
    Project,
    RawPython,
    Ref,
    Return,
    RunBoss,
    RunWave,
    SpawnEnemy,
    SpawnTask,
    Spell,
    Stage,
    Task,
    Wait,
    Wave,
)
from src.authoring.program import AuthoringProgram
from src.compiler.content_entry import load_content_entry
from src.compiler.package_builder import PackageBuilder
from src.core.project_context import ProjectContext
from src.game.stage import StageManager
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.game.stage.enemy_script import EnemyScript
from src.game.stage.spellcard import NonSpell as RuntimeNonSpell
from src.game.stage.spellcard import SpellCard
from src.game.stage.stage_base import StageScript
from src.game.stage.wave_base import Wave as RuntimeWave


def _runtime_program(project_id: str = "runtime_bundle") -> AuthoringProgram:
    return AuthoringProgram.from_units(
        [
            Project(
                project_id,
                "Runtime Demo",
                Ref("runtime_stage"),
                [Ref("runtime_stage"), Ref("seed_stage"), Ref("raw_stage"), Ref("asset_stage")],
            ),
            Stage(
                "runtime_stage",
                "Generated Runtime",
                [
                    SpawnTask(Ref("background_task"), uid="spawn_task"),
                    Wait(2, uid="stage_wait"),
                    RawPython("type(self).task_observed = getattr(self, 'task_done', False)", uid="task_observed"),
                    Parallel(
                        [
                            [Wait(1), RawPython("self.left_done = True")],
                            [Wait(2), RawPython("self.right_done = True")],
                        ],
                        uid="parallel",
                    ),
                    Call(Ref("identity"), [7], uid="call_identity"),
                    RunWave(Ref("wave"), uid="run_wave"),
                    RunBoss(Ref("boss"), uid="run_boss"),
                    RawPython("type(self).completed = True", uid="completed"),
                ],
            ),
            Wave(
                "wave",
                "Wave",
                [SpawnEnemy(Ref("enemy"), uid="spawn_enemy"), Wait(3, uid="wave_wait")],
            ),
            Enemy(
                "enemy",
                "Enemy",
                [
                    FireCircle(
                        count=8,
                        speed=3.0,
                        play_sound=False,
                        render_angle=45.0,
                        uid="circle",
                    ),
                    FireArc(count=5, speed=2.0, play_sound=False, uid="arc"),
                    Wait(1, uid="enemy_wait"),
                ],
                sprite="res://assets/images/enemy/enemy1.json",
            ),
            Boss(
                "boss",
                "Boss",
                "res://assets/images/enemy/enemy1.json",
                [Ref("nons"), Ref("spell")],
            ),
            NonSpell("nons", body=[Wait(1, uid="nons_wait")]),
            Spell("spell", "Spell", [Wait(1, uid="spell_wait")]),
            Task(
                "background_task",
                "Background",
                body=[Wait(1), RawPython("_ctx.task_done = True")],
            ),
            Function(
                "identity",
                "Identity",
                [Parameter("value", "int")],
                [Return(Expr("value"))],
            ),
            Stage(
                "seed_stage",
                "Seed",
                [RawPython("import random\nself.sample = random.random()", uid="sample"), Wait(1)],
            ),
            Stage(
                "raw_stage",
                "Raw",
                [RawPython("raise ValueError('boom')", uid="raw_boom")],
            ),
            Stage(
                "asset_stage",
                "Assets",
                [Wait(1)],
                bgm="res://assets/audio/music/00.wav",
                background="res://assets/images/background/bamboo.json",
            ),
        ]
    )


@contextmanager
def _built_entry(tmp_path: Path, program: AuthoringProgram):
    output_root = tmp_path / "generated"
    builder = PackageBuilder(output_root, project_root=Path.cwd())
    target = builder.build(program)
    project_id = next(unit.id for unit in program.logical_units() if unit.kind == "Project")
    sys.path.insert(0, str(output_root))
    importlib.invalidate_caches()
    try:
        entry = importlib.import_module(f"{project_id}.entry")
        yield target, entry
    finally:
        sys.path.remove(str(output_root))
        for name in list(sys.modules):
            if name == project_id or name.startswith(f"{project_id}."):
                sys.modules.pop(name, None)
        importlib.invalidate_caches()


class _BulletPool:
    def __init__(self):
        self.clear_count = 0
        self.batch_calls = []

    def spawn_bullets_batch(self, **kwargs):
        self.batch_calls.append(kwargs)
        return list(range(len(kwargs["angles"])))

    def clear_all(self):
        self.clear_count += 1


class _Player:
    pos = (0.0, -0.8)


@pytest.fixture(scope="module")
def generated_bundle(tmp_path_factory):
    with _built_entry(tmp_path_factory.mktemp("generated_runtime"), _runtime_program()) as built:
        yield built


def test_generated_full_closure_imports_existing_runtime_types(generated_bundle):
    _, entry = generated_bundle
    registry = load_content_entry(entry)
    stage_class = registry.get_stage()
    wave_class = importlib.import_module("runtime_bundle.stages.runtime_stage.waves.wave").Wave_wave
    enemy_class = importlib.import_module("runtime_bundle.stages.runtime_stage.enemies.enemy").Enemy_enemy
    spell_module = importlib.import_module("runtime_bundle.stages.runtime_stage.spells.spell")
    nons_module = importlib.import_module("runtime_bundle.stages.runtime_stage.spells.nons")

    assert issubclass(stage_class, StageScript)
    assert issubclass(wave_class, RuntimeWave)
    assert issubclass(enemy_class, EnemyScript)
    assert issubclass(spell_module.Spell_spell, SpellCard)
    assert issubclass(nons_module.NonSpell_nons, RuntimeNonSpell)


def test_existing_stage_manager_runs_generated_stage_from_start_to_end(generated_bundle):
    _, entry = generated_bundle
    stage_class = entry.START_STAGE
    stage_class.completed = False
    stage_class.task_observed = False
    pool = _BulletPool()
    player = _Player()
    manager = StageManager()
    manager.bind_engine(pool, player)
    manager.load_stage(stage_class)

    for _ in range(500):
        manager.update(1 / 60, pool, player)
        if manager.is_finished and not manager.coroutines:
            break

    assert manager.is_finished
    assert stage_class.completed is True
    assert stage_class.task_observed is True
    assert pool.clear_count == 1
    assert len(pool.batch_calls) == 2


def test_fixed_seed_repeats_generated_runtime_result(generated_bundle):
    _, entry = generated_bundle
    samples = []
    for _ in range(2):
        random.seed(20260828)
        stage = entry.STAGE_BY_ID["seed_stage"]()
        stage.start()
        for _frame in range(10):
            stage.update()
            if not stage._active:
                break
        samples.append(stage.sample)

    assert samples[0] == samples[1]


def test_raw_python_runtime_error_identifies_author_node(generated_bundle):
    _, entry = generated_bundle
    coroutine = entry.STAGE_BY_ID["raw_stage"]().run()

    with pytest.raises(RuntimeError) as caught:
        coroutine.send(None)

    assert "raw_boom" in str(caught.value)
    assert "ValueError: boom" in str(caught.value)


def test_generated_package_keeps_resource_references_without_copying_assets(generated_bundle):
    target, _ = generated_bundle
    stage_source = (target / "stages" / "asset_stage" / "stage.py").read_text(encoding="utf-8")

    assert "res://assets/audio/music/00.wav" in stage_source
    assert "res://assets/images/background/bamboo.json" in stage_source
    assert not list(target.rglob("*.ogg"))
    assert {path.name for path in target.rglob("*.json")} == {"manifest.json", "source_map.json"}


class _ResourceBank:
    def __init__(self):
        self.bgm = {}
        self.se = {}

    def has_bgm(self, name):
        return name in self.bgm

    def load_bgm(self, name, path):
        self.bgm[name] = path
        return True

    def has_se(self, name):
        return name in self.se

    def load_se(self, name, path):
        self.se[name] = path
        return True


class _ResourceAudio:
    def __init__(self):
        self.stage_bank = _ResourceBank()


class _ResourceBackground:
    def __init__(self):
        self.calls = []

    def load_from_json(self, path, asset_base=""):
        self.calls.append((path, asset_base))
        return True


class _ResourceContext:
    def __init__(self):
        self.audio = _ResourceAudio()
        self.background_renderer = _ResourceBackground()
        self.played_bgm = []
        self.played_se = []

    def play_bgm(self, name):
        self.played_bgm.append(name)
        return True

    def play_se(self, name, volume=None, min_interval=0.0):
        self.played_se.append((name, volume, min_interval))
        return True

    def set_background(self, name):
        raise AssertionError(f"res:// background was not resolved: {name}")


def test_generated_support_resolves_project_resources_at_runtime(generated_bundle, tmp_path):
    _, entry = generated_bundle
    audio_path = tmp_path / "assets" / "audio" / "music" / "00.wav"
    se_path = tmp_path / "assets" / "audio" / "se" / "shot.wav"
    background_path = tmp_path / "assets" / "images" / "background" / "bamboo.json"
    dialogue_path = tmp_path / "assets" / "dialogue" / "intro.json"
    for path in (audio_path, se_path, background_path, dialogue_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"RIFF")
    se_path.write_bytes(b"RIFF")
    background_path.write_text("{}", encoding="utf-8")
    dialogue = [{"text": "hello", "position": "left"}]
    dialogue_path.write_text(json.dumps(dialogue), encoding="utf-8")

    previous = ProjectContext._current
    ProjectContext.set_current(ProjectContext(tmp_path))
    try:
        support = importlib.import_module("runtime_bundle.stages.asset_stage._support")
        stage = entry.STAGE_BY_ID["asset_stage"]()
        context = _ResourceContext()
        stage.bind(context)
        stage._play_bgm(stage.bgm)
        support._pystg_play_se(stage, "res://assets/audio/se/shot.wav", volume=0.5)
        loaded_dialogue = support._pystg_dialogue("res://assets/dialogue/intro.json")
    finally:
        ProjectContext._current = previous

    assert context.background_renderer.calls == [
        (str(background_path.resolve()), str(background_path.parent.resolve()))
    ]
    assert list(context.audio.stage_bank.bgm.values()) == [str(audio_path.resolve())]
    assert list(context.audio.stage_bank.se.values()) == [str(se_path.resolve())]
    assert context.played_bgm == list(context.audio.stage_bank.bgm)
    assert context.played_se[0][0] == next(iter(context.audio.stage_bank.se))
    assert loaded_dialogue == dialogue


class _BatchPool:
    def __init__(self):
        self.calls = []

    def spawn_bullets_batch(self, **kwargs):
        self.calls.append(kwargs)
        return list(range(len(kwargs["angles"])))


def test_generated_high_density_actions_use_runtime_batch_path(generated_bundle):
    enemy_class = importlib.import_module(
        "runtime_bundle.stages.runtime_stage.enemies.enemy"
    ).Enemy_enemy
    pool = _BatchPool()
    context = StageContext(pool, _Player())
    enemy = enemy_class()
    enemy.bind(context, x=0.25, y=0.5)
    coroutine = enemy.run()
    while True:
        try:
            coroutine.send(None)
        except StopIteration:
            break

    assert len(pool.calls) == 2
    assert [len(call["angles"]) for call in pool.calls] == [8, 5]
    assert all(
        call["positions"].tolist() == [[0.25, 0.5]] * len(call["angles"])
        for call in pool.calls
    )
    assert enemy._bullets == list(range(8)) + list(range(5))
    assert pool.calls[0]["render_angles"].tolist() == pytest.approx(
        [0.7853982] * 8
    )
    assert not hasattr(pool, "spawn_bullet")

    real_pool = OptimizedBulletPool(max_bullets=32)
    real_enemy = enemy_class()
    real_enemy.bind(StageContext(real_pool, _Player()), x=0.25, y=0.5)
    real_coroutine = real_enemy.run()
    while True:
        try:
            real_coroutine.send(None)
        except StopIteration:
            break

    assert real_pool.batch_spawn_calls == 2
    assert int(real_pool.data["alive"].sum()) == 13
    assert real_pool.data["render_angle"][:8].tolist() == pytest.approx(
        [0.7853982] * 8
    )
    assert real_pool.emitter_callbacks == {}
