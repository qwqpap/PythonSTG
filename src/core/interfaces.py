"""
抽象接口定义 - 用于解耦各模块

包含:
- IRenderable: 可渲染对象接口
- IRenderBackend: 渲染后端接口
- ICollidable: 可碰撞对象接口
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum, auto
import numpy as np


# ============= 渲染数据结构 =============

@dataclass
class SpriteRenderData:
    """精灵渲染数据"""
    position: Tuple[float, float]  # 归一化坐标
    size: Tuple[float, float]      # 像素尺寸
    angle: float = 0.0             # 弧度
    uv: Tuple[float, float, float, float] = (0, 0, 1, 1)  # u_left, v_top, u_right, v_bottom
    color: Tuple[float, float, float, float] = (1, 1, 1, 1)  # RGBA
    texture_id: str = ""           # 纹理ID


@dataclass  
class BulletRenderBatch:
    """子弹批量渲染数据"""
    positions: np.ndarray   # shape: (N, 2), float32
    angles: np.ndarray      # shape: (N,), float32
    uvs: np.ndarray         # shape: (N, 4), float32  [u_left, v_top, u_right, v_bottom]
    scales: np.ndarray      # shape: (N, 2), float32  [width, height]
    texture_id: str = ""    # 纹理ID
    count: int = 0


class RenderLayer(Enum):
    """渲染层级"""
    BACKGROUND = 0
    ENEMY = 1
    BOSS = 2
    ITEM = 3
    PLAYER_BULLET = 4
    PLAYER_OPTION = 5
    PLAYER = 6
    ENEMY_BULLET_LARGE = 7
    ENEMY_BULLET_MEDIUM = 8
    ENEMY_BULLET_SMALL = 9
    LASER = 10
    EFFECT = 11
    HITBOX = 12
    UI = 13


# ============= 可渲染对象接口 =============

class IRenderable(ABC):
    """
    可渲染对象接口
    
    所有需要渲染的游戏对象都应实现此接口
    """
    
    @abstractmethod
    def get_render_layer(self) -> RenderLayer:
        """获取渲染层级"""
        pass
    
    @abstractmethod
    def get_render_data(self) -> Optional[SpriteRenderData]:
        """
        获取渲染数据
        
        Returns:
            SpriteRenderData 或 None（如果不需要渲染）
        """
        pass
    
    def is_visible(self) -> bool:
        """是否可见（用于裁剪）"""
        return True


class IBatchRenderable(ABC):
    """
    批量渲染接口
    
    用于子弹池等大量同类对象的批量渲染
    """
    
    @abstractmethod
    def get_render_layer(self) -> RenderLayer:
        """获取渲染层级"""
        pass
    
    @abstractmethod
    def get_batch_render_data(self) -> List[BulletRenderBatch]:
        """
        获取批量渲染数据
        
        Returns:
            按纹理分组的渲染批次列表
        """
        pass


# ============= 渲染后端接口 =============

class IRenderBackend(ABC):
    """
    渲染后端接口
    
    抽象渲染实现，支持不同的图形API（OpenGL、WebGPU等）
    """
    
    @abstractmethod
    def init(self, width: int, height: int) -> bool:
        """初始化渲染后端"""
        pass
    
    @abstractmethod
    def begin_frame(self):
        """开始新的一帧"""
        pass
    
    @abstractmethod
    def end_frame(self):
        """结束当前帧"""
        pass
    
    @abstractmethod
    def clear(self, r: float, g: float, b: float, a: float = 1.0):
        """清屏"""
        pass
    
    @abstractmethod
    def set_viewport(self, x: int, y: int, width: int, height: int):
        """设置视口"""
        pass
    
    @abstractmethod
    def draw_sprite(self, data: SpriteRenderData):
        """绘制单个精灵"""
        pass
    
    @abstractmethod
    def draw_bullet_batch(self, batch: BulletRenderBatch):
        """批量绘制子弹"""
        pass
    
    @abstractmethod
    def load_texture(self, texture_id: str, filepath: str) -> bool:
        """加载纹理"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """清理资源"""
        pass


# ============= 碰撞相关接口 =============

class ColliderType(Enum):
    """碰撞体类型"""
    CIRCLE = auto()
    RECT = auto()
    LINE = auto()   # 用于激光
    POLY = auto()   # 多边形（曲线激光段）


@dataclass
class ColliderData:
    """碰撞体数据"""
    collider_type: ColliderType
    # 圆形碰撞体
    center: Tuple[float, float] = (0, 0)
    radius: float = 0.0
    # 矩形碰撞体
    width: float = 0.0
    height: float = 0.0
    angle: float = 0.0
    # 线段碰撞体
    start: Tuple[float, float] = (0, 0)
    end: Tuple[float, float] = (0, 0)
    line_width: float = 0.0


class ICollidable(ABC):
    """
    可碰撞对象接口
    
    所有参与碰撞检测的对象都应实现此接口
    """
    
    @abstractmethod
    def get_collider(self) -> ColliderData:
        """获取碰撞体数据"""
        pass
    
    @abstractmethod
    def is_collision_enabled(self) -> bool:
        """碰撞检测是否启用"""
        pass
    
    def get_collision_layer(self) -> int:
        """获取碰撞层（用于过滤碰撞对象）"""
        return 0
    
    def get_collision_mask(self) -> int:
        """获取碰撞掩码（与哪些层碰撞）"""
        return 0xFFFFFFFF


# ============= 碰撞层常量 =============

class CollisionLayer:
    """碰撞层定义"""
    PLAYER = 1 << 0          # 玩家
    PLAYER_BULLET = 1 << 1   # 玩家子弹
    ENEMY = 1 << 2           # 敌人
    ENEMY_BULLET = 1 << 3    # 敌弹
    LASER = 1 << 4           # 激光
    ITEM = 1 << 5            # 道具
    BOSS = 1 << 6            # Boss
    
    # 常用掩码
    PLAYER_HITS = ENEMY_BULLET | LASER | ENEMY | BOSS  # 玩家会被这些击中
    PLAYER_BULLET_HITS = ENEMY | BOSS                   # 玩家子弹会击中这些
    ITEM_COLLECT = PLAYER                               # 道具被玩家收集
