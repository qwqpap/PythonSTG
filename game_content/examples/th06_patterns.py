"""Reusable TH06-like numerical mechanisms on the ordinary PySTG runtime.

These reproduce the two activation formulas, not the ECL instruction set or
original assets. Choose source/target groups explicitly instead of inferring
bullet roles from sprite pixel heights. One normalized unit is taken as 192px
for these examples; author speed and acceleration retain the engine's units.
"""

import math

import numpy as np

from src.content_api import distance_acceleration, neighbor_activation
from src.game.stage.enemy_script import EnemyScript
from src.game.stage.stage_base import StageScript


PIXELS_PER_UNIT = 192.0
START_SPEED = 0.01 * 60.0 * 60.0 / PIXELS_PER_UNIT
VECTOR_ACCEL = 0.01 * 60.0 * 60.0 * 60.0 / PIXELS_PER_UNIT


def distance_turn(ctx, group, center, *, angle_offset=0.0, color='blue'):
    """Stage6Func9: resting small bullets accelerate by distance to the boss.

    angle_offset is one shared random angle in radians, not a draw per bullet.
    Returns the exact activated generations for later acceleration removal.
    """
    snapshot = ctx.read_bullets(group, fields=('pos', 'speed'))
    snapshot = snapshot.select(snapshot['speed'] == 0)
    acceleration = distance_acceleration(
        snapshot['pos'], np.asarray(center, dtype=np.float32),
        math.pi * PIXELS_PER_UNIT / 256.0, angle_offset, VECTOR_ACCEL,
        0.1 / (PIXELS_PER_UNIT * PIXELS_PER_UNIT),
    )
    ctx.transform_bullets(snapshot.group, speed=START_SPEED,
                          vector_accel=acceleration, bullet_type='ball_s', color=color)
    return snapshot.group


def neighbor_turn(ctx, sources, targets, center, *, color='purple'):
    """StageXFunc15: first nearby large bullet activates a resting small one.

    The strict 64px radius and unwrapped 2.2 angle multiplier are preserved.
    The captured source group is read in pool-slot order, not nearest-source
    order. Call once per stage frame to handle moving sources.
    """
    source = ctx.read_bullets(sources, fields=('pos',))
    target = ctx.read_bullets(targets, fields=('pos', 'speed'))
    matched, angles, acceleration, _ = neighbor_activation(
        source['pos'], target['pos'], np.asarray(center, dtype=np.float32),
        64.0 / PIXELS_PER_UNIT, 2.2, target['speed'] == 0, VECTOR_ACCEL,
    )
    activated = target.select(matched)
    ctx.transform_bullets(activated.group, angle=np.rad2deg(angles[matched]),
                          speed=START_SPEED, vector_accel=acceleration[matched],
                          bullet_type='ball_s', color=color)
    return activated.group


async def stop_acceleration(ctx, group, frames=120):
    """One task for an entire activation batch, never one task per bullet."""
    try:
        await ctx.wait(frames)
    finally:
        ctx.transform_bullets(group, vector_accel=(0.0, 0.0))


class ConvertedFairy(EnemyScript):
    hp = 20
    sprite = 'enemy1'

    async def run(self):
        # Source direction/velocity are author units, available before on_spawn.
        self.fire_circle(count=8, speed=1.0, play_sound=False)
        angle = math.radians(self.source_angle)
        await self.move_linear(math.cos(angle) * 0.3, math.sin(angle) * 0.3, duration=90)


class BatchMechanicsStage(StageScript):
    """Ordinary handwritten demonstration stage, usable with StageManager."""

    name = '批量数值机制示例'

    async def run(self):
        rng = np.random.default_rng(self.ctx.seed)
        positions = rng.uniform((-0.75, -0.6), (0.75, 0.6), (256, 2)).astype(np.float32)
        group = self.ctx.capture_bullets(self.ctx.create_bullets_batch(
            positions=positions, angles=-90, speeds=0, bullet_type='ball_s', tag=61,
        ))
        activated = distance_turn(self.ctx, group, (0.0, 0.5),
                                  angle_offset=float(rng.uniform(-math.pi, math.pi)))
        self.spawn_task(stop_acceleration(self.ctx, activated))
        await self.wait(180)
        self.ctx.clear_all_bullets()

        targets = self.ctx.capture_bullets(self.ctx.create_bullets_batch(
            positions=positions, angles=0, speeds=0, bullet_type='ball_s', tag=62,
        ))
        sources = self.ctx.capture_bullets(self.ctx.create_bullets_batch(
            positions=[(-0.7, 0.3), (0.7, -0.3)], angles=[0, 180], speeds=24,
            bullet_type='ball_l', tag=63,
        ))
        for _ in range(120):
            activated = neighbor_turn(self.ctx, sources, targets, (0.0, 0.5))
            if len(activated):
                self.spawn_task(stop_acceleration(self.ctx, activated))
            await self.wait(1)
        await self.wait(120)
        self.ctx.clear_all_bullets()

        group = self.ctx.capture_bullets(self.ctx.create_bullets_batch(
            positions=[(0.8, 0.7), (-0.8, 0.7)], angles=[0, 180], speeds=48,
            bullet_type='grain_a', tag=64,
        ))
        self.ctx.set_bullet_behavior(group, stages=[
            {'frames': 60, 'homing': 'player', 'max_turn_rate': 30, 'wrap_x': 2},
            {'frames': 60, 'vector_accel': (0, -12)},
            {'speed': 36, 'wrap_x': 0},
        ])
        await self.wait(180)
        self.ctx.clear_all_bullets()

        token = self.ctx.convert_bullets_on_end(65, ConvertedFairy)
        try:
            self.ctx.create_bullets_batch(
                positions=[(-0.5 + i / 15.0, 0.5) for i in range(16)],
                angles=-90, speeds=12, tag=65, max_lifetime=0.5,
            )
            await self.wait(180)
        finally:
            self.ctx.cancel_bullet_conversion(token)
