"""TH06 actor/laser mechanisms on the ordinary StageScript/SpellCard runtime.

These are editable mechanism examples, not original stage scripts or assets.
For the reference formulas below, one normalized unit represents 192 pixels;
TH06's downward-positive Y and radian angles are converted explicitly.

Preview:
    python tools/preview_spell.py game_content/examples/th06_controls.py ControlMechanicsSpell
"""

import math

import numpy as np

from src.devtools.spell_preview import preview
from src.game.stage.boss_base import spellcard
from src.game.stage.enemy_script import EnemyScript
from src.game.stage.spellcard import SpellCard
from src.game.stage.stage_base import BossDef, StageScript


PIXELS_PER_UNIT = 192.0


def crossed_lasers(ctx, center, *, angle_offset=0.0):
    """Stage6Func7, laser branch: two eight-direction chains, three layers.

    The offset is one shared angle in radians. Difficulty selects the original
    length/width branch; start, active, fade and hitbox times remain separate.
    Geometric/layout formulas match the reference; taper/render assets do not
    claim pixel-identical TH06 appearance or collision.
    """
    easy = ctx.difficulty in ('easy', 'normal')
    lasers = []
    for outer in range(2):
        base = (-math.pi if outer == 0 else -7 * math.pi / 8) + angle_offset
        delta = math.pi / 4 if outer == 0 else -math.pi / 4
        headings = base + np.arange(8, dtype=np.float64) * math.pi / 4
        positions = np.column_stack((
            center[0] + np.cos(headings) * 32 / PIXELS_PER_UNIT,
            center[1] - np.sin(headings) * 32 / PIXELS_PER_UNIT,
        ))
        for layer in range(3):
            link = 112.0 if layer < 2 else 480.0
            length = (link if easy else 440.0) / PIXELS_PER_UNIT
            for i, heading in enumerate(headings):
                laser = ctx.create_laser(
                    *positions[i], angle=-math.degrees(heading),
                    l1=0.0, l2=length, l3=0.0,
                    width=(28.0 if easy else 20.0) / PIXELS_PER_UNIT,
                    color=2 if easy else 8,
                )
                if laser is None:
                    raise RuntimeError('the 48-laser pattern exceeded LaserPool capacity')
                laser.configure_lifecycle(
                    warning_frames=60 + layer * 16,
                    active_frames=90 - layer * 16, fade_frames=16,
                    hitbox_delay=50, hitbox_fade_frames=16,
                    transition_hitbox='midpoint',
                )
                lasers.append(laser)
            positions[:, 0] += np.cos(headings) * link / PIXELS_PER_UNIT
            positions[:, 1] -= np.sin(headings) * link / PIXELS_PER_UNIT
            headings += delta
    return lasers


def fire_along_lasers(ctx, lasers, *, angle=-90.0, speed=12.0, tag=614):
    """StageXFunc14: sample living ray segments at strictly less than the end."""
    points = [laser.sample_points(48.0 / PIXELS_PER_UNIT)
              for laser in lasers if laser.alive]
    if not points:
        return np.empty(0, dtype=np.int32)
    return ctx.create_bullets_batch(
        positions=np.concatenate(points), angles=angle, speeds=speed,
        bullet_type='grain_a', color='blue', tag=tag,
    )


class FakeBoss(EnemyScript):
    """A shootable decoy: hits trigger a counterattack but never remove HP."""

    hp = 300
    sprite = 'enemy1'
    hitbox_radius = 0.06

    def __init__(self):
        super().__init__()
        self.hit_reactions = 0
        self.next_reaction = 0

    async def on_spawn(self):
        self.set_interaction(damageable=False)
        self.set_movement_bounds(-0.8, 0.8, -0.2, 0.7)

    async def on_hit(self, damage):
        if self.time < self.next_reaction:
            return
        self.next_reaction = self.time + 12
        self.hit_reactions += 1
        self.fire_circle(count=32, speed=18.0, color='purple', play_sound=False)
        await self.wait(4)
        self.fire_circle(count=32, speed=12.0, start_angle=5.625,
                         color='red', play_sound=False)

    async def run(self):
        while True:
            await self.move_to(-0.55, 0.3, 45, easing='ease_out_fast')
            await self.move_to(0.55, 0.3, 45, easing='ease_in_fast')


@preview(seed=1337, boss_pos=(0.0, 0.5), duration=420)
class ControlMechanicsSpell(SpellCard):
    """One spell usable both in a real Boss phase and standalone preview."""

    name = '移动、假身与交错激光'
    time_limit = 12.0

    async def run(self):
        self.fake = FakeBoss()
        self.fake.bind(self.ctx, -0.55, 0.3)
        self.fake.start()
        self.ctx.add_enemy_script(self.fake)
        self.boss.set_movement_bounds(-0.65, 0.65, 0.2, 0.8)
        await self.boss.move_to(0.25, 0.6, 45, easing='ease_out')

        self.lasers = crossed_lasers(self.ctx, (self.boss.x, self.boss.y), angle_offset=0.15)
        await self.wait(166)

        # A moving finite segment uses the same Laser, renderer and hitbox.
        laser = self.ctx.create_laser(
            -0.8, 0.65, -25.0, 0.0, 0.5, 0.0, 0.06, color='blue',
        )
        if laser is None:
            raise RuntimeError('moving-laser example exceeded LaserPool capacity')
        laser.configure_motion(speed=0.6, start_offset=0.0, end_offset=0.1, length=0.5)
        laser.configure_lifecycle(warning_frames=24, active_frames=120, fade_frames=16)
        for _ in range(8):
            await self.wait(12)
            self.track_bullets(fire_along_lasers(self.ctx, [laser]))
        await self.wait(64)


class ControlMechanicsStage(StageScript):
    id = 'th06_controls'
    name = 'TH06 控制机制示例'
    boss = BossDef(
        'controls_boss', '机制示例', '',
        [spellcard(ControlMechanicsSpell, '', hp=1000, time=12.0, bonus=0)],
    )

    async def run(self):
        await self.run_boss(self.boss)


class TimeStopMechanicsSpell(SpellCard):
    """The controller keeps running while projectiles and countdown stop."""

    name = '时停机制'
    time_limit = 3.0

    async def run(self):
        count = 96 if self.ctx.difficulty in ('easy', 'normal') else 192
        self.fire_circle(count=count, speed=6, color='blue', play_sound=False)
        laser = self.ctx.create_laser(-0.8, 0.6, -25, 0, 1.5, 0, 0.04)
        if laser is None:
            raise RuntimeError('time-stop example exceeded LaserPool capacity')
        laser.configure_lifecycle(warning_frames=10, active_frames=120, fade_frames=12)
        await self.wait(15)
        with self.ctx.stop_time():
            # One ordinary task controls the frozen world. finally/with releases
            # it on death, phase end, seek, restart and runtime exceptions.
            await self.wait(60)
        await self.wait(60)


class BombAwareBat(EnemyScript):
    """HandleBatTransformation: same enemy, unhittable during Bomb + 60 frames."""

    sprite = 'enemy1'

    async def run(self):
        remaining = 0
        while True:
            if self.ctx.get_player().is_bombing:
                remaining = 60
                self.set_interaction(interactable=False, visible=False)
            elif remaining > 0:
                remaining -= 1
                if remaining == 0:
                    self.set_interaction(interactable=True, visible=True)
            await self.wait(1)


__all__ = [
    'crossed_lasers', 'fire_along_lasers', 'FakeBoss',
    'ControlMechanicsSpell', 'ControlMechanicsStage',
    'TimeStopMechanicsSpell', 'BombAwareBat',
]
