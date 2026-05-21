"""
弹幕游戏主入口 - 负责初始化和游戏主循环
"""
import sys
import os
import json
import time
import moderngl

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.window import GameWindow, FrameClock, EVENT_QUIT, EVENT_KEYDOWN
from src.core.input_manager import KeyboardState, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_z, KEY_ESCAPE, KEY_c
from src.core.audio_backend import init_audio_backend
from src.render import Renderer
from src.game.bullet import BulletPool
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.bomb import trigger_player_bomb
from src.game.player import Player, check_collisions, load_player
from src.game.stage import StageManager
from src.game.boss import BossManager
from src.game.laser import LaserPool, get_laser_texture_data
from src.game.item import ItemPool, ItemConfig
from src.game.audio import GameAudioBank, AudioManager
from src.game.userdata import (
    get_settings,
    get_progress,
    ReplayRecorder,
    ReplayPlayback,
    list_replays,
    load_replay,
)
from src.resource.sprite import SpriteManager
from src.core import (
    GameConfig, get_config, init_config,
    CollisionManager, get_collision_manager, init_sprite_registry
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
from src.ui.staff_roll_renderer import StaffRollRenderer
from src.ui.continue_menu_renderer import ContinueMenuRenderer
from src.ui.main_menu_layout import load_layout as load_main_menu_layout
from src.ui.hud import load_hud_layout
from src.ui.bitmap_font import get_font_manager
from game_content.stages.stage1.stage_script import Stage1
from game_content.stages.stage1.stage_asset_preview import Stage1AssetPreview
from game_content.stages.stage2.stage_script import Stage2
from game_content.stages.stage3.stage_script import Stage3
from game_content.stages.stage_test.stage_script import StageTest

# 所有正式关卡（按通关顺序），debug 菜单和关卡选择器用此列表
ALL_STAGES = [Stage1, Stage2, Stage3]


def _stage_class_by_id(stage_id: str):
    """根据 stage.id（或类名）查找对应的关卡类，回退 Stage1。"""
    sid = (stage_id or "").lower()
    for cls in ALL_STAGES + [StageTest]:
        if getattr(cls, "id", "").lower() == sid:
            return cls
        if cls.__name__.lower() == sid:
            return cls
    return Stage1

# ===== Debug 模式 =====
DEBUG_MODE = "--debug" in sys.argv
PROFILE_MODE = "--profile" in sys.argv
PROFILE_REPORT_FRAMES = 120


def _get_cli_option(prefix: str):
    """读取形如 --key=value 的命令行参数。"""
    for arg in sys.argv[1:]:
        if arg.startswith(prefix):
            return arg.split("=", 1)[1].strip()
    return None


def resolve_stage_class():
    """根据 --stage 参数解析要加载的关卡类。"""
    stage_arg = (_get_cli_option("--stage=") or "stage1").strip().lower()
    stage_map = {
        "stage1": Stage1,
        "stage2": Stage2,
        "stage3": Stage3,
        "asset_preview": Stage1AssetPreview,
        "preview": Stage1AssetPreview,
        "assets": Stage1AssetPreview,
    }
    stage_class = stage_map.get(stage_arg)
    if stage_class is None:
        print(f"[main] 未识别的 --stage={stage_arg}，回退到 stage1")
        return Stage1
    print(f"[main] 当前关卡: {stage_class.__name__} (--stage={stage_arg})")
    return stage_class


def _scan_wave_bookmarks(stage_class):
    """扫描 stage 包目录下 waves/ 子目录，收集 DEBUG_BOOKMARK=True 的 Wave 类。"""
    import importlib
    import pkgutil
    from src.game.stage.wave_base import Wave

    results = []
    module_name = getattr(stage_class, '__module__', '')
    # e.g. "game_content.stages.stage1.stage_script" -> "game_content.stages.stage1"
    package_name = '.'.join(module_name.split('.')[:-1])
    waves_package = f"{package_name}.waves"
    try:
        waves_mod = importlib.import_module(waves_package)
    except ImportError:
        return results

    waves_path = getattr(waves_mod, '__path__', [])
    for finder, mod_name, _ in pkgutil.iter_modules(waves_path):
        full_name = f"{waves_package}.{mod_name}"
        try:
            mod = importlib.import_module(full_name)
        except Exception:
            continue
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if (
                isinstance(obj, type)
                and issubclass(obj, Wave)
                and obj is not Wave
                and getattr(obj, 'DEBUG_BOOKMARK', False)
            ):
                results.append(obj)
    # 去重，保持发现顺序
    seen = set()
    unique = []
    for cls in results:
        if id(cls) not in seen:
            seen.add(id(cls))
            unique.append(cls)
    return unique


def build_debug_menu(stage_class):
    """从 StageScript 子类构建 Debug 跳转菜单"""
    from src.game.stage.stage_base import BossDef
    from src.game.stage.boss_base import BossPhaseType

    entries = [{"label": "从头开始", "target": None, "is_bookmark": False}]

    # ---- Bookmark 区域：Wave 类 + BossPhase ----
    bookmark_entries = []

    # Wave bookmarks
    for wave_cls in _scan_wave_bookmarks(stage_class):
        bookmark_entries.append({
            "label": f"[Bookmark] Wave: {wave_cls.__name__}",
            "target": {"type": "wave", "wave_class": wave_cls},
            "is_bookmark": True,
        })

    # Boss phase bookmarks
    for attr_name in vars(stage_class):
        if attr_name.startswith('_'):
            continue
        attr = getattr(stage_class, attr_name, None)
        if not isinstance(attr, BossDef):
            continue
        is_midboss = "mid" in attr_name.lower()
        effective_type = "midboss" if is_midboss else "boss"
        for i, phase in enumerate(attr.phases):
            sc = phase.script_class
            if sc and getattr(sc, 'DEBUG_BOOKMARK', False):
                if phase.phase_type == BossPhaseType.SPELLCARD:
                    phase_label = phase.name or f"符卡 {i}"
                else:
                    phase_label = f"通常攻撃 {i + 1}"
                bookmark_entries.append({
                    "label": f"[Bookmark] {attr.name} / {phase_label}",
                    "target": {"type": effective_type, "phase": i},
                    "is_bookmark": True,
                })

    if bookmark_entries:
        entries.append({"label": "───── Bookmarks ─────", "target": None, "is_bookmark": False, "separator": True})
        entries.extend(bookmark_entries)

    # ---- Boss 入口区域 ----
    for attr_name in vars(stage_class):
        if attr_name.startswith('_'):
            continue
        attr = getattr(stage_class, attr_name, None)
        if not isinstance(attr, BossDef):
            continue
        is_midboss = "mid" in attr_name.lower()
        effective_type = "midboss" if is_midboss else "boss"
        type_label = "道中 Boss" if is_midboss else "Boss"

        # Boss 入口（从第 0 阶段开始）
        entries.append({
            "label": f"{type_label}: {attr.name} ({attr.id})",
            "target": {"type": effective_type, "phase": 0},
            "is_bookmark": False,
        })

        # 每个阶段
        for i, phase in enumerate(attr.phases):
            if phase.phase_type == BossPhaseType.SPELLCARD:
                phase_label = phase.name or f"符卡 {i}"
            else:
                phase_label = f"通常攻撃 {i + 1}"
            entries.append({
                "label": f"  └ Phase {i}: {phase_label}",
                "target": {"type": effective_type, "phase": i},
                "is_bookmark": False,
            })

    return entries


def run_replay_select_menu(window, ctx, screen_size):
    """列出 userdata/replays/ 中的重放文件，让玩家选一个。返回 path 或 None。"""
    from src.ui.main_menu_renderer import MainMenuRenderer
    from src.core.window import FrameClock, EVENT_QUIT, EVENT_KEYDOWN
    from src.core.input_manager import KEY_UP, KEY_DOWN, KEY_z, KEY_ESCAPE

    replays = list_replays()
    if not replays:
        # 没有重放：弹一个空菜单提示
        labels = ["（暂无重放，按 ESC 返回）"]
        entries = [None]
    else:
        labels = [
            f"{r['stage']:<8} | {r['character']:<6} | {r['frame_count']:>5}帧 | {r['created_at']}"
            for r in replays
        ]
        entries = [r["path"] for r in replays]

    layout = {
        "bg_gradient": {"top": [10, 25, 25], "bottom": [20, 40, 50]},
        "title": {
            "text": "选择重放",
            "font_size": 36,
            "color": [180, 220, 255],
            "y_ratio": 0.08,
        },
        "options": [{"text": lbl} for lbl in labels],
        "option_spacing": 28,
        "option_font_size": 20,
        "option_colors": {"normal": [180, 200, 200], "selected": [255, 255, 120]},
        "hint": {
            "text": "↑↓ 选择   Z 播放   ESC 返回",
            "font_size": 18,
            "color": [140, 140, 140],
            "y_offset": -30,
        },
    }

    selected_index = 0
    renderer = MainMenuRenderer(ctx, screen_size[0], screen_size[1])
    clock = FrameClock()
    n = len(entries)

    while True:
        clock.tick(60)
        for event in window.poll_events():
            if event['type'] == EVENT_QUIT:
                renderer.cleanup()
                return None
            if event['type'] == EVENT_KEYDOWN:
                if event['key'] == KEY_UP:
                    selected_index = (selected_index - 1) % n
                elif event['key'] == KEY_DOWN:
                    selected_index = (selected_index + 1) % n
                elif event['key'] == KEY_z:
                    renderer.cleanup()
                    return entries[selected_index]
                elif event['key'] == KEY_ESCAPE:
                    renderer.cleanup()
                    return None

        ctx.viewport = window.viewport
        ctx.clear(0.0, 0.0, 0.0)
        renderer.render(selected_index, layout=layout)
        window.swap_buffers()


def run_settings_menu(window, ctx, screen_size, audio_manager):
    """
    设置菜单：分类卡片 + 滑块/开关/循环 + 实时预览。
    控制：↑↓ 选项；←→ 调节（滑块/循环）；Z 触发动作或切换；ESC 保存返回。
    """
    from src.ui.settings_menu_renderer import SettingsMenuRenderer
    from src.core.window import FrameClock, EVENT_QUIT, EVENT_KEYDOWN
    from src.core.input_manager import (
        KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_z, KEY_ESCAPE,
    )

    settings = get_settings()

    # 缓冲区：在菜单中编辑，统一 commit
    state = {
        "se_volume": settings.se_volume,
        "bgm_volume": settings.bgm_volume,
        "fullscreen": settings.fullscreen,
        "last_character": settings.last_character,
    }
    char_options = ["tao", "orin", "tenshi"]
    char_display = {"tao": "桃 (Tao)", "orin": "燐 (Orin)", "tenshi": "天子 (Tenshi)"}

    # 项目列表：每项指向 state 的某个键 + 控件类型
    # idx -> dict
    def build_items() -> list:
        return [
            {"section": "音频", "key": "se_volume",     "label": "SE 音量",  "type": "slider",
             "value": state["se_volume"]},
            {"section": "音频", "key": "bgm_volume",    "label": "BGM 音量", "type": "slider",
             "value": state["bgm_volume"]},
            {"section": "显示", "key": "fullscreen",    "label": "全屏 (重启生效)", "type": "toggle",
             "value": state["fullscreen"]},
            {"section": "游戏", "key": "last_character","label": "默认自机", "type": "cycle",
             "value": state["last_character"],
             "display": char_display.get(state["last_character"], state["last_character"]),
             "options": char_options},
            {"section": "其它", "label": "重置为默认值", "type": "action", "key": "_reset"},
            {"label": "返回（自动保存）", "type": "action", "key": "_back"},
        ]

    def apply_audio_live():
        settings.se_volume = state["se_volume"]
        settings.bgm_volume = state["bgm_volume"]
        settings.apply_audio(audio_manager)

    def commit_and_save():
        settings.se_volume = state["se_volume"]
        settings.bgm_volume = state["bgm_volume"]
        settings.fullscreen = state["fullscreen"]
        settings.last_character = state["last_character"]
        settings.apply_audio(audio_manager)
        settings.save()

    def reset_defaults():
        state["se_volume"] = 0.7
        state["bgm_volume"] = 0.6
        state["fullscreen"] = False
        state["last_character"] = "tao"
        apply_audio_live()

    selected = 0
    renderer = SettingsMenuRenderer(ctx, screen_size[0], screen_size[1])
    clock = FrameClock()

    while True:
        clock.tick(60)

        items = build_items()
        n = len(items)

        for event in window.poll_events():
            if event['type'] == EVENT_QUIT:
                commit_and_save()
                renderer.cleanup()
                return
            if event['type'] != EVENT_KEYDOWN:
                continue

            key = event['key']
            cur = items[selected]
            kind = cur["type"]
            ckey = cur.get("key")

            if key == KEY_UP:
                selected = (selected - 1) % n
            elif key == KEY_DOWN:
                selected = (selected + 1) % n
            elif key in (KEY_LEFT, KEY_RIGHT):
                delta = 1 if key == KEY_RIGHT else -1
                if kind == "slider" and ckey:
                    step = 0.05
                    state[ckey] = max(0.0, min(1.0, state[ckey] + delta * step))
                    apply_audio_live()
                elif kind == "toggle" and ckey:
                    state[ckey] = not state[ckey]
                elif kind == "cycle" and ckey:
                    options = cur.get("options", [])
                    if options:
                        try:
                            idx = options.index(state[ckey])
                        except ValueError:
                            idx = 0
                        state[ckey] = options[(idx + delta) % len(options)]
            elif key == KEY_z:
                if kind == "toggle" and ckey:
                    state[ckey] = not state[ckey]
                elif kind == "cycle" and ckey:
                    options = cur.get("options", [])
                    if options:
                        try:
                            idx = options.index(state[ckey])
                        except ValueError:
                            idx = 0
                        state[ckey] = options[(idx + 1) % len(options)]
                elif kind == "action":
                    if ckey == "_back":
                        commit_and_save()
                        renderer.cleanup()
                        return
                    elif ckey == "_reset":
                        reset_defaults()
            elif key == KEY_ESCAPE:
                commit_and_save()
                renderer.cleanup()
                return

        # 重新构建以反映 state 变化
        items = build_items()
        model = {
            "title": "设置",
            "items": items,
            "selected": selected,
            "hint": "↑↓ 选项    ←→ 调节    Z 切换/确认    ESC 保存返回",
        }

        ctx.viewport = window.viewport
        ctx.clear(0.0, 0.0, 0.0)
        renderer.render(model)
        window.swap_buffers()


def run_stage_select_menu(window, ctx, screen_size, stage_classes, current_class):
    """Debug: 在进入书签菜单之前让用户选择关卡。
    按 Z 确认选择，ESC 跳过（保持 current_class）。
    """
    from src.ui.main_menu_renderer import MainMenuRenderer
    from src.core.window import FrameClock, EVENT_QUIT, EVENT_KEYDOWN
    from src.core.input_manager import KEY_UP, KEY_DOWN, KEY_z, KEY_ESCAPE

    entries = list(stage_classes)
    labels = [f"{cls.name}  ({cls.id})" for cls in entries]
    layout = {
        "bg_gradient": {"top": [10, 10, 25], "bottom": [25, 25, 50]},
        "title": {
            "text": "Debug: 选择关卡",
            "font_size": 36,
            "color": [180, 220, 255],
            "y_ratio": 0.08,
        },
        "options": [{"text": lbl} for lbl in labels],
        "option_spacing": 36,
        "option_font_size": 26,
        "option_colors": {"normal": [160, 160, 200], "selected": [255, 255, 120]},
        "hint": {
            "text": "↑↓ 选择关卡   Z 确认   ESC 跳过",
            "font_size": 18,
            "color": [140, 140, 140],
            "y_offset": -30,
        },
    }

    # 默认选中当前关卡
    try:
        selected_index = entries.index(current_class)
    except ValueError:
        selected_index = 0

    renderer = MainMenuRenderer(ctx, screen_size[0], screen_size[1])
    clock = FrameClock()

    while True:
        clock.tick(60)
        for event in window.poll_events():
            if event['type'] == EVENT_QUIT:
                renderer.cleanup()
                return current_class
            if event['type'] == EVENT_KEYDOWN:
                if event['key'] == KEY_UP:
                    selected_index = (selected_index - 1) % len(entries)
                elif event['key'] == KEY_DOWN:
                    selected_index = (selected_index + 1) % len(entries)
                elif event['key'] == KEY_z:
                    renderer.cleanup()
                    return entries[selected_index]
                elif event['key'] == KEY_ESCAPE:
                    renderer.cleanup()
                    return current_class

        ctx.viewport = window.viewport
        ctx.clear(0.0, 0.0, 0.0)
        renderer.render(selected_index, layout=layout)
        window.swap_buffers()


def run_debug_menu(window, ctx, screen_size, stage_class):
    """在 GUI 中显示 Debug 跳转菜单，处理用户输入并返回选择的 target 或 None"""
    from src.ui.main_menu_renderer import MainMenuRenderer
    from src.core.window import FrameClock, EVENT_QUIT, EVENT_KEYDOWN
    from src.core.input_manager import KEY_UP, KEY_DOWN, KEY_z, KEY_ESCAPE, KEY_b

    stage_name = getattr(stage_class, 'name', stage_class.__name__)
    entries = build_debug_menu(stage_class)
    
    # 构建适合 Debug 菜单的布局
    # 为了容纳更多选项，缩小字体，减小间距，并将整体上移
    layout = {
        "bg_gradient": {"top": [20, 10, 10], "bottom": [40, 20, 20]}, # 偏红背景区别于主菜单
        "title": {
            "text": f"Debug: {stage_name}",
            "font_size": 36,
            "color": [255, 200, 200],
            "y_ratio": 0.05
        },
        "options": [{"text": entry["label"]} for entry in entries],
        "option_spacing": 26,             # 间距更紧凑
        "option_font_size": 22,           # 字体更小
        "option_colors": {"normal": [180, 180, 180], "selected": [255, 255, 100]},
        "hint": {
            "text": "↑↓ 选择  Z 确认  ESC 从头  [B] 书签",
            "font_size": 18,
            "color": [150, 150, 150],
            "y_offset": -30
        }
    }

    renderer = MainMenuRenderer(ctx, screen_size[0], screen_size[1])
    num_options = len(entries)
    selected_index = 0
    clock = FrameClock()

    while True:
        clock.tick(60)

        for event in window.poll_events():
            if event['type'] == EVENT_QUIT:
                renderer.cleanup()
                return None
            if event['type'] == EVENT_KEYDOWN:
                if event['key'] == KEY_UP:
                    selected_index = (selected_index - 1) % num_options
                elif event['key'] == KEY_DOWN:
                    selected_index = (selected_index + 1) % num_options
                elif event['key'] == KEY_z:
                    renderer.cleanup()
                    return entries[selected_index]["target"]
                elif event['key'] == KEY_ESCAPE:
                    renderer.cleanup()
                    return None # 默认不跳过
                elif event['key'] == KEY_b:
                    # 清除当前选中的 Bookmark 标记（仅对书签项生效）
                    if entries[selected_index].get("is_bookmark") and entries[selected_index].get("target"):
                        sc_class = None
                        # 找到对应的 script_class 以清除标记
                        for attr_name in vars(stage_class):
                            if attr_name.startswith('_'):
                                continue
                            attr = getattr(stage_class, attr_name, None)
                            from src.game.stage.stage_base import BossDef
                            if not isinstance(attr, BossDef):
                                continue
                            for phase in attr.phases:
                                if getattr(phase.script_class, 'DEBUG_BOOKMARK', False):
                                    phase.script_class.DEBUG_BOOKMARK = False
                        # 重建菜单
                        entries = build_debug_menu(stage_class)
                        layout["options"] = [{"text": e["label"]} for e in entries]
                        num_options = len(entries)
                        selected_index = min(selected_index, num_options - 1)

        ctx.viewport = window.viewport
        ctx.clear(0.0, 0.0, 0.0)
        renderer.render(selected_index, layout=layout)
        window.swap_buffers()


def initialize_window_and_context():
    """初始化GLFW窗口和ModernGL上下文"""
    init_audio_backend()

    config = init_config()

    base_size = (config.base_width, config.base_height)
    screen_size = (config.window_width, config.window_height)
    game_viewport = config.game_viewport

    # 读取持久化的 fullscreen 偏好（设置菜单里的 "全屏 (重启生效)"）
    settings = get_settings()
    fullscreen = bool(settings.fullscreen)

    window = GameWindow(
        screen_size[0], screen_size[1],
        "东方做题狙特别版",
        fullscreen=fullscreen,
    )
    if fullscreen:
        print(f"[main] Fullscreen ON: framebuffer={window.framebuffer_size}, "
              f"viewport={window.viewport}")

    ctx = moderngl.create_context()

    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    # game_viewport 是 logical 坐标 (UI/对话/emoji 的着色器需要)。
    # 但 renderer.render_frame 通过 ctx.viewport 设置 GL viewport，
    # 必须用 framebuffer 像素坐标，否则全屏时游戏只渲染到左下角小块。
    fb_w, fb_h = window.framebuffer_size
    scale_x = fb_w / screen_size[0]
    scale_y = fb_h / screen_size[1]
    game_viewport_fb = (
        int(round(game_viewport[0] * scale_x)),
        int(round(game_viewport[1] * scale_y)),
        int(round(game_viewport[2] * scale_x)),
        int(round(game_viewport[3] * scale_y)),
    )

    return window, ctx, base_size, screen_size, game_viewport, game_viewport_fb


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


def initialize_sprite_registry_from_assets(sprite_manager: SpriteManager, textures: dict):
    """
    用当前已加载资产重建 SpriteRegistry，确保 OptimizedBulletPool 的 sprite_idx/UV/纹理映射正确。
    """
    texture_sizes = {}
    for path, tex in textures.items():
        texture_sizes[path] = tex.size
        texture_sizes[path.replace('\\', '/')] = tex.size
        texture_sizes[path.lower()] = tex.size
        texture_sizes[path.replace('\\', '/').lower()] = tex.size

    registry = init_sprite_registry(max_sprites=8192)
    registry.register_from_sprite_manager(sprite_manager, texture_sizes)
    print(f"SpriteRegistry 已重建: {registry.count} sprites")


def initialize_game_objects(stage_class, audio_manager=None, background_renderer=None,
                            character: str = "tao"):
    """初始化游戏对象（玩家、子弹池、关卡管理器等）"""
    try:
        player = load_player(character)
    except Exception:
        print(f"[main] 加载玩家 '{character}' 失败，回退 tao")
        player = load_player("tao")
    print(f"已加载玩家: {player.name}")
    # 使用优化版子弹池（整数 sprite 索引 + 向量化渲染数据准备）
    bullet_pool = OptimizedBulletPool(max_bullets=50000)
    laser_pool = LaserPool(max_lasers=100)
    item_pool = ItemPool(max_items=1000)
    boss_manager = BossManager()
    stage_manager = StageManager()
    
    stage_manager.set_boss_manager(boss_manager)

    stage_manager.bind_engine(
        bullet_pool=bullet_pool,
        laser_pool=laser_pool,
        player=player,
        audio_manager=audio_manager,
        item_pool=item_pool,
        background_renderer=background_renderer,
    )

    stage_manager.load_stage(stage_class)

    return player, bullet_pool, laser_pool, item_pool, stage_manager


def run_main_menu(window, ctx, screen_size, audio_manager) -> int:
    """
    显示主菜单，处理用户输入。
    Returns:
        选中的菜单项索引（Z 确认）；-1 表示退出（ESC 或关窗口）。
        约定：选项顺序由 main_menu_layout.json 决定：
          0 = 开始游戏
          1 = 测试关卡
          2 = 退出
    """
    main_menu_renderer = MainMenuRenderer(ctx, screen_size[0], screen_size[1])
    main_menu_layout = load_main_menu_layout("assets/ui/main_menu_layout.json")
    options = main_menu_layout.get("options", [])
    num_options = max(1, len(options))
    # 找到"退出"选项的索引，用于 Z 确认时判断
    quit_index = next(
        (i for i, o in enumerate(options)
         if (o.get("text", "") if isinstance(o, dict) else str(o)) in ("退出", "Quit", "Exit")),
        num_options - 1,
    )
    selected_index = 0
    clock = FrameClock()

    audio_manager.play_bgm("00", announce=False)

    while True:
        dt = clock.tick(60)

        for event in window.poll_events():
            if event['type'] == EVENT_QUIT:
                audio_manager.stop_bgm(fade_ms=300)
                main_menu_renderer.cleanup()
                return -1
            if event['type'] == EVENT_KEYDOWN:
                if event['key'] == KEY_UP:
                    selected_index = (selected_index - 1) % num_options
                elif event['key'] == KEY_DOWN:
                    selected_index = (selected_index + 1) % num_options
                elif event['key'] == KEY_z:
                    audio_manager.stop_bgm(fade_ms=300)
                    main_menu_renderer.cleanup()
                    if selected_index == quit_index:
                        return -1
                    return selected_index
                elif event['key'] == KEY_ESCAPE:
                    audio_manager.stop_bgm(fade_ms=300)
                    main_menu_renderer.cleanup()
                    return -1

        ctx.viewport = window.viewport
        ctx.clear(0.0, 0.0, 0.0)
        main_menu_renderer.render(selected_index, layout=main_menu_layout)
        window.swap_buffers()


def main():
    """游戏主函数"""
    window, ctx, base_size, screen_size, game_viewport, game_viewport_fb = initialize_window_and_context()
    selected_stage_class = resolve_stage_class()
    game_audio = GameAudioBank()
    game_audio.load_defaults()
    audio_manager = AudioManager(game_audio)

    # ===== 加载玩家设置并应用音量 =====
    settings = get_settings()
    settings.apply_audio(audio_manager)
    progress = get_progress()  # 触发加载

    # ===== CLI: --replay=path 直接进入回放 =====
    cli_replay_path = _get_cli_option("--replay=")
    pending_replay_playback = None
    if cli_replay_path:
        rep = load_replay(cli_replay_path)
        if rep is None:
            print(f"[main] 重放文件加载失败: {cli_replay_path}")
        else:
            pending_replay_playback = ReplayPlayback(rep)
            print(f"[main] 准备回放: {rep}")

    while True:
        # 选定模式：正常 / 回放
        replay_playback = pending_replay_playback
        pending_replay_playback = None  # 只触发一次

        if replay_playback is None:
            menu_choice = run_main_menu(window, ctx, screen_size, audio_manager)
            if menu_choice < 0:
                # 退出
                settings.save()
                audio_manager.stop_bgm(fade_ms=0)
                audio_manager.set_stage_bank(None)
                audio_manager.cleanup()
                window.destroy()
                sys.exit(0)

            # 根据菜单选项决定起始关卡
            # 0=开始游戏  1=测试关卡  2=查看重放  3=设置  4=退出
            if menu_choice == 0:
                active_stage_class = selected_stage_class
            elif menu_choice == 1:
                active_stage_class = StageTest
            elif menu_choice == 2:
                # 查看重放
                path = run_replay_select_menu(window, ctx, screen_size)
                if path:
                    rep = load_replay(path)
                    if rep is not None:
                        replay_playback = ReplayPlayback(rep)
                if replay_playback is None:
                    continue  # 返回主菜单
                active_stage_class = _stage_class_by_id(replay_playback.stage_id)
            elif menu_choice == 3:
                # 设置
                run_settings_menu(window, ctx, screen_size, audio_manager)
                continue
            else:
                active_stage_class = selected_stage_class
        else:
            # 来自 CLI --replay
            active_stage_class = _stage_class_by_id(replay_playback.stage_id)

        while True:
            # ===== 先创建加载画面渲染器（不依赖任何纹理资源） =====
            loading_renderer = LoadingScreenRenderer(ctx, screen_size[0], screen_size[1])

            def _show_loading(hint: str, progress: float | None = None):
                """立即渲染一帧加载画面，避免 UI 卡死感。"""
                info = {"stage_name": "Loading", "hint": hint}
                if progress is not None:
                    info["progress"] = progress
                window.poll_events()
                ctx.viewport = window.viewport
                ctx.clear(0.0, 0.0, 0.0)
                loading_renderer.render(info)
                window.swap_buffers()

            _show_loading("Loading textures...", 0.05)
            texture_asset_manager = init_texture_asset_manager(asset_root="assets")

            _show_loading("Loading laser config...", 0.15)
            laser_tex_data = get_laser_texture_data()
            laser_tex_data.load_config("assets/images/laser/laser_config.json")

            sprite_manager = SpriteManager()

            _show_loading("Uploading GPU textures...", 0.25)
            textures, sprite_uv_map = load_resources(ctx, texture_asset_manager)

            _show_loading("Registering sprites...", 0.50)
            sprite_manager._sync_from_asset_manager()
            initialize_sprite_registry_from_assets(sprite_manager, textures)

            renderer = Renderer(ctx, base_size, sprite_manager, textures, sprite_uv_map)

            _show_loading("Loading fonts...", 0.60)
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

            # ── QQ 群弹幕 emoji 子系统 ────────────────────────────────────────
            from src.game.emoji_danmaku import EmojiDanmakuSystem
            emoji_sys = EmojiDanmakuSystem(
                ctx=ctx,
                screen_size=screen_size,
                game_viewport=game_viewport,
                panel_origin=(panel_origin_x, panel_origin_y),
            )
            emoji_sys.start()

            _show_loading("Initializing UI...", 0.68)
            dialog_gl_renderer = DialogGLRenderer(ctx, screen_size[0], screen_size[1], game_viewport)
            pause_menu_renderer = PauseMenuRenderer(ctx, screen_size[0], screen_size[1])
            staff_roll_renderer = StaffRollRenderer(ctx, screen_size[0], screen_size[1])
            continue_menu_renderer = ContinueMenuRenderer(ctx, screen_size[0], screen_size[1])

            # 符卡宣言渲染器（共享资源，服务所有 Boss 符卡）
            # 需要窗口坐标下的游戏视口（y 从上），game_viewport 是 OpenGL 坐标（y 从下），
            # 这里将 y 翻转一次
            _gv_x, _gv_y_bot, _gv_w, _gv_h = game_viewport
            _gv_y_top = screen_size[1] - (_gv_y_bot + _gv_h)
            from src.game.stage.spell_declaration import SpellDeclarationRenderer
            spell_declaration_renderer = SpellDeclarationRenderer(
                ctx,
                window_size=(screen_size[0], screen_size[1]),
                game_viewport_win=(_gv_x, _gv_y_top, _gv_w, _gv_h),
            )

            item_renderer = ItemRenderer(ctx, base_size)
            item_renderer.load_texture("assets/images/item/item.png")

            _show_loading("Loading backgrounds...", 0.75)
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

            # 加载全窗口UI背景图（显示在游戏内容下层、UI面板区域）
            renderer.set_window_bg_texture('assets/ui/ui_bg.png')

            _show_loading("Loading audio...", 0.88)

            # ===== Debug: 关卡选择 + 书签菜单（在初始化关卡之前） =====
            debug_target = None
            if DEBUG_MODE:
                selected_stage_class = run_stage_select_menu(
                    window, ctx, screen_size, ALL_STAGES, selected_stage_class)
                active_stage_class = selected_stage_class
                debug_target = run_debug_menu(window, ctx, screen_size, active_stage_class)

            _show_loading("Initializing stage...", 0.95)

            # ===== 决定本局自机与 RNG 种子 =====
            if replay_playback is not None:
                run_character = replay_playback.character or settings.last_character
                run_seed = int(replay_playback.rng_seed)
            else:
                run_character = settings.last_character
                run_seed = int(time.time() * 1000) & 0x7FFFFFFF

            # 全局 RNG 播种，保证录制/回放确定性
            import random as _rnd
            try:
                import numpy as _np
                _np.random.seed(run_seed & 0xFFFFFFFF)
            except Exception:
                pass
            _rnd.seed(run_seed)

            player, bullet_pool, laser_pool, item_pool, stage_manager = initialize_game_objects(
                stage_class=active_stage_class,
                audio_manager=audio_manager,
                background_renderer=background_renderer,
                character=run_character,
            )

            # ===== 录制器 =====
            replay_recorder = None
            if replay_playback is None:
                replay_recorder = ReplayRecorder(
                    stage_id=getattr(active_stage_class, "id", active_stage_class.__name__),
                    character=run_character,
                    rng_seed=run_seed,
                )

            _show_loading("Ready.", 1.0)

            if debug_target:
                stage_manager.debug_skip_to = debug_target

            # 加载高分记录
            item_pool.stats.load_hiscore()
            player.bombs = item_pool.stats.bombs
            
            # 连接 bomb 回调：统一清弹、转点、收点和 Boss 积分事件
            def _on_player_bomb():
                item_pool.stats.bombs = max(0, item_pool.stats.bombs - 1)
                trigger_player_bomb(player, bullet_pool, item_pool, stage_manager)
            player.on_bomb_callback = _on_player_bomb

            # 连接 death 回调：触发 Continue 流程
            # 用 list 装可变 flag 是因为闭包内不能直接 reassign 外层变量；
            # 真正的状态切换由主循环每帧检查 player.is_dead 完成。
            def _on_player_death():
                # 仅打印日志，状态切换交给主循环（避免在 update 里同步 mutate UI 状态）
                print(f"[main] player died (continues_left={continues_left})")
            player.on_death = _on_player_death

            def _get_active_boss():
                if stage_manager.current_stage:
                    boss = getattr(stage_manager.current_stage, '_current_boss', None)
                    if boss is not None and getattr(boss, '_active', False):
                        return boss
                return stage_manager.get_active_boss()
            
            clock = FrameClock()
            running = True
            
            paused = False
            pause_menu_index = 0
            game_result_state = None

            # ===== Continue / Game Over 状态机 =====
            # continue_state ∈ { "none", "asking", "game_over" }
            #   "none"      : 正常游戏中
            #   "asking"    : 玩家死亡，正在弹 Continue? 菜单
            #   "game_over" : NO 或 continues 用尽，黑屏淡出后回主菜单
            MAX_CONTINUES = 3
            continue_state = "none"
            continue_menu_index = 0       # 0=YES, 1=NO
            continues_left = MAX_CONTINUES
            game_over_timer = 0           # game_over 阶段帧计数
            GAME_OVER_HOLD_FRAMES = 150   # ~2.5s 黑屏停留
            run_continued = False         # 一旦使用过 continue，本局不再上传分数 / 解锁下一关
            profile_acc = {
                "events": 0.0,
                "update": 0.0,
                "collision": 0.0,
                "render": 0.0,
                "frame": 0.0,
                "render_bg": 0.0,
                "render_enemy": 0.0,
                "render_item": 0.0,
                "render_player": 0.0,
                "render_player_sprite": 0.0,
                "render_enemy_bullet": 0.0,
                "render_laser": 0.0,
                "render_hitbox": 0.0,
                "render_ui": 0.0,
                "render_emoji_game": 0.0,
                "render_spell_decl": 0.0,
                "render_dialog": 0.0,
                "render_overlay": 0.0,
                "swap": 0.0,
            }
            profile_frames = 0

            def _profile_maybe_report():
                nonlocal profile_frames, profile_acc
                if (not PROFILE_MODE) or profile_frames < PROFILE_REPORT_FRAMES:
                    return

                inv = 1.0 / profile_frames
                avg_ms = {k: (v * inv * 1000.0) for k, v in profile_acc.items()}

                bullets_alive = -1
                if hasattr(bullet_pool, 'data') and 'alive' in bullet_pool.data.dtype.fields:
                    bullets_alive = int((bullet_pool.data['alive'] == 1).sum())

                enemy_count = 0
                if stage_manager.current_context:
                    enemy_count += len(stage_manager.current_context.get_enemy_scripts())
                if stage_manager.current_stage and stage_manager.current_stage._current_boss:
                    boss = stage_manager.current_stage._current_boss
                    if boss._active:
                        enemy_count += 1

                print(
                    "[PROFILE] "
                    f"avg_frame={avg_ms['frame']:.3f}ms "
                    f"events={avg_ms['events']:.3f}ms "
                    f"update={avg_ms['update']:.3f}ms "
                    f"collision={avg_ms['collision']:.3f}ms "
                    f"render={avg_ms['render']:.3f}ms "
                    f"rbg={avg_ms['render_bg']:.3f} "
                    f"renemy={avg_ms['render_enemy']:.3f} "
                    f"ritem={avg_ms['render_item']:.3f} "
                    f"rplayer={avg_ms['render_player']:.3f} "
                    f"rps={avg_ms['render_player_sprite']:.3f} "
                    f"rbullet={avg_ms['render_enemy_bullet']:.3f} "
                    f"rlaser={avg_ms['render_laser']:.3f} "
                    f"rhit={avg_ms['render_hitbox']:.3f} "
                    f"rui={avg_ms['render_ui']:.3f} "
                    f"remoji={avg_ms['render_emoji_game']:.3f} "
                    f"rdecl={avg_ms['render_spell_decl']:.3f} "
                    f"rdialog={avg_ms['render_dialog']:.3f} "
                    f"roverlay={avg_ms['render_overlay']:.3f} "
                    f"swap={avg_ms['swap']:.3f} "
                    f"fps={clock.get_fps():.1f} maxfps={clock.get_max_fps():.1f} "
                    f"bullets={bullets_alive} targets={enemy_count}"
                )

                profile_acc = {k: 0.0 for k in profile_acc}
                profile_frames = 0

            while running:
                dt = clock.tick(60)
                frame_start = time.perf_counter() if PROFILE_MODE else 0.0
                events_start = time.perf_counter() if PROFILE_MODE else 0.0
                
                for event in window.poll_events():
                    if event['type'] == EVENT_QUIT:
                        running = False
                    elif event['type'] == EVENT_KEYDOWN:
                        # ===== Continue / Game Over 优先拦截 =====
                        # 在 asking / game_over 状态下，吃掉所有键，不允许 ESC 触发 pause、
                        # 也不允许 C 切换自机、Z 触发其它逻辑。
                        if continue_state == "asking":
                            if event['key'] in (KEY_LEFT, KEY_RIGHT):
                                continue_menu_index = 1 - continue_menu_index
                            elif event['key'] == KEY_z:
                                if continue_menu_index == 0:
                                    # YES：消耗一个 continue，把玩家原地复活
                                    continues_left -= 1
                                    run_continued = True
                                    # ── 玩家死亡状态完整复位 ────────────────────
                                    # 仅置 is_dead=False 不够：take_damage 还启动了
                                    # death_timer 累加 + DEATH 动画。这两样不复位
                                    # 玩家就会以"死亡造型 + 时间不停积累"的状态复活。
                                    player.is_dead = False
                                    player.is_respawning = False
                                    player.death_timer = 0.0
                                    if hasattr(player, "animation") and player.animation:
                                        try:
                                            player.animation.play_spawn_animation()
                                        except Exception:
                                            pass
                                    # 资源（先 power 后 stats，避免 setter 副作用拿到旧值）
                                    player.power = 1.0
                                    player.lives = 2
                                    player.bombs = 3
                                    item_pool.stats.power = 100  # 0..max_power 的整数（100 = 1.00）
                                    item_pool.stats.lives = 2
                                    item_pool.stats.bombs = 3
                                    player.invincible_timer = 3.0
                                    player.pos = [0.0, -0.8]
                                    # 清场：清掉残余敌弹/激光/表情弹，避免一复活就再死
                                    bullet_pool.clear_all()
                                    laser_pool.clear()
                                    emoji_sys.clear()
                                    # 恢复 BGM（asking 进入时被 pause_bgm 暂停）
                                    try:
                                        audio_manager.unpause_bgm()
                                    except Exception:
                                        pass
                                    print(f"[main] CONTINUE used (continues_left={continues_left}, run_continued=True)")
                                    continue_state = "none"
                                else:
                                    # NO：进入 game_over
                                    continue_state = "game_over"
                                    game_over_timer = 0
                            elif event['key'] == KEY_ESCAPE:
                                # ESC = NO
                                continue_state = "game_over"
                                game_over_timer = 0
                            continue  # 不再走下面的 ESC/C/Z 普通逻辑
                        elif continue_state == "game_over":
                            # GAME OVER 阶段：完全不响应输入，等 timer 跑完
                            continue

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
                        else:
                            if event['key'] == KEY_c and replay_playback is None:
                                # 回放期间禁用切换自机，否则破坏确定性
                                dialog_active = False
                                if stage_manager.current_stage:
                                    dialog_state = stage_manager.current_stage.get_dialog_renderer()
                                    dialog_active = dialog_state and hasattr(dialog_state, 'is_active') and dialog_state.is_active()
                                
                                if not dialog_active and not stage_manager.loading_info:
                                    _player_cycle = {"tao": "orin", "orin": "tenshi", "tenshi": "tao"}
                                    new_name = _player_cycle.get(player.name, "tao")
                                    # 持久化"上次使用的自机"
                                    settings.last_character = new_name
                                    old_pos = list(player.pos)
                                    old_lives = player.lives
                                    old_power = player.power
                                    old_invinc = player.invincible_timer
                                    
                                    player = load_player(new_name)
                                    player.pos = old_pos
                                    player.lives = old_lives
                                    player.power = old_power
                                    player.bombs = item_pool.stats.bombs
                                    player.invincible_timer = max(old_invinc, 0.5)  # 给个短暂无敌防判定死
                                    player.on_bomb_callback = _on_player_bomb
                                    
                                    # 强制清空渲染器的纹理缓存，以便下一次渲染加载新自机的图片
                                    if hasattr(renderer, 'player_texture') and renderer.player_texture:
                                        renderer.player_texture.release()
                                        renderer.player_texture = None
                                    if hasattr(renderer, 'player_bullet_texture') and renderer.player_bullet_texture:
                                        renderer.player_bullet_texture.release()
                                        renderer.player_bullet_texture = None
                                        
                                    stage_manager._engine_refs['player'] = player
                                    if stage_manager.current_context:
                                        stage_manager.current_context.player = player
                if PROFILE_MODE:
                    profile_acc["events"] += time.perf_counter() - events_start

                # ===== 输入注入：回放替换、录制采样 =====
                if replay_playback is not None and not paused:
                    if replay_playback.is_finished:
                        # 重放结束后回到主菜单
                        game_result_state = "MAIN_MENU"
                        running = False
                        keys = KeyboardState({})
                    else:
                        keys = replay_playback.next_keys()
                        # 回放使用固定 dt 保证 dt 相关逻辑可复现
                        dt = 1.0 / 60.0
                else:
                    keys = KeyboardState(window.get_key_states())
                    if replay_recorder is not None and not paused:
                        replay_recorder.capture(keys)

                # ===== 全通关检测 =====
                # StageManager.is_finished 在最后一个 stage 没有 _next_stage_class 时置 True，
                # 这意味着包括 ending 对话 + staff roll 都跑完了。
                if getattr(stage_manager, "is_finished", False) and not paused:
                    print("[main] 检测到全通关 → 回主菜单")
                    game_result_state = "MAIN_MENU"
                    running = False

                # ===== 加载画面模式 =====
                if stage_manager.loading_info:
                    loading_render_start = time.perf_counter() if PROFILE_MODE else 0.0
                    ctx.viewport = window.viewport
                    ctx.clear(0.0, 0.0, 0.0)
                    loading_renderer.render(stage_manager.loading_info)
                    hud.state.fps = round(clock.get_fps())
                    hud.state.max_fps = round(clock.get_max_fps())
                    loading_swap_start = time.perf_counter() if PROFILE_MODE else 0.0
                    window.swap_buffers()
                    if PROFILE_MODE:
                        profile_acc["render"] += loading_swap_start - loading_render_start
                        profile_acc["swap"] += time.perf_counter() - loading_swap_start

                    if not paused:
                        loading_update_start = time.perf_counter() if PROFILE_MODE else 0.0
                        stage_manager.update(dt, bullet_pool, player)
                        if PROFILE_MODE:
                            profile_acc["update"] += time.perf_counter() - loading_update_start
                    if PROFILE_MODE:
                        profile_acc["frame"] += time.perf_counter() - frame_start
                        profile_frames += 1
                        _profile_maybe_report()
                    continue

                # ===== 正常游戏模式 =====
                dialog_active = False
                if stage_manager.current_stage:
                    dialog_state = stage_manager.current_stage.get_dialog_renderer()
                    if dialog_state and hasattr(dialog_state, 'is_active') and dialog_state.is_active():
                        dialog_active = True

                # Continue 菜单弹出时 / Game Over 黑屏期间，世界完全冻结
                world_frozen = paused or (continue_state != "none")

                update_start = time.perf_counter() if PROFILE_MODE else 0.0
                if not world_frozen:
                    if not dialog_active:
                        # 收集敌人列表用于追踪弹
                        _enemies_for_homing = []
                        if stage_manager.current_context:
                            _enemies_for_homing.extend(stage_manager.current_context.get_enemy_scripts())
                        if stage_manager.current_stage and stage_manager.current_stage._current_boss:
                            _boss = stage_manager.current_stage._current_boss
                            if _boss._active:
                                _enemies_for_homing.append(_boss)

                        player.update(dt, keys, enemies=_enemies_for_homing or None)
                        bullet_pool.update(dt)
                        laser_pool.update()
                        item_pool.update(player.pos[0], player.pos[1], dt)
                        emoji_sys.update(dt, player)

                    stage_manager.update(dt, bullet_pool, player)
                if PROFILE_MODE:
                    profile_acc["update"] += time.perf_counter() - update_start

                if stage_manager.loading_info:
                    loading_render_start = time.perf_counter() if PROFILE_MODE else 0.0
                    ctx.viewport = window.viewport
                    ctx.clear(0.0, 0.0, 0.0)
                    loading_renderer.render(stage_manager.loading_info)
                    hud.state.fps = round(clock.get_fps())
                    hud.state.max_fps = round(clock.get_max_fps())
                    loading_swap_start = time.perf_counter() if PROFILE_MODE else 0.0
                    window.swap_buffers()
                    if PROFILE_MODE:
                        profile_acc["render"] += loading_swap_start - loading_render_start
                        profile_acc["swap"] += time.perf_counter() - loading_swap_start
                        profile_acc["frame"] += time.perf_counter() - frame_start
                        profile_frames += 1
                        _profile_maybe_report()
                    continue
                
                player.score = item_pool.stats.score
                player.power = item_pool.stats.get_power_float()
                player.lives = item_pool.stats.lives
                player.bombs = item_pool.stats.bombs

                # ===== Continue / Game Over：拦截在伤害判定之前 =====
                # 玩家上一帧被打到 0 命，进入 asking 状态（凍 frame 不再 update）
                if continue_state == "none" and player.is_dead:
                    if continues_left > 0:
                        continue_state = "asking"
                        continue_menu_index = 0  # 默认指向 YES
                        # Continue 弹窗期间静音 BGM，气氛先冷下来
                        try:
                            audio_manager.pause_bgm()
                        except Exception:
                            pass
                    else:
                        continue_state = "game_over"
                        game_over_timer = 0
                        try:
                            audio_manager.stop_bgm(fade_ms=300)
                        except Exception:
                            pass

                # GAME OVER：黑屏停留 → 回主菜单
                if continue_state == "game_over":
                    game_over_timer += 1
                    if game_over_timer >= GAME_OVER_HOLD_FRAMES:
                        print(f"[main] GAME OVER → 回主菜单 (run_continued={run_continued})")
                        game_result_state = "MAIN_MENU"
                        running = False

                collision_mgr = get_collision_manager()

                collision_start = time.perf_counter() if PROFILE_MODE else 0.0
                if not world_frozen and not dialog_active:
                    hit_x, hit_y = player.get_hit_position()
                    if player.invincible_timer <= 0:
                        bullet_result = collision_mgr.check_player_vs_bullets(
                            hit_x, hit_y, player.hit_radius, bullet_pool
                        )
                        if bullet_result.occurred:
                            if player.take_damage():
                                print(f"Player hit by bullet! Lives left: {player.lives}")
                                item_pool.stats.bombs = 3
                                # 把 player.lives 的减扣同步回 stats，否则下一帧
                                # `player.lives = item_pool.stats.lives` 又把命数撑回去
                                item_pool.stats.lives = player.lives
                                bullet_pool.data['alive'][bullet_result.index] = 0
                                # Notify boss scoring system
                                _ab = stage_manager.current_stage._current_boss if stage_manager.current_stage else None
                                if _ab and _ab._active:
                                    _ab.on_player_miss()

                        # emoji 弹判定
                        if emoji_sys.check_player_collision(player):
                            if player.take_damage():
                                print(f"Player hit by emoji bullet! Lives left: {player.lives}")
                                item_pool.stats.bombs = 3
                                item_pool.stats.lives = player.lives

                    if player.invincible_timer <= 0:
                        laser_result = collision_mgr.check_player_vs_lasers(
                            hit_x, hit_y, player.hit_radius, laser_pool
                        )
                        if laser_result.occurred:
                            if player.take_damage():
                                print(f"Player hit by laser! Lives left: {player.lives}")
                                item_pool.stats.bombs = 3
                                item_pool.stats.lives = player.lives
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
                                damage_mul = player.get_bomb_damage_multiplier() if hasattr(player, 'get_bomb_damage_multiplier') else 1.0
                                target.damage(hit.damage * damage_mul)
                                # +10 per bullet hit (matches LuaSTG)
                                item_pool.stats.score += 10
                                if player.script and hasattr(player.script, 'on_bullet_hit_enemy'):
                                    player.script.on_bullet_hit_enemy(
                                        hit.bullet_idx, target, hit.damage)

                        # === 自机激光碰撞检测 ===
                        player_lasers = getattr(player, 'player_lasers', None)
                        if player_lasers:
                            for laser_data in player_lasers:
                                lx = laser_data['x']
                                ly = laser_data.get('y', -1.0)
                                laser_dmg = laser_data.get('damage', 2)
                                # laser精灵旋转90°后的光柱半宽
                                _spr = {}
                                _all_spr = {**getattr(player, 'sprites', {}), **getattr(player, 'bullet_sprites', {})}
                                _spr = _all_spr.get(laser_data.get('sprite', ''), {})
                                _rect = _spr.get('rect', [0, 0, 6, 12])
                                beam_hw = _rect[3] / 192.0 / 2.0

                                for target in collision_targets:
                                    alive_f = getattr(target, '_active', getattr(target, 'alive', True))
                                    if not alive_f:
                                        continue
                                    t_pos = getattr(target, 'pos', None)
                                    if t_pos is not None:
                                        tx, ty = float(t_pos[0]), float(t_pos[1])
                                    elif hasattr(target, 'x') and hasattr(target, 'y'):
                                        tx, ty = float(target.x), float(target.y)
                                    else:
                                        continue
                                    hit_r = getattr(target, 'hitbox_radius', getattr(target, 'hit_radius', 0.05))
                                    if abs(tx - lx) < beam_hw + hit_r and ty > ly:
                                        damage_mul = player.get_bomb_damage_multiplier() if hasattr(player, 'get_bomb_damage_multiplier') else 1.0
                                        target.damage(laser_dmg * damage_mul)
                                        item_pool.stats.score += 10

                    # === Graze detection ===
                    graze_count = collision_mgr.check_player_graze(
                        hit_x, hit_y, player.graze_radius, bullet_pool
                    )
                    if graze_count > 0:
                        item_pool.stats.graze += graze_count
                        item_pool.stats.update_point_rate()
                        player.add_graze(graze_count)
                if PROFILE_MODE:
                    profile_acc["collision"] += time.perf_counter() - collision_start
                
                hud.update_from_player(player)
                hud.state.graze = item_pool.stats.graze
                hud.state.bombs = item_pool.stats.bombs
                hud.state.point_value = item_pool.stats.point_rate
                active_boss = _get_active_boss()
                hud.update_from_boss(active_boss)
                
                enemy_scripts = None
                if hasattr(stage_manager, 'current_context') and stage_manager.current_context:
                    enemy_scripts = stage_manager.current_context.get_enemy_scripts()

                render_start = time.perf_counter() if PROFILE_MODE else 0.0
                render_segments = {} if PROFILE_MODE else None
                renderer.render_frame(
                    bullet_pool, player, stage_manager, laser_pool,
                    viewport_rect=game_viewport_fb,
                    item_renderer=item_renderer,
                    item_pool=item_pool,
                    dt=0 if paused else dt,
                    enemy_scripts=enemy_scripts,
                    profile_segments=render_segments,
                )
                
                ctx.viewport = window.viewport
                # 飘落 emoji 叠加在游戏画面上（在 HUD 之前，使其被 UI 覆盖）
                emoji_game_start = time.perf_counter() if PROFILE_MODE else 0.0
                emoji_sys.render_game()
                if PROFILE_MODE:
                    profile_acc["render_emoji_game"] += time.perf_counter() - emoji_game_start

                ui_start = time.perf_counter() if PROFILE_MODE else 0.0
                ui_renderer.render_hud(hud)
                # 热度条 + 抽奖动画叠加在 HUD 上
                emoji_sys.render_ui(ui_renderer)
                bgm_notification_text = audio_manager.get_bgm_notification_text()
                if bgm_notification_text:
                    ui_renderer.render_ttf_text(
                        text=bgm_notification_text,
                        x=screen_size[0] - 24,
                        y=screen_size[1] - 56,
                        size=26,
                        color=(255, 255, 255),
                        alpha=1.0,
                        align='right',
                        stroke_width=2,
                        stroke_color=(0, 0, 0),
                    )
                if PROFILE_MODE:
                    profile_acc["render_ui"] += time.perf_counter() - ui_start

                # 符卡宣言动画（叠加在 HUD 上，带状文字经 scissor 裁剪到游戏视口）
                if active_boss is not None:
                    _decl = getattr(active_boss, 'declaration', None)
                    if _decl is not None:
                        spell_decl_start = time.perf_counter() if PROFILE_MODE else 0.0
                        spell_declaration_renderer.render(_decl)
                        if PROFILE_MODE:
                            profile_acc["render_spell_decl"] += time.perf_counter() - spell_decl_start

                if stage_manager.current_stage:
                    dialog_state = stage_manager.current_stage.get_dialog_renderer()
                    if dialog_state:
                        dialog_start = time.perf_counter() if PROFILE_MODE else 0.0
                        # Staff roll 走单独的渲染器（全屏覆盖，不画对话框）
                        from src.game.stage.staff_roll import StaffRollState
                        if isinstance(dialog_state, StaffRollState):
                            staff_roll_renderer.render(dialog_state)
                        else:
                            dialog_gl_renderer.render(dialog_state)
                        if PROFILE_MODE:
                            profile_acc["render_dialog"] += time.perf_counter() - dialog_start

                overlay_start = time.perf_counter() if PROFILE_MODE else 0.0
                if paused:
                    pause_menu_renderer.render(pause_menu_index)

                # ===== Continue / Game Over 覆盖层 =====
                if continue_state == "asking":
                    continue_menu_renderer.render({
                        "mode": "continue",
                        "selected": continue_menu_index,
                        "continues_left": continues_left,
                    })
                elif continue_state == "game_over":
                    _go_progress = min(1.0, game_over_timer / float(max(1, GAME_OVER_HOLD_FRAMES)))
                    continue_menu_renderer.render({
                        "mode": "game_over",
                        "game_over_progress": _go_progress,
                    })
                if PROFILE_MODE:
                    profile_acc["render_overlay"] += time.perf_counter() - overlay_start

                hud.state.fps = round(clock.get_fps())
                hud.state.max_fps = round(clock.get_max_fps())

                swap_start = time.perf_counter() if PROFILE_MODE else 0.0
                if PROFILE_MODE:
                    profile_acc["render"] += swap_start - render_start
                window.swap_buffers()
                if PROFILE_MODE:
                    profile_acc["swap"] += time.perf_counter() - swap_start
                    if render_segments:
                        for k, v in render_segments.items():
                            profile_acc[k] += v
                    profile_acc["frame"] += time.perf_counter() - frame_start
                    profile_frames += 1
                    _profile_maybe_report()
            
            # 保存高分记录（用过 Continue 的本局不计入高分榜）
            if not run_continued:
                item_pool.stats.save_hiscore()
            else:
                print("[main] 本局使用过 Continue → 不写入 hiscore")

            # ===== 保存重放（仅录制模式）=====
            # 用过 Continue 的本局不能可靠回放：续关菜单的输入走 window.poll_events()
            # 而非 KeyboardState 录制流，且 asking 期间帧被冻结（recorder 也跟着冻），
            # 回放时无法重现暂停-续关那一段。直接跳过保存避免产出会跑偏的 .replay 文件。
            if run_continued and replay_recorder is not None and replay_recorder.frame_count > 0:
                print("[main] 本局使用过 Continue → 不保存重放（无法保证回放确定性）")
            elif replay_recorder is not None and replay_recorder.frame_count > 0:
                stage_id = getattr(active_stage_class, "id", active_stage_class.__name__)
                cleared = bool(getattr(stage_manager, "is_finished", False)) or \
                          (getattr(stage_manager, "current_stage", None) is not None and
                           getattr(stage_manager.current_stage, "_finished", False))
                result = {
                    "score": int(item_pool.stats.score),
                    "cleared": cleared,
                    "exit": game_result_state or "QUIT",
                }
                saved_path = replay_recorder.save(result=result)
                if saved_path:
                    print(f"[main] 重放已保存: {saved_path} ({replay_recorder.frame_count} 帧)")

                # 进度记录：通关解锁下一关 + 提交最佳分
                # 用过 continue 的本局不计分、不解锁（标准弹幕游戏惯例）
                if run_continued:
                    print("[main] 本局使用过 Continue → 不上传分数 / 不解锁下一关")
                else:
                    try:
                        progress.submit_score(stage_id, run_character, int(item_pool.stats.score))
                        if cleared:
                            progress.record_clear(stage_id, run_character)
                            # 解锁下一关
                            ids = [getattr(c, "id", c.__name__) for c in ALL_STAGES]
                            if stage_id in ids:
                                i = ids.index(stage_id)
                                if i + 1 < len(ids):
                                    if progress.unlock(ids[i + 1]):
                                        print(f"[main] 解锁新关卡: {ids[i + 1]}")
                        progress.save()
                    except Exception as e:
                        print(f"[main] 保存进度失败: {e}")

            # 始终保存设置（如音量/上次自机）
            settings.save()

            emoji_sys.stop()
            audio_manager.stop_bgm(fade_ms=0)
            audio_manager.set_stage_bank(None)
            renderer.cleanup()
            item_renderer.cleanup()
            ui_renderer.cleanup()
            dialog_gl_renderer.cleanup()
            loading_renderer.cleanup()
            pause_menu_renderer.cleanup()
            continue_menu_renderer.cleanup()
            staff_roll_renderer.cleanup()
            spell_declaration_renderer.cleanup()
            if background_renderer:
                background_renderer.cleanup()
            texture_asset_manager.clear_all()

            if game_result_state == "MAIN_MENU":
                break  # Break inner loop, go back to top `while True:` where `run_main_menu` is
            elif game_result_state == "RESTART":
                pass   # Just continue inner loop, re-initializing everything except Main Menu
            else:
                audio_manager.cleanup()
                window.destroy()
                sys.exit()

if __name__ == "__main__":
    main()
