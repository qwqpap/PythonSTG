"""
Stage 2 开场波次 - TODO

在此编写 Stage 2 的开场波次。
参考 stage1/waves/opening_wave.py 的格式。
"""

from src.game.stage.wave_base import Wave


class OpeningWave(Wave):
    async def run(self):
        # TODO: 编写开场波次
        await self.wait(60)


wave = OpeningWave
