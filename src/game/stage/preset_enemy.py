"""
敌人预设系统 - 类似 LuaSTG 的 style 系统

允许通过预设ID快速创建具有特定外观和默认行为的敌人。
预设配置存储在 assets/configs/enemy_presets.json 中。

使用示例：

    from src.game.stage.preset_enemy import PresetEnemy, create_preset_enemy

    # 方式1: 使用预设ID直接创建
    class SimpleRedFairy(PresetEnemy):
        preset_id = "enemy1"

        async def run(self):
            await self.move_to(self.x, 0.3, duration=60)
            self.fire_circle(count=8, speed=self._default_bullet_speed())
            await self.wait(20)
            await self.move_to(self.x, -0.2, duration=60)

    # 方式2: 使用行为预设
    class AutoRedFairy(PresetEnemy):
        preset_id = "enemy1"
        behavior_preset = "rush_in_shoot_leave"  # 自动应用预设行为

    # 方式3: 动态创建（适合编辑器）
    EnemyClass = create_preset_enemy(
        preset_id="enemy_orb",
        behavior="side_pass_shoot",
        overrides={"hp": 50, "score": 200}
    )
    enemy = EnemyClass()
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
        hp / sprite / score / hitbox_radius: 可选，覆盖预设中的同名属性
    """

    # 子类需要覆盖的属性
    preset_id: Optional[str] = None
    behavior_preset: Optional[str] = None
    attack_preset: Optional[str] = None

    # 预设中可以被类属性覆盖的字段
    OVERRIDABLE_FIELDS = ('hp', 'sprite', 'score', 'hitbox_radius')

    @classmethod
    def _collect_class_overrides(cls) -> Dict[str, Any]:
        """收集子类和 create_preset_enemy(overrides=...) 显式设置的可覆盖属性。

        只检查 PresetEnemy 之前的 MRO 层级，避免误用 EnemyScript 的默认值。
        越接近子类的定义优先级越高。
        """
        chain = []
        for klass in cls.__mro__:
            if klass is PresetEnemy:
                break
            chain.append(klass)

        overrides: Dict[str, Any] = {}
        for klass in reversed(chain):
            for field in cls.OVERRIDABLE_FIELDS:
                if field in klass.__dict__:
                    overrides[field] = klass.__dict__[field]
        return overrides

    def __init__(self):
        super().__init__()

        # 加载预设配置
        if self.preset_id is None:
            raise ValueError(f"{self.__class__.__name__} 必须设置 preset_id")

        manager = PresetManager()
        preset = manager.get_preset(self.preset_id)

        if preset is None:
            raise ValueError(f"未找到预设: {self.preset_id}")

        # 应用预设配置到实例；类属性（含 overrides）优先于预设值
        overrides = self._collect_class_overrides()
        self.hp = overrides.get('hp', preset.get('hp', 30))
        self.sprite = overrides.get('sprite', preset.get('sprite', 'enemy_fairy'))
        self.score = overrides.get('score', preset.get('score', 100))
        self.hitbox_radius = overrides.get('hitbox_radius', preset.get('hitbox_radius', 0.02))

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

    def _default_bullet_speed(self) -> float:
        """预设射击动作使用的子弹速度。

        优先使用 defaults['bullet_speed']；未定义时回退到 defaults['move_speed']，
        以保持既有预设的行为不变。
        """
        return float(self.defaults.get('bullet_speed', self.defaults.get('move_speed', 2.0)))

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
        """移动到目标位置

        参数：
            target: "y=0.3"、"x=0.5"、"x=-x"（镜像到另一侧）或 [x, y]
            duration: 移动帧数，默认 60；提供时忽略 speed
            speed: 未提供 duration 时按速度计算帧数（归一化坐标/秒）
        """
        target = params.get('target', 'y=0.3')
        target_x, target_y = self.x, self.y

        # 解析目标位置
        if isinstance(target, str):
            if target.startswith('y='):
                target_y = float(target.split('=')[1])
            elif target.startswith('x='):
                x_expr = target.split('=')[1]
                target_x = -self.x if x_expr == '-x' else float(x_expr)
            else:
                return
        elif isinstance(target, (list, tuple)) and len(target) == 2:
            target_x, target_y = float(target[0]), float(target[1])
        else:
            return

        duration = params.get('duration')
        if duration is None:
            speed = max(float(params.get('speed', 2.0)), 0.001)
            distance = math.hypot(target_x - self.x, target_y - self.y)
            duration = max(1, int(distance / speed * 60))

        await self.move_to(target_x, target_y, duration=int(duration))

    async def _execute_shoot_burst(self, params: Dict[str, Any]):
        """执行连射"""
        count = params.get('count', 3)
        interval = params.get('interval', 20)

        bullet_type = self.defaults.get('bullet_type', 'ball_s')
        bullet_color = self.defaults.get('bullet_color', 'red')

        for _ in range(count):
            self.fire_circle(
                count=8,
                speed=self._default_bullet_speed(),
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
                speed=self._default_bullet_speed(),
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
        speed = self._default_bullet_speed()

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
        """沿圆形路径绕行一圈

        参数：
            center: 圆心 (x, y) 或 {"x": ..., "y": ...}，默认 (0.0, 0.5)
            radius: 半径（归一化坐标），默认 0.25
            duration: 绕行一圈的帧数，默认 180
            start_angle: 起始角度（度），默认 0
            clockwise: 顺时针绕行时为 True，默认 False
        """
        center = params.get('center', (0.0, 0.5))
        if isinstance(center, dict):
            center_x = float(center.get('x', 0.0))
            center_y = float(center.get('y', 0.5))
        elif isinstance(center, (list, tuple)) and len(center) == 2:
            center_x = float(center[0])
            center_y = float(center[1])
        else:
            center_x, center_y = 0.0, 0.5

        radius = float(params.get('radius', 0.25))
        duration = max(1, int(params.get('duration', 180)))
        start_angle = math.radians(float(params.get('start_angle', 0)))
        direction = -1.0 if params.get('clockwise', False) else 1.0

        for step in range(1, duration + 1):
            angle = start_angle + direction * 2 * math.pi * (step / duration)
            self.set_position(
                center_x + radius * math.cos(angle),
                center_y + radius * math.sin(angle),
            )
            await self.wait(1)

    async def _execute_move_linear(self, params: Dict[str, Any]):
        """沿直线匀速移动

        参数：
            dx, dy: 总位移（归一化坐标）。提供任意一个时，按总位移处理。
            direction: 移动方向（度，0=右，-90=下），未提供 dx/dy 时使用
            speed: 移动速度（归一化坐标/秒），未提供 dx/dy 时使用
            duration: 移动帧数，默认 60
        """
        duration = max(1, int(params.get('duration', 60)))

        if 'dx' in params or 'dy' in params:
            dx = float(params.get('dx', 0.0))
            dy = float(params.get('dy', 0.0))
        else:
            direction = math.radians(float(params.get('direction', -90)))
            distance = float(params.get('speed', 2.0)) * duration / 60.0
            dx = math.cos(direction) * distance
            dy = math.sin(direction) * distance

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
        RedFairyClass = create_preset_enemy("enemy1", behavior="rush_in_shoot_leave")
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
