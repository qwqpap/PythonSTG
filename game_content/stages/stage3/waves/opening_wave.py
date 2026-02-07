"""
Stage 3 开场波次 - TODO
"""

from src.game.stage.wave_base import Wave


class OpeningWave(Wave):
    async def run(self):
        # TODO: 编写开场波次
        await self.wait(60)


wave = OpeningWave
