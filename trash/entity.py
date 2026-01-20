import numpy as np

class Entity:
    """
    游戏实体基类
    """
    def __init__(self, pos=np.array([0.0, 0.0], dtype='f4')):
        self.pos = pos.copy()
        self.alive = True
    
    def update(self, dt):
        """
        更新实体状态
        :param dt: 时间步长
        """
        pass
    
    def draw(self, renderer):
        """
        渲染实体
        :param renderer: 渲染器
        """
        pass
    
    def is_alive(self):
        """
        检查实体是否存活
        :return: 是否存活
        """
        return self.alive
    
    def set_pos(self, pos):
        """
        设置实体位置
        :param pos: 新位置
        """
        self.pos = pos.copy()
    
    def get_pos(self):
        """
        获取实体位置
        :return: 位置
        """
        return self.pos.copy()