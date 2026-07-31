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
from .project_context import ProjectContext, ProjectContextError, get_project_context
from .engine_session import EngineSession
from .atomic_io import atomic_write_json, atomic_write_text

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

    # 项目路径
    'ProjectContext',
    'ProjectContextError',
    'get_project_context',
    'EngineSession',
    'atomic_write_json',
    'atomic_write_text',
]
