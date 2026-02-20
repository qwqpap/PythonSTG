"""
玩家脚本系统
允许自机通过外部脚本定义行为，而不是硬编码到引擎中

v3: 脚本完全控制发射逻辑、僚机管理和技能
"""
import importlib.util
import math
import os
from typing import TYPE_CHECKING, Optional, Callable, Any, List, Tuple

if TYPE_CHECKING:
    from .player_base import PlayerBase
    from .option_entity import OptionEntity


class PlayerScript:
    """
    玩家脚本基类（v3）
    自机脚本应继承此类并重写需要的方法。

    v3 新增：
    - fire API（fire / fire_arc / fire_circle / fire_from_option）
    - 僚机 API（spawn_option / remove_option）
    - on_shoot(is_focused) 完全控制发射
    - on_skill(slot) 技能触发
    - on_bullet_hit_enemy 被动钩子
    """
    
    def __init__(self, player: 'PlayerBase'):
        self.player = player
        self.config = {}

    # ================================================================
    # 便捷属性
    # ================================================================

    @property
    def bullet_pool(self):
        return self.player.bullet_pool

    @property
    def options(self) -> list:
        return self.player.option_manager.options

    # ================================================================
    # 发射 API（类似 SpellCard.fire 风格）
    # ================================================================

    def fire(self, bullet_anim: str = "", angle: float = 90.0,
             speed: float = 0.05, damage: float = 10.0,
             x: float = None, y: float = None,
             homing: bool = False, homing_strength: float = 5.0,
             penetrate: int = 0, scale: float = 1.0,
             sprite_id: str = '', **kwargs) -> int:
        """
        发射一颗子弹。
        :param bullet_anim: 子弹动画名（在 bullet_anims 中注册的）
        :param angle: 发射角度（度，90=向上）
        :param speed: 速度
        :param damage: 伤害
        :param x, y: 发射位置（None=玩家当前位置）
        :param homing: 是否追踪
        :param sprite_id: 静态精灵ID（bullet_anim 为空时使用）
        :return: bullet_idx
        """
        if x is None:
            x = self.player.pos[0]
        if y is None:
            y = self.player.pos[1]

        angle_rad = math.radians(angle)
        bullet_type = 1 if homing else 0

        anim_id = -1
        if bullet_anim:
            anim_id = self.bullet_pool.anim_registry.get_id(bullet_anim)

        return self.bullet_pool.spawn(
            x=x, y=y,
            angle=angle_rad,
            speed=speed,
            sprite_id=sprite_id,
            damage=damage,
            bullet_type=bullet_type,
            homing_strength=homing_strength if homing else 0.0,
            penetrate=penetrate,
            scale=scale,
            anim_id=anim_id,
        )

    def fire_from_option(self, option_idx: int, bullet_anim: str = "",
                         angle: float = 90.0, speed: float = 0.05,
                         damage: float = 5.0, **kwargs) -> int:
        """从指定僚机位置发射"""
        opts = self.options
        if option_idx < 0 or option_idx >= len(opts):
            return -1
        opt = opts[option_idx]
        return self.fire(
            bullet_anim=bullet_anim,
            angle=angle, speed=speed, damage=damage,
            x=opt.current_x, y=opt.current_y,
            **kwargs
        )

    def fire_arc(self, count: int = 5, center_angle: float = 90.0,
                 arc_angle: float = 60.0, **kwargs) -> list:
        """发射扇形弹幕"""
        results = []
        if count <= 1:
            results.append(self.fire(angle=center_angle, **kwargs))
            return results
        start = center_angle - arc_angle / 2
        step = arc_angle / (count - 1)
        for i in range(count):
            angle = start + step * i
            results.append(self.fire(angle=angle, **kwargs))
        return results

    def fire_circle(self, count: int = 8, start_angle: float = 0.0,
                    **kwargs) -> list:
        """发射圆形弹幕"""
        results = []
        for i in range(count):
            angle = start_angle + (360.0 / count) * i
            results.append(self.fire(angle=angle, **kwargs))
        return results

    # ================================================================
    # 僚机 API
    # ================================================================

    def spawn_option(self, anim_id: str = "", offset_x: float = 0.0,
                     offset_y: float = 0.0,
                     focused_offset: Tuple[float, float] = None,
                     render_size_px: float = 16.0) -> 'OptionEntity':
        """创建一个僚机"""
        from .option_entity import OptionEntity
        fx = focused_offset[0] if focused_offset else offset_x
        fy = focused_offset[1] if focused_offset else offset_y
        opt = OptionEntity(
            anim_id=anim_id,
            offset_x=offset_x,
            offset_y=offset_y,
            focused_offset_x=fx,
            focused_offset_y=fy,
            current_x=self.player.pos[0] + offset_x,
            current_y=self.player.pos[1] + offset_y,
            render_size_px=render_size_px,
        )
        self.player.option_manager.add(opt)
        return opt

    def remove_option(self, option: 'OptionEntity'):
        """移除一个僚机"""
        self.player.option_manager.remove(option)

    def clear_options(self):
        """清除所有僚机"""
        self.player.option_manager.clear()

    # ================================================================
    # 生命周期钩子（子类重写）
    # ================================================================

    def on_init(self):
        """初始化时调用（配置加载完成后）"""
        pass

    def on_update(self, dt: float):
        """每帧更新"""
        pass

    def on_shoot(self, is_focused: bool):
        """
        按住射击键时每帧调用。
        v3 脚本应重写此方法实现自定义发射逻辑。
        默认返回 False 表示使用旧版 ShotSystem。
        """
        return False

    def on_bomb(self, is_focused: bool) -> bool:
        """使用符卡时调用"""
        return False

    def on_skill(self, slot: str) -> bool:
        """技能槽位触发"""
        return False

    def on_hit(self) -> bool:
        """被弹时调用"""
        return False

    # ================================================================
    # 被动钩子
    # ================================================================

    def on_bullet_hit_enemy(self, bullet_idx: int, enemy, damage: float):
        """玩家子弹命中敌人时调用"""
        pass

    def on_graze(self, count: int):
        """擦弹时调用"""
        pass

    def on_power_change(self, old_power: float, new_power: float):
        """Power变化时调用"""
        pass

    # ================================================================
    # 兼容 v2 接口
    # ================================================================

    def get_shot_params(self) -> dict:
        """v2 兼容：获取射击参数"""
        return {}

    def get_option_positions(self) -> list:
        """v2 兼容：获取子机位置列表"""
        positions = self.player.option_manager.get_positions()
        if positions:
            return positions
        return None

    def on_render(self, renderer: Any):
        """自定义渲染"""
        pass


def load_player_script(script_path: str, player: 'PlayerBase') -> Optional[PlayerScript]:
    """
    加载玩家脚本
    :param script_path: 脚本文件路径
    :param player: 玩家实例
    :return: 脚本实例，加载失败返回 None
    """
    if not os.path.exists(script_path):
        return None
    
    try:
        spec = importlib.util.spec_from_file_location("player_script", script_path)
        if spec is None or spec.loader is None:
            print(f"警告: 无法加载脚本 {script_path}")
            return None
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        script_class = None
        for name in dir(module):
            obj = getattr(module, name)
            if (isinstance(obj, type) and 
                issubclass(obj, PlayerScript) and 
                obj is not PlayerScript):
                script_class = obj
                break
        
        if script_class is None and hasattr(module, 'create_script'):
            return module.create_script(player)
        
        if script_class is None:
            print(f"警告: 脚本 {script_path} 中没有找到 PlayerScript 子类")
            return None
        
        script = script_class(player)
        return script
        
    except Exception as e:
        print(f"加载脚本失败 {script_path}: {e}")
        import traceback
        traceback.print_exc()
        return None
