import numpy as np

class Entity:
    def __init__(self, pos, sprite_id):
        """
        实体基类
        :param pos: 初始位置 (x, y)
        :param sprite_id: 精灵ID
        """
        self.pos = np.array(pos, dtype='f4')
        self.vel = np.array([0.0, 0.0], dtype='f4')
        self.angle = 0.0
        self.speed = 0.0
        self.sprite_id = sprite_id
        self.alive = True
        self.scale = 1.0
        self.alpha = 1.0
    
    def update(self, dt):
        """
        更新实体位置和状态
        :param dt: 时间步长
        """
        # 更新位置
        self.pos += self.vel * dt
        
        # 根据速度更新角度
        if self.speed > 0:
            self.angle = np.arctan2(self.vel[1], self.vel[0])
    
    def set_velocity(self, velocity):
        """
        设置速度向量
        :param velocity: 速度向量 (vx, vy)
        """
        self.vel = np.array(velocity, dtype='f4')
        self.speed = np.linalg.norm(self.vel)
    
    def set_speed(self, speed):
        """
        设置速度大小，保持当前方向
        :param speed: 速度大小
        """
        if self.speed > 0:
            self.vel = (self.vel / self.speed) * speed
        self.speed = speed
    
    def set_angle(self, angle):
        """
        设置角度并更新速度方向
        :param angle: 角度（弧度）
        """
        self.angle = angle
        self.vel = np.array([
            self.speed * np.cos(angle),
            self.speed * np.sin(angle)
        ], dtype='f4')
    
    def move(self, dx, dy):
        """
        移动实体
        :param dx: x方向移动距离
        :param dy: y方向移动距离
        """
        self.pos += np.array([dx, dy], dtype='f4')
    
    def get_bounding_box(self):
        """
        获取实体的边界框
        :return: 边界框 (x_min, y_min, x_max, y_max)
        """
        # 默认实现，子类可以重写
        return (
            self.pos[0] - 0.1,
            self.pos[1] - 0.1,
            self.pos[0] + 0.1,
            self.pos[1] + 0.1
        )
    
    def is_colliding(self, other):
        """
        检查与其他实体是否碰撞
        :param other: 其他实体
        :return: 是否碰撞
        """
        # 默认使用边界框碰撞检测，子类可以重写
        a_min, a_max = self.get_bounding_box()[:2], self.get_bounding_box()[2:]
        b_min, b_max = other.get_bounding_box()[:2], other.get_bounding_box()[2:]
        
        return (
            a_min[0] < b_max[0] and
            a_max[0] > b_min[0] and
            a_min[1] < b_max[1] and
            a_max[1] > b_min[1]
        )