#!/usr/bin/env python3
"""
Boss系统测试脚本
"""
import pygame
import sys
import numpy as np
from entity import Entity
from boss import Boss, BossPhase
from stage import StageManager
from bullet import BulletPool

# 初始化Pygame
pygame.init()

# 游戏基础尺寸（从boli.py复制）
BASE_WIDTH = 384
BASE_HEIGHT = 448

# 设置屏幕尺寸
SCREEN_WIDTH = BASE_WIDTH
SCREEN_HEIGHT = BASE_HEIGHT
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Boss System Test")

# 创建颜色常量
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

# 坐标转换函数：归一化坐标转像素坐标（与boli.py一致）
def normalized_to_pixel(norm_x, norm_y):
    """
    将归一化坐标转换为像素坐标
    :param norm_x: 归一化X坐标（-1到1）
    :param norm_y: 归一化Y坐标（-1到1）
    :return: 像素坐标元组（0到BASE_WIDTH, 0到BASE_HEIGHT）
    """
    pixel_x = (norm_x + 1) / 2 * BASE_WIDTH
    pixel_y = (norm_y + 1) / 2 * BASE_HEIGHT
    return pixel_x, pixel_y

# 简单的渲染器类
class SimpleRenderer:
    def __init__(self, screen):
        self.screen = screen
    
    def draw_circle(self, pos, radius, color):
        # 将游戏坐标转换为屏幕坐标
        screen_pos = normalized_to_pixel(pos[0], pos[1])
        screen_radius = int(radius * min(BASE_WIDTH, BASE_HEIGHT) / 2)
        pygame.draw.circle(
            self.screen,
            (int(color[0]*255), int(color[1]*255), int(color[2]*255)),
            (int(screen_pos[0]), int(screen_pos[1])),
            screen_radius
        )

# 简单的引擎类
class SimpleEngine:
    def __init__(self):
        self.bullet_pool = BulletPool(max_bullets=10000)

# 示例Boss阶段1
class TestBossPhase1(BossPhase):
    def __init__(self, boss):
        super().__init__(boss, 1)  # 正确传递phase_id
    
    def _pattern(self):
        boss = self.boss
        bullet_pool = yield
        
        # 简单的圆形扩散弹幕
        for i in range(5):
            angle_step = 2 * np.pi / 18
            for j in range(18):
                angle = j * angle_step
                bullet_pool.spawn_bullet(
                    boss.pos[0], boss.pos[1],
                    angle, 0.01,
                    color=(1.0, 0.0, 0.0),
                    sprite_id='bullet1'
                )
            # 等待60帧
            for _ in range(60):
                yield

# 示例Boss
class TestBoss(Boss):
    def __init__(self):
        super().__init__(np.array([0.0, 0.5], dtype='f4'))
        self.hp = 500.0
        self.max_hp = 500.0
        self.hit_radius = 0.08
        
        # 添加阶段
        self.add_phase(0, TestBossPhase1(self))
    
    def draw(self, renderer):
        if not self.is_alive():
            return
        
        # 绘制Boss
        renderer.draw_circle(self.pos, self.hit_radius, (1.0, 0.0, 0.0))
        
        # 绘制Boss的HP条
        hp_percent = self.get_hp_percentage()
        hp_bar_width = 0.5
        hp_bar_height = 0.02
        hp_bar_pos = np.array([self.pos[0] - hp_bar_width/2, self.pos[1] - 0.15], dtype='f4')
        
        # 绘制背景
        bg_pos_pixel = normalized_to_pixel(hp_bar_pos[0], hp_bar_pos[1])
        bg_color = (0.5, 0.5, 0.5)
        bg_rect = pygame.Rect(
            int(bg_pos_pixel[0]),
            int(bg_pos_pixel[1]),
            int(hp_bar_width * BASE_WIDTH),
            int(hp_bar_height * BASE_HEIGHT)
        )
        pygame.draw.rect(screen, bg_color, bg_rect)
        
        # 绘制HP
        hp_color = (0.0, 1.0, 0.0) if hp_percent > 0.5 else (1.0, 1.0, 0.0) if hp_percent > 0.25 else (1.0, 0.0, 0.0)
        hp_rect = pygame.Rect(
            int(bg_pos_pixel[0]),
            int(bg_pos_pixel[1]),
            int(hp_bar_width * BASE_WIDTH * hp_percent),
            int(hp_bar_height * BASE_HEIGHT)
        )
        pygame.draw.rect(screen, hp_color, hp_rect)

# 主游戏循环
def main():
    # 创建引擎和渲染器
    engine = SimpleEngine()
    renderer = SimpleRenderer(screen)
    
    # 创建StageManager
    stage_manager = StageManager(engine)
    
    # 创建Boss
    boss = TestBoss()
    stage_manager.set_boss(boss)
    
    # 创建玩家子弹池
    player_bullets = BulletPool(max_bullets=1000)
    stage_manager.set_player_bullets(player_bullets)
    
    # 让Boss登场
    boss.spawn()
    
    # 创建时钟
    clock = pygame.time.Clock()
    fps = 60
    
    # 主循环
    running = True
    while running:
        # 处理事件
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    # 空格键：向Boss发射子弹
                    for i in range(5):
                        player_bullets.spawn_bullet(
                            0.0, -0.8,  # 玩家位置（屏幕底部中央）
                            np.pi/2, 0.02,  # 向上发射
                            color=(0.0, 0.0, 1.0),
                            sprite_id='player_bullet'
                        )
        
        # 清空屏幕
        screen.fill(BLACK)
        
        # 更新游戏状态
        stage_manager.update()
        engine.bullet_pool.update(1/fps)
        player_bullets.update(1/fps)
        
        # 绘制
        # 绘制Boss
        stage_manager.draw(renderer)
        
        # 绘制子弹
        active_bullets = engine.bullet_pool.get_active_bullets()
        if len(active_bullets[0]) > 0:
            for pos, color, angle, sprite_id in zip(*active_bullets):
                renderer.draw_circle(pos, 0.01, color)
        
        # 绘制玩家子弹
        player_active_bullets = player_bullets.get_active_bullets()
        if len(player_active_bullets[0]) > 0:
            for pos, color, angle, sprite_id in zip(*player_active_bullets):
                renderer.draw_circle(pos, 0.01, color)
        
        # 绘制FPS
        fps_text = f"FPS: {int(clock.get_fps())}"
        font = pygame.font.Font(None, 36)
        text_surface = font.render(fps_text, True, WHITE)
        screen.blit(text_surface, (10, 10))
        
        # 绘制Boss信息
        boss_info = f"Boss HP: {int(boss.hp)}/{int(boss.max_hp)} | Phase: {boss.phase}"
        boss_text_surface = font.render(boss_info, True, WHITE)
        screen.blit(boss_text_surface, (10, 50))
        
        # 更新显示
        pygame.display.flip()
        
        # 控制帧率
        clock.tick(fps)
    
    # 退出游戏
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
