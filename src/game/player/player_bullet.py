"""
玩家子弹池系统
独立于敌弹系统，用于管理玩家发射的子弹
"""
import numpy as np
from numba import njit
import math


class PlayerBulletPool:
    """玩家子弹池"""
    
    def __init__(self, max_bullets=2000):
        """
        初始化玩家子弹池
        :param max_bullets: 最大子弹数量
        """
        self.max_bullets = max_bullets
        
        # 子弹类型常量
        self.TYPE_NORMAL = 0      # 普通直线弹
        self.TYPE_HOMING = 1      # 追踪弹
        self.TYPE_LASER = 2       # 激光
        self.TYPE_MISSILE = 3     # 导弹（有加速度）
        
        # 创建结构化数组存储子弹数据
        self.dtype = np.dtype([
            ('pos', 'f4', 2),          # 位置 (x, y)
            ('vel', 'f4', 2),          # 速度 (vx, vy)
            ('angle', 'f4'),           # 角度（弧度）
            ('speed', 'f4'),           # 速度大小
            ('alive', 'i4'),           # 活跃状态
            ('bullet_type', 'i4'),     # 子弹类型
            ('damage', 'f4'),          # 伤害值
            ('sprite_idx', 'i4'),      # 精灵索引
            ('lifetime', 'f4'),        # 已存活时间
            ('max_lifetime', 'f4'),    # 最大生命周期（0=无限）
            ('homing_strength', 'f4'), # 追踪强度
            ('target_idx', 'i4'),      # 追踪目标索引（-1=无目标）
            ('scale', 'f4'),           # 缩放
            ('alpha', 'f4'),           # 透明度
            ('color', 'f4', 4),        # 颜色 (r, g, b, a)
            ('penetrate', 'i4'),       # 穿透次数（0=碰到就消失）
        ])
        
        # 初始化数据数组
        self.data = np.zeros(max_bullets, dtype=self.dtype)
        self.data['scale'] = 1.0
        self.data['alpha'] = 1.0
        self.data['color'] = [1.0, 1.0, 1.0, 1.0]
        
        # 空闲索引栈
        self.free_indices = list(range(max_bullets - 1, -1, -1))
        self.active_count = 0
        
        # 精灵ID到索引的映射
        self.sprite_id_to_idx = {}
        self.sprite_idx_to_id = {}
    
    def register_sprite(self, sprite_id: str, idx: int):
        """注册精灵ID映射"""
        self.sprite_id_to_idx[sprite_id] = idx
        self.sprite_idx_to_id[idx] = sprite_id
    
    def spawn(self, x: float, y: float, angle: float, speed: float,
              sprite_id: str = '', damage: float = 10.0,
              bullet_type: int = 0, homing_strength: float = 0.0,
              max_lifetime: float = 0.0, penetrate: int = 0,
              color: tuple = None, scale: float = 1.0) -> int:
        """
        生成一颗玩家子弹
        :return: 子弹索引，-1表示池已满
        """
        if not self.free_indices:
            return -1
        
        idx = self.free_indices.pop()
        self.active_count += 1
        
        # 计算速度向量
        vx = speed * math.cos(angle)
        vy = speed * math.sin(angle)
        
        # 设置子弹数据
        self.data[idx]['pos'] = [x, y]
        self.data[idx]['vel'] = [vx, vy]
        self.data[idx]['angle'] = angle
        self.data[idx]['speed'] = speed
        self.data[idx]['alive'] = 1
        self.data[idx]['bullet_type'] = bullet_type
        self.data[idx]['damage'] = damage
        self.data[idx]['sprite_idx'] = self.sprite_id_to_idx.get(sprite_id, 0)
        self.data[idx]['lifetime'] = 0.0
        self.data[idx]['max_lifetime'] = max_lifetime
        self.data[idx]['homing_strength'] = homing_strength
        self.data[idx]['target_idx'] = -1
        self.data[idx]['scale'] = scale
        self.data[idx]['alpha'] = 1.0
        self.data[idx]['penetrate'] = penetrate
        
        if color:
            self.data[idx]['color'] = color
        else:
            self.data[idx]['color'] = [1.0, 1.0, 1.0, 1.0]
        
        return idx
    
    def kill(self, idx: int):
        """销毁子弹"""
        if self.data[idx]['alive']:
            self.data[idx]['alive'] = 0
            self.free_indices.append(idx)
            self.active_count -= 1
    
    def update(self, dt: float, enemies=None):
        """
        更新所有子弹
        :param dt: 时间步长
        :param enemies: 敌人列表（用于追踪弹）
        """
        _update_player_bullets(
            self.data, dt,
            enemies.data if enemies else None,
            self.TYPE_HOMING
        )
        
        # 回收出界或超时的子弹
        for idx in range(self.max_bullets):
            if self.data[idx]['alive']:
                # 检查出界
                x, y = self.data[idx]['pos']
                if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
                    self.kill(idx)
                    continue
                
                # 检查生命周期
                max_life = self.data[idx]['max_lifetime']
                if max_life > 0 and self.data[idx]['lifetime'] > max_life:
                    self.kill(idx)
    
    def check_collision_with_enemies(self, enemies) -> list:
        """
        检查与敌人的碰撞
        :param enemies: 敌人/Boss 列表，支持 EnemyScript、BossBase 或任意有 x,y 和 damage(amount) 的对象
        :return: 碰撞列表 [(bullet_idx, enemy_idx, damage), ...]
        """
        collisions = []
        
        if enemies is None or len(enemies) == 0:
            return collisions
        
        for b_idx in range(self.max_bullets):
            if not self.data[b_idx]['alive']:
                continue
            
            bx, by = self.data[b_idx]['pos']
            damage = float(self.data[b_idx]['damage'])
            penetrate = int(self.data[b_idx]['penetrate'])
            
            for e_idx, enemy in enumerate(enemies):
                # 支持 _active / alive / is_active
                alive = getattr(enemy, 'alive', getattr(enemy, '_active', True))
                if not alive:
                    continue
                
                # 支持 pos 或 (x, y)
                pos = getattr(enemy, 'pos', None)
                if pos is None:
                    ex = getattr(enemy, 'x', 0)
                    ey = getattr(enemy, 'y', 0)
                else:
                    ex, ey = pos[0], pos[1]
                
                hit_radius = getattr(enemy, 'hitbox_radius', getattr(enemy, 'hit_radius', 0.05))
                combined_r = hit_radius + 0.02  # 子弹半径约 0.02
                dist_sq = (bx - ex) ** 2 + (by - ey) ** 2
                
                if dist_sq < combined_r ** 2:
                    collisions.append((b_idx, e_idx, damage))
                    
                    if penetrate <= 0:
                        self.kill(b_idx)
                        break
                    else:
                        self.data[b_idx]['penetrate'] -= 1
        
        return collisions
    
    def get_active_data(self):
        """获取活跃子弹的数据（用于渲染）"""
        mask = self.data['alive'] == 1
        return self.data[mask]
    
    def clear(self):
        """清空所有子弹"""
        self.data['alive'] = 0
        self.free_indices = list(range(self.max_bullets - 1, -1, -1))
        self.active_count = 0


@njit(cache=True)
def _update_player_bullets(data, dt, enemy_data, TYPE_HOMING):
    """
    更新玩家子弹（numba加速）
    """
    for idx in range(data.shape[0]):
        if data[idx]['alive'] == 0:
            continue
        
        # 更新生命周期
        data[idx]['lifetime'] += dt
        
        bullet_type = data[idx]['bullet_type']
        
        # 追踪弹逻辑
        if bullet_type == TYPE_HOMING and enemy_data is not None:
            homing_strength = data[idx]['homing_strength']
            if homing_strength > 0:
                # 找最近的敌人
                min_dist_sq = 1e10
                target_x, target_y = 0.0, 0.0
                found_target = False
                
                bx, by = data[idx]['pos']
                
                for e_idx in range(enemy_data.shape[0]):
                    if enemy_data[e_idx]['alive'] == 0:
                        continue
                    
                    ex = enemy_data[e_idx]['pos'][0]
                    ey = enemy_data[e_idx]['pos'][1]
                    dist_sq = (ex - bx) ** 2 + (ey - by) ** 2
                    
                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq
                        target_x, target_y = ex, ey
                        found_target = True
                
                if found_target:
                    # 计算目标角度
                    target_angle = math.atan2(target_y - by, target_x - bx)
                    current_angle = data[idx]['angle']
                    
                    # 角度差
                    angle_diff = target_angle - current_angle
                    # 归一化到 [-pi, pi]
                    while angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    while angle_diff < -math.pi:
                        angle_diff += 2 * math.pi
                    
                    # 限制转向速度
                    max_turn = homing_strength * dt
                    if angle_diff > max_turn:
                        angle_diff = max_turn
                    elif angle_diff < -max_turn:
                        angle_diff = -max_turn
                    
                    # 更新角度和速度方向
                    new_angle = current_angle + angle_diff
                    data[idx]['angle'] = new_angle
                    speed = data[idx]['speed']
                    data[idx]['vel'][0] = speed * math.cos(new_angle)
                    data[idx]['vel'][1] = speed * math.sin(new_angle)
        
        # 更新位置
        data[idx]['pos'][0] += data[idx]['vel'][0] * dt
        data[idx]['pos'][1] += data[idx]['vel'][1] * dt
