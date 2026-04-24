"""
Orin player script (v3).
High speed: wider spread.
Low speed: tighter forward stream.
Passive: homing spirit sparks at power >= 2, but rate-limited for balance.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from src.game.player.player_script import PlayerScript


class OrinScript(PlayerScript):
    """Kaenbyou Rin"""

    def on_init(self):
        self.fire_timer = 0.0
        self.passive_timer = 0.0
        self.spawn_option("coplane_idle", offset_x=-0.12, offset_y=0.02,
                          focused_offset=(-0.06, 0.03))
        self.spawn_option("coplane_idle", offset_x=0.12, offset_y=0.02,
                          focused_offset=(0.06, 0.03))

    def on_update(self, dt):
        if self.fire_timer > 0:
            self.fire_timer -= dt
        if self.passive_timer > 0:
            self.passive_timer -= dt

    def on_shoot(self, is_focused):
        if self.fire_timer > 0:
            return
        self.fire_timer = 4.0 / 60.0

        if is_focused:
            self.fire(bullet_anim="orin_bullet", angle=90, speed=6, damage=3.5,
                      x=self.player.pos[0] - 0.015)
            self.fire(bullet_anim="orin_bullet", angle=90, speed=6, damage=3.5,
                      x=self.player.pos[0] + 0.015)
            self.fire(bullet_anim="orin_bullet", angle=90, speed=5.5, damage=3.0,
                      x=self.player.pos[0] - 0.035)
            self.fire(bullet_anim="orin_bullet", angle=90, speed=5.5, damage=3.0,
                      x=self.player.pos[0] + 0.035)
        else:
            self.fire(bullet_anim="orin_bullet", angle=90, speed=5, damage=2.5)
            self.fire(bullet_anim="orin_bullet", angle=85, speed=5, damage=2.25)
            self.fire(bullet_anim="orin_bullet", angle=95, speed=5, damage=2.25)
            self.fire(bullet_anim="orin_bullet", angle=80, speed=4.5, damage=1.75)
            self.fire(bullet_anim="orin_bullet", angle=100, speed=4.5, damage=1.75)
            self.fire(bullet_anim="orin_bullet", angle=90, speed=6, damage=1.5)

    def on_bullet_hit_enemy(self, bullet_idx, enemy, damage):
        if self.player.power >= 2.0 and self.passive_timer <= 0:
            bpos = self.bullet_pool.data[bullet_idx]["pos"]
            self.fire(
                bullet_anim="orin_bullet",
                x=float(bpos[0]),
                y=float(bpos[1]),
                angle=90,
                speed=3,
                damage=2.5,
                homing=True,
                homing_strength=5.0,
            )
            self.passive_timer = 0.10

    def on_bomb(self, is_focused):
        self.player.invincible_timer = 5.0
        self.player.spell_cooldown = 5.0
        return True
