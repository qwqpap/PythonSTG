"""
弹幕游戏主入口 - 负责初始化和游戏主循环
"""
import sys
import os
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
from src.resource.sprite import SpriteManager
from src.resource.asset_manager import AssetManager
from src.ui import HUD, UIRenderer
from src.ui.bitmap_font import get_font_manager
from levels.boli import level_1
from levels.laser_test import laser_test_level


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


def load_resources(ctx, sprite_manager):
    """
    加载游戏资源（精灵配置和纹理）
    带有改进的错误处理和纹理加载优化
    
    Returns:
        tuple: (textures, sprite_uv_map)
    """
    # 加载精灵配置文件夹
    sprite_config_folder = "assets/images"
    if not sprite_manager.load_sprite_config_folder(sprite_config_folder):
        print("Failed to load sprite configurations!")
        pygame.quit()
        sys.exit()
    
    # 设置默认精灵ID
    default_sprite_id = 'star_small1' if 'star_small1' in sprite_manager.get_all_sprite_ids() else next(iter(sprite_manager.get_all_sprite_ids()), None)
    
    # 加载纹理图片
    textures = {}
    texture_uv_map = {}
    failed_textures = []
    
    # 为每个纹理创建纹理对象（带错误处理）
    for texture_path in sprite_manager.get_all_texture_paths():
        try:
            if not os.path.exists(texture_path):
                print(f"Warning: Texture file not found: {texture_path}")
                failed_textures.append(texture_path)
                continue
                
            img = pygame.image.load(texture_path).convert_alpha()
            texture = ctx.texture(img.get_size(), 4, pygame.image.tobytes(img, "RGBA", True))
            texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
            textures[texture_path] = texture
            print(f"Loaded texture: {texture_path}")
            
            # 为当前纹理预计算所有精灵的UV坐标
            img_width, img_height = img.get_size()
            texture_uv_map[texture_path] = {}
            
            for sprite_id in sprite_manager.get_all_sprite_ids():
                if sprite_manager.get_sprite_texture_path(sprite_id) == texture_path:
                    sprite_data = sprite_manager.get_sprite(sprite_id)
                    sprite_rect = sprite_data['rect']
                    uv_left = sprite_rect[0] / img_width
                    uv_top = (img_height - (sprite_rect[1] + sprite_rect[3])) / img_height
                    uv_right = (sprite_rect[0] + sprite_rect[2]) / img_width
                    uv_bottom = (img_height - sprite_rect[1]) / img_height
                    texture_uv_map[texture_path][sprite_id] = [uv_left, uv_top, uv_right, uv_bottom]
        except Exception as e:
            print(f"Error loading texture {texture_path}: {e}")
            failed_textures.append(texture_path)
    
    # 如果没有加载到纹理，使用默认图片
    if not textures:
        print("No textures loaded, trying default fallback...")
        bullet_texture_path = "assets/images/bullet/bullet1.png"
        try:
            if os.path.exists(bullet_texture_path):
                img = pygame.image.load(bullet_texture_path).convert_alpha()
                texture = ctx.texture(img.get_size(), 4, pygame.image.tobytes(img, "RGBA", True))
                texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
                textures[bullet_texture_path] = texture
                print(f"Loaded fallback texture: {bullet_texture_path}")
                
                img_width, img_height = img.get_size()
                texture_uv_map[bullet_texture_path] = {}
                if default_sprite_id:
                    sprite_data = sprite_manager.get_sprite(default_sprite_id)
                    sprite_rect = sprite_data['rect']
                    uv_left = sprite_rect[0] / img_width
                    uv_top = (img_height - (sprite_rect[1] + sprite_rect[3])) / img_height
                    uv_right = (sprite_rect[0] + sprite_rect[2]) / img_width
                    uv_bottom = (img_height - sprite_rect[1]) / img_height
                    texture_uv_map[bullet_texture_path][default_sprite_id] = [uv_left, uv_top, uv_right, uv_bottom]
            else:
                print(f"Warning: Default texture also not found: {bullet_texture_path}")
        except Exception as e:
            print(f"Error loading fallback texture: {e}")
    
    # 创建综合UV映射
    sprite_uv_map = {}
    for texture_path, uv_map in texture_uv_map.items():
        for sprite_id, uv_coords in uv_map.items():
            sprite_uv_map[sprite_id] = uv_coords
    
    if failed_textures:
        print(f"Failed to load {len(failed_textures)} texture(s)")
    
    print(f"Loaded {len(textures)} texture(s) successfully")
    return textures, sprite_uv_map


def initialize_game_objects():
    """初始化游戏对象（玩家、子弹池、关卡管理器等）"""
    player = Player()
    bullet_pool = BulletPool(max_bullets=50000)
    laser_pool = LaserPool(max_lasers=100)
    boss_manager = BossManager()
    enemy_manager = EnemyManager()
    stage_manager = StageManager()
    
    # 设置管理器
    stage_manager.set_boss_manager(boss_manager)
    stage_manager.set_enemy_manager(enemy_manager)
    
    # 加载第一关（可选择：level_1 或 laser_test_level）
    # stage_manager.add_coroutine(lambda: level_1(stage_manager, bullet_pool, player))
    stage_manager.add_coroutine(lambda: laser_test_level(stage_manager, bullet_pool, player, laser_pool))
    
    return player, bullet_pool, laser_pool, stage_manager


def main():
    """游戏主函数"""
    # 初始化Pygame和OpenGL
    screen, ctx, base_size, screen_size, game_viewport = initialize_pygame_and_context()
    
    # 初始化资产管理器
    asset_manager = AssetManager(asset_root="assets")
    
    # 加载激光纹理配置
    laser_tex_data = get_laser_texture_data()
    laser_tex_data.load_config("assets/images/laser/laser_config.json")
    
    # 初始化精灵管理器
    sprite_manager = SpriteManager()
    
    # 加载资源
    textures, sprite_uv_map = load_resources(ctx, sprite_manager)
    
    # 初始化渲染器
    renderer = Renderer(ctx, base_size, sprite_manager, textures, sprite_uv_map)
    
    # 初始化 UI 系统
    font_manager = get_font_manager()
    font_manager.load_font('score', 'assets/images/ui/font/score.fnt')
    
    # UI 面板位置（在游戏视口右侧留16px间距，再加32px右边距）
    panel_origin_x = game_viewport[0] + game_viewport[2] + 16
    panel_origin_y = game_viewport[1]
    panel_width = screen_size[0] - panel_origin_x - 32
    panel_height = game_viewport[3]
    hud = HUD(screen_width=screen_size[0], screen_height=screen_size[1],
              panel_origin=(panel_origin_x, panel_origin_y),
              panel_size=(panel_width, panel_height),
              game_origin=(game_viewport[0], game_viewport[1]),
              game_size=(game_viewport[2], game_viewport[3]))
    ui_renderer = UIRenderer(ctx, screen_width=screen_size[0], screen_height=screen_size[1])
    
    # 初始化游戏对象
    player, bullet_pool, laser_pool, stage_manager = initialize_game_objects()
    
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
        active_boss = stage_manager.get_active_boss()
        if active_boss:
            hud.update_from_boss(active_boss)
        
        # 渲染游戏场景（限定到左侧游戏视口）
        renderer.render_frame(bullet_pool, player, stage_manager, laser_pool, viewport_rect=game_viewport)
        
        # 将视口恢复为全窗口，渲染HUD
        ctx.viewport = (0, 0, screen_size[0], screen_size[1])
        ui_renderer.render_hud(hud)
        
        # 每10帧打印调试信息
        current_fps = int(clock.get_fps())
        if pygame.time.get_ticks() % 100 < 16:
            positions, _, _, _ = bullet_pool.get_active_bullets()
            active_count = len(positions)
            laser_count = laser_pool.laser_count
            bent_laser_count = laser_pool.bent_laser_count
            print(f"FPS: {current_fps}, Bullets: {active_count}, Lasers: {laser_count}, Bent Lasers: {bent_laser_count}, "
                  f"Lives: {player.lives}, Focus: {player.is_focused}, "
                  f"Position: ({player.pos[0]:.2f}, {player.pos[1]:.2f}), Frame: {stage_manager.get_frame_count()}")
        
        # 更新屏幕
        pygame.display.flip()
    
    # 清理资源
    renderer.cleanup()
    ui_renderer.cleanup()
    asset_manager.clear_all()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
