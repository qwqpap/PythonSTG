import numpy as np
from numba import njit

class Player:
    def __init__(self):
        """
        初始化玩家对象
        """
        self.pos = np.array([0.0, -0.8], dtype='f4')  # 初始位置在屏幕下方
        self.hit_radius = 0.01  # 极其微小的判定点（灵梦啊嗯）
        self.speed_high = 0.02   # 普通速度
        self.speed_low = 0.008   # Shift 低速模式
        
        # 资源属性
        self.power = 1.00
        self.score = 0
        self.lives = 3
        
        # 状态机
        self.is_focused = False  # 是否按住 Shift
        self.invincible_timer = 0 # 无敌时间
        self.state = "IDLE"      # 用于后期切换动画逻辑
    
    def update(self, dt, keys):
        """
        更新玩家状态
        :param dt: 时间步长
        :param keys: 键盘状态
        """
        # 处理无敌时间
        if self.invincible_timer > 0:
            self.invincible_timer -= dt
            if self.invincible_timer < 0:
                self.invincible_timer = 0
        
        # 处理Shift键，切换focus状态
        self.is_focused = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        
        # 计算移动速度
        current_speed = self.speed_low if self.is_focused else self.speed_high
        
        # 处理移动输入
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.pos[1] += current_speed * dt * 60  # 乘以60使速度单位与帧率无关
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.pos[1] -= current_speed * dt * 60
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.pos[0] -= current_speed * dt * 60
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.pos[0] += current_speed * dt * 60
        
        # 限制玩家在屏幕范围内
        # 考虑渲染时的宽高比校正（384/448），调整Y轴边界
        aspect_ratio = 384.0 / 448.0
        self.pos[0] = np.clip(self.pos[0], -1.0, 1.0)
        self.pos[1] = np.clip(self.pos[1], -1.0 / aspect_ratio, 1.0 / aspect_ratio)
    
    def get_speed(self):
        """
        获取当前移动速度
        :return: 当前速度值
        """
        return self.speed_low if self.is_focused else self.speed_high
    
    def take_damage(self):
        """
        玩家受到伤害
        :return: 是否真的受到伤害（考虑无敌时间）
        """
        if self.invincible_timer <= 0:
            self.lives -= 1
            self.invincible_timer = 3.0  # 3秒无敌时间
            return True
        return False

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

# 导入pygame，避免循环导入
import pygame