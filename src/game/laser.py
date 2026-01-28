"""
激光系统 - 实现直线激光和曲线激光
完全重构版本，使用图集纹理和精灵系统
参考 LuaSTG 的激光实现

激光纹理格式：
- 每个激光纹理(laser1-4.png)分为3部分：头(head)、身(body)、尾(tail)
- 16种颜色变体垂直排列，每行高度 = 总高度/16
- 渲染时按l1/l2/l3缩放各部分
"""
import numpy as np
import math
import json
import os
from typing import Tuple, Optional, List, Dict, Any

try:
    from numba import jit
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    print("Warning: Numba not available, collision detection will be slower")
    def jit(*args, **kwargs):
        def decorator(f):
            return f
        return decorator


# ============= Numba JIT 优化的碰撞检测 =============

@jit(nopython=True)
def _check_laser_collision_jit(px: float, py: float, radius: float,
                               x: float, y: float, angle: float,
                               l1: float, l2: float, l3: float,
                               width: float) -> bool:
    """
    JIT优化的激光碰撞检测 (三段式)
    
    Args:
        px, py: 玩家位置
        radius: 玩家碰撞半径
        x, y: 激光起点
        angle: 激光角度（弧度）
        l1, l2, l3: 头部/身体/尾部长度
        width: 激光当前宽度
    """
    # 转换到激光局部坐标系
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    
    dx = px - x
    dy = py - y
    
    # 旋转到激光坐标系 (激光沿正X方向)
    local_x = dx * cos_a + dy * sin_a
    local_y = -dx * sin_a + dy * cos_a
    local_y = abs(local_y)
    
    if local_x < 0:
        return False
    
    half_width = width * 0.5 + radius
    total_length = l1 + l2 + l3
    
    if local_x > total_length:
        return False
    
    # 头部（锥形，从0到half_width）
    if local_x < l1:
        if l1 > 0:
            segment_width = (local_x / l1) * half_width
        else:
            segment_width = half_width
        return local_y < segment_width
    
    # 身体（矩形）
    if local_x < l1 + l2:
        return local_y < half_width
    
    # 尾部（锥形，从half_width到0）
    remaining = total_length - local_x
    if l3 > 0:
        segment_width = (remaining / l3) * half_width
    else:
        segment_width = half_width
    return local_y < segment_width


@jit(nopython=True)
def _check_bent_laser_collision_jit(px: float, py: float, radius: float,
                                    path_x: np.ndarray, path_y: np.ndarray,
                                    width: float, path_len: int) -> bool:
    """JIT优化的曲线激光碰撞检测"""
    collision_dist_sq = (width * 0.5 + radius) ** 2
    
    for i in range(path_len - 1):
        x1, y1 = path_x[i], path_y[i]
        x2, y2 = path_x[i + 1], path_y[i + 1]
        
        dx = x2 - x1
        dy = y2 - y1
        length_sq = dx * dx + dy * dy
        
        if length_sq < 1e-6:
            dist_sq = (px - x1) ** 2 + (py - y1) ** 2
        else:
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
            nearest_x = x1 + t * dx
            nearest_y = y1 + t * dy
            dist_sq = (px - nearest_x) ** 2 + (py - nearest_y) ** 2
        
        if dist_sq < collision_dist_sq:
            return True
    
    return False


# ============= 激光纹理数据管理 =============

class LaserTextureData:
    """激光纹理数据（单例，管理所有激光纹理信息）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.textures: Dict[str, Dict] = {}
        self.bent_laser_data: Dict = {}
        self.loaded = False
    
    def load_config(self, config_path: str):
        """从JSON加载激光纹理配置"""
        if not os.path.exists(config_path):
            print(f"激光配置文件不存在: {config_path}")
            return False
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            base_dir = os.path.dirname(config_path)
            
            # 加载直线激光纹理配置
            for name, data in config.get('laser_textures', {}).items():
                self.textures[name] = {
                    'file': os.path.join(base_dir, data['file']),
                    'head_width': data['head_width'],
                    'body_width': data['body_width'],
                    'tail_width': data['tail_width'],
                    'row_height': data['row_height'],
                    'margin': data.get('margin', 1),
                    'colors': data.get('colors', 16),
                }
            
            # 加载曲线激光配置
            if 'bent_laser' in config:
                bent = config['bent_laser']
                self.bent_laser_data = {
                    'file': os.path.join(base_dir, bent['file']),
                    'segment_width': bent['segment_width'],
                    'row_height': bent['row_height'],
                    'colors': bent.get('colors', 16),
                }
            
            self.loaded = True
            print(f"已加载激光纹理配置: {len(self.textures)} 种直线激光")
            return True
            
        except Exception as e:
            print(f"加载激光配置失败: {e}")
            return False
    
    def get_texture_rects(self, texture_id: str, color_index: int) -> Optional[Dict]:
        """
        获取指定激光纹理和颜色的三段rect
        
        Args:
            texture_id: 纹理ID (如 'laser1')
            color_index: 颜色索引 (1-16)
            
        Returns:
            包含 head_rect, body_rect, tail_rect 的字典
        """
        if texture_id not in self.textures:
            return None
        
        tex = self.textures[texture_id]
        color_index = max(1, min(tex['colors'], int(color_index)))
        
        row = color_index - 1
        y = row * tex['row_height']
        h = tex['row_height']
        
        head_x = 0
        body_x = tex['head_width']
        tail_x = tex['head_width'] + tex['body_width']
        
        return {
            'texture_file': tex['file'],
            'head_rect': (head_x, y, tex['head_width'], h),
            'body_rect': (body_x, y, tex['body_width'], h),
            'tail_rect': (tail_x, y, tex['tail_width'], h),
            'head_width': tex['head_width'],
            'body_width': tex['body_width'],
            'tail_width': tex['tail_width'],
            'row_height': h,
            'margin': tex['margin'],
        }
    
    def get_bent_laser_rect(self, color_index: int) -> Optional[Dict]:
        """获取曲线激光纹理rect"""
        if not self.bent_laser_data:
            return None
        
        data = self.bent_laser_data
        color_index = max(1, min(data['colors'], int(color_index)))
        
        row = color_index - 1
        y = row * data['row_height']
        
        return {
            'texture_file': data['file'],
            'rect': (0, y, data['segment_width'], data['row_height']),
            'segment_width': data['segment_width'],
            'row_height': data['row_height'],
        }


# 全局实例
_laser_texture_data = LaserTextureData()


def get_laser_texture_data() -> LaserTextureData:
    """获取全局激光纹理数据实例"""
    return _laser_texture_data


# ============= 激光类 =============

class Laser:
    """
    直线激光类
    三段式（头部、身体、尾部），支持展开/持续/收缩动画
    """
    
    def __init__(self, x: float, y: float, angle: float,
                 l1: float, l2: float, l3: float,
                 width: float,
                 texture_id: str = 'laser1',
                 color_index: int = 1,
                 node: float = 0, head: float = 0):
        """
        初始化激光
        
        Args:
            x, y: 激光起点坐标
            angle: 激光角度（度）
            l1, l2, l3: 头部/身体/尾部长度
            width: 最大宽度
            texture_id: 纹理ID (如 'laser1', 'laser2')
            color_index: 颜色索引 (1-16)
            node: 起点装饰节点大小 (0表示不显示)
            head: 终点装饰节点大小 (0表示不显示)
        """
        self.x = x
        self.y = y
        self.angle = angle
        
        # 三段长度
        self.l1 = l1  # 头部
        self.l2 = l2  # 身体
        self.l3 = l3  # 尾部
        
        # 宽度
        self.max_width = width
        self.current_width = 0.0
        
        # 纹理
        self.texture_id = texture_id
        self.color_index = max(1, min(16, int(color_index)))
        
        # 装饰
        self.node = node
        self.head_node = head
        
        # 状态
        self.alpha = 0.0
        self.phase = 'off'  # off, expanding, on, shrinking, dead
        self.timer = 0
        self.counter = 0
        self.dw = 0.0
        self.da = 0.0
        
        # 属性
        self.alive = True
        self.visible = True
        self.collidable = False
        
        # 缓存的纹理rect
        self._texture_rects = None
    
    @property
    def total_length(self) -> float:
        return self.l1 + self.l2 + self.l3
    
    def turn_on(self, time: int = 30):
        """
        开启激光（渐变展开）
        
        Args:
            time: 展开帧数
        """
        time = max(1, int(time))
        self.phase = 'expanding'
        self.counter = time
        self.da = (1.0 - self.alpha) / time
        self.dw = (self.max_width - self.current_width) / time
    
    def turn_half_on(self, time: int = 30):
        """半开启（预警状态）"""
        time = max(1, int(time))
        self.counter = time
        self.da = (0.5 - self.alpha) / time
        self.dw = (0.5 * self.max_width - self.current_width) / time
    
    def turn_off(self, time: int = 30):
        """关闭激光（渐变收缩）"""
        time = max(1, int(time))
        self.phase = 'shrinking'
        self.counter = time
        self.da = -self.alpha / time
        self.dw = -self.current_width / time
        self.collidable = False
    
    def update(self):
        """每帧更新"""
        if not self.alive:
            return
        
        self.timer += 1
        
        if self.counter > 0:
            self.counter -= 1
            self.current_width += self.dw
            self.alpha += self.da
            
            # 状态转换
            if self.counter == 0:
                if self.phase == 'expanding':
                    self.phase = 'on'
                    self.collidable = True
                    self.alpha = 1.0
                    self.current_width = self.max_width
                elif self.phase == 'shrinking':
                    self.phase = 'dead'
                    self.alive = False
                    self.visible = False
        
        # 限制值范围
        self.alpha = max(0.0, min(1.0, self.alpha))
        self.current_width = max(0.0, self.current_width)
    
    def check_collision(self, px: float, py: float, radius: float) -> bool:
        """检查碰撞"""
        if not self.collidable or not self.alive or self.alpha < 0.999:
            return False
        
        angle_rad = math.radians(self.angle)
        return _check_laser_collision_jit(
            px, py, radius,
            self.x, self.y, angle_rad,
            self.l1, self.l2, self.l3,
            self.current_width
        )
    
    def get_texture_rects(self) -> Optional[Dict]:
        """获取纹理rect数据（带缓存）"""
        if self._texture_rects is None:
            self._texture_rects = get_laser_texture_data().get_texture_rects(
                self.texture_id, self.color_index
            )
        return self._texture_rects
    
    def get_render_data(self) -> Optional[Dict]:
        """获取渲染数据"""
        if not self.visible or self.current_width <= 0:
            return None
        
        tex_rects = self.get_texture_rects()
        
        return {
            'x': self.x,
            'y': self.y,
            'angle': self.angle,
            'l1': self.l1,
            'l2': self.l2,
            'l3': self.l3,
            'width': self.current_width,
            'alpha': self.alpha,
            'color_index': self.color_index,
            'texture_id': self.texture_id,
            'texture_rects': tex_rects,
            'node': self.node,
            'head_node': self.head_node,
            'timer': self.timer,
        }
    
    def kill(self):
        """销毁激光"""
        if self.alive:
            self.turn_off(30)
    
    def change_image(self, texture_id: str, color_index: int = None):
        """更换纹理"""
        self.texture_id = texture_id
        if color_index is not None:
            self.color_index = max(1, min(16, int(color_index)))
        self._texture_rects = None  # 清除缓存


class BentLaser:
    """
    曲线激光类
    沿路径弯曲，支持跟随目标
    """
    
    def __init__(self, x: float, y: float,
                 length: int, width: float,
                 color_index: int = 1,
                 sample_rate: int = 4):
        """
        初始化曲线激光
        
        Args:
            x, y: 起点坐标
            length: 路径长度（采样点数）
            width: 宽度
            color_index: 颜色索引
            sample_rate: 采样率
        """
        self.length = max(2, int(length))
        self.max_width = width
        self.current_width = 0.0
        self.color_index = max(1, min(16, int(color_index)))
        self.sample_rate = max(1, sample_rate)
        
        # 路径数据 (循环缓冲区)
        self.path_x = np.zeros(self.length, dtype=np.float64)
        self.path_y = np.zeros(self.length, dtype=np.float64)
        self.path_x.fill(x)
        self.path_y.fill(y)
        self.path_index = 0
        self.path_count = 1
        
        # 头部位置
        self.head_x = x
        self.head_y = y
        
        # 状态
        self.alpha = 0.0
        self.timer = 0
        self.counter = 0
        self.dw = 0.0
        self.da = 0.0
        
        self.alive = True
        self.visible = True
        self.collidable = False
        
        self._bent_rect = None
    
    def update_head(self, x: float, y: float):
        """更新头部位置并记录路径"""
        self.head_x = x
        self.head_y = y
        
        if self.timer % self.sample_rate == 0:
            self.path_index = (self.path_index + 1) % self.length
            self.path_x[self.path_index] = x
            self.path_y[self.path_index] = y
            self.path_count = min(self.path_count + 1, self.length)
    
    def turn_on(self, time: int = 30):
        """开启"""
        time = max(1, int(time))
        self.counter = time
        self.da = (1.0 - self.alpha) / time
        self.dw = (self.max_width - self.current_width) / time
    
    def turn_off(self, time: int = 30):
        """关闭"""
        time = max(1, int(time))
        self.counter = time
        self.da = -self.alpha / time
        self.dw = -self.current_width / time
        self.collidable = False
    
    def update(self):
        """每帧更新"""
        if not self.alive:
            return
        
        self.timer += 1
        
        if self.counter > 0:
            self.counter -= 1
            self.current_width += self.dw
            self.alpha += self.da
            
            if self.counter == 0:
                if self.alpha >= 0.99:
                    self.collidable = True
                elif self.alpha <= 0.01:
                    self.alive = False
                    self.visible = False
        
        self.alpha = max(0.0, min(1.0, self.alpha))
        self.current_width = max(0.0, self.current_width)
    
    def check_collision(self, px: float, py: float, radius: float) -> bool:
        """检查碰撞"""
        if not self.collidable or not self.alive:
            return False
        
        if self.path_count < 2:
            return False
        
        # 构建有效路径数组
        valid_count = min(self.path_count, self.length)
        path_x = np.zeros(valid_count, dtype=np.float64)
        path_y = np.zeros(valid_count, dtype=np.float64)
        
        for i in range(valid_count):
            idx = (self.path_index - valid_count + 1 + i + self.length) % self.length
            path_x[i] = self.path_x[idx]
            path_y[i] = self.path_y[idx]
        
        return _check_bent_laser_collision_jit(
            px, py, radius,
            path_x, path_y,
            self.current_width, valid_count
        )
    
    def get_render_data(self) -> Optional[Dict]:
        """获取渲染数据"""
        if not self.visible or self.current_width <= 0 or self.path_count < 2:
            return None
        
        if self._bent_rect is None:
            self._bent_rect = get_laser_texture_data().get_bent_laser_rect(self.color_index)
        
        valid_count = min(self.path_count, self.length)
        path_x = []
        path_y = []
        
        for i in range(valid_count):
            idx = (self.path_index - valid_count + 1 + i + self.length) % self.length
            path_x.append(self.path_x[idx])
            path_y.append(self.path_y[idx])
        
        return {
            'path_x': path_x,
            'path_y': path_y,
            'width': self.current_width,
            'alpha': self.alpha,
            'color_index': self.color_index,
            'texture_rect': self._bent_rect,
        }
    
    def kill(self):
        """销毁"""
        if self.alive:
            self.turn_off(30)


# ============= 激光池管理 =============

class LaserPool:
    """激光对象池"""
    
    def __init__(self, max_lasers: int = 100, max_bent: int = 50):
        self.max_lasers = max_lasers
        self.max_bent = max_bent
        
        self.lasers: List[Laser] = []
        self.bent_lasers: List[BentLaser] = []
    
    def create_laser(self, x: float, y: float, angle: float,
                     l1: float, l2: float, l3: float,
                     width: float,
                     texture_id: str = 'laser1',
                     color_index: int = 1,
                     on_time: int = 30,
                     **kwargs) -> Optional[Laser]:
        """创建直线激光"""
        if len(self.lasers) >= self.max_lasers:
            # 清理死亡的激光
            self.lasers = [l for l in self.lasers if l.alive]
            if len(self.lasers) >= self.max_lasers:
                return None
        
        laser = Laser(x, y, angle, l1, l2, l3, width, texture_id, color_index, **kwargs)
        laser.turn_on(on_time)
        self.lasers.append(laser)
        return laser
    
    def create_bent_laser(self, x: float, y: float,
                          length: int, width: float,
                          color_index: int = 1,
                          on_time: int = 30,
                          **kwargs) -> Optional[BentLaser]:
        """创建曲线激光"""
        if len(self.bent_lasers) >= self.max_bent:
            self.bent_lasers = [l for l in self.bent_lasers if l.alive]
            if len(self.bent_lasers) >= self.max_bent:
                return None
        
        laser = BentLaser(x, y, length, width, color_index, **kwargs)
        laser.turn_on(on_time)
        self.bent_lasers.append(laser)
        return laser
    
    def update(self):
        """更新所有激光"""
        for laser in self.lasers:
            laser.update()
        for laser in self.bent_lasers:
            laser.update()
        
        # 清理死亡的激光
        self.lasers = [l for l in self.lasers if l.alive]
        self.bent_lasers = [l for l in self.bent_lasers if l.alive]
    
    def check_collision(self, px: float, py: float, radius: float) -> bool:
        """检查是否与任何激光碰撞"""
        for laser in self.lasers:
            if laser.check_collision(px, py, radius):
                return True
        for laser in self.bent_lasers:
            if laser.check_collision(px, py, radius):
                return True
        return False
    
    def get_all_lasers(self) -> Tuple[List[Laser], List[BentLaser]]:
        """获取所有活跃的激光"""
        return self.lasers, self.bent_lasers
    
    def clear(self):
        """清空所有激光"""
        self.lasers.clear()
        self.bent_lasers.clear()
    
    @property
    def laser_count(self) -> int:
        return len(self.lasers)
    
    @property
    def bent_laser_count(self) -> int:
        return len(self.bent_lasers)
