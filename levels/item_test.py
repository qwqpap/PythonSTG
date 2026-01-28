"""
物品系统测试关卡

演示:
- 敌人击破掉落物品
- 收点线机制
- 物品吸附与收集
- 分数/Power/残机碎片
"""

import math
import random
from src.game.item import ItemType


def item_test_level(stage_manager, bullet_pool, player, item_pool):
    """物品系统测试关卡"""
    
    # 简单敌人类：被击破时掉落物品
    class TestEnemy:
        def __init__(self, x, y, hp=100, drop_power=5, drop_point=3, drop_faith=1):
            self.x = x
            self.y = y
            self.hp = hp
            self.max_hp = hp
            self.alive = True
            self.drop_power = drop_power
            self.drop_point = drop_point
            self.drop_faith = drop_faith
            self.timer = 0
            self.vy = -0.005
        
        def update(self):
            self.timer += 1
            self.y += self.vy
            if self.y < -1.2:
                self.alive = False
        
        def take_damage(self, amount):
            self.hp -= amount
            if self.hp <= 0 and self.alive:
                self.alive = False
                # 掉落物品
                item_pool.spawn_drop(
                    self.x, self.y,
                    power=self.drop_power,
                    point=self.drop_point,
                    faith=self.drop_faith
                )
                return True
            return False
    
    # 存储敌人
    enemies = []
    
    # 生成敌人波次
    def spawn_enemy_wave(count, y=0.9, spacing=0.3, **kwargs):
        start_x = -(count - 1) * spacing / 2
        for i in range(count):
            x = start_x + i * spacing
            enemies.append(TestEnemy(x, y, **kwargs))
    
    # 帧计数器
    frame = [0]
    
    def update():
        frame[0] += 1
        
        # 生成敌人波次
        if frame[0] == 60:
            spawn_enemy_wave(3, drop_power=10, drop_point=5, drop_faith=2)
        
        if frame[0] == 180:
            spawn_enemy_wave(5, drop_power=5, drop_point=3, drop_faith=1)
        
        if frame[0] == 300:
            # 大量掉落测试
            spawn_enemy_wave(1, x=0, drop_power=50, drop_point=20, drop_faith=10)
        
        if frame[0] == 420:
            spawn_enemy_wave(4, drop_power=8, drop_point=4, drop_faith=2)
        
        if frame[0] == 540:
            # 残机碎片测试
            for _ in range(3):
                item_pool.spawn(
                    random.uniform(-0.5, 0.5), 0.8,
                    ItemType.LIFE_CHIP
                )
        
        if frame[0] == 660:
            # 炸弹碎片测试
            for _ in range(3):
                item_pool.spawn(
                    random.uniform(-0.5, 0.5), 0.8,
                    ItemType.BOMB_CHIP
                )
        
        if frame[0] == 780:
            # 大P点
            item_pool.spawn(0, 0.8, ItemType.POWER_LARGE)
            item_pool.spawn(-0.2, 0.8, ItemType.POWER_LARGE)
            item_pool.spawn(0.2, 0.8, ItemType.POWER_LARGE)
        
        if frame[0] == 900:
            # 1UP
            item_pool.spawn(0, 0.8, ItemType.EXTEND)
        
        # 循环
        if frame[0] >= 1000:
            frame[0] = 0
        
        # 更新敌人
        for enemy in enemies[:]:
            if enemy.alive:
                enemy.update()
                
                # 简单碰撞检测（玩家子弹）
                # 这里简化：每帧有概率被"击中"
                if random.random() < 0.02:
                    enemy.take_damage(50)
            else:
                enemies.remove(enemy)
    
    # 主循环
    while True:
        update()
        yield


def simple_item_demo(stage_manager, bullet_pool, player, item_pool):
    """
    简单物品演示
    
    按方向键移动，物品会自动掉落
    - 靠近物品会吸附
    - 移动到屏幕上方（收点线）会吸附所有物品
    """
    
    frame = 0
    
    while True:
        frame += 1
        
        # 每2秒随机掉落一些物品
        if frame % 120 == 0:
            # 随机位置
            x = random.uniform(-0.7, 0.7)
            y = 0.85
            
            # 随机类型
            item_type = random.choice([
                ItemType.POWER,
                ItemType.POWER,
                ItemType.POWER,
                ItemType.POINT,
                ItemType.POINT,
                ItemType.FAITH,
                ItemType.LIFE_CHIP,
                ItemType.BOMB_CHIP,
            ])
            
            item_pool.spawn(x, y, item_type)
        
        # 每5秒掉落一批
        if frame % 300 == 0:
            cx = random.uniform(-0.5, 0.5)
            item_pool.spawn_drop(cx, 0.8, power=20, point=10, faith=5)
        
        yield
