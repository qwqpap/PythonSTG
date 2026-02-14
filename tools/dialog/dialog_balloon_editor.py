"""
对话气泡可视化编辑器

纹理结构说明（按图集 x 坐标排列）:
  - "body" sprite (x=0): 左侧是 body 可平铺区，右侧(center_x 之后)是尾巴帽
  - "head" sprite (x=108): 左侧(0 到 center_x)是头部帽，右侧是 body 可平铺区
  - 组装: [HEAD_CAP] + [BODY_TILE × N] + [TAIL_CAP]

功能：
- 查看 dialog_balloon.png 纹理图集和每个 sprite
- 可视化 center_x 分界线（cap | body 的边界）
- 实时预览 HEAD_CAP + BODY_TILE × N + TAIL_CAP 组装效果
- 调整 body_repeat_width（body tile 宽度）
- 切换 8 种样式
- 保存修改到 dialog_balloon.json

用法:
    python tools/dialog/dialog_balloon_editor.py
"""

import sys
import os
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import pygame
from pygame import Surface

# === 常量 ===
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
BG_COLOR = (40, 40, 50)
PANEL_COLOR = (55, 55, 65)
TEXT_COLOR = (220, 220, 220)
ACCENT_COLOR = (100, 180, 255)
HIGHLIGHT_COLOR = (255, 200, 80)
SLIDER_BG = (70, 70, 80)
SLIDER_FG = (100, 180, 255)
BUTTON_COLOR = (80, 120, 180)
BUTTON_HOVER = (100, 150, 210)
HEAD_COLOR = (255, 100, 100)
BODY_COLOR = (100, 255, 100)
TAIL_COLOR = (100, 100, 255)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "assets", "images", "ui", "dialog_balloon.json")
SHEET_PATH = os.path.join(PROJECT_ROOT, "assets", "images", "ui", "dialog_balloon.png")


class Slider:
    def __init__(self, x, y, w, label, min_val, max_val, value, step=1):
        self.rect = pygame.Rect(x, y, w, 24)
        self.label = label
        self.min_val = min_val
        self.max_val = max_val
        self.value = value
        self.step = step
        self.dragging = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            track = pygame.Rect(self.rect.x + 140, self.rect.y, self.rect.w - 140, self.rect.h)
            if track.collidepoint(event.pos):
                self.dragging = True
                self._update_value(event.pos[0], track)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            track = pygame.Rect(self.rect.x + 140, self.rect.y, self.rect.w - 140, self.rect.h)
            self._update_value(event.pos[0], track)

    def _update_value(self, mouse_x, track):
        t = max(0, min(1, (mouse_x - track.x) / track.w))
        raw = self.min_val + t * (self.max_val - self.min_val)
        self.value = round(raw / self.step) * self.step
        self.value = max(self.min_val, min(self.max_val, self.value))

    def render(self, screen, font):
        label_surf = font.render(f"{self.label}: {self.value}", True, TEXT_COLOR)
        screen.blit(label_surf, (self.rect.x, self.rect.y + 2))
        track = pygame.Rect(self.rect.x + 140, self.rect.y + 6, self.rect.w - 140, 12)
        pygame.draw.rect(screen, SLIDER_BG, track, border_radius=4)
        t = (self.value - self.min_val) / max(1, self.max_val - self.min_val)
        fill_w = int(t * track.w)
        pygame.draw.rect(screen, SLIDER_FG, pygame.Rect(track.x, track.y, fill_w, track.h), border_radius=4)
        pygame.draw.circle(screen, (255, 255, 255), (track.x + fill_w, track.y + 6), 8)


class Button:
    def __init__(self, x, y, w, h, text):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.hovered = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def render(self, screen, font):
        color = BUTTON_HOVER if self.hovered else BUTTON_COLOR
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        text_surf = font.render(self.text, True, (255, 255, 255))
        screen.blit(text_surf, text_surf.get_rect(center=self.rect.center))


class BalloonEditor:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("对话气泡编辑器 - Dialog Balloon Editor")

        self.font = pygame.font.Font(None, 20)
        self.title_font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 16)

        cn_font_path = os.path.join(PROJECT_ROOT, "assets", "fonts", "SourceHanSansCN-Bold.otf")
        if os.path.exists(cn_font_path):
            self.cn_font = pygame.font.Font(cn_font_path, 18)
            self.cn_title_font = pygame.font.Font(cn_font_path, 24)
            self.preview_font = pygame.font.Font(cn_font_path, 20)
        else:
            self.cn_font = self.font
            self.cn_title_font = self.title_font
            self.preview_font = self.font

        self.config = self._load_config()
        self.sheet = self._load_sheet()
        self.sprites = self._slice_sprites()

        self.current_style = 1
        self.char_count = 10

        self._init_controls()
        self.clock = pygame.time.Clock()
        self.running = True
        self.status_msg = ""
        self.status_timer = 0

    def _load_config(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_sheet(self):
        return pygame.image.load(SHEET_PATH).convert_alpha()

    def _slice_sprites(self):
        sprites = {}
        for name, info in self.config.get("sprites", {}).items():
            rect = info.get("rect")
            if not rect or len(rect) != 4:
                continue
            x, y, w, h = rect
            sprite = Surface((w, h), pygame.SRCALPHA)
            sprite.blit(self.sheet, (0, 0), pygame.Rect(x, y, w, h))
            sprites[name] = sprite
        return sprites

    def _init_controls(self):
        panel_x = 700
        sy = 110

        self.slider_char_count = Slider(panel_x, sy, 460, "Chars(预览)", 1, 30, self.char_count)
        sy += 36
        self.slider_body_repeat_width = Slider(panel_x, sy, 460, "TileWidth", 4, 60, 16)
        sy += 36
        self.slider_head_cap_width = Slider(panel_x, sy, 460, "HeadCap宽", 0, 90, 36)
        sy += 36
        self.slider_tail_cap_width = Slider(panel_x, sy, 460, "TailCap宽", 0, 90, 54)
        sy += 36
        self.slider_body_tile_offset = Slider(panel_x, sy, 460, "Tile偏移", 0, 90, 36)

        self.sliders = [
            self.slider_char_count,
            self.slider_body_repeat_width,
            self.slider_head_cap_width,
            self.slider_tail_cap_width,
            self.slider_body_tile_offset,
        ]

        self.style_buttons = []
        for i in range(1, 9):
            self.style_buttons.append((i, Button(panel_x + (i - 1) * 58, 55, 50, 30, f"S{i}")))

        self.save_button = Button(panel_x, 720, 200, 40, "Save Config")

    def _sync_sliders_to_style(self):
        style_key = f"style_{self.current_style}"
        style_cfg = self.config.get("balloon_styles", {}).get(style_key, {})
        sprites_cfg = self.config.get("sprites", {})

        self.slider_body_repeat_width.value = int(style_cfg.get("body_repeat_width", 16))

        # 计算默认值 from sprite center_x
        head_name = style_cfg.get("head", "")
        tail_name = style_cfg.get("body", "")  # config "body" = 实际尾部件
        head_info = sprites_cfg.get(head_name, {})
        tail_info = sprites_cfg.get(tail_name, {})
        head_sprite = self.sprites.get(head_name)
        tail_sprite = self.sprites.get(tail_name)

        head_cx = head_info.get("center", [36])[0]
        tail_cx = tail_info.get("center", [54])[0]
        tail_w = tail_sprite.get_width() if tail_sprite else 108
        head_w = head_sprite.get_width() if head_sprite else 90

        default_head_cap = head_cx
        default_tail_cap = tail_w - tail_cx
        default_tile_offset = head_cx

        self.slider_head_cap_width.value = int(style_cfg.get("head_cap_width", default_head_cap))
        self.slider_tail_cap_width.value = int(style_cfg.get("tail_cap_width", default_tail_cap))
        self.slider_body_tile_offset.value = int(style_cfg.get("body_tile_offset", default_tile_offset))

        # 更新 slider 范围
        self.slider_head_cap_width.max_val = head_w
        self.slider_tail_cap_width.max_val = tail_w
        self.slider_body_tile_offset.max_val = head_w - 1

    def run(self):
        self._sync_sliders_to_style()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                        break
                    if event.key == pygame.K_LEFT:
                        self.current_style = max(1, self.current_style - 1)
                        self._sync_sliders_to_style()
                    if event.key == pygame.K_RIGHT:
                        self.current_style = min(8, self.current_style + 1)
                        self._sync_sliders_to_style()

                for slider in self.sliders:
                    slider.handle_event(event)

                for style_id, btn in self.style_buttons:
                    if btn.handle_event(event):
                        self.current_style = style_id
                        self._sync_sliders_to_style()

                if self.save_button.handle_event(event):
                    self._save_config()

            self.char_count = int(self.slider_char_count.value)
            if self.status_timer > 0:
                self.status_timer -= 1

            self._render()
            self.clock.tick(60)
        pygame.quit()

    def _render(self):
        self.screen.fill(BG_COLOR)
        self._render_sprite_analysis()
        self._render_control_panel()
        self._render_assembly_preview()

        if self.status_timer > 0 and self.status_msg:
            msg_surf = self.cn_font.render(self.status_msg, True, (100, 255, 100))
            self.screen.blit(msg_surf, (WINDOW_WIDTH // 2 - msg_surf.get_width() // 2, WINDOW_HEIGHT - 30))

        pygame.display.flip()

    def _get_style_sprites(self):
        style_key = f"style_{self.current_style}"
        style_cfg = self.config.get("balloon_styles", {}).get(style_key, {})
        sprites_cfg = self.config.get("sprites", {})

        head_name = style_cfg.get("head", "")
        tail_name = style_cfg.get("body", "")  # config "body" = 实际尾部件

        head_sprite = self.sprites.get(head_name)
        tail_sprite = self.sprites.get(tail_name)
        head_info = sprites_cfg.get(head_name, {})
        tail_info = sprites_cfg.get(tail_name, {})

        return style_cfg, head_name, tail_name, head_sprite, tail_sprite, head_info, tail_info

    def _render_sprite_analysis(self):
        """左侧：纹理分析面板，显示 head 和 tail(body) sprite 的结构"""
        title = self.cn_title_font.render(f"样式 {self.current_style} 纹理分析", True, ACCENT_COLOR)
        self.screen.blit(title, (20, 10))

        style_cfg, head_name, tail_name, head_sprite, tail_sprite, head_info, tail_info = self._get_style_sprites()

        y = 45
        display_scale = 2.0  # 放大显示

        # --- HEAD sprite ---
        self._render_sprite_detail(
            20, y, "HEAD sprite (左帽+body)", head_name, head_sprite, head_info,
            HEAD_COLOR, display_scale, is_head=True
        )

        if head_sprite:
            y += int(head_sprite.get_height() * display_scale) + 60

        # --- TAIL sprite (config 中叫 "body") ---
        self._render_sprite_detail(
            20, y, "TAIL sprite (body+右帽)", tail_name, tail_sprite, tail_info,
            TAIL_COLOR, display_scale, is_head=False
        )

    def _render_sprite_detail(self, x, y, label, name, sprite, info, color, scale, is_head):
        """显示单个 sprite 的详细结构，用 slider 值显示裁剪区域"""
        label_surf = self.cn_font.render(f"{label}: {name}", True, color)
        self.screen.blit(label_surf, (x, y))
        y += 22

        if not sprite:
            err = self.font.render("Missing!", True, (255, 80, 80))
            self.screen.blit(err, (x, y))
            return

        sw, sh = sprite.get_size()
        dw, dh = int(sw * scale), int(sh * scale)
        scaled = pygame.transform.smoothscale(sprite, (dw, dh))
        self.screen.blit(scaled, (x, y))
        pygame.draw.rect(self.screen, color, (x, y, dw, dh), 1)

        # center_x 参考线 (虚线风格用半透明)
        center_x_val = info.get("center", [sw // 2])[0]
        cx_px = int(center_x_val * scale)
        pygame.draw.line(self.screen, (*HIGHLIGHT_COLOR[:3], 120), (x + cx_px, y), (x + cx_px, y + dh), 1)

        if is_head:
            # head sprite: 左侧 = HEAD CAP, 右侧 = BODY 区域
            head_cap_w = int(self.slider_head_cap_width.value)
            tile_offset = int(self.slider_body_tile_offset.value)
            tile_w = int(self.slider_body_repeat_width.value)

            cap_px = int(head_cap_w * scale)
            tile_offset_px = int(tile_offset * scale)
            tile_px = int(tile_w * scale)

            # 半透明高亮 HEAD CAP 区域
            if cap_px > 0:
                cap_overlay = Surface((cap_px, dh), pygame.SRCALPHA)
                cap_overlay.fill((*HEAD_COLOR, 50))
                self.screen.blit(cap_overlay, (x, y))
            # HEAD CAP 右边界 (实线)
            pygame.draw.line(self.screen, HEAD_COLOR, (x + cap_px, y), (x + cap_px, y + dh), 2)

            # 高亮 body tile 提取区域
            tile_end_px = min(tile_offset_px + tile_px, dw)
            if tile_end_px > tile_offset_px:
                tile_overlay = Surface((tile_end_px - tile_offset_px, dh), pygame.SRCALPHA)
                tile_overlay.fill((*BODY_COLOR, 40))
                self.screen.blit(tile_overlay, (x + tile_offset_px, y))
                pygame.draw.rect(self.screen, HIGHLIGHT_COLOR,
                                 (x + tile_offset_px, y, tile_end_px - tile_offset_px, dh), 2)

            # 标注
            cap_label = self.small_font.render(f"HEAD CAP ({head_cap_w}px)", True, HEAD_COLOR)
            self.screen.blit(cap_label, (x + 2, y + dh + 2))
            tile_label = self.small_font.render(f"TILE @{tile_offset}+{tile_w}px", True, HIGHLIGHT_COLOR)
            self.screen.blit(tile_label, (x + tile_offset_px, y + dh + 16))
        else:
            # tail sprite (config "body"): 左侧 = BODY 区域, 右侧 = TAIL CAP
            tail_cap_w = int(self.slider_tail_cap_width.value)
            tail_start = sw - tail_cap_w
            tail_start_px = int(tail_start * scale)
            tail_cap_px = int(tail_cap_w * scale)

            # 半透明高亮 TAIL CAP 区域
            if tail_cap_px > 0:
                cap_overlay = Surface((dw - tail_start_px, dh), pygame.SRCALPHA)
                cap_overlay.fill((*TAIL_COLOR, 50))
                self.screen.blit(cap_overlay, (x + tail_start_px, y))
            # TAIL CAP 左边界 (实线)
            pygame.draw.line(self.screen, TAIL_COLOR, (x + tail_start_px, y), (x + tail_start_px, y + dh), 2)

            # 标注
            body_label = self.small_font.render(f"BODY ({tail_start}px)", True, BODY_COLOR)
            self.screen.blit(body_label, (x + 2, y + dh + 2))
            cap_label = self.small_font.render(f"TAIL CAP ({tail_cap_w}px)", True, TAIL_COLOR)
            self.screen.blit(cap_label, (x + tail_start_px + 2, y + dh + 2))

        # 尺寸信息
        size_text = self.small_font.render(f"{sw}x{sh}  center_x={center_x_val}", True, TEXT_COLOR)
        self.screen.blit(size_text, (x + dw + 10, y))

    def _render_control_panel(self):
        """右侧控制面板"""
        panel_x = 700
        pygame.draw.rect(self.screen, PANEL_COLOR, (panel_x - 10, 10, 510, WINDOW_HEIGHT - 20), border_radius=8)

        title = self.cn_title_font.render(f"样式 {self.current_style} 控制", True, ACCENT_COLOR)
        self.screen.blit(title, (panel_x, 20))

        for style_id, btn in self.style_buttons:
            if style_id == self.current_style:
                pygame.draw.rect(self.screen, HIGHLIGHT_COLOR, btn.rect.inflate(4, 4), 2, border_radius=6)
            btn.render(self.screen, self.font)

        for slider in self.sliders:
            slider.render(self.screen, self.font)

        # 当前结构信息
        style_cfg, head_name, tail_name, head_sprite, tail_sprite, head_info, tail_info = self._get_style_sprites()

        info_y = 300
        tile_w = int(self.slider_body_repeat_width.value)
        head_cap_w = int(self.slider_head_cap_width.value)
        tail_cap_w = int(self.slider_tail_cap_width.value)
        tile_offset = int(self.slider_body_tile_offset.value)

        body_total = tile_w * self.char_count
        total_w = head_cap_w + body_total + tail_cap_w

        info_lines = [
            f"组装结构:",
            f"  HEAD_CAP = head sprite [0..{head_cap_w}] = {head_cap_w}px",
            f"  BODY_TILE = head sprite [{tile_offset}..{tile_offset+tile_w}] × {self.char_count}",
            f"  TAIL_CAP = body sprite 右 {tail_cap_w}px",
            f"  总宽度 = {head_cap_w}+{body_total}+{tail_cap_w} = {total_w}px",
            f"",
            f"Config 映射:",
            f"  head → {head_name}",
            f"  body → {tail_name} (含尾帽)",
        ]
        for line in info_lines:
            self.screen.blit(self.cn_font.render(line, True, TEXT_COLOR), (panel_x, info_y))
            info_y += 20

        # 操作说明
        help_y = info_y + 10
        help_lines = [
            "操作说明:",
            "  ← →  切换样式",
            "  HeadCap宽 = 头帽裁剪宽度",
            "  TailCap宽 = 尾帽裁剪宽度",
            "  Tile偏移 = body tile 在 head 中的起始位置",
            "  TileWidth = body tile 宽度",
            "  Save 保存到 JSON",
        ]
        for line in help_lines:
            self.screen.blit(self.cn_font.render(line, True, (150, 150, 160)), (panel_x, help_y))
            help_y += 20

        self.save_button.render(self.screen, self.font)

    def _render_assembly_preview(self):
        """底部：气泡组装预览"""
        preview_x = 20
        preview_y = 550

        title = self.cn_title_font.render(f"组装预览 (样式 {self.current_style}, {self.char_count} 字符)", True, ACCENT_COLOR)
        self.screen.blit(title, (preview_x, preview_y - 30))

        style_cfg, head_name, tail_name, head_sprite, tail_sprite, head_info, tail_info = self._get_style_sprites()
        if not head_sprite or not tail_sprite:
            self.screen.blit(self.font.render("Missing sprites!", True, (255, 80, 80)), (preview_x, preview_y))
            return

        # 使用 slider 值
        tile_width = int(self.slider_body_repeat_width.value)
        head_cap_w = int(self.slider_head_cap_width.value)
        tail_cap_w = int(self.slider_tail_cap_width.value)
        tile_offset = int(self.slider_body_tile_offset.value)
        sprite_h = head_sprite.get_height()
        head_w = head_sprite.get_width()
        tail_w = tail_sprite.get_width()

        # 提取 body tile（from head sprite，从 tile_offset 开始）
        tile_x = min(tile_offset, max(0, head_w - tile_width))
        actual_tile_w = min(tile_width, head_w - tile_x)
        if actual_tile_w <= 0:
            actual_tile_w = 1
        body_tile = Surface((actual_tile_w, sprite_h), pygame.SRCALPHA)
        body_tile.blit(head_sprite, (0, 0), pygame.Rect(tile_x, 0, actual_tile_w, sprite_h))

        # 组装
        body_total_w = actual_tile_w * self.char_count
        total_w = head_cap_w + body_total_w + tail_cap_w
        bubble = Surface((total_w, sprite_h), pygame.SRCALPHA)

        # HEAD CAP
        bubble.blit(head_sprite, (0, 0), pygame.Rect(0, 0, head_cap_w, sprite_h))

        # BODY TILES
        x = head_cap_w
        for _ in range(self.char_count):
            bubble.blit(body_tile, (x, 0))
            x += actual_tile_w

        # TAIL CAP
        tail_start = tail_w - tail_cap_w
        bubble.blit(tail_sprite, (x, 0), pygame.Rect(tail_start, 0, tail_cap_w, sprite_h))

        # 添加预览文字
        preview_text = "测试文本预览样例！这是气泡"[:self.char_count]
        text_color = tuple(self.config.get("layout_params", {}).get("text_color", [0, 0, 0]))
        text_surf = self.preview_font.render(preview_text, True, text_color)
        text_y = (sprite_h - text_surf.get_height()) // 2
        text_x = head_cap_w + 4
        bubble.blit(text_surf, (text_x, text_y))

        # 缩放显示
        max_preview_w = 650
        max_preview_h = 180
        scale = min(max_preview_w / max(1, total_w), max_preview_h / max(1, sprite_h), 2.5)
        dw = int(total_w * scale)
        dh = int(sprite_h * scale)

        if dw > 0 and dh > 0:
            scaled_bubble = pygame.transform.smoothscale(bubble, (dw, dh))
            self.screen.blit(scaled_bubble, (preview_x, preview_y))
            pygame.draw.rect(self.screen, (100, 100, 100), (preview_x, preview_y, dw, dh), 1)

            # 标注各段
            label_y = preview_y + dh + 5
            head_disp_w = int(head_cap_w * scale)
            body_disp_w = int(body_total_w * scale)
            tail_disp_w = int(tail_cap_w * scale)

            # HEAD CAP 标注
            pygame.draw.line(self.screen, HEAD_COLOR,
                             (preview_x, label_y), (preview_x + head_disp_w, label_y), 2)
            self.screen.blit(self.small_font.render(f"HEAD {head_cap_w}px", True, HEAD_COLOR),
                             (preview_x, label_y + 3))

            # BODY 标注
            bx = preview_x + head_disp_w
            pygame.draw.line(self.screen, BODY_COLOR, (bx, label_y), (bx + body_disp_w, label_y), 2)
            self.screen.blit(self.small_font.render(
                f"BODY {body_total_w}px ({self.char_count}x{tile_width})", True, BODY_COLOR),
                (bx, label_y + 3))

            # TAIL CAP 标注
            tx = preview_x + head_disp_w + body_disp_w
            pygame.draw.line(self.screen, TAIL_COLOR, (tx, label_y), (tx + tail_disp_w, label_y), 2)
            self.screen.blit(self.small_font.render(f"TAIL {tail_cap_w}px", True, TAIL_COLOR),
                             (tx, label_y + 3))

            # 总宽度
            self.screen.blit(self.font.render(
                f"Total: {total_w}px x {sprite_h}px  (display {scale:.1f}x)", True, TEXT_COLOR),
                (preview_x, label_y + 22))

    def _save_config(self):
        style_key = f"style_{self.current_style}"
        if style_key in self.config.get("balloon_styles", {}):
            sc = self.config["balloon_styles"][style_key]
            sc["body_repeat_width"] = int(self.slider_body_repeat_width.value)
            sc["head_cap_width"] = int(self.slider_head_cap_width.value)
            sc["tail_cap_width"] = int(self.slider_tail_cap_width.value)
            sc["body_tile_offset"] = int(self.slider_body_tile_offset.value)

        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            self.status_msg = f"已保存到 {CONFIG_PATH}"
            self.status_timer = 180
            print(f"[BalloonEditor] Saved: {CONFIG_PATH}")
        except Exception as e:
            self.status_msg = f"保存失败: {e}"
            self.status_timer = 300


def main():
    editor = BalloonEditor()
    editor.run()


if __name__ == "__main__":
    main()
