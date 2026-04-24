"""
Tenshi player script (v3).
Continuous dual lasers with focus changing beam spacing.
Damage scales linearly with power through PlayerScript helpers.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from src.game.player.player_script import PlayerScript


class TenshiScript(PlayerScript):
    """Hinanawi Tenshi"""

    def on_init(self):
        self.player.player_lasers = []

    def on_update(self, dt):
        if not self.player.is_shooting:
            self.player.player_lasers = []

    def on_shoot(self, is_focused):
        px = self.player.pos[0]
        py = self.player.pos[1]

        if is_focused:
            offset_x = 0.04
            beam_damage = self.scale_damage(1.7)
        else:
            offset_x = 0.10
            beam_damage = self.scale_damage(1.5)

        self.player.player_lasers = [
            {"x": px - offset_x, "y": py + 0.03, "sprite": "laser1", "damage": beam_damage},
            {"x": px + offset_x, "y": py + 0.03, "sprite": "laser1", "damage": beam_damage},
        ]

    def on_bomb(self, is_focused):
        self.player.invincible_timer = 5.0
        self.player.spell_cooldown = 5.0
        return True
