"""
对话立绘渲染编辑器

用于编辑:
- 左右立绘槽位锚点 (anchor_px)
- 焦点效果（说话者上移、非说话者透明度与饱和度）

用法:
    python tools/dialog/dialog_portrait_editor.py
"""

import json
import os
import sys
from typing import Dict, Tuple, Optional

from PIL import Image, ImageEnhance
import pygame
from pygame import Surface


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
from src.core.atomic_io import atomic_write_json

CONFIG_PATH = os.path.join(PROJECT_ROOT, "assets", "ui", "dialog_portrait_layout.json")
CHAR_DIR = os.path.join(PROJECT_ROOT, "assets", "images", "character")

WINDOW_WIDTH = 1380
WINDOW_HEIGHT = 840
BG_COLOR = (34, 36, 44)
PANEL_COLOR = (50, 53, 64)
TEXT_COLOR = (220, 224, 236)
ACCENT = (120, 190, 255)

VIEW_X = 20
VIEW_Y = 20
VIEW_W = 880
VIEW_H = 760

DEFAULT_LAYOUT = {
    "slots": {
        "left": {"anchor_px": [220, 900]},
        "right": {"anchor_px": [1060, 900]},
    },
    "focus": {
        "speaker_lift_px": 20,
        "active_alpha": 1.0,
        "inactive_alpha": 0.62,
        "active_saturation": 1.0,
        "inactive_saturation": 0.35,
    },
    "render_order": ["left", "right"],
}


class Slider:
    def __init__(self, x, y, w, label, min_val, max_val, value, step=1.0, precision=2):
        self.rect = pygame.Rect(x, y, w, 24)
        self.label = label
        self.min_val = float(min_val)
        self.max_val = float(max_val)
        self.value = float(value)
        self.step = float(step)
        self.precision = precision
        self.dragging = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            track = pygame.Rect(self.rect.x + 175, self.rect.y + 6, self.rect.w - 175, 12)
            if track.collidepoint(event.pos):
                self.dragging = True
                self._update_value(event.pos[0], track)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            track = pygame.Rect(self.rect.x + 175, self.rect.y + 6, self.rect.w - 175, 12)
            self._update_value(event.pos[0], track)

    def _update_value(self, mouse_x, track):
        t = max(0.0, min(1.0, (mouse_x - track.x) / max(1, track.w)))
        raw = self.min_val + t * (self.max_val - self.min_val)
        v = round(raw / self.step) * self.step
        self.value = max(self.min_val, min(self.max_val, v))

    def render(self, screen: Surface, font):
        text = f"{self.label}: {self.value:.{self.precision}f}" if self.precision > 0 else f"{self.label}: {int(self.value)}"
        label_surf = font.render(text, True, TEXT_COLOR)
        screen.blit(label_surf, (self.rect.x, self.rect.y + 2))

        track = pygame.Rect(self.rect.x + 175, self.rect.y + 6, self.rect.w - 175, 12)
        pygame.draw.rect(screen, (72, 76, 90), track, border_radius=4)
        t = (self.value - self.min_val) / max(1e-6, self.max_val - self.min_val)
        fill_w = int(t * track.w)
        pygame.draw.rect(screen, ACCENT, pygame.Rect(track.x, track.y, fill_w, track.h), border_radius=4)
        pygame.draw.circle(screen, (255, 255, 255), (track.x + fill_w, track.y + 6), 7)


class Button:
    def __init__(self, x, y, w, h, text):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.hovered = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            return True
        return False

    def render(self, screen: Surface, font, active=False):
        if active:
            color = (100, 170, 245)
        else:
            color = (94, 106, 140) if self.hovered else (72, 84, 116)
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        text_surf = font.render(self.text, True, (248, 250, 252))
        screen.blit(text_surf, text_surf.get_rect(center=self.rect.center))


class PortraitEditor:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("对话立绘渲染编辑器")
        self.clock = pygame.time.Clock()
        self.running = True

        self.font = pygame.font.Font(None, 20)
        self.title_font = pygame.font.Font(None, 28)
        cn_font_path = os.path.join(PROJECT_ROOT, "assets", "fonts", "SourceHanSansCN-Bold.otf")
        if os.path.exists(cn_font_path):
            self.cn_font = pygame.font.Font(cn_font_path, 18)
            self.cn_title_font = pygame.font.Font(cn_font_path, 24)
        else:
            self.cn_font = self.font
            self.cn_title_font = self.title_font

        self.layout_cfg = self._load_layout_config()
        self._effects_cache: Dict[Tuple, Surface] = {}
        self.left_actor, self.right_actor = self._load_actor_samples()
        self.active_position = "left"
        self.status_text = ""
        self.status_frames = 0

        self._init_controls()

    def _load_layout_config(self) -> Dict:
        if not os.path.exists(CONFIG_PATH):
            return json.loads(json.dumps(DEFAULT_LAYOUT))
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            cfg = json.loads(json.dumps(DEFAULT_LAYOUT))
            cfg["slots"].update(loaded.get("slots", {}))
            cfg["focus"].update(loaded.get("focus", {}))
            render_order = loaded.get("render_order")
            if isinstance(render_order, list) and render_order:
                cfg["render_order"] = render_order
            return cfg
        except Exception:
            return json.loads(json.dumps(DEFAULT_LAYOUT))

    def _find_anchor_ratio(self, portrait_info: dict, width: int, height: int) -> Tuple[float, float]:
        anchor = portrait_info.get("anchor")
        if anchor is None:
            anchor = portrait_info.get("center", [0.5, 0.95])
        if not isinstance(anchor, (list, tuple)) or len(anchor) < 2:
            return 0.5, 0.95
        ax = float(anchor[0])
        ay = float(anchor[1])
        if ax > 1.0:
            ax = ax / max(1.0, float(width))
        if ay > 1.0:
            ay = ay / max(1.0, float(height))
        return max(0.0, min(1.0, ax)), max(0.0, min(1.0, ay))

    def _load_actor_samples(self):
        actors = []
        if os.path.isdir(CHAR_DIR):
            for char_name in sorted(os.listdir(CHAR_DIR)):
                char_path = os.path.join(CHAR_DIR, char_name)
                cfg_path = os.path.join(char_path, "character.json")
                if not os.path.isdir(char_path) or not os.path.exists(cfg_path):
                    continue
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    default_key = cfg.get("default_portrait", "normal")
                    pinfo = cfg.get("portraits", {}).get(default_key) or {}
                    rel_file = pinfo.get("file")
                    if not rel_file:
                        continue
                    full_path = os.path.join(CHAR_DIR, rel_file)
                    if not os.path.exists(full_path):
                        continue
                    img = pygame.image.load(full_path).convert_alpha()
                    actors.append(
                        {
                            "id": char_name,
                            "surface": img,
                            "base_scale": float(cfg.get("base_scale", 1.0) or 1.0),
                            "portrait_scale": float(pinfo.get("scale", 1.0) or 1.0),
                            "anchor": self._find_anchor_ratio(pinfo, img.get_width(), img.get_height()),
                        }
                    )
                except Exception:
                    continue

        if not actors:
            placeholder = Surface((320, 480), pygame.SRCALPHA)
            placeholder.fill((220, 120, 180, 230))
            sample = {
                "id": "Sample",
                "surface": placeholder,
                "base_scale": 1.0,
                "portrait_scale": 1.0,
                "anchor": (0.5, 0.95),
            }
            return sample, sample

        if len(actors) == 1:
            return actors[0], actors[0]
        return actors[0], actors[1]

    def _init_controls(self):
        panel_x = 930
        y = 80
        slots = self.layout_cfg.get("slots", {})
        focus = self.layout_cfg.get("focus", {})
        left_anchor = slots.get("left", {}).get("anchor_px", [220, 900])
        right_anchor = slots.get("right", {}).get("anchor_px", [1060, 900])

        self.s_left_x = Slider(panel_x, y, 420, "Left Anchor X", 0, 1280, left_anchor[0], step=1, precision=0)
        y += 34
        self.s_left_y = Slider(panel_x, y, 420, "Left Anchor Y", 0, 1200, left_anchor[1], step=1, precision=0)
        y += 34
        self.s_right_x = Slider(panel_x, y, 420, "Right Anchor X", 0, 1280, right_anchor[0], step=1, precision=0)
        y += 34
        self.s_right_y = Slider(panel_x, y, 420, "Right Anchor Y", 0, 1200, right_anchor[1], step=1, precision=0)
        y += 40

        self.s_lift = Slider(panel_x, y, 420, "Speaker Lift", 0, 120, focus.get("speaker_lift_px", 20), step=1, precision=0)
        y += 34
        self.s_active_alpha = Slider(panel_x, y, 420, "Active Alpha", 0.1, 1.0, focus.get("active_alpha", 1.0), step=0.01, precision=2)
        y += 34
        self.s_inactive_alpha = Slider(panel_x, y, 420, "Inactive Alpha", 0.1, 1.0, focus.get("inactive_alpha", 0.62), step=0.01, precision=2)
        y += 34
        self.s_active_sat = Slider(panel_x, y, 420, "Active Saturation", 0.0, 1.5, focus.get("active_saturation", 1.0), step=0.01, precision=2)
        y += 34
        self.s_inactive_sat = Slider(panel_x, y, 420, "Inactive Saturation", 0.0, 1.5, focus.get("inactive_saturation", 0.35), step=0.01, precision=2)
        y += 34
        self.s_preview_scale = Slider(panel_x, y, 420, "Preview Scale", 0.2, 2.0, 1.0, step=0.01, precision=2)

        self.sliders = [
            self.s_left_x, self.s_left_y, self.s_right_x, self.s_right_y,
            self.s_lift, self.s_active_alpha, self.s_inactive_alpha, self.s_active_sat,
            self.s_inactive_sat, self.s_preview_scale,
        ]

        self.btn_active_left = Button(panel_x, 560, 200, 36, "说话者: 左侧")
        self.btn_active_right = Button(panel_x + 220, 560, 200, 36, "说话者: 右侧")
        self.btn_save = Button(panel_x, 730, 420, 42, "保存到 dialog_portrait_layout.json")

    def _scaled_actor_surface(self, actor: dict) -> Surface:
        src = actor["surface"]
        factor = max(0.1, self.s_preview_scale.value * actor.get("base_scale", 1.0) * actor.get("portrait_scale", 1.0))
        w = max(1, int(src.get_width() * factor))
        h = max(1, int(src.get_height() * factor))
        return pygame.transform.smoothscale(src, (w, h))

    def _effect_surface(self, src: Surface, saturation: float, alpha: float) -> Surface:
        key = (id(src), src.get_width(), src.get_height(), int(saturation * 1000), int(alpha * 1000))
        cached = self._effects_cache.get(key)
        if cached is not None:
            return cached

        raw = pygame.image.tostring(src, "RGBA")
        img = Image.frombytes("RGBA", src.get_size(), raw)
        if abs(saturation - 1.0) > 1e-4:
            img = ImageEnhance.Color(img).enhance(max(0.0, saturation))
        if abs(alpha - 1.0) > 1e-4:
            a = img.split()[3].point(lambda p: int(max(0, min(255, p * alpha))))
            img.putalpha(a)
        out = pygame.image.fromstring(img.tobytes(), img.size, "RGBA").convert_alpha()

        if len(self._effects_cache) > 256:
            self._effects_cache.clear()
        self._effects_cache[key] = out
        return out

    def _render_actor(self, actor: dict, position: str, is_active: bool):
        scaled = self._scaled_actor_surface(actor)
        if is_active:
            sat = self.s_active_sat.value
            alpha = self.s_active_alpha.value
            lift = int(self.s_lift.value)
        else:
            sat = self.s_inactive_sat.value
            alpha = self.s_inactive_alpha.value
            lift = 0

        final_surface = self._effect_surface(scaled, sat, alpha)
        w, h = final_surface.get_size()
        anchor_x, anchor_y = actor.get("anchor", (0.5, 0.95))

        slot_x = int(self.s_left_x.value) if position == "left" else int(self.s_right_x.value)
        slot_y = int(self.s_left_y.value) if position == "left" else int(self.s_right_y.value)

        draw_x = VIEW_X + int(slot_x - anchor_x * w)
        draw_y = VIEW_Y + int(slot_y - anchor_y * h - lift)
        self.screen.blit(final_surface, (draw_x, draw_y))

        color = (250, 230, 110) if is_active else (176, 185, 205)
        name = f"{actor.get('id', '?')} ({position})"
        name_surf = self.cn_font.render(name, True, color)
        self.screen.blit(name_surf, (draw_x, max(VIEW_Y + 4, draw_y - 24)))

    def _save(self):
        self.layout_cfg["slots"]["left"]["anchor_px"] = [int(self.s_left_x.value), int(self.s_left_y.value)]
        self.layout_cfg["slots"]["right"]["anchor_px"] = [int(self.s_right_x.value), int(self.s_right_y.value)]
        focus = self.layout_cfg["focus"]
        focus["speaker_lift_px"] = int(self.s_lift.value)
        focus["active_alpha"] = round(self.s_active_alpha.value, 3)
        focus["inactive_alpha"] = round(self.s_inactive_alpha.value, 3)
        focus["active_saturation"] = round(self.s_active_sat.value, 3)
        focus["inactive_saturation"] = round(self.s_inactive_sat.value, 3)

        try:
            atomic_write_json(CONFIG_PATH, self.layout_cfg)
            self.status_text = f"已保存: {CONFIG_PATH}"
            self.status_frames = 180
        except Exception as e:
            self.status_text = f"保存失败: {e}"
            self.status_frames = 300

    def _render(self):
        self.screen.fill(BG_COLOR)
        pygame.draw.rect(self.screen, (24, 28, 36), (VIEW_X, VIEW_Y, VIEW_W, VIEW_H), border_radius=8)
        pygame.draw.rect(self.screen, (78, 86, 104), (VIEW_X, VIEW_Y, VIEW_W, VIEW_H), 1, border_radius=8)

        # 槽位标记
        lx, ly = int(self.s_left_x.value), int(self.s_left_y.value)
        rx, ry = int(self.s_right_x.value), int(self.s_right_y.value)
        for x, y, txt, color in (
            (lx, ly, "L Slot", (108, 196, 255)),
            (rx, ry, "R Slot", (255, 162, 120)),
        ):
            sx, sy = VIEW_X + x, VIEW_Y + y
            pygame.draw.line(self.screen, color, (sx - 12, sy), (sx + 12, sy), 2)
            pygame.draw.line(self.screen, color, (sx, sy - 12), (sx, sy + 12), 2)
            self.screen.blit(self.font.render(txt, True, color), (sx + 10, sy + 6))

        self._render_actor(self.left_actor, "left", self.active_position == "left")
        self._render_actor(self.right_actor, "right", self.active_position == "right")

        panel_x = 910
        pygame.draw.rect(self.screen, PANEL_COLOR, (panel_x, 20, 450, 790), border_radius=8)
        self.screen.blit(self.cn_title_font.render("立绘渲染参数", True, ACCENT), (panel_x + 16, 30))
        self.screen.blit(self.cn_font.render("实时预览：说话者上移，另一侧降低饱和度+透明度", True, (170, 180, 200)), (panel_x + 16, 58))

        for slider in self.sliders:
            slider.render(self.screen, self.font)
        self.btn_active_left.render(self.screen, self.cn_font, active=self.active_position == "left")
        self.btn_active_right.render(self.screen, self.cn_font, active=self.active_position == "right")
        self.btn_save.render(self.screen, self.cn_font)

        help_lines = [
            "快捷键:",
            "A: 左侧说话",
            "D: 右侧说话",
            "S: 保存",
            "ESC: 退出",
        ]
        y = 610
        for line in help_lines:
            self.screen.blit(self.cn_font.render(line, True, (166, 176, 196)), (panel_x + 16, y))
            y += 24

        if self.status_frames > 0 and self.status_text:
            self.status_frames -= 1
            msg = self.cn_font.render(self.status_text, True, (120, 255, 160))
            self.screen.blit(msg, (VIEW_X + 10, VIEW_Y + VIEW_H - 26))

        pygame.display.flip()

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                        break
                    if event.key == pygame.K_a:
                        self.active_position = "left"
                    if event.key == pygame.K_d:
                        self.active_position = "right"
                    if event.key == pygame.K_s:
                        self._save()
                for slider in self.sliders:
                    slider.handle_event(event)
                if self.btn_active_left.handle_event(event):
                    self.active_position = "left"
                if self.btn_active_right.handle_event(event):
                    self.active_position = "right"
                if self.btn_save.handle_event(event):
                    self._save()

            self._render()
            self.clock.tick(60)
        pygame.quit()


def main():
    PortraitEditor().run()


if __name__ == "__main__":
    main()
