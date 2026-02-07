"""
符卡系统测试关卡

使用新的 StageContext 测试符卡系统
"""
import numpy as np
from typing import Generator

from src.game.stage.context import StageContext


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
    
    # 使用统一的 StageContext
    ctx = StageContext(bullet_pool=bullet_pool, player=player)
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
    bullet_pool.clear_all()
    
    # 等待一下再结束
    for _ in range(120):
        yield
