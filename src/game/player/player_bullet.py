"""
玩家子弹池系统
独立于敌弹系统，用于管理玩家发射的子弹
支持子弹动画（v3 配置）
"""
import numpy as np
from numba import njit
import math
from typing import Dict, List, Optional


class BulletAnimRegistry:
    """子弹动画注册表：管理 bullet_anim_id -> 帧序列的映射"""

    def __init__(self, max_anims: int = 64):
        self.max_anims = max_anims
        self.anim_names: Dict[str, int] = {}
        # 每个动画最多 32 帧
        self.frame_table = np.zeros((max_anims, 32), dtype=np.int32)
        self.frame_count = np.zeros(max_anims, dtype=np.int32)
        self.frame_duration = np.ones(max_anims, dtype=np.float32) * (4.0 / 60.0)
        self.loop_flags = np.ones(max_anims, dtype=np.int32)
        self._next_id = 0

    def register(self, name: str, sprite_ids: List[int],
                 frame_duration: int = 4, loop: bool = True) -> int:
        if name in self.anim_names:
            return self.anim_names[name]
        if self._next_id >= self.max_anims:
            return -1

        anim_id = self._next_id
        self._next_id += 1
        self.anim_names[name] = anim_id
        n = min(len(sprite_ids), 32)
        for i in range(n):
            self.frame_table[anim_id, i] = sprite_ids[i]
        self.frame_count[anim_id] = n
        self.frame_duration[anim_id] = frame_duration / 60.0
        self.loop_flags[anim_id] = 1 if loop else 0
        return anim_id

    def get_id(self, name: str) -> int:
        return self.anim_names.get(name, -1)


class PlayerBulletPool:
    """玩家子弹池"""
    
    def __init__(self, max_bullets=2000):
        self.max_bullets = max_bullets
        
        self.TYPE_NORMAL = 0
        self.TYPE_HOMING = 1
        self.TYPE_LASER = 2
        self.TYPE_MISSILE = 3
        
        self.dtype = np.dtype([
            ('pos', 'f4', 2),
            ('vel', 'f4', 2),
            ('angle', 'f4'),
            ('speed', 'f4'),
            ('alive', 'i4'),
            ('bullet_type', 'i4'),
            ('damage', 'f4'),
            ('sprite_idx', 'i4'),
            ('lifetime', 'f4'),
            ('max_lifetime', 'f4'),
            ('homing_strength', 'f4'),
            ('target_idx', 'i4'),
            ('scale', 'f4'),
            ('alpha', 'f4'),
            ('color', 'f4', 4),
            ('penetrate', 'i4'),
            ('anim_id', 'i4'),       # 动画 ID（-1 = 无动画，使用静态 sprite_idx）
            ('anim_timer', 'f4'),    # 动画计时器
        ])
        
        self.data = np.zeros(max_bullets, dtype=self.dtype)
        self.data['scale'] = 1.0
        self.data['alpha'] = 1.0
        self.data['color'] = [1.0, 1.0, 1.0, 1.0]
        self.data['anim_id'] = -1
        
        self.free_indices = list(range(max_bullets - 1, -1, -1))
        self.active_count = 0
        
        self.sprite_id_to_idx = {}
        self.sprite_idx_to_id = {}

        self.anim_registry = BulletAnimRegistry()
    
    def register_sprite(self, sprite_id: str, idx: int):
        """注册精灵ID映射"""
        self.sprite_id_to_idx[sprite_id] = idx
        self.sprite_idx_to_id[idx] = sprite_id
    
    def register_bullet_anim(self, name: str, frame_sprite_ids: List[str],
                             frame_duration: int = 4, loop: bool = True) -> int:
        """注册子弹动画，返回 anim_id"""
        idx_list = []
        for sid in frame_sprite_ids:
            if sid not in self.sprite_id_to_idx:
                n = len(self.sprite_id_to_idx)
                self.register_sprite(sid, n)
            idx_list.append(self.sprite_id_to_idx[sid])
        return self.anim_registry.register(name, idx_list, frame_duration, loop)

    def spawn(self, x: float, y: float, angle: float, speed: float,
              sprite_id: str = '', damage: float = 10.0,
              bullet_type: int = 0, homing_strength: float = 0.0,
              max_lifetime: float = 0.0, penetrate: int = 0,
              color: tuple = None, scale: float = 1.0,
              anim_id: int = -1) -> int:
        """
        生成一颗玩家子弹
        :param anim_id: 动画ID（-1=静态，使用sprite_id）
        :return: 子弹索引，-1表示池已满
        """
        if not self.free_indices:
            return -1
        
        idx = self.free_indices.pop()
        self.active_count += 1
        
        vx = speed * math.cos(angle)
        vy = speed * math.sin(angle)
        
        self.data[idx]['pos'] = [x, y]
        self.data[idx]['vel'] = [vx, vy]
        self.data[idx]['angle'] = angle
        self.data[idx]['speed'] = speed
        self.data[idx]['alive'] = 1
        self.data[idx]['bullet_type'] = bullet_type
        self.data[idx]['damage'] = damage
        self.data[idx]['lifetime'] = 0.0
        self.data[idx]['max_lifetime'] = max_lifetime
        self.data[idx]['homing_strength'] = homing_strength
        self.data[idx]['target_idx'] = -1
        self.data[idx]['scale'] = scale
        self.data[idx]['alpha'] = 1.0
        self.data[idx]['penetrate'] = penetrate
        self.data[idx]['anim_id'] = anim_id
        self.data[idx]['anim_timer'] = 0.0

        if anim_id >= 0 and anim_id < self.anim_registry.frame_count.shape[0]:
            fc = self.anim_registry.frame_count[anim_id]
            if fc > 0:
                self.data[idx]['sprite_idx'] = self.anim_registry.frame_table[anim_id, 0]
            else:
                self.data[idx]['sprite_idx'] = self.sprite_id_to_idx.get(sprite_id, 0)
        else:
            self.data[idx]['sprite_idx'] = self.sprite_id_to_idx.get(sprite_id, 0)
        
        if color:
            self.data[idx]['color'] = color
        else:
            self.data[idx]['color'] = [1.0, 1.0, 1.0, 1.0]
        
        return idx
    
    def kill(self, idx: int):
        """销毁子弹"""
        if self.data[idx]['alive']:
            self.data[idx]['alive'] = 0
            self.data[idx]['anim_id'] = -1
            self.free_indices.append(idx)
            self.active_count -= 1
    
    def update(self, dt: float, enemies=None):
        _update_player_bullets(
            self.data, dt,
            enemies.data if enemies else None,
            self.TYPE_HOMING,
            self.anim_registry.frame_table,
            self.anim_registry.frame_count,
            self.anim_registry.frame_duration,
            self.anim_registry.loop_flags,
        )
        
        for idx in range(self.max_bullets):
            if self.data[idx]['alive']:
                x, y = self.data[idx]['pos']
                if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
                    self.kill(idx)
                    continue
                
                max_life = self.data[idx]['max_lifetime']
                if max_life > 0 and self.data[idx]['lifetime'] > max_life:
                    self.kill(idx)
    
    def check_collision_with_enemies(self, enemies) -> list:
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
                alive = getattr(enemy, 'alive', getattr(enemy, '_active', True))
                if not alive:
                    continue
                
                pos = getattr(enemy, 'pos', None)
                if pos is None:
                    ex = getattr(enemy, 'x', 0)
                    ey = getattr(enemy, 'y', 0)
                else:
                    ex, ey = pos[0], pos[1]
                
                hit_radius = getattr(enemy, 'hitbox_radius', getattr(enemy, 'hit_radius', 0.05))
                combined_r = hit_radius + 0.02
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
        self.data['anim_id'] = -1
        self.free_indices = list(range(self.max_bullets - 1, -1, -1))
        self.active_count = 0

    # 兼容旧代码
    def clear_all(self):
        self.clear()


@njit(cache=True)
def _update_player_bullets(data, dt, enemy_data, TYPE_HOMING,
                           anim_frame_table, anim_frame_count,
                           anim_frame_duration, anim_loop_flags):
    for idx in range(data.shape[0]):
        if data[idx]['alive'] == 0:
            continue
        
        data[idx]['lifetime'] += dt
        
        # ---- 动画帧更新 ----
        aid = data[idx]['anim_id']
        if aid >= 0 and aid < anim_frame_count.shape[0]:
            fc = anim_frame_count[aid]
            if fc > 0:
                data[idx]['anim_timer'] += dt
                fd = anim_frame_duration[aid]
                if fd > 0:
                    frame_idx = int(data[idx]['anim_timer'] / fd)
                    if anim_loop_flags[aid] == 1:
                        frame_idx = frame_idx % fc
                    else:
                        if frame_idx >= fc:
                            frame_idx = fc - 1
                    data[idx]['sprite_idx'] = anim_frame_table[aid, frame_idx]
        
        bullet_type = data[idx]['bullet_type']
        
        # ---- 追踪弹逻辑 ----
        if bullet_type == TYPE_HOMING and enemy_data is not None:
            homing_strength = data[idx]['homing_strength']
            if homing_strength > 0:
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
                    target_angle = math.atan2(target_y - by, target_x - bx)
                    current_angle = data[idx]['angle']
                    
                    angle_diff = target_angle - current_angle
                    while angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    while angle_diff < -math.pi:
                        angle_diff += 2 * math.pi
                    
                    max_turn = homing_strength * dt
                    if angle_diff > max_turn:
                        angle_diff = max_turn
                    elif angle_diff < -max_turn:
                        angle_diff = -max_turn
                    
                    new_angle = current_angle + angle_diff
                    data[idx]['angle'] = new_angle
                    speed = data[idx]['speed']
                    data[idx]['vel'][0] = speed * math.cos(new_angle)
                    data[idx]['vel'][1] = speed * math.sin(new_angle)
        
        # ---- 更新位置 ----
        data[idx]['pos'][0] += data[idx]['vel'][0] * dt
        data[idx]['pos'][1] += data[idx]['vel'][1] * dt
