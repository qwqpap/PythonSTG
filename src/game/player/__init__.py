"""
玩家系统模块
提供可配置的玩家类、射击系统、动画状态机等
支持通过脚本定义自机行为
"""

# 导入子模块
from .player_bullet import PlayerBulletPool
from .player_shot import (
    PlayerShotSystem, 
    ShotPattern, 
    ShotType, 
    OptionConfig,
    create_shot_type_from_config,
    create_options_from_config
)
from .player_animation import (
    PlayerAnimationStateMachine,
    AnimationState,
    Animation,
    AnimationConfig
)
from .player_base import PlayerBase
from .player_config import (
    PlayerConfigLoader,
    load_player,
    generate_config_template
)
from .player_script import PlayerScript, load_player_script

# 兼容旧代码：Player 别名指向 PlayerBase
Player = PlayerBase

# 提供便捷函数：通过配置文件加载特定角色
def load_sakuya(config_path: str = None) -> PlayerBase:
    """加载咲夜角色（通过配置文件和脚本）"""
    return load_player("sakuya")

__all__ = [
    # 主要类
    'Player',
    'PlayerBase',
    'PlayerBulletPool',
    'PlayerShotSystem',
    'PlayerAnimationStateMachine',
    'PlayerConfigLoader',
    'PlayerScript',
    
    # 数据类
    'ShotPattern',
    'ShotType',
    'OptionConfig',
    'AnimationState',
    'Animation',
    'AnimationConfig',
    
    # 工具函数
    'load_player',
    'load_sakuya',
    'load_player_script',
    'create_shot_type_from_config',
    'create_options_from_config',
    'generate_config_template',
]


# ============ 保留旧的碰撞检测函数（向后兼容）============
import numpy as np
from numba import njit

@njit
def check_collisions(player_x, player_y, player_radius, bullet_data):
    """
    检查玩家与子弹的碰撞
    :param player_x: 玩家x坐标
    :param player_y: 玩家y坐标
    :param player_radius: 玩家判定半径
    :param bullet_data: 子弹数据数组
    :return: 碰撞的子弹索引，-1表示无碰撞
    """
    # 直接遍历所有子弹，跳过非活跃的，避免使用np.where
    for idx in range(bullet_data.shape[0]):
        if bullet_data[idx]['alive'] == 0:
            continue
        
        # 计算欧几里得距离的平方（避免开方运算，提升性能）
        dx = bullet_data[idx]['pos'][0] - player_x
        dy = bullet_data[idx]['pos'][1] - player_y
        dist_sq = dx*dx + dy*dy
        
        # 判定半径：玩家半径 + 子弹半径
        combined_r = player_radius + bullet_data[idx]['radius']
        if dist_sq < combined_r * combined_r:
            return idx  # 返回撞到的子弹索引
    return -1