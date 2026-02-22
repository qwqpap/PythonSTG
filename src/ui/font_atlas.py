"""
Font atlas - freetype-py based glyph atlas for GL text rendering

Renders TTF glyphs into a texture atlas, provides UV mapping for
character-by-character GL quad rendering.

Used by UI renderers as an alternative to the software-surface approach.
The bitmap_font.py (HGE .fnt) system is preserved for HUD score display.
"""

import os
from typing import Dict, Optional, Tuple
import numpy as np

try:
    import freetype
    HAS_FREETYPE = True
except ImportError:
    HAS_FREETYPE = False

try:
    import moderngl
except ImportError:
    moderngl = None


class GlyphInfo:
    """Metrics and UV for one rendered glyph."""
    __slots__ = (
        'char', 'width', 'height',
        'bearing_x', 'bearing_y', 'advance',
        'u0', 'v0', 'u1', 'v1',
    )

    def __init__(self):
        self.char = ''
        self.width = 0
        self.height = 0
        self.bearing_x = 0
        self.bearing_y = 0
        self.advance = 0
        self.u0 = 0.0
        self.v0 = 0.0
        self.u1 = 0.0
        self.v1 = 0.0


class FontAtlas:
    """
    Packs glyphs from a TrueType font into a single RGBA texture atlas.

    Usage:
        atlas = FontAtlas("path/to/font.otf", 28)
        atlas.preload_ascii()
        atlas.preload_cjk_common()
        tex = atlas.create_gl_texture(ctx)

        # render text
        for ch in text:
            g = atlas.get_glyph(ch)
            # emit a quad at (cursor_x + g.bearing_x, baseline - g.bearing_y)
            # with UV (g.u0, g.v0) -> (g.u1, g.v1)
    """

    def __init__(self, font_path: str, pixel_size: int, atlas_size: int = 2048):
        if not HAS_FREETYPE:
            raise RuntimeError("freetype-py is required for FontAtlas")
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"Font not found: {font_path}")

        self._face = freetype.Face(font_path)
        self._face.set_pixel_sizes(0, pixel_size)
        self._pixel_size = pixel_size

        self._atlas_w = atlas_size
        self._atlas_h = atlas_size
        self._bitmap = np.zeros((atlas_size, atlas_size, 4), dtype=np.uint8)

        self._cursor_x = 1
        self._cursor_y = 1
        self._row_height = 0

        self._glyphs: Dict[str, GlyphInfo] = {}
        self._dirty = True
        self._gl_texture = None

    @property
    def pixel_size(self) -> int:
        return self._pixel_size

    @property
    def line_height(self) -> int:
        return int(self._face.size.height >> 6)

    # ---------- Glyph loading ----------

    def _load_glyph(self, char: str) -> Optional[GlyphInfo]:
        if char in self._glyphs:
            return self._glyphs[char]

        self._face.load_char(char, freetype.FT_LOAD_RENDER)
        bmp = self._face.glyph.bitmap
        g = GlyphInfo()
        g.char = char
        g.width = bmp.width
        g.height = bmp.rows
        g.bearing_x = self._face.glyph.bitmap_left
        g.bearing_y = self._face.glyph.bitmap_top
        g.advance = self._face.glyph.advance.x >> 6

        if g.width == 0 or g.height == 0:
            g.u0 = g.v0 = g.u1 = g.v1 = 0.0
            self._glyphs[char] = g
            return g

        if self._cursor_x + g.width + 1 > self._atlas_w:
            self._cursor_x = 1
            self._cursor_y += self._row_height + 1
            self._row_height = 0

        if self._cursor_y + g.height + 1 > self._atlas_h:
            print(f"[FontAtlas] Atlas full, cannot add glyph '{char}'")
            return None

        buf = np.array(bmp.buffer, dtype=np.uint8).reshape((g.height, g.width))

        x0, y0 = self._cursor_x, self._cursor_y
        self._bitmap[y0:y0 + g.height, x0:x0 + g.width, 0] = 255
        self._bitmap[y0:y0 + g.height, x0:x0 + g.width, 1] = 255
        self._bitmap[y0:y0 + g.height, x0:x0 + g.width, 2] = 255
        self._bitmap[y0:y0 + g.height, x0:x0 + g.width, 3] = buf

        g.u0 = x0 / self._atlas_w
        g.v0 = y0 / self._atlas_h
        g.u1 = (x0 + g.width) / self._atlas_w
        g.v1 = (y0 + g.height) / self._atlas_h

        self._cursor_x += g.width + 1
        self._row_height = max(self._row_height, g.height)
        self._glyphs[char] = g
        self._dirty = True
        return g

    def get_glyph(self, char: str) -> Optional[GlyphInfo]:
        """Get glyph info, loading on demand if needed."""
        if char in self._glyphs:
            return self._glyphs[char]
        return self._load_glyph(char)

    # ---------- Bulk preloading ----------

    def preload_ascii(self):
        for code in range(32, 127):
            self._load_glyph(chr(code))

    def preload_chars(self, chars: str):
        for ch in chars:
            self._load_glyph(ch)

    def preload_cjk_common(self, count: int = 3500):
        """Preload the most common CJK Unified Ideographs (U+4E00..U+9FFF)."""
        loaded = 0
        for code in range(0x4E00, 0x9FFF + 1):
            if loaded >= count:
                break
            self._load_glyph(chr(code))
            loaded += 1

    # ---------- GL texture ----------

    def create_gl_texture(self, ctx: 'moderngl.Context') -> 'moderngl.Texture':
        data = self._bitmap.tobytes()
        tex = ctx.texture((self._atlas_w, self._atlas_h), 4, data)
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._gl_texture = tex
        self._dirty = False
        return tex

    def update_gl_texture(self):
        """Re-upload atlas data if new glyphs were added."""
        if self._gl_texture and self._dirty:
            self._gl_texture.write(self._bitmap.tobytes())
            self._dirty = False

    @property
    def gl_texture(self):
        return self._gl_texture

    # ---------- Text measurement ----------

    def text_width(self, text: str) -> int:
        w = 0
        for ch in text:
            g = self.get_glyph(ch)
            if g:
                w += g.advance
        return w

    def text_height(self) -> int:
        return self.line_height
