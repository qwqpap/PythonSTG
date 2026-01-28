"""
HUD 布局可视化编辑器（Tk）
- 读取 assets/ui/hud_layout.json
- 显示窗口、游戏视口、右侧面板、各 UI 元素位置
- 支持拖拽元素，保存回 JSON

用法：
    python tools/ui_layout_editor.py
"""

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox

ROOT = os.path.dirname(os.path.dirname(__file__))
DEFAULT_LAYOUT_PATH = os.path.join(ROOT, "assets", "ui", "hud_layout.json")

# 与游戏保持一致的窗口/视口参数
SCREEN_SIZE = (1280, 960)
BASE_SIZE = (384, 448)
GAME_SCALE = 2
GAME_VIEW_SIZE = (BASE_SIZE[0] * GAME_SCALE, BASE_SIZE[1] * GAME_SCALE)
MARGIN_X = 32
MARGIN_Y = (SCREEN_SIZE[1] - GAME_VIEW_SIZE[1]) // 2
GAME_ORIGIN = (MARGIN_X, MARGIN_Y)

def load_config(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"布局文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_position_list(val):
    return isinstance(val, (list, tuple)) and len(val) == 2 and all(isinstance(x, (int, float)) for x in val)


def is_game_space_key(name):
    return name.startswith("boss_") or name.startswith("spell_")


class LayoutEditor:
    def __init__(self, master, layout_path=DEFAULT_LAYOUT_PATH):
        self.master = master
        self.master.title("HUD Layout Editor")
        self.layout_path = layout_path
        self.data = load_config(self.layout_path)

        self.screen_size = SCREEN_SIZE
        self.game_origin = GAME_ORIGIN
        self.game_size = GAME_VIEW_SIZE

        self.panel_cfg = self.data.get("panel", {})
        self.layout = self.data.get("layout", {})
        self.gap_to_game = self.panel_cfg.get("gap_to_game", 16)
        self.margin_right = self.panel_cfg.get("margin_right", 32)
        self.bg_color = tuple(self.panel_cfg.get("bg_color", [16, 16, 32]))
        self.bg_alpha = self.panel_cfg.get("bg_alpha", 0.6)

        # 计算面板位置尺寸
        self.panel_origin = (
            self.game_origin[0] + self.game_size[0] + self.gap_to_game,
            self.game_origin[1]
        )
        available_width = self.screen_size[0] - self.panel_origin[0] - self.margin_right
        default_panel_size = [max(200, available_width), self.game_size[1]]
        size_cfg = self.panel_cfg.get("size", default_panel_size)
        self.panel_size = (
            int(size_cfg[0]),
            int(size_cfg[1] if len(size_cfg) > 1 else default_panel_size[1])
        )

        self.canvas = tk.Canvas(master, width=self.screen_size[0], height=self.screen_size[1], bg="#0d0d10")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        ctrl_frame = tk.Frame(master)
        ctrl_frame.pack(fill=tk.X)
        tk.Button(ctrl_frame, text="保存", command=self.on_save).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(ctrl_frame, text="重新加载", command=self.on_reload).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(ctrl_frame, text="打开其他布局", command=self.on_open_file).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Label(ctrl_frame, text="拖拽矩形以调整位置 (面板元素相对面板，Boss元素相对游戏区域)" ).pack(side=tk.LEFT, padx=8)

        self.selected = None
        self.drag_offset = (0, 0)

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)

        self.draw()

    def reload_config(self):
        self.data = load_config(self.layout_path)
        self.panel_cfg = self.data.get("panel", {})
        self.layout = self.data.get("layout", {})
        self.gap_to_game = self.panel_cfg.get("gap_to_game", 16)
        self.margin_right = self.panel_cfg.get("margin_right", 32)
        self.bg_color = tuple(self.panel_cfg.get("bg_color", [16, 16, 32]))
        self.bg_alpha = self.panel_cfg.get("bg_alpha", 0.6)
        self.panel_origin = (
            self.game_origin[0] + self.game_size[0] + self.gap_to_game,
            self.game_origin[1]
        )
        available_width = self.screen_size[0] - self.panel_origin[0] - self.margin_right
        default_panel_size = [max(200, available_width), self.game_size[1]]
        size_cfg = self.panel_cfg.get("size", default_panel_size)
        self.panel_size = (
            int(size_cfg[0]),
            int(size_cfg[1] if len(size_cfg) > 1 else default_panel_size[1])
        )

    def draw(self):
        self.canvas.delete("all")
        # 背景网格
        self.draw_grid(64, fill="#202030")
        # 游戏区域
        gx, gy = self.game_origin
        gw, gh = self.game_size
        self.canvas.create_rectangle(gx, gy, gx + gw, gy + gh, outline="#4ec9b0", width=2)
        self.canvas.create_text(gx + 8, gy + 14, text="Game", anchor="nw", fill="#4ec9b0")
        # 面板区域
        px, py = self.panel_origin
        pw, ph = self.panel_size
        self.canvas.create_rectangle(px, py, px + pw, py + ph, outline="#c586c0", width=2)
        self.canvas.create_text(px + 8, py + 14, text="Panel", anchor="nw", fill="#c586c0")

        # 绘制元素
        self.items = {}
        for name, pos in self.layout.items():
            if not is_position_list(pos):
                continue
            abs_pos = self.to_abs(name, pos)
            bounds = self.get_bounds(name, abs_pos)
            color = "#dcdcaa" if is_game_space_key(name) else "#9cdcfe"
            rect = self.canvas.create_rectangle(*bounds, outline=color, fill="", width=2)
            label = self.canvas.create_text(bounds[0] + 4, bounds[1] + 4, text=name, anchor="nw", fill=color)
            self.items[name] = (rect, label)

    def draw_grid(self, step, fill="#202020"):
        w, h = self.screen_size
        for x in range(0, w, step):
            self.canvas.create_line(x, 0, x, h, fill=fill)
        for y in range(0, h, step):
            self.canvas.create_line(0, y, w, y, fill=fill)

    def to_abs(self, name, pos):
        if is_game_space_key(name):
            return (pos[0] + self.game_origin[0], pos[1] + self.game_origin[1])
        return (pos[0] + self.panel_origin[0], pos[1] + self.panel_origin[1])

    def to_rel(self, name, abs_pos):
        if is_game_space_key(name):
            return (abs_pos[0] - self.game_origin[0], abs_pos[1] - self.game_origin[1])
        return (abs_pos[0] - self.panel_origin[0], abs_pos[1] - self.panel_origin[1])

    def get_bounds(self, name, abs_pos):
        lx, ly = abs_pos
        w = self.layout.get(f"{name}_width", 120)
        h = self.layout.get(f"{name}_height", 20)
        return (lx, ly, lx + w, ly + h)

    def hit_test(self, x, y):
        for name, (rect, _) in self.items.items():
            coords = self.canvas.coords(rect)
            if coords[0] <= x <= coords[2] and coords[1] <= y <= coords[3]:
                return name
        return None

    def on_press(self, event):
        name = self.hit_test(event.x, event.y)
        if name:
            self.selected = name
            abs_pos = self.to_abs(name, self.layout[name])
            self.drag_offset = (event.x - abs_pos[0], event.y - abs_pos[1])
        else:
            self.selected = None

    def on_drag(self, event):
        if not self.selected:
            return
        name = self.selected
        new_abs = (event.x - self.drag_offset[0], event.y - self.drag_offset[1])
        new_rel = self.to_rel(name, new_abs)
        self.layout[name] = [int(new_rel[0]), int(new_rel[1])]
        self.draw()

    def on_save(self):
        # 写回布局
        self.data["panel"] = self.panel_cfg
        self.data["layout"] = self.layout
        try:
            save_config(self.layout_path, self.data)
            messagebox.showinfo("保存", f"已保存到 {self.layout_path}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def on_reload(self):
        try:
            self.reload_config()
            self.draw()
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def on_open_file(self):
        path = filedialog.askopenfilename(title="选择布局文件", filetypes=[("JSON", "*.json"), ("All", "*.*")], initialdir=os.path.join(ROOT, "assets", "ui"))
        if path:
            self.layout_path = path
            self.on_reload()


def main():
    root = tk.Tk()
    app = LayoutEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
