"""
妖精编队波次 - Stage 1

左右各 5 个妖精从屏幕外高处依次飞入，边飞边对玩家射击自机狙。
左侧 5 个先出（从左上角斜向右下飞入），右侧 5 个紧随其后（从右上角斜向左下飞入）。
间隔 20 帧依次登场。

wave 只负责：在哪里生成、生成多少个、间隔多久、飞行方向。
enemy 只负责：沿给定方向飞行并射击。
"""

from src.game.stage.wave_base import Wave
from game_content.stages.stage1.enemies.fairy import SideFlyFairy


# 左侧妖精：从右侧飞入（方向朝右下）
class LeftFairy(SideFlyFairy):
    fly_angle = -30     # 向右下方飞（从左上角进入屏幕）


# 右侧妖精：从左侧飞入（方向朝左下）
class RightFairy(SideFlyFairy):
    fly_angle = -150    # 向左下方飞（从右上角进入屏幕）


class FairyWave(Wave):
    """左右各 5 个妖精，从屏幕外高处斜向飞入，边飞边射自机狙"""

    async def run(self):
        # 左侧 5 个：从左上角屏幕外出发，x 从 -0.9 到 -0.5，y 在屏幕上方外侧
        for i in range(20):
            x = -0.9 + i * 0.1
            self.spawn_enemy_class(LeftFairy, x=x, y=1.1)
            x = 0.9 - i * 0.1
            self.spawn_enemy_class(RightFairy, x=x, y=1.1)
            await self.wait(60)



        # 等待所有敌人飞出屏幕（fly_duration=180 帧）
        await self.wait(200)


wave = FairyWave
