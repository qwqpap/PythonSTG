"""
开场波次 - Stage 1

关卡开始后第一波敌弹。
几列米弹从上方整齐落下，给玩家"进入战斗"的感觉。
节奏平缓，用于热身。

内容编写规则：
- 只使用 Wave 基类提供的 API（self.fire / self.wait 等）
- 不要 import 引擎内部模块（BulletPool, EnemyManager 等）
- 所有坐标使用归一化坐标（-1~1 或 0~1）
"""

from src.game.stage.wave_base import Wave


class OpeningWave(Wave):
    """开场 - 三波米弹下落"""
    
    async def run(self):
        # 3波，每波8列
        for wave_num in range(3):
            for i in range(8):
                x = -0.7 + i * 0.2
                self.fire(
                    x=x, y=0.9,
                    angle=-90, speed=1.8,
                    bullet_type="rice", color="blue"
                )
            await self.wait(30)  # 每波间隔 0.5 秒
        
        # 等待子弹飞出屏幕
        await self.wait(60)


# 注册波次（用于动态加载）
wave = OpeningWave
