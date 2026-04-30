import random
from src.game.stage.wave_base import Wave

from game_content.stages.stage3.enemies.geology_fairy import GeologyFairy
from game_content.stages.stage3.enemies.stress_yin_yang import StressYinYang

class Stage3Wave1(Wave):
    """
    Stage 3 Wave 1 
    地质学初见体验：极其凌厉的快慢刀混搭
    大量的地质妖精使用高压风筝弹穿刺阵型，紧接着是应力阴阳玉的毁灭级扫射。
    """
    async def run(self):
        # 1. 晶体妖精集群：高压高速突袭
        for i in range(10):
            # 随机在左右两极度倾斜处刷出，增加走位偏移难度
            spawn_x = random.uniform(0.4, 1.2)
            if i % 2 == 0:
                spawn_x = -spawn_x
                
            enemy = self.spawn_enemy_class(GeologyFairy, x=spawn_x, y=1.4)
            if enemy:
                enemy.hp = 30
                enemy.score = 1500
                enemy.sprite = "enemy1"
                
            await self.wait(25) # 短间隔，形成全屏高压
            
        # 给予玩家稍微喘息的准备时间（清理屏幕残留物）
        await self.wait(80)
        
        # 2. 阴阳玉应力阵列：两侧同时降下，形成交叉的极速火力网
        for x_pos in [-0.9, -0.4, 0.4, 0.9]:
            enemy = self.spawn_enemy_class(StressYinYang, x=x_pos, y=1.3)
            if enemy:
                enemy.hp = 50
                enemy.score = 3000
                enemy.sprite = "enemy2"
        
        # 等待该波次敌人完全行动完毕并退场
        await self.wait(200)
