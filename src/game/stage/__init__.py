import pygame
import sys
import numpy as np

class StageManager:
    def __init__(self):
        """
        初始化关卡管理器
        """
        self.coroutines = []
        self.frame_count = 0
        self.stage_number = 1
        self.is_paused = False
        self.boss_manager = None
        self.enemy_manager = None
        self.current_stage = None  # 当前 StageScript 实例（用于对话系统等）
        self.current_context = None  # 当前 StageContext 实例
    
    def set_boss_manager(self, boss_manager):
        """
        设置Boss管理器
        :param boss_manager: Boss管理器对象
        """
        self.boss_manager = boss_manager
    
    def set_enemy_manager(self, enemy_manager):
        """
        设置敌人管理器
        :param enemy_manager: 敌人管理器对象
        """
        self.enemy_manager = enemy_manager
    
    def add_coroutine(self, coro_func):
        """
        添加一个协程到管理器
        :param coro_func: 协程函数，应该返回一个生成器对象
        """
        try:
            coro = coro_func()
            self.coroutines.append(coro)
        except Exception as e:
            print(f"Error in coroutine: {e}")
    
    def update(self, dt, bullet_pool, player):
        """
        更新所有协程
        :param dt: 时间步长
        :param bullet_pool: 子弹池对象
        :param player: 玩家对象
        """
        if self.is_paused:
            return
        
        # 更新Boss
        if self.boss_manager:
            self.boss_manager.update(dt, bullet_pool)
        
        # 更新敌人
        if self.enemy_manager:
            self.enemy_manager.update(dt, bullet_pool)
        
        # 更新协程
        new_coroutines = []
        for coro in self.coroutines:
            try:
                # 执行协程的下一个步骤
                next(coro)
                new_coroutines.append(coro)
            except StopIteration:
                # 协程结束
                pass
            except Exception as e:
                print(f"Error in coroutine: {e}")
        
        self.coroutines = new_coroutines
        self.frame_count += 1
    
    def get_frame_count(self):
        """
        获取当前帧计数
        :return: 当前帧计数
        """
        return self.frame_count
    
    def pause(self):
        """
        暂停游戏
        """
        self.is_paused = True
    
    def resume(self):
        """
        恢复游戏
        """
        self.is_paused = False
    
    def clear(self):
        """
        清除所有协程
        """
        self.coroutines.clear()
        self.frame_count = 0
        if self.boss_manager:
            self.boss_manager.clear()
        if self.enemy_manager:
            self.enemy_manager.clear()
    
    def add_boss(self, boss):
        """
        添加Boss到关卡
        :param boss: Boss对象
        """
        if self.boss_manager:
            self.boss_manager.add_boss(boss)
    
    def add_enemy(self, enemy):
        """
        添加敌人到关卡
        :param enemy: Enemy对象
        """
        if self.enemy_manager:
            self.enemy_manager.add_enemy(enemy)
    
    def get_active_boss(self):
        """
        获取当前活跃的Boss
        :return: 当前活跃的Boss对象，或None
        """
        if self.boss_manager:
            return self.boss_manager.get_active_boss()
        return None
    
    def get_active_enemies(self):
        """
        获取当前活跃的敌人
        :return: 活跃敌人列表，或空列表
        """
        if self.enemy_manager:
            return self.enemy_manager.get_active_enemies()
        return []
    
    def wait(self, frames):
        """
        等待指定帧数（生成器函数）
        :param frames: 要等待的帧数
        :return: 生成器对象
        """
        for _ in range(frames):
            yield