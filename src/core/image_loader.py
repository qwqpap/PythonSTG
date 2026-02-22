"""
Image loading abstraction - Pillow backend

Provides:
- load_image_rgba(): Load image file to (width, height, bytes)
- SoftwareSurface: RGBA surface for 2D composition (replaces pygame.Surface)
- FontRenderer: TTF font text rendering (replaces pygame.font.Font)

Replaces pygame.image, pygame.Surface, pygame.transform, pygame.draw, pygame.font.
"""

import os
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont


def load_image_rgba(path: str, flip_y: bool = False) -> Tuple[int, int, bytes]:
    """
    Load image file and return raw RGBA bytes.

    Args:
        path: Image file path
        flip_y: If True, flip vertically for OpenGL

    Returns:
        (width, height, rgba_bytes)
    """
    img = Image.open(path).convert("RGBA")
    if flip_y:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    return img.width, img.height, img.tobytes("raw", "RGBA")


def load_image_surface(path: str) -> 'SoftwareSurface':
    """Load image file as a SoftwareSurface."""
    img = Image.open(path).convert("RGBA")
    return SoftwareSurface(img)


class SoftwareSurface:
    """
    RGBA software surface backed by Pillow Image.
    Provides a pygame.Surface-like API for 2D composition and drawing.
    """

    def __init__(self, width_or_image, height=None):
        if isinstance(width_or_image, Image.Image):
            self._image = width_or_image if width_or_image.mode == "RGBA" else width_or_image.convert("RGBA")
        elif height is not None:
            self._image = Image.new("RGBA", (max(1, int(width_or_image)), max(1, int(height))), (0, 0, 0, 0))
        else:
            raise ValueError("SoftwareSurface requires (width, height) or a PIL Image")
        self._draw: Optional[ImageDraw.ImageDraw] = None
        self._alpha: Optional[int] = None

    @property
    def _drawer(self) -> ImageDraw.ImageDraw:
        if self._draw is None:
            self._draw = ImageDraw.Draw(self._image)
        return self._draw

    def _invalidate_draw(self):
        self._draw = None

    # ---- Size queries ----

    def get_size(self) -> Tuple[int, int]:
        return self._image.size

    def get_width(self) -> int:
        return self._image.width

    def get_height(self) -> int:
        return self._image.height

    # ---- Fill / clear ----

    def fill(self, color):
        if len(color) == 3:
            color = (*color, 255)
        elif len(color) == 4:
            color = tuple(color)
        new_img = Image.new("RGBA", self._image.size, color)
        self._image = new_img
        self._invalidate_draw()

    # ---- Blit / paste ----

    def blit(self, src: 'SoftwareSurface', dest, area=None):
        """
        Paste src onto this surface at dest position.

        Args:
            src: Source SoftwareSurface
            dest: (x, y) tuple
            area: Optional (x, y, w, h) sub-rect from source (pygame.Rect-style)
        """
        src_img = src._image if isinstance(src, SoftwareSurface) else src

        if area is not None:
            ax, ay, aw, ah = int(area[0]), int(area[1]), int(area[2]), int(area[3])
            src_img = src_img.crop((ax, ay, ax + aw, ay + ah))

        if isinstance(src, SoftwareSurface) and src._alpha is not None and src._alpha < 255:
            src_img = src_img.copy()
            alpha_band = src_img.split()[3]
            alpha_band = alpha_band.point(lambda p: int(p * src._alpha / 255))
            src_img.putalpha(alpha_band)

        dx, dy = int(dest[0]), int(dest[1])
        self._image.paste(src_img, (dx, dy), src_img)
        self._invalidate_draw()

    # ---- Sub-surface / crop ----

    def subsurface(self, rect) -> 'SoftwareSurface':
        x, y, w, h = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
        cropped = self._image.crop((x, y, x + w, y + h)).copy()
        return SoftwareSurface(cropped)

    def copy(self) -> 'SoftwareSurface':
        s = SoftwareSurface(self._image.copy())
        s._alpha = self._alpha
        return s

    # ---- Alpha ----

    def set_alpha(self, alpha: int):
        self._alpha = max(0, min(255, int(alpha)))

    def get_alpha(self):
        return self._alpha

    def convert_alpha(self) -> 'SoftwareSurface':
        return SoftwareSurface(self._image.convert("RGBA"))

    # ---- Export to bytes ----

    def to_bytes(self, fmt: str = "RGBA", flip_y: bool = False) -> bytes:
        img = self._image
        if flip_y:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        return img.tobytes("raw", fmt)

    def to_bytes_size(self, fmt: str = "RGBA", flip_y: bool = False) -> Tuple[Tuple[int, int], bytes]:
        """Return ((w, h), bytes)."""
        return self.get_size(), self.to_bytes(fmt, flip_y)

    # ---- Drawing primitives ----

    def draw_line(self, color, start, end, width=1):
        self._drawer.line([tuple(start), tuple(end)], fill=tuple(color), width=width)

    def draw_rect(self, color, rect, width=0):
        x, y, w, h = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
        if width == 0:
            self._drawer.rectangle([x, y, x + w, y + h], fill=tuple(color))
        else:
            self._drawer.rectangle([x, y, x + w, y + h], outline=tuple(color), width=width)

    def draw_circle(self, color, center, radius, width=0):
        cx, cy, r = int(center[0]), int(center[1]), int(radius)
        bbox = [cx - r, cy - r, cx + r, cy + r]
        if width == 0:
            self._drawer.ellipse(bbox, fill=tuple(color))
        else:
            self._drawer.ellipse(bbox, outline=tuple(color), width=width)

    # ---- Rect helper ----

    def get_rect(self, **kwargs):
        w, h = self._image.size
        x, y = 0, 0
        if 'center' in kwargs:
            cx, cy = kwargs['center']
            x = int(cx) - w // 2
            y = int(cy) - h // 2
        return (x, y, w, h)

    # ---- Static transform helpers ----

    @staticmethod
    def scale(surface: 'SoftwareSurface', size: tuple) -> 'SoftwareSurface':
        img = surface._image.resize((max(1, int(size[0])), max(1, int(size[1]))), Image.NEAREST)
        return SoftwareSurface(img)

    @staticmethod
    def smoothscale(surface: 'SoftwareSurface', size: tuple) -> 'SoftwareSurface':
        img = surface._image.resize((max(1, int(size[0])), max(1, int(size[1]))), Image.LANCZOS)
        return SoftwareSurface(img)

    @staticmethod
    def flip(surface: 'SoftwareSurface', flip_x: bool, flip_y: bool) -> 'SoftwareSurface':
        img = surface._image
        if flip_x:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if flip_y:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        return SoftwareSurface(img)


class FontRenderer:
    """
    TTF font renderer using Pillow's ImageFont.
    Replaces pygame.font.Font.
    """

    def __init__(self, font_path: Optional[str], size: int):
        self._size = size
        try:
            if font_path and os.path.exists(font_path):
                self._font = ImageFont.truetype(font_path, size)
            else:
                self._font = ImageFont.load_default()
        except Exception:
            self._font = ImageFont.load_default()

    def render(self, text: str, antialias: bool = True, color=(255, 255, 255)) -> SoftwareSurface:
        """Render text to a SoftwareSurface."""
        if not text:
            return SoftwareSurface(1, max(1, self._size))
        color = tuple(color)
        if len(color) == 3:
            color = (*color, 255)

        bbox = self._font.getbbox(text)
        w = max(1, int(bbox[2] - bbox[0]))
        h = max(1, int(bbox[3] - bbox[1]))

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((-bbox[0], -bbox[1]), text, font=self._font, fill=color)

        return SoftwareSurface(img)

    def size(self, text: str) -> Tuple[int, int]:
        """Get (width, height) of rendered text without creating a surface."""
        if not text:
            return (0, self._size)
        bbox = self._font.getbbox(text)
        return (max(1, int(bbox[2] - bbox[0])), max(1, int(bbox[3] - bbox[1])))

    def get_linesize(self) -> int:
        try:
            ascent, descent = self._font.getmetrics()
            return int(ascent + descent)
        except Exception:
            return self._size
