"""
Stage 3 final spell adapted from D:/Downloads/test1.lstges.

The original practice card builds a large static star tableau around the boss,
waits briefly, then emits a slow rotating 3-way star spread forever.
"""

import math

from src.game.stage.spellcard import SpellCard


PIXEL_UNIT = 2.0 / 448.0
HALO_POINTS_PER_RING = 120  # Reduced from 360 to keep runtime light.

FIXED_ROWS = {
    100: [30, 40, 50, 60],
    90: [-90, -80, 20, 40, 50, 60],
    80: [-90, -80, -10, 20, 30, 40, 50, 60, 70],
    70: [-80, -70, -60, 20, 30, 40, 50, 60, 70],
    60: [-80, -70, -60, -50, 20, 30, 40, 50, 60, 70],
    50: [-80, -70, -60, -50, -40, 30, 40, 50, 60, 70],
    40: [-120, -110, -100, -90, -80, -70, -60, -50, -40, -30, -20, -10, 50, 60],
    30: [-110, -100, -90, -80, -70, -60, -50, -40, -30, -20, 60, 70],
    20: [-100, -90, -80, -70, -60, -50, -40, -30, 60, 70],
    10: [-110, -100, -90, -80, -70, -60, -50, -30, 70, 80],
    -10: [-120, -110, -100, -90, -80, -60, -50, 70, 80, 90],
    -20: [-110, -100, -90, -20, -10, 10, 80, 90],
    -30: [-30, -20, -10, 10, 20, 30, 80, 90, 100],
    -40: [-40, -30, -10, 10, 20, 30, 40, 100],
    -50: [-40, -30, -20, -10, 10, 20, 30, 40],
    -60: [-40, -30, -20, -10, 10, 20, 30, 40],
    -70: [-40, -30, -20, -10, 10, 20, 30, 40],
    -80: [-40, -30, -20, -10, 10, 20, 30, 40],
    -90: [-30, -10, 10, 20, 30],
    -100: [-50, -40, -30, 10, 30, 40, 50],
    -110: [-60, -50, -40, -30, -20, -10, 10, 20, 30, 40, 50, 60],
}


class StarSpell4(SpellCard):
    def _spawn_star(self, dx_px: float, dy_px: float) -> None:
        self.fire(
            x=self.boss.x + dx_px * PIXEL_UNIT,
            y=self.boss.y + dy_px * PIXEL_UNIT,
            angle=0.0,
            speed=0.0,
            bullet_type="star_s",
            color="yellow",
            play_sound=False,
        )

    def _spawn_ring(self, radius_px: float, count: int, start_angle_deg: float = 0.0) -> None:
        for i in range(count):
            angle_deg = start_angle_deg + (360.0 / count) * i
            angle_rad = math.radians(angle_deg)
            self._spawn_star(
                radius_px * math.cos(angle_rad),
                radius_px * math.sin(angle_rad),
            )

    def _spawn_dense_halo(self) -> None:
        radius_px = 180.0
        for _ in range(20):
            self._spawn_ring(radius_px=radius_px, count=HALO_POINTS_PER_RING)
            radius_px += 10.0

    def _spawn_spokes(self) -> None:
        for angle_deg in (90.0, 210.0, 330.0):
            angle_rad = math.radians(angle_deg)
            radius_px = 0.0
            for _ in range(9):
                self._spawn_star(
                    radius_px * math.cos(angle_rad),
                    radius_px * math.sin(angle_rad),
                )
                radius_px += 20.0

    def _spawn_fixed_pattern(self) -> None:
        for y_px, x_list in FIXED_ROWS.items():
            for x_px in x_list:
                self._spawn_star(x_px, y_px)

    async def run(self):
        await self.boss.move_to(0.0, 0.0, duration=60)

        self._spawn_ring(radius_px=180.0, count=72, start_angle_deg=0.0)
        self._spawn_dense_halo()
        self._spawn_ring(radius_px=135.0, count=36, start_angle_deg=0.0)
        self._spawn_spokes()
        self._spawn_fixed_pattern()

        await self.wait(60)

        angle = 0.0
        while True:
            self.fire_circle(
                x=self.boss.x,
                y=self.boss.y,
                count=3,
                speed=20.0,
                start_angle=angle,
                bullet_type="star_s",
                color="yellow",
            )
            angle += 2.0
            await self.wait(10)
