"""
敌人预设系统 - 类似 LuaSTG 的 style 系统

允许通过预设ID快速创建具有特定外观和默认行为的敌人。
预设配置存储在 assets/configs/enemy_presets.json 中。

使用示例：

    from src.game.stage.preset_enemy import PresetEnemy, create_preset_enemy

    # 方式1: 使用预设ID直接创建
    class SimpleRedFairy(PresetEnemy):
        preset_id = "fairy_red"

        async def run(self):
            await self.move_to(self.x, 0.3, duration=60)
            self.fire_circle(count=8, speed=self.defaults['move_speed'])
            await self.wait(20)
            await self.move_to(self.x, -0.2, duration=60)

    # 方式2: 使用行为预设
    class AutoRedFairy(PresetEnemy):
        preset_id = "fairy_red"
        behavior_preset = "rush_in_shoot_leave"  # 自动应用预设行为

    # 方式3: 动态创建（适合编辑器）
    enemy = create_preset_enemy(
        preset_id="fairy_blue",
        behavior="side_pass_shoot",
        overrides={"hp": 50, "score": 200}
    )
"""

import json
import math
from pathlib import Path
from typing import Dict, Any, Optional, List
from abc import ABC
from .enemy_script import EnemyScript


class PresetManager:
    """敌人预设管理器 - 单例模式"""

    _instance: Optional['PresetManager'] = None
    _presets: Dict[str, Any] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._presets = None
        return cls._instance

    def load_presets(self, config_path: Optional[Path] = None):
        """加载预设配置文件"""
        if config_path is None:
            # 默认路径
            config_path = Path(__file__).parent.parent.parent.parent / "assets" / "configs" / "enemy_presets.json"

        if not config_path.exists():
            print(f"警告: 预设配置文件不存在: {config_path}")
            self._presets = {"presets": {}, "behavior_presets": {}, "attack_presets": {}}
            return

        with open(config_path, 'r', encoding='utf-8') as f:
            self._presets = json.load(f)

        print(f"已加载 {len(self._presets.get('presets', {}))} 个敌人预设")
        print(f"已加载 {len(self._presets.get('behavior_presets', {}))} 个行为预设")
        print(f"已加载 {len(self._presets.get('attack_presets', {}))} 个攻击预设")

    def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """获取指定ID的预设配置"""
        if self._presets is None:
            self.load_presets()

        return self._presets.get('presets', {}).get(preset_id)

    def get_behavior_preset(self, behavior_id: str) -> Optional[Dict[str, Any]]:
        """获取行为预设"""
        if self._presets is None:
            self.load_presets()

        return self._presets.get('behavior_presets', {}).get(behavior_id)

    def get_attack_preset(self, attack_id: str) -> Optional[Dict[str, Any]]:
        """获取攻击预设"""
        if self._presets is None:
            self.load_presets()

        return self._presets.get('attack_presets', {}).get(attack_id)

    def list_presets(self) -> List[str]:
        """列出所有可用的预设ID"""
        if self._presets is None:
            self.load_presets()

        return list(self._presets.get('presets', {}).keys())

    def list_behaviors(self) -> List[str]:
        """列出所有可用的行为预设ID"""
        if self._presets is None:
            self.load_presets()

        return list(self._presets.get('behavior_presets', {}).keys())

    def get_preset_info(self, preset_id: str) -> Optional[str]:
        """获取预设的友好名称和描述"""
        preset = self.get_preset(preset_id)
        if preset:
            return f"{preset.get('name', preset_id)} (HP:{preset.get('hp')}, 得分:{preset.get('score')})"
        return None


class PresetEnemy(EnemyScript, ABC):
    """
    预设敌人基类

    子类通过设置 preset_id 来自动加载对应的预设配置。
    可选设置 behavior_preset 来自动应用预设行为。

    属性：
        preset_id: 预设ID（必须设置）
        behavior_preset: 行为预设ID（可选，如果设置则自动执行）
        attack_preset: 攻击预设ID（可选）
    """

    # 子类需要覆盖的属性
    preset_id: Optional[str] = None
    behavior_preset: Optional[str] = None
    attack_preset: Optional[str] = None

    def __init__(self):
        super().__init__()

        # 加载预设配置
        if self.preset_id is None:
            raise ValueError(f"{self.__class__.__name__} 必须设置 preset_id")

        manager = PresetManager()
        preset = manager.get_preset(self.preset_id)

        if preset is None:
            raise ValueError(f"未找到预设: {self.preset_id}")

        # 应用预设配置到实例
        self.hp = preset.get('hp', 30)
        self.sprite = preset.get('sprite', 'enemy_fairy')
        self.score = preset.get('score', 100)
        self.hitbox_radius = preset.get('hitbox_radius', 0.02)

        # 存储默认值（子类可以使用）
        self.defaults = preset.get('defaults', {})
        self.animations = preset.get('animations', {})
        self.drop_item = preset.get('drop', None)

        # 加载行为预设（如果有）
        self._behavior_data = None
        if self.behavior_preset:
            self._behavior_data = manager.get_behavior_preset(self.behavior_preset)

        # 加载攻击预设（如果有）
        self._attack_data = None
        if self.attack_preset:
            self._attack_data = manager.get_attack_preset(self.attack_preset)

    async def run(self):
        """
        默认行为：如果设置了 behavior_preset，则执行预设行为。
        否则子类需要覆盖此方法。
        """
        if self._behavior_data:
            await self._execute_behavior_preset()
        else:
            # 如果没有预设行为且子类也没有覆盖 run()，则执行默认行为
            await self._default_behavior()

    async def _execute_behavior_preset(self):
        """执行预设行为"""
        if not self._behavior_data:
            return

        phases = self._behavior_data.get('phases', [])

        for phase in phases:
            action = phase.get('action')
            params = phase.get('params', {})

            if action == 'move_to':
                await self._execute_move_to(params)
            elif action == 'shoot_burst':
                await self._execute_shoot_burst(params)
            elif action == 'shoot_continuous':
                await self._execute_shoot_continuous(params)
            elif action == 'shoot_pattern':
                await self._execute_shoot_pattern(params)
            elif action == 'wait':
                await self.wait(params.get('duration', 60))
            elif action == 'move_circle':
                await self._execute_move_circle(params)
            elif action == 'move_linear':
                await self._execute_move_linear(params)

    async def _execute_move_to(self, params: Dict[str, Any]):
        """执行移动到目标位置"""
        target = params.get('target', 'y=0.3')
        duration = params.get('duration', 60)

        # 解析目标位置
        if isinstance(target, str):
            if target.startswith('y='):
                y = float(target.split('=')[1])
                await self.move_to(self.x, y, duration=duration)
            elif target.startswith('x='):
                x_expr = target.split('=')[1]
                x = -self.x if x_expr == '-x' else float(x_expr)
                await self.move_to(x, self.y, duration=duration)
        elif isinstance(target, (list, tuple)) and len(target) == 2:
            await self.move_to(target[0], target[1], duration=duration)

    async def _execute_shoot_burst(self, params: Dict[str, Any]):
        """执行连射"""
        count = params.get('count', 3)
        interval = params.get('interval', 20)

        bullet_type = self.defaults.get('bullet_type', 'ball_s')
        bullet_color = self.defaults.get('bullet_color', 'red')

        for _ in range(count):
            self.fire_circle(
                count=8,
                speed=self.defaults.get('move_speed', 2.0),
                bullet_type=bullet_type,
                color=bullet_color
            )
            await self.wait(interval)

    async def _execute_shoot_continuous(self, params: Dict[str, Any]):
        """执行持续射击"""
        count = params.get('count', 5)
        interval = params.get('interval', 10)

        bullet_type = self.defaults.get('bullet_type', 'ball_s')
        bullet_color = self.defaults.get('bullet_color', 'red')

        for _ in range(count):
            self.fire_at_player(
                speed=self.defaults.get('move_speed', 2.0),
                bullet_type=bullet_type,
                color=bullet_color
            )
            await self.wait(interval)

    async def _execute_shoot_pattern(self, params: Dict[str, Any]):
        """执行弹幕模式"""
        pattern = params.get('pattern', 'circle')
        count = params.get('count', 8)

        bullet_type = self.defaults.get('bullet_type', 'ball_s')
        bullet_color = self.defaults.get('bullet_color', 'red')
        speed = self.defaults.get('move_speed', 2.0)

        if pattern == 'circle':
            self.fire_circle(
                count=count,
                speed=speed,
                bullet_type=bullet_type,
                color=bullet_color
            )
        elif pattern == 'arc':
            self.fire_arc(
                count=count,
                speed=speed,
                center_angle=-90,
                arc_angle=120,
                bullet_type=bullet_type,
                color=bullet_color
            )

    async def _execute_move_circle(self, params: Dict[str, Any]):
        """执行圆形移动（简化版）"""
        duration = params.get('duration', 180)
        # 这里是简化实现，实际可能需要更复杂的圆形路径
        for _ in range(duration // 10):
            await self.wait(10)

    async def _execute_move_linear(self, params: Dict[str, Any]):
        """执行线性移动"""
        direction = params.get('direction', -90)
        speed = params.get('speed', 2.0)
        duration = params.get('duration', 60)

        dx = math.cos(math.radians(direction)) * speed / 60
        dy = math.sin(math.radians(direction)) * speed / 60

        await self.move_linear(dx, dy, duration=duration)

    async def _default_behavior(self):
        """默认行为：简单的进入-停留-离开"""
        await self.move_to(self.x, 0.3, duration=60)
        await self.wait(60)
        await self.move_to(self.x, -0.2, duration=60)


def create_preset_enemy(
    preset_id: str,
    behavior: Optional[str] = None,
    attack: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None
) -> type:
    """
    动态创建预设敌人类

    参数：
        preset_id: 预设ID
        behavior: 行为预设ID（可选）
        attack: 攻击预设ID（可选）
        overrides: 覆盖的属性字典（可选）

    返回：
        动态创建的敌人类

    示例：
        RedFairyClass = create_preset_enemy("fairy_red", behavior="rush_in_shoot_leave")
        enemy_instance = RedFairyClass()
    """

    # 创建类属性
    class_attrs = {
        'preset_id': preset_id,
        'behavior_preset': behavior,
        'attack_preset': attack,
    }

    # 应用覆盖
    if overrides:
        class_attrs.update(overrides)

    # 动态创建类
    class_name = f"Dynamic_{preset_id}_{behavior or 'default'}"
    return type(class_name, (PresetEnemy,), class_attrs)


def list_available_presets() -> Dict[str, List[str]]:
    """
    列出所有可用的预设

    返回：
        包含 'enemies', 'behaviors', 'attacks' 的字典
    """
    manager = PresetManager()

    return {
        'enemies': manager.list_presets(),
        'behaviors': manager.list_behaviors(),
        'attacks': list(manager._presets.get('attack_presets', {}).keys()) if manager._presets else []
    }


def get_preset_details(preset_id: str) -> Optional[Dict[str, Any]]:
    """获取预设的详细信息（用于编辑器UI）"""
    manager = PresetManager()
    return manager.get_preset(preset_id)
