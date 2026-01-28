"""
精灵图切分工具
专门处理按行排列的动画精灵图
支持每行不同帧数的切分
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
from PIL import Image, ImageTk, ImageDraw


class SpriteSheetCutter:
    """精灵图切分工具"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("精灵图切分工具")
        self.root.geometry("1400x900")
        
        # 图像数据
        self.image = None
        self.image_path = None
        self.photo = None
        self.display_image = None
        
        # 切分数据
        self.rows = []  # [(y_start, height, frame_count, anim_name), ...]
        self.sprites = {}  # sprite_id -> (x, y, w, h)
        
        # 显示设置
        self.zoom = 1.0
        self.show_grid = tk.BooleanVar(value=True)
        self.show_frames = tk.BooleanVar(value=True)
        
        # 当前编辑状态
        self.current_row_idx = -1
        self.dragging = False
        self.drag_start_y = 0
        
        # 动画预览状态
        self.preview_frames = []  # 当前预览的帧图像列表
        self.preview_frame_idx = 0
        self.preview_playing = False
        self.preview_timer = None
        self.preview_photo = None
        self.preview_fps_var = None
        self.preview_zoom_var = None
        
        # 判定圈显示
        self.show_hitbox = tk.BooleanVar(value=False)
        self.hitbox_radius_var = None
        self.graze_radius_var = None
        
        self._create_ui()
    
    def _create_ui(self):
        """创建UI"""
        # 工具栏
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="打开图像", command=self._open_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="保存配置", command=self._save_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="加载配置", command=self._load_config).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        
        ttk.Checkbutton(toolbar, text="显示网格", variable=self.show_grid, 
                        command=self._refresh_canvas).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(toolbar, text="显示帧", variable=self.show_frames,
                        command=self._refresh_canvas).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(toolbar, text="缩放:").pack(side=tk.LEFT, padx=(20, 5))
        self.zoom_var = tk.StringVar(value="100%")
        zoom_combo = ttk.Combobox(toolbar, textvariable=self.zoom_var, 
                                   values=["50%", "100%", "150%", "200%", "300%"], width=6)
        zoom_combo.pack(side=tk.LEFT)
        zoom_combo.bind('<<ComboboxSelected>>', self._on_zoom_change)
        
        # 主区域
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左侧：Canvas
        canvas_frame = ttk.Frame(main_paned)
        main_paned.add(canvas_frame, weight=3)
        
        # Canvas + 滚动条
        canvas_container = ttk.Frame(canvas_frame)
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        self.h_scroll = ttk.Scrollbar(canvas_container, orient=tk.HORIZONTAL)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.v_scroll = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.canvas = tk.Canvas(canvas_container, bg='#2a2a2a',
                                xscrollcommand=self.h_scroll.set,
                                yscrollcommand=self.v_scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.h_scroll.config(command=self.canvas.xview)
        self.v_scroll.config(command=self.canvas.yview)
        
        # 绑定事件
        self.canvas.bind('<Button-1>', self._on_canvas_click)
        self.canvas.bind('<B1-Motion>', self._on_canvas_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_canvas_release)
        self.canvas.bind('<MouseWheel>', self._on_mouse_wheel)
        
        # 右侧：配置面板（可滚动）
        right_frame = ttk.Frame(main_paned, width=380)
        main_paned.add(right_frame, weight=1)
        
        # 创建滚动容器
        right_canvas = tk.Canvas(right_frame, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=right_canvas.yview)
        self.config_inner_frame = ttk.Frame(right_canvas)
        
        self.config_inner_frame.bind(
            "<Configure>",
            lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        )
        
        right_canvas.create_window((0, 0), window=self.config_inner_frame, anchor="nw")
        right_canvas.configure(yscrollcommand=right_scrollbar.set)
        
        right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 保存引用以便后续使用
        self.right_canvas = right_canvas
        
        self._create_config_panel(self.config_inner_frame)
    
    def _create_config_panel(self, parent):
        """创建配置面板"""
        # 快速设置
        quick_frame = ttk.LabelFrame(parent, text="快速设置", padding=5)
        quick_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(quick_frame, text="统一帧高度:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.uniform_height_var = tk.IntVar(value=48)
        ttk.Spinbox(quick_frame, textvariable=self.uniform_height_var, 
                    from_=16, to=256, width=6).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(quick_frame, text="统一帧宽度:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.uniform_width_var = tk.IntVar(value=32)
        ttk.Spinbox(quick_frame, textvariable=self.uniform_width_var,
                    from_=16, to=256, width=6).grid(row=1, column=1, sticky=tk.W)
        
        ttk.Button(quick_frame, text="自动检测行", 
                   command=self._auto_detect_rows).grid(row=2, column=0, columnspan=2, pady=5)
        ttk.Button(quick_frame, text="按统一大小切分全图",
                   command=self._uniform_cut).grid(row=3, column=0, columnspan=2, pady=2)
        
        # 行列表
        row_frame = ttk.LabelFrame(parent, text="动画行", padding=5)
        row_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 列表
        self.row_tree = ttk.Treeview(row_frame, columns=('y', 'height', 'frames', 'name'),
                                      show='headings', height=8)
        self.row_tree.heading('y', text='Y')
        self.row_tree.heading('height', text='高度')
        self.row_tree.heading('frames', text='帧数')
        self.row_tree.heading('name', text='动画名')
        
        self.row_tree.column('y', width=40)
        self.row_tree.column('height', width=50)
        self.row_tree.column('frames', width=40)
        self.row_tree.column('name', width=100)
        
        self.row_tree.pack(fill=tk.BOTH, expand=True)
        self.row_tree.bind('<<TreeviewSelect>>', self._on_row_select)
        
        # 行操作按钮
        btn_frame = ttk.Frame(row_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加行", command=self._add_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除行", command=self._delete_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="上移", command=lambda: self._move_row(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="下移", command=lambda: self._move_row(1)).pack(side=tk.LEFT, padx=2)
        
        # 行编辑
        edit_frame = ttk.LabelFrame(parent, text="编辑选中行", padding=5)
        edit_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Y起始:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.row_y_var = tk.IntVar(value=0)
        ttk.Spinbox(edit_frame, textvariable=self.row_y_var, from_=0, to=2048, width=6).grid(row=0, column=1)
        
        ttk.Label(edit_frame, text="高度:").grid(row=0, column=2, sticky=tk.W, pady=2, padx=(10,0))
        self.row_h_var = tk.IntVar(value=48)
        ttk.Spinbox(edit_frame, textvariable=self.row_h_var, from_=1, to=512, width=6).grid(row=0, column=3)
        
        ttk.Label(edit_frame, text="帧数:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.row_frames_var = tk.IntVar(value=4)
        ttk.Spinbox(edit_frame, textvariable=self.row_frames_var, from_=1, to=32, width=6).grid(row=1, column=1)
        
        ttk.Label(edit_frame, text="帧宽:").grid(row=1, column=2, sticky=tk.W, pady=2, padx=(10,0))
        self.row_fw_var = tk.IntVar(value=32)
        ttk.Spinbox(edit_frame, textvariable=self.row_fw_var, from_=1, to=512, width=6).grid(row=1, column=3)
        
        ttk.Label(edit_frame, text="动画名:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.row_name_var = tk.StringVar(value="idle")
        ttk.Entry(edit_frame, textvariable=self.row_name_var, width=15).grid(row=2, column=1, columnspan=3, sticky=tk.W)
        
        ttk.Label(edit_frame, text="前缀:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.row_prefix_var = tk.StringVar(value="reimu")
        ttk.Entry(edit_frame, textvariable=self.row_prefix_var, width=15).grid(row=3, column=1, columnspan=3, sticky=tk.W)
        
        ttk.Button(edit_frame, text="应用更改", command=self._apply_row_changes).grid(row=4, column=0, columnspan=4, pady=5)
        
        # 预设动画名
        preset_frame = ttk.LabelFrame(parent, text="预设动画名", padding=5)
        preset_frame.pack(fill=tk.X, padx=5, pady=5)
        
        presets = [("idle", "idle"), ("左移", "move_left"), ("右移", "move_right"),
                   ("左移(满)", "move_left_full"), ("右移(满)", "move_right_full")]
        
        for i, (label, name) in enumerate(presets):
            ttk.Button(preset_frame, text=label, width=8,
                       command=lambda n=name: self.row_name_var.set(n)).grid(row=i//3, column=i%3, padx=2, pady=2)
        
        # 生成按钮
        gen_frame = ttk.Frame(parent)
        gen_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(gen_frame, text="生成精灵配置", 
                   command=self._generate_sprites).pack(fill=tk.X, pady=2)
        ttk.Button(gen_frame, text="生成动画配置",
                   command=self._generate_animations).pack(fill=tk.X, pady=2)
        ttk.Button(gen_frame, text="导出完整配置 (精灵+动画)",
                   command=self._export_full_config).pack(fill=tk.X, pady=2)
        
        # 动画预览区域
        self._create_preview_panel(parent)
    
    def _create_preview_panel(self, parent):
        """创建动画预览面板"""
        preview_frame = ttk.LabelFrame(parent, text="动画预览", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 预览Canvas（带背景色）
        canvas_container = ttk.Frame(preview_frame)
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        self.preview_canvas = tk.Canvas(canvas_container, bg='#1a1a2e', 
                                         width=150, height=150)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 帧信息
        self.preview_info_var = tk.StringVar(value="选择一行来预览动画")
        ttk.Label(preview_frame, textvariable=self.preview_info_var).pack()
        
        # 控制按钮
        ctrl_frame = ttk.Frame(preview_frame)
        ctrl_frame.pack(fill=tk.X, pady=5)
        
        self.play_btn_text = tk.StringVar(value="▶ 播放")
        ttk.Button(ctrl_frame, textvariable=self.play_btn_text, width=8,
                   command=self._toggle_preview_play).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame, text="◀", width=3,
                   command=self._preview_prev_frame).pack(side=tk.LEFT, padx=1)
        ttk.Button(ctrl_frame, text="▶", width=3,
                   command=self._preview_next_frame).pack(side=tk.LEFT, padx=1)
        ttk.Button(ctrl_frame, text="⟳", width=3,
                   command=self._reload_preview).pack(side=tk.LEFT, padx=1)
        
        # FPS和缩放设置
        settings_frame = ttk.Frame(preview_frame)
        settings_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(settings_frame, text="FPS:").pack(side=tk.LEFT)
        self.preview_fps_var = tk.IntVar(value=8)
        fps_spin = ttk.Spinbox(settings_frame, textvariable=self.preview_fps_var,
                                from_=1, to=60, width=4)
        fps_spin.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(settings_frame, text="缩放:").pack(side=tk.LEFT, padx=(10, 0))
        self.preview_zoom_var = tk.DoubleVar(value=2.0)
        zoom_spin = ttk.Spinbox(settings_frame, textvariable=self.preview_zoom_var,
                                 from_=0.5, to=8.0, increment=0.5, width=4)
        zoom_spin.pack(side=tk.LEFT, padx=2)
        zoom_spin.bind('<Return>', lambda e: self._refresh_preview_frame())
        
        # 背景色选择
        bg_frame = ttk.Frame(preview_frame)
        bg_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(bg_frame, text="背景:").pack(side=tk.LEFT)
        self.preview_bg_var = tk.StringVar(value="#1a1a2e")
        
        bg_colors = [("#1a1a2e", "深蓝"), ("#000000", "黑"), ("#ffffff", "白"), 
                     ("#ff00ff", "粉"), ("#00ff00", "绿")]
        for color, name in bg_colors:
            ttk.Button(bg_frame, text=name, width=3,
                       command=lambda c=color: self._set_preview_bg(c)).pack(side=tk.LEFT, padx=1)
        
        # 判定圈显示设置
        hitbox_frame = ttk.LabelFrame(preview_frame, text="判定圈", padding=3)
        hitbox_frame.pack(fill=tk.X, pady=5)
        
        # 显示开关
        hitbox_toggle = ttk.Frame(hitbox_frame)
        hitbox_toggle.pack(fill=tk.X)
        
        ttk.Checkbutton(hitbox_toggle, text="显示判定圈", variable=self.show_hitbox,
                        command=self._refresh_preview_frame).pack(side=tk.LEFT)
        
        # 半径设置
        radius_frame = ttk.Frame(hitbox_frame)
        radius_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(radius_frame, text="判定:").pack(side=tk.LEFT)
        self.hitbox_radius_var = tk.DoubleVar(value=3.0)
        hitbox_spin = ttk.Spinbox(radius_frame, textvariable=self.hitbox_radius_var,
                                   from_=0.5, to=20.0, increment=0.5, width=5)
        hitbox_spin.pack(side=tk.LEFT, padx=2)
        hitbox_spin.bind('<Return>', lambda e: self._refresh_preview_frame())
        hitbox_spin.bind('<<Increment>>', lambda e: self.root.after(10, self._refresh_preview_frame))
        hitbox_spin.bind('<<Decrement>>', lambda e: self.root.after(10, self._refresh_preview_frame))
        
        ttk.Label(radius_frame, text="擦弹:").pack(side=tk.LEFT, padx=(10, 0))
        self.graze_radius_var = tk.DoubleVar(value=24.0)
        graze_spin = ttk.Spinbox(radius_frame, textvariable=self.graze_radius_var,
                                  from_=1, to=50.0, increment=1, width=5)
        graze_spin.pack(side=tk.LEFT, padx=2)
        graze_spin.bind('<Return>', lambda e: self._refresh_preview_frame())
        graze_spin.bind('<<Increment>>', lambda e: self.root.after(10, self._refresh_preview_frame))
        graze_spin.bind('<<Decrement>>', lambda e: self.root.after(10, self._refresh_preview_frame))
    
    def _set_preview_bg(self, color):
        """设置预览背景色"""
        self.preview_bg_var.set(color)
        self.preview_canvas.config(bg=color)
        self._refresh_preview_frame()
    
    def _load_preview_for_row(self, row_idx):
        """为指定行加载预览帧"""
        if self.image is None or row_idx < 0 or row_idx >= len(self.rows):
            self.preview_frames = []
            return
        
        row = self.rows[row_idx]
        y_start, height, frame_count, anim_name, frame_width = row
        
        # 限制最大帧数，防止卡死
        max_frames = min(frame_count, 100)
        
        self.preview_frames = []
        
        for f in range(max_frames):
            x = f * frame_width
            # 裁剪帧
            frame_img = self.image.crop((x, y_start, x + frame_width, y_start + height))
            self.preview_frames.append(frame_img)
        
        self.preview_frame_idx = 0
        self._refresh_preview_frame()
        
        if frame_count > max_frames:
            self.preview_info_var.set(f"{anim_name}: {max_frames}/{frame_count} 帧(已限制)")
        else:
            self.preview_info_var.set(f"{anim_name}: {frame_count} 帧")
    
    def _refresh_preview_frame(self):
        """刷新预览当前帧"""
        self.preview_canvas.delete('all')
        
        if not self.preview_frames:
            self.preview_canvas.create_text(
                75, 75, text="无预览", fill='#666666'
            )
            return
        
        # 获取当前帧
        frame = self.preview_frames[self.preview_frame_idx]
        
        # 缩放
        zoom = self.preview_zoom_var.get() if self.preview_zoom_var else 2.0
        new_w = int(frame.width * zoom)
        new_h = int(frame.height * zoom)
        
        scaled = frame.resize((new_w, new_h), Image.NEAREST)
        self.preview_photo = ImageTk.PhotoImage(scaled)
        
        # 居中显示
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        if canvas_w < 10:
            canvas_w = 150
        if canvas_h < 10:
            canvas_h = 150
        
        x = canvas_w // 2
        y = canvas_h // 2
        
        self.preview_canvas.create_image(x, y, image=self.preview_photo)
        
        # 绘制判定圈
        if self.show_hitbox.get():
            # 获取半径（乘以缩放）
            hitbox_r = self.hitbox_radius_var.get() * zoom
            graze_r = self.graze_radius_var.get() * zoom
            
            # 擦弹圈（蓝色，较大）
            self.preview_canvas.create_oval(
                x - graze_r, y - graze_r,
                x + graze_r, y + graze_r,
                outline='#00aaff', width=2, dash=(4, 2)
            )
            
            # 判定点（红色，较小）
            self.preview_canvas.create_oval(
                x - hitbox_r, y - hitbox_r,
                x + hitbox_r, y + hitbox_r,
                outline='#ff3333', width=2, fill='#ff333366'
            )
            
            # 中心点
            self.preview_canvas.create_oval(
                x - 2, y - 2, x + 2, y + 2,
                fill='#ffffff', outline='#ffffff'
            )
        
        # 更新帧信息
        total = len(self.preview_frames)
        current = self.preview_frame_idx + 1
        
        if self.current_row_idx >= 0 and self.current_row_idx < len(self.rows):
            anim_name = self.rows[self.current_row_idx][3]
            self.preview_info_var.set(f"{anim_name}: {current}/{total}")
    
    def _toggle_preview_play(self):
        """切换预览播放状态"""
        if self.preview_playing:
            self._stop_preview()
        else:
            self._start_preview()
    
    def _start_preview(self):
        """开始预览播放"""
        if not self.preview_frames:
            return
        
        self.preview_playing = True
        self.play_btn_text.set("⏸ 暂停")
        self._play_next_preview_frame()
    
    def _stop_preview(self):
        """停止预览播放"""
        self.preview_playing = False
        self.play_btn_text.set("▶ 播放")
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
            self.preview_timer = None
    
    def _play_next_preview_frame(self):
        """播放下一预览帧"""
        if not self.preview_playing or not self.preview_frames:
            return
        
        self.preview_frame_idx = (self.preview_frame_idx + 1) % len(self.preview_frames)
        self._refresh_preview_frame()
        
        # 计算延迟
        fps = self.preview_fps_var.get() if self.preview_fps_var else 8
        delay = max(16, int(1000 / fps))
        
        self.preview_timer = self.root.after(delay, self._play_next_preview_frame)
    
    def _preview_prev_frame(self):
        """预览上一帧"""
        if self.preview_frames:
            self.preview_frame_idx = (self.preview_frame_idx - 1) % len(self.preview_frames)
            self._refresh_preview_frame()
    
    def _preview_next_frame(self):
        """预览下一帧"""
        if self.preview_frames:
            self.preview_frame_idx = (self.preview_frame_idx + 1) % len(self.preview_frames)
            self._refresh_preview_frame()
    
    def _reload_preview(self):
        """重新加载预览"""
        if self.current_row_idx >= 0:
            self._load_preview_for_row(self.current_row_idx)

    def _open_image(self):
        """打开图像"""
        path = filedialog.askopenfilename(
            title="选择精灵图",
            filetypes=[("图片文件", "*.png;*.jpg;*.bmp"), ("所有文件", "*.*")]
        )
        
        if path:
            try:
                self.image = Image.open(path).convert('RGBA')
                self.image_path = path
                self.rows.clear()
                self._refresh_canvas()
                
                # 更新窗口标题
                self.root.title(f"精灵图切分工具 - {os.path.basename(path)}")
                
                # 设置默认值
                w, h = self.image.size
                self.uniform_height_var.set(min(48, h))
                self.uniform_width_var.set(min(32, w))
                
            except Exception as e:
                messagebox.showerror("错误", f"无法打开图像: {e}")
    
    def _on_zoom_change(self, event=None):
        """缩放改变"""
        zoom_str = self.zoom_var.get()
        self.zoom = int(zoom_str.replace('%', '')) / 100
        self._refresh_canvas()
    
    def _refresh_canvas(self):
        """刷新Canvas"""
        self.canvas.delete('all')
        
        if self.image is None:
            return
        
        # 缩放图像
        w, h = self.image.size
        new_w = int(w * self.zoom)
        new_h = int(h * self.zoom)
        
        # 创建显示图像
        self.display_image = self.image.resize((new_w, new_h), Image.NEAREST)
        
        # 绘制网格和帧
        if self.show_grid.get() or self.show_frames.get():
            draw_image = self.display_image.copy()
            draw = ImageDraw.Draw(draw_image)
            
            # 绘制行分隔线和帧
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8']
            
            for i, row in enumerate(self.rows):
                y_start, height, frame_count, anim_name, frame_width = row
                color = colors[i % len(colors)]
                
                y1 = int(y_start * self.zoom)
                y2 = int((y_start + height) * self.zoom)
                
                if self.show_grid.get():
                    # 行边界
                    draw.line([(0, y1), (new_w, y1)], fill=color, width=2)
                    draw.line([(0, y2), (new_w, y2)], fill=color, width=2)
                
                if self.show_frames.get():
                    # 帧分隔
                    for f in range(frame_count + 1):
                        x = int(f * frame_width * self.zoom)
                        if x <= new_w:
                            draw.line([(x, y1), (x, y2)], fill=color, width=1)
                    
                    # 动画名标签
                    draw.text((5, y1 + 2), f"{anim_name} ({frame_count}帧)", fill=color)
            
            self.display_image = draw_image
        
        self.photo = ImageTk.PhotoImage(self.display_image)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        
        # 更新滚动区域
        self.canvas.config(scrollregion=(0, 0, new_w, new_h))
    
    def _on_canvas_click(self, event):
        """Canvas点击"""
        if self.image is None:
            return
        
        # 转换为画布坐标
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        
        # 转换为图像坐标
        img_y = int(y / self.zoom)
        
        # 检查是否点击了某行的边界（用于拖动调整）
        for i, row in enumerate(self.rows):
            y_start, height, _, _, _ = row
            y_end = y_start + height
            
            # 检查是否在行的底边附近
            if abs(img_y - y_end) < 5:
                self.dragging = True
                self.current_row_idx = i
                self.drag_start_y = img_y
                return
        
        # 如果没有点击边界，尝试选中该行
        for i, row in enumerate(self.rows):
            y_start, height, _, _, _ = row
            if y_start <= img_y < y_start + height:
                self._select_row(i)
                return
    
    def _on_canvas_drag(self, event):
        """Canvas拖动"""
        if not self.dragging or self.current_row_idx < 0:
            return
        
        y = self.canvas.canvasy(event.y)
        img_y = int(y / self.zoom)
        
        # 调整行高度
        row = list(self.rows[self.current_row_idx])
        new_height = max(16, img_y - row[0])
        row[1] = new_height
        self.rows[self.current_row_idx] = tuple(row)
        
        self._refresh_canvas()
        self._refresh_row_list()
    
    def _on_canvas_release(self, event):
        """Canvas释放"""
        self.dragging = False
    
    def _on_mouse_wheel(self, event):
        """鼠标滚轮"""
        # Ctrl+滚轮缩放
        if event.state & 0x4:  # Ctrl
            if event.delta > 0:
                self.zoom = min(4.0, self.zoom * 1.2)
            else:
                self.zoom = max(0.25, self.zoom / 1.2)
            self.zoom_var.set(f"{int(self.zoom * 100)}%")
            self._refresh_canvas()
        else:
            # 普通滚动
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def _auto_detect_rows(self):
        """自动检测行"""
        if self.image is None:
            messagebox.showwarning("警告", "请先打开图像")
            return
        
        # 简单的行检测：检查每行是否有非透明像素
        w, h = self.image.size
        pixels = self.image.load()
        
        row_height = self.uniform_height_var.get()
        frame_width = self.uniform_width_var.get()
        
        self.rows.clear()
        
        y = 0
        row_idx = 0
        anim_names = ['idle', 'move_left', 'move_right', 'move_left_full', 'move_right_full']
        
        while y < h:
            # 检测这一行的实际内容宽度
            max_x = 0
            has_content = False
            
            for check_y in range(y, min(y + row_height, h)):
                for x in range(w - 1, -1, -1):
                    pixel = pixels[x, check_y]
                    if len(pixel) >= 4 and pixel[3] > 10:  # 有非透明内容
                        max_x = max(max_x, x)
                        has_content = True
                        break
            
            if has_content and max_x > 0:
                # 估算帧数
                frame_count = max(1, (max_x + frame_width) // frame_width)
                anim_name = anim_names[row_idx % len(anim_names)] if row_idx < len(anim_names) else f"anim_{row_idx}"
                
                self.rows.append((y, row_height, frame_count, anim_name, frame_width))
                row_idx += 1
            
            y += row_height
        
        self._refresh_row_list()
        self._refresh_canvas()
        
        messagebox.showinfo("完成", f"检测到 {len(self.rows)} 行动画")
    
    def _uniform_cut(self):
        """按统一大小切分"""
        if self.image is None:
            messagebox.showwarning("警告", "请先打开图像")
            return
        
        w, h = self.image.size
        row_height = self.uniform_height_var.get()
        frame_width = self.uniform_width_var.get()
        
        self.rows.clear()
        
        anim_names = ['idle', 'move_left', 'move_right', 'move_left_full', 'move_right_full']
        
        y = 0
        row_idx = 0
        while y + row_height <= h:
            frame_count = w // frame_width
            anim_name = anim_names[row_idx] if row_idx < len(anim_names) else f"anim_{row_idx}"
            
            self.rows.append((y, row_height, frame_count, anim_name, frame_width))
            y += row_height
            row_idx += 1
        
        self._refresh_row_list()
        self._refresh_canvas()
    
    def _refresh_row_list(self):
        """刷新行列表"""
        for item in self.row_tree.get_children():
            self.row_tree.delete(item)
        
        for i, row in enumerate(self.rows):
            y_start, height, frame_count, anim_name, frame_width = row
            self.row_tree.insert('', 'end', iid=str(i), values=(y_start, height, frame_count, anim_name))
    
    def _on_row_select(self, event):
        """行选择事件"""
        selection = self.row_tree.selection()
        if not selection:
            return
        
        idx = int(selection[0])
        # 如果已经是当前选中的行，不重复处理
        if idx == self.current_row_idx:
            return
        self._select_row(idx)
    
    def _select_row(self, idx):
        """选中行"""
        if idx < 0 or idx >= len(self.rows):
            return
        
        self.current_row_idx = idx
        row = self.rows[idx]
        
        self.row_y_var.set(row[0])
        self.row_h_var.set(row[1])
        self.row_frames_var.set(row[2])
        self.row_name_var.set(row[3])
        self.row_fw_var.set(row[4])
        
        # 高亮选中（不触发事件，因为已经设置了current_row_idx）
        current_selection = self.row_tree.selection()
        if not current_selection or int(current_selection[0]) != idx:
            self.row_tree.selection_set(str(idx))
        
        # 加载动画预览
        self._load_preview_for_row(idx)
    
    def _add_row(self):
        """添加行"""
        if self.image is None:
            return
        
        # 计算新行的Y位置
        if self.rows:
            last_row = self.rows[-1]
            y_start = last_row[0] + last_row[1]
        else:
            y_start = 0
        
        height = self.uniform_height_var.get()
        frame_width = self.uniform_width_var.get()
        frame_count = self.image.size[0] // frame_width
        
        self.rows.append((y_start, height, frame_count, f"anim_{len(self.rows)}", frame_width))
        self._refresh_row_list()
        self._refresh_canvas()
    
    def _delete_row(self):
        """删除行"""
        selection = self.row_tree.selection()
        if not selection:
            return
        
        idx = int(selection[0])
        if 0 <= idx < len(self.rows):
            del self.rows[idx]
            self._refresh_row_list()
            self._refresh_canvas()
    
    def _move_row(self, direction):
        """移动行"""
        selection = self.row_tree.selection()
        if not selection:
            return
        
        idx = int(selection[0])
        new_idx = idx + direction
        
        if 0 <= new_idx < len(self.rows):
            self.rows[idx], self.rows[new_idx] = self.rows[new_idx], self.rows[idx]
            self._refresh_row_list()
            self.row_tree.selection_set(str(new_idx))
    
    def _apply_row_changes(self):
        """应用行更改"""
        if self.current_row_idx < 0 or self.current_row_idx >= len(self.rows):
            return
        
        self.rows[self.current_row_idx] = (
            self.row_y_var.get(),
            self.row_h_var.get(),
            self.row_frames_var.get(),
            self.row_name_var.get(),
            self.row_fw_var.get()
        )
        
        self._refresh_row_list()
        self._refresh_canvas()
        
        # 刷新预览
        self._load_preview_for_row(self.current_row_idx)
    
    def _generate_sprites(self):
        """生成精灵配置"""
        if not self.rows:
            messagebox.showwarning("警告", "请先添加行配置")
            return
        
        prefix = self.row_prefix_var.get()
        self.sprites.clear()
        
        for row in self.rows:
            y_start, height, frame_count, anim_name, frame_width = row
            
            for f in range(frame_count):
                sprite_id = f"{prefix}_{anim_name}_{f}"
                x = f * frame_width
                self.sprites[sprite_id] = (x, y_start, frame_width, height)
        
        messagebox.showinfo("完成", f"已生成 {len(self.sprites)} 个精灵")
        return self.sprites
    
    def _generate_animations(self):
        """生成动画配置"""
        if not self.rows:
            messagebox.showwarning("警告", "请先添加行配置")
            return
        
        prefix = self.row_prefix_var.get()
        animations = {}
        
        for row in self.rows:
            y_start, height, frame_count, anim_name, frame_width = row
            
            frames = [f"{prefix}_{anim_name}_{f}" for f in range(frame_count)]
            
            animations[anim_name] = {
                'frames': frames,
                'fps': 8,
                'loop': True
            }
        
        messagebox.showinfo("完成", f"已生成 {len(animations)} 个动画")
        return animations
    
    def _export_full_config(self):
        """导出完整配置"""
        if not self.rows:
            messagebox.showwarning("警告", "请先添加行配置")
            return
        
        # 生成精灵和动画
        sprites = self._generate_sprites()
        animations = self._generate_animations()
        
        # 选择保存位置
        path = filedialog.asksaveasfilename(
            title="保存配置",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")]
        )
        
        if not path:
            return
        
        # 构建配置
        texture_name = os.path.basename(self.image_path) if self.image_path else "texture.png"
        
        config = {
            "version": "2.0",
            "texture": texture_name,
            "sprites": {},
            "animations": animations
        }
        
        # 添加精灵
        for sprite_id, rect in sprites.items():
            config["sprites"][sprite_id] = {
                "rect": list(rect)
            }
        
        # 保存
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            messagebox.showinfo("成功", f"配置已保存到:\n{path}\n\n精灵: {len(sprites)} 个\n动画: {len(animations)} 个")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")
    
    def _save_config(self):
        """保存切分配置（用于后续编辑）"""
        if not self.rows:
            messagebox.showwarning("警告", "没有可保存的配置")
            return
        
        path = filedialog.asksaveasfilename(
            title="保存切分配置",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")]
        )
        
        if not path:
            return
        
        config = {
            "type": "sprite_sheet_config",
            "image": os.path.basename(self.image_path) if self.image_path else "",
            "prefix": self.row_prefix_var.get(),
            "rows": [
                {
                    "y": r[0],
                    "height": r[1],
                    "frames": r[2],
                    "name": r[3],
                    "frame_width": r[4]
                }
                for r in self.rows
            ]
        }
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", "切分配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")
    
    def _load_config(self):
        """加载切分配置"""
        path = filedialog.askopenfilename(
            title="加载切分配置",
            filetypes=[("JSON文件", "*.json")]
        )
        
        if not path:
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            if config.get("type") != "sprite_sheet_config":
                messagebox.showwarning("警告", "这不是有效的切分配置文件")
                return
            
            self.row_prefix_var.set(config.get("prefix", "sprite"))
            
            self.rows.clear()
            for r in config.get("rows", []):
                self.rows.append((
                    r.get("y", 0),
                    r.get("height", 48),
                    r.get("frames", 4),
                    r.get("name", "anim"),
                    r.get("frame_width", 32)
                ))
            
            # 尝试加载对应图像
            img_name = config.get("image", "")
            if img_name:
                img_path = os.path.join(os.path.dirname(path), img_name)
                if os.path.exists(img_path):
                    self.image = Image.open(img_path).convert('RGBA')
                    self.image_path = img_path
            
            self._refresh_row_list()
            self._refresh_canvas()
            
            messagebox.showinfo("成功", f"已加载 {len(self.rows)} 行配置")
            
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {e}")


def main():
    root = tk.Tk()
    app = SpriteSheetCutter(root)
    root.mainloop()


if __name__ == '__main__':
    main()
