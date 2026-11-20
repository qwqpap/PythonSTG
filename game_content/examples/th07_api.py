"""Ordinary API examples, NOT a port of a TH07 stage/character/spell.

Preview: python tools/preview_spell.py game_content/examples/th07_api.py SlowMotionSpell --no-watch --no-config
MechanicsPlayerScript can be installed on a configured PlayerBase; it reuses
that character's own bullet sprites. No original game assets are bundled here.
"""

from dataclasses import dataclass

from src.core.collision_shapes import Hitbox
from src.game.player.hit import HitDecision
from src.game.player.player_bullet import ImpactArea
from src.game.player.player_script import PlayerScript
from src.game.stage.enemy_script import EnemyScript
from src.game.stage.spellcard import SpellCard


@dataclass
class BorderState:
    active: bool = False
    breaks: int = 0


def install_border_rule(ctx, state):
    """A content-owned protection rule, separate from Cherry scoring policy."""
    def receive(player, hit):
        if not state.active:
            return None  # player script / configured Deathbomb window
        state.active = False
        state.breaks += 1
        ctx.clear_all_bullets(to_items=True)
        return HitDecision.handled(invulnerability_frames=60, fail_capture=True)

    ctx.set_player_hit_rule(receive)


class MechanicsPlayerScript(PlayerScript):
    """Focused anchored beam; unfocused missiles with a growing impact area."""

    def on_init(self):
        self.frame = 0
        self.beam = None
        self.sprite = next(iter(self.player.bullet_sprites), '')
        self.player.deathbomb_window_frames = 6  # example only; character policy owns it
        self.player.set_hitbox(Hitbox.box(.012, .018))

    def on_update(self, dt):
        self.frame += 1
        if self.beam is not None:
            if not self.player.is_shooting or not self.player.is_focused:
                self.beam.cancel()
                self.beam = None
            else:
                self.beam.set_damage(self.scale_damage(12.0))

    def on_shoot(self, focused):
        if focused:
            if self.beam is None or not self.beam.active:
                self.beam = self.fire_laser(
                    length=2.2, width=.04, damage=12.0, hit_interval=6,
                    sprite_id=self.sprite)
        elif self.frame % 12 == 0:
            self.fire(angle=90, speed=2.0, damage=20.0, sprite_id=self.sprite,
                      hitbox=Hitbox.box(.025, .05),
                      impact=ImpactArea(
                          Hitbox.circle(.045), damage=5.0, frames=30,
                          hit_interval=6, end_hitbox=Hitbox.circle(.18),
                          sprite_id=self.sprite))


class ContactTarget(EnemyScript):
    hp = 500
    hitbox_radius = .05

    async def run(self):
        self.set_hitbox(Hitbox.box(.08, .10))
        self.set_contact_hitbox(Hitbox.box(.06, .08))
        # Extra offsets can be updated by content for history/trail contacts.
        await self.move_to(.35, .25, duration=120, easing='linear')
        await self.wait(600)


class SlowMotionSpell(SpellCard):
    name = 'TH07 API exercise (not an original spell)'
    time_limit = 30
    preview = {'duration': 600, 'seed': 7}

    async def run(self):
        while True:
            self.fire_circle(count=24, speed=1.4, color='blue', play_sound=False)
            await self.wait(30)
            with self.ctx.slow_motion(1.0/3.0):
                # 30 simulation frames take 90 control updates. Actor movement
                # is interpolated on every physical update, not once per 3.
                await self.boss.move_to(.3, .55, duration=30, easing='linear')
                self.fire_arc(count=17, speed=1.8, center_angle=-90,
                              arc_angle=120, play_sound=False)
                await self.wait(30)
            await self.boss.move_to(0., .55, duration=30, easing='linear')


def play_looped_music(ctx, name, intro_end_frame, loop_end_frame):
    """Frames are source PCM frames, not bytes; local resource conversion is separate."""
    return ctx.play_bgm(name, loops=-1, fade_ms=150,
                        loop_start_frame=intro_end_frame, loop_end_frame=loop_end_frame)
