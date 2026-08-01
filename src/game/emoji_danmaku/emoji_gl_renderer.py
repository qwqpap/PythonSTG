"""
Emoji OpenGL 渲染器

使用 PIL 将 emoji 字符渲染为 RGBA 纹理，再通过简单的带旋转/缩放的四边形着色器
在屏幕像素坐标系中绘制每个 emoji 对象。

字体查找顺序（跨平台）：
  Linux  : NotoColorEmoji → NotoEmoji → unifont（逐路径尝试）
  Windows: seguiemj.ttf
  macOS  : AppleColorEmoji.ttc
  最终回退：使用纯色块 + 字母代替

每个 emoji 字符单独创建一张 EMOJI_TEX_SIZE × EMOJI_TEX_SIZE 的 RGBA 纹理。
"""
import math
import os
import sys
from typing import Optional

import moderngl
import numpy as np
from PIL import Image, ImageDraw, ImageFont

EMOJI_TEX_SIZE = 96       # emoji 纹理边长（像素）
RENDER_PX_SIZE = 48.0     # 屏幕上的默认显示尺寸（scale=1.0 时）

_FONT_CANDIDATES: list[str] = [
    # Linux
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto-cjk/NotoColorEmoji.ttf",
    "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/unifont/unifont.ttf",
    # Windows
    "C:/Windows/Fonts/seguiemj.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    # macOS
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/Library/Fonts/Apple Color Emoji.ttc",
]

_EMOJI_FALLBACK_COLORS: dict[str, tuple[int, int, int]] = {
    "😂": (255, 220, 50),
    "😡": (255, 60, 60),
    "💩": (130, 85, 30),
    "😅": (100, 200, 255),
}
_EMOJI_FALLBACK_LETTERS: dict[str, str] = {
    "😂": "XD",
    "😡": ">_<",
    "💩": "poo",
    "😅": "swt",
}


def _safe_print(message: object, *, stream=None) -> None:
    """Print diagnostics without crashing on legacy Windows console encodings."""
    output = sys.stdout if stream is None else stream
    encoding = getattr(output, "encoding", None) or "utf-8"
    safe_message = str(message).encode(
        encoding,
        errors="backslashreplace",
    ).decode(encoding)
    print(safe_message, file=output)


def _try_render_emoji_pil(emoji_char: str) -> Optional["Image"]:
    """用 PIL 渲染单个 emoji，失败返回 None。"""
    try:
        from PIL import Image, ImageDraw, ImageFont

        for path in _FONT_CANDIDATES:
            if not os.path.exists(path):
                continue
            try:
                font = ImageFont.truetype(path, EMOJI_TEX_SIZE - 8)
            except Exception:
                continue

            img = Image.new("RGBA", (EMOJI_TEX_SIZE, EMOJI_TEX_SIZE), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            try:
                draw.text((4, 4), emoji_char, font=font, embedded_color=True)
            except TypeError:
                # 旧版 Pillow 不支持 embedded_color
                draw.text((4, 4), emoji_char, font=font)

            # 检查是否真的渲染出来了（有非透明像素）
            arr = np.array(img)
            if arr[:, :, 3].max() > 10:
                return img
    except ImportError:
        pass
    return None


def _make_fallback_image(emoji_char: str) -> "Image":
    """当没有 emoji 字体时，用纯色块 + 小标签作为替代。"""
    from PIL import Image, ImageDraw, ImageFont

    s = EMOJI_TEX_SIZE
    color = _EMOJI_FALLBACK_COLORS.get(emoji_char, (180, 180, 180))
    label = _EMOJI_FALLBACK_LETTERS.get(emoji_char, "?")

    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆形背景
    draw.ellipse([4, 4, s - 4, s - 4], fill=(*color, 230))

    # 文字
    font = None
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, s // 3)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    # 居中绘制
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((s - tw) // 2, (s - th) // 2), label, font=font, fill=(30, 30, 30, 255))
    return img


def _make_emoji_image(emoji_char: str) -> "Image":
    img = _try_render_emoji_pil(emoji_char)
    if img is None:
        img = _make_fallback_image(emoji_char)
    return img


# ── 渲染器 ────────────────────────────────────────────────────────────────────

class EmojiGLRenderer:
    """
    OpenGL 渲染器，负责：
      1. 将 4 个 emoji 字符烘焙成 GL 纹理
      2. 每帧将 FallingEmoji / EmojiProjectile 列表绘制到屏幕
    """

    _VERT = """
#version 330
uniform vec2 u_screen_size;
uniform vec2 u_pos;        // 屏幕中心像素坐标
uniform float u_rot;       // 旋转弧度
uniform vec2 u_size;       // 宽高像素
uniform float u_alpha;

in vec2 in_vert;   // 单位正方形 [-0.5, 0.5]
in vec2 in_uv;

out vec2 v_uv;
out float v_alpha;

void main() {
    vec2 scaled = in_vert * u_size;
    float s = sin(u_rot);
    float c = cos(u_rot);
    vec2 rot = vec2(scaled.x * c - scaled.y * s,
                    scaled.x * s + scaled.y * c);
    vec2 pos = rot + u_pos;
    // 像素 → NDC，Y 轴翻转（屏幕坐标原点在左上）
    vec2 ndc = (pos / u_screen_size) * 2.0 - 1.0;
    ndc.y = -ndc.y;
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_uv    = in_uv;
    v_alpha = u_alpha;
}
"""

    _FRAG = """
#version 330
uniform sampler2D u_tex;
in vec2 v_uv;
in float v_alpha;
out vec4 f_color;

void main() {
    vec4 c = texture(u_tex, v_uv);
    c.a *= v_alpha;
    // 预乘透明度后混合（Pillow 输出为直通 alpha）
    f_color = c;
}
"""

    def __init__(
        self,
        ctx: moderngl.Context,
        screen_size: tuple[int, int],
        emoji_chars: list[str],
    ) -> None:
        self.ctx = ctx
        self.screen_w, self.screen_h = screen_size
        self._textures: dict[str, moderngl.Texture] = {}

        self._init_shader()
        self._init_geometry()
        self._bake_textures(emoji_chars)

    # ── 初始化 ────────────────────────────────────────────────────────────────

    def _init_shader(self) -> None:
        self.prog = self.ctx.program(
            vertex_shader=self._VERT, fragment_shader=self._FRAG
        )
        self.prog["u_screen_size"].value = (float(self.screen_w), float(self.screen_h))
        self.prog["u_tex"].value = 0

    def _init_geometry(self) -> None:
        # 单位正方形：两个三角形，共 6 顶点
        verts = np.array([
            # x      y     u    v
            -0.5, -0.5,  0.0, 1.0,
             0.5, -0.5,  1.0, 1.0,
            -0.5,  0.5,  0.0, 0.0,
             0.5, -0.5,  1.0, 1.0,
             0.5,  0.5,  1.0, 0.0,
            -0.5,  0.5,  0.0, 0.0,
        ], dtype="f4")
        self.vbo = self.ctx.buffer(verts.tobytes())
        self.vao = self.ctx.vertex_array(
            self.prog,
            [(self.vbo, "2f 2f", "in_vert", "in_uv")],
        )

    # emoji → 文件名映射（assets/images/emoji/ 目录下的 PNG 文件名，不含 .png）
    _FILENAMES: dict[str, str] = {
        "😂": "face-with-tears-of-joy_1f602",
        "😡": "pouting-face_1f621",
        "💩": "pile-of-poo_1f4a9",
        "😅": "grinning-face-with-sweat_1f605",
    }

    # 预生成 PNG 存放目录（相对于项目根），从 assets 加载
    _ASSET_DIR: str = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "assets", "images", "emoji"
    )

    def _load_png_to_texture(self, png_path: str) -> Optional[moderngl.Texture]:
        """从 PNG 文件创建 GL 纹理，失败返回 None。"""
        try:
            img = Image.open(png_path).convert("RGBA")
            img = img.resize((EMOJI_TEX_SIZE, EMOJI_TEX_SIZE), Image.LANCZOS)
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            data = img.tobytes("raw", "RGBA")
            tex = self.ctx.texture((EMOJI_TEX_SIZE, EMOJI_TEX_SIZE), 4, data)
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            return tex
        except Exception as e:
            print(f"    PNG 加载失败 {png_path}: {e}")
            return None

    def _bake_textures(self, emoji_chars: list[str]) -> None:
        _safe_print("[emoji_danmaku] 正在加载 emoji 纹理...")
        asset_dir = os.path.normpath(self._ASSET_DIR)

        for ch in emoji_chars:
            try:
                tex: Optional[moderngl.Texture] = None

                # ── 优先：读取预生成的 PNG 文件 ─────────────────────────────
                fn = self._FILENAMES.get(ch)
                if fn:
                    png_path = os.path.join(asset_dir, f"{fn}.png")
                    if os.path.exists(png_path):
                        tex = self._load_png_to_texture(png_path)
                        if tex:
                            _safe_print(f"  {ch}  ← {fn}.png ✓")

                # ── 回退：PIL 即时渲染 ────────────────────────────────────
                if tex is None:
                    img = _make_emoji_image(ch)
                    img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    data = img.tobytes("raw", "RGBA")
                    tex = self.ctx.texture((EMOJI_TEX_SIZE, EMOJI_TEX_SIZE), 4, data)
                    tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
                    _safe_print(f"  {ch}  ← PIL 渲染（未找到预生成 PNG）✓")

                self._textures[ch] = tex
            except Exception as e:
                _safe_print(f"  {ch}  加载失败: {e}")

        _safe_print("[emoji_danmaku] emoji 纹理加载完成。")

    # ── 渲染 ─────────────────────────────────────────────────────────────────

    def render_object(
        self,
        emoji: str,
        x: float,
        y: float,
        scale: float = 1.0,
        rotation_deg: float = 0.0,
        alpha: float = 1.0,
    ) -> None:
        """渲染单个 emoji 对象（屏幕像素坐标，中心为锚点）。"""
        tex = self._textures.get(emoji)
        if tex is None:
            return

        px = RENDER_PX_SIZE * scale
        self.prog["u_pos"].value = (x, y)
        self.prog["u_rot"].value = math.radians(rotation_deg)
        self.prog["u_size"].value = (px, px)
        self.prog["u_alpha"].value = max(0.0, min(1.0, alpha))

        tex.use(0)
        self.vao.render(moderngl.TRIANGLES)

    def render_list(
        self,
        objects: list,
        clip_rect: tuple[int, int, int, int] | None = None,
    ) -> None:
        """
        批量渲染 FallingEmoji / EmojiProjectile 列表。
        对象需有属性: emoji, x, y, scale, rotation, alpha, alive

        clip_rect: (x, y, w, h) 屏幕像素裁剪区域（top-left 原点），
                   传入后用 GL scissor 限制渲染范围，防止溢出到 UI 区域。
        """
        if not objects:
            return

        # 启用透明度混合
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        # scissor 裁剪到游戏区域（OpenGL scissor 使用左下原点）
        if clip_rect is not None:
            cx, cy, cw, ch = clip_rect
            gl_scissor_y = self.screen_h - (cy + ch)
            self.ctx.scissor = (cx, gl_scissor_y, cw, ch)

        for obj in objects:
            if not obj.alive:
                continue
            self.render_object(
                obj.emoji, obj.x, obj.y,
                scale=obj.scale,
                rotation_deg=obj.rotation,
                alpha=obj.alpha,
            )

        # 恢复 scissor
        if clip_rect is not None:
            self.ctx.scissor = None

    def cleanup(self) -> None:
        for tex in self._textures.values():
            tex.release()
        self._textures.clear()
        self.vbo.release()
