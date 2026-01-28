"""
符卡系统测试关卡

测试新的 SpellCard 系统
"""
import math
import numpy as np
from typing import Generator

# 导入符卡系统
from src.game.stage.spellcard import SpellCard, SpellCardContext


class PlayerWrapper:
    """包装 Player，提供 x, y 属性"""
    def __init__(self, player):
        self._player = player
    
    @property
    def x(self):
        return self._player.pos[0]
    
    @property
    def y(self):
        return self._player.pos[1]


class SimpleSpellCardContext(SpellCardContext):
    """
    简单的符卡上下文实现
    用于测试，连接到现有的 BulletPool
    """
    
    def __init__(self, bullet_pool, player):
        self.bullet_pool = bullet_pool
        self._player = player
        self._player_wrapper = PlayerWrapper(player)
        self._bullet_indices = []  # 跟踪创建的子弹索引
    
    def create_bullet(self, x, y, angle, speed, bullet_type="ball_m", color="red", 
                      accel=0, angle_accel=0, owner=None, **kwargs):
        """创建子弹"""
        # 根据颜色和类型选择精灵
        sprite_id = self._get_sprite_id(bullet_type, color)
        
        # 添加到子弹池 - 使用 spawn_bullet
        idx = self.bullet_pool.spawn_bullet(
            x=x, y=y, 
            angle=math.radians(angle), 
            speed=speed / 60.0,  # 转换为每帧速度
            sprite_id=sprite_id
        )
        if idx >= 0:
            self._bullet_indices.append(idx)
        return idx
    
    def _get_sprite_id(self, bullet_type: str, color: str) -> str:
        """根据类型和颜色获取精灵ID"""
        # 映射到现有的精灵
        type_map = {
            "ball_s": "ball_small",
            "ball_m": "ball_mid",
            "ball_l": "ball_huge",
            "rice": "rice",
            "scale": "scale",
            "arrowhead": "arrowhead",
        }
        
        color_map = {
            "red": "1",
            "blue": "2", 
            "green": "3",
            "yellow": "4",
            "purple": "5",
            "white": "6",
            "darkblue": "7",
            "orange": "8",
        }
        
        base = type_map.get(bullet_type, "ball_mid")
        color_suffix = color_map.get(color, "1")
        
        return f"{base}{color_suffix}"
    
    def remove_bullet(self, bullet_idx):
        """移除子弹"""
        if 0 <= bullet_idx < len(self.bullet_pool.data['alive']):
            self.bullet_pool.data['alive'][bullet_idx] = 0
            if bullet_idx in self._bullet_indices:
                self._bullet_indices.remove(bullet_idx)
    
    def bullet_to_item(self, bullet_idx):
        """将子弹转换为道具（简化实现：直接移除）"""
        self.remove_bullet(bullet_idx)
    
    def get_player(self):
        """获取玩家"""
        return self._player_wrapper


class DummyBoss:
    """测试用的假 Boss"""
    def __init__(self):
        self.x = 0.0
        self.y = 0.5
        self.hp = 1500
        self.max_hp = 1500
    
    def move_to(self, x, y, duration=60):
        """移动到指定位置（生成器）"""
        start_x, start_y = self.x, self.y
        for i in range(duration):
            t = (i + 1) / duration
            t = t * t * (3 - 2 * t)  # smoothstep
            self.x = start_x + (x - start_x) * t
            self.y = start_y + (y - start_y) * t
            yield


def spellcard_test_level(stage_manager, bullet_pool, player) -> Generator:
    """
    符卡测试关卡
    
    测试新的符卡脚本系统
    """
    print("=== 符卡系统测试开始 ===")
    
    # 创建上下文和假Boss
    ctx = SimpleSpellCardContext(bullet_pool, player)
    boss = DummyBoss()
    
    # 动态加载符卡脚本
    import importlib.util
    import os
    
    script_path = "game_content/stages/stage1/spellcards/spell_1.py"
    
    if not os.path.exists(script_path):
        print(f"符卡脚本不存在: {script_path}")
        return
    
    # 加载模块
    spec = importlib.util.spec_from_file_location("spell_module", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # 获取符卡类
    if hasattr(module, 'spellcard'):
        SpellCardClass = module.spellcard
        if isinstance(SpellCardClass, type):
            spellcard = SpellCardClass()
        else:
            spellcard = SpellCardClass
    else:
        print("未找到符卡类")
        return
    
    print(f"加载符卡: {spellcard.name}")
    print(f"HP: {spellcard.hp}, 时间: {spellcard.time_limit}s")
    
    # 绑定并启动
    spellcard.bind(boss, ctx)
    
    # 先运行 setup
    setup_coro = spellcard.setup()
    if setup_coro:
        try:
            while True:
                next(setup_coro)
                yield
        except StopIteration:
            pass
    
    print(f"符卡开始! Boss位置: ({boss.x:.2f}, {boss.y:.2f})")
    
    # 运行主弹幕逻辑
    run_coro = spellcard.run()
    frame = 0
    
    while frame < spellcard.time_limit * 60:  # 时间限制
        frame += 1
        spellcard._time = frame
        
        # 推进协程
        if run_coro:
            try:
                next(run_coro)
            except StopIteration:
                print("符卡逻辑结束")
                break
        
        # 每秒打印一次状态
        if frame % 60 == 0:
            active_count = np.sum(bullet_pool.data['alive'])
            print(f"[{frame//60}s] 子弹数: {active_count}, Boss: ({boss.x:.2f}, {boss.y:.2f})")
        
        yield
    
    print("=== 符卡结束 ===")
    
    # 清除所有子弹
    bullet_pool.clear()
    
    # 等待一下再结束
    for _ in range(120):
        yield
