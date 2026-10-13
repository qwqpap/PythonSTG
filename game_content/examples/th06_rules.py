"""Public rule-extension examples for a TH06 content port.

The raw 128P/8P denomination and rank bounds match the reference. Point scores,
extend thresholds and bonus below are deliberately simple demonstrations, NOT
the full original scoring table. Replace these ordinary callables with the
reference policies when porting the actual stages; no pool internals are used.
"""

from src.game.item import ItemType
from src.game.stage.boss_base import spellcard
from src.game.stage.spellcard import SpellCard
from src.game.stage.stage_base import BossDef, StageScript


def configure_demo_rules(ctx):
    stats, state = ctx.item_stats, ctx.run_state
    bounds = {'easy': (12, 20), 'extra': (14, 18)}
    state.min_rank, state.max_rank = bounds.get(ctx.difficulty, (10, 32))
    state.rank_event_deltas.update({'player.missed': -1600, 'player.bomb_used': -200})
    stats.max_power, stats.power_scale = 128, 32.0
    stats.power = 0
    ctx.item_config.collect_line_y = 0.5
    ctx.item_config.auto_collect_requires_full_power = True
    stats.hit_score = 0
    stats.point_rate = {'hard': 150000, 'lunatic': 200000, 'extra': 300000}.get(
        ctx.difficulty, 100000,
    )

    def collect(stats, item):
        if item.item_type in (ItemType.POWER, ItemType.POWER_LARGE, ItemType.POWER_FULL):
            value = {ItemType.POWER: 1, ItemType.POWER_LARGE: 8, ItemType.POWER_FULL: 128}[item.item_type]
            stats.power = min(stats.max_power, stats.power + value)
            stats.add_score(10)
            state.adjust_rank(1)
        elif item.item_type == ItemType.POINT:
            # Illustration only; the original height-dependent formula is not
            # replaced by this two-level demonstration in a real content port.
            stats.add_score(stats.point_rate if item.y >= 0.5 else stats.point_rate // 2)
            state.adjust_rank(30 if item.y >= 0.5 else 3)
        elif item.item_type == ItemType.FAITH_MINOR:
            stats.add_score(500)
        elif item.item_type == ItemType.EXTEND:
            stats.lives = min(stats.max_lives, stats.lives + 1)
        elif item.item_type == ItemType.BOMB:
            stats.bombs = min(stats.max_bombs, stats.bombs + 1)

    stats.on_graze = lambda stats, count: state.adjust_rank(6 * count)
    ctx.set_item_collection_rule(collect)


def demo_bonus(boss, spell):
    """One sparse Boss calculation, never a callback per projectile."""
    if spell.is_survival:
        return spell.bonus
    remaining = max(0.0, min(1.0, spell.time_remaining / spell.time_limit))
    return int(spell.bonus * (0.5 + 0.5 * remaining))


def demo_finish(boss, result):
    """Choose capture/bonus/drops and clear semantics in ordinary content."""
    captured = result.no_miss and result.no_bomb and (
        result.reason == 'defeated' or (result.is_survival and result.reason == 'timeout')
    )
    if captured:
        boss.ctx.add_score(result.bonus - result.bonus % 10)
    # clear_on_end=False was set by the phase: the actual live bullets are
    # still available here, rather than having been erased before settlement.
    boss.ctx.bullets_to_items(boss.ctx.select_bullets())
    boss.ctx.clear_all_lasers()
    boss.ctx.spawn_item(boss.x, boss.y, ItemType.POWER_LARGE)
    boss.ctx.spawn_drop(boss.x, boss.y, point=3)


class RuleMechanicsSpell(SpellCard):
    is_survival = True

    async def run(self):
        self.fire_circle(count=16, speed=0, color='blue', play_sound=False)
        while True:
            await self.wait(1)

    async def on_timeout(self):
        self.ctx.emit_event('example.spell_timeout', {'timer': self.timer_frames})
        await self.ctx.wait(1)


class RuleMechanicsStage(StageScript):
    id = 'th06_rules'
    name = '可配置规则示例'
    boss = BossDef('rules', '规则示例', '', [
        spellcard(RuleMechanicsSpell, '', hp=300, time=0.1, bonus=1000000,
                  bonus_rule=demo_bonus, finish_rule=demo_finish),
    ])

    async def run(self):
        configure_demo_rules(self.ctx)
        await self.run_boss(self.boss)
        # Stage-owned end hooks finish here; they do not outlive a stopped stage.
        await self.wait(30)


__all__ = ['configure_demo_rules', 'demo_bonus', 'demo_finish',
           'RuleMechanicsSpell', 'RuleMechanicsStage']
