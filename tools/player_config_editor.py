"""
自机配置可视化编辑器
用于编辑玩家的JSON配置文件，预览动画和纹理
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import json
import os
import math
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw

class PlayerConfigEditor:
    """自机配置编辑器"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("自机配置编辑器")
        self.root.geometry("1400x900")
        
        # 当前配置
        self.config = {}
        self.config_path = None
        self.player_dir = None
        
        # 纹理相关
        self.texture_image = None
        self.texture_photo = None
        self.sprite_rects = {}  # sprite_id -> (x, y, w, h)
        
        # 动画预览
        self.animation_frames = []
        self.current_frame_idx = 0
        self.animation_playing = False
        self.animation_timer = None
        
        # 射击预览
        self.shot_preview_active = False
        
        # 创建UI
        self._create_menu()
        self._create_main_layout()
        
        # 默认配置
        self._new_config()
    
    def _create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="新建", command=self._new_config, accelerator="Ctrl+N")
        file_menu.add_command(label="打开...", command=self._open_config, accelerator="Ctrl+O")
        file_menu.add_command(label="保存", command=self._save_config, accelerator="Ctrl+S")
        file_menu.add_command(label="另存为...", command=self._save_config_as)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        
        # 视图菜单
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="视图", menu=view_menu)
        view_menu.add_command(label="刷新预览", command=self._refresh_preview)
        
        # 快捷键绑定
        self.root.bind('<Control-n>', lambda e: self._new_config())
        self.root.bind('<Control-o>', lambda e: self._open_config())
        self.root.bind('<Control-s>', lambda e: self._save_config())
    
    def _create_main_layout(self):
        """创建主布局"""
        # 主分割面板
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左侧：配置编辑区
        left_frame = ttk.Frame(main_paned, width=500)
        main_paned.add(left_frame, weight=1)
        
        # 右侧：预览区
        right_frame = ttk.Frame(main_paned, width=600)
        main_paned.add(right_frame, weight=2)
        
        self._create_config_panel(left_frame)
        self._create_preview_panel(right_frame)
    
    def _create_config_panel(self, parent):
        """创建配置编辑面板"""
        # 使用Notebook实现标签页
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # 基础信息标签页
        basic_frame = ttk.Frame(notebook)
        notebook.add(basic_frame, text="基础信息")
        self._create_basic_tab(basic_frame)
        
        # 属性标签页
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="属性")
        self._create_stats_tab(stats_frame)
        
        # 动画标签页
        anim_frame = ttk.Frame(notebook)
        notebook.add(anim_frame, text="动画")
        self._create_animation_tab(anim_frame)
        
        # 射击标签页
        shot_frame = ttk.Frame(notebook)
        notebook.add(shot_frame, text="射击")
        self._create_shot_tab(shot_frame)
        
        # Option标签页
        option_frame = ttk.Frame(notebook)
        notebook.add(option_frame, text="Option")
        self._create_option_tab(option_frame)
        
        # 符卡标签页
        spell_frame = ttk.Frame(notebook)
        notebook.add(spell_frame, text="符卡")
        self._create_spellcard_tab(spell_frame)
    
    def _create_basic_tab(self, parent):
        """基础信息标签页"""
        frame = ttk.LabelFrame(parent, text="基本信息", padding=10)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 名称
        ttk.Label(frame, text="名称:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.name_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=2)
        
        # 描述
        ttk.Label(frame, text="描述:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.desc_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.desc_var, width=30).grid(row=1, column=1, sticky=tk.W, pady=2)
        
        # 作者
        ttk.Label(frame, text="作者:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.author_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.author_var, width=30).grid(row=2, column=1, sticky=tk.W, pady=2)
        
        # 纹理文件
        texture_frame = ttk.LabelFrame(parent, text="纹理", padding=10)
        texture_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(texture_frame, text="纹理文件:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.texture_var = tk.StringVar()
        ttk.Entry(texture_frame, textvariable=self.texture_var, width=25).grid(row=0, column=1, sticky=tk.W, pady=2)
        ttk.Button(texture_frame, text="浏览...", command=self._browse_texture).grid(row=0, column=2, padx=5)
        
        # 精灵配置
        ttk.Label(texture_frame, text="精灵配置:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.sprite_config_var = tk.StringVar()
        ttk.Entry(texture_frame, textvariable=self.sprite_config_var, width=25).grid(row=1, column=1, sticky=tk.W, pady=2)
        ttk.Button(texture_frame, text="浏览...", command=self._browse_sprite_config).grid(row=1, column=2, padx=5)
        ttk.Button(texture_frame, text="加载", command=self._load_sprite_config).grid(row=1, column=3, padx=5)
        
        # 初始值
        initial_frame = ttk.LabelFrame(parent, text="初始值", padding=10)
        initial_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(initial_frame, text="生命:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.lives_var = tk.IntVar(value=3)
        ttk.Spinbox(initial_frame, textvariable=self.lives_var, from_=1, to=9, width=5).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(initial_frame, text="符卡:").grid(row=0, column=2, sticky=tk.W, pady=2, padx=(20, 0))
        self.bombs_var = tk.IntVar(value=3)
        ttk.Spinbox(initial_frame, textvariable=self.bombs_var, from_=0, to=9, width=5).grid(row=0, column=3, sticky=tk.W)
        
        ttk.Label(initial_frame, text="Power:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.power_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(initial_frame, textvariable=self.power_var, from_=1.0, to=4.0, increment=0.01, width=5).grid(row=1, column=1, sticky=tk.W)
    
    def _create_stats_tab(self, parent):
        """属性标签页"""
        frame = ttk.LabelFrame(parent, text="移动属性", padding=10)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 高速移动
        ttk.Label(frame, text="高速移动速度:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.speed_high_var = tk.DoubleVar(value=0.02)
        speed_high_spin = ttk.Spinbox(frame, textvariable=self.speed_high_var, 
                                       from_=0.001, to=0.1, increment=0.001, width=8)
        speed_high_spin.grid(row=0, column=1, sticky=tk.W)
        
        # 低速移动
        ttk.Label(frame, text="低速移动速度:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.speed_low_var = tk.DoubleVar(value=0.008)
        ttk.Spinbox(frame, textvariable=self.speed_low_var, 
                    from_=0.001, to=0.05, increment=0.001, width=8).grid(row=1, column=1, sticky=tk.W)
        
        # 判定半径
        hitbox_frame = ttk.LabelFrame(parent, text="判定", padding=10)
        hitbox_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(hitbox_frame, text="判定点半径:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.hit_radius_var = tk.DoubleVar(value=0.01)
        ttk.Spinbox(hitbox_frame, textvariable=self.hit_radius_var, 
                    from_=0.001, to=0.05, increment=0.001, width=8).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(hitbox_frame, text="擦弹半径:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.graze_radius_var = tk.DoubleVar(value=0.05)
        ttk.Spinbox(hitbox_frame, textvariable=self.graze_radius_var, 
                    from_=0.01, to=0.2, increment=0.01, width=8).grid(row=1, column=1, sticky=tk.W)
        
        # 可视化预览按钮
        ttk.Button(hitbox_frame, text="在预览中显示判定", 
                   command=self._toggle_hitbox_preview).grid(row=2, column=0, columnspan=2, pady=10)
        self.show_hitbox = tk.BooleanVar(value=True)
    
    def _create_animation_tab(self, parent):
        """动画标签页"""
        # 动画列表
        list_frame = ttk.LabelFrame(parent, text="动画列表", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 列表和滚动条
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.anim_listbox = tk.Listbox(list_container, yscrollcommand=scrollbar.set, height=8)
        self.anim_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.anim_listbox.yview)
        
        self.anim_listbox.bind('<<ListboxSelect>>', self._on_animation_select)
        
        # 按钮
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加", command=self._add_animation).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除", command=self._delete_animation).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="预览", command=self._preview_animation).pack(side=tk.LEFT, padx=2)
        
        # 动画编辑
        edit_frame = ttk.LabelFrame(parent, text="动画编辑", padding=5)
        edit_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="名称:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.anim_name_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.anim_name_var, width=20).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="帧率 (FPS):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.anim_fps_var = tk.DoubleVar(value=8.0)
        ttk.Spinbox(edit_frame, textvariable=self.anim_fps_var, from_=1, to=60, width=8).grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="循环:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.anim_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(edit_frame, variable=self.anim_loop_var).grid(row=2, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="帧列表:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.anim_frames_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.anim_frames_var, width=40).grid(row=3, column=1, columnspan=2, sticky=tk.W)
        ttk.Label(edit_frame, text="(逗号分隔的精灵ID)").grid(row=4, column=1, sticky=tk.W)
        
        ttk.Button(edit_frame, text="应用更改", command=self._apply_animation_changes).grid(row=5, column=0, columnspan=2, pady=10)
    
    def _create_shot_tab(self, parent):
        """射击标签页"""
        # 射击模式选择
        mode_frame = ttk.LabelFrame(parent, text="射击模式", padding=5)
        mode_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.shot_mode_var = tk.StringVar(value="unfocused")
        ttk.Radiobutton(mode_frame, text="高速 (Unfocused)", variable=self.shot_mode_var, 
                        value="unfocused", command=self._on_shot_mode_change).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="低速 (Focused)", variable=self.shot_mode_var, 
                        value="focused", command=self._on_shot_mode_change).pack(side=tk.LEFT, padx=10)
        
        # 射击属性
        attr_frame = ttk.LabelFrame(parent, text="射击属性", padding=5)
        attr_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(attr_frame, text="名称:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.shot_name_var = tk.StringVar()
        ttk.Entry(attr_frame, textvariable=self.shot_name_var, width=25).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(attr_frame, text="射击间隔 (秒):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.shot_rate_var = tk.DoubleVar(value=0.05)
        ttk.Spinbox(attr_frame, textvariable=self.shot_rate_var, from_=0.01, to=1.0, 
                    increment=0.01, width=8).grid(row=1, column=1, sticky=tk.W)
        
        # Pattern列表
        pattern_frame = ttk.LabelFrame(parent, text="发射点 (Patterns)", padding=5)
        pattern_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 列表
        self.pattern_tree = ttk.Treeview(pattern_frame, columns=('offset', 'angle', 'speed', 'bullet', 'damage'), 
                                          show='headings', height=6)
        self.pattern_tree.heading('offset', text='偏移')
        self.pattern_tree.heading('angle', text='角度')
        self.pattern_tree.heading('speed', text='速度')
        self.pattern_tree.heading('bullet', text='子弹')
        self.pattern_tree.heading('damage', text='伤害')
        
        self.pattern_tree.column('offset', width=80)
        self.pattern_tree.column('angle', width=50)
        self.pattern_tree.column('speed', width=50)
        self.pattern_tree.column('bullet', width=100)
        self.pattern_tree.column('damage', width=50)
        
        self.pattern_tree.pack(fill=tk.BOTH, expand=True)
        self.pattern_tree.bind('<<TreeviewSelect>>', self._on_pattern_select)
        
        # Pattern编辑
        edit_frame = ttk.Frame(pattern_frame)
        edit_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(edit_frame, text="X偏移:").grid(row=0, column=0, pady=2)
        self.pattern_x_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(edit_frame, textvariable=self.pattern_x_var, from_=-0.5, to=0.5, 
                    increment=0.01, width=6).grid(row=0, column=1)
        
        ttk.Label(edit_frame, text="Y偏移:").grid(row=0, column=2, pady=2, padx=(10, 0))
        self.pattern_y_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(edit_frame, textvariable=self.pattern_y_var, from_=-0.5, to=0.5, 
                    increment=0.01, width=6).grid(row=0, column=3)
        
        ttk.Label(edit_frame, text="角度:").grid(row=1, column=0, pady=2)
        self.pattern_angle_var = tk.DoubleVar(value=90.0)
        ttk.Spinbox(edit_frame, textvariable=self.pattern_angle_var, from_=0, to=360, 
                    increment=5, width=6).grid(row=1, column=1)
        
        ttk.Label(edit_frame, text="速度:").grid(row=1, column=2, pady=2, padx=(10, 0))
        self.pattern_speed_var = tk.DoubleVar(value=0.8)
        ttk.Spinbox(edit_frame, textvariable=self.pattern_speed_var, from_=0.1, to=2.0, 
                    increment=0.05, width=6).grid(row=1, column=3)
        
        ttk.Label(edit_frame, text="子弹:").grid(row=2, column=0, pady=2)
        self.pattern_bullet_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.pattern_bullet_var, width=15).grid(row=2, column=1, columnspan=2, sticky=tk.W)
        
        ttk.Label(edit_frame, text="伤害:").grid(row=2, column=3, pady=2, padx=(10, 0))
        self.pattern_damage_var = tk.DoubleVar(value=10.0)
        ttk.Spinbox(edit_frame, textvariable=self.pattern_damage_var, from_=1, to=100, width=6).grid(row=2, column=4)
        
        ttk.Label(edit_frame, text="追踪:").grid(row=3, column=0, pady=2)
        self.pattern_homing_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(edit_frame, variable=self.pattern_homing_var).grid(row=3, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="追踪强度:").grid(row=3, column=2, pady=2, padx=(10, 0))
        self.pattern_homing_str_var = tk.DoubleVar(value=5.0)
        ttk.Spinbox(edit_frame, textvariable=self.pattern_homing_str_var, from_=0.1, to=20, 
                    increment=0.5, width=6).grid(row=3, column=3)
        
        # 按钮
        btn_frame = ttk.Frame(pattern_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="添加", command=self._add_pattern).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="更新", command=self._update_pattern).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除", command=self._delete_pattern).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="预览射击", command=self._preview_shot).pack(side=tk.RIGHT, padx=2)
    
    def _create_option_tab(self, parent):
        """Option标签页"""
        # Option列表
        list_frame = ttk.LabelFrame(parent, text="Option列表", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.option_listbox = tk.Listbox(list_frame, height=6)
        self.option_listbox.pack(fill=tk.BOTH, expand=True)
        self.option_listbox.bind('<<ListboxSelect>>', self._on_option_select)
        
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加", command=self._add_option).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除", command=self._delete_option).pack(side=tk.LEFT, padx=2)
        
        # Option编辑
        edit_frame = ttk.LabelFrame(parent, text="Option编辑", padding=5)
        edit_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="精灵:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.option_sprite_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.option_sprite_var, width=20).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="高速位置 X:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.option_x_var = tk.DoubleVar(value=0.1)
        ttk.Spinbox(edit_frame, textvariable=self.option_x_var, from_=-0.5, to=0.5, 
                    increment=0.01, width=8).grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="高速位置 Y:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.option_y_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(edit_frame, textvariable=self.option_y_var, from_=-0.5, to=0.5, 
                    increment=0.01, width=8).grid(row=2, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="低速位置 X:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.option_fx_var = tk.DoubleVar(value=0.03)
        ttk.Spinbox(edit_frame, textvariable=self.option_fx_var, from_=-0.5, to=0.5, 
                    increment=0.01, width=8).grid(row=3, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="低速位置 Y:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.option_fy_var = tk.DoubleVar(value=0.05)
        ttk.Spinbox(edit_frame, textvariable=self.option_fy_var, from_=-0.5, to=0.5, 
                    increment=0.01, width=8).grid(row=4, column=1, sticky=tk.W)
        
        ttk.Button(edit_frame, text="应用更改", command=self._apply_option_changes).grid(row=5, column=0, columnspan=2, pady=10)
    
    def _create_spellcard_tab(self, parent):
        """符卡标签页"""
        # 符卡列表
        list_frame = ttk.LabelFrame(parent, text="符卡列表", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.spell_listbox = tk.Listbox(list_frame, height=6)
        self.spell_listbox.pack(fill=tk.BOTH, expand=True)
        self.spell_listbox.bind('<<ListboxSelect>>', self._on_spell_select)
        
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加", command=self._add_spellcard).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除", command=self._delete_spellcard).pack(side=tk.LEFT, padx=2)
        
        # 符卡编辑
        edit_frame = ttk.LabelFrame(parent, text="符卡编辑", padding=5)
        edit_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="名称:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.spell_name_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.spell_name_var, width=25).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="消耗:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.spell_cost_var = tk.IntVar(value=100)
        ttk.Spinbox(edit_frame, textvariable=self.spell_cost_var, from_=0, to=500, width=8).grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="脚本:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.spell_script_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.spell_script_var, width=25).grid(row=2, column=1, sticky=tk.W)
        
        ttk.Label(edit_frame, text="描述:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.spell_desc_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.spell_desc_var, width=35).grid(row=3, column=1, sticky=tk.W)
        
        ttk.Button(edit_frame, text="应用更改", command=self._apply_spell_changes).grid(row=4, column=0, columnspan=2, pady=10)
    
    def _create_preview_panel(self, parent):
        """创建预览面板"""
        # 预览Canvas
        preview_frame = ttk.LabelFrame(parent, text="预览", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.preview_canvas = tk.Canvas(preview_frame, bg='#1a1a2e', width=400, height=500)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        
        # 控制面板
        ctrl_frame = ttk.Frame(parent)
        ctrl_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(ctrl_frame, text="▶ 播放动画", command=self._toggle_animation).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="◀", command=self._prev_frame).pack(side=tk.LEFT)
        ttk.Button(ctrl_frame, text="▶", command=self._next_frame).pack(side=tk.LEFT)
        
        self.frame_label = ttk.Label(ctrl_frame, text="帧: 0/0")
        self.frame_label.pack(side=tk.LEFT, padx=10)
        
        # 缩放
        ttk.Label(ctrl_frame, text="缩放:").pack(side=tk.LEFT, padx=(20, 5))
        self.zoom_var = tk.DoubleVar(value=2.0)
        zoom_spin = ttk.Spinbox(ctrl_frame, textvariable=self.zoom_var, from_=0.5, to=8.0, 
                                 increment=0.5, width=5, command=self._refresh_preview)
        zoom_spin.pack(side=tk.LEFT)
        
        # 精灵选择
        sprite_frame = ttk.LabelFrame(parent, text="精灵列表", padding=5)
        sprite_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 搜索
        search_frame = ttk.Frame(sprite_frame)
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.sprite_search_var = tk.StringVar()
        self.sprite_search_var.trace('w', self._filter_sprites)
        ttk.Entry(search_frame, textvariable=self.sprite_search_var, width=20).pack(side=tk.LEFT, padx=5)
        
        # 列表
        list_container = ttk.Frame(sprite_frame)
        list_container.pack(fill=tk.BOTH, expand=True, pady=5)
        
        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.sprite_listbox = tk.Listbox(list_container, yscrollcommand=scrollbar.set, height=10)
        self.sprite_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.sprite_listbox.yview)
        
        self.sprite_listbox.bind('<<ListboxSelect>>', self._on_sprite_select)
        self.sprite_listbox.bind('<Double-Button-1>', self._on_sprite_double_click)
    
    # ============ 文件操作 ============
    
    def _new_config(self):
        """新建配置"""
        self.config = {
            "name": "新角色",
            "description": "",
            "author": "",
            "texture": "",
            "stats": {
                "speed_high": 0.02,
                "speed_low": 0.008,
                "hit_radius": 0.01,
                "graze_radius": 0.05
            },
            "initial": {
                "lives": 3,
                "bombs": 3,
                "power": 1.0
            },
            "animations": {
                "animations": {}
            },
            "shot_types": {
                "unfocused": {
                    "name": "",
                    "fire_rate": 0.05,
                    "patterns": []
                },
                "focused": {
                    "name": "",
                    "fire_rate": 0.04,
                    "patterns": []
                }
            },
            "options": [],
            "spellcards": []
        }
        self.config_path = None
        self.player_dir = None
        self._load_config_to_ui()
    
    def _open_config(self):
        """打开配置文件"""
        path = filedialog.askopenfilename(
            title="打开自机配置",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                self.config_path = path
                self.player_dir = os.path.dirname(path)
                self._load_config_to_ui()
                self._try_load_texture()
                self.root.title(f"自机配置编辑器 - {os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("错误", f"无法加载配置: {e}")
    
    def _save_config(self):
        """保存配置"""
        if self.config_path is None:
            self._save_config_as()
            return
        
        self._save_ui_to_config()
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", "配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"无法保存配置: {e}")
    
    def _save_config_as(self):
        """另存为"""
        path = filedialog.asksaveasfilename(
            title="保存自机配置",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")]
        )
        
        if path:
            self.config_path = path
            self.player_dir = os.path.dirname(path)
            self._save_config()
            self.root.title(f"自机配置编辑器 - {os.path.basename(path)}")
    
    # ============ UI加载/保存 ============
    
    def _load_config_to_ui(self):
        """将配置加载到UI"""
        # 基础信息
        self.name_var.set(self.config.get('name', ''))
        self.desc_var.set(self.config.get('description', ''))
        self.author_var.set(self.config.get('author', ''))
        self.texture_var.set(self.config.get('texture', ''))
        
        # 初始值
        initial = self.config.get('initial', {})
        self.lives_var.set(initial.get('lives', 3))
        self.bombs_var.set(initial.get('bombs', 3))
        self.power_var.set(initial.get('power', 1.0))
        
        # 属性
        stats = self.config.get('stats', {})
        self.speed_high_var.set(stats.get('speed_high', 0.02))
        self.speed_low_var.set(stats.get('speed_low', 0.008))
        self.hit_radius_var.set(stats.get('hit_radius', 0.01))
        self.graze_radius_var.set(stats.get('graze_radius', 0.05))
        
        # 动画
        self._refresh_animation_list()
        
        # 射击
        self._refresh_shot_patterns()
        
        # Option
        self._refresh_option_list()
        
        # 符卡
        self._refresh_spell_list()
    
    def _save_ui_to_config(self):
        """将UI保存到配置"""
        self.config['name'] = self.name_var.get()
        self.config['description'] = self.desc_var.get()
        self.config['author'] = self.author_var.get()
        self.config['texture'] = self.texture_var.get()
        
        self.config['initial'] = {
            'lives': self.lives_var.get(),
            'bombs': self.bombs_var.get(),
            'power': self.power_var.get()
        }
        
        self.config['stats'] = {
            'speed_high': self.speed_high_var.get(),
            'speed_low': self.speed_low_var.get(),
            'hit_radius': self.hit_radius_var.get(),
            'graze_radius': self.graze_radius_var.get()
        }
    
    # ============ 纹理加载 ============
    
    def _browse_texture(self):
        """浏览纹理文件"""
        path = filedialog.askopenfilename(
            title="选择纹理文件",
            filetypes=[("图片文件", "*.png;*.jpg;*.bmp"), ("所有文件", "*.*")]
        )
        
        if path:
            if self.player_dir:
                # 尝试使用相对路径
                try:
                    rel_path = os.path.relpath(path, self.player_dir)
                    self.texture_var.set(rel_path)
                except:
                    self.texture_var.set(os.path.basename(path))
            else:
                self.texture_var.set(os.path.basename(path))
            
            self._load_texture(path)
    
    def _browse_sprite_config(self):
        """浏览精灵配置文件"""
        path = filedialog.askopenfilename(
            title="选择精灵配置文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if path:
            self.sprite_config_var.set(path)
    
    def _load_sprite_config(self):
        """加载精灵配置"""
        path = self.sprite_config_var.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning("警告", "请先选择有效的精灵配置文件")
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                sprite_config = json.load(f)
            
            self.sprite_rects.clear()
            
            # 解析精灵
            sprites = sprite_config.get('sprites', {})
            for sprite_id, data in sprites.items():
                if isinstance(data, dict) and 'rect' in data:
                    rect = data['rect']
                    self.sprite_rects[sprite_id] = tuple(rect)
            
            # 更新精灵列表
            self._refresh_sprite_list()
            
            # 尝试加载对应纹理
            texture_file = sprite_config.get('texture') or sprite_config.get('__image_filename')
            if texture_file:
                texture_path = os.path.join(os.path.dirname(path), texture_file)
                if os.path.exists(texture_path):
                    self._load_texture(texture_path)
            
            messagebox.showinfo("成功", f"已加载 {len(self.sprite_rects)} 个精灵")
            
        except Exception as e:
            messagebox.showerror("错误", f"加载精灵配置失败: {e}")
    
    def _try_load_texture(self):
        """尝试加载纹理"""
        texture_name = self.texture_var.get()
        if not texture_name or not self.player_dir:
            return
        
        texture_path = os.path.join(self.player_dir, texture_name)
        if os.path.exists(texture_path):
            self._load_texture(texture_path)
    
    def _load_texture(self, path):
        """加载纹理图片"""
        try:
            self.texture_image = Image.open(path).convert('RGBA')
            self._refresh_preview()
            self._refresh_sprite_list()
        except Exception as e:
            messagebox.showerror("错误", f"加载纹理失败: {e}")
    
    def _refresh_sprite_list(self):
        """刷新精灵列表"""
        self.sprite_listbox.delete(0, tk.END)
        
        for sprite_id in sorted(self.sprite_rects.keys()):
            self.sprite_listbox.insert(tk.END, sprite_id)
    
    def _filter_sprites(self, *args):
        """过滤精灵列表"""
        search = self.sprite_search_var.get().lower()
        self.sprite_listbox.delete(0, tk.END)
        
        for sprite_id in sorted(self.sprite_rects.keys()):
            if search in sprite_id.lower():
                self.sprite_listbox.insert(tk.END, sprite_id)
    
    # ============ 预览 ============
    
    def _refresh_preview(self, *args):
        """刷新预览"""
        self.preview_canvas.delete('all')
        
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        
        if canvas_w < 10:
            canvas_w = 400
        if canvas_h < 10:
            canvas_h = 500
        
        center_x = canvas_w // 2
        center_y = canvas_h // 2
        
        zoom = self.zoom_var.get()
        
        # 绘制网格
        self._draw_grid(canvas_w, canvas_h, center_x, center_y)
        
        # 绘制自机
        self._draw_player_preview(center_x, center_y, zoom)
        
        # 绘制判定框
        if self.show_hitbox.get():
            self._draw_hitbox_preview(center_x, center_y, zoom)
        
        # 绘制射击预览
        if self.shot_preview_active:
            self._draw_shot_preview(center_x, center_y, zoom)
    
    def _draw_grid(self, w, h, cx, cy):
        """绘制背景网格"""
        grid_size = 50
        
        for x in range(0, w, grid_size):
            color = '#2a2a4e' if x != cx else '#4a4a6e'
            self.preview_canvas.create_line(x, 0, x, h, fill=color)
        
        for y in range(0, h, grid_size):
            color = '#2a2a4e' if y != cy else '#4a4a6e'
            self.preview_canvas.create_line(0, y, w, y, fill=color)
    
    def _draw_player_preview(self, cx, cy, zoom):
        """绘制自机预览"""
        if not self.animation_frames:
            # 没有动画，显示占位符
            size = int(50 * zoom)
            self.preview_canvas.create_rectangle(
                cx - size//2, cy - size//2, cx + size//2, cy + size//2,
                outline='#ff6b6b', width=2
            )
            self.preview_canvas.create_text(cx, cy, text="自机", fill='#ff6b6b')
            return
        
        # 显示当前帧
        if self.current_frame_idx < len(self.animation_frames):
            frame_img = self.animation_frames[self.current_frame_idx]
            
            # 缩放
            new_w = int(frame_img.width * zoom)
            new_h = int(frame_img.height * zoom)
            scaled = frame_img.resize((new_w, new_h), Image.NEAREST)
            
            self.current_frame_photo = ImageTk.PhotoImage(scaled)
            self.preview_canvas.create_image(cx, cy, image=self.current_frame_photo)
    
    def _draw_hitbox_preview(self, cx, cy, zoom):
        """绘制判定框预览"""
        # 判定点
        hit_r = self.hit_radius_var.get() * 1000 * zoom  # 缩放到像素
        self.preview_canvas.create_oval(
            cx - hit_r, cy - hit_r, cx + hit_r, cy + hit_r,
            outline='#ff0000', width=2
        )
        
        # 擦弹范围
        graze_r = self.graze_radius_var.get() * 1000 * zoom
        self.preview_canvas.create_oval(
            cx - graze_r, cy - graze_r, cx + graze_r, cy + graze_r,
            outline='#00ff00', width=1, dash=(4, 4)
        )
    
    def _draw_shot_preview(self, cx, cy, zoom):
        """绘制射击预览"""
        mode = self.shot_mode_var.get()
        shot_types = self.config.get('shot_types', {})
        shot_type = shot_types.get(mode, {})
        patterns = shot_type.get('patterns', [])
        
        scale = 200 * zoom  # 坐标缩放
        
        for pattern in patterns:
            offset = pattern.get('offset', [0, 0])
            angle = pattern.get('angle', 90)
            
            # 发射点位置
            px = cx + offset[0] * scale
            py = cy - offset[1] * scale  # Y轴翻转
            
            # 绘制发射点
            self.preview_canvas.create_oval(
                px - 5, py - 5, px + 5, py + 5,
                fill='#ffcc00', outline='#ff9900'
            )
            
            # 绘制发射方向
            angle_rad = math.radians(angle)
            line_len = 30
            end_x = px + math.cos(angle_rad) * line_len
            end_y = py - math.sin(angle_rad) * line_len  # Y轴翻转
            
            self.preview_canvas.create_line(
                px, py, end_x, end_y,
                fill='#ffcc00', width=2, arrow=tk.LAST
            )
        
        # 绘制Option位置
        options = self.config.get('options', [])
        for opt in options:
            offset = opt.get('offset', [0, 0])
            focused_offset = opt.get('focused_offset', offset)
            
            # 高速模式位置
            ox = cx + offset[0] * scale
            oy = cy - offset[1] * scale
            self.preview_canvas.create_oval(
                ox - 8, oy - 8, ox + 8, oy + 8,
                fill='#6699ff', outline='#3366cc'
            )
            
            # 低速模式位置（虚线）
            fox = cx + focused_offset[0] * scale
            foy = cy - focused_offset[1] * scale
            self.preview_canvas.create_oval(
                fox - 8, foy - 8, fox + 8, foy + 8,
                outline='#3366cc', dash=(3, 3)
            )
    
    def _toggle_hitbox_preview(self):
        """切换判定框显示"""
        self.show_hitbox.set(not self.show_hitbox.get())
        self._refresh_preview()
    
    # ============ 动画操作 ============
    
    def _refresh_animation_list(self):
        """刷新动画列表"""
        self.anim_listbox.delete(0, tk.END)
        
        anims = self.config.get('animations', {})
        if isinstance(anims, dict):
            anim_dict = anims.get('animations', anims)
            if isinstance(anim_dict, dict):
                for name in sorted(anim_dict.keys()):
                    if isinstance(anim_dict[name], dict):
                        self.anim_listbox.insert(tk.END, name)
    
    def _on_animation_select(self, event):
        """动画选择事件"""
        selection = self.anim_listbox.curselection()
        if not selection:
            return
        
        name = self.anim_listbox.get(selection[0])
        anims = self.config.get('animations', {})
        anim_dict = anims.get('animations', anims)
        
        if name in anim_dict:
            anim = anim_dict[name]
            self.anim_name_var.set(name)
            self.anim_fps_var.set(anim.get('fps', 8))
            self.anim_loop_var.set(anim.get('loop', True))
            self.anim_frames_var.set(', '.join(anim.get('frames', [])))
    
    def _add_animation(self):
        """添加动画"""
        name = f"anim_{len(self.anim_listbox.get(0, tk.END))}"
        
        anims = self.config.setdefault('animations', {})
        anim_dict = anims.setdefault('animations', {})
        
        anim_dict[name] = {
            'frames': [],
            'fps': 8,
            'loop': True
        }
        
        self._refresh_animation_list()
    
    def _delete_animation(self):
        """删除动画"""
        selection = self.anim_listbox.curselection()
        if not selection:
            return
        
        name = self.anim_listbox.get(selection[0])
        
        anims = self.config.get('animations', {})
        anim_dict = anims.get('animations', anims)
        
        if name in anim_dict:
            del anim_dict[name]
            self._refresh_animation_list()
    
    def _apply_animation_changes(self):
        """应用动画更改"""
        selection = self.anim_listbox.curselection()
        if not selection:
            return
        
        old_name = self.anim_listbox.get(selection[0])
        new_name = self.anim_name_var.get()
        
        anims = self.config.get('animations', {})
        anim_dict = anims.get('animations', anims)
        
        # 解析帧列表
        frames_str = self.anim_frames_var.get()
        frames = [f.strip() for f in frames_str.split(',') if f.strip()]
        
        anim_data = {
            'frames': frames,
            'fps': self.anim_fps_var.get(),
            'loop': self.anim_loop_var.get()
        }
        
        # 如果名称改变，删除旧的
        if old_name != new_name and old_name in anim_dict:
            del anim_dict[old_name]
        
        anim_dict[new_name] = anim_data
        self._refresh_animation_list()
    
    def _preview_animation(self):
        """预览动画"""
        selection = self.anim_listbox.curselection()
        if not selection:
            return
        
        name = self.anim_listbox.get(selection[0])
        anims = self.config.get('animations', {})
        anim_dict = anims.get('animations', anims)
        
        if name not in anim_dict:
            return
        
        anim = anim_dict[name]
        frames = anim.get('frames', [])
        
        # 加载帧图片
        self.animation_frames = []
        
        for frame_id in frames:
            if frame_id in self.sprite_rects and self.texture_image:
                rect = self.sprite_rects[frame_id]
                frame_img = self.texture_image.crop((
                    rect[0], rect[1], 
                    rect[0] + rect[2], rect[1] + rect[3]
                ))
                self.animation_frames.append(frame_img)
        
        if self.animation_frames:
            self.current_frame_idx = 0
            self._update_frame_label()
            self._refresh_preview()
    
    def _toggle_animation(self):
        """切换动画播放"""
        if self.animation_playing:
            self.animation_playing = False
            if self.animation_timer:
                self.root.after_cancel(self.animation_timer)
        else:
            if self.animation_frames:
                self.animation_playing = True
                self._play_animation_frame()
    
    def _play_animation_frame(self):
        """播放动画帧"""
        if not self.animation_playing or not self.animation_frames:
            return
        
        self.current_frame_idx = (self.current_frame_idx + 1) % len(self.animation_frames)
        self._update_frame_label()
        self._refresh_preview()
        
        # 计算帧间隔
        fps = self.anim_fps_var.get()
        delay = int(1000 / fps) if fps > 0 else 125
        
        self.animation_timer = self.root.after(delay, self._play_animation_frame)
    
    def _prev_frame(self):
        """上一帧"""
        if self.animation_frames:
            self.current_frame_idx = (self.current_frame_idx - 1) % len(self.animation_frames)
            self._update_frame_label()
            self._refresh_preview()
    
    def _next_frame(self):
        """下一帧"""
        if self.animation_frames:
            self.current_frame_idx = (self.current_frame_idx + 1) % len(self.animation_frames)
            self._update_frame_label()
            self._refresh_preview()
    
    def _update_frame_label(self):
        """更新帧标签"""
        total = len(self.animation_frames)
        current = self.current_frame_idx + 1 if total > 0 else 0
        self.frame_label.config(text=f"帧: {current}/{total}")
    
    # ============ 射击操作 ============
    
    def _on_shot_mode_change(self):
        """射击模式切换"""
        self._refresh_shot_patterns()
    
    def _refresh_shot_patterns(self):
        """刷新射击pattern列表"""
        # 清空树
        for item in self.pattern_tree.get_children():
            self.pattern_tree.delete(item)
        
        mode = self.shot_mode_var.get()
        shot_types = self.config.get('shot_types', {})
        shot_type = shot_types.get(mode, {})
        
        self.shot_name_var.set(shot_type.get('name', ''))
        self.shot_rate_var.set(shot_type.get('fire_rate', 0.05))
        
        patterns = shot_type.get('patterns', [])
        
        for i, p in enumerate(patterns):
            offset = p.get('offset', [0, 0])
            self.pattern_tree.insert('', 'end', iid=str(i), values=(
                f"({offset[0]:.2f}, {offset[1]:.2f})",
                p.get('angle', 90),
                p.get('speed', 0.8),
                p.get('bullet', ''),
                p.get('damage', 10)
            ))
    
    def _on_pattern_select(self, event):
        """Pattern选择事件"""
        selection = self.pattern_tree.selection()
        if not selection:
            return
        
        idx = int(selection[0])
        mode = self.shot_mode_var.get()
        shot_types = self.config.get('shot_types', {})
        patterns = shot_types.get(mode, {}).get('patterns', [])
        
        if idx < len(patterns):
            p = patterns[idx]
            offset = p.get('offset', [0, 0])
            self.pattern_x_var.set(offset[0])
            self.pattern_y_var.set(offset[1])
            self.pattern_angle_var.set(p.get('angle', 90))
            self.pattern_speed_var.set(p.get('speed', 0.8))
            self.pattern_bullet_var.set(p.get('bullet', ''))
            self.pattern_damage_var.set(p.get('damage', 10))
            self.pattern_homing_var.set(p.get('homing', False))
            self.pattern_homing_str_var.set(p.get('homing_strength', 5.0))
    
    def _add_pattern(self):
        """添加Pattern"""
        mode = self.shot_mode_var.get()
        shot_types = self.config.setdefault('shot_types', {})
        shot_type = shot_types.setdefault(mode, {'patterns': []})
        patterns = shot_type.setdefault('patterns', [])
        
        pattern = {
            'offset': [self.pattern_x_var.get(), self.pattern_y_var.get()],
            'angle': self.pattern_angle_var.get(),
            'speed': self.pattern_speed_var.get(),
            'bullet': self.pattern_bullet_var.get(),
            'damage': self.pattern_damage_var.get()
        }
        
        if self.pattern_homing_var.get():
            pattern['homing'] = True
            pattern['homing_strength'] = self.pattern_homing_str_var.get()
        
        patterns.append(pattern)
        self._refresh_shot_patterns()
    
    def _update_pattern(self):
        """更新Pattern"""
        selection = self.pattern_tree.selection()
        if not selection:
            return
        
        idx = int(selection[0])
        mode = self.shot_mode_var.get()
        shot_types = self.config.get('shot_types', {})
        patterns = shot_types.get(mode, {}).get('patterns', [])
        
        if idx < len(patterns):
            patterns[idx] = {
                'offset': [self.pattern_x_var.get(), self.pattern_y_var.get()],
                'angle': self.pattern_angle_var.get(),
                'speed': self.pattern_speed_var.get(),
                'bullet': self.pattern_bullet_var.get(),
                'damage': self.pattern_damage_var.get()
            }
            
            if self.pattern_homing_var.get():
                patterns[idx]['homing'] = True
                patterns[idx]['homing_strength'] = self.pattern_homing_str_var.get()
            
            # 更新shot_type的名称和fire_rate
            shot_types[mode]['name'] = self.shot_name_var.get()
            shot_types[mode]['fire_rate'] = self.shot_rate_var.get()
            
            self._refresh_shot_patterns()
    
    def _delete_pattern(self):
        """删除Pattern"""
        selection = self.pattern_tree.selection()
        if not selection:
            return
        
        idx = int(selection[0])
        mode = self.shot_mode_var.get()
        shot_types = self.config.get('shot_types', {})
        patterns = shot_types.get(mode, {}).get('patterns', [])
        
        if idx < len(patterns):
            del patterns[idx]
            self._refresh_shot_patterns()
    
    def _preview_shot(self):
        """预览射击"""
        self.shot_preview_active = not self.shot_preview_active
        self._refresh_preview()
    
    # ============ Option操作 ============
    
    def _refresh_option_list(self):
        """刷新Option列表"""
        self.option_listbox.delete(0, tk.END)
        
        options = self.config.get('options', [])
        for i, opt in enumerate(options):
            sprite = opt.get('sprite', f'Option {i+1}')
            self.option_listbox.insert(tk.END, f"{i+1}. {sprite}")
    
    def _on_option_select(self, event):
        """Option选择事件"""
        selection = self.option_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        options = self.config.get('options', [])
        
        if idx < len(options):
            opt = options[idx]
            self.option_sprite_var.set(opt.get('sprite', ''))
            offset = opt.get('offset', [0, 0])
            self.option_x_var.set(offset[0])
            self.option_y_var.set(offset[1])
            focused = opt.get('focused_offset', [0, 0])
            self.option_fx_var.set(focused[0])
            self.option_fy_var.set(focused[1])
    
    def _add_option(self):
        """添加Option"""
        options = self.config.setdefault('options', [])
        options.append({
            'sprite': 'option',
            'offset': [0.1, 0.0],
            'focused_offset': [0.03, 0.05],
            'shot_patterns': []
        })
        self._refresh_option_list()
    
    def _delete_option(self):
        """删除Option"""
        selection = self.option_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        options = self.config.get('options', [])
        
        if idx < len(options):
            del options[idx]
            self._refresh_option_list()
    
    def _apply_option_changes(self):
        """应用Option更改"""
        selection = self.option_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        options = self.config.get('options', [])
        
        if idx < len(options):
            options[idx]['sprite'] = self.option_sprite_var.get()
            options[idx]['offset'] = [self.option_x_var.get(), self.option_y_var.get()]
            options[idx]['focused_offset'] = [self.option_fx_var.get(), self.option_fy_var.get()]
            self._refresh_option_list()
    
    # ============ 符卡操作 ============
    
    def _refresh_spell_list(self):
        """刷新符卡列表"""
        self.spell_listbox.delete(0, tk.END)
        
        spells = self.config.get('spellcards', [])
        for spell in spells:
            name = spell.get('name', '未命名')
            self.spell_listbox.insert(tk.END, name)
    
    def _on_spell_select(self, event):
        """符卡选择事件"""
        selection = self.spell_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        spells = self.config.get('spellcards', [])
        
        if idx < len(spells):
            spell = spells[idx]
            self.spell_name_var.set(spell.get('name', ''))
            self.spell_cost_var.set(spell.get('cost', 100))
            self.spell_script_var.set(spell.get('script', ''))
            self.spell_desc_var.set(spell.get('description', ''))
    
    def _add_spellcard(self):
        """添加符卡"""
        spells = self.config.setdefault('spellcards', [])
        spells.append({
            'name': '新符卡',
            'cost': 100,
            'script': '',
            'description': ''
        })
        self._refresh_spell_list()
    
    def _delete_spellcard(self):
        """删除符卡"""
        selection = self.spell_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        spells = self.config.get('spellcards', [])
        
        if idx < len(spells):
            del spells[idx]
            self._refresh_spell_list()
    
    def _apply_spell_changes(self):
        """应用符卡更改"""
        selection = self.spell_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        spells = self.config.get('spellcards', [])
        
        if idx < len(spells):
            spells[idx] = {
                'name': self.spell_name_var.get(),
                'cost': self.spell_cost_var.get(),
                'script': self.spell_script_var.get(),
                'description': self.spell_desc_var.get()
            }
            self._refresh_spell_list()
    
    # ============ 精灵选择 ============
    
    def _on_sprite_select(self, event):
        """精灵选择事件"""
        selection = self.sprite_listbox.curselection()
        if not selection:
            return
        
        sprite_id = self.sprite_listbox.get(selection[0])
        
        # 显示该精灵
        if sprite_id in self.sprite_rects and self.texture_image:
            rect = self.sprite_rects[sprite_id]
            frame_img = self.texture_image.crop((
                rect[0], rect[1],
                rect[0] + rect[2], rect[1] + rect[3]
            ))
            self.animation_frames = [frame_img]
            self.current_frame_idx = 0
            self._update_frame_label()
            self._refresh_preview()
    
    def _on_sprite_double_click(self, event):
        """精灵双击事件 - 复制ID"""
        selection = self.sprite_listbox.curselection()
        if not selection:
            return
        
        sprite_id = self.sprite_listbox.get(selection[0])
        self.root.clipboard_clear()
        self.root.clipboard_append(sprite_id)
        
        # 显示提示
        messagebox.showinfo("已复制", f"精灵ID已复制到剪贴板:\n{sprite_id}")


def main():
    root = tk.Tk()
    app = PlayerConfigEditor(root)
    root.mainloop()


if __name__ == '__main__':
    main()
