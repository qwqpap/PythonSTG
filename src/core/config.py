"""
游戏配置管理 - 集中管理所有游戏参数

使用方式:
    from src.core import GameConfig, get_config, init_config
    
    # 初始化（启动时调用一次）
    config = init_config()
    
    # 或使用自定义参数
    config = init_config(base_width=384, base_height=448)
    
    # 获取全局配置实例
    config = get_config()
    
    # 使用配置
    print(config.base_width)
    print(config.aspect_ratio)
"""

from dataclasses import dataclass, field
from typing import Tuple, Optional
import json
import os


@dataclass
class RenderConfig:
    """渲染相关配置"""
    # 缓冲区大小
    max_bullets: int = 50000
    max_lasers: int = 100
    max_items: int = 1000
    max_enemies: int = 200
    max_player_bullets: int = 2000
    
    # 渲染批次
    instance_buffer_size: int = 50000
    
    # 默认精灵大小（像素）
    default_sprite_size: float = 16.0


@dataclass
class PhysicsConfig:
    """物理/碰撞相关配置"""
    # 边界（归一化坐标）
    bound_left: float = -1.2
    bound_right: float = 1.2
    bound_top: float = 1.2
    bound_bottom: float = -1.2
    
    # 子弹出界销毁边界
    bullet_despawn_margin: float = 0.5


@dataclass
class PlayerConfig:
    """玩家默认配置"""
    default_hit_radius: float = 0.01
    default_graze_radius: float = 0.05
    default_speed_high: float = 0.02
    default_speed_low: float = 0.008
    default_lives: int = 3
    default_bombs: int = 3
    default_power: float = 1.0
    max_power: float = 4.0
    invincible_duration: float = 3.0


@dataclass
class GameConfig:
    """
    游戏全局配置
    
    统一管理所有硬编码的游戏参数
    """
    # ===== 核心尺寸参数 =====
    # 游戏逻辑基础尺寸（东方标准）
    base_width: int = 384
    base_height: int = 448
    
    # 窗口配置
    window_width: int = 1280
    window_height: int = 960
    game_scale: int = 2  # 游戏区域放大倍数
    
    # 游戏视口边距
    viewport_margin_x: int = 32
    
    # ===== 计算属性 =====
    @property
    def aspect_ratio(self) -> float:
        """宽高比"""
        return self.base_width / self.base_height
    
    @property
    def game_view_width(self) -> int:
        """游戏视口宽度"""
        return self.base_width * self.game_scale
    
    @property
    def game_view_height(self) -> int:
        """游戏视口高度"""
        return self.base_height * self.game_scale
    
    @property
    def game_viewport(self) -> Tuple[int, int, int, int]:
        """游戏视口 (x, y, width, height)"""
        margin_y = (self.window_height - self.game_view_height) // 2
        return (
            self.viewport_margin_x,
            margin_y,
            self.game_view_width,
            self.game_view_height
        )
    
    @property
    def y_scale_factor(self) -> float:
        """Y轴缩放因子（用于shader）"""
        return self.base_width / self.base_height
    
    @property
    def pixel_to_ndc_scale(self) -> float:
        """像素到NDC的缩放因子"""
        return 2.0 / self.base_height
    
    # ===== 子配置 =====
    render: RenderConfig = field(default_factory=RenderConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    player: PlayerConfig = field(default_factory=PlayerConfig)
    
    # ===== 工具方法 =====
    def pixel_to_normalized(self, x: float, y: float) -> Tuple[float, float]:
        """
        将像素坐标转换为归一化坐标 (-1 到 1)
        
        Args:
            x: 像素X坐标 (0 到 base_width)
            y: 像素Y坐标 (0 到 base_height)
            
        Returns:
            归一化坐标元组
        """
        norm_x = (x / self.base_width) * 2 - 1
        norm_y = (y / self.base_height) * 2 - 1
        return norm_x, norm_y
    
    def normalized_to_pixel(self, norm_x: float, norm_y: float) -> Tuple[float, float]:
        """
        将归一化坐标转换为像素坐标
        
        Args:
            norm_x: 归一化X坐标 (-1 到 1)
            norm_y: 归一化Y坐标 (-1 到 1)
            
        Returns:
            像素坐标元组
        """
        x = (norm_x + 1) * 0.5 * self.base_width
        y = (norm_y + 1) * 0.5 * self.base_height
        return x, y
    
    def is_in_bounds(self, x: float, y: float, margin: float = 0.0) -> bool:
        """
        检查归一化坐标是否在边界内
        
        Args:
            x, y: 归一化坐标
            margin: 额外边距
            
        Returns:
            是否在边界内
        """
        return (
            self.physics.bound_left - margin <= x <= self.physics.bound_right + margin and
            self.physics.bound_bottom - margin <= y <= self.physics.bound_top + margin
        )
    
    def get_shader_constants(self) -> dict:
        """获取shader中需要的常量"""
        return {
            'aspect_ratio': self.aspect_ratio,
            'y_scale': self.y_scale_factor,
            'base_width': self.base_width,
            'base_height': self.base_height,
        }
    
    def to_dict(self) -> dict:
        """导出为字典"""
        return {
            'base_width': self.base_width,
            'base_height': self.base_height,
            'window_width': self.window_width,
            'window_height': self.window_height,
            'game_scale': self.game_scale,
            'viewport_margin_x': self.viewport_margin_x,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'GameConfig':
        """从字典创建配置"""
        return cls(
            base_width=data.get('base_width', 384),
            base_height=data.get('base_height', 448),
            window_width=data.get('window_width', 1280),
            window_height=data.get('window_height', 960),
            game_scale=data.get('game_scale', 2),
            viewport_margin_x=data.get('viewport_margin_x', 32),
        )
    
    def save(self, filepath: str):
        """保存配置到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> 'GameConfig':
        """从文件加载配置"""
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        return cls()


# ===== 全局配置实例 =====
_config_instance: Optional[GameConfig] = None


def init_config(**kwargs) -> GameConfig:
    """
    初始化全局配置
    
    Args:
        **kwargs: 配置参数，会覆盖默认值
        
    Returns:
        GameConfig实例
    """
    global _config_instance
    _config_instance = GameConfig(**kwargs)
    return _config_instance


def get_config() -> GameConfig:
    """
    获取全局配置实例
    
    Returns:
        GameConfig实例，如未初始化则使用默认值
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = GameConfig()
    return _config_instance
