"""Ordinary PythonSTG content for TH07 stage 5 Youmu, source Sub37--77.

The source ECL and matching 1.00b decompilation determine the formulas here.
ExIns12/13/14/21 are snapshot/batch operations, not a VM or per-bullet tasks.
Full original ANM transforms and source RNG consumed by effects remain separate
resource fidelity work; the gameplay code does not claim replay equivalence.
"""

from __future__ import annotations

from contextlib import contextmanager
import math

import numpy as np
from numba import njit

from src.core.collision_shapes import Hitbox
from src.game.stage.boss_base import BossPhase, BossPhaseType

from .common import TH07Enemy, TH07Spell, damage_rule, bullet_speed, px, py, to_source_damage
from .resources import source_sprite
from .road import Timeline1Enemies, drop_power_or_points


SPELL_NAMES = (
    ('幽鬼剣「妖童餓鬼の断食 -Easy-」', '幽鬼剣「妖童餓鬼の断食」',
     '餓鬼剣「餓鬼道草紙」', '餓王剣「餓鬼十王の報い」'),
    ('獄界剣「二百由旬の一閃 -Easy-」', '獄界剣「二百由旬の一閃」',
     '獄炎剣「業風閃影陣」', '獄神剣「業風神閃斬」'),
    ('畜趣剣「無為無策の冥罰 -Easy-」', '畜趣剣「無為無策の冥罰」',
     '修羅剣「現世妄執」', '修羅剣「現世妄執 -Lunatic-」'),
    ('人界剣「悟入幻想 -Easy-」', '人界剣「悟入幻想」',
     '人世剣「大悟顕晦」', '人神剣「俗諦常住」'),
    ('天上剣「天人の五衰 -Easy-」', '天上剣「天人の五衰」',
     '天界剣「七魄忌諱」', '天神剣「三魂七魄」'),
)
SPELL_IDS = tuple(tuple(range(first, first + 4)) for first in (68, 72, 76, 80, 84))


def normalize_angle(angle):
    while angle > math.pi:
        angle -= math.tau
    while angle < -math.pi:
        angle += math.tau
    return angle


def source_exit_angle(owner, bounds):
    """Opcode52 including its original right-boundary current-angle quirk."""
    x, y = owner.source_position
    player_x = owner.ctx.get_player().x * 192 + 192
    angle = (normalize_angle(owner.rng.random() * math.pi / 2 + 3 * math.pi / 4)
             if player_x < x else owner.rng.random() * math.pi / 2 - math.pi / 4)
    left, top, right, bottom = bounds
    if x < left + 96:
        if angle > math.pi / 2:
            angle = math.pi - angle
        elif angle < -math.pi / 2:
            angle = -math.pi - angle
    if x > right - 96:
        if 0 <= angle < math.pi / 2:
            angle = math.pi - getattr(owner, 'source_move_angle', 0.)
        elif -math.pi / 2 < angle <= 0:
            angle = -math.pi - angle
    if y < top + 48 and angle < 0:
        angle = -angle
    if y > bottom - 48 and angle > 0:
        angle = -angle
    return angle


def _bounds(owner, bounds):
    left, top, right, bottom = bounds
    owner.source_bounds = bounds
    owner.boss.set_movement_bounds(px(left), px(right), py(bottom), py(top))


def _clear_enemies(ctx):
    for enemy in tuple(ctx.get_enemy_scripts()):
        if not isinstance(enemy, Timeline1Enemies):
            enemy.kill()


def _clear_bullets(ctx, *, reward=True):
    if reward:
        ctx.bullets_to_items(ctx.read_bullets(fields=()).group)
    ctx.clear_all_bullets()
    ctx.clear_all_lasers()


@contextmanager
def sword_charge(owner, divisor=3):
    """ExIns10/11: scoped slowdown and generation-safe arrow color restore."""
    registry = owner.ctx.bullet_pool.sprite_registry
    indices = np.asarray([registry.get_index(source_sprite(6, c)) for c in range(16)])
    snapshot = owner.ctx.read_bullets(fields=('sprite_idx',))
    arrows = snapshot.select(np.isin(snapshot['sprite_idx'], indices))
    if len(arrows):
        owner.ctx.transform_bullets(arrows.group,
                                   sprite_indices=registry.get_index(source_sprite(6, 15)))
    background = owner.state.background_controller
    if background is not None:
        background.set_slash(True)
    try:
        with owner.ctx.slow_motion(1. / divisor):
            yield
    finally:
        if background is not None:
            background.set_slash(False)
        if len(arrows):
            owner.ctx.transform_bullets(arrows.group, sprite_indices=arrows['sprite_idx'])


@njit(cache=True)
def _split_random(seed, count, upward, second):
    """Nine U16 draws per child: XY, sprite, angle, acceleration in source order."""
    values = np.empty((count, 5), np.float32)
    for row in range(count):
        for column in range(5):
            tmp = ((seed ^ 0x9630) - 0x6553) & 0xffff
            seed = (((tmp & 0xc000) >> 14) + tmp * 4) & 0xffff
            if column == 2:
                values[row, column] = seed % 3
                continue
            high = seed
            tmp = ((seed ^ 0x9630) - 0x6553) & 0xffff
            seed = (((tmp & 0xc000) >> 14) + tmp * 4) & 0xffff
            unit = np.float32((high << 16) | seed) / np.float32(4294967296.)
            if column < 2:
                values[row, column] = unit * 32 - 16
            elif column == 3:
                angle = unit * np.float32(3 * math.pi / 2)
                angle += np.float32(math.pi / 4 if upward else -math.pi / 2)
                if angle > math.pi:
                    angle -= 2 * math.pi
                values[row, column] = angle
            else:
                values[row, column] = unit * np.float32(.008) + np.float32(.01)
    return seed, values


def burst_large_bullets(owner, upward=False, *, second=False):
    """ExIns12/21: one bounded numerical emission, preserving source RNG order."""
    snapshot = owner.ctx.read_bullets(fields=('pos', 'sprite_idx'))
    registry = owner.ctx.bullet_pool.sprite_registry
    large = np.asarray([registry.get_index(source_sprite(10, c)) for c in range(4)])
    source_y = 224 - snapshot['pos'][:, 1] * 192
    height = (128 if owner.diff == 2 else 180) if second else (64 if owner.diff < 2 else 48)
    selected = snapshot.select(np.isin(snapshot['sprite_idx'], large)
                               & (source_y > owner.sy - height) & (source_y < owner.sy + height))
    owner.ctx.flash_screen((207/255, 207/255, 1., 80/255), 8)
    if not len(selected):
        return 0
    per_parent = 15 if second else owner.rank((10, 18, 22, 25))
    count = len(selected) * per_parent
    owner.rng.seed, randoms = _split_random(owner.rng.seed, count, upward, second)
    owner.rng.generation += count * 9
    positions = np.repeat(selected['pos'], per_parent, axis=0).copy()
    positions[:, 0] += randoms[:, 0] / 192
    positions[:, 1] -= randoms[:, 1] / 192
    styles = np.asarray((0, 3, 7))[randoms[:, 2].astype(np.int32)]
    colors = np.where(styles == 7, 2 if second else 1, 4 if second else 2)
    sprite_indices = np.asarray([
        registry.get_index(source_sprite(style, color))
        for style, color in zip(styles, colors)
    ], np.int32)
    angles = randoms[:, 3]
    warmup = np.zeros(count, np.float32)
    if not second:
        warmup_mask = np.tile(np.arange(per_parent) & 1, len(selected)).astype(bool)
        for style in (0, 3, 7):
            mask = warmup_mask & (styles == style)
            warmup[mask] = owner.state.assets.manifest['bullet_spawns'][str(style)]['fast']['end_frame']
        positions[warmup_mask, 0] -= np.cos(angles[warmup_mask]) * .4 / 192
        positions[warmup_mask, 1] += np.sin(angles[warmup_mask]) * .4 / 192
    born = owner.ctx.create_bullets_batch(positions=positions, angles=-np.rad2deg(angles),
                                         speeds=bullet_speed(np.full(count, .1)),
                                         sprite_id=source_sprite(0, 2),
                                         hitbox=Hitbox.box(4/192, 4/192))
    group = owner.ctx.capture_bullets(born)
    n = len(group)
    sizes = np.where(styles[:n] == 0, 4., np.where(styles[:n] == 3, 6., 10.)) / 192
    owner.ctx.transform_bullets(group, sprite_indices=sprite_indices[:n],
                               hitbox_size=np.column_stack((sizes, sizes)))
    owner.ctx.configure_bullet_birth(group, warmup_frames=warmup[:n],
                                    motion_factor=np.where(warmup[:n] > 0, .5, 1.),
                                    offscreen_grace_frames=warmup[:n])
    owner.ctx.set_bullet_behavior(group, stages=(
        {'frames': 100, 'accel': randoms[:n, 4] * (216000. / 192)}, {},
    ))
    owner.ctx.remove_bullets(selected.group)
    owner.state.emitted += n
    owner.state.dropped_bullets += count - n
    return n


def _markers(owner):
    """Numeric source state2, bound to slot generation rather than Python objects."""
    state = owner.state
    if not hasattr(state, '_sword_generations'):
        capacity = len(owner.ctx.bullet_pool.data)
        state._sword_generations = np.zeros(capacity, np.uint64)
        state._sword_marks = np.zeros(capacity, np.uint8)
    return state._sword_generations, state._sword_marks


def curve_bullets_below(owner):
    """ExIns13, one snapshot/NumPy selection and one numerical behavior write."""
    snapshot = owner.ctx.read_bullets(fields=('pos', 'speed'))
    generations, marks = _markers(owner)
    ids = snapshot.group.indices
    tagged = (generations[ids] == snapshot.group.generations) & (marks[ids] != 0)
    x = snapshot['pos'][:, 0] * 192 + 192
    y = 224 - snapshot['pos'][:, 1] * 192
    selected = snapshot.select(~tagged & (y > owner.sy) & (y < 352)
                               & (x > owner.sx - 16) & (x < owner.sx + 16))
    if not len(selected):
        return
    ids = selected.group.indices
    owner.ctx.set_bullet_behavior(selected.group, stages=(
        {'frames': 160, 'accel': -selected['speed'] / 3.,
         'turn_rate': np.where(ids & 1, -180., 180.)}, {},
    ))
    generations[ids] = selected.group.generations
    marks[ids] = 1


def redirect_curved_bullets(owner):
    """ExIns14: store one player-aimed vector for each marked bullet, then coast."""
    snapshot = owner.ctx.read_bullets(fields=('pos',))
    generations, marks = _markers(owner)
    ids = snapshot.group.indices
    selected = snapshot.select((generations[ids] == snapshot.group.generations) & (marks[ids] == 1))
    owner.ctx.flash_screen((207/255, 207/255, 1., 80/255), 16)
    if len(selected):
        player = owner.ctx.get_player()
        delta = np.asarray((player.x, player.y)) - selected['pos']
        angles = np.arctan2(delta[:, 1], delta[:, 0])
        acceleration = np.column_stack((np.cos(angles), np.sin(angles))) * (2/75 * 216000/192)
        owner.ctx.set_bullet_behavior(selected.group, stages=(
            {'frames': 90, 'vector_accel': acceleration}, {},
        ))
        marks[selected.group.indices] = 2


async def _charge_effect(owner, count=30, particles=4):
    owner.sound(5)
    for _ in range(count):
        owner.effect(33, particles, -8355585)
        await owner.wait(4)


async def _slash(owner, target, *, right, divisor=3, charge=30, particles=4):
    await _charge_effect(owner, charge, particles)
    with sword_charge(owner, divisor):
        owner.sound(35)
        owner.animate(137 if right else 139)
        await owner.wait(20)
        owner.animate(133 if right else 135)
        await owner.wait(30)
        owner.boss.set_position(px(target[0]), py(target[1]))
    owner.sound(15)
    owner.animate(134 if right else 136)


class HorizontalSlash(TH07Enemy):
    """Sub61 collision strip: its 56-frame life is not just an animation."""

    hp = 1
    score = 10
    sprite = ''

    async def run(self):
        self.set_interaction(collidable=False, damageable=False)
        self.set_contact_hitbox(Hitbox.box(256/192, (32/1.5)/192))
        self.animate(143)
        await self.wait(56)


class VerticalSlash(TH07Enemy):
    """Sub65 decorative sword, not a second player damage region."""

    hp = 1
    score = 10
    sprite = ''

    async def run(self):
        self.set_interaction(collidable=False, damageable=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(144)
        await self.wait(180)


class FixedSword(TH07Enemy):
    """Sub67/68 delayed top/down bullet emitter."""

    hp = 1
    score = 10
    sprite = ''

    def __init__(self, *, upward=False):
        super().__init__()
        self.upward = upward

    async def run(self):
        self.set_interaction(collidable=False, damageable=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(147 if self.upward else 146)
        await self.wait(120)
        spread = math.pi / 6 if self.upward else self.rng.random() * (-math.pi / 24) + math.pi / 6
        for index in range(5):
            self.emit(2, 10 if self.upward else 6, self.rank((2, 4, 4, 4)), 2,
                      self.rank((1.8, 2.4, 2.4, 2.4)) if self.upward else 2.9,
                      1., -math.pi / 2 if self.upward else math.pi / 2, spread, 514,
                      offset=(0, (160-index*32) * (1 if self.upward else -1)))
            await self.wait(12)


class PermanentSlash(TH07Enemy):
    """Sub74: literal 4412x32 unshootable collision strip until phase clear."""

    hp = 30000
    score = 10
    sprite = ''

    async def run(self):
        self.set_interaction(collidable=False, damageable=False)
        self.set_contact_hitbox(Hitbox.box((4412/1.5)/192, (32/1.5)/192))
        self.animate(145)
        await self.wait(30000)


class EdgeStream(TH07Enemy):
    """Sub63 / Sub72 hidden, invulnerable stage actors, never bullet objects."""

    hp = 1
    score = 10
    sprite = ''

    def __init__(self, *, bottom=False):
        super().__init__()
        self.bottom = bottom

    async def run(self):
        self.set_interaction(damageable=False, visible=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(26)
        if self.bottom:
            count, delay = 0, 4
            width = self.rank((.4, .5, .6, .8))
            while True:
                # Sub72 computes and overwrites these two random fields.
                self.rng.random()
                self.rng.random()
                x = self.rng.random() * 384
                y = self.rng.random() * 32 + 420
                speed = self.rng.random() * width + .3
                self.emit(2, 6, 1, 1, speed, 1., -math.pi / 2, math.pi / 8, 514,
                          aim_mode=3, position=(x, y))
                count += 1
                width += .001
                if count % 60 == 0 and delay > 0:
                    delay -= 1
                await self.wait(delay + self.rank((8, 6, 4, 3)))
        else:
            while True:
                y = self.rng.random() * 448
                speed = self.rng.random() * self.rank((.5, .5, .5, .9)) + .5
                self.emit(1, 6, 1, 1, speed, 1., 0., math.pi / 8, 514,
                          aim_mode=3, position=(-4, y))
                if self.diff == 2:
                    await self.wait(1)
                y = self.rng.random() * 448
                await self.wait(2)
                speed = self.rng.random() * self.rank((.5, .5, .5, .9)) + .5
                self.emit(1, 2, 1, 1, speed, 1., math.pi, math.pi / 8, 514,
                          aim_mode=3, position=(388, y))
                await self.wait(2)


class SoulEmitter(TH07Enemy):
    """Sub76: sparse moving spirit emits numerical arrow bullets."""

    hp = 1
    score = 10
    sprite = ''

    def __init__(self, *, direction=0., color=2):
        super().__init__()
        self.direction, self.color = direction, color

    async def run(self):
        self.set_interaction(damageable=False, visible=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(26)
        self.spawn_task(self.move_polar_source(self.direction, self.rank((6., 4.2, 4.2, 4.2))),
                        immediate=True)
        radial, layers = 60., 1
        for _ in range(self.rank((30, 45, 45, 45))):
            grace = int(radial)
            # The source consumes this random-sign instruction but never uses it.
            self.rng.integers(0, 2)
            angle = self.rng.random() * math.tau - math.pi
            origin = self.sx + math.cos(angle)*radial, self.sy + math.sin(angle)*radial
            radial -= .5
            layers = 3 - layers
            commands = ((0, 8192, 0, grace, -1, -1., -1.),
                        (1, 32, 0, 60, -1, .025, 0.))
            self.emit(6, self.color, 1, layers, 1., .4, angle + math.pi, 0., 8740,
                      position=origin, commands=commands)
            await self.wait(1)


class _YoumuEntrance(TH07Spell):
    def __init__(self, *, midboss=False):
        super().__init__()
        self.midboss = midboss

    async def run(self):
        self.boss.set_hitbox(Hitbox.box(48/192, 64/192))
        self.boss.set_contact_hitbox(enabled=False)
        self.boss.set_interaction(damageable=False)
        self.boss.clear_movement_bounds()
        self.boss.set_position(px(-32), py(32))
        self.animate(128)
        await self.move_source(192, 128 if self.midboss else 112, 60, easing=4)
        await self.wait(220)
        self.animate(135)
        while True:
            await self.wait(10000)


async def _entrance(boss, ctx, *, midboss):
    entrance = _YoumuEntrance(midboss=midboss)
    entrance.bind(boss, ctx)
    try:
        await entrance.run()
    finally:
        entrance.dispose()


async def enter_midboss(boss, ctx):
    await _entrance(boss, ctx, midboss=True)


async def enter_youmu(boss, ctx):
    await _entrance(boss, ctx, midboss=False)


class _YoumuSpell(TH07Spell):
    clear_on_end = False

    async def open_card(self, x, y, *, delay=0, timer=None):
        _clear_bullets(self.ctx)
        _clear_enemies(self.ctx)
        self.boss.clear_movement_bounds()
        self.boss.set_contact_hitbox(Hitbox.box(32/192, (64/1.5)/192))
        self.boss.set_interaction(damageable=False, interactable=True)
        if delay:
            await self.wait(delay)
        self.state.is_spell = True
        self.declared = True
        self.boss.declare_spell()
        if timer is not None:
            self.time_limit = timer
        self.set_timer(0)
        await self.move_source(x, y, 120, easing=4)
        self.boss.set_interaction(damageable=True)
        self.protected_until = self.time + 240
        self.animate(128)

    async def random_move(self, frames, speed, pause=None):
        angle = source_exit_angle(self, self.source_bounds)
        self.source_move_angle = normalize_angle(angle)
        x, y = self.source_position
        self.spawn_task(self.move_source(x+math.cos(angle)*speed*frames,
                                         y+math.sin(angle)*speed*frames,
                                         frames, easing=4), immediate=True)
        if pause is not None:
            await self.wait(pause)


class YoumuNonspell(_YoumuSpell):
    """Sub38/48 normal patterns; synchronous Sub calls preserve caller time."""

    hp = 19000
    time_limit = 60
    midboss = False

    async def run(self):
        self.boss.set_interaction(damageable=True, interactable=True)
        self.boss.set_hitbox(Hitbox.box(48/192, 64/192))
        self.boss.set_contact_hitbox(Hitbox.box(32/192, (64/1.5)/192))
        self.protected_until = self.time + (60 if self.midboss else 240)
        for _ in range(6):
            self.effect(13)
            await self.wait(10)
        _bounds(self, (32, 48, 352, 128))
        self.source_move_angle = 0.
        while True:
            await self.curved_pair(128 if self.midboss else 96, 8, 13,
                                   self.rank((6, 8, 12, 15)), first=True)
            await self.wait(100)
            await self.random_move(60, 1.5, 60)
            await self.curved_pair(160 if self.midboss else 96,
                                   11 if self.midboss else 10, 14,
                                   self.rank((8, 10, 14, 18)), first=False)
            await self.wait(90)
            await self.random_move(60, 1.5, 60)
            for right, frames in ((True, 50), (False, 30), (True, 10), (False, 60)):
                await self.side_sweep(right)
                await self.random_move(frames, 2.5 if frames != 60 else 1.5,
                                       frames if frames != 60 else 100)

    async def curved_pair(self, radius, color_a, color_b, maximum, *, first):
        self.animate(135)
        angle = self.aim_source()
        c, s = math.cos(angle), math.sin(angle)
        radial = radius if self.midboss else radius*1.5
        theta, ways = 0., 1
        commands = ((0, 8192, 0, 160, -1, -1., -1.),)
        for _ in range(16 if self.midboss else 32):
            for sign, color in ((1, color_a), (-1, color_b)):
                x, y = self.source_position
                wave = math.sin(theta) * radius * sign
                origin = x+radial*c-wave*s*(1. if self.midboss else 1.4), y+radial*s+wave*c
                radial -= radius/16
                theta += math.pi/32
                self.emit(3, color, ways, 1,
                          self.rank((1., 1.2, 1.3, 1.4)) if self.midboss else self.rank((1.4, 1.4, 1.4, 1.6)),
                          1., angle,
                          self.rank((math.pi/10, math.pi/10, math.pi/14, math.pi/18)) if self.midboss
                          else self.rank((math.pi/5, math.pi/9, math.pi/12, math.pi/15)),
                          8706, commands=commands, position=origin)
                await self.wait(3 if self.midboss or not first else 5)
                if sign < 0:
                    if self.midboss and ways < 12:
                        ways += self.rank((1, 3, 3, 3))
                    elif not self.midboss and ways < maximum:
                        ways += 1
        self.animate(128)

    async def side_sweep(self, right):
        self.animate(135 if right else 133)
        await _charge_effect(self, 4, 32)
        self.animate(136 if right else 134)
        self.sound(2)
        x = self.rng.random()*32+(368 if right else -16)
        y = self.rng.random()*128-64
        dy = y/8
        for _ in range(16):
            self.emit(6, 6 if right else 2,
                      (1 if right else 2) if self.midboss else (3 if right else 4),
                      self.rank((2, 4, 4, 4)) if self.midboss else 4,
                      self.rank((3.5, 3.5, 4., 5.)) if self.midboss else self.rank((3., 3.5, 4.5, 5.2)),
                      self.rank((1.5, 1., 1., 1.)) if self.midboss else 1., 0.,
                      (math.pi/8 if right else math.pi/6) if self.midboss
                      else self.rank((math.pi/6, math.pi/6, math.pi/8, math.pi/10)),
                      520 if self.midboss else 516, aim_mode=0,
                      position=(x, self.sy+y))
            x += -24 if right else 24
            y -= dy
            await self.wait(2)
        await self.wait(1)
        self.animate(128)


class YoumuMidNonspell(YoumuNonspell):
    hp = 15000
    midboss = True

    async def on_defeated(self):
        if self.end_reason != 'threshold':
            await retreat_midboss(self, True)

    async def on_timeout(self):
        await retreat_midboss(self, False)


async def retreat_midboss(owner, rewarded):
    _clear_bullets(owner.ctx)
    _clear_enemies(owner.ctx)
    if rewarded:
        drop_power_or_points(owner, 7)
        owner.drop(1, 7)
        owner.drop(5)
        owner.sound(18)
    owner.boss.clear_movement_bounds()
    owner.boss.set_interaction(damageable=False, interactable=False)
    owner.boss.set_contact_hitbox(enabled=False)
    await owner.move_source(-128, 32, 60, easing=4)


class HungryGhostSword(_YoumuSpell):
    hp = 1500
    time_limit = 50

    async def run(self):
        await self.open_card(64 if self.diff < 2 else 320, self.rank((128, 128, 192, 256)))
        while True:
            if self.diff < 2:
                for target, right in ((320, True), (64, False)):
                    await self.slash_ring((target, self.sy), right)
                    await self.wait(90)
            else:
                # The source does not wait 90 frames between H/L slashes.
                for target, right in ((64, False), (320, True)):
                    await self.slash_ring((target, self.sy), right)

    async def slash_ring(self, target, right):
        await _slash(self, target, right=right)
        self.spawn_source(HorizontalSlash, 192, self.sy-7)
        await self.wait(30)
        x = self.rng.random()*32+(-16 if right else 368)
        for _ in range(16):
            for second in (False, True):
                turn = ((self.rng.random()*math.tau-math.pi)/600 if self.diff >= 2
                        else (-math.pi/60 if second else math.pi/60))
                angle = self.rng.random()*math.tau-math.pi
                commands = [(0, 8192, 0, 160, -1, -1., -1.),
                            (1, 32, 1, 90, -1, .015 if self.diff >= 2 else -.01, turn)]
                if self.diff < 2:
                    commands.append((2, 32, 0, 90, -1, .025, 0.))
                if second:
                    ways = self.rank((10, 18 if right else 14, 18, 12))
                    speed, flags = (.9 if self.diff < 2 else .3), 8738
                else:
                    ways = self.rank((12 if right else 8, 18 if right else 10, 18, 18))
                    speed, flags = (1.5 if self.diff < 2 else .5), (8724 if self.diff == 3 else 8740)
                self.emit(6, 6, ways, 1, speed, 1., angle, math.pi/8, flags,
                          aim_mode=3, position=(x, self.sy), commands=commands)
            x += 24 if right else -24
            await self.wait(2)

    async def on_defeated(self):
        await retreat_midboss(self, True)

    async def on_timeout(self):
        await retreat_midboss(self, False)


class TwoHundredYojana(_YoumuSpell):
    hp = 2000
    time_limit = 55

    async def _large_bullets(self):
        angle, speed, index = -math.pi/32, .6, 0
        while True:
            await self.wait(self.rank((9, 7, 6, 6)))
            index %= 64
            speed = (3.6 if self.diff == 3 else 2.5)-speed
            self.emit(10, 1, 1, 1, speed, 1., angle, math.pi/8, 514,
                      aim_mode=3, position=(192, 32))
            angle += (1 if index < 32 else -1)*.10431069
            index += 1

    async def run(self):
        await self.open_card(192, 64)
        self.spawn_task(self._large_bullets(), immediate=True)
        self.spawn_task(self.move_source(48, 192, 60, easing=4), immediate=True)
        await self.wait(90)
        while True:
            for target, right in ((320, True), (64, False)):
                await _slash(self, (target, self.sy), right=right)
                for offset in ((-7, 57, -71) if self.diff == 2 else
                               (-7, 49, -63, 105, -119) if self.diff == 3 else (-7,)):
                    self.spawn_source(HorizontalSlash, 192, self.sy+offset)
                await self.wait(60)
                burst_large_bullets(self, upward=not right)
                if self.diff >= 2:
                    burst_large_bullets(self, upward=not right, second=True)
                self.sound(35)
                await self.wait(90)


class YoumuSecondNonspell(_YoumuSpell):
    hp = 15000
    time_limit = 60

    async def run(self):
        self.state.is_spell = False
        self.boss.set_interaction(damageable=True, interactable=True)
        self.boss.set_contact_hitbox(Hitbox.box(32/192, (64/1.5)/192))
        self.protected_until = self.time+240
        drop_power_or_points(self, 7)
        self.drop(1, 7)
        await self.wait(40)
        self.spawn_task(self.move_source(128 if self.sx < 192 else 256, 96, 40, easing=4), immediate=True)
        await self.wait(60)
        _bounds(self, (32, 48, 352, 128))
        while True:
            await self.fan_pair(8, 13)
            await self.random_move(60, 1.5, 60)
            await self.fan_pair(2, 6)
            await self.jade_pair()
            await self.fan_pair(2, 6)
            await self.random_move(60, 1.5, 120)

    async def fan_pair(self, first, second):
        self.animate(135)
        angle = self.aim_source()
        a, b, back = angle+math.pi/7, angle-math.pi/7, angle-math.pi
        for ways in range(1, 9):
            for theta, color, flags in ((a, first, 516), (b, second, 4)):
                self.emit(3, color, ways, 1, 2., 1., theta, math.pi/12, flags)
            await self.wait(4)
            for theta, color, flags in ((a, second, 516), (b, first, 4)):
                self.emit(3, color, ways, self.diff+1, self.rank((2.5, 3.5, 4.2, 5.3)),
                          1., theta, math.pi/32, flags)
            self.emit(3, first, 16, 1, 4., 1., back, math.pi/16, 516)
            await self.wait(4)

    async def jade_pair(self):
        await _charge_effect(self, 4, 32)
        await self.wait(10)
        self.animate(142)
        for color, x, spacing in ((3, -32, 1), (1, 32, 2)):
            self.sound(15)
            for index in range(8):
                self.emit(9, color, 1, 1, 1.2+index*.25, 1., 0., math.pi/12, 516,
                          aim_mode=0, offset=(x, 0))
                await self.wait(spacing)


class WorldlyObsession(_YoumuSpell):
    hp = 2000
    time_limit = 60

    async def _curve(self):
        while True:
            curve_bullets_below(self)
            await self.wait_control(1)

    async def run(self):
        await self.open_card(192, 64)
        await self.wait(90)
        self.spawn_source(EdgeStream, 0, 0)
        await self.wait(120)
        while True:
            self.animate(137)
            await _charge_effect(self, 30, 8)
            self.animate(141)
            self.spawn_source(VerticalSlash, self.sx, 248)
            self.sound(35)
            curve = self.spawn_task(self._curve(), immediate=True)
            try:
                for _ in range(11):
                    await self.wait(10)
                    self.sound(35)
                with sword_charge(self, 2):
                    for _ in range(5):
                        await self.wait(10)
                        self.sound(35)
                redirect_curved_bullets(self)
            finally:
                curve.cancel()
            self.sound(15)
            await self.wait(60)
            player_x = self.ctx.get_player().x*192+192
            self.spawn_task(self.move_source(player_x, self.sy, 60, easing=4), immediate=True)
            await self.wait(60)


class InactionPunishment(_YoumuSpell):
    hp = 2000
    time_limit = 60

    async def run(self):
        await self.open_card(320, 224)
        await self.wait(20)
        while True:
            for target in (64, 320):
                start_x, distance = self.sx, target-self.sx
                # Sub69 always uses 139/135, even on its rightward return.
                await _slash(self, (target, 224), right=False)
                if target >= 192:
                    self.animate(134)
                x = start_x
                step = distance/8
                for _ in range(5):
                    self.spawn_source(FixedSword, x, 224, upward=False)
                    x += step
                    await self.wait(6)
                    self.spawn_source(FixedSword, x, 224, upward=True)
                    x += step
                    await self.wait(6)
                await self.wait(60)
                self.sound(35)


class HumanRealm(_YoumuSpell):
    """Sub55's 180-frame non-card prelude and Sub70 share the same 4400HP."""

    hp = 4400
    time_limit = 69

    async def run(self):
        self.declared = False
        self.state.is_spell = False
        self.boss.set_interaction(damageable=True, interactable=True)
        self.protected_until = self.time+240
        drop_power_or_points(self, 7)
        self.drop(1, 7)
        await self.wait(180)
        await self.open_card(352, 416, timer=66)
        await self.wait(60)
        await _slash(self, (32, self.sy), right=False, divisor=2, charge=4, particles=20)
        self.spawn_source(PermanentSlash, 192, self.sy+16)
        await self.wait(60)
        burst_large_bullets(self)
        self.sound(35)
        self.spawn_task(self.move_source(48, 96, 120, easing=4), immediate=True)
        self.spawn_source(EdgeStream, 0, 0, bottom=True)
        await self.wait(120)
        _bounds(self, (32, 48, 352, 112))
        while True:
            await self.random_move(60, 1.5, 60)
            self.animate(137)
            await self.wait(30)
            self.animate(141)
            self.sound(15)
            angle, spread, speed = self.aim_source(), math.pi/4, .5
            for _ in range(self.rank((7, 12, 12, 16))):
                self.emit(7, 1, 3, 1, speed, 1., angle, spread, 514)
                self.emit(7, 1, 6, 1, speed, 1., angle+math.pi, math.pi/6, 512)
                speed += self.rank((.18, .2, .22, .3))
                spread -= .02727077
                await self.wait(2)
            await self.wait(10)


class FiveSigns(_YoumuSpell):
    hp = 2000
    time_limit = 67

    async def run(self):
        self.declared = False
        self.state.is_spell = False
        drop_power_or_points(self, 7)
        self.drop(1, 7)
        await self.wait(60)
        await self.open_card(192, 96, timer=66)
        _bounds(self, (64, 48, 320, 128))
        while True:
            self.animate(137)
            await self.wait(12)
            with sword_charge(self, 3):
                self.sound(35)
                await _charge_effect(self, 10, 8)
                await self.wait(8)
            self.animate(141)
            self.sound(15)
            angle = self.aim_source()
            for color, offset in ((2, 0.), (4, -math.pi/5), (4, -math.pi/5),
                                   (6, -2*math.pi/5), (14, math.pi/5), (13, 2*math.pi/5)):
                self.spawn_source(SoulEmitter, *self.source_position,
                                  direction=angle+offset, color=color)
            if self.diff >= 2:
                for color, offset in ((8, -3*math.pi/5), (11, 3*math.pi/5)):
                    self.spawn_source(SoulEmitter, *self.source_position,
                                      direction=angle+offset, color=color)
            if self.diff == 3:
                self.emit(10, 0, 3, 2, 3.5, 1., 0., math.pi/5, 516, aim_mode=0)
            await self.wait(60)
            await self.random_move(60, 1.5, 60)


async def finish_youmu(boss, ctx):
    """Sub56: 60 simulation frames of particle destruction, then death."""
    ending = _YoumuSpellForEnding()
    ending.bind(boss, ctx)
    ending.start()
    try:
        while ending._active:
            ending.update()
            await ctx.wait_control(1)
    finally:
        ending.dispose()


class _YoumuSpellForEnding(_YoumuSpell):
    async def run(self):
        _clear_enemies(self.ctx)
        self.boss.set_interaction(damageable=False, interactable=False)
        self.boss.set_contact_hitbox(enabled=False)
        angle = self.rng.random()*math.tau-math.pi
        self.spawn_task(self.move_source(self.sx+math.cos(angle)*9,
                                         self.sy+math.sin(angle)*9, 60, easing=4), immediate=True)
        colors = (-1, -1, -32640, -32640, -8323200, -8323200,
                  -8355585, -8355585, -128, -128)
        for _ in range(6):
            for color in colors:
                await self.wait(1)
                self.effect(22, 1, color)
            self.sound(7)
        self.sound(18)
        self.effect(22, 64, -8355585)
        _clear_bullets(self.ctx)


def _damage_rule(boss, hit):
    spell = boss.current_spellcard
    if isinstance(spell, (HumanRealm, FiveSigns)) and not getattr(spell, 'declared', False):
        damage = min(70, int(to_source_damage(hit.amount)))
        return damage//9 if spell.time < getattr(spell, 'protected_until', 0) else damage
    return damage_rule(boss, hit)


def _bonus_rule(boss, spell):
    if not getattr(spell, 'declared', False):
        return 0
    seconds = spell.time_limit
    value = int(4_000_000-spell.elapsed_seconds*(4_000_000//(int(seconds)+10)))
    return max(0, value-value%10)


def _finish_rule(boss, result):
    if result.reason == 'timeout':
        _clear_bullets(boss.ctx, reward=False)
    declared = getattr(boss.current_spellcard, 'declared', False)
    if result.phase_type is BossPhaseType.SPELLCARD and declared:
        if result.reason != 'timeout':
            _clear_bullets(boss.ctx)
        _clear_enemies(boss.ctx)
    if (result.phase_type is BossPhaseType.SPELLCARD and declared
            and result.reason in ('defeated', 'threshold')
            and result.no_miss and result.no_bomb and result.capture_failure_reason is None):
        boss.ctx.add_score(result.bonus-result.bonus%10)


def _mid_transition(boss, result):
    return 1 if result.reason == 'threshold' else len(boss.phases)


def _first_transition(boss, result):
    return 2 if result.reason == 'defeated' else 1


def _second_transition(boss, result):
    return 4 if result.reason == 'defeated' else 3


def build_midboss_phases(difficulty):
    if difficulty not in range(4):
        raise ValueError('TH07 difficulty must be 0..3')
    return [
        BossPhase(BossPhaseType.NONSPELL, 15000, 60, script_class=YoumuMidNonspell,
                  hp_threshold=1500, transition_rule=_mid_transition,
                  damage_rule=_damage_rule, finish_rule=_finish_rule),
        BossPhase(BossPhaseType.SPELLCARD, 1500, 50, script_class=HungryGhostSword,
                  name=SPELL_NAMES[0][difficulty], bonus=4_000_000, carry_hp=True,
                  auto_declaration=False, declaration_blocks_spell=False,
                  damage_rule=_damage_rule, finish_rule=_finish_rule, bonus_rule=_bonus_rule),
    ]


def build_youmu_phases(difficulty):
    if difficulty not in range(4):
        raise ValueError('TH07 difficulty must be 0..3')
    common = dict(declaration_blocks_spell=False, damage_rule=_damage_rule,
                  finish_rule=_finish_rule, bonus_rule=_bonus_rule)
    return [
        BossPhase(BossPhaseType.NONSPELL, 19000, 60, script_class=YoumuNonspell,
                  hp_threshold=2000, transition_rule=_first_transition, **common),
        BossPhase(BossPhaseType.SPELLCARD, 2000, 55, script_class=TwoHundredYojana,
                  name=SPELL_NAMES[1][difficulty], bonus=4_000_000, carry_hp=True,
                  auto_declaration=False, **common),
        BossPhase(BossPhaseType.NONSPELL, 15000, 60, script_class=YoumuSecondNonspell,
                  hp_threshold=2000, transition_rule=_second_transition, **common),
        BossPhase(BossPhaseType.SPELLCARD, 2000, 60,
                  script_class=InactionPunishment if difficulty<2 else WorldlyObsession,
                  name=SPELL_NAMES[2][difficulty], bonus=4_000_000, carry_hp=True,
                  auto_declaration=False, **common),
        BossPhase(BossPhaseType.SPELLCARD, 4400, 69, script_class=HumanRealm,
                  name=SPELL_NAMES[3][difficulty], bonus=4_000_000, hp_threshold=2000,
                  transition_rule=lambda boss, result: (5 if result.reason!='defeated' else len(boss.phases)),
                  auto_declaration=False, **common),
        BossPhase(BossPhaseType.SPELLCARD, 2000, 67, script_class=FiveSigns,
                  name=SPELL_NAMES[4][difficulty], bonus=4_000_000, carry_hp=True,
                  auto_declaration=False, **common),
    ]


__all__ = ['SPELL_IDS', 'SPELL_NAMES', 'build_midboss_phases', 'build_youmu_phases',
           'enter_midboss', 'enter_youmu', 'finish_youmu', 'sword_charge',
           'burst_large_bullets', 'curve_bullets_below', 'redirect_curved_bullets']
