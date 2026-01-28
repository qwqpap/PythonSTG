"""
玩家脚本系统
允许自机通过外部脚本定义行为，而不是硬编码到引擎中
"""
import importlib.util
import os
from typing import TYPE_CHECKING, Optional, Callable, Any

if TYPE_CHECKING:
    from .player_base import PlayerBase


class PlayerScript:
    """
    玩家脚本基类
    自机脚本应继承此类并重写需要的方法
    """
    
    def __init__(self, player: 'PlayerBase'):
        """
        初始化脚本
        :param player: 玩家实例引用
        """
        self.player = player
    
    def on_init(self):
        """
        初始化时调用（配置加载完成后）
        可用于设置自定义属性、初始化状态等
        """
        pass
    
    def on_update(self, dt: float):
        """
        每帧更新时调用
        :param dt: 时间步长（秒）
        """
        pass
    
    def on_shoot(self) -> bool:
        """
        射击时调用
        :return: True 表示脚本处理了射击，False 使用默认射击
        """
        return False
    
    def on_bomb(self, is_focused: bool) -> bool:
        """
        使用符卡时调用
        :param is_focused: 是否处于低速模式
        :return: True 表示脚本处理了符卡，False 使用默认行为
        """
        return False
    
    def on_hit(self) -> bool:
        """
        被弹时调用
        :return: True 表示脚本处理了被弹，False 使用默认行为
        """
        return False
    
    def on_graze(self, count: int):
        """
        擦弹时调用
        :param count: 擦弹数量
        """
        pass
    
    def on_power_change(self, old_power: float, new_power: float):
        """
        Power变化时调用
        :param old_power: 旧Power值
        :param new_power: 新Power值
        """
        pass
    
    def get_shot_params(self) -> dict:
        """
        获取射击参数（每次射击前调用）
        可返回的参数:
        - spread_range: 散射角度范围
        - target_angle: 瞄准角度
        - damage_bonus: 伤害加成
        - fire_rate_multiplier: 射速倍率
        :return: 参数字典
        """
        return {}
    
    def get_option_positions(self) -> list:
        """
        获取子机位置列表
        :return: [(x, y), ...] 子机位置列表，None 表示使用默认
        """
        return None
    
    def on_render(self, renderer: Any):
        """
        自定义渲染时调用（在默认渲染之后）
        :param renderer: 渲染器实例
        """
        pass


def load_player_script(script_path: str, player: 'PlayerBase') -> Optional[PlayerScript]:
    """
    加载玩家脚本
    :param script_path: 脚本文件路径
    :param player: 玩家实例
    :return: 脚本实例，加载失败返回 None
    """
    if not os.path.exists(script_path):
        print(f"警告: 找不到脚本文件 {script_path}")
        return None
    
    try:
        # 动态加载模块
        spec = importlib.util.spec_from_file_location("player_script", script_path)
        if spec is None or spec.loader is None:
            print(f"警告: 无法加载脚本 {script_path}")
            return None
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 查找脚本类
        script_class = None
        for name in dir(module):
            obj = getattr(module, name)
            if (isinstance(obj, type) and 
                issubclass(obj, PlayerScript) and 
                obj is not PlayerScript):
                script_class = obj
                break
        
        # 如果没找到类，查找 create_script 函数
        if script_class is None and hasattr(module, 'create_script'):
            return module.create_script(player)
        
        if script_class is None:
            print(f"警告: 脚本 {script_path} 中没有找到 PlayerScript 子类")
            return None
        
        # 创建实例
        script = script_class(player)
        return script
        
    except Exception as e:
        print(f"加载脚本失败 {script_path}: {e}")
        import traceback
        traceback.print_exc()
        return None
