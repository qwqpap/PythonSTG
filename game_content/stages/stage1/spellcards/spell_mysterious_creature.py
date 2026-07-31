import random

from src.game.stage.spellcard import SpellCard
from src.content_api import TAG_BOMB_PROTECTED_NODE


class MysteriousCreatureSpell(SpellCard):
    """生符「食堂的神秘小生物」"""

    name = "生符「食堂的神秘小生物」"
    DEBUG_BOOKMARK = True

    # 网格参数（12x7=84个，覆盖全屏但不过密）
    grid_cols: int = 12
    grid_rows: int = 7
    x_min: float = -0.88
    x_max: float = 0.88
    y_min: float = 0.08
    y_max: float = 0.88

    # 3秒延迟后才开始第一波
    trigger_delay_frames: int = 180

    # 链式反应：每节点爆出 burst_count 颗快弹
    explosion_burst_count: int = 16
    explosion_speed: float = 10.0  # 快弹，明显爆裂感（游戏单位/秒）

    # 波在 8 秒（480 帧）内从左到右扫过全网格
    wave_spread_frames: int = 480

    time_limit: float = 60.0

    async def setup(self):
        await self.boss.move_to(0.0, 0.80, duration=60)

    def _col_x(self, col: int) -> float:
        return self.x_min + col * (self.x_max - self.x_min) / max(self.grid_cols - 1, 1)

    def _spawn_grid(self) -> list[dict]:
        """生成一轮网格，返回节点列表（静止弹，speed=0）"""
        colors = ("darkgreen", "green", "darkcyan", "cyan")
        nodes = []
        for col in range(self.grid_cols):
            for row in range(self.grid_rows):
                x = self._col_x(col)
                y = self.y_min + row * (self.y_max - self.y_min) / max(self.grid_rows - 1, 1)
                bullet = self.fire(
                    x=x, y=y,
                    angle=0.0, speed=0.0,
                    bullet_type="mildew",
                    color=colors[(col + row) % len(colors)],
                    tag=TAG_BOMB_PROTECTED_NODE,
                )
                nodes.append({"col": col, "row": row, "x": x, "y": y, "bullet": bullet})
        return nodes

    def _explode_node(self, node: dict):
        """节点爆炸：移除静止弹，向八方散射快弹"""
        self.ctx.remove_bullet(node["bullet"])
        node["bullet"] = None

        x, y = node["x"], node["y"]
        warm_colors = ("green", "cyan", "yellow", "white")
        for i in range(self.explosion_burst_count):
            angle = (360.0 / self.explosion_burst_count) * i + random.uniform(-10.0, 10.0)
            self.fire(
                x=x, y=y,
                angle=angle,
                speed=self.explosion_speed + random.uniform(-0.5, 0.5),
                bullet_type="mildew",
                color=random.choice(warm_colors),
            )

    def _update_grid(self, nodes: list[dict], wave_front_x: float):
        """触发波前范围内尚未爆炸的静止节点（网格弹 speed=0，坐标不变，直接用存储值）"""
        alive_nodes = []
        for node in nodes:
            if node["bullet"] is None:
                continue
            # 用列的理论 x 坐标判断是否已被波前扫到
            if self._col_x(node["col"]) <= wave_front_x:
                self._explode_node(node)
            else:
                alive_nodes.append(node)
        nodes[:] = alive_nodes

    async def run(self):
        # 等待初始延迟
        await self.wait(self.trigger_delay_frames)

        wave_rate = (self.x_max - self.x_min) / self.wave_spread_frames  # NDC/帧

        while True:
            # ── 每个 8 秒周期：生成网格 → 波前从左到右逐帧推进 → 自然结束后重复 ──
            nodes = self._spawn_grid()

            for cycle_frame in range(self.wave_spread_frames + 1):
                wave_front_x = self.x_min + cycle_frame * wave_rate
                self._update_grid(nodes, wave_front_x)
                await self.wait(1)

            # 安全清理（正常情况下 nodes 扫完后已空）
            for node in nodes:
                if node["bullet"] is not None:
                    self.ctx.remove_bullet(node["bullet"])
                    node["bullet"] = None


spellcard = MysteriousCreatureSpell
