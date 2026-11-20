"""TH07 stage 6 Youmu: source Sub18--27, without an ECL interpreter.

Ordinary content coroutines preserve sub-call time (it does not advance the
caller's ECL clock), emission counts, source coordinates and four difficulties.
Source references use ecldata6.ecl plus matching decomp commit 4878bf0e42a9:
EclManager.cpp / EnemyEclInstr.cpp / EnemyManager.cpp. Sprite rect playback is
not a claim that all original ANM transforms, trails and background interrupts
have been ported.
"""

from __future__ import annotations

from contextlib import contextmanager
import math

import numpy as np

from src.core.collision_shapes import Hitbox
from src.game.stage.boss_base import BossPhase, BossPhaseType

from .common import TH07Enemy, TH07Spell, damage_rule, px, py
from .resources import source_sprite
from .road import BackgroundMotes, drop_power_or_points


YOUMU_SPELL_IDS = (88, 89, 90, 91)
YOUMU_SPELL_NAMES = (
    '六道剣「一念無量劫 -Easy-」',
    '六道剣「一念無量劫」',
    '六道剣「一念無量劫 -Hard-」',
    '六道剣「一念無量劫 -Lunatic-」',
)


def normalize_angle(angle):
    """Source AddNormalizeAngle range, including its +pi boundary."""
    while angle > math.pi:
        angle -= math.tau
    while angle < -math.pi:
        angle += math.tau
    return angle


def source_exit_angle(owner, bounds):
    """Opcode52, including the source's right-edge current-angle quirk.

    This is NOT uniform(-pi, pi): first choose a horizontal sector away from
    the player, then reflect at each movement-bound margin. Bounds are source
    (left, top, right, bottom) pixels.
    """
    x, y = owner.source_position
    player = owner.ctx.get_player()
    player_x = player.x * 192 + 192
    if player_x < x:
        angle = normalize_angle(owner.rng.random() * (math.pi / 2) + 3 * math.pi / 4)
    else:
        angle = owner.rng.random() * (math.pi / 2) - math.pi / 4
    left, top, right, bottom = bounds
    if x < left + 96:
        if angle > math.pi / 2:
            angle = math.pi - angle
        elif angle < -math.pi / 2:
            angle = -math.pi - angle
    if x > right - 96:
        if 0 <= angle < math.pi / 2:
            angle = math.pi - getattr(owner, 'source_move_angle', 0.0)
        elif -math.pi / 2 < angle <= 0:
            angle = -math.pi - angle
    if y < top + 48 and angle < 0:
        angle = -angle
    if y > bottom - 48 and angle > 0:
        angle = -angle
    return angle


def _set_source_bounds(boss, bounds):
    left, top, right, bottom = bounds
    boss.set_movement_bounds(px(left), px(right), py(bottom), py(top))


def _clear_source_enemies(ctx):
    # Sub1 has canDie=0 and no death callback: RemoveAllEnemies sets its HP=0,
    # but it remains the stage-owned background-particle controller.
    for enemy in tuple(ctx.get_enemy_scripts()):
        if isinstance(enemy, BackgroundMotes):
            continue
        enemy.kill()


def _clear_source_bullets(ctx):
    snapshot = ctx.read_bullets(fields=())
    ctx.bullets_to_items(snapshot.group)
    ctx.clear_all_bullets()
    ctx.clear_all_lasers()


@contextmanager
def _sword_charge(owner):
    """ExIns10(1)/11: retain logical velocities; new runtime scales its dt.

    The source only changes existing arrow sprites. Saved generations prevent
    restoring an old color onto a newly allocated bullet after a clear.
    """
    registry = owner.ctx.bullet_pool.sprite_registry
    arrow_ids = np.asarray(
        [registry.get_index(source_sprite(6, color)) for color in range(16)],
        dtype=np.int32,
    )
    white = registry.get_index(source_sprite(6, 15))
    snapshot = owner.ctx.read_bullets(fields=('sprite_idx',))
    arrows = snapshot.select(np.isin(snapshot['sprite_idx'], arrow_ids))
    if len(arrows):
        owner.ctx.transform_bullets(arrows.group, sprite_indices=white)
    background = owner.state.background_controller
    if background is not None:
        background.set_slash(True)
    try:
        with owner.ctx.slow_motion(1.0):
            yield
    finally:
        if background is not None:
            background.set_slash(False)
        if len(arrows):
            owner.ctx.transform_bullets(arrows.group, sprite_indices=arrows['sprite_idx'])


def _bonus_rule(boss, spell):
    # BeginSpellcard: maxScore / (deadlineSeconds + 10), then round to 10.
    value = int(5_000_000 - spell.elapsed_seconds * 100_000)
    return max(0, value - value % 10)


def _finish_rule(boss, result):
    """No engine-default chips or arbitrary P/point drops on these phases."""
    if result.reason == 'timeout':
        boss.ctx.clear_all_bullets()
        boss.ctx.clear_all_lasers()
    if (result.phase_type is BossPhaseType.SPELLCARD
            and result.reason == 'defeated' and result.no_miss and result.no_bomb
            and result.capture_failure_reason is None):
        boss.ctx.add_score(result.bonus - result.bonus % 10)


def _normal_transition(boss, result):
    # Raw115(27): nonspell timeout RETREATS. Only raw148 -> Sub23 enters
    # the card. A lethal overkill follows raw107(26), not the threshold branch.
    return 1 if result.reason == 'threshold' else len(boss.phases)


async def _retreat(owner, rewarded):
    """Sub26/27: 60 simulation frames; only Sub26 grants the listed items."""
    _clear_source_bullets(owner.ctx)
    _clear_source_enemies(owner.ctx)
    if rewarded:
        drop_power_or_points(owner, 10)
        owner.drop(1, 5)  # raw154 is five point items, not a particle trail.
        owner.drop(3)     # raw124(3) is a Bomb, not an extend.
        owner.sound(18)
    owner.boss.clear_movement_bounds()
    owner.boss.set_contact_hitbox(enabled=False)
    owner.boss.set_interaction(damageable=False, interactable=False)
    await owner.move_source(-128, 32, 60, easing='ease_out')


class _YoumuEntrance(TH07Spell):
    async def run(self):
        self.boss.set_hitbox(Hitbox.box(48 / 192, 64 / 192))
        self.boss.set_contact_hitbox(enabled=False)
        self.boss.set_interaction(damageable=False)
        self.boss.clear_movement_bounds()
        self.boss.set_position(px(-32), py(32))
        self.animate(128)
        await self.move_source(192, 128, 60, easing='ease_out')
        await self.wait(220)
        self.animate(135)
        while True:
            await self.wait(10000)


async def enter_youmu(boss, ctx):
    """Start on a stage task at Timeline0/1914; cancel at interrupt19.

    Entrance is deliberately not a fake third BossPhase. The stage/dialogue
    controller owns this one ordinary task and cancels it before starting the
    two actual battle phases.
    """
    entrance = _YoumuEntrance()
    entrance.bind(boss, ctx)
    try:
        await entrance.run()
    finally:
        entrance.dispose()


class YoumuNonspell(TH07Spell):
    """Sub19 with synchronous Sub20/21/22 calls, not concurrent substitutes."""

    name = ''
    hp = 15000
    time_limit = 60
    clear_on_end = False

    async def run(self):
        self.boss.set_interaction(damageable=True, interactable=True)
        self.boss.set_hitbox(Hitbox.box(48 / 192, 64 / 192))
        # CheckBulletPlayerCollision divides source enemy dimensions by 1.5.
        self.boss.set_contact_hitbox(Hitbox.box(32 / 192, (64 / 1.5) / 192))
        self.protected_until = self.time + 60
        # Source creates six tracked directional effect13 owners at 10-frame
        # intervals. The adapter reports its resource-transform limitations.
        for _ in range(6):
            self.effect(13)
            await self.wait(10)
        _set_source_bounds(self.boss, (32, 48, 352, 128))
        self.source_move_angle = 0.0
        self.source_cycles = 0
        while True:
            await self._curved_pair(112, 8, 13)
            await self.wait(100)
            await self._random_move(60, 1.5, 60)
            await self._curved_pair(96, 11, 14)
            await self.wait(90)
            await self._random_move(60, 1.5, 60)
            await self._side_sweep(right=True)
            await self._random_move(50, 2.5, 50)
            await self._side_sweep(right=False)
            await self._random_move(30, 2.5, 30)
            await self._side_sweep(right=True)
            await self._random_move(10, 2.5, 10)
            await self._side_sweep(right=False)
            await self._random_move(60, 1.5, 100)
            self.source_cycles += 1

    async def _random_move(self, frames, speed, pause):
        angle = source_exit_angle(self, (32, 48, 352, 128))
        self.source_move_angle = normalize_angle(angle)
        x, y = self.source_position
        self.spawn_task(self.move_source(
            x + math.cos(angle) * speed * frames,
            y + math.sin(angle) * speed * frames,
            frames, easing='ease_out',
        ), immediate=True)
        await self.wait(pause)

    async def _curved_pair(self, radius, color_a, color_b):
        self.animate(135)
        angle = self.aim_source()
        c, s = math.cos(angle), math.sin(angle)
        radial, theta, ways = float(radius), 0.0, 1
        self.commands = [(0, 8192, 0, 160, -1, -1.0, -1.0)]
        for _ in range(16):
            for sign, color in ((1, color_a), (-1, color_b)):
                x, y = self.source_position
                wave = math.sin(theta) * radius * sign
                position = (x + radial * c - wave * s, y + radial * s + wave * c)
                radial -= radius / 16
                theta += math.pi / 32
                self.emit(
                    3, color, ways, 1, self.rank((1.0, 1.5, 1.7, 2.0)), 1.0,
                    angle, self.rank((math.pi / 10, math.pi / 10, math.pi / 11, math.pi / 12)),
                    8706, commands=self.commands, aim_mode=3, position=position,
                )
                if sign < 0 and ways < 24:
                    ways += self.rank((3, 5, 5, 5))
                await self.wait(5)
        self.animate(128)

    async def _side_sweep(self, *, right):
        self.animate(135 if right else 133)
        self.sound(5)
        for _ in range(4):
            self.effect(33, 32, -8355585)
            await self.wait(4)
        self.animate(136 if right else 134)
        self.sound(2)
        x_offset = self.rng.random() * 32 + (368 if right else -16)
        y_offset = self.rng.random() * 128 - 64
        y_step = y_offset / 8
        for _ in range(16):
            x, y = self.source_position
            # Opcode78's Y value is relative; unlike its X expression, the
            # source does not subtract the current actor Y.
            self.emit(
                6, 6 if right else 2, 1 if right else 2,
                self.rank((2, 4, 4, 4)), self.rank((3.5, 3.5, 4.0, 5.0)),
                self.rank((1.5, 1.0, 1.0, 1.0)), 0.0,
                math.pi / 8 if right else math.pi / 6,
                520, commands=self.commands, aim_mode=0,
                position=(x_offset, y + y_offset),
            )
            x_offset += -24 if right else 24
            y_offset -= y_step
            await self.wait(2)
        await self.wait(1)
        self.animate(128)

    async def on_defeated(self):
        if self.end_reason != 'threshold':
            await _retreat(self, True)

    async def on_timeout(self):
        await _retreat(self, False)


class SwordSweep(TH07Enemy):
    """Sub25: fixed sword actor with a Hermite-interpolated emission offset."""

    hp = 1
    score = 10
    sprite = ''

    def __init__(self, *, sword_angle=0.0, ring_angle=0.0):
        super().__init__()
        self.sword_angle = sword_angle
        self.ring_angle = ring_angle

    async def run(self):
        self.set_interaction(interactable=False, damageable=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(146)
        self.set_visual(rotation=-math.degrees(self.sword_angle))
        self.sound(15)
        await self.wait(60)
        # All four random-sign instructions consume RNG, even for +/-0.
        for _ in range(4):
            self.rng.integers(0, 2)
        start_x = math.cos(self.sword_angle) * 128
        start_y = math.sin(self.sword_angle) * 128
        speed = self.rank((1.0, 1.2, 1.5, 1.8))
        for shot in range(14):
            if shot == 0:
                ox, oy = self.sword_angle, self.ring_angle
            else:
                t = shot * 3 / 42
                multiplier = 1 - 2 * t * t * (3 - 2 * t)
                ox, oy = start_x * multiplier, start_y * multiplier
            x, y = self.source_position
            # The original uses the current X OFFSET as a radian angle here.
            # Retain that oddity instead of inventing a cleaner sword pattern.
            self.emit(
                6, 4, self.rank((2, 3, 3, 4)), 1, speed, 1.0,
                ox, math.pi / 8, 548, aim_mode=1,
                position=(x + ox, y + oy),
            )
            await self.wait(3)
        await self.wait(10)


class YoumuInfiniteKalpa(TH07Spell):
    """Sub23/24: one original card, including all four source variants."""

    name = YOUMU_SPELL_NAMES[1]
    hp = 1500
    time_limit = 40
    bonus = 5_000_000
    clear_on_end = False

    async def run(self):
        self.boss.set_interaction(damageable=False, interactable=True)
        _set_source_bounds(self.boss, (64, 48, 320, 256))
        _clear_source_enemies(self.ctx)
        _clear_source_bullets(self.ctx)
        self.spawn_task(self.move_source(192, 180, 120, easing='ease_out'), immediate=True)
        await self.wait(120)
        self.boss.set_interaction(damageable=True)
        self.protected_until = self.time + 240
        self.animate(128)
        while True:
            for angle_step, count in (
                (math.pi / 4, 8), (-math.pi / 4, 8),
                (3 * math.pi / 10, 12), (-3 * math.pi / 7, 16),
            ):
                await self._sword_pattern(angle_step, count)

    async def _sword_pattern(self, angle_step, count):
        self.sound(5)
        for _ in range(4):
            self.effect(33, 12, -8355585)
            await self.wait(4)
        with _sword_charge(self):
            self.sound(35)
            self.animate(137)
            await self.wait(50)
        self.animate(141)
        theta, sword_angle = 0.0, math.pi / 2
        for _ in range(count):
            x, y = self.source_position
            self.spawn_source(
                SwordSweep, x + math.cos(theta) * 112, y + math.sin(theta) * 112,
                sword_angle=sword_angle, ring_angle=theta,
            )
            theta = normalize_angle(theta + angle_step)
            sword_angle = normalize_angle(sword_angle + angle_step)
            await self.wait(3)
        await self.wait(102)

    async def on_defeated(self):
        await _retreat(self, True)

    async def on_timeout(self):
        await _retreat(self, False)


def build_youmu_phases(difficulty):
    """Two real phases; preserve the strict remaining-HP source threshold."""
    if difficulty not in range(4):
        raise ValueError('TH07 difficulty must be 0, 1, 2, or 3')
    return [
        BossPhase(
            BossPhaseType.NONSPELL, hp=15000, time_limit=60,
            script_class=YoumuNonspell, hp_threshold=1500,
            transition_rule=_normal_transition, finish_rule=_finish_rule,
            damage_rule=damage_rule,
        ),
        BossPhase(
            BossPhaseType.SPELLCARD, hp=1500, time_limit=40,
            script_class=YoumuInfiniteKalpa, name=YOUMU_SPELL_NAMES[difficulty],
            bonus=5_000_000, carry_hp=True, declaration_blocks_spell=False,
            finish_rule=_finish_rule, bonus_rule=_bonus_rule,
            damage_rule=damage_rule,
        ),
    ]


__all__ = [
    'YOUMU_SPELL_IDS', 'YOUMU_SPELL_NAMES', 'YoumuNonspell',
    'YoumuInfiniteKalpa', 'SwordSweep', 'build_youmu_phases', 'enter_youmu',
    'source_exit_angle', 'normalize_angle',
]
