"""CD0 parity tests for explicit Fire options and the real bullet pool."""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from src.authoring import dsl
from src.authoring.dsl import Project, Ref, RunWave, Stage
from src.authoring.program import AuthoringProgram
from src.authoring.python_source import load_python_source, save_python_source
from src.compiler.codegen import CodeGenerator
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext


class _Player:
    pos = (0.0, -0.8)


_STRAIGHT_FIRE_OPTIONS = {
    "bullet_type",
    "color",
    "accel",
    "angle_accel",
    "tag",
    "friction",
    "time_scale",
    "bounce_x",
    "bounce_y",
    "spin",
    "render_angle",
    "render_scale",
    "max_lifetime",
    "collision_radius",
    "curve_type",
    "curve_params",
}


@pytest.mark.parametrize(
    "constructor",
    (dsl.Fire, dsl.FireCircle, dsl.FireArc, dsl.FireAtPlayer, dsl.FirePolar, dsl.FireOrbit),
)
def test_fire_constructors_have_no_hidden_runtime_options(constructor):
    signature = inspect.signature(constructor)

    assert not any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


@pytest.mark.parametrize(
    "constructor",
    (dsl.Fire, dsl.FireCircle, dsl.FireArc, dsl.FireAtPlayer),
)
def test_straight_fire_constructors_expose_the_runtime_motion_options(constructor):
    assert _STRAIGHT_FIRE_OPTIONS <= set(inspect.signature(constructor).parameters)


def test_unknown_fire_keyword_opens_read_only_without_rewriting(tmp_path):
    path = tmp_path / "stage.py"
    original = (
        b"from src.authoring.dsl import Fire, Stage\n\n"
        b"stage = Stage('stage', 'Stage', body=[Fire(x=0.0, y=0.0, not_real=1)])\n"
    )
    path.write_bytes(original)

    document = load_python_source(path, module_name="demo.stage")

    assert document.read_only
    assert document.raw_bytes == original
    assert "invalid Fire call" in document.diagnostics[0].message


def test_explicit_batch_fire_options_parse_save_and_build(tmp_path):
    path = tmp_path / "wave.py"
    path.write_text(
        "from src.authoring.dsl import FireCircle, Wave\n\n"
        "wave = Wave(\n"
        "    'wave',\n"
        "    'Wave',\n"
        "    body=[\n"
        "        FireCircle(\n"
        "            x=0.0, y=0.5, count=3, speed=3.0, start_angle=10.0,\n"
        "            play_sound=False, bullet_type='rice', color='blue',\n"
        "            accel=1.5, angle_accel=30.0, tag=7, friction=0.2,\n"
        "            time_scale=0.5, bounce_x=True, bounce_y=True, spin=20.0,\n"
        "            render_angle=45.0, render_scale=1.1, max_lifetime=2.0,\n"
        "            collision_radius=0.01, curve_type=4,\n"
        "            curve_params=(0.5, 1.0, 0.0, 2.0), uid='burst',\n"
        "        ),\n"
        "    ],\n"
        ")\n",
        encoding="utf-8",
    )

    document = load_python_source(path, module_name="demo.wave")
    assert not document.read_only
    document.mark_dirty()
    save_python_source(document)
    reopened = load_python_source(path, module_name="demo.wave")
    node = reopened.unit.body[0]
    assert _STRAIGHT_FIRE_OPTIONS <= set(node.arguments)

    program = AuthoringProgram.from_units(
        [
            Project("demo", "Demo", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [RunWave(Ref("wave"))]),
            reopened.unit,
        ]
    )
    result = CodeGenerator(program).generate()
    source = result.modules["stages/stage/waves/wave.py"]
    assert "accel=1.5" in source
    assert "angle_accel=30.0" in source
    assert "curve_params=(0.5, 1.0, 0.0, 2.0)" in source


def test_stage_context_single_and_batch_share_motion_state_and_evolution():
    options = {
        "bullet_type": "ball_m",
        "color": "red",
        "accel": 3.0,
        "angle_accel": 60.0,
        "tag": 17,
        "friction": 0.0,
        "time_scale": 1.0,
        "bounce_x": True,
        "bounce_y": True,
        "spin": 45.0,
        "render_angle": 30.0,
        "render_scale": 1.25,
        "max_lifetime": 3.0,
        "collision_radius": 0.03,
        "curve_type": 0,
        "curve_params": (0.0, 0.0, 0.0, 0.0),
    }
    single_pool = OptimizedBulletPool(max_bullets=4)
    batch_pool = OptimizedBulletPool(max_bullets=4)
    single_context = StageContext(single_pool, _Player())
    batch_context = StageContext(batch_pool, _Player())

    single_index = single_context.create_bullet(
        x=0.0, y=0.0, angle=15.0, speed=4.0, **options
    )
    batch_index = int(
        batch_context.create_bullets_batch(
            positions=[(0.0, 0.0)], angles=[15.0], speeds=[4.0], **options
        )[0]
    )
    assert single_pool.spawned_total == 1
    assert batch_pool.spawned_total == 1

    for field in (
        "pos",
        "vel",
        "acc",
        "angle",
        "render_angle",
        "angular_vel",
        "render_scale",
        "speed",
        "speed_accel",
        "motion_angular_vel",
        "motion_angular_accel",
        "radius",
        "lifetime",
        "max_lifetime",
        "friction",
        "tag",
        "time_scale",
        "flags",
        "curve_type",
        "curve_param",
    ):
        np.testing.assert_allclose(
            single_pool.data[field][single_index],
            batch_pool.data[field][batch_index],
            rtol=1e-6,
            atol=1e-7,
        )

    assert single_pool.data["speed_accel"][single_index] == pytest.approx(3.0 / 60.0)
    assert single_pool.data["motion_angular_accel"][single_index] == pytest.approx(
        math.radians(60.0)
    )

    for _ in range(60):
        single_pool.update(1.0 / 60.0)
        batch_pool.update(1.0 / 60.0)

    for field in (
        "pos",
        "vel",
        "angle",
        "render_angle",
        "speed",
        "motion_angular_vel",
    ):
        np.testing.assert_allclose(
            single_pool.data[field][single_index],
            batch_pool.data[field][batch_index],
            rtol=1e-5,
            atol=1e-6,
        )
    assert single_pool.data["speed"][single_index] == pytest.approx(7.0 / 60.0, abs=1e-5)
    assert single_pool.data["motion_angular_vel"][single_index] == pytest.approx(
        math.radians(60.0), abs=1e-5
    )


def test_delayed_straight_spawn_keeps_explicit_motion_fields():
    """The queue path must not erase the author-visible motion parameters."""

    pool = OptimizedBulletPool(max_bullets=2)
    assert (
        pool.spawn_bullet(
            x=0.0,
            y=0.0,
            angle=0.0,
            speed=2.0 / 60.0,
            delay=1,
            speed_accel=3.0 / 60.0,
            motion_angular_accel=math.radians(60.0),
        )
        == -1
    )

    pool.update(1.0 / 60.0)
    assert not np.any(pool.data["alive"])
    assert pool.spawned_total == 0
    pool.update(1.0 / 60.0)

    spawned = np.flatnonzero(pool.data["alive"])
    assert spawned.tolist() == [0]
    assert pool.spawned_total == 1
    index = int(spawned[0])
    assert pool.data["speed_accel"][index] == pytest.approx(3.0 / 60.0)
    assert pool.data["motion_angular_accel"][index] == pytest.approx(
        math.radians(60.0)
    )
