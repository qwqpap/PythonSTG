import numpy as np
from numba import njit
import math

# 不要往里面写动态方法：加速度，角加速度，跟踪等
# 动态方法可以在弹幕描述脚本里面实现
# 或者新的modifier_bullet.py文件里面实现

class SpawnRequest:
    """生成请求"""
    def __init__(self, x, y, angle, speed, sprite_id='', init=None, delay=0):
        self.x = x
        self.y = y
        self.angle = angle
        self.speed = speed
        self.sprite_id = sprite_id
        self.init = init  # 初始化回调
        self.delay = delay  # 延迟帧数

class DeathEvent:
    """死亡事件"""
    def __init__(self, idx, x, y, handler=None):
        self.idx = idx
        self.x = x
        self.y = y
        self.handler = handler  # 死亡处理回调

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
            ('alive', 'i4'),       # 活跃状态 (0: 非活跃, 1: 活跃)
            ('sprite_id', 'U32')   # 精灵ID
        ])
        
        # 初始化子弹池
        self.data = np.zeros(max_bullets, dtype=self.dtype)
        
        # 生成队列和死亡队列
        self.spawn_queue = []  # 生成请求队列
        self.death_queue = []  # 死亡事件队列
        
        # 上一帧的活跃状态，用于检测死亡
        self.last_alive = np.zeros(max_bullets, dtype='i4')
    
    def spawn_bullet(self, x, y, angle, speed, sprite_id='', init=None, delay=0):
        """
        生成子弹（从池子里找空位）
        :param x: 初始x坐标
        :param y: 初始y坐标
        :param angle: 角度（弧度）
        :param speed: 速度大小
        :param sprite_id: 精灵ID，用于指定使用的精灵资源
        :param init: 初始化回调
        :param delay: 延迟帧数
        :return: 子弹索引，如果没有空位则返回-1
        """
        # 如果有延迟，添加到生成队列
        if delay > 0:
            self.spawn_queue.append(SpawnRequest(x, y, angle, speed, sprite_id, init, delay))
            return -1
        
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
            
            # 激活子弹
            self.data['alive'][idx] = 1
            
            # 执行初始化回调
            if init:
                init(self, idx)
            
            return idx
        return -1
    
    def spawn_pattern(self, x, y, angle, speed, count=18, angle_spread=math.pi*2, sprite_id=''):
        """
        生成一个圆形扩散的子弹图案
        :param x: 中心x坐标
        :param y: 中心y坐标
        :param angle: 基础角度（弧度）
        :param speed: 速度大小
        :param count: 子弹数量
        :param angle_spread: 角度扩散范围（弧度）
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

        # 标记为活跃
        self.data['alive'][use_indices] = 1
    
    def kill_bullet(self, idx, handler=None):
        """
        杀死子弹
        :param idx: 子弹索引
        :param handler: 死亡处理回调
        """
        if 0 <= idx < self.max_bullets and self.data['alive'][idx]:
            # 标记为非活跃
            self.data['alive'][idx] = 0
            
            # 添加到死亡队列
            x, y = self.data['pos'][idx]
            self.death_queue.append(DeathEvent(idx, x, y, handler))
    
    def update(self, dt):
        """
        更新所有活跃子弹
        :param dt: 时间步长
        """
        # 保存当前活跃状态
        self.last_alive[:] = self.data['alive']
        
        # 调用Numba加速的更新函数
        _update_bullets(self.data, dt)
        
        # 收集死亡事件
        self._collect_deaths()
        
        # 处理死亡队列
        self._process_death_queue()
        
        # 处理生成队列
        self._process_spawn_queue()
    
    def _collect_deaths(self):
        """
        收集死亡事件
        """
        # 找出刚死亡的子弹
        died_indices = np.where((self.last_alive == 1) & (self.data['alive'] == 0))[0]
        
        for idx in died_indices:
            x, y = self.data['pos'][idx]
            self.death_queue.append(DeathEvent(idx, x, y))
    
    def _process_death_queue(self):
        """
        处理死亡队列
        """
        for event in self.death_queue:
            if event.handler:
                event.handler(self, event)
        
        # 清空死亡队列
        self.death_queue.clear()
    
    def _process_spawn_queue(self):
        """
        处理生成队列
        """
        # 处理延迟为0的生成请求
        new_queue = []
        for req in self.spawn_queue:
            if req.delay <= 0:
                # 直接生成子弹
                self._spawn_from_request(req)
            else:
                # 减少延迟
                req.delay -= 1
                new_queue.append(req)
        
        # 更新生成队列
        self.spawn_queue = new_queue
    
    def _spawn_from_request(self, req):
        """
        从生成请求生成子弹
        :param req: 生成请求
        """
        # 找到第一个非活跃的子弹
        dead_indices = np.where(self.data['alive'] == 0)[0]
        if len(dead_indices) > 0:
            idx = dead_indices[0]
            
            # 设置位置
            self.data['pos'][idx] = (req.x, req.y)
            
            # 计算速度向量
            vx = math.cos(req.angle) * req.speed
            vy = math.sin(req.angle) * req.speed
            self.data['vel'][idx] = (vx, vy)
            
            # 设置其他属性
            self.data['angle'][idx] = req.angle
            self.data['speed'][idx] = req.speed
            self.data['sprite_id'][idx] = req.sprite_id
            
            # 激活子弹
            self.data['alive'][idx] = 1
            
            # 执行初始化回调
            if req.init:
                req.init(self, idx)
    
    def get_active_bullets(self):
        """
        获取所有活跃的子弹数据
        :return: 活跃子弹的位置、角度和精灵ID数据
        """
        active_mask = self.data['alive'] == 1
        active_data = self.data[active_mask]
        
        if len(active_data) > 0:
            positions = active_data['pos']
            angles = active_data['angle']
            sprite_ids = active_data['sprite_id']
            return positions, angles, sprite_ids
        return np.array([]), np.array([]), np.array([])

    def clear_all(self):
        """
        清空所有子弹（设置为非活跃）
        """
        self.data['alive'] = 0
        self.spawn_queue.clear()
        self.death_queue.clear()
    
    def pre_update(self, dt):
        """以后加上子弹的其他处理"""
        pass

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

                