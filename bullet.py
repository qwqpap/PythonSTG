import numpy as np
from numba import njit
import math

# 不要往里面写动态方法：加速度，角加速度，跟踪等
# 动态方法可以在弹幕描述脚本里面实现
# 或者新的modifier_bullet.py文件里面实现

class SpawnRequest:
    """生成请求"""
    def __init__(self, x, y, angle, speed, color=None, sprite_id='', init=None, delay=0, acc=None, on_death=None, max_lifetime=0.0, modifiers=None):
        self.x = x
        self.y = y
        self.angle = angle
        self.speed = speed
        self.color = color
        self.sprite_id = sprite_id
        self.init = init  # 初始化回调
        self.delay = delay  # 延迟帧数
        self.acc = acc or (0.0, 0.0)  # 加速度 (ax, ay)
        self.on_death = on_death  # 死亡回调
        self.max_lifetime = max_lifetime  # 最大生命周期（秒）
        self.modifiers = modifiers or []  # modifier列表

class DeathEvent:
    """死亡事件"""
    def __init__(self, idx, x, y, handler=None):
        self.idx = idx
        self.x = x
        self.y = y
        self.handler = handler  # 死亡处理回调

# Modifier系统
class Modifier:
    """modifier基类，定义统一的接口"""
    def update(self, bullet_data, idx, dt):
        """
        更新子弹数据
        :param bullet_data: 子弹数据数组
        :param idx: 子弹索引
        :param dt: 时间步长
        """
        pass

class AccelerationModifier(Modifier):
    """加速度modifier，用于添加恒定加速度"""
    def __init__(self, ax, ay):
        """
        :param ax: x方向加速度
        :param ay: y方向加速度
        """
        self.ax = ax
        self.ay = ay
    
    def update(self, bullet_data, idx, dt):
        """
        应用加速度效果
        :param bullet_data: 子弹数据数组
        :param idx: 子弹索引
        :param dt: 时间步长
        """
        # 更新速度
        bullet_data[idx]['vel'][0] += self.ax * dt
        bullet_data[idx]['vel'][1] += self.ay * dt

class AngularAccelerationModifier(Modifier):
    """角加速度modifier，用于添加恒定角加速度"""
    def __init__(self, angular_acc):
        """
        :param angular_acc: 角加速度（弧度/秒²）
        """
        self.angular_acc = angular_acc
    
    def update(self, bullet_data, idx, dt):
        """
        应用角加速度效果
        :param bullet_data: 子弹数据数组
        :param idx: 子弹索引
        :param dt: 时间步长
        """
        from math import cos, sin, sqrt, atan2
        
        # 获取当前速度大小和角度
        speed = bullet_data[idx]['speed']
        angle = bullet_data[idx]['angle']
        
        # 更新角度
        new_angle = angle + self.angular_acc * dt
        
        # 重新计算速度向量
        bullet_data[idx]['vel'][0] = speed * cos(new_angle)
        bullet_data[idx]['vel'][1] = speed * sin(new_angle)
        
        # 更新角度
        bullet_data[idx]['angle'] = new_angle

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
            ('acc', 'f4', 2),      # 加速度 (ax, ay)
            ('angle', 'f4'),       # 角度（弧度）
            ('speed', 'f4'),       # 速度大小
            ('color', 'f4', 3),    # 颜色 (r, g, b)
            ('alive', 'i4'),       # 活跃状态 (0: 非活跃, 1: 活跃)
            ('sprite_id', 'U32'),   # 精灵ID
            ('lifetime', 'f4'),     # 当前生命周期
            ('max_lifetime', 'f4'),  # 最大生命周期
            ('radius', 'f4')        # 碰撞半径
        ])
        
        # 初始化子弹池
        self.data = np.zeros(max_bullets, dtype=self.dtype)
        
        # 预生成随机颜色
        self.data['color'] = np.random.uniform(0.0, 1.0, (max_bullets, 3)).astype('f4')
        
        # 生成队列和死亡队列
        self.spawn_queue = []  # 生成请求队列
        self.death_queue = []  # 死亡事件队列
        
        # 上一帧的活跃状态，用于检测死亡
        self.last_alive = np.zeros(max_bullets, dtype='i4')
        
        # 存储子弹死亡回调函数
        self.on_death_handlers = {}
        
        # 存储子弹的生命周期
        self.lifetimes = np.zeros(max_bullets, dtype='f4')
        self.max_lifetimes = np.zeros(max_bullets, dtype='f4')
        
        # Modifier系统：存储每个子弹的modifier列表
        self.bullet_modifiers = {}
        # Modifier系统：存储所有使用中的modifier，用于全局管理
        self.active_modifiers = set()
        
        # 空闲子弹索引列表，优化spawn_bullet性能
        self.free_indices = list(range(max_bullets))
    
    def spawn_bullet(self, x, y, angle, speed, color=None, sprite_id='', init=None, delay=0, acc=None, on_death=None, max_lifetime=0.0, modifiers=None):
        """
        生成子弹（从池子里找空位）
        :param x: 初始x坐标
        :param y: 初始y坐标
        :param angle: 角度（弧度）
        :param speed: 速度大小
        :param color: 颜色 (r, g, b)，如果为None则使用预生成的随机颜色
        :param sprite_id: 精灵ID，用于指定使用的精灵资源
        :param init: 初始化回调
        :param delay: 延迟帧数
        :param acc: 加速度 (ax, ay)，如果为None则使用(0, 0)
        :param on_death: 死亡回调函数
        :param max_lifetime: 最大生命周期（秒），0表示无限
        :param modifiers: modifier列表，用于添加动态效果
        :return: 子弹索引，如果没有空位则返回-1
        """
        acc = acc or (0.0, 0.0)
        modifiers = modifiers or []
        
        # 如果有延迟，添加到生成队列
        if delay > 0:
            self.spawn_queue.append(SpawnRequest(x, y, angle, speed, color, sprite_id, init, delay, acc, on_death, max_lifetime, modifiers))
            return -1
        
        # 从空闲列表中获取空闲子弹索引
        if len(self.free_indices) > 0:
            idx = self.free_indices.pop()
            
            # 设置位置
            self.data['pos'][idx] = (x, y)
            
            # 计算速度向量
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            self.data['vel'][idx] = (vx, vy)
            
            # 设置加速度
            self.data['acc'][idx] = acc
            
            # 设置其他属性
            self.data['angle'][idx] = angle
            self.data['speed'][idx] = speed
            self.data['sprite_id'][idx] = sprite_id
            
            # 如果提供了颜色，则使用提供的颜色
            if color is not None:
                self.data['color'][idx] = color
            
            # 设置生命周期
            self.data['lifetime'][idx] = 0.0
            self.data['max_lifetime'][idx] = max_lifetime
            
            # 设置碰撞半径（默认值）
            self.data['radius'][idx] = 0.01  # 默认碰撞半径
            
            # 存储死亡回调
            if on_death:
                self.on_death_handlers[idx] = on_death
            else:
                self.on_death_handlers.pop(idx, None)
            
            # 添加modifier
            for modifier in modifiers:
                self.add_modifier(idx, modifier)
            
            # 激活子弹
            self.data['alive'][idx] = 1
            
            # 执行初始化回调
            if init:
                init(self, idx)
            
            return idx
        return -1
    
    def spawn_pattern(self, x, y, angle, speed, count=18, angle_spread=math.pi*2, color=None, sprite_id='', acc=None):
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
        :param acc: 加速度 (ax, ay)，如果为None则使用(0, 0)
        """
        # 向量化生成多个子弹，避免每次调用 spawn_bullet 时进行 O(n) 的 np.where 搜索
        if count <= 0:
            return

        acc = acc or (0.0, 0.0)
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
        self.data['acc'][use_indices, 0] = acc[0]
        self.data['acc'][use_indices, 1] = acc[1]
        self.data['angle'][use_indices] = angles[:n]
        self.data['speed'][use_indices] = speed
        self.data['sprite_id'][use_indices] = sprite_id
        self.data['radius'][use_indices] = 0.01  # 默认碰撞半径
        self.data['lifetime'][use_indices] = 0.0
        self.data['max_lifetime'][use_indices] = 0.0  # 无限生命周期

        if color is not None:
            self.data['color'][use_indices] = color

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
        
        # 调用Numba加速的更新函数（基础物理更新）
        _update_bullets(self.data, dt)
        
        # 应用所有modifier效果（Python层面，支持复杂逻辑）
        # 遍历所有有modifier的子弹索引
        if self.bullet_modifiers:
            # 优化：创建副本避免字典在遍历过程中被修改
            bullet_indices = list(self.bullet_modifiers.keys())
            for idx in bullet_indices:
                # 检查子弹是否仍然活跃
                if self.data['alive'][idx]:
                    # 应用所有modifier，优化：只有速度改变时才更新speed和angle
                    modifiers = self.bullet_modifiers[idx]
                    if modifiers:
                        # 保存当前速度，用于检查是否改变
                        old_vx, old_vy = self.data['vel'][idx]
                        
                        for modifier in modifiers:
                            modifier.update(self.data, idx, dt)
                    
                        # 检查速度是否改变
                        new_vx, new_vy = self.data['vel'][idx]
                        if old_vx != new_vx or old_vy != new_vy:
                            # 速度改变了，更新speed和angle
                            self.data['speed'][idx] = np.sqrt(new_vx**2 + new_vy**2)
                            self.data['angle'][idx] = np.arctan2(new_vy, new_vx)
                else:
                    # 子弹已经死亡，清理modifier
                    # 优化：直接删除键，避免调用复杂的remove_all_modifiers
                    del self.bullet_modifiers[idx]
        
        # 收集死亡事件（修复：移除了提前return，确保死亡事件被处理）
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
            # 获取on_death回调
            handler = self.on_death_handlers.pop(idx, None)
            self.death_queue.append(DeathEvent(idx, x, y, handler))
            # 将死亡的子弹索引添加回空闲列表
            self.free_indices.append(idx)
    
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
        # 从空闲列表中获取空闲子弹索引
        if len(self.free_indices) > 0:
            idx = self.free_indices.pop()
            
            # 设置位置
            self.data['pos'][idx] = (req.x, req.y)
            
            # 计算速度向量
            vx = math.cos(req.angle) * req.speed
            vy = math.sin(req.angle) * req.speed
            self.data['vel'][idx] = (vx, vy)
            
            # 设置加速度
            self.data['acc'][idx] = req.acc
            
            # 设置其他属性
            self.data['angle'][idx] = req.angle
            self.data['speed'][idx] = req.speed
            self.data['sprite_id'][idx] = req.sprite_id
            
            # 如果提供了颜色，则使用提供的颜色
            if req.color is not None:
                self.data['color'][idx] = req.color
            
            # 设置生命周期
            self.data['lifetime'][idx] = 0.0
            self.data['max_lifetime'][idx] = req.max_lifetime
            
            # 设置碰撞半径（默认值）
            self.data['radius'][idx] = 0.01  # 默认碰撞半径
            
            # 存储死亡回调
            if req.on_death:
                self.on_death_handlers[idx] = req.on_death
            else:
                self.on_death_handlers.pop(idx, None)
            
            # 添加modifier
            for modifier in req.modifiers:
                self.add_modifier(idx, modifier)
            
            # 激活子弹
            self.data['alive'][idx] = 1
            
            # 执行初始化回调
            if req.init:
                req.init(self, idx)
    
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
        self.spawn_queue.clear()
        self.death_queue.clear()
        # 清空modifier
        self.bullet_modifiers.clear()
        self.active_modifiers.clear()
        self.on_death_handlers.clear()
    
    def add_modifier(self, idx, modifier):
        """
        为子弹添加modifier
        :param idx: 子弹索引
        :param modifier: Modifier实例
        """
        if idx not in self.bullet_modifiers:
            self.bullet_modifiers[idx] = []
        self.bullet_modifiers[idx].append(modifier)
        self.active_modifiers.add(modifier)
    
    def remove_modifier(self, idx, modifier):
        """
        从子弹移除modifier
        :param idx: 子弹索引
        :param modifier: Modifier实例
        """
        if idx in self.bullet_modifiers:
            if modifier in self.bullet_modifiers[idx]:
                self.bullet_modifiers[idx].remove(modifier)
                # 如果子弹没有modifier了，移除该索引
                if not self.bullet_modifiers[idx]:
                    del self.bullet_modifiers[idx]
            # 如果modifier不再被任何子弹使用，从活跃集合中移除
            still_used = False
            for mods in self.bullet_modifiers.values():
                if modifier in mods:
                    still_used = True
                    break
            if not still_used:
                self.active_modifiers.remove(modifier)
    
    def remove_all_modifiers(self, idx):
        """
        移除子弹的所有modifier
        :param idx: 子弹索引
        """
        if idx in self.bullet_modifiers:
            # 从活跃集合中移除不再使用的modifier
            for modifier in self.bullet_modifiers[idx]:
                still_used = False
                for other_idx, mods in self.bullet_modifiers.items():
                    if other_idx != idx and modifier in mods:
                        still_used = True
                        break
                if not still_used:
                    self.active_modifiers.remove(modifier)
            # 移除该子弹的所有modifier
            del self.bullet_modifiers[idx]
    
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
            # 更新生命周期
            data[i]['lifetime'] += dt
            
            # 检查最大生命周期
            if data[i]['max_lifetime'] > 0.0 and data[i]['lifetime'] >= data[i]['max_lifetime']:
                data[i]['alive'] = 0
                continue
            
            # 更新速度（加速度）
            data[i]['vel'][0] += data[i]['acc'][0] * dt
            data[i]['vel'][1] += data[i]['acc'][1] * dt
            
            # 更新位置
            data[i]['pos'][0] += data[i]['vel'][0] * dt
            data[i]['pos'][1] += data[i]['vel'][1] * dt
            
            # 更新速度大小
            data[i]['speed'] = np.sqrt(data[i]['vel'][0]**2 + data[i]['vel'][1]**2)
            
            # 更新角度
            data[i]['angle'] = np.arctan2(data[i]['vel'][1], data[i]['vel'][0])
            
            # 边界检测（假设屏幕范围是-1到1，子弹离开屏幕一定距离后再消失）
            x, y = data[i]['pos']
            if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
                data[i]['alive'] = 0

                