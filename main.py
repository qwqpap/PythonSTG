"""
弹幕游戏主入口 - 负责初始化和游戏主循环
"""
import sys
import os
import json
import moderngl

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.window import GameWindow, FrameClock, EVENT_QUIT, EVENT_KEYDOWN
from src.core.input_manager import KeyboardState, KEY_UP, KEY_DOWN, KEY_z, KEY_ESCAPE
from src.core.audio_backend import init_audio_backend
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
from src.ui.pause_menu_renderer import PauseMenuRenderer
from src.ui.main_menu_layout import load_layout as load_main_menu_layout
from src.ui.hud import load_hud_layout
from src.ui.bitmap_font import get_font_manager
from game_content.stages.stage1.stage_script import Stage1


def initialize_window_and_context():
    """初始化GLFW窗口和ModernGL上下文"""
    init_audio_backend()
    
    config = init_config()
    
    base_size = (config.base_width, config.base_height)
    screen_size = (config.window_width, config.window_height)
    game_viewport = config.game_viewport
    
    window = GameWindow(screen_size[0], screen_size[1], "弹幕游戏")
    
    ctx = moderngl.create_context()
    
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    
    return window, ctx, base_size, screen_size, game_viewport


def load_resources(ctx, texture_asset_manager: TextureAssetManager):
    """
    加载游戏资源（使用新的统一纹理资产管理系统）
    
    Args:
        ctx: ModernGL上下文
        texture_asset_manager: 纹理资产管理器
    
    Returns:
        tuple: (textures, sprite_uv_map)
    """
    sprite_config_folder = "assets/images"
    if not texture_asset_manager.load_sprite_config_folder(sprite_config_folder):
        print("Failed to load sprite configurations!")
        sys.exit()
    
    all_sprite_ids = texture_asset_manager.get_all_sprite_ids()
    default_sprite_id = 'star_small1' if 'star_small1' in all_sprite_ids else next(iter(all_sprite_ids), None)
    
    textures = texture_asset_manager.create_all_gl_textures(ctx, flip_y=True)
    
    sprite_uv_map = texture_asset_manager.compute_all_sprite_uvs(flip_y=True)
    
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
    
    stage_manager.set_boss_manager(boss_manager)

    stage_manager.bind_engine(
        bullet_pool=bullet_pool,
        player=player,
        audio_manager=audio_manager,
        item_pool=item_pool,
    )

    stage_manager.load_stage(Stage1)

    return player, bullet_pool, laser_pool, item_pool, stage_manager


def run_main_menu(window, ctx, screen_size) -> bool:
    """
    显示主菜单，处理用户输入。
    Returns:
        True: 用户选择开始游戏
        False: 用户选择退出
    """
    main_menu_renderer = MainMenuRenderer(ctx, screen_size[0], screen_size[1])
    main_menu_layout = load_main_menu_layout("assets/ui/main_menu_layout.json")
    num_options = max(1, len(main_menu_layout.get("options", [])))
    selected_index = 0
    clock = FrameClock()

    while True:
        dt = clock.tick(60)

        for event in window.poll_events():
            if event['type'] == EVENT_QUIT:
                main_menu_renderer.cleanup()
                return False
            if event['type'] == EVENT_KEYDOWN:
                if event['key'] == KEY_UP:
                    selected_index = (selected_index - 1) % num_options
                elif event['key'] == KEY_DOWN:
                    selected_index = (selected_index + 1) % num_options
                elif event['key'] == KEY_z:
                    main_menu_renderer.cleanup()
                    return selected_index == 0
                elif event['key'] == KEY_ESCAPE:
                    main_menu_renderer.cleanup()
                    return False

        ctx.viewport = (0, 0, screen_size[0], screen_size[1])
        ctx.clear(0.0, 0.0, 0.0)
        main_menu_renderer.render(selected_index, layout=main_menu_layout)
        window.swap_buffers()


def main():
    """游戏主函数"""
    window, ctx, base_size, screen_size, game_viewport = initialize_window_and_context()

    while True:
        if not run_main_menu(window, ctx, screen_size):
            window.destroy()
            sys.exit(0)
        
        while True:
            texture_asset_manager = init_texture_asset_manager(asset_root="assets")
        
            laser_tex_data = get_laser_texture_data()
            laser_tex_data.load_config("assets/images/laser/laser_config.json")
            
            sprite_manager = SpriteManager()
            
            textures, sprite_uv_map = load_resources(ctx, texture_asset_manager)
            
            sprite_manager._sync_from_asset_manager()
            
            renderer = Renderer(ctx, base_size, sprite_manager, textures, sprite_uv_map)
            
            font_manager = get_font_manager()
            font_manager.load_font('score', 'assets/images/ui/font/score.fnt')
            
            hud_layout_cfg = load_hud_layout('assets/ui/hud_layout.json')
            panel_cfg = hud_layout_cfg.get('panel', {}) if hud_layout_cfg else {}
            gap_to_game = panel_cfg.get('gap_to_game', 16)
            margin_right = panel_cfg.get('margin_right', 32)
            bg_color = tuple(panel_cfg.get('bg_color', [16, 16, 32]))
            bg_alpha = panel_cfg.get('bg_alpha', 0.6)
            layout_override = hud_layout_cfg.get('layout') if hud_layout_cfg else None

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

            dialog_gl_renderer = DialogGLRenderer(ctx, screen_size[0], screen_size[1], game_viewport)

            loading_renderer = LoadingScreenRenderer(ctx, screen_size[0], screen_size[1])
            pause_menu_renderer = PauseMenuRenderer(ctx, screen_size[0], screen_size[1])

            item_renderer = ItemRenderer(ctx, base_size)
            item_renderer.load_texture("assets/images/item/item.png")
            
            background_renderer = None
            try:
                from src.game.background_render import BackgroundRenderer
                
                background_renderer = BackgroundRenderer(ctx, base_size)
                
                background_renderer.load_background('lake')
                
                renderer.set_background_renderer(background_renderer)
                print("背景系统初始化成功")
            except Exception as e:
                print(f"背景系统初始化失败（可选功能）: {e}")
                import traceback
                traceback.print_exc()
            
            game_audio = GameAudioBank()
            game_audio.load_defaults()
            audio_manager = AudioManager(game_audio)
            
            player, bullet_pool, laser_pool, item_pool, stage_manager = initialize_game_objects(
                audio_manager=audio_manager,
                background_renderer=background_renderer
            )
            
            # 加载高分记录
            item_pool.stats.load_hiscore()
            
            # 连接 bomb 回调：通知 Boss 积分系统
            def _on_player_bomb():
                if stage_manager.current_stage and stage_manager.current_stage._current_boss:
                    boss = stage_manager.current_stage._current_boss
                    if boss._active:
                        boss.on_player_bomb()
            player.on_bomb_callback = _on_player_bomb
            
            clock = FrameClock()
            running = True
            
            paused = False
            pause_menu_index = 0
            game_result_state = None

            while running:
                dt = clock.tick(60)
                
                for event in window.poll_events():
                    if event['type'] == EVENT_QUIT:
                        running = False
                    elif event['type'] == EVENT_KEYDOWN:
                        if event['key'] == KEY_ESCAPE:
                            paused = not paused
                            if paused:
                                audio_manager.pause_bgm()
                                pause_menu_index = 0
                            else:
                                audio_manager.unpause_bgm()
                        
                        if paused:
                            if event['key'] == KEY_UP:
                                pause_menu_index = (pause_menu_index - 1) % 3
                            elif event['key'] == KEY_DOWN:
                                pause_menu_index = (pause_menu_index + 1) % 3
                            elif event['key'] == KEY_z:
                                if pause_menu_index == 0:
                                    # 继续游戏
                                    paused = False
                                    audio_manager.unpause_bgm()
                                elif pause_menu_index == 1:
                                    # 重新开始
                                    game_result_state = "RESTART"
                                    running = False
                                elif pause_menu_index == 2:
                                    # 返回主菜单
                                    game_result_state = "MAIN_MENU"
                                    running = False
                
                keys = KeyboardState(window.get_key_states())

                # ===== 加载画面模式 =====
                if stage_manager.loading_info:
                    ctx.viewport = (0, 0, screen_size[0], screen_size[1])
                    ctx.clear(0.0, 0.0, 0.0)
                    loading_renderer.render(stage_manager.loading_info)
                    hud.state.fps = int(clock.get_fps())
                    window.swap_buffers()

                    if not paused:
                        stage_manager.update(dt, bullet_pool, player)
                    continue

                # ===== 正常游戏模式 =====
                dialog_active = False
                if stage_manager.current_stage:
                    dialog_state = stage_manager.current_stage.get_dialog_renderer()
                    if dialog_state and hasattr(dialog_state, 'is_active') and dialog_state.is_active():
                        dialog_active = True

                if not paused:
                    if not dialog_active:
                        player.update(dt, keys)
                        bullet_pool.update(dt)
                        laser_pool.update()
                        item_pool.update(player.pos[0], player.pos[1], dt)

                    stage_manager.update(dt, bullet_pool, player)

                if stage_manager.loading_info:
                    ctx.viewport = (0, 0, screen_size[0], screen_size[1])
                    ctx.clear(0.0, 0.0, 0.0)
                    loading_renderer.render(stage_manager.loading_info)
                    hud.state.fps = int(clock.get_fps())
                    window.swap_buffers()
                    continue
                
                player.score = item_pool.stats.score
                player.power = item_pool.stats.get_power_float()
                player.lives = item_pool.stats.lives

                collision_mgr = get_collision_manager()

                if not paused and not dialog_active:
                    hit_x, hit_y = player.get_hit_position()
                    if player.invincible_timer <= 0:
                        bullet_result = collision_mgr.check_player_vs_bullets(
                            hit_x, hit_y, player.hit_radius, bullet_pool
                        )
                        if bullet_result.occurred:
                            if player.take_damage():
                                print(f"Player hit by bullet! Lives left: {player.lives}")
                                bullet_pool.data['alive'][bullet_result.index] = 0
                                # Notify boss scoring system
                                _ab = stage_manager.current_stage._current_boss if stage_manager.current_stage else None
                                if _ab and _ab._active:
                                    _ab.on_player_miss()

                    if player.invincible_timer <= 0:
                        laser_result = collision_mgr.check_player_vs_lasers(
                            hit_x, hit_y, player.hit_radius, laser_pool
                        )
                        if laser_result.occurred:
                            if player.take_damage():
                                print(f"Player hit by laser! Lives left: {player.lives}")
                                # Notify boss scoring system
                                _ab = stage_manager.current_stage._current_boss if stage_manager.current_stage else None
                                if _ab and _ab._active:
                                    _ab.on_player_miss()
                    
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
                                # +10 per bullet hit (matches LuaSTG)
                                item_pool.stats.score += 10
                                if player.script and hasattr(player.script, 'on_bullet_hit_enemy'):
                                    player.script.on_bullet_hit_enemy(
                                        hit.bullet_idx, target, hit.damage)

                    # === Graze detection ===
                    graze_count = collision_mgr.check_player_graze(
                        hit_x, hit_y, player.graze_radius, bullet_pool
                    )
                    if graze_count > 0:
                        item_pool.stats.graze += graze_count
                        item_pool.stats.update_point_rate()
                        player.add_graze(graze_count)
                
                hud.update_from_player(player)
                hud.state.graze = item_pool.stats.graze
                hud.state.bombs = item_pool.stats.bombs
                hud.state.point_value = item_pool.stats.point_rate
                active_boss = stage_manager.get_active_boss()
                if active_boss:
                    hud.update_from_boss(active_boss)
                
                enemy_scripts = None
                if hasattr(stage_manager, 'current_context') and stage_manager.current_context:
                    enemy_scripts = stage_manager.current_context.get_enemy_scripts()

                renderer.render_frame(
                    bullet_pool, player, stage_manager, laser_pool,
                    viewport_rect=game_viewport,
                    item_renderer=item_renderer,
                    item_pool=item_pool,
                    dt=0 if paused else dt,
                    enemy_scripts=enemy_scripts
                )
                
                ctx.viewport = (0, 0, screen_size[0], screen_size[1])
                ui_renderer.render_hud(hud)

                if stage_manager.current_stage:
                    dialog_state = stage_manager.current_stage.get_dialog_renderer()
                    if dialog_state:
                        dialog_gl_renderer.render(dialog_state)

                if paused:
                    pause_menu_renderer.render(pause_menu_index)

                hud.state.fps = int(clock.get_fps())
                
                window.swap_buffers()
            
            # 保存高分记录
            item_pool.stats.save_hiscore()
            
            audio_manager.cleanup()
            renderer.cleanup()
            item_renderer.cleanup()
            ui_renderer.cleanup()
            dialog_gl_renderer.cleanup()
            loading_renderer.cleanup()
            pause_menu_renderer.cleanup()
            if background_renderer:
                background_renderer.cleanup()
            texture_asset_manager.clear_all()

            if game_result_state == "MAIN_MENU":
                break  # Break inner loop, go back to top `while True:` where `run_main_menu` is
            elif game_result_state == "RESTART":
                pass   # Just continue inner loop, re-initializing everything except Main Menu
            else:
                window.destroy()
                sys.exit()

if __name__ == "__main__":
    main()
