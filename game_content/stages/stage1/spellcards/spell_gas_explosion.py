import random

from src.game.stage.spellcard import SpellCard
from src.content_api import TAG_BOMB_PROTECTED_NODE


class GasExplosionSpell(SpellCard):
    """烈符「瓦斯爆炸」- LuaSTG 风格移植版。"""

    name = "烈符「瓦斯爆炸」"
    DEBUG_BOOKMARK = True

    # 参考 Lua: for 1..80 每 5 帧生成 + 每轮额外 60 帧
    batch_spawn_count: int = 80
    spawn_interval_frames: int = 5
    batch_rest_frames: int = 60

    # wasi 行为：静止一段时间后爆裂
    gas_fuse_frames: int = 400
    gas_burst_count: int = 7

    def _spawn_gas_node(self, x: float, y: float, nodes: list[dict]):
        idx = self.fire(
            x=x,
            y=y,
            angle=0.0,
            speed=0.0,
            bullet_type="mildew",
            color="darkcyan",
            tag=TAG_BOMB_PROTECTED_NODE,
        )
        nodes.append({"idx": idx, "x": x, "y": y, "born": self.time})

    def _explode_gas_node(self, node: dict):
        self.ctx.remove_bullet(node["idx"])

        for _ in range(self.gas_burst_count):
            self.fire(
                x=node["x"],
                y=node["y"],
                angle=random.uniform(0.0, 360.0),
                speed=4.8,
                bullet_type="gun",
                color="darkorange",
            )

        self.fire(
            x=node["x"],
            y=node["y"],
            angle=random.uniform(0.0, 360.0),
            speed=11.0,
            bullet_type="arrow_l",
            color="darkred",
        )

    def _update_gas_nodes(self, nodes: list[dict]):
        alive_nodes = []
        for node in nodes:
            if self.time - node["born"] >= self.gas_fuse_frames:
                self._explode_gas_node(node)
            else:
                alive_nodes.append(node)
        nodes[:] = alive_nodes

    async def setup(self):
        await self.boss.move_to(0.0, 0.55, duration=60)

    async def run(self):
        nodes: list[dict] = []

        while True:
            x_px = 190.0
            y_px = 220.0

            for _ in range(self.batch_spawn_count):
                # Lua: x = x - ran:Float(-5,15), y = y - ran:Float(-7,18)
                x_px += random.uniform(-15.0, 5.0)
                y_px += random.uniform(-18.0, 7.0)

                x = max(-0.98, min(0.98, x_px / 220.0))
                y = max(-1.10, min(1.10, y_px / 220.0))
                self._spawn_gas_node(x, y, nodes)

                for _ in range(self.spawn_interval_frames):
                    self._update_gas_nodes(nodes)
                    await self.wait(1)

            for _ in range(self.batch_rest_frames):
                self._update_gas_nodes(nodes)
                await self.wait(1)


spellcard = GasExplosionSpell
