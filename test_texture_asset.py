"""
纹理资产管理系统测试
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame
from src.resource.texture_asset import (
    TextureAssetManager, 
    Sprite, 
    AnimatedSprite,
    init_texture_asset_manager,
    get_texture_asset_manager
)


def test_basic_loading():
    """测试基本加载功能"""
    print("\n=== 测试基本加载 ===")
    
    # 初始化pygame
    pygame.init()
    pygame.display.set_mode((800, 600))
    
    # 创建管理器
    manager = TextureAssetManager("assets")
    
    # 加载旧格式配置（兼容性测试）
    atlas = manager.load_legacy_config("images/item/item.json")
    if atlas:
        print(f"✓ 成功加载旧格式配置: {atlas.name}")
        print(f"  精灵数量: {len(atlas.sprites)}")
        for name, sprite in atlas.sprites.items():
            print(f"    - {name}: rect={sprite.rect}, center={sprite.center}")
    else:
        print("✗ 加载旧格式配置失败")
    
    # 测试精灵获取
    sprite = manager.get_sprite("item_power")
    if sprite:
        print(f"✓ 获取精灵成功: {sprite.name}")
        print(f"  UV坐标: {manager.get_sprite_uv('item_power')}")
    
    # 测试Surface获取
    surface = manager.get_sprite_surface("item_power")
    if surface:
        print(f"✓ 获取精灵Surface成功: {surface.get_size()}")
    
    # 输出统计
    stats = manager.get_stats()
    print(f"\n统计信息: {stats}")


def test_animation():
    """测试动画功能"""
    print("\n=== 测试动画功能 ===")
    
    # 创建一个测试动画
    from src.resource.texture_asset import SpriteFrame, AnimatedSprite
    
    frames = [
        SpriteFrame(rect=(0, 0, 32, 32), center=(16, 16)),
        SpriteFrame(rect=(32, 0, 32, 32), center=(16, 16)),
        SpriteFrame(rect=(64, 0, 32, 32), center=(16, 16)),
        SpriteFrame(rect=(96, 0, 32, 32), center=(16, 16)),
    ]
    
    anim = AnimatedSprite(
        name="test_anim",
        texture_path="test.png",
        frames=frames,
        frame_duration=0.1,
        loop=True
    )
    
    print(f"动画帧数: {anim.frame_count}")
    print(f"总时长: {anim.total_duration}秒")
    
    # 测试时间到帧的映射
    test_times = [0.0, 0.05, 0.1, 0.25, 0.4, 0.5]
    for t in test_times:
        frame_idx = anim.get_frame_index_at_time(t)
        print(f"  时间 {t:.2f}s -> 帧 {frame_idx}")
    
    print("✓ 动画测试完成")


def test_new_format_config():
    """测试新格式配置"""
    print("\n=== 测试新格式配置 ===")
    
    manager = TextureAssetManager("assets")
    
    # 注意: 这个测试需要实际存在对应的png文件才能完全成功
    # 这里主要测试配置解析逻辑
    atlas = manager.load_atlas_config("images/bullet/example_new_format.json")
    
    if atlas:
        print(f"✓ 成功加载新格式配置: {atlas.name}")
        print(f"  精灵: {list(atlas.sprites.keys())}")
        print(f"  动画: {list(atlas.animations.keys())}")
        
        # 检查动画解析
        for anim_name, anim in atlas.animations.items():
            print(f"\n  动画 '{anim_name}':")
            print(f"    帧数: {anim.frame_count}")
            print(f"    帧时长: {anim.frame_duration}s")
            print(f"    循环: {anim.loop}")
    else:
        print("! 配置加载失败（可能是缺少png文件，但配置解析应该正常）")


def test_global_instance():
    """测试全局实例"""
    print("\n=== 测试全局实例 ===")
    
    manager1 = init_texture_asset_manager("assets")
    manager2 = get_texture_asset_manager()
    
    if manager1 is manager2:
        print("✓ 全局实例工作正常")
    else:
        print("✗ 全局实例异常")


def visual_test():
    """可视化测试 - 显示加载的精灵"""
    print("\n=== 可视化测试 ===")
    
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("纹理资产管理系统测试")
    clock = pygame.time.Clock()
    
    manager = TextureAssetManager("assets")
    manager.load_legacy_config("images/item/item.json")
    
    # 获取所有精灵
    sprites = list(manager.sprites.keys())
    print(f"加载了 {len(sprites)} 个精灵")
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
        
        screen.fill((30, 30, 40))
        
        # 绘制所有精灵
        x, y = 50, 50
        for sprite_name in sprites:
            if sprite_name.startswith('item.'):  # 跳过带前缀的重复项
                continue
            surface = manager.get_sprite_surface(sprite_name)
            if surface:
                screen.blit(surface, (x, y))
                # 绘制名称
                font = pygame.font.SysFont(None, 16)
                text = font.render(sprite_name, True, (200, 200, 200))
                screen.blit(text, (x, y + 40))
                x += 80
                if x > 700:
                    x = 50
                    y += 80
        
        # 显示帧率
        fps_text = pygame.font.SysFont(None, 24).render(
            f"FPS: {clock.get_fps():.1f} - Press ESC to exit", 
            True, (255, 255, 255)
        )
        screen.blit(fps_text, (10, 10))
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()
    print("✓ 可视化测试完成")


if __name__ == "__main__":
    print("=" * 50)
    print("纹理资产管理系统测试")
    print("=" * 50)
    
    test_basic_loading()
    test_animation()
    test_new_format_config()
    test_global_instance()
    
    # 询问是否运行可视化测试
    try:
        response = input("\n是否运行可视化测试? (y/n): ").strip().lower()
        if response == 'y':
            visual_test()
    except EOFError:
        pass
    
    print("\n测试完成!")
