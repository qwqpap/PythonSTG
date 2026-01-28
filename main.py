"""
弹幕游戏主入口 - 负责初始化和游戏主循环
"""
import sys
import os
import json
import pygame
import moderngl

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.render import Renderer
from src.game.bullet import BulletPool
from src.game.player import Player, check_collisions
from src.game.stage import StageManager
from src.game.boss import BossManager
from src.game.enemy import EnemyManager
from src.game.laser import LaserPool, get_laser_texture_data
from src.game.item import ItemPool, ItemConfig
from src.resource.sprite import SpriteManager
from src.resource.texture_asset import (
    TextureAssetManager, 
    get_texture_asset_manager, 
    init_texture_asset_manager
)
from src.render.item_renderer import ItemRenderer
from src.ui import HUD, UIRenderer
from src.ui.hud import load_hud_layout
from src.ui.bitmap_font import get_font_manager
from levels.boli import level_1
from levels.laser_test import laser_test_level
from levels.item_test import simple_item_demo


def initialize_pygame_and_context():
    """初始化Pygame和ModernGL上下文"""
    pygame.init()
    
    # 游戏逻辑尺寸（坐标系使用）
    base_size = (384, 448)
    game_scale = 2  # 游戏区域放大倍数
    game_view_size = (base_size[0] * game_scale, base_size[1] * game_scale)
    
    # 窗口尺寸（包含右侧信息栏）
    screen_size = (1280, 960)
    # 游戏视口放在左侧，留出右侧信息面板空间
    margin_x = 32
    margin_y = (screen_size[1] - game_view_size[1]) // 2
    game_viewport = (margin_x, margin_y, game_view_size[0], game_view_size[1])
    
    screen = pygame.display.set_mode(screen_size, pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.display.set_caption("弹幕游戏")
    
    # 获取ModernGL上下文
    ctx = moderngl.create_context()
    
    # 启用alpha混合
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    
    return screen, ctx, base_size, screen_size, game_viewport


def load_resources(ctx, texture_asset_manager: TextureAssetManager):
    """
    加载游戏资源（使用新的统一纹理资产管理系统）
    
    Args:
        ctx: ModernGL上下文
        texture_asset_manager: 纹理资产管理器
    
    Returns:
        tuple: (textures, sprite_uv_map)
    """
    # 加载精灵配置文件夹
    sprite_config_folder = "assets/images"
    if not texture_asset_manager.load_sprite_config_folder(sprite_config_folder):
        print("Failed to load sprite configurations!")
        pygame.quit()
        sys.exit()
    
    # 设置默认精灵ID
    all_sprite_ids = texture_asset_manager.get_all_sprite_ids()
    default_sprite_id = 'star_small1' if 'star_small1' in all_sprite_ids else next(iter(all_sprite_ids), None)
    
    # 使用新的资产管理器创建所有GL纹理
    textures = texture_asset_manager.create_all_gl_textures(ctx, flip_y=True)
    
    # 预计算所有精灵的UV坐标
    sprite_uv_map = texture_asset_manager.compute_all_sprite_uvs(flip_y=True)
    
    # 打印加载统计
    stats = texture_asset_manager.get_stats()
    print(f"资源加载完成: {stats['atlases']} 图集, {stats['sprites']} 精灵, {stats['animations']} 动画")
    print(f"Loaded {len(textures)} texture(s) successfully")
    
    return textures, sprite_uv_map


def initialize_game_objects():
    """初始化游戏对象（玩家、子弹池、关卡管理器等）"""
    player = Player()
    bullet_pool = BulletPool(max_bullets=50000)
    laser_pool = LaserPool(max_lasers=100)
    item_pool = ItemPool(max_items=1000)
    boss_manager = BossManager()
    enemy_manager = EnemyManager()
    stage_manager = StageManager()
    
    # 设置管理器
    stage_manager.set_boss_manager(boss_manager)
    stage_manager.set_enemy_manager(enemy_manager)
    
    # 加载关卡（可选择不同关卡）
    stage_manager.add_coroutine(lambda: level_1(stage_manager, bullet_pool, player))
    # stage_manager.add_coroutine(lambda: laser_test_level(stage_manager, bullet_pool, player, laser_pool))
    # stage_manager.add_coroutine(lambda: simple_item_demo(stage_manager, bullet_pool, player, item_pool))
    
    return player, bullet_pool, laser_pool, item_pool, stage_manager


def main():
    """游戏主函数"""
    # 初始化Pygame和OpenGL
    screen, ctx, base_size, screen_size, game_viewport = initialize_pygame_and_context()
    
    # 初始化统一纹理资产管理器
    texture_asset_manager = init_texture_asset_manager(asset_root="assets")
    
    # 加载激光纹理配置
    laser_tex_data = get_laser_texture_data()
    laser_tex_data.load_config("assets/images/laser/laser_config.json")
    
    # 初始化精灵管理器（兼容层，内部使用texture_asset_manager）
    sprite_manager = SpriteManager()
    
    # 加载资源（使用新的统一资产管理系统）
    textures, sprite_uv_map = load_resources(ctx, texture_asset_manager)
    
    # 同步到精灵管理器兼容层
    sprite_manager._sync_from_asset_manager()
    
    # 初始化渲染器
    renderer = Renderer(ctx, base_size, sprite_manager, textures, sprite_uv_map)
    
    # 初始化 UI 系统
    font_manager = get_font_manager()
    font_manager.load_font('score', 'assets/images/ui/font/score.fnt')
    
    # 加载 HUD 布局配置
    hud_layout_cfg = load_hud_layout('assets/ui/hud_layout.json')
    panel_cfg = hud_layout_cfg.get('panel', {}) if hud_layout_cfg else {}
    gap_to_game = panel_cfg.get('gap_to_game', 16)
    margin_right = panel_cfg.get('margin_right', 32)
    bg_color = tuple(panel_cfg.get('bg_color', [16, 16, 32]))
    bg_alpha = panel_cfg.get('bg_alpha', 0.6)
    layout_override = hud_layout_cfg.get('layout') if hud_layout_cfg else None

    # UI 面板位置（根据配置/窗口尺寸计算）
    panel_origin_x = game_viewport[0] + game_viewport[2] + gap_to_game
    panel_origin_y = game_viewport[1]
    available_width = screen_size[0] - panel_origin_x - margin_right
    default_panel_size = [max(200, available_width), game_viewport[3]]
    panel_size_cfg = panel_cfg.get('size', default_panel_size)
    panel_width = panel_size_cfg[0]
    panel_height = panel_size_cfg[1] if len(panel_size_cfg) > 1 else default_panel_size[1]
    hud = HUD(screen_width=screen_size[0], screen_height=screen_size[1],
              panel_origin=(panel_origin_x, panel_origin_y),
              panel_size=(panel_width, panel_height),
              game_origin=(game_viewport[0], game_viewport[1]),
              game_size=(game_viewport[2], game_viewport[3]),
              bg_color=bg_color, bg_alpha=bg_alpha,
              layout_override=layout_override)
    ui_renderer = UIRenderer(ctx, screen_width=screen_size[0], screen_height=screen_size[1])
    
    # 初始化物品渲染器
    item_renderer = ItemRenderer(ctx, base_size)
    item_renderer.load_texture("assets/images/item/item.png")
    
    # 初始化游戏对象
    player, bullet_pool, laser_pool, item_pool, stage_manager = initialize_game_objects()
    
    # 游戏主循环
    clock = pygame.time.Clock()
    running = True
    
    while running:
        # 计算时间步长
        dt = clock.tick(60) / 1000.0
        
        # 事件处理
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        # 获取键盘状态
        keys = pygame.key.get_pressed()
        
        # 更新游戏逻辑
        player.update(dt, keys)
        stage_manager.update(dt, bullet_pool, player)
        bullet_pool.update(dt)
        laser_pool.update()  # 更新激光
        item_pool.update(player.pos[0], player.pos[1], dt)  # 更新物品
        
        # 同步物品统计到玩家和HUD
        player.score = item_pool.stats.score
        player.power = item_pool.stats.get_power_float()
        player.lives = item_pool.stats.lives
        
        # 碰撞检测 - 子弹
        if player.invincible_timer <= 0:
            collided_bullet = check_collisions(player.pos[0], player.pos[1], player.hit_radius, bullet_pool.data)
            if collided_bullet != -1:
                if player.take_damage():
                    print(f"Player hit by bullet! Lives left: {player.lives}")
                    bullet_pool.data['alive'][collided_bullet] = 0
        
        # 碰撞检测 - 激光
        if player.invincible_timer <= 0:
            # 检查直线激光
            lasers, bent_lasers = laser_pool.get_all_lasers()
            for laser in lasers:
                if laser.check_collision(player.pos[0], player.pos[1], player.hit_radius):
                    if player.take_damage():
                        print(f"Player hit by laser! Lives left: {player.lives}")
                        break
            
            # 检查曲线激光
            for bent_laser in bent_lasers:
                if bent_laser.check_collision(player.pos[0], player.pos[1], player.hit_radius):
                    if player.take_damage():
                        print(f"Player hit by bent laser! Lives left: {player.lives}")
                        break
        
        # 更新 HUD 状态
        hud.update_from_player(player)
        hud.state.graze = item_pool.stats.graze
        hud.state.bombs = item_pool.stats.bombs
        hud.state.point_value = item_pool.stats.point_rate
        active_boss = stage_manager.get_active_boss()
        if active_boss:
            hud.update_from_boss(active_boss)
        
        # 渲染游戏场景（限定到左侧游戏视口）
        renderer.render_frame(bullet_pool, player, stage_manager, laser_pool, viewport_rect=game_viewport)
        
        # 渲染物品（在游戏视口内）
        ctx.viewport = game_viewport
        item_renderer.render_items(item_pool.get_active_items())
        
        # 将视口恢复为全窗口，渲染HUD
        ctx.viewport = (0, 0, screen_size[0], screen_size[1])
        ui_renderer.render_hud(hud)
        
        # 更新FPS用于屏幕显示
        hud.state.fps = int(clock.get_fps())
        
        # 更新屏幕
        pygame.display.flip()
    
    # 清理资源
    renderer.cleanup()
    item_renderer.cleanup()
    ui_renderer.cleanup()
    texture_asset_manager.clear_all()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
