import random

from src.content_api import CURVE_LINEAR_SPEED
from src.game.stage.spellcard import SpellCard


class CoalInfernoSpell(SpellCard):
    """煤符「燃尽一切的巨大之煤」"""

    name = "煤符「燃尽一切的巨大之煤」"
    DEBUG_BOOKMARK = True

    coal_spawn_interval: int = 30
    coal_spawn_y: float = 1.02
    coal_base_speed: float = 0.55
    coal_speed_accel: float = 0.45
    shatter_y: float = 0.20
    min_fall_frames_before_shatter: int = 52

    spark_ring_count: int = 26
    spark_speed_min: float = 5.8
    spark_speed_max: float = 8.4

    async def setup(self):
        await self.boss.move_to(0.0, 0.72, duration=60)

    def _spawn_coal(self, x: float, coals: list[dict]):
        idx = self.fire(
            x=x,
            y=self.coal_spawn_y,
            angle=-90.0,
            speed=self.coal_base_speed,
            bullet_type="ball_l",     # 近黑色大圆弹（煤球）
            color="darkblue",
            curve_type=CURVE_LINEAR_SPEED,
            curve_params=(self.coal_speed_accel, 0.0, 0.0, self.coal_base_speed),
        )
        coals.append({"idx": idx, "born": self.time})

    def _get_bullet_pos_if_alive(self, idx: int):
        pool = getattr(self.ctx, "bullet_pool", None)
        if pool is None or idx is None or idx < 0:
            return None
        if idx >= len(pool.data["alive"]) or pool.data["alive"][idx] == 0:
            return None
        px, py = pool.data["pos"][idx]
        return float(px), float(py)

    def _shatter_coal(self, idx: int, x: float, y: float):
        self.ctx.remove_bullet(idx)

        step = 360.0 / self.spark_ring_count
        base_phase = random.uniform(0.0, 360.0)
        warm_colors = ("red", "orange", "yellow")
        for i in range(self.spark_ring_count):
            angle = base_phase + i * step + random.uniform(-2.0, 2.0)
            speed = random.uniform(self.spark_speed_min, self.spark_speed_max)
            color = warm_colors[i % 3]
            self.fire(
                x=x,
                y=y,
                angle=angle,
                speed=speed,
                bullet_type="grain_b",  # 细长鳞弹（火星）
                color=color,
            )

        # 第二层更快的交错火星，增强压迫感
        for i in range(0, self.spark_ring_count, 2):
            angle = base_phase + i * step + step * 0.5
            self.fire(
                x=x,
                y=y,
                angle=angle,
                speed=self.spark_speed_max + 1.0,
                bullet_type="grain_b",
                color="red" if (i // 2) % 2 == 0 else "yellow",
            )

    def _update_and_shatter_coals(self, coals: list[dict]):
        alive_coals = []
        for coal in coals:
            pos = self._get_bullet_pos_if_alive(coal["idx"])
            if pos is None:
                continue

            x, y = pos
            if self.time - coal["born"] < self.min_fall_frames_before_shatter:
                alive_coals.append(coal)
                continue

            if y <= self.shatter_y:
                self._shatter_coal(coal["idx"], x, y)
                continue

            alive_coals.append(coal)
        coals[:] = alive_coals

    async def run(self):
        coals: list[dict] = []

        while True:
            if self.time % self.coal_spawn_interval == 0:
                self._spawn_coal(random.uniform(-0.88, 0.88), coals)
                if self.time % (self.coal_spawn_interval * 3) == 0:
                    self._spawn_coal(random.uniform(-0.88, 0.88), coals)

            self._update_and_shatter_coals(coals)
            await self.wait(1)


spellcard = CoalInfernoSpell
