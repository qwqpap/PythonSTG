"""
敌人展示波次 - Stage 1

展示使用预设系统创建的各种敌人。
这个波次会按顺序展示不同类型的敌人和它们的纹理。
"""

from src.game.stage.wave_base import Wave
from game_content.stages.stage1.enemies.fairy import (
    Enemy1Auto,
    Enemy1Custom,
    Enemy2Custom,
    Enemy3Auto,
    Enemy5Custom,
    Enemy7Custom,
    Enemy9Boss,
    KedamaSwarm
)


class EnemyShowcaseWave(Wave):
    """敌人展示波次 - 展示各种预设敌人"""

    async def run(self):
        # === 第一波：小型妖精编队 ===

        # 3个 enemy1 (红色) 从上方飞入
        for i in range(3):
            x = -0.4 + i * 0.4
            self.spawn_enemy_class(Enemy1Custom, x=x, y=1.0)
            await self.wait(20)

        await self.wait(60)

        # 5个 enemy2 (蓝色) 从两侧横向飞入
        for i in range(5):
            x = -0.7 if i % 2 == 0 else 0.7
            y = 0.7 - i * 0.08
            self.spawn_enemy_class(Enemy2Custom, x=x, y=y)
            await self.wait(15)

        await self.wait(90)

        # === 第二波：中型敌人 ===

        # 3个 enemy3 (绿色) 编队
        for i in range(3):
            x = -0.3 + i * 0.3
            self.spawn_enemy_class(Enemy3Auto, x=x, y=1.0)
            await self.wait(30)

        await self.wait(80)

        # === 第三波：毛玉群 ===

        # 8个 kedama 快速下落
        for i in range(8):
            x = -0.7 + i * 0.2
            self.spawn_enemy_class(KedamaSwarm, x=x, y=1.0)
            await self.wait(8)

        await self.wait(100)

        # === 第四波：大型妖精 ===

        # 2个 enemy5 (红色大妖精)
        for i in range(2):
            x = -0.3 if i == 0 else 0.3
            self.spawn_enemy_class(Enemy5Custom, x=x, y=1.0)
            await self.wait(60)

        await self.wait(120)

        # === 第五波：中型强敌 ===

        # 1个 enemy7 (红色中型敌) - 中心位置
        self.spawn_enemy_class(Enemy7Custom, x=0.0, y=1.0)

        await self.wait(150)

        # === 第六波：大型Boss级敌人 ===

        # 1个 enemy9 (大型敌)
        self.spawn_enemy_class(Enemy9Boss, x=0.0, y=1.0)

        await self.wait(60)


# 注册波次
wave = EnemyShowcaseWave
