import sys
import os
import pygame
import numpy as np
from bullet import BulletPool
from sprite_manager import SpriteManager

def main():
    # 初始化pygame
    pygame.init()
    
    # 创建窗口
    screen_width, screen_height = 800, 600
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("Bullet Sprite System Test")
    
    # 初始化精灵管理器
    sprite_manager = SpriteManager()
    
    # 加载多个精灵配置文件
    sprite_configs = [
        r"c:\Users\m1573\Documents\Downloads\pystg\image\bullet1.json",
        r"c:\Users\m1573\Documents\Downloads\pystg\image\bullet2.json",
        r"c:\Users\m1573\Documents\Downloads\pystg\image\bullet3.json",
        r"c:\Users\m1573\Documents\Downloads\pystg\image\bullet4.json"
    ]
    
    for config_path in sprite_configs:
        if sprite_manager.load_sprite_config(config_path):
            print(f"Successfully loaded {os.path.basename(config_path)}")
        else:
            print(f"Failed to load {os.path.basename(config_path)}!")
    
    # 获取所有可用的精灵ID
    all_sprite_ids = sprite_manager.get_all_sprite_ids()
    print(f"Loaded {len(all_sprite_ids)} sprites from all configuration files.")
    
    # 创建子弹池
    bullet_pool = BulletPool(max_bullets=1000)
    
    # 生成一些使用不同精灵ID的子弹
    # 注意：子弹系统使用归一化坐标（-1到1），而不是像素坐标
    center_x, center_y = 0.0, 0.0  # 屏幕中心在归一化坐标中是(0, 0)
    num_bullets = 50
    
    # 选择一些不同的精灵ID用于测试
    test_sprite_ids = [
        'arrow_big1', 'star_big1', 'gun_bullet1', 'square1',
        'ball_mid1', 'mildew1', 'ellipse1', 'star_small1'
    ]
    
    # 加载所有需要的纹理
    textures = {}
    for sprite_id in test_sprite_ids:
        sprite_data = sprite_manager.get_sprite(sprite_id)
        if sprite_data:
            # 获取配置文件中的原始路径
            original_img_path = sprite_data['image_path']
            img_filename = os.path.basename(original_img_path)
            
            # 尝试在bullet目录下查找图片
            img_path = os.path.join("image", "bullet", img_filename)
            if img_path not in textures:
                try:
                    textures[img_path] = pygame.image.load(img_path).convert_alpha()
                    print(f"Loaded texture: {os.path.basename(img_path)}")
                    # 更新精灵数据中的图片路径
                    sprite_data['image_path'] = img_path
                except pygame.error as e:
                    print(f"Failed to load {img_path}: {e}")
                    textures[img_path] = None
    
    # 生成测试子弹
    for i in range(num_bullets):
        # 计算角度和位置（使用归一化坐标）
        angle = (i / num_bullets) * 2 * np.pi
        radius = 0.3  # 归一化坐标中的半径，0.3表示屏幕宽度的30%
        x = center_x + radius * np.cos(angle)
        y = center_y + radius * np.sin(angle)
        
        # 计算速度（使用归一化坐标）
        speed = 0.01  # 归一化坐标中的速度
        vx = speed * np.cos(angle)
        vy = speed * np.sin(angle)
        
        # 选择一个精灵ID
        sprite_id = test_sprite_ids[i % len(test_sprite_ids)]
        
        # 生成随机颜色
        color = (np.random.rand(), np.random.rand(), np.random.rand())
        
        # 创建子弹
        bullet_pool.spawn_bullet(x, y, angle, speed, color=color, sprite_id=sprite_id)
    
    print(f"Generated {num_bullets} bullets with different sprite IDs.")
    
    # 游戏循环
    running = True
    clock = pygame.time.Clock()
    frame_count = 0
    
    while running and frame_count < 1000:  # 运行约16秒（60fps）
        frame_count += 1
        
        # 处理事件
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
        
        # 更新子弹
        bullet_pool.update(1.0 / 60.0)  # 固定60fps更新
        
        # 清空屏幕
        screen.fill((0, 0, 0))
        
        # 渲染子弹
        positions, colors, angles, sprite_ids = bullet_pool.get_active_bullets()
        print(f"Frame {frame_count}: {len(positions)} active bullets")  # 调试信息
        
        for i in range(len(positions)):
            x_normalized, y_normalized = positions[i]
            sprite_id = sprite_ids[i]
            
            if sprite_id:
                sprite_data = sprite_manager.get_sprite(sprite_id)
                if sprite_data:
                    img_path = sprite_data['image_path']
                    rect = sprite_data['rect']
                    center = sprite_data['center']
                    
                    if img_path in textures and textures[img_path]:
                        # 获取纹理和精灵区域
                        texture = textures[img_path]
                        sprite_rect = pygame.Rect(rect[0], rect[1], rect[2], rect[3])
                        
                        # 将归一化坐标转换为屏幕像素坐标
                        x_screen = (x_normalized + 1) * screen_width / 2
                        y_screen = (y_normalized + 1) * screen_height / 2
                        
                        # 计算绘制位置（基于中心点）
                        draw_x = int(x_screen - center[0])
                        draw_y = int(y_screen - center[1])
                        
                        # 绘制精灵
                        screen.blit(texture, (draw_x, draw_y), sprite_rect)
        
        # 显示信息
        font = pygame.font.Font(None, 36)
        text = font.render(f"Bullets: {len(positions)}", True, (255, 255, 255))
        screen.blit(text, (10, 10))
        
        # 更新显示
        pygame.display.flip()
        
        # 控制帧率
        clock.tick(60)
    
    # 等待用户按下任意键再退出
    print("Press any key to exit...")
    pygame.event.clear()
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
                waiting = False
                running = False
    
    # 退出游戏
    pygame.quit()
    print("Test completed!")

if __name__ == "__main__":
    main()