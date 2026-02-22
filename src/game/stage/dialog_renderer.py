"""
对话渲染器

渲染对话气泡、立绘、文本等元素。
参照 LuaSTG boss_dialog.lua 中的渲染实现。
"""

import math
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass

from ...core.image_loader import load_image_surface, SoftwareSurface, FontRenderer

Surface = SoftwareSurface


@dataclass
class PortraitState:
    """立绘状态"""
    character: str
    portrait: str
    position: str  # "left" or "right"
    x: float
    y: float
    scale: float
    alpha: float = 0.0
    timer: int = 0
    is_entering: bool = True
    is_leaving: bool = False


class PortraitRenderer:
    """
    立绘渲染器

    管理角色立绘的加载、显示、淡入淡出动画。
    参照 LuaSTG boss.dialog.character 实现。
    """

    FADE_IN_FRAMES = 16        # 淡入帧数
    FADE_OUT_FRAMES = 30       # 淡出帧数
    MOVE_SPEED = 1.25          # 移动速率

    DEFAULT_POSITIONS = {
        "left": (80, 128),
        "right": (380, 128)
    }

    def __init__(self, assets_dir: Path):
        """
        Args:
            assets_dir: 资源目录路径（assets/images/character/）
        """
        self.assets_dir = assets_dir
        self._portraits: Dict[str, Surface] = {}  # 缓存加载的立绘
        self._character_configs: Dict[str, Dict] = {}  # 角色配置

        # 当前显示的立绘
        self._active_portraits: Dict[Tuple[str, int], PortraitState] = {}  # (position, num) -> state

    def load_character(self, character: str):
        """
        加载角色配置和立绘

        Args:
            character: 角色ID（如 "Hinanawi_Tenshi"）
        """
        if character in self._character_configs:
            return

        config_path = self.assets_dir / character / "character.json"
        if not config_path.exists():
            print(f"[PortraitRenderer] 警告: 找不到角色配置 {config_path}")
            return

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self._character_configs[character] = config

        # 预加载所有立绘
        for portrait_name, portrait_info in config.get("portraits", {}).items():
            portrait_key = f"{character}:{portrait_name}"
            if portrait_key not in self._portraits:
                portrait_file = self.assets_dir / portrait_info["file"]
                if portrait_file.exists():
                    try:
                        surface = load_image_surface(str(portrait_file))
                        self._portraits[portrait_key] = surface
                    except Exception as e:
                        print(f"[PortraitRenderer] 加载立绘失败 {portrait_file}: {e}")

    def show_portrait(
        self,
        character: str,
        portrait: str = "normal",
        position: str = "left",
        x: Optional[float] = None,
        y: Optional[float] = None,
        scale: float = 1.0,
        num: int = 1
    ):
        """
        显示立绘（带淡入动画）

        Args:
            character: 角色ID
            portrait: 立绘key
            position: 位置 ("left" or "right")
            x, y: 自定义坐标（None=使用默认）
            scale: 缩放倍数
            num: 角色编号（支持多角色同时在场）
        """
        self.load_character(character)

        key = (position, num)

        # 如果已经显示，更新状态
        if key in self._active_portraits:
            state = self._active_portraits[key]
            state.character = character
            state.portrait = portrait
            state.timer = 0
            state.is_entering = True
            state.is_leaving = False
        else:
            # 创建新状态
            default_x, default_y = self.DEFAULT_POSITIONS.get(position, (230, 128))
            state = PortraitState(
                character=character,
                portrait=portrait,
                position=position,
                x=x if x is not None else default_x,
                y=y if y is not None else default_y,
                scale=scale,
                alpha=0.0,
                timer=0,
                is_entering=True,
                is_leaving=False
            )
            self._active_portraits[key] = state

    def hide_portrait(self, position: str = "left", num: int = 1):
        """
        隐藏立绘（带淡出动画）

        Args:
            position: 位置
            num: 角色编号
        """
        key = (position, num)
        if key in self._active_portraits:
            self._active_portraits[key].is_leaving = True
            self._active_portraits[key].timer = 0

    def update(self):
        """更新所有立绘动画"""
        to_remove = []

        for key, state in self._active_portraits.items():
            state.timer += 1

            # 淡入动画
            if state.is_entering:
                t = min(state.timer / self.FADE_IN_FRAMES, 1.0)
                # sin^2 缓动
                state.alpha = math.sin(t * math.pi / 2) ** 2
                if t >= 1.0:
                    state.is_entering = False
                    state.alpha = 1.0

            # 淡出动画
            elif state.is_leaving:
                t = min(state.timer / self.FADE_OUT_FRAMES, 1.0)
                state.alpha = 1.0 - t
                if t >= 1.0:
                    to_remove.append(key)

        # 移除完成淡出的立绘
        for key in to_remove:
            del self._active_portraits[key]

    def render(self, screen: Surface, camera_offset: Tuple[float, float] = (0, 0)):
        """
        渲染所有立绘

        Args:
            screen: SoftwareSurface
            camera_offset: 摄像机偏移（通常为(0,0)）
        """
        for state in self._active_portraits.values():
            portrait_key = f"{state.character}:{state.portrait}"
            if portrait_key not in self._portraits:
                continue

            surface = self._portraits[portrait_key]

            # 计算位置偏移（淡入时的移动效果）
            offset_x = 0
            offset_y = 0
            if state.is_entering:
                t = state.timer / self.FADE_IN_FRAMES
                # 从对角移入
                pos_sign = 1 if state.position == "right" else -1
                offset_x = (1 - t) * 32 * pos_sign
                offset_y = (1 - t) * 16

            # 计算最终位置
            x = state.x + offset_x + camera_offset[0]
            y = state.y + offset_y + camera_offset[1]

            # 应用缩放
            if state.scale != 1.0:
                w, h = surface.get_size()
                new_w = int(w * state.scale)
                new_h = int(h * state.scale)
                surface = SoftwareSurface.scale(surface, (new_w, new_h))

            # 应用透明度
            if state.alpha < 1.0:
                surface = surface.copy()
                surface.set_alpha(int(state.alpha * 255))

            # 居中渲染
            rect = surface.get_rect(center=(int(x), int(y)))
            screen.blit(surface, (rect[0], rect[1]))

    def clear_all(self):
        """清空所有立绘"""
        self._active_portraits.clear()


class BalloonRenderer:
    """
    气泡渲染器

    渲染对话气泡和文字。
    参照 LuaSTG boss.dialog.balloon 实现。
    """

    SCALE_ANIMATION_FRAMES = 10  # 缩放动画帧数
    CHAR_WIDTH = 16              # 字符宽度
    CHAR_HEIGHT = 32             # 字符高度

    def __init__(self, balloon_config: Dict, font: Any = None):
        """
        Args:
            balloon_config: dialog_balloon.json 配置
            font: FontRenderer 对象
        """
        self.config = balloon_config
        self.font = font
        self._active_balloons: list = []  # 当前显示的气泡

    def add_balloon(
        self,
        text: str,
        x: float,
        y: float,
        style: int = 1,
        position: str = "left"
    ):
        """
        添加气泡

        Args:
            text: 文字内容
            x, y: 气泡位置
            style: 气泡样式（1-8）
            position: 位置方向 ("left"/"right")
        """
        balloon = {
            "text": text,
            "x": x,
            "y": y,
            "style": style,
            "position": position,
            "timer": 0,
            "text_progress"​: 0,  # 打字机进度
        }
        self._active_balloons.append(balloon)

    def update(self):
        """更新所有气泡"""
        for balloon in self._active_balloons:
            balloon["timer"] += 1

            # 打字机效果：每3帧显示一个字符
            if balloon["text_progress"] < len(balloon["text"]):
                if balloon["timer"] % 3 == 0:
                    balloon["text_progress"] += 1

    def render(self, screen: Surface, balloon_sprites: Dict[str, Surface]):
        """
        渲染所有气泡

        Args:
            screen: SoftwareSurface
            balloon_sprites: 气泡精灵字典 {sprite_name: Surface}
        """
        if not self.font:
            return

        for balloon in self._active_balloons:
            self._render_balloon(screen, balloon, balloon_sprites)

    def _render_balloon(self, screen: Surface, balloon: Dict, sprites: Dict[str, Surface]):
        """渲染单个气泡"""
        style = balloon["style"]
        x = balloon["x"]
        y = balloon["y"]
        timer = balloon["timer"]

        # 缩放动画
        if timer < self.SCALE_ANIMATION_FRAMES:
            scale = timer / self.SCALE_ANIMATION_FRAMES
        else:
            scale = 1.0

        # 获取气泡样式配置
        style_key = f"style_{style}"
        style_config = self.config.get("balloon_styles", {}).get(style_key)
        if not style_config:
            return

        # 计算气泡尺寸
        text_len = len(balloon["text"])
        body_width = text_len * self.CHAR_WIDTH

        # TODO: 渲染气泡头、体、尾
        # TODO: 渲染文字（打字机效果）

        # 简化版实现：直接渲染文字（后续完善）
        visible_text = balloon["text"][:balloon["text_progress"]]
        if visible_text and self.font:
            text_surface = self.font.render(visible_text, True, (0, 0, 0))
            text_rect = text_surface.get_rect(center=(int(x), int(y)))
            screen.blit(text_surface, (text_rect[0], text_rect[1]))

    def clear_all(self):
        """清空所有气泡"""
        self._active_balloons.clear()


# ==================== 完整对话渲染器 ====================

class DialogRenderer:
    """
    完整对话渲染器

    集成立绘渲染器和气泡渲染器，提供统一接口。
    """

    def __init__(self, assets_dir: Path, balloon_config_path: Path):
        """
        Args:
            assets_dir: 角色资源目录（assets/images/character/）
            balloon_config_path: 气泡配置路径（assets/images/ui/dialog_balloon.json）
        """
        self.portrait_renderer = PortraitRenderer(assets_dir)

        # 加载气泡配置
        with open(balloon_config_path, 'r', encoding='utf-8') as f:
            balloon_config = json.load(f)

        # 加载字体
        font = None
        try:
            font_path = assets_dir.parent.parent / "fonts" / "SourceHanSansCN-Bold.otf"
            if font_path.exists():
                font = FontRenderer(str(font_path), 24)
        except Exception as e:
            print(f"[DialogRenderer] 加载字体失败: {e}")
            font = FontRenderer(None, 24)

        self.balloon_renderer = BalloonRenderer(balloon_config, font)

    def update(self):
        """更新渲染器"""
        self.portrait_renderer.update()
        self.balloon_renderer.update()

    def render(self, screen: Surface):
        """渲染对话"""
        self.portrait_renderer.render(screen)
        self.balloon_renderer.render(screen, {})  # TODO: 传入气泡精灵

    def clear_all(self):
        """清空所有显示"""
        self.portrait_renderer.clear_all()
        self.balloon_renderer.clear_all()
