"""
优化版子弹池 - 使用整数精灵索引和向量化渲染数据准备

主要优化:
1. sprite_id 使用 uint16 整数索引（从32字节减少到2字节）
2. 预计算并缓存渲染数据（UV、尺寸）
3. 使用向量化操作准备批量渲染数据
4. 支持按纹理/大小分组的高效渲染
"""

import numpy as np
from numba import njit
import math
from typing import Dict, List, Tuple, Optional, Callable, Any
from dataclasses import dataclass

# 使用绝对导入
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from src.core.sprite_registry import SpriteRegistry, get_sprite_registry
from src.core.config import get_config


@dataclass
class SpawnRequest:
    """生成请求"""
    x: float
    y: float
    angle: float
    speed: float
    sprite_idx: int = 0
    delay: int = 0
    acc: Tuple[float, float] = (0.0, 0.0)
    max_lifetime: float = 0.0
    radius: float = 0.0
    init: Optional[Callable] = None
    on_death: Optional[Callable] = None


@dataclass
class DeathEvent:
    """死亡事件"""
    idx: int
    x: float
    y: float
    handler: Optional[Callable] = None


class OptimizedBulletPool:
    """
    优化版子弹池
    
    相比原版的主要改进:
    - sprite_idx 使用 uint16（2字节 vs 原来的128字节字符串）
    - 渲染数据使用向量化操作批量准备
    - 支持按纹理/大小分类高效分组
    
    兼容性:
    - 提供与原BulletPool相同的接口
    - 可以通过sprite_id字符串spawn（内部转换为索引）
    """
    
    def __init__(self, max_bullets: int = 50000, sprite_registry: SpriteRegistry = None):
        """
        初始化子弹池
        
        Args:
            max_bullets: 最大子弹数量
            sprite_registry: 精灵注册表（为None则使用全局实例）
        """
        self.max_bullets = max_bullets
        self.sprite_registry = sprite_registry or get_sprite_registry()
        
        # 优化后的数据结构 - sprite_idx使用uint16
        self.dtype = np.dtype([
            ('pos', 'f4', 2),        # 位置 (x, y)
            ('vel', 'f4', 2),        # 速度 (vx, vy)
            ('acc', 'f4', 2),        # 加速度 (ax, ay)
            ('angle', 'f4'),         # 角度（弧度）
            ('speed', 'f4'),         # 速度大小
            ('alive', 'i4'),         # 活跃状态
            ('sprite_idx', 'u2'),    # 精灵索引（优化：2字节 vs 原128字节）
            ('radius', 'f4'),        # 碰撞半径
            ('lifetime', 'f4'),      # 生命周期
            ('max_lifetime', 'f4'),  # 最大生命周期
        ])
        
        # 初始化数据数组
        self.data = np.zeros(max_bullets, dtype=self.dtype)
        
        # 空闲索引列表
        self.free_indices = list(range(max_bullets))
        
        # 死亡处理器
        self.death_handlers: Dict[int, Callable] = {}
        
        # 生成队列和死亡队列
        self.spawn_queue: List[SpawnRequest] = []
        self.death_queue: List[DeathEvent] = []
        
        # 上一帧活跃状态
        self.last_alive = np.zeros(max_bullets, dtype='i4')
        
        # ===== 渲染优化相关 =====
        # 预分配渲染数据缓冲区
        self._render_positions = np.zeros((max_bullets, 2), dtype='f4')
        self._render_angles = np.zeros(max_bullets, dtype='f4')
        self._render_uvs = np.zeros((max_bullets, 4), dtype='f4')
        self._render_scales = np.zeros((max_bullets, 2), dtype='f4')
        self._render_tex_indices = np.zeros(max_bullets, dtype='u2')
        self._render_categories = np.zeros(max_bullets, dtype='u1')
        
        # 缓存配置
        config = get_config()
        self._scale_factor = config.pixel_to_ndc_scale
        
        # 兼容旧接口的sprite_id映射
        self._sprite_id_to_idx: Dict[str, int] = {}
    
    def register_sprite(self, sprite_id: str) -> int:
        """
        注册精灵ID（兼容旧接口）
        
        实际的精灵数据应通过sprite_registry注册
        这里只建立ID到索引的映射缓存
        """
        if sprite_id in self._sprite_id_to_idx:
            return self._sprite_id_to_idx[sprite_id]
        
        idx = self.sprite_registry.get_index(sprite_id)
        self._sprite_id_to_idx[sprite_id] = idx
        return idx
    
    def spawn_bullet(
        self,
        x: float,
        y: float,
        angle: float,
        speed: float,
        sprite_id: str = '',
        sprite_idx: int = -1,
        delay: int = 0,
        acc: Tuple[float, float] = None,
        max_lifetime: float = 0.0,
        radius: float = 0.0,
        init: Callable = None,
        on_death: Callable = None,
        **kwargs  # 忽略不支持的参数
    ) -> int:
        """
        生成子弹
        
        Args:
            x, y: 初始位置
            angle: 角度（弧度）
            speed: 速度
            sprite_id: 精灵ID字符串（兼容旧接口）
            sprite_idx: 精灵索引（优先使用）
            delay: 延迟帧数
            acc: 加速度 (ax, ay)
            max_lifetime: 最大生命周期
            radius: 碰撞半径
            init: 初始化回调
            on_death: 死亡回调
            
        Returns:
            子弹索引，-1表示失败
        """
        acc = acc or (0.0, 0.0)
        
        # 获取精灵索引
        if sprite_idx < 0:
            if sprite_id:
                sprite_idx = self.register_sprite(sprite_id)
            else:
                sprite_idx = 0  # 默认精灵
        
        # 处理延迟
        if delay > 0:
            self.spawn_queue.append(SpawnRequest(
                x=x, y=y, angle=angle, speed=speed,
                sprite_idx=sprite_idx, delay=delay, acc=acc,
                max_lifetime=max_lifetime, radius=radius,
                init=init, on_death=on_death
            ))
            return -1
        
        # 获取空闲索引
        if not self.free_indices:
            return -1
        
        idx = self.free_indices.pop()
        
        # 设置数据
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed
        
        self.data['pos'][idx] = (x, y)
        self.data['vel'][idx] = (vx, vy)
        self.data['acc'][idx] = acc
        self.data['angle'][idx] = angle
        self.data['speed'][idx] = speed
        self.data['sprite_idx'][idx] = sprite_idx
        self.data['radius'][idx] = radius
        self.data['lifetime'][idx] = 0.0
        self.data['max_lifetime'][idx] = max_lifetime
        self.data['alive'][idx] = 1
        
        # 死亡处理器
        if on_death:
            self.death_handlers[idx] = on_death
        elif idx in self.death_handlers:
            del self.death_handlers[idx]
        
        # 初始化回调
        if init:
            init(self, idx)
        
        return idx
    
    def spawn_pattern(
        self,
        x: float,
        y: float,
        angle: float,
        speed: float,
        count: int = 18,
        angle_spread: float = math.pi * 2,
        sprite_id: str = '',
        sprite_idx: int = -1,
        max_lifetime: float = 0.0,
        radius: float = 0.0,
        acc: Tuple[float, float] = None,
        on_death: Callable = None,
    ):
        """
        批量生成圆形扩散子弹（向量化优化）
        """
        if count <= 0:
            return
        
        acc = acc or (0.0, 0.0)
        
        # 获取精灵索引
        if sprite_idx < 0:
            sprite_idx = self.register_sprite(sprite_id) if sprite_id else 0
        
        # 计算角度数组
        angle_step = angle_spread / count
        angles = np.array([angle + i * angle_step for i in range(count)], dtype='f4')
        
        # 计算速度向量
        vxs = np.cos(angles) * speed
        vys = np.sin(angles) * speed
        
        # 获取空闲索引
        available = min(count, len(self.free_indices))
        if available == 0:
            return
        
        use_indices = []
        for _ in range(available):
            use_indices.append(self.free_indices.pop())
        use_indices = np.array(use_indices, dtype='i4')
        n = len(use_indices)
        
        # 批量写入（向量化）
        self.data['pos'][use_indices, 0] = x
        self.data['pos'][use_indices, 1] = y
        self.data['vel'][use_indices, 0] = vxs[:n]
        self.data['vel'][use_indices, 1] = vys[:n]
        self.data['acc'][use_indices, 0] = acc[0]
        self.data['acc'][use_indices, 1] = acc[1]
        self.data['angle'][use_indices] = angles[:n]
        self.data['speed'][use_indices] = speed
        self.data['sprite_idx'][use_indices] = sprite_idx
        self.data['radius'][use_indices] = radius
        self.data['lifetime'][use_indices] = 0.0
        self.data['max_lifetime'][use_indices] = max_lifetime
        self.data['alive'][use_indices] = 1
        
        # 死亡处理器
        if on_death:
            for idx in use_indices:
                self.death_handlers[idx] = on_death
    
    def kill_bullet(self, idx: int, handler: Callable = None):
        """杀死子弹"""
        if 0 <= idx < self.max_bullets and self.data['alive'][idx]:
            self.data['alive'][idx] = 0
            
            if handler is None:
                handler = self.death_handlers.pop(idx, None)
            
            x, y = self.data['pos'][idx]
            self.death_queue.append(DeathEvent(idx, x, y, handler))
    
    def update(self, dt: float):
        """更新所有子弹"""
        # 保存当前活跃状态
        self.last_alive[:] = self.data['alive']
        
        # 调用Numba优化的更新函数
        _update_bullets_optimized(self.data, dt)
        
        # 收集死亡事件
        self._collect_deaths()
        
        # 处理死亡队列
        self._process_death_queue()
        
        # 处理生成队列
        self._process_spawn_queue()
    
    def _collect_deaths(self):
        """收集死亡事件"""
        died_mask = (self.last_alive == 1) & (self.data['alive'] == 0)
        died_indices = np.where(died_mask)[0]
        
        for idx in died_indices:
            x, y = self.data['pos'][idx]
            handler = self.death_handlers.pop(idx, None)
            self.death_queue.append(DeathEvent(idx, x, y, handler))
            self.free_indices.append(idx)
    
    def _process_death_queue(self):
        """处理死亡队列"""
        for event in self.death_queue:
            if event.handler:
                event.handler(self, event)
        self.death_queue.clear()
    
    def _process_spawn_queue(self):
        """处理生成队列"""
        new_queue = []
        for req in self.spawn_queue:
            if req.delay <= 0:
                self._spawn_from_request(req)
            else:
                req.delay -= 1
                new_queue.append(req)
        self.spawn_queue = new_queue
    
    def _spawn_from_request(self, req: SpawnRequest):
        """从生成请求创建子弹"""
        if not self.free_indices:
            return
        
        idx = self.free_indices.pop()
        
        vx = math.cos(req.angle) * req.speed
        vy = math.sin(req.angle) * req.speed
        
        self.data['pos'][idx] = (req.x, req.y)
        self.data['vel'][idx] = (vx, vy)
        self.data['acc'][idx] = req.acc
        self.data['angle'][idx] = req.angle
        self.data['speed'][idx] = req.speed
        self.data['sprite_idx'][idx] = req.sprite_idx
        self.data['radius'][idx] = req.radius
        self.data['lifetime'][idx] = 0.0
        self.data['max_lifetime'][idx] = req.max_lifetime
        self.data['alive'][idx] = 1
        
        if req.on_death:
            self.death_handlers[idx] = req.on_death
        
        if req.init:
            req.init(self, idx)
    
    # ===== 渲染数据准备（向量化优化） =====
    
    def prepare_render_data(self) -> Dict[int, Dict]:
        """
        准备渲染数据（向量化操作）
        
        Returns:
            按纹理索引分组的渲染数据
            {texture_idx: {
                'positions': ndarray,
                'angles': ndarray,
                'uvs': ndarray,
                'scales': ndarray,
                'categories': ndarray,
                'count': int
            }}
        """
        # 获取活跃子弹掩码
        active_mask = self.data['alive'] == 1
        active_count = np.sum(active_mask)
        
        if active_count == 0:
            return {}
        
        # 提取活跃子弹数据
        active_data = self.data[active_mask]
        
        # 向量化准备渲染数据
        positions = active_data['pos']
        angles = active_data['angle']
        sprite_indices = active_data['sprite_idx']
        
        # 从注册表批量获取UV和尺寸
        uv_array = self.sprite_registry._uv_array
        size_array = self.sprite_registry._size_array
        category_array = self.sprite_registry._category_array
        tex_idx_array = self.sprite_registry._texture_idx_array
        
        # 向量化索引（关键优化点）
        uvs = uv_array[sprite_indices]
        scales = size_array[sprite_indices] * self._scale_factor
        categories = category_array[sprite_indices]
        tex_indices = tex_idx_array[sprite_indices]
        
        # 按纹理分组
        result = {}
        unique_tex = np.unique(tex_indices)
        
        for tex_idx in unique_tex:
            mask = tex_indices == tex_idx
            count = np.sum(mask)
            
            result[tex_idx] = {
                'positions': positions[mask],
                'angles': angles[mask],
                'uvs': uvs[mask],
                'scales': scales[mask],
                'categories': categories[mask],
                'count': count,
            }
        
        return result
    
    def prepare_render_data_sorted(self) -> List[Dict]:
        """
        准备按大小分类排序的渲染数据
        
        Returns:
            渲染批次列表，按大小从大到小排序
        """
        grouped = self.prepare_render_data()
        
        result = []
        # 按大小类别（从大到小）和纹理分组
        for category in range(6):  # LASER=0 到 TINY=5
            for tex_idx, data in grouped.items():
                cat_mask = data['categories'] == category
                count = np.sum(cat_mask)
                
                if count > 0:
                    result.append({
                        'texture_idx': tex_idx,
                        'texture_path': self.sprite_registry.get_texture_path(tex_idx),
                        'positions': data['positions'][cat_mask],
                        'angles': data['angles'][cat_mask],
                        'uvs': data['uvs'][cat_mask],
                        'scales': data['scales'][cat_mask],
                        'count': count,
                        'category': category,
                    })
        
        return result
    
    # ===== 兼容旧接口 =====
    
    def get_active_bullets(self):
        """
        兼容旧版接口：获取活跃子弹数据
        
        Returns:
            (positions, colors, angles, sprite_ids)
        """
        active_mask = self.data['alive'] == 1
        active_data = self.data[active_mask]
        
        if len(active_data) == 0:
            return np.array([]), np.array([]), np.array([]), np.array([])
        
        positions = active_data['pos']
        colors = np.zeros((len(active_data), 3), dtype='f4')  # 不使用颜色
        angles = active_data['angle']
        
        # 将索引转换回字符串ID（兼容旧渲染器）
        sprite_ids = np.array([
            self.sprite_registry.get_id(idx) 
            for idx in active_data['sprite_idx']
        ])
        
        return positions, colors, angles, sprite_ids
    
    def clear_all(self):
        """清空所有子弹"""
        self.data['alive'] = 0
        self.spawn_queue.clear()
        self.death_queue.clear()
        self.free_indices = list(range(self.max_bullets))
        self.death_handlers.clear()


# ============= Numba JIT 优化函数 =============

@njit(cache=True)
def _update_bullets_optimized(data, dt: float):
    """
    优化的子弹更新函数（Numba JIT）
    """
    n = len(data)
    for i in range(n):
        if data[i]['alive'] == 0:
            continue
        
        # 更新生命周期
        data[i]['lifetime'] += dt
        
        # 检查最大生命周期
        max_life = data[i]['max_lifetime']
        if max_life > 0.0 and data[i]['lifetime'] >= max_life:
            data[i]['alive'] = 0
            continue
        
        # 更新速度（加速度）
        data[i]['vel'][0] += data[i]['acc'][0] * dt
        data[i]['vel'][1] += data[i]['acc'][1] * dt
        
        # 更新位置
        data[i]['pos'][0] += data[i]['vel'][0] * dt
        data[i]['pos'][1] += data[i]['vel'][1] * dt
        
        # 更新速度大小和角度
        vx, vy = data[i]['vel'][0], data[i]['vel'][1]
        data[i]['speed'] = math.sqrt(vx * vx + vy * vy)
        data[i]['angle'] = math.atan2(vy, vx)
        
        # 边界检测
        x, y = data[i]['pos'][0], data[i]['pos'][1]
        if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
            data[i]['alive'] = 0
