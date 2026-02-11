"""
纹理资产可视化编辑器

功能:
- 浏览和加载资产JSON配置文件
- 可视化预览纹理图集、精灵和动画
- 编辑精灵区域（拖拽、调整大小）
- 编辑动画帧和播放预览
- 保存修改后的配置

用法:
    python tools/texture_asset_editor.py
"""

raise SystemExit("已弃用：请使用 tools/asset_manager_qt.py")

import json
import os
import sys
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageTk, ImageDraw
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

# 添加项目根目录到路径
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ASSETS_ROOT = os.path.join(ROOT, "assets", "images")


@dataclass
class EditorSprite:
    """编辑器中的精灵数据"""
    name: str
    rect: List[int]  # [x, y, width, height]
    center: List[float]
    radius: float = 0.0
    rotate: bool = False
    scale: List[float] = None
    metadata: Dict = None
    
    def __post_init__(self):
        if self.scale is None:
            self.scale = [1.0, 1.0]
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        d = {
            "rect": self.rect,
            "center": self.center,
        }
        if self.radius > 0:
            d["radius"] = self.radius
        if self.rotate:
            d["rotate"] = self.rotate
        if self.scale != [1.0, 1.0]:
            d["scale"] = self.scale
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass 
class EditorAnimationFrame:
    """编辑器中的动画帧"""
    rect: List[int]
    center: Optional[List[float]] = None
    
    def to_dict(self) -> dict:
        d = {"rect": self.rect}
        if self.center:
            d["center"] = self.center
        return d


@dataclass
class EditorAnimation:
    """编辑器中的动画数据"""
    name: str
    frames: List[EditorAnimationFrame]
    center: List[float]
    radius: float = 0.0
    rotate: bool = False
    frame_duration: float = 0.1
    loop: bool = True
    strip: Optional[Dict] = None  # 如果使用strip模式
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        d = {
            "center": self.center,
            "frame_duration": self.frame_duration,
            "loop": self.loop,
        }
        
        if self.strip:
            d["strip"] = self.strip
        else:
            d["frames"] = [f.to_dict() for f in self.frames]
        
        if self.radius > 0:
            d["radius"] = self.radius
        if self.rotate:
            d["rotate"] = self.rotate
        if self.metadata:
            d["metadata"] = self.metadata
        return d


class TextureAssetEditor:
    """纹理资产编辑器主类"""
    
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title("纹理资产编辑器 - Texture Asset Editor")
        self.master.geometry("1400x900")
        
        # 数据
        self.current_file: Optional[str] = None
        self.config_data: Dict = {}
        self.texture_image: Optional[Image.Image] = None
        self.texture_photo: Optional[ImageTk.PhotoImage] = None
        self.sprites: Dict[str, EditorSprite] = {}
        self.animations: Dict[str, EditorAnimation] = {}
        
        # 编辑状态
        self.selected_item: Optional[str] = None
        self.selected_type: Optional[str] = None  # 'sprite' or 'animation'
        self.editing_mode: str = "select"  # select, draw_rect, edit_center
        self.drag_start: Optional[Tuple[int, int]] = None
        self.drag_handle: Optional[str] = None  # 拖拽的控制点
        self.zoom_level: float = 1.0
        self.pan_offset: Tuple[int, int] = (0, 0)
        
        # 动画预览状态
        self.animation_playing: bool = False
        self.animation_start_time: float = 0
        self.current_frame_index: int = 0
        
        # 修改追踪
        self.is_modified: bool = False
        
        self._setup_ui()
        self._setup_bindings()
        
        # 定时器
        self._update_animation()
    
    def _setup_ui(self):
        """设置UI界面"""
        # 主框架
        self.main_pane = ttk.PanedWindow(self.master, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)
        
        # 左侧面板 - 文件和资产列表
        self.left_frame = ttk.Frame(self.main_pane, width=280)
        self.main_pane.add(self.left_frame, weight=0)
        
        # 中间面板 - 纹理预览
        self.center_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(self.center_frame, weight=1)
        
        # 右侧面板 - 属性编辑
        self.right_frame = ttk.Frame(self.main_pane, width=300)
        self.main_pane.add(self.right_frame, weight=0)
        
        self._setup_left_panel()
        self._setup_center_panel()
        self._setup_right_panel()
        self._setup_menu()
        self._setup_toolbar()
    
    def _setup_menu(self):
        """设置菜单栏"""
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="新建配置", command=self._new_config, accelerator="Ctrl+N")
        file_menu.add_command(label="打开配置...", command=self._open_config, accelerator="Ctrl+O")
        file_menu.add_command(label="保存", command=self._save_config, accelerator="Ctrl+S")
        file_menu.add_command(label="另存为...", command=self._save_config_as)
        file_menu.add_separator()
        file_menu.add_command(label="加载纹理图片...", command=self._load_texture)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        
        # 编辑菜单
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="编辑", menu=edit_menu)
        edit_menu.add_command(label="添加精灵", command=self._add_sprite)
        edit_menu.add_command(label="添加动画", command=self._add_animation)
        edit_menu.add_separator()
        edit_menu.add_command(label="删除选中", command=self._delete_selected, accelerator="Delete")
        edit_menu.add_command(label="复制选中", command=self._duplicate_selected, accelerator="Ctrl+D")
        
        # 视图菜单
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="视图", menu=view_menu)
        view_menu.add_command(label="放大", command=lambda: self._zoom(1.25), accelerator="+")
        view_menu.add_command(label="缩小", command=lambda: self._zoom(0.8), accelerator="-")
        view_menu.add_command(label="适应窗口", command=self._fit_view, accelerator="F")
        view_menu.add_command(label="原始大小", command=self._reset_zoom, accelerator="1")
        
        # 快捷键绑定
        self.master.bind("<Control-n>", lambda e: self._new_config())
        self.master.bind("<Control-o>", lambda e: self._open_config())
        self.master.bind("<Control-s>", lambda e: self._save_config())
        self.master.bind("<Control-d>", lambda e: self._duplicate_selected())
        self.master.bind("<Delete>", lambda e: self._delete_selected())
        self.master.bind("<plus>", lambda e: self._zoom(1.25))
        self.master.bind("<minus>", lambda e: self._zoom(0.8))
        self.master.bind("<Key-1>", lambda e: self._reset_zoom())
        self.master.bind("<Key-f>", lambda e: self._fit_view())
    
    def _setup_toolbar(self):
        """设置工具栏"""
        toolbar = ttk.Frame(self.master)
        toolbar.pack(side=tk.TOP, fill=tk.X, before=self.main_pane)
        
        # 模式选择
        ttk.Label(toolbar, text="模式:").pack(side=tk.LEFT, padx=(10, 5))
        
        self.mode_var = tk.StringVar(value="select")
        modes = [
            ("选择", "select"),
            ("绘制矩形", "draw_rect"),
            ("编辑中心点", "edit_center"),
        ]
        for text, mode in modes:
            rb = ttk.Radiobutton(toolbar, text=text, variable=self.mode_var, value=mode,
                                command=self._on_mode_change)
            rb.pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # 缩放控制
        ttk.Label(toolbar, text="缩放:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="-", width=3, command=lambda: self._zoom(0.8)).pack(side=tk.LEFT)
        self.zoom_label = ttk.Label(toolbar, text="100%", width=6)
        self.zoom_label.pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="+", width=3, command=lambda: self._zoom(1.25)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="适应", command=self._fit_view).pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # 网格显示
        self.show_grid_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="显示网格", variable=self.show_grid_var, 
                       command=self._refresh_canvas).pack(side=tk.LEFT)
        
        self.show_all_rects_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="显示所有区域", variable=self.show_all_rects_var,
                       command=self._refresh_canvas).pack(side=tk.LEFT, padx=10)
    
    def _setup_left_panel(self):
        """设置左侧面板"""
        # 文件浏览器
        file_frame = ttk.LabelFrame(self.left_frame, text="资产文件", padding=5)
        file_frame.pack(fill=tk.X, padx=5, pady=5)
        
        btn_frame = ttk.Frame(file_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="打开", command=self._open_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="刷新", command=self._refresh_file_list).pack(side=tk.LEFT, padx=2)
        
        # 文件列表
        self.file_tree = ttk.Treeview(file_frame, height=8, show="tree")
        self.file_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.file_tree.bind("<<TreeviewSelect>>", self._on_file_select)
        
        # 资产列表
        asset_frame = ttk.LabelFrame(self.left_frame, text="资产列表", padding=5)
        asset_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 精灵列表
        sprite_frame = ttk.LabelFrame(asset_frame, text="精灵 Sprites", padding=3)
        sprite_frame.pack(fill=tk.BOTH, expand=True)
        
        self.sprite_listbox = tk.Listbox(sprite_frame, height=8, selectmode=tk.SINGLE)
        self.sprite_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        sprite_scroll = ttk.Scrollbar(sprite_frame, command=self.sprite_listbox.yview)
        sprite_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.sprite_listbox.config(yscrollcommand=sprite_scroll.set)
        self.sprite_listbox.bind("<<ListboxSelect>>", self._on_sprite_select)
        
        sprite_btn_frame = ttk.Frame(asset_frame)
        sprite_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(sprite_btn_frame, text="+ 精灵", command=self._add_sprite).pack(side=tk.LEFT, padx=2)
        ttk.Button(sprite_btn_frame, text="删除", command=lambda: self._delete_item('sprite')).pack(side=tk.LEFT, padx=2)
        
        # 动画列表
        anim_frame = ttk.LabelFrame(asset_frame, text="动画 Animations", padding=3)
        anim_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        self.anim_listbox = tk.Listbox(anim_frame, height=8, selectmode=tk.SINGLE)
        self.anim_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        anim_scroll = ttk.Scrollbar(anim_frame, command=self.anim_listbox.yview)
        anim_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.anim_listbox.config(yscrollcommand=anim_scroll.set)
        self.anim_listbox.bind("<<ListboxSelect>>", self._on_animation_select)
        
        anim_btn_frame = ttk.Frame(asset_frame)
        anim_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(anim_btn_frame, text="+ 动画", command=self._add_animation).pack(side=tk.LEFT, padx=2)
        ttk.Button(anim_btn_frame, text="删除", command=lambda: self._delete_item('animation')).pack(side=tk.LEFT, padx=2)
        
        self._refresh_file_list()
    
    def _setup_center_panel(self):
        """设置中间面板 - 纹理预览"""
        # Canvas with scrollbars
        canvas_frame = ttk.Frame(self.center_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(canvas_frame, bg="#2d2d2d", highlightthickness=0)
        self.h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        
        self.canvas.config(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 状态栏
        self.status_frame = ttk.Frame(self.center_frame)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = ttk.Label(self.status_frame, text="就绪")
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        self.coord_label = ttk.Label(self.status_frame, text="坐标: -")
        self.coord_label.pack(side=tk.RIGHT, padx=5)
    
    def _setup_right_panel(self):
        """设置右侧面板 - 属性编辑"""
        # 精灵属性编辑区
        self.sprite_props_frame = ttk.LabelFrame(self.right_frame, text="精灵属性", padding=5)
        self.sprite_props_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 名称
        row = ttk.Frame(self.sprite_props_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="名称:", width=10).pack(side=tk.LEFT)
        self.sprite_name_var = tk.StringVar()
        self.sprite_name_entry = ttk.Entry(row, textvariable=self.sprite_name_var)
        self.sprite_name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.sprite_name_entry.bind("<FocusOut>", self._on_sprite_name_change)
        self.sprite_name_entry.bind("<Return>", self._on_sprite_name_change)
        
        # Rect
        rect_frame = ttk.LabelFrame(self.sprite_props_frame, text="区域 Rect", padding=3)
        rect_frame.pack(fill=tk.X, pady=5)
        
        self.rect_vars = [tk.IntVar() for _ in range(4)]
        labels = ["X:", "Y:", "宽:", "高:"]
        for i, label in enumerate(labels):
            row = ttk.Frame(rect_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label, width=5).pack(side=tk.LEFT)
            entry = ttk.Spinbox(row, from_=0, to=9999, textvariable=self.rect_vars[i], width=8)
            entry.pack(side=tk.LEFT)
            entry.bind("<FocusOut>", self._on_rect_change)
            entry.bind("<Return>", self._on_rect_change)
        
        # Center
        center_frame = ttk.LabelFrame(self.sprite_props_frame, text="中心点 Center", padding=3)
        center_frame.pack(fill=tk.X, pady=5)
        
        self.center_vars = [tk.DoubleVar() for _ in range(2)]
        for i, label in enumerate(["X:", "Y:"]):
            row = ttk.Frame(center_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label, width=5).pack(side=tk.LEFT)
            entry = ttk.Spinbox(row, from_=-999, to=999, textvariable=self.center_vars[i], 
                               width=8, increment=0.5)
            entry.pack(side=tk.LEFT)
            entry.bind("<FocusOut>", self._on_center_change)
            entry.bind("<Return>", self._on_center_change)
        
        ttk.Button(center_frame, text="居中", command=self._center_sprite).pack(pady=2)
        
        # Radius
        row = ttk.Frame(self.sprite_props_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="半径:", width=10).pack(side=tk.LEFT)
        self.radius_var = tk.DoubleVar()
        radius_entry = ttk.Spinbox(row, from_=0, to=999, textvariable=self.radius_var, 
                                   width=8, increment=0.5)
        radius_entry.pack(side=tk.LEFT)
        radius_entry.bind("<FocusOut>", self._on_radius_change)
        radius_entry.bind("<Return>", self._on_radius_change)
        
        # Rotate
        row = ttk.Frame(self.sprite_props_frame)
        row.pack(fill=tk.X, pady=2)
        self.rotate_var = tk.BooleanVar()
        ttk.Checkbutton(row, text="跟随方向旋转 (Rotate)", variable=self.rotate_var,
                       command=self._on_rotate_change).pack(side=tk.LEFT)
        
        # 动画属性编辑区
        self.anim_props_frame = ttk.LabelFrame(self.right_frame, text="动画属性", padding=5)
        self.anim_props_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 动画名称
        row = ttk.Frame(self.anim_props_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="名称:", width=10).pack(side=tk.LEFT)
        self.anim_name_var = tk.StringVar()
        self.anim_name_entry = ttk.Entry(row, textvariable=self.anim_name_var)
        self.anim_name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.anim_name_entry.bind("<FocusOut>", self._on_anim_name_change)
        self.anim_name_entry.bind("<Return>", self._on_anim_name_change)
        
        # 帧时长
        row = ttk.Frame(self.anim_props_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="帧时长(秒):", width=10).pack(side=tk.LEFT)
        self.frame_duration_var = tk.DoubleVar(value=0.1)
        fd_entry = ttk.Spinbox(row, from_=0.01, to=10, textvariable=self.frame_duration_var,
                              width=8, increment=0.01)
        fd_entry.pack(side=tk.LEFT)
        fd_entry.bind("<FocusOut>", self._on_frame_duration_change)
        fd_entry.bind("<Return>", self._on_frame_duration_change)
        
        # 循环
        row = ttk.Frame(self.anim_props_frame)
        row.pack(fill=tk.X, pady=2)
        self.anim_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="循环播放 (Loop)", variable=self.anim_loop_var,
                       command=self._on_anim_loop_change).pack(side=tk.LEFT)
        
        # 帧列表
        frame_list_frame = ttk.LabelFrame(self.anim_props_frame, text="帧列表", padding=3)
        frame_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.frame_listbox = tk.Listbox(frame_list_frame, height=6)
        self.frame_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        frame_scroll = ttk.Scrollbar(frame_list_frame, command=self.frame_listbox.yview)
        frame_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.frame_listbox.config(yscrollcommand=frame_scroll.set)
        self.frame_listbox.bind("<<ListboxSelect>>", self._on_frame_select)
        
        frame_btn_frame = ttk.Frame(self.anim_props_frame)
        frame_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(frame_btn_frame, text="+ 帧", command=self._add_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn_frame, text="删除帧", command=self._delete_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn_frame, text="▲", command=self._move_frame_up, width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn_frame, text="▼", command=self._move_frame_down, width=3).pack(side=tk.LEFT, padx=2)
        
        # 动画预览控制
        preview_frame = ttk.LabelFrame(self.right_frame, text="动画预览", padding=5)
        preview_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 预览画布
        self.preview_canvas = tk.Canvas(preview_frame, width=128, height=128, bg="#1a1a1a")
        self.preview_canvas.pack(pady=5)
        
        # 播放控制
        ctrl_frame = ttk.Frame(preview_frame)
        ctrl_frame.pack(fill=tk.X)
        
        self.play_btn = ttk.Button(ctrl_frame, text="▶ 播放", command=self._toggle_animation)
        self.play_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(ctrl_frame, text="◀", command=self._prev_frame, width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame, text="▶", command=self._next_frame, width=3).pack(side=tk.LEFT, padx=2)
        
        self.frame_info_label = ttk.Label(preview_frame, text="帧: 0/0")
        self.frame_info_label.pack(pady=2)
    
    def _setup_bindings(self):
        """设置Canvas事件绑定"""
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<MouseWheel>", self._on_canvas_scroll)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)
        
        # 关闭窗口事件
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _refresh_file_list(self):
        """刷新文件列表"""
        self.file_tree.delete(*self.file_tree.get_children())
        
        if not os.path.exists(ASSETS_ROOT):
            return
        
        def add_dir(parent, path):
            try:
                items = sorted(os.listdir(path))
                for item in items:
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path):
                        node = self.file_tree.insert(parent, "end", text=f"📁 {item}", 
                                                     values=(item_path,), open=False)
                        add_dir(node, item_path)
                    elif item.endswith('.json'):
                        self.file_tree.insert(parent, "end", text=f"📄 {item}", 
                                             values=(item_path,))
            except PermissionError:
                pass
        
        root_node = self.file_tree.insert("", "end", text="📁 images", values=(ASSETS_ROOT,), open=True)
        add_dir(root_node, ASSETS_ROOT)
    
    def _on_file_select(self, event):
        """文件选择事件"""
        selection = self.file_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        values = self.file_tree.item(item, "values")
        if values:
            path = values[0]
            if path.endswith('.json'):
                if self.is_modified:
                    if not self._confirm_discard():
                        return
                self._load_config(path)
    
    def _load_config(self, path: str):
        """加载配置文件"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
        except Exception as e:
            messagebox.showerror("错误", f"无法加载配置文件:\n{e}")
            return
        
        self.current_file = path
        self.is_modified = False
        self.sprites.clear()
        self.animations.clear()
        
        # 解析精灵
        sprites_data = self.config_data.get('sprites', {})
        for name, data in sprites_data.items():
            self.sprites[name] = EditorSprite(
                name=name,
                rect=list(data.get('rect', [0, 0, 32, 32])),
                center=list(data.get('center', [16, 16])),
                radius=data.get('radius', 0.0),
                rotate=data.get('rotate', False),
                scale=list(data.get('scale', [1.0, 1.0])),
                metadata=data.get('metadata', {})
            )
        
        # 解析动画
        anims_data = self.config_data.get('animations', {})
        for name, data in anims_data.items():
            frames = []
            if 'frames' in data:
                for fd in data['frames']:
                    frames.append(EditorAnimationFrame(
                        rect=list(fd.get('rect', [0, 0, 32, 32])),
                        center=list(fd['center']) if 'center' in fd else None
                    ))
            elif 'strip' in data:
                strip = data['strip']
                for i in range(strip.get('count', 1)):
                    if strip.get('direction', 'horizontal') == 'horizontal':
                        x = strip['x'] + i * (strip['width'] + strip.get('spacing', 0))
                        y = strip['y']
                    else:
                        x = strip['x']
                        y = strip['y'] + i * (strip['height'] + strip.get('spacing', 0))
                    frames.append(EditorAnimationFrame(rect=[x, y, strip['width'], strip['height']]))
            
            self.animations[name] = EditorAnimation(
                name=name,
                frames=frames,
                center=list(data.get('center', [16, 16])),
                radius=data.get('radius', 0.0),
                rotate=data.get('rotate', False),
                frame_duration=data.get('frame_duration', 0.1),
                loop=data.get('loop', True),
                strip=data.get('strip'),
                metadata=data.get('metadata', {})
            )
        
        # 加载纹理
        texture_file = self.config_data.get('texture') or self.config_data.get('__image_filename', '')
        if texture_file:
            texture_path = os.path.join(os.path.dirname(path), texture_file)
            self._load_texture_file(texture_path)
        
        self._update_lists()
        self._update_title()
        self._refresh_canvas()
        self._set_status(f"已加载: {os.path.basename(path)}")
    
    def _load_texture_file(self, path: str):
        """加载纹理图片"""
        if not os.path.exists(path):
            self.texture_image = None
            self.texture_photo = None
            self._set_status(f"纹理文件不存在: {path}")
            return
        
        try:
            self.texture_image = Image.open(path).convert("RGBA")
            self._update_texture_photo()
            self._set_status(f"纹理大小: {self.texture_image.width}x{self.texture_image.height}")
        except Exception as e:
            messagebox.showerror("错误", f"无法加载纹理:\n{e}")
            self.texture_image = None
            self.texture_photo = None
    
    def _update_texture_photo(self):
        """更新缩放后的纹理图片"""
        if self.texture_image is None:
            return
        
        w = int(self.texture_image.width * self.zoom_level)
        h = int(self.texture_image.height * self.zoom_level)
        resized = self.texture_image.resize((w, h), Image.Resampling.NEAREST)
        self.texture_photo = ImageTk.PhotoImage(resized)
        
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
    
    def _refresh_canvas(self):
        """刷新画布"""
        self.canvas.delete("all")
        
        if self.texture_photo is None:
            self.canvas.create_text(200, 200, text="请加载纹理图片", fill="#666", font=("Arial", 14))
            return
        
        # 绘制纹理
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.texture_photo, tags="texture")
        
        # 绘制网格
        if self.show_grid_var.get() and self.texture_image:
            self._draw_grid()
        
        # 绘制所有区域
        if self.show_all_rects_var.get():
            self._draw_all_rects()
        
        # 绘制选中项
        if self.selected_item:
            self._draw_selected_item()
        
        # 更新滚动区域
        if self.texture_image:
            w = int(self.texture_image.width * self.zoom_level)
            h = int(self.texture_image.height * self.zoom_level)
            self.canvas.config(scrollregion=(0, 0, w, h))
    
    def _draw_grid(self):
        """绘制网格"""
        w = int(self.texture_image.width * self.zoom_level)
        h = int(self.texture_image.height * self.zoom_level)
        grid_size = int(32 * self.zoom_level)
        
        for x in range(0, w, grid_size):
            self.canvas.create_line(x, 0, x, h, fill="#444", tags="grid")
        for y in range(0, h, grid_size):
            self.canvas.create_line(0, y, w, y, fill="#444", tags="grid")
    
    def _draw_all_rects(self):
        """绘制所有精灵和动画区域"""
        z = self.zoom_level
        
        # 绘制精灵
        for name, sprite in self.sprites.items():
            if name == self.selected_item and self.selected_type == 'sprite':
                continue
            x, y, w, h = sprite.rect
            self.canvas.create_rectangle(
                x * z, y * z, (x + w) * z, (y + h) * z,
                outline="#4a9eff", width=1, tags="sprite_rect"
            )
            self.canvas.create_text(
                x * z + 2, y * z + 2, text=name, anchor=tk.NW,
                fill="#4a9eff", font=("Arial", 8), tags="sprite_label"
            )
        
        # 绘制动画帧
        for name, anim in self.animations.items():
            if name == self.selected_item and self.selected_type == 'animation':
                continue
            for i, frame in enumerate(anim.frames):
                x, y, w, h = frame.rect
                self.canvas.create_rectangle(
                    x * z, y * z, (x + w) * z, (y + h) * z,
                    outline="#ff9e4a", width=1, dash=(2, 2), tags="anim_rect"
                )
            if anim.frames:
                x, y, w, h = anim.frames[0].rect
                self.canvas.create_text(
                    x * z + 2, y * z - 10, text=f"🎬 {name}", anchor=tk.NW,
                    fill="#ff9e4a", font=("Arial", 8), tags="anim_label"
                )
    
    def _draw_selected_item(self):
        """绘制选中的项"""
        z = self.zoom_level
        
        if self.selected_type == 'sprite' and self.selected_item in self.sprites:
            sprite = self.sprites[self.selected_item]
            x, y, w, h = sprite.rect
            cx, cy = sprite.center
            
            # 绘制矩形
            self.canvas.create_rectangle(
                x * z, y * z, (x + w) * z, (y + h) * z,
                outline="#00ff00", width=2, tags="selected"
            )
            
            # 绘制控制点
            handles = [
                ("nw", x, y), ("n", x + w/2, y), ("ne", x + w, y),
                ("w", x, y + h/2), ("e", x + w, y + h/2),
                ("sw", x, y + h), ("s", x + w/2, y + h), ("se", x + w, y + h)
            ]
            for handle_name, hx, hy in handles:
                self.canvas.create_rectangle(
                    hx * z - 4, hy * z - 4, hx * z + 4, hy * z + 4,
                    fill="#00ff00", outline="white", tags=f"handle_{handle_name}"
                )
            
            # 绘制中心点
            center_x = x + cx
            center_y = y + cy
            self.canvas.create_oval(
                (center_x - 3) * z, (center_y - 3) * z,
                (center_x + 3) * z, (center_y + 3) * z,
                fill="red", outline="white", tags="center"
            )
            self.canvas.create_line(
                (center_x - 8) * z, center_y * z,
                (center_x + 8) * z, center_y * z,
                fill="red", tags="center"
            )
            self.canvas.create_line(
                center_x * z, (center_y - 8) * z,
                center_x * z, (center_y + 8) * z,
                fill="red", tags="center"
            )
            
            # 绘制碰撞半径
            if sprite.radius > 0:
                self.canvas.create_oval(
                    (center_x - sprite.radius) * z, (center_y - sprite.radius) * z,
                    (center_x + sprite.radius) * z, (center_y + sprite.radius) * z,
                    outline="yellow", dash=(3, 3), tags="radius"
                )
        
        elif self.selected_type == 'animation' and self.selected_item in self.animations:
            anim = self.animations[self.selected_item]
            
            # 绘制所有帧
            for i, frame in enumerate(anim.frames):
                x, y, w, h = frame.rect
                color = "#ffff00" if i == self.current_frame_index else "#ff9900"
                self.canvas.create_rectangle(
                    x * z, y * z, (x + w) * z, (y + h) * z,
                    outline=color, width=2 if i == self.current_frame_index else 1,
                    tags="selected"
                )
                self.canvas.create_text(
                    x * z + 2, y * z + 2, text=str(i), anchor=tk.NW,
                    fill=color, font=("Arial", 10, "bold"), tags="frame_num"
                )
            
            # 绘制当前帧中心点
            if anim.frames and 0 <= self.current_frame_index < len(anim.frames):
                frame = anim.frames[self.current_frame_index]
                x, y, w, h = frame.rect
                cx, cy = anim.center
                center_x = x + cx
                center_y = y + cy
                self.canvas.create_oval(
                    (center_x - 3) * z, (center_y - 3) * z,
                    (center_x + 3) * z, (center_y + 3) * z,
                    fill="red", outline="white", tags="center"
                )
    
    def _update_lists(self):
        """更新资产列表"""
        self.sprite_listbox.delete(0, tk.END)
        for name in sorted(self.sprites.keys()):
            self.sprite_listbox.insert(tk.END, name)
        
        self.anim_listbox.delete(0, tk.END)
        for name in sorted(self.animations.keys()):
            anim = self.animations[name]
            self.anim_listbox.insert(tk.END, f"{name} ({len(anim.frames)}帧)")
    
    def _on_sprite_select(self, event):
        """精灵选择事件"""
        selection = self.sprite_listbox.curselection()
        if not selection:
            return
        
        name = self.sprite_listbox.get(selection[0])
        self.selected_item = name
        self.selected_type = 'sprite'
        
        # 清除动画选择
        self.anim_listbox.selection_clear(0, tk.END)
        
        self._update_sprite_props()
        self._refresh_canvas()
    
    def _on_animation_select(self, event):
        """动画选择事件"""
        selection = self.anim_listbox.curselection()
        if not selection:
            return
        
        text = self.anim_listbox.get(selection[0])
        name = text.split(' (')[0]
        self.selected_item = name
        self.selected_type = 'animation'
        self.current_frame_index = 0
        
        # 清除精灵选择
        self.sprite_listbox.selection_clear(0, tk.END)
        
        self._update_animation_props()
        self._refresh_canvas()
        self._update_preview()
    
    def _update_sprite_props(self):
        """更新精灵属性面板"""
        if self.selected_type != 'sprite' or self.selected_item not in self.sprites:
            return
        
        sprite = self.sprites[self.selected_item]
        self.sprite_name_var.set(sprite.name)
        
        for i, val in enumerate(sprite.rect):
            self.rect_vars[i].set(val)
        
        for i, val in enumerate(sprite.center):
            self.center_vars[i].set(val)
        
        self.radius_var.set(sprite.radius)
        self.rotate_var.set(sprite.rotate)
    
    def _update_animation_props(self):
        """更新动画属性面板"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        anim = self.animations[self.selected_item]
        self.anim_name_var.set(anim.name)
        self.frame_duration_var.set(anim.frame_duration)
        self.anim_loop_var.set(anim.loop)
        
        # 更新帧列表
        self.frame_listbox.delete(0, tk.END)
        for i, frame in enumerate(anim.frames):
            self.frame_listbox.insert(tk.END, f"帧{i}: {frame.rect}")
        
        self._update_frame_info()
    
    def _update_frame_info(self):
        """更新帧信息"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            self.frame_info_label.config(text="帧: 0/0")
            return
        
        anim = self.animations[self.selected_item]
        self.frame_info_label.config(text=f"帧: {self.current_frame_index + 1}/{len(anim.frames)}")
    
    def _update_preview(self):
        """更新动画预览"""
        self.preview_canvas.delete("all")
        
        if self.texture_image is None:
            return
        
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        anim = self.animations[self.selected_item]
        if not anim.frames or self.current_frame_index >= len(anim.frames):
            return
        
        frame = anim.frames[self.current_frame_index]
        x, y, w, h = frame.rect
        
        try:
            # 裁剪帧图像
            frame_img = self.texture_image.crop((x, y, x + w, y + h))
            
            # 缩放到预览大小
            preview_size = 120
            scale = min(preview_size / w, preview_size / h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            frame_img = frame_img.resize((new_w, new_h), Image.Resampling.NEAREST)
            
            self.preview_photo = ImageTk.PhotoImage(frame_img)
            
            # 居中显示
            cx = 64
            cy = 64
            self.preview_canvas.create_image(cx, cy, image=self.preview_photo, tags="preview")
            
            # 绘制中心点
            cx_offset = anim.center[0] * scale
            cy_offset = anim.center[1] * scale
            self.preview_canvas.create_oval(
                64 - new_w/2 + cx_offset - 2, 64 - new_h/2 + cy_offset - 2,
                64 - new_w/2 + cx_offset + 2, 64 - new_h/2 + cy_offset + 2,
                fill="red", outline="white"
            )
        except Exception as e:
            self.preview_canvas.create_text(64, 64, text="预览错误", fill="#666")
    
    def _update_animation(self):
        """更新动画帧（定时器）"""
        if self.animation_playing and self.selected_type == 'animation':
            if self.selected_item in self.animations:
                anim = self.animations[self.selected_item]
                if anim.frames:
                    elapsed = time.time() - self.animation_start_time
                    if anim.loop:
                        self.current_frame_index = int(elapsed / anim.frame_duration) % len(anim.frames)
                    else:
                        self.current_frame_index = min(
                            int(elapsed / anim.frame_duration),
                            len(anim.frames) - 1
                        )
                    
                    self._update_preview()
                    self._update_frame_info()
                    self._refresh_canvas()
        
        self.master.after(16, self._update_animation)  # ~60fps
    
    def _toggle_animation(self):
        """切换动画播放"""
        self.animation_playing = not self.animation_playing
        if self.animation_playing:
            self.animation_start_time = time.time()
            self.play_btn.config(text="⏸ 暂停")
        else:
            self.play_btn.config(text="▶ 播放")
    
    def _prev_frame(self):
        """上一帧"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        anim = self.animations[self.selected_item]
        if anim.frames:
            self.current_frame_index = (self.current_frame_index - 1) % len(anim.frames)
            self._update_preview()
            self._update_frame_info()
            self._refresh_canvas()
    
    def _next_frame(self):
        """下一帧"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        anim = self.animations[self.selected_item]
        if anim.frames:
            self.current_frame_index = (self.current_frame_index + 1) % len(anim.frames)
            self._update_preview()
            self._update_frame_info()
            self._refresh_canvas()
    
    # Canvas 事件处理
    def _on_canvas_click(self, event):
        """画布点击"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        
        # 转换为图片坐标
        img_x = x / self.zoom_level
        img_y = y / self.zoom_level
        
        mode = self.mode_var.get()
        
        if mode == "select":
            # 检查是否点击了控制点
            handle = self._get_handle_at(x, y)
            if handle:
                self.drag_handle = handle
                self.drag_start = (img_x, img_y)
                return
            
            # 检查是否点击了精灵
            for name, sprite in self.sprites.items():
                sx, sy, sw, sh = sprite.rect
                if sx <= img_x <= sx + sw and sy <= img_y <= sy + sh:
                    self.selected_item = name
                    self.selected_type = 'sprite'
                    self.drag_start = (img_x - sx, img_y - sy)
                    self._select_in_list()
                    self._update_sprite_props()
                    self._refresh_canvas()
                    return
            
            # 检查是否点击了动画帧
            for name, anim in self.animations.items():
                for i, frame in enumerate(anim.frames):
                    fx, fy, fw, fh = frame.rect
                    if fx <= img_x <= fx + fw and fy <= img_y <= fy + fh:
                        self.selected_item = name
                        self.selected_type = 'animation'
                        self.current_frame_index = i
                        self._select_in_list()
                        self._update_animation_props()
                        self._refresh_canvas()
                        return
        
        elif mode == "draw_rect":
            self.drag_start = (img_x, img_y)
        
        elif mode == "edit_center":
            if self.selected_type == 'sprite' and self.selected_item in self.sprites:
                sprite = self.sprites[self.selected_item]
                sx, sy, sw, sh = sprite.rect
                sprite.center = [img_x - sx, img_y - sy]
                self._update_sprite_props()
                self._refresh_canvas()
                self._mark_modified()
    
    def _on_canvas_drag(self, event):
        """画布拖拽"""
        if self.drag_start is None:
            return
        
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        img_x = x / self.zoom_level
        img_y = y / self.zoom_level
        
        mode = self.mode_var.get()
        
        if mode == "select":
            if self.drag_handle:
                # 调整大小
                self._resize_with_handle(img_x, img_y)
            elif self.selected_type == 'sprite' and self.selected_item in self.sprites:
                # 移动精灵
                sprite = self.sprites[self.selected_item]
                sprite.rect[0] = int(img_x - self.drag_start[0])
                sprite.rect[1] = int(img_y - self.drag_start[1])
                self._update_sprite_props()
                self._refresh_canvas()
                self._mark_modified()
        
        elif mode == "draw_rect":
            # 绘制临时矩形
            self.canvas.delete("temp_rect")
            sx, sy = self.drag_start
            self.canvas.create_rectangle(
                sx * self.zoom_level, sy * self.zoom_level,
                img_x * self.zoom_level, img_y * self.zoom_level,
                outline="#00ff00", width=2, dash=(4, 4), tags="temp_rect"
            )
    
    def _on_canvas_release(self, event):
        """画布释放"""
        if self.drag_start is None:
            return
        
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        img_x = x / self.zoom_level
        img_y = y / self.zoom_level
        
        mode = self.mode_var.get()
        
        if mode == "draw_rect":
            # 创建新精灵
            sx, sy = self.drag_start
            x1, y1 = min(sx, img_x), min(sy, img_y)
            x2, y2 = max(sx, img_x), max(sy, img_y)
            w, h = int(x2 - x1), int(y2 - y1)
            
            if w > 4 and h > 4:
                name = self._get_unique_name("sprite")
                self.sprites[name] = EditorSprite(
                    name=name,
                    rect=[int(x1), int(y1), w, h],
                    center=[w / 2, h / 2],
                    radius=0.0,
                    rotate=False
                )
                self.selected_item = name
                self.selected_type = 'sprite'
                self._update_lists()
                self._select_in_list()
                self._update_sprite_props()
                self._mark_modified()
            
            self.canvas.delete("temp_rect")
        
        self.drag_start = None
        self.drag_handle = None
        self._refresh_canvas()
    
    def _on_canvas_motion(self, event):
        """鼠标移动"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        img_x = int(x / self.zoom_level)
        img_y = int(y / self.zoom_level)
        self.coord_label.config(text=f"坐标: ({img_x}, {img_y})")
    
    def _on_canvas_scroll(self, event):
        """鼠标滚轮缩放"""
        if event.delta > 0:
            self._zoom(1.1)
        else:
            self._zoom(0.9)
    
    def _on_canvas_right_click(self, event):
        """右键菜单"""
        menu = tk.Menu(self.master, tearoff=0)
        menu.add_command(label="添加精灵", command=self._add_sprite)
        menu.add_command(label="添加动画", command=self._add_animation)
        if self.selected_item:
            menu.add_separator()
            menu.add_command(label="删除选中", command=self._delete_selected)
            menu.add_command(label="复制选中", command=self._duplicate_selected)
        menu.tk_popup(event.x_root, event.y_root)
    
    def _get_handle_at(self, x: float, y: float) -> Optional[str]:
        """获取点击位置的控制点"""
        if self.selected_type != 'sprite' or self.selected_item not in self.sprites:
            return None
        
        sprite = self.sprites[self.selected_item]
        sx, sy, sw, sh = sprite.rect
        z = self.zoom_level
        
        handles = {
            "nw": (sx, sy), "n": (sx + sw/2, sy), "ne": (sx + sw, sy),
            "w": (sx, sy + sh/2), "e": (sx + sw, sy + sh/2),
            "sw": (sx, sy + sh), "s": (sx + sw/2, sy + sh), "se": (sx + sw, sy + sh)
        }
        
        for handle_name, (hx, hy) in handles.items():
            if abs(x - hx * z) < 6 and abs(y - hy * z) < 6:
                return handle_name
        
        return None
    
    def _resize_with_handle(self, img_x: float, img_y: float):
        """使用控制点调整大小"""
        if self.selected_type != 'sprite' or self.selected_item not in self.sprites:
            return
        
        sprite = self.sprites[self.selected_item]
        sx, sy, sw, sh = sprite.rect
        
        if 'n' in self.drag_handle:
            new_y = int(img_y)
            sprite.rect[3] = sy + sh - new_y
            sprite.rect[1] = new_y
        if 's' in self.drag_handle:
            sprite.rect[3] = int(img_y - sy)
        if 'w' in self.drag_handle:
            new_x = int(img_x)
            sprite.rect[2] = sx + sw - new_x
            sprite.rect[0] = new_x
        if 'e' in self.drag_handle:
            sprite.rect[2] = int(img_x - sx)
        
        # 确保最小尺寸
        sprite.rect[2] = max(sprite.rect[2], 4)
        sprite.rect[3] = max(sprite.rect[3], 4)
        
        self._update_sprite_props()
        self._refresh_canvas()
        self._mark_modified()
    
    def _select_in_list(self):
        """在列表中选中当前项"""
        if self.selected_type == 'sprite':
            self.anim_listbox.selection_clear(0, tk.END)
            for i in range(self.sprite_listbox.size()):
                if self.sprite_listbox.get(i) == self.selected_item:
                    self.sprite_listbox.selection_clear(0, tk.END)
                    self.sprite_listbox.selection_set(i)
                    self.sprite_listbox.see(i)
                    break
        else:
            self.sprite_listbox.selection_clear(0, tk.END)
            for i in range(self.anim_listbox.size()):
                if self.anim_listbox.get(i).startswith(self.selected_item):
                    self.anim_listbox.selection_clear(0, tk.END)
                    self.anim_listbox.selection_set(i)
                    self.anim_listbox.see(i)
                    break
    
    # 属性编辑回调
    def _on_sprite_name_change(self, event=None):
        """精灵名称变更"""
        if self.selected_type != 'sprite' or self.selected_item not in self.sprites:
            return
        
        new_name = self.sprite_name_var.get().strip()
        if not new_name or new_name == self.selected_item:
            return
        
        if new_name in self.sprites:
            messagebox.showwarning("警告", "精灵名称已存在")
            self.sprite_name_var.set(self.selected_item)
            return
        
        sprite = self.sprites.pop(self.selected_item)
        sprite.name = new_name
        self.sprites[new_name] = sprite
        self.selected_item = new_name
        self._update_lists()
        self._select_in_list()
        self._mark_modified()
    
    def _on_rect_change(self, event=None):
        """矩形变更"""
        if self.selected_type != 'sprite' or self.selected_item not in self.sprites:
            return
        
        sprite = self.sprites[self.selected_item]
        sprite.rect = [v.get() for v in self.rect_vars]
        self._refresh_canvas()
        self._mark_modified()
    
    def _on_center_change(self, event=None):
        """中心点变更"""
        if self.selected_type != 'sprite' or self.selected_item not in self.sprites:
            return
        
        sprite = self.sprites[self.selected_item]
        sprite.center = [v.get() for v in self.center_vars]
        self._refresh_canvas()
        self._mark_modified()
    
    def _on_radius_change(self, event=None):
        """半径变更"""
        if self.selected_type != 'sprite' or self.selected_item not in self.sprites:
            return
        
        sprite = self.sprites[self.selected_item]
        sprite.radius = self.radius_var.get()
        self._refresh_canvas()
        self._mark_modified()
    
    def _on_rotate_change(self):
        """旋转变更"""
        if self.selected_type != 'sprite' or self.selected_item not in self.sprites:
            return
        
        sprite = self.sprites[self.selected_item]
        sprite.rotate = self.rotate_var.get()
        self._mark_modified()
    
    def _center_sprite(self):
        """将中心点设为精灵中心"""
        if self.selected_type != 'sprite' or self.selected_item not in self.sprites:
            return
        
        sprite = self.sprites[self.selected_item]
        sprite.center = [sprite.rect[2] / 2, sprite.rect[3] / 2]
        self._update_sprite_props()
        self._refresh_canvas()
        self._mark_modified()
    
    def _on_anim_name_change(self, event=None):
        """动画名称变更"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        new_name = self.anim_name_var.get().strip()
        if not new_name or new_name == self.selected_item:
            return
        
        if new_name in self.animations:
            messagebox.showwarning("警告", "动画名称已存在")
            self.anim_name_var.set(self.selected_item)
            return
        
        anim = self.animations.pop(self.selected_item)
        anim.name = new_name
        self.animations[new_name] = anim
        self.selected_item = new_name
        self._update_lists()
        self._select_in_list()
        self._mark_modified()
    
    def _on_frame_duration_change(self, event=None):
        """帧时长变更"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        anim = self.animations[self.selected_item]
        anim.frame_duration = self.frame_duration_var.get()
        self._mark_modified()
    
    def _on_anim_loop_change(self):
        """循环变更"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        anim = self.animations[self.selected_item]
        anim.loop = self.anim_loop_var.get()
        self._mark_modified()
    
    def _on_frame_select(self, event):
        """帧选择"""
        selection = self.frame_listbox.curselection()
        if selection:
            self.current_frame_index = selection[0]
            self._update_preview()
            self._update_frame_info()
            self._refresh_canvas()
    
    def _add_frame(self):
        """添加帧"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            messagebox.showinfo("提示", "请先选择一个动画")
            return
        
        anim = self.animations[self.selected_item]
        
        # 默认使用上一帧的位置偏移
        if anim.frames:
            last = anim.frames[-1]
            new_rect = [last.rect[0] + last.rect[2], last.rect[1], last.rect[2], last.rect[3]]
        else:
            new_rect = [0, 0, 32, 32]
        
        anim.frames.append(EditorAnimationFrame(rect=new_rect))
        self._update_animation_props()
        self._refresh_canvas()
        self._mark_modified()
    
    def _delete_frame(self):
        """删除帧"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        selection = self.frame_listbox.curselection()
        if not selection:
            return
        
        anim = self.animations[self.selected_item]
        del anim.frames[selection[0]]
        self.current_frame_index = max(0, min(self.current_frame_index, len(anim.frames) - 1))
        self._update_animation_props()
        self._refresh_canvas()
        self._mark_modified()
    
    def _move_frame_up(self):
        """上移帧"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        selection = self.frame_listbox.curselection()
        if not selection or selection[0] == 0:
            return
        
        anim = self.animations[self.selected_item]
        idx = selection[0]
        anim.frames[idx], anim.frames[idx - 1] = anim.frames[idx - 1], anim.frames[idx]
        self.current_frame_index = idx - 1
        self._update_animation_props()
        self.frame_listbox.selection_set(idx - 1)
        self._mark_modified()
    
    def _move_frame_down(self):
        """下移帧"""
        if self.selected_type != 'animation' or self.selected_item not in self.animations:
            return
        
        selection = self.frame_listbox.curselection()
        anim = self.animations[self.selected_item]
        if not selection or selection[0] >= len(anim.frames) - 1:
            return
        
        idx = selection[0]
        anim.frames[idx], anim.frames[idx + 1] = anim.frames[idx + 1], anim.frames[idx]
        self.current_frame_index = idx + 1
        self._update_animation_props()
        self.frame_listbox.selection_set(idx + 1)
        self._mark_modified()
    
    # 工具栏回调
    def _on_mode_change(self):
        """模式变更"""
        self.editing_mode = self.mode_var.get()
    
    def _zoom(self, factor: float):
        """缩放"""
        self.zoom_level = max(0.1, min(10, self.zoom_level * factor))
        self._update_texture_photo()
        self._refresh_canvas()
    
    def _fit_view(self):
        """适应视图"""
        if self.texture_image is None:
            return
        
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        img_w = self.texture_image.width
        img_h = self.texture_image.height
        
        self.zoom_level = min(canvas_w / img_w, canvas_h / img_h) * 0.9
        self._update_texture_photo()
        self._refresh_canvas()
    
    def _reset_zoom(self):
        """重置缩放"""
        self.zoom_level = 1.0
        self._update_texture_photo()
        self._refresh_canvas()
    
    # 菜单回调
    def _new_config(self):
        """新建配置"""
        if self.is_modified:
            if not self._confirm_discard():
                return
        
        self.current_file = None
        self.config_data = {
            "version": "2.0",
            "description": "",
            "texture": "",
            "sprites": {},
            "animations": {}
        }
        self.sprites.clear()
        self.animations.clear()
        self.texture_image = None
        self.texture_photo = None
        self.selected_item = None
        self.selected_type = None
        self.is_modified = False
        
        self._update_lists()
        self._update_title()
        self._refresh_canvas()
    
    def _open_config(self):
        """打开配置"""
        if self.is_modified:
            if not self._confirm_discard():
                return
        
        path = filedialog.askopenfilename(
            title="打开配置文件",
            initialdir=ASSETS_ROOT,
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if path:
            self._load_config(path)
    
    def _save_config(self):
        """保存配置"""
        if self.current_file is None:
            self._save_config_as()
            return
        
        self._save_to_file(self.current_file)
    
    def _save_config_as(self):
        """另存为"""
        path = filedialog.asksaveasfilename(
            title="保存配置文件",
            initialdir=ASSETS_ROOT,
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")]
        )
        if path:
            self._save_to_file(path)
            self.current_file = path
            self._update_title()
    
    def _save_to_file(self, path: str):
        """保存到文件"""
        # 构建配置数据
        config = {
            "version": "2.0",
            "description": self.config_data.get("description", ""),
            "texture": self.config_data.get("texture", ""),
            "sprites": {},
            "animations": {}
        }
        
        for name, sprite in self.sprites.items():
            config["sprites"][name] = sprite.to_dict()
        
        for name, anim in self.animations.items():
            config["animations"][name] = anim.to_dict()
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self.is_modified = False
            self._update_title()
            self._set_status(f"已保存: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败:\n{e}")
    
    def _load_texture(self):
        """加载纹理"""
        path = filedialog.askopenfilename(
            title="选择纹理图片",
            initialdir=ASSETS_ROOT,
            filetypes=[("图片文件", "*.png;*.jpg;*.jpeg;*.bmp"), ("所有文件", "*.*")]
        )
        if path:
            self._load_texture_file(path)
            
            # 更新配置中的纹理路径
            if self.current_file:
                rel_path = os.path.relpath(path, os.path.dirname(self.current_file))
                self.config_data['texture'] = rel_path
            else:
                self.config_data['texture'] = os.path.basename(path)
            
            self._refresh_canvas()
            self._mark_modified()
    
    def _add_sprite(self):
        """添加精灵"""
        name = self._get_unique_name("sprite")
        self.sprites[name] = EditorSprite(
            name=name,
            rect=[0, 0, 32, 32],
            center=[16, 16],
            radius=0.0,
            rotate=False
        )
        self.selected_item = name
        self.selected_type = 'sprite'
        self._update_lists()
        self._select_in_list()
        self._update_sprite_props()
        self._refresh_canvas()
        self._mark_modified()
    
    def _add_animation(self):
        """添加动画"""
        name = self._get_unique_name("animation")
        self.animations[name] = EditorAnimation(
            name=name,
            frames=[EditorAnimationFrame(rect=[0, 0, 32, 32])],
            center=[16, 16],
            radius=0.0,
            rotate=False,
            frame_duration=0.1,
            loop=True
        )
        self.selected_item = name
        self.selected_type = 'animation'
        self.current_frame_index = 0
        self._update_lists()
        self._select_in_list()
        self._update_animation_props()
        self._refresh_canvas()
        self._mark_modified()
    
    def _delete_selected(self):
        """删除选中项"""
        if not self.selected_item:
            return
        
        if self.selected_type == 'sprite':
            self._delete_item('sprite')
        else:
            self._delete_item('animation')
    
    def _delete_item(self, item_type: str):
        """删除项"""
        if item_type == 'sprite':
            selection = self.sprite_listbox.curselection()
            if not selection:
                return
            name = self.sprite_listbox.get(selection[0])
            if messagebox.askyesno("确认", f"确定删除精灵 '{name}'?"):
                del self.sprites[name]
                if self.selected_item == name:
                    self.selected_item = None
                    self.selected_type = None
        else:
            selection = self.anim_listbox.curselection()
            if not selection:
                return
            text = self.anim_listbox.get(selection[0])
            name = text.split(' (')[0]
            if messagebox.askyesno("确认", f"确定删除动画 '{name}'?"):
                del self.animations[name]
                if self.selected_item == name:
                    self.selected_item = None
                    self.selected_type = None
        
        self._update_lists()
        self._refresh_canvas()
        self._mark_modified()
    
    def _duplicate_selected(self):
        """复制选中项"""
        if not self.selected_item:
            return
        
        if self.selected_type == 'sprite' and self.selected_item in self.sprites:
            src = self.sprites[self.selected_item]
            new_name = self._get_unique_name(src.name)
            self.sprites[new_name] = EditorSprite(
                name=new_name,
                rect=src.rect.copy(),
                center=src.center.copy(),
                radius=src.radius,
                rotate=src.rotate,
                scale=src.scale.copy(),
                metadata=src.metadata.copy()
            )
            self.selected_item = new_name
        
        elif self.selected_type == 'animation' and self.selected_item in self.animations:
            src = self.animations[self.selected_item]
            new_name = self._get_unique_name(src.name)
            self.animations[new_name] = EditorAnimation(
                name=new_name,
                frames=[EditorAnimationFrame(rect=f.rect.copy(), center=f.center.copy() if f.center else None) 
                        for f in src.frames],
                center=src.center.copy(),
                radius=src.radius,
                rotate=src.rotate,
                frame_duration=src.frame_duration,
                loop=src.loop,
                metadata=src.metadata.copy()
            )
            self.selected_item = new_name
        
        self._update_lists()
        self._select_in_list()
        self._refresh_canvas()
        self._mark_modified()
    
    def _get_unique_name(self, base: str) -> str:
        """获取唯一名称"""
        existing = set(self.sprites.keys()) | set(self.animations.keys())
        if base not in existing:
            return base
        
        i = 1
        while f"{base}_{i}" in existing:
            i += 1
        return f"{base}_{i}"
    
    def _mark_modified(self):
        """标记已修改"""
        self.is_modified = True
        self._update_title()
    
    def _update_title(self):
        """更新窗口标题"""
        title = "纹理资产编辑器"
        if self.current_file:
            title += f" - {os.path.basename(self.current_file)}"
        if self.is_modified:
            title += " *"
        self.master.title(title)
    
    def _set_status(self, text: str):
        """设置状态栏"""
        self.status_label.config(text=text)
    
    def _confirm_discard(self) -> bool:
        """确认丢弃修改"""
        return messagebox.askyesno("未保存的更改", "有未保存的更改，确定丢弃吗？")
    
    def _on_close(self):
        """关闭窗口"""
        if self.is_modified:
            result = messagebox.askyesnocancel("保存", "是否保存更改？")
            if result is None:
                return
            if result:
                self._save_config()
        self.master.destroy()


def main():
    root = tk.Tk()
    app = TextureAssetEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
