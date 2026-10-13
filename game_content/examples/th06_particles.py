"""Ordinary particle authoring, with TH06-inspired numeric mechanisms.

Reference: EffectManager.cpp / BatWingEffect in YomotsuHisami/th06 at
fa4d48f66d4701fef6c5e802ca85a738b0d5177c. Movement formulas are adapted to
units/second, upward-positive Y, 192 pixels/unit. This uses our existing
sprites and new visual timings, NOT the original ANM or original RNG stream.

    python tools/preview_spell.py game_content/examples/th06_particles.py ParticleMechanicsSpell
    python main.py --content-entry game_content/examples/th06_particles.py
"""

import math

import numpy as np

from src.devtools.spell_preview import preview
from src.game.particle import ParticleEffect
from src.game.stage.boss_base import spellcard
from src.game.stage.spellcard import SpellCard
from src.game.stage.stage_base import BossDef, StageScript


PIXELS_PER_UNIT = 192.0
SPARK = ParticleEffect(('grain_a16',), lifetime=36, scale=1.4, scale_end=0.25, blend='add')
BURST = ParticleEffect(('preimg8',), lifetime=30, scale=0.3, scale_end=1.8, blend='add')
FLASH = ParticleEffect(('preimg8',), lifetime=16, scale=0.5, scale_end=2.5, blend='add')
WING = ParticleEffect(('grain_a16',), lifetime=120, scale=(2.0, 1.0),
                      scale_end=(0.3, 0.3), angular_speed=90.0, blend='add')
GATHER = ParticleEffect(('preimg8',), lifetime=61, scale=0.4, scale_end=0.9, blend='add', layer='back')
GATHER_SLOW = ParticleEffect(('preimg8',), lifetime=241, scale=0.25, scale_end=0.8,
                            blend='add', layer='back')
ORBIT = ParticleEffect(('preimg8',), lifetime=180, scale=0.4, alpha_end=1.0, blend='add')


def random_splash(ctx, center, *, count=64, big=False):
    """Uniform square velocity with constant braking; explicit Euler."""
    pixels_per_frame = (np.random.random((count, 2)) * 256.0 - 128.0)
    pixels_per_frame *= 4.0 / 33.0 if big else 1.0 / 12.0
    pixels_per_frame[:, 1] *= -1.0
    velocity = pixels_per_frame * 60.0 / PIXELS_PER_UNIT
    braking_frames = 20 if big else 19
    return ctx.emit_particles(
        BURST if big else SPARK, *center, count=count, velocity=velocity,
        acceleration=-velocity * 60.0 / braking_frames,
        color=(0.65, 0.85, 1.0, 0.9) if big else (1.0, 0.5, 0.7, 1.0),
    )


def gather(ctx, center, *, count=32, slow=False):
    """Fixed directions; r(t)=256px*(1-t/60), or /240 for slow gathering."""
    radius = 256.0 / PIXELS_PER_UNIT
    frames = 240 if slow else 60
    return ctx.emit_particles(
        GATHER_SLOW if slow else GATHER, *center, count=count, motion='radial',
        radius=radius, radial_speed=-radius * 60.0 / frames,
        direction=np.random.uniform(-180.0, 180.0, count),
        color=(0.45, 0.65, 1.0, 0.8),
    )


def wing_pair(ctx, center, frame):
    """A sparse actor emitter produces two numeric particles, never two Tasks.

    Uses the reference increasing emission cadence, mirrored positions and
    constant braking. Original attached glow/actor animation is not included.
    """
    emit = (frame > 120 or (frame > 60 and frame % 2 == 0)
            or (frame > 30 and frame % 4 == 0) or frame % 8 == 0)
    if not emit:
        return None
    half = (frame % 16) // 2
    modifier = half + (int(np.random.randint(half)) if half else 0)
    distance = (32.0 + modifier * 10.0) / PIXELS_PER_UNIT
    heading = math.radians((frame + 46) % 90 - 45 - modifier * 4.5)
    dx, dy = math.cos(heading) * distance, -math.sin(heading) * distance
    velocity = np.column_stack((
        np.random.uniform(-20.0, 20.0, 2) / PIXELS_PER_UNIT,
        np.full(2, (16.0 - 8.0 * modifier) / PIXELS_PER_UNIT),
    ))
    return ctx.emit_particles(
        WING, [center[0] + dx, center[0] - dx], [center[1] + dy] * 2,
        count=2, velocity=velocity, acceleration=-velocity / 2.0,
        rotation=-math.degrees(heading), color=(0.2, 0.35, 1.0, 1.0),
    )


async def projected_orbit(ctx, center, *, count=48, frames=100):
    """One controller rotates a batch about 3D axes and draws the 2D projection.

    Rodrigues rotation represents the quaternion rotation geometrically. This
    is an author formula, not another 3D renderer/ANM VM. The original depth,
    axis/radius controller and attached animation still need content migration.
    """
    axes = np.random.normal(size=(count, 3))
    axes /= np.linalg.norm(axes, axis=1)[:, None]
    tangent = np.column_stack((axes[:, 1], -axes[:, 0], np.zeros(count)))
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    perpendicular = np.cross(axes, tangent)
    phase = np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)
    group = ctx.emit_particles(ORBIT, *center, count=count, color=(0.7, 0.4, 1.0, 1.0))
    try:
        for frame in range(frames):
            angle = phase + frame * 0.04
            offsets = (tangent * np.cos(angle)[:, None]
                       + perpendicular * np.sin(angle)[:, None]) * 0.4
            position = np.column_stack((center[0] + offsets[:, 0], center[1] - offsets[:, 1]))
            ctx.transform_particles(group, position=position)
            await ctx.wait(1)
        for frame in range(1, 16):
            alpha = 1.0 - frame / 16.0
            ctx.transform_particles(group, color=(0.7, 0.4, 1.0, alpha), scale=2.0 - alpha)
            await ctx.wait(1)
    finally:
        ctx.clear_particles(group)


@preview(seed=1337, boss_pos=(0.0, 0.45), duration=560)
class ParticleMechanicsSpell(SpellCard):
    name = '粒子机制：散射、闪光、收拢、双翼'
    time_limit = 12.0

    async def run(self):
        center = (self.boss.x, self.boss.y)
        random_splash(self.ctx, center)
        await self.wait(36)
        random_splash(self.ctx, center, count=32, big=True)
        await self.wait(36)
        self.ctx.emit_particles(FLASH, *center, color=(0.5, 0.8, 1.0, 1.0))
        group = self.ctx.capture_bullets(self.fire_circle(
            count=32, speed=0.0, color='blue', play_sound=False))
        await self.wait(12)
        self.ctx.transform_bullets(group, speed=6.0)
        gather(self.ctx, center)
        gather(self.ctx, center, count=24, slow=True)
        await self.wait(30)
        with self.ctx.stop_time('effects'):
            # Only the decoration stops. Actor tasks and bullets keep running.
            await self.wait(20)
        self.spawn_task(projected_orbit(self.ctx, center))
        for frame in range(160):
            wing_pair(self.ctx, center, frame)
            await self.wait(1)
        await self.wait(150)


class ParticleMechanicsStage(StageScript):
    id = 'th06_particles'
    name = 'TH06 粒子机制示例（非原作贴图）'
    boss = BossDef('particle_boss', '粒子机制', '', [
        spellcard(ParticleMechanicsSpell, '', hp=1000, time=12.0, bonus=0),
    ])

    async def run(self):
        await self.run_boss(self.boss)


STAGES = [ParticleMechanicsStage]
START_STAGE = ParticleMechanicsStage
STAGE_BY_ID = {stage.id: stage for stage in STAGES}
