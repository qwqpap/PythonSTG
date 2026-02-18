import pygame
import sys
import os
import inspect
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
        self.loading_info = None  # dict or None → 控制加载画面显示

        # 引擎对象引用（由 bind_engine 设置）
        self._engine_refs = None
        self._audio_manager = None

    # ==================== 引擎绑定 ====================

    def bind_engine(self, bullet_pool, player,
                    audio_manager=None, **kwargs):
        """
        一次性绑定引擎对象（在 main.py 初始化时调用一次）

        Args:
            bullet_pool: 子弹池
            player: 玩家对象
            audio_manager: 音频管理器（可选）
            **kwargs: 额外引擎对象（laser_pool, item_pool 等）
        """
        self._engine_refs = {
            'bullet_pool': bullet_pool,
            'player': player,
            **kwargs
        }
        self._audio_manager = audio_manager

    # ==================== 关卡加载 ====================

    def load_stage(self, stage_class):
        """
        加载并运行一个 StageScript 子类。
        自动处理：loading 画面 → 音频加载 → ctx 创建 → 运行 → 清理。

        Args:
            stage_class: StageScript 的子类（类本身，不是实例）

        Example:
            from game_content.stages.stage1.stage_script import Stage1
            stage_manager.load_stage(Stage1)
        """
        if self._engine_refs is None:
            raise RuntimeError(
                "必须先调用 bind_engine() 绑定引擎对象，才能使用 load_stage()"
            )
        self.add_coroutine(lambda: self._run_stage(stage_class))

    def _run_stage(self, stage_class):
        """
        统一的关卡运行流程。

        替代 levels/stage1_level.py 中的手写胶水代码。
        自动完成：loading 画面 → 音频加载 → StageContext 创建 → 关卡运行 → 清理。
        """
        from .context import StageContext
        from ..audio import StageAudioBank

        bullet_pool = self._engine_refs['bullet_pool']
        player = self._engine_refs['player']

        # ===== 阶段 1：加载画面 =====
        self.loading_info = {
            "stage_name": getattr(stage_class, 'name', ''),
            "title": getattr(stage_class, 'title', ''),
            "subtitle": getattr(stage_class, 'subtitle', ''),
            "hint": "Loading...",
        }
        yield  # 显示加载画面

        # 加载关卡私有音频
        stage_dir = self._find_stage_directory(stage_class)
        if self._audio_manager and stage_dir:
            stage_id = getattr(stage_class, 'id', 'unknown')
            stage_bank = StageAudioBank.from_directory(stage_id, stage_dir)
            self._audio_manager.set_stage_bank(stage_bank)
            self.loading_info["hint"] = "Ready"

        yield  # 刷新一帧

        # 停留一段时间让玩家看到关卡信息
        for _ in range(120):
            yield

        # ===== 阶段 2：开始关卡 =====
        self.loading_info = None

        # 创建上下文：将引擎对象包装成内容脚本可用的统一接口
        ctx = StageContext(
            bullet_pool=bullet_pool,
            player=player,
            enemy_manager=self.enemy_manager,
            audio_manager=self._audio_manager,
            item_pool=self._engine_refs.get('item_pool'),
        )

        # 将 ctx 保存到 stage_manager，供渲染器访问
        self.current_context = ctx

        # 使用程序化关卡脚本
        stage = stage_class()
        stage.bind(ctx)
        stage.start()

        # 保存 stage 对象到 stage_manager，供对话渲染使用
        self.current_stage = stage

        stage_name = getattr(stage_class, 'name', stage_class.__name__)
        print(f"=== {stage_name} 开始 ===")

        while stage._active:
            stage.update()
            yield

        print(f"=== {stage_name} 结束 ===")

        # ===== 阶段 3：清理 =====
        self.current_stage = None
        self.current_context = None

        if self._audio_manager:
            self._audio_manager.stop_bgm(fade_ms=500)
            self._audio_manager.set_stage_bank(None)

        bullet_pool.clear_all()
        for _ in range(120):
            yield

    @staticmethod
    def _find_stage_directory(stage_class):
        """
        自动定位 StageScript 子类所在的关卡目录。

        使用 inspect.getfile() 获取类定义文件的路径，
        然后返回其所在目录（即关卡包目录）。
        """
        try:
            source_file = inspect.getfile(stage_class)
            return os.path.dirname(os.path.abspath(source_file))
        except (TypeError, OSError):
            return None

    # ==================== 原有接口（保持兼容） ====================

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