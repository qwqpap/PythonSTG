"""
核心模块 - 包含配置、抽象接口等基础组件
"""

from .config import GameConfig, get_config, init_config, RenderConfig, PhysicsConfig, PlayerConfig
from .interfaces import (
    IRenderable, IRenderBackend, ICollidable, IBatchRenderable,
    SpriteRenderData, BulletRenderBatch, RenderLayer,
    ColliderType, ColliderData, CollisionLayer
)
from .collision import CollisionManager, get_collision_manager, CollisionResult, BulletCollisionResult
from .sprite_registry import SpriteRegistry, SpriteInfo, get_sprite_registry, init_sprite_registry

__all__ = [
    # 配置
    'GameConfig',
    'get_config',
    'init_config',
    'RenderConfig',
    'PhysicsConfig',
    'PlayerConfig',
    
    # 渲染接口
    'IRenderable',
    'IRenderBackend',
    'ICollidable',
    'IBatchRenderable',
    'SpriteRenderData',
    'BulletRenderBatch',
    'RenderLayer',
    
    # 碰撞接口
    'ColliderType',
    'ColliderData',
    'CollisionLayer',
    'CollisionManager',
    'get_collision_manager',
    'CollisionResult',
    'BulletCollisionResult',
    
    # 精灵注册表
    'SpriteRegistry',
    'SpriteInfo',
    'get_sprite_registry',
    'init_sprite_registry',
]
