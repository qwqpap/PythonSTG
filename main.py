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
from src.game.player import Player, check_collisions, load_player
from src.game.stage import StageManager
from src.game.boss import BossManager
from src.game.laser import LaserPool, get_laser_texture_data
from src.game.item import ItemPool, ItemConfig
from src.game.audio import GameAudioBank, AudioManager
from src.resource.sprite import SpriteManager
from src.core import (
    GameConfig, get_config, init_config,
    CollisionManager, get_collision_manager
)
from src.resource.texture_asset import (
    TextureAssetManager, 
    get_texture_asset_manager, 
    init_texture_asset_manager
)
from src.render.item_renderer import ItemRenderer
from src.ui import HUD, UIRenderer
from src.ui.dialog_gl_renderer import DialogGLRenderer
from src.ui.loading_renderer import LoadingScreenRenderer
from src.ui.main_menu_renderer import MainMenuRenderer
from src.ui.hud import load_hud_layout
from src.ui.bitmap_font import get_font_manager
from game_content.stages.stage1.stage_script import Stage1


def initialize_pygame_and_context():
    """初始化Pygame和ModernGL上下文"""
    pygame.init()
    
    # 初始化全局配置
    config = init_config()
    
    # 从配置获取尺寸参数
    base_size = (config.base_width, config.base_height)
    screen_size = (config.window_width, config.window_height)
    game_viewport = config.game_viewport
    
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


def initialize_game_objects(audio_manager=None, background_renderer=None):
    """初始化游戏对象（玩家、子弹池、关卡管理器等）"""
    player = load_player("orin")
    print(f"已加载玩家: {player.name}")
    bullet_pool = BulletPool(max_bullets=50000)
    laser_pool = LaserPool(max_lasers=100)
    item_pool = ItemPool(max_items=1000)
    boss_manager = BossManager()
    stage_manager = StageManager()
    
    # 设置管理器
    stage_manager.set_boss_manager(boss_manager)

    # 绑定引擎对象（一次性）
    stage_manager.bind_engine(
        bullet_pool=bullet_pool,
        player=player,
        audio_manager=audio_manager,
        item_pool=item_pool,
    )

    # 加载关卡
    stage_manager.load_stage(Stage1)

    return player, bullet_pool, laser_pool, item_pool, stage_manager


def run_main_menu(ctx, screen_size) -> bool:
    """
    显示主菜单，处理用户输入。
    Returns:
        True: 用户选择开始游戏
        False: 用户选择退出
    """
    main_menu_renderer = MainMenuRenderer(ctx, screen_size[0], screen_size[1])
    selected_index = 0
    clock = pygame.time.Clock()

    while True:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                main_menu_renderer.cleanup()
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected_index = (selected_index - 1) % 2
                elif event.key == pygame.K_DOWN:
                    selected_index = (selected_index + 1) % 2
                elif event.key == pygame.K_z:
                    main_menu_renderer.cleanup()
                    return selected_index == 0  # 0=开始游戏, 1=退出
                elif event.key == pygame.K_ESCAPE:
                    main_menu_renderer.cleanup()
                    return False

        ctx.viewport = (0, 0, screen_size[0], screen_size[1])
        ctx.clear(0.0, 0.0, 0.0)
        main_menu_renderer.render(selected_index)
        pygame.display.flip()


def main():
    """游戏主函数"""
    # 初始化Pygame和OpenGL
    screen, ctx, base_size, screen_size, game_viewport = initialize_pygame_and_context()

    # 主菜单：选择开始游戏或退出
    if not run_main_menu(ctx, screen_size):
        pygame.quit()
        sys.exit(0)
    
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

    # 初始化对话渲染器（ModernGL）
    dialog_gl_renderer = DialogGLRenderer(ctx, screen_size[0], screen_size[1], game_viewport)

    # 初始化加载画面渲染器
    loading_renderer = LoadingScreenRenderer(ctx, screen_size[0], screen_size[1])

    # 初始化物品渲染器
    item_renderer = ItemRenderer(ctx, base_size)
    item_renderer.load_texture("assets/images/item/item.png")
    
    # 初始化背景渲染器（可选）
    background_renderer = None
    try:
        from src.game.background_render import BackgroundRenderer
        
        background_renderer = BackgroundRenderer(ctx, base_size)
        
        # 使用数据驱动背景（推荐，可通过编辑器调整参数）
        # 可选: 'lake', 'temple', 'bamboo', 'gensokyosora'
        # 配置文件在 assets/images/background/*.json
        background_renderer.load_background('lake')
        
        renderer.set_background_renderer(background_renderer)
        print("背景系统初始化成功")
    except Exception as e:
        print(f"背景系统初始化失败（可选功能）: {e}")
        import traceback
        traceback.print_exc()
    
    # 初始化音频系统
    game_audio = GameAudioBank()
    game_audio.load_defaults()
    audio_manager = AudioManager(game_audio)
    
    # 初始化游戏对象
    player, bullet_pool, laser_pool, item_pool, stage_manager = initialize_game_objects(
        audio_manager=audio_manager,
        background_renderer=background_renderer
    )
    
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

        # ===== 加载画面模式 =====
        if stage_manager.loading_info:
            # 先渲染加载画面（flip 后画面立即可见），再推进协程（可能阻塞 I/O）
            ctx.viewport = (0, 0, screen_size[0], screen_size[1])
            ctx.clear(0.0, 0.0, 0.0)
            loading_renderer.render(stage_manager.loading_info)
            hud.state.fps = int(clock.get_fps())
            pygame.display.flip()

            stage_manager.update(dt, bullet_pool, player)
            continue

        # ===== 正常游戏模式 =====
        # 检查是否有活跃的对话（对话期间暂停游戏逻辑）
        dialog_active = False
        if stage_manager.current_stage:
            dialog_state = stage_manager.current_stage.get_dialog_renderer()
            if dialog_state and hasattr(dialog_state, 'is_active') and dialog_state.is_active():
                dialog_active = True

        # 更新游戏逻辑（对话期间跳过）
        if not dialog_active:
            player.update(dt, keys)
            bullet_pool.update(dt)
            laser_pool.update()  # 更新激光
            item_pool.update(player.pos[0], player.pos[1], dt)  # 更新物品

        # 关卡协程始终更新（包括对话协程）
        stage_manager.update(dt, bullet_pool, player)

        # 协程可能刚进入加载阶段（第一次 step 设置了 loading_info）
        if stage_manager.loading_info:
            ctx.viewport = (0, 0, screen_size[0], screen_size[1])
            ctx.clear(0.0, 0.0, 0.0)
            loading_renderer.render(stage_manager.loading_info)
            hud.state.fps = int(clock.get_fps())
            pygame.display.flip()
            continue
        
        # 同步物品统计到玩家和HUD
        player.score = item_pool.stats.score
        player.power = item_pool.stats.get_power_float()
        player.lives = item_pool.stats.lives

        # 获取碰撞管理器
        collision_mgr = get_collision_manager()

        # 碰撞检测（对话期间跳过）
        if not dialog_active:
            # 碰撞检测 - 玩家 vs 敌弹
            hit_x, hit_y = player.get_hit_position()
            if player.invincible_timer <= 0:
                bullet_result = collision_mgr.check_player_vs_bullets(
                    hit_x, hit_y, player.hit_radius, bullet_pool
                )
                if bullet_result.occurred:
                    if player.take_damage():
                        print(f"Player hit by bullet! Lives left: {player.lives}")
                        bullet_pool.data['alive'][bullet_result.index] = 0

            # 碰撞检测 - 玩家 vs 激光
            if player.invincible_timer <= 0:
                laser_result = collision_mgr.check_player_vs_lasers(
                    hit_x, hit_y, player.hit_radius, laser_pool
                )
                if laser_result.occurred:
                    if player.take_damage():
                        print(f"Player hit by laser! Lives left: {player.lives}")
            
            # 碰撞检测 - 玩家子弹 vs 敌人/Boss（使用 Numba 加速）
            collision_targets = []
            if stage_manager.current_context:
                collision_targets.extend(stage_manager.current_context.get_enemy_scripts())
            if stage_manager.current_stage and stage_manager.current_stage._current_boss:
                boss = stage_manager.current_stage._current_boss
                if boss._active:
                    collision_targets.append(boss)
            
            if collision_targets:
                hits, active_targets = collision_mgr.check_player_bullets_vs_targets(
                    player.bullet_pool,
                    collision_targets,
                    hit_radius=0.02,
                )
                for hit in hits:
                    if 0 <= hit.target_idx < len(active_targets):
                        target = active_targets[hit.target_idx]
                        target.damage(int(hit.damage))
                        if player.script and hasattr(player.script, 'on_bullet_hit_enemy'):
                            player.script.on_bullet_hit_enemy(
                                hit.bullet_idx, target, hit.damage)
        
        # 更新 HUD 状态
        hud.update_from_player(player)
        hud.state.graze = item_pool.stats.graze
        hud.state.bombs = item_pool.stats.bombs
        hud.state.point_value = item_pool.stats.point_rate
        active_boss = stage_manager.get_active_boss()
        if active_boss:
            hud.update_from_boss(active_boss)
        
        # 渲染游戏场景（按正确的图层顺序，包含道具渲染和背景）
        # 获取敌人脚本列表（如果有）
        enemy_scripts = None
        if hasattr(stage_manager, 'current_context') and stage_manager.current_context:
            enemy_scripts = stage_manager.current_context.get_enemy_scripts()

        renderer.render_frame(
            bullet_pool, player, stage_manager, laser_pool,
            viewport_rect=game_viewport,
            item_renderer=item_renderer,
            item_pool=item_pool,
            dt=dt,
            enemy_scripts=enemy_scripts
        )
        
        # 道具在 renderer.render_frame 中通过 item_pool SoA 数据直接渲染
        
        # 将视口恢复为全窗口，渲染HUD
        ctx.viewport = (0, 0, screen_size[0], screen_size[1])
        ui_renderer.render_hud(hud)

        # 渲染对话（如果有，使用 ModernGL）
        if stage_manager.current_stage:
            dialog_state = stage_manager.current_stage.get_dialog_renderer()
            if dialog_state:
                dialog_gl_renderer.render(dialog_state)

        # 更新FPS用于屏幕显示
        hud.state.fps = int(clock.get_fps())
        
        # 更新屏幕
        pygame.display.flip()
    
    # 清理资源
    audio_manager.cleanup()
    renderer.cleanup()
    item_renderer.cleanup()
    ui_renderer.cleanup()
    dialog_gl_renderer.cleanup()
    loading_renderer.cleanup()
    if background_renderer:
        background_renderer.cleanup()
    texture_asset_manager.clear_all()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
