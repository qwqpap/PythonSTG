"""
敌人展示波次 - Stage 1

按顺序展示敌人预设的各类精灵和行为，用于确认预设与纹理是否正常。

该波次不参与 Stage 1 的正式流程。需要查看时，在关卡的 run() 中加入：

    await self.run_wave(EnemyShowcaseWave)
"""

from src.game.stage.wave_base import Wave
from game_content.stages.stage1.enemies.preset_examples import (
    AutoBlueFairy,
    AutoGreenFairy,
    AutoLargeRedFairy,
    AutoMidRedEnemy,
    CustomRedFairy,
    KedamaDiver,
    ShowcaseBossEnemy,
)


class EnemyShowcaseWave(Wave):
    """敌人展示波次 - 依次展示各种预设敌人"""

    async def run(self):
        # === 第一波：小型妖精编队 ===

        # 3 个 enemy1（红色妖精）从上方飞入
        for i in range(3):
            x = -0.4 + i * 0.4
            self.spawn_enemy_class(CustomRedFairy, x=x, y=1.0)
            await self.wait(20)

        await self.wait(60)

        # 5 个 enemy2（蓝色妖精）从两侧横向飞入
        for i in range(5):
            x = -0.7 if i % 2 == 0 else 0.7
            y = 0.7 - i * 0.08
            self.spawn_enemy_class(AutoBlueFairy, x=x, y=y)
            await self.wait(15)

        await self.wait(90)

        # === 第二波：中型敌人 ===

        # 3 个 enemy3（绿色妖精）编队
        for i in range(3):
            x = -0.3 + i * 0.3
            self.spawn_enemy_class(AutoGreenFairy, x=x, y=1.0)
            await self.wait(30)

        await self.wait(80)

        # === 第三波：毛玉群 ===

        # 8 个 kedama 快速下落
        for i in range(8):
            x = -0.7 + i * 0.2
            self.spawn_enemy_class(KedamaDiver, x=x, y=1.0)
            await self.wait(8)

        await self.wait(100)

        # === 第四波：大型妖精 ===

        # 2 个 enemy5（红色大妖精）
        for i in range(2):
            x = -0.3 if i == 0 else 0.3
            self.spawn_enemy_class(AutoLargeRedFairy, x=x, y=1.0)
            await self.wait(60)

        await self.wait(120)

        # === 第五波：中型强敌 ===

        # 1 个 enemy7（红色中型敌）- 中心位置
        self.spawn_enemy_class(AutoMidRedEnemy, x=0.0, y=1.0)

        await self.wait(150)

        # === 第六波：Boss 级敌人 ===

        # 1 个 enemy9（大型敌）
        self.spawn_enemy_class(ShowcaseBossEnemy, x=0.0, y=1.0)

        await self.wait(60)


# 注册波次
wave = EnemyShowcaseWave
