import numpy as np
from numba import njit
import math

class BulletPool:
    def __init__(self, max_bullets=50000):
        """
        初始化子弹池
        :param max_bullets: 最大子弹数量
        """
        self.max_bullets = max_bullets
        
        # 创建结构化数组存储子弹数据
        self.dtype = np.dtype([
            ('pos', 'f4', 2),      # 位置 (x, y)
            ('vel', 'f4', 2),      # 速度 (vx, vy)
            ('angle', 'f4'),       # 角度（弧度）
            ('speed', 'f4'),       # 速度大小
            ('color', 'f4', 3),    # 颜色 (r, g, b)
            ('alive', 'i4'),       # 活跃状态 (0: 非活跃, 1: 活跃)
            ('sprite_id', 'U32')   # 精灵ID
        ])
        
        # 初始化子弹池
        self.data = np.zeros(max_bullets, dtype=self.dtype)
        
        # 预生成随机颜色
        self.data['color'] = np.random.uniform(0.0, 1.0, (max_bullets, 3)).astype('f4')
        
    def spawn_bullet(self, x, y, angle, speed, color=None, sprite_id=''):
        """
        生成子弹（从池子里找空位）
        :param x: 初始x坐标
        :param y: 初始y坐标
        :param angle: 角度（弧度）
        :param speed: 速度大小
        :param color: 颜色 (r, g, b)，如果为None则使用预生成的随机颜色
        :param sprite_id: 精灵ID，用于指定使用的精灵资源
        :return: 子弹索引，如果没有空位则返回-1
        """
        # 找到第一个非活跃的子弹
        dead_indices = np.where(self.data['alive'] == 0)[0]
        if len(dead_indices) > 0:
            idx = dead_indices[0]
            
            # 设置位置
            self.data['pos'][idx] = (x, y)
            
            # 计算速度向量
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            self.data['vel'][idx] = (vx, vy)
            
            # 设置其他属性
            self.data['angle'][idx] = angle
            self.data['speed'][idx] = speed
            self.data['sprite_id'][idx] = sprite_id
            
            # 如果提供了颜色，则使用提供的颜色
            if color is not None:
                self.data['color'][idx] = color
            
            # 激活子弹
            self.data['alive'][idx] = 1
            
            return idx
        return -1
    
    def spawn_pattern(self, x, y, angle, speed, count=18, angle_spread=math.pi*2, color=None, sprite_id=''):
        """
        生成一个圆形扩散的子弹图案
        :param x: 中心x坐标
        :param y: 中心y坐标
        :param angle: 基础角度（弧度）
        :param speed: 速度大小
        :param count: 子弹数量
        :param angle_spread: 角度扩散范围（弧度）
        :param color: 颜色 (r, g, b)
        :param sprite_id: 精灵ID，用于指定使用的精灵资源
        """
        # 向量化生成多个子弹，避免每次调用 spawn_bullet 时进行 O(n) 的 np.where 搜索
        if count <= 0:
            return

        angle_step = angle_spread / count
        angles = np.array([angle + i * angle_step for i in range(count)], dtype='f4')

        # 计算速度向量
        vxs = np.cos(angles) * speed
        vys = np.sin(angles) * speed

        # 一次性找出可用的空位（避免在循环里反复扫描）
        free_indices = np.flatnonzero(self.data['alive'] == 0)
        if len(free_indices) == 0:
            return

        use_indices = free_indices[:min(count, len(free_indices))]
        n = len(use_indices)

        # 批量写入属性
        self.data['pos'][use_indices, 0] = x
        self.data['pos'][use_indices, 1] = y
        self.data['vel'][use_indices, 0] = vxs[:n]
        self.data['vel'][use_indices, 1] = vys[:n]
        self.data['angle'][use_indices] = angles[:n]
        self.data['speed'][use_indices] = speed
        self.data['sprite_id'][use_indices] = sprite_id

        if color is not None:
            self.data['color'][use_indices] = color

        # 标记为活跃
        self.data['alive'][use_indices] = 1
    
    def update(self, dt):
        """
        更新所有活跃子弹
        :param dt: 时间步长
        """
        # 调用Numba加速的更新函数
        _update_bullets(self.data, dt)

    def get_active_bullets(self):
        """
        获取所有活跃的子弹数据
        :return: 活跃子弹的位置、颜色、角度和精灵ID数据
        """
        active_mask = self.data['alive'] == 1
        active_data = self.data[active_mask]
        
        if len(active_data) > 0:
            positions = active_data['pos']
            colors = active_data['color']
            angles = active_data['angle']
            sprite_ids = active_data['sprite_id']
            return positions, colors, angles, sprite_ids
        return np.array([]), np.array([]), np.array([]), np.array([])

    def clear_all(self):
        """
        清空所有子弹（设置为非活跃）
        """
        self.data['alive'] = 0

@njit
def _update_bullets(data, dt):
    """
    Numba加速的子弹更新函数
    :param data: 子弹数据数组
    :param dt: 时间步长
    """
    for i in range(len(data)):
        if data[i]['alive']:
            # 更新位置
            data[i]['pos'][0] += data[i]['vel'][0] * dt
            data[i]['pos'][1] += data[i]['vel'][1] * dt
            
            # 边界检测（假设屏幕范围是-1到1，子弹离开屏幕一定距离后再消失）
            x, y = data[i]['pos']
            if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
                data[i]['alive'] = 0