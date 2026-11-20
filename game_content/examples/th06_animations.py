"""Ordinary API example using existing engine art, not original TH06 ANM.

Run: python tools/preview_spell.py game_content/examples/th06_animations.py AnimationMechanicsSpell
The stage additionally exercises a dying EnemyScript and a detached effect.
"""

from src.devtools.spell_preview import preview
from src.game.stage.boss_base import spellcard
from src.game.stage.enemy_script import EnemyScript
from src.game.stage.spellcard import SpellCard
from src.game.stage.stage_base import BossDef, StageScript
from src.game.stage.wave_base import Wave


class AnimatedFairy(EnemyScript):
    sprite = 'enemy5'

    async def on_spawn(self):
        self.on_death = self.death_effect

    def death_effect(self, enemy):
        # Independent effect: the enemy has already been disposed.
        self.ctx.play_animation('enemy_orb', self.x, self.y, loop=False,
                                speed=2.0, scale=1.8, blend='add', alpha=0.7)

    async def run(self):
        aura = self.attach_animation('enemy_aura', layer='back', scale=1.8,
                                     color=(0.5, 0.7, 1.0, 0.65))
        await self.play_animation('enemy5_move_left', loop=False, speed=2.0)
        await self.move_to(self.x, 0.0, 45)
        # This particular trail survives the enemy; other attachments do not.
        aura.detach()
        self.ctx.spawn_task(fade(aura, self.ctx, 30))
        self.kill()


async def fade(effect, ctx, frames):
    for frame in range(frames):
        effect.set_visual(alpha=(1.0-frame/frames)*0.65,
                          rotation=frame*3.0, scale=1.8+frame*0.02)
        await ctx.wait(1)
    effect.remove()


@preview(boss='animation_boss', boss_pos=(0.0, 0.55), duration=360, seed=1337)
class AnimationMechanicsSpell(SpellCard):
    DEBUG_BOOKMARK = True
    time_limit = 8.0

    async def run(self):
        self.boss.texture = 'enemy1'
        self.boss.setup_render_obj(self.ctx.animations.assets)
        aura = self.boss.attach_animation('enemy_aura', layer='back', scale=2.2,
                                          color=(0.3, 0.5, 1.0, 0.65))
        ring = self.boss.attach_animation('enemy_orb_ring', offset=(0.25, 0.0),
                                          follow_rotation=True, scale=0.5)
        cast = self.boss.play_animation('enemy1_move_left', loop=False, speed=2.0)
        await self.wait(5)
        cast.pause()
        await self.wait(12)
        cast.resume()
        await cast
        assert cast.finished
        # Automatic idle/movement has resumed; only visuals rotate, not hitboxes.
        self.boss.set_visual(rotation=20.0, alpha=0.85)
        await self.boss.move_to(0.45, 0.45, 60)
        with self.ctx.stop_time('effects'):
            await self.wait(20)
        for frame in range(45):
            aura.set_visual(rotation=frame*4.0)
            self.fire_circle(count=8, speed=2.0, start_angle=frame*8.0,
                             play_sound=False)
            await self.wait(2)
        ring.remove()
        aura.detach()
        await fade(aura, self.ctx, 30)
        self.boss.set_visual(rotation=0.0, alpha=1.0)
        await self.wait(20)


class AnimationFairyWave(Wave):
    DEBUG_BOOKMARK = True

    async def run(self):
        self.spawn_enemy_class(AnimatedFairy, x=-0.4, y=0.65)
        await self.wait(120)


class AnimationMechanicsStage(StageScript):
    id = 'th06_animations'
    name = '主动画、附属动画与死亡效果示例'
    boss = BossDef('animation_boss', '动画机制', 'enemy1', [
        spellcard(AnimationMechanicsSpell, '', hp=1000, time=8.0, bonus=0),
    ])

    async def run(self):
        await self.run_wave(AnimationFairyWave)
        await self.run_boss(self.boss)


STAGES = [AnimationMechanicsStage]
START_STAGE = AnimationMechanicsStage
STAGE_BY_ID = {stage.id: stage for stage in STAGES}
