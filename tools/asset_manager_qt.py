#!/usr/bin/env python3
"""
PyQt5 纹理资产管理器 - 引擎集成版
直接使用游戏引擎的统一纹理管理系统

功能:
- 直接读取与游戏引擎相同的资源配置
- 所有修改即时同步到引擎
- 保存直接写入引擎使用的JSON配置
- 支持所有资产类型：子弹、激光、玩家、敌人、道具、背景、UI
- 可视化编辑精灵区域、中心点、碰撞半径
- 动画预览和帧编辑
- 激光三段式预览（head/body/tail）
- 16色变体组管理

作者: STG Engine Team
"""

import sys
import os
import json
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QGroupBox, QFormLayout, QScrollArea, QFrame, QTabWidget,
    QFileDialog, QMessageBox, QToolBar, QAction, QStatusBar, QMenu,
    QDialog, QDialogButtonBox, QRadioButton, QButtonGroup, QSlider,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem,
    QStyle, QSizePolicy, QToolButton, QHeaderView, QTableWidget, QTableWidgetItem
)
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QSize, pyqtSignal
from PyQt5.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush, QFont, 
    QIcon, QKeySequence, QTransform, QWheelEvent, QMouseEvent
)

# 添加项目根目录到路径，以便导入引擎模块
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 尝试导入引擎的统一纹理系统
try:
    from src.resource.unified_texture import (
        UnifiedTextureManager, TextureSheet, TextureRegion,
        AssetType, BaseAsset, SpriteAsset, AnimationAsset,
        LaserAsset, BentLaserAsset, ColorVariantGroup, PlayerAsset
    )
    HAS_ENGINE = True
except ImportError as e:
    print(f"警告: 无法导入引擎纹理系统: {e}")
    print("编辑器需要引擎模块才能运行")
    HAS_ENGINE = False

# 常量
ASSETS_ROOT = PROJECT_ROOT / "assets"
IMAGES_ROOT = ASSETS_ROOT / "images"


class ZoomableGraphicsView(QGraphicsView):
    """支持缩放和平移的图形视图"""
    
    zoom_changed = pyqtSignal(float)
    mouse_moved = pyqtSignal(int, int)
    rect_drawn = pyqtSignal(QRectF)
    canvas_clicked = pyqtSignal(float, float, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor(45, 45, 45)))
        
        self._zoom = 1.0
        self._is_drawing = False
        self._draw_start = None
        self._current_rect = None
        self._mode = "select"
    
    @property
    def zoom(self):
        return self._zoom
    
    @zoom.setter
    def zoom(self, value):
        self._zoom = max(0.1, min(value, 10.0))
        self.setTransform(QTransform().scale(self._zoom, self._zoom))
        self.zoom_changed.emit(self._zoom)
    
    def set_mode(self, mode: str):
        """设置编辑模式"""
        self._mode = mode
        if mode == "select":
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.ArrowCursor)
        elif mode == "draw_rect":
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
        elif mode == "edit_center":
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.PointingHandCursor)
    
    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.zoom *= factor
    
    def mousePressEvent(self, event: QMouseEvent):
        if self._mode == "draw_rect" and event.button() == Qt.LeftButton:
            self._is_drawing = True
            self._draw_start = self.mapToScene(event.pos())
            
            if self._current_rect:
                self.scene().removeItem(self._current_rect)
            
            self._current_rect = QGraphicsRectItem()
            self._current_rect.setPen(QPen(QColor(255, 100, 100), 2, Qt.DashLine))
            self._current_rect.setBrush(QBrush(QColor(255, 100, 100, 50)))
            self.scene().addItem(self._current_rect)
        elif self._mode in ("select", "edit_center") and event.button() == Qt.LeftButton:
            pos = self.mapToScene(event.pos())
            self.canvas_clicked.emit(pos.x(), pos.y(), int(event.button()))
            if self._mode == "select":
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        pos = self.mapToScene(event.pos())
        self.mouse_moved.emit(int(pos.x()), int(pos.y()))
        
        if self._is_drawing and self._draw_start:
            rect = QRectF(self._draw_start, pos).normalized()
            self._current_rect.setRect(rect)
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._is_drawing and self._mode == "draw_rect":
            self._is_drawing = False
            if self._current_rect:
                rect = self._current_rect.rect()
                if rect.width() > 2 and rect.height() > 2:
                    self.rect_drawn.emit(rect)
                self.scene().removeItem(self._current_rect)
                self._current_rect = None
        else:
            super().mouseReleaseEvent(event)
    
    def fit_in_view(self):
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoom_changed.emit(self._zoom)
    
    def reset_zoom(self):
        self.zoom = 1.0


class EngineIntegratedAssetManager(QMainWindow):
    """
    引擎集成资产管理器
    直接使用 UnifiedTextureManager 加载和管理资源
    """
    
    def __init__(self):
        super().__init__()
        
        if not HAS_ENGINE:
            QMessageBox.critical(None, "错误", "无法导入引擎模块，编辑器无法启动")
            sys.exit(1)
        
        # 引擎纹理管理器 - 核心！
        self.engine = UnifiedTextureManager(str(ASSETS_ROOT))
        
        # 当前选中的纹理表和资产
        self.current_sheet: Optional[TextureSheet] = None
        self.current_sheet_name: Optional[str] = None
        self.current_config_path: Optional[str] = None
        
        # 选中项
        self.selected_asset_name: Optional[str] = None
        self.selected_asset_type: Optional[str] = None  # 'sprite', 'animation', 'laser', 'bent_laser'
        
        # 修改追踪
        self.is_modified = False
        self._pending_changes: Dict[str, Any] = {}
        
        # 动画状态
        self.animation_playing = False
        self.animation_frame = 0
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animation)
        
        # 图形项缓存
        self._rect_items: Dict[str, QGraphicsRectItem] = {}
        self._center_items: Dict[str, QGraphicsEllipseItem] = {}
        self._grid_items: List[QGraphicsLineItem] = []
        self._label_items: List[QGraphicsTextItem] = []
        
        # 点击检测
        self._hit_rects: List[Tuple[int, str, str, Tuple[int, int, int, int], Optional[int]]] = []
        
        # 复制粘贴
        self._rect_clipboard: Optional[Tuple[int, int, int, int]] = None
        
        # 编辑模式
        self._current_mode = "select"
        
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._apply_theme()
        
        self.setWindowTitle("纹理资产管理器 - 引擎集成版")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)
        
        # 自动发现并加载所有配置
        self._discover_all_configs()
        self._refresh_asset_tree()
    
    def _setup_ui(self):
        """设置UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 主分割器
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # 左侧面板 - 资产浏览器（引擎视角）
        left_panel = self._create_left_panel()
        self.main_splitter.addWidget(left_panel)
        
        # 中间面板 - 纹理预览
        center_panel = self._create_center_panel()
        self.main_splitter.addWidget(center_panel)
        
        # 右侧面板 - 属性编辑
        right_panel = self._create_right_panel()
        self.main_splitter.addWidget(right_panel)
        
        self.main_splitter.setSizes([320, 750, 350])
        
        self.statusBar().showMessage("引擎集成模式 - 所有更改将直接同步到游戏")
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧面板 - 引擎资产浏览器"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 引擎状态
        status_group = QGroupBox("引擎状态")
        status_layout = QVBoxLayout(status_group)
        
        self.engine_status_label = QLabel("✓ 引擎已连接")
        self.engine_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        status_layout.addWidget(self.engine_status_label)
        
        stats_label = QLabel()
        stats_label.setWordWrap(True)
        self.stats_label = stats_label
        status_layout.addWidget(stats_label)
        
        btn_reload = QPushButton("🔄 重新加载所有资源")
        btn_reload.clicked.connect(self._reload_all_configs)
        status_layout.addWidget(btn_reload)
        
        layout.addWidget(status_group)
        
        # 资产树（按纹理表组织）
        tree_group = QGroupBox("资产浏览器 (引擎视角)")
        tree_layout = QVBoxLayout(tree_group)
        
        # 搜索框
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索资产...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_edit)
        tree_layout.addLayout(search_layout)
        
        # 资产树
        self.asset_tree = QTreeWidget()
        self.asset_tree.setHeaderLabels(["名称", "类型", "尺寸"])
        self.asset_tree.setColumnWidth(0, 180)
        self.asset_tree.setColumnWidth(1, 60)
        self.asset_tree.setColumnWidth(2, 60)
        self.asset_tree.itemClicked.connect(self._on_asset_tree_clicked)
        self.asset_tree.itemDoubleClicked.connect(self._on_asset_tree_double_clicked)
        tree_layout.addWidget(self.asset_tree)
        
        layout.addWidget(tree_group, stretch=1)
        
        return panel
    
    def _create_center_panel(self) -> QWidget:
        """创建中间面板 - 纹理预览"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 图形视图
        self.scene = QGraphicsScene()
        self.view = ZoomableGraphicsView(self.scene)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.mouse_moved.connect(self._on_mouse_moved)
        self.view.rect_drawn.connect(self._on_rect_drawn)
        self.view.canvas_clicked.connect(self._on_canvas_clicked)
        
        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)
        
        # 模式选择
        toolbar.addWidget(QLabel("模式:"))
        
        self.mode_group = QButtonGroup(self)
        modes = [("选择", "select"), ("绘制矩形", "draw_rect"), ("编辑中心点", "edit_center")]
        
        for text, mode in modes:
            rb = QRadioButton(text)
            rb.setProperty("mode", mode)
            rb.toggled.connect(self._on_mode_changed)
            self.mode_group.addButton(rb)
            toolbar.addWidget(rb)
            if mode == "select":
                rb.setChecked(True)
        
        toolbar.addStretch()
        
        # 缩放控制
        toolbar.addWidget(QLabel("缩放:"))
        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedWidth(30)
        btn_zoom_out.clicked.connect(lambda: self._zoom(0.8))
        toolbar.addWidget(btn_zoom_out)
        
        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(60)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        toolbar.addWidget(self.zoom_label)
        
        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedWidth(30)
        btn_zoom_in.clicked.connect(lambda: self._zoom(1.25))
        toolbar.addWidget(btn_zoom_in)
        
        btn_fit = QPushButton("适应")
        btn_fit.clicked.connect(self._fit_view)
        toolbar.addWidget(btn_fit)
        
        toolbar.addStretch()
        
        # 显示选项
        self.show_grid_cb = QCheckBox("网格")
        self.show_grid_cb.setChecked(True)
        self.show_grid_cb.toggled.connect(self._refresh_canvas)
        toolbar.addWidget(self.show_grid_cb)
        
        self.show_all_cb = QCheckBox("所有区域")
        self.show_all_cb.setChecked(True)
        self.show_all_cb.toggled.connect(self._refresh_canvas)
        toolbar.addWidget(self.show_all_cb)
        
        self.show_labels_cb = QCheckBox("名称")
        self.show_labels_cb.setChecked(False)
        self.show_labels_cb.toggled.connect(self._refresh_canvas)
        toolbar.addWidget(self.show_labels_cb)
        
        layout.addLayout(toolbar)
        layout.addWidget(self.view)
        
        # 坐标显示
        coord_bar = QHBoxLayout()
        coord_bar.setContentsMargins(5, 2, 5, 2)
        self.coord_label = QLabel("坐标: -")
        coord_bar.addWidget(self.coord_label)
        coord_bar.addStretch()
        self.info_label = QLabel("")
        coord_bar.addWidget(self.info_label)
        layout.addLayout(coord_bar)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板 - 属性编辑"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # 当前资产信息
        info_group = QGroupBox("当前资产")
        info_layout = QFormLayout(info_group)
        
        self.asset_name_label = QLabel("-")
        self.asset_name_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        info_layout.addRow("名称:", self.asset_name_label)
        
        self.asset_type_label = QLabel("-")
        info_layout.addRow("类型:", self.asset_type_label)
        
        self.asset_sheet_label = QLabel("-")
        info_layout.addRow("纹理表:", self.asset_sheet_label)
        
        scroll_layout.addWidget(info_group)
        
        # 精灵属性
        self.sprite_props_group = QGroupBox("精灵属性")
        sprite_form = QFormLayout(self.sprite_props_group)
        
        # Rect
        rect_widget = QWidget()
        rect_layout = QHBoxLayout(rect_widget)
        rect_layout.setContentsMargins(0, 0, 0, 0)
        
        self.rect_x = QSpinBox()
        self.rect_x.setRange(0, 9999)
        self.rect_x.valueChanged.connect(self._on_rect_changed)
        self.rect_y = QSpinBox()
        self.rect_y.setRange(0, 9999)
        self.rect_y.valueChanged.connect(self._on_rect_changed)
        self.rect_w = QSpinBox()
        self.rect_w.setRange(1, 9999)
        self.rect_w.valueChanged.connect(self._on_rect_changed)
        self.rect_h = QSpinBox()
        self.rect_h.setRange(1, 9999)
        self.rect_h.valueChanged.connect(self._on_rect_changed)
        
        rect_layout.addWidget(QLabel("X:"))
        rect_layout.addWidget(self.rect_x)
        rect_layout.addWidget(QLabel("Y:"))
        rect_layout.addWidget(self.rect_y)
        rect_layout.addWidget(QLabel("W:"))
        rect_layout.addWidget(self.rect_w)
        rect_layout.addWidget(QLabel("H:"))
        rect_layout.addWidget(self.rect_h)
        
        sprite_form.addRow("区域:", rect_widget)
        
        # Center
        center_widget = QWidget()
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        self.center_x = QDoubleSpinBox()
        self.center_x.setRange(-999, 999)
        self.center_x.setSingleStep(0.5)
        self.center_x.valueChanged.connect(self._on_center_changed)
        self.center_y = QDoubleSpinBox()
        self.center_y.setRange(-999, 999)
        self.center_y.setSingleStep(0.5)
        self.center_y.valueChanged.connect(self._on_center_changed)
        
        btn_center = QPushButton("居中")
        btn_center.clicked.connect(self._center_sprite)
        
        center_layout.addWidget(QLabel("X:"))
        center_layout.addWidget(self.center_x)
        center_layout.addWidget(QLabel("Y:"))
        center_layout.addWidget(self.center_y)
        center_layout.addWidget(btn_center)
        
        sprite_form.addRow("中心点:", center_widget)
        
        # Radius
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0, 999)
        self.radius_spin.setSingleStep(0.5)
        self.radius_spin.valueChanged.connect(self._on_radius_changed)
        sprite_form.addRow("碰撞半径:", self.radius_spin)
        
        # Rotate
        self.rotate_cb = QCheckBox("跟随方向旋转")
        self.rotate_cb.toggled.connect(self._on_rotate_changed)
        sprite_form.addRow("", self.rotate_cb)
        
        scroll_layout.addWidget(self.sprite_props_group)
        
        # 动画属性
        self.anim_props_group = QGroupBox("动画属性")
        anim_form = QFormLayout(self.anim_props_group)
        
        self.frame_duration_spin = QSpinBox()
        self.frame_duration_spin.setRange(1, 999)
        self.frame_duration_spin.setValue(5)
        self.frame_duration_spin.valueChanged.connect(self._on_frame_duration_changed)
        anim_form.addRow("帧时长(游戏帧):", self.frame_duration_spin)
        
        self.anim_loop_cb = QCheckBox("循环播放")
        self.anim_loop_cb.setChecked(True)
        self.anim_loop_cb.toggled.connect(self._on_anim_loop_changed)
        anim_form.addRow("", self.anim_loop_cb)
        
        # 帧列表
        self.frame_list = QListWidget()
        self.frame_list.setMaximumHeight(120)
        self.frame_list.itemClicked.connect(self._on_frame_clicked)
        anim_form.addRow("帧列表:", self.frame_list)
        
        frame_btn_widget = QWidget()
        frame_btn_layout = QHBoxLayout(frame_btn_widget)
        frame_btn_layout.setContentsMargins(0, 0, 0, 0)
        
        btn_add_frame = QPushButton("+ 帧")
        btn_add_frame.clicked.connect(self._add_frame)
        btn_del_frame = QPushButton("删除帧")
        btn_del_frame.clicked.connect(self._delete_frame)
        
        frame_btn_layout.addWidget(btn_add_frame)
        frame_btn_layout.addWidget(btn_del_frame)
        
        anim_form.addRow("", frame_btn_widget)
        
        scroll_layout.addWidget(self.anim_props_group)
        
        # 动画预览
        preview_group = QGroupBox("动画预览")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(128, 128)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #1a1a1a; border: 1px solid #333;")
        preview_layout.addWidget(self.preview_label, alignment=Qt.AlignCenter)
        
        preview_ctrl = QHBoxLayout()
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.clicked.connect(self._toggle_animation)
        btn_prev = QPushButton("◀")
        btn_prev.setFixedWidth(30)
        btn_prev.clicked.connect(self._prev_frame)
        btn_next = QPushButton("▶")
        btn_next.setFixedWidth(30)
        btn_next.clicked.connect(self._next_frame)
        
        preview_ctrl.addWidget(self.play_btn)
        preview_ctrl.addWidget(btn_prev)
        preview_ctrl.addWidget(btn_next)
        preview_layout.addLayout(preview_ctrl)
        
        self.frame_info_label = QLabel("帧: 0/0")
        self.frame_info_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.frame_info_label)
        
        scroll_layout.addWidget(preview_group)
        
        # 激光属性
        self.laser_props_group = QGroupBox("激光属性")
        laser_form = QFormLayout(self.laser_props_group)
        
        self.laser_color_label = QLabel("-")
        laser_form.addRow("颜色:", self.laser_color_label)
        
        # Head/Body/Tail
        for part, label in [('head', '头部'), ('body', '身体'), ('tail', '尾部')]:
            part_widget = QWidget()
            part_layout = QHBoxLayout(part_widget)
            part_layout.setContentsMargins(0, 0, 0, 0)
            
            x_spin = QSpinBox()
            x_spin.setRange(0, 9999)
            y_spin = QSpinBox()
            y_spin.setRange(0, 9999)
            w_spin = QSpinBox()
            w_spin.setRange(1, 9999)
            h_spin = QSpinBox()
            h_spin.setRange(1, 9999)
            
            part_layout.addWidget(QLabel("X:"))
            part_layout.addWidget(x_spin)
            part_layout.addWidget(QLabel("Y:"))
            part_layout.addWidget(y_spin)
            part_layout.addWidget(QLabel("W:"))
            part_layout.addWidget(w_spin)
            part_layout.addWidget(QLabel("H:"))
            part_layout.addWidget(h_spin)
            
            setattr(self, f'laser_{part}_x', x_spin)
            setattr(self, f'laser_{part}_y', y_spin)
            setattr(self, f'laser_{part}_w', w_spin)
            setattr(self, f'laser_{part}_h', h_spin)
            
            laser_form.addRow(f"{label}:", part_widget)
        
        scroll_layout.addWidget(self.laser_props_group)
        
        # 批量工具
        batch_group = QGroupBox("批量工具")
        batch_layout = QVBoxLayout(batch_group)
        
        btn_copy_rect = QPushButton("复制当前区域")
        btn_copy_rect.clicked.connect(self._copy_rect)
        batch_layout.addWidget(btn_copy_rect)
        
        btn_paste_rect = QPushButton("粘贴到当前")
        btn_paste_rect.clicked.connect(self._paste_rect)
        batch_layout.addWidget(btn_paste_rect)
        
        btn_grid = QPushButton("生成网格 (N×M)")
        btn_grid.clicked.connect(self._open_grid_dialog)
        batch_layout.addWidget(btn_grid)
        
        scroll_layout.addWidget(batch_group)
        
        # 保存按钮
        save_group = QGroupBox("保存")
        save_layout = QVBoxLayout(save_group)
        
        self.save_btn = QPushButton("💾 保存到引擎配置")
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.save_btn.clicked.connect(self._save_current_config)
        save_layout.addWidget(self.save_btn)
        
        self.save_status_label = QLabel("未修改")
        self.save_status_label.setAlignment(Qt.AlignCenter)
        save_layout.addWidget(self.save_status_label)
        
        scroll_layout.addWidget(save_group)
        
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        # 初始隐藏属性面板
        self.sprite_props_group.setVisible(False)
        self.anim_props_group.setVisible(False)
        self.laser_props_group.setVisible(False)
        
        return panel
    
    def _setup_menu(self):
        """设置菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        reload_action = QAction("🔄 重新加载所有配置", self)
        reload_action.setShortcut(QKeySequence("Ctrl+R"))
        reload_action.triggered.connect(self._reload_all_configs)
        file_menu.addAction(reload_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("💾 保存当前配置(&S)", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_current_config)
        file_menu.addAction(save_action)
        
        save_all_action = QAction("保存所有修改", self)
        save_all_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_all_action.triggered.connect(self._save_all_configs)
        file_menu.addAction(save_all_action)
        
        file_menu.addSeparator()
        
        new_config_action = QAction("新建配置文件...", self)
        new_config_action.triggered.connect(self._new_config)
        file_menu.addAction(new_config_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")
        
        add_sprite_action = QAction("添加精灵", self)
        add_sprite_action.triggered.connect(self._add_sprite)
        edit_menu.addAction(add_sprite_action)
        
        add_anim_action = QAction("添加动画", self)
        add_anim_action.triggered.connect(self._add_animation)
        edit_menu.addAction(add_anim_action)
        
        edit_menu.addSeparator()
        
        del_action = QAction("删除选中", self)
        del_action.setShortcut(QKeySequence.Delete)
        del_action.triggered.connect(self._delete_selected)
        edit_menu.addAction(del_action)
        
        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")
        
        zoom_in_action = QAction("放大", self)
        zoom_in_action.setShortcut(QKeySequence("="))
        zoom_in_action.triggered.connect(lambda: self._zoom(1.25))
        view_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("缩小", self)
        zoom_out_action.setShortcut(QKeySequence("-"))
        zoom_out_action.triggered.connect(lambda: self._zoom(0.8))
        view_menu.addAction(zoom_out_action)
        
        fit_action = QAction("适应窗口", self)
        fit_action.setShortcut(QKeySequence("F"))
        fit_action.triggered.connect(self._fit_view)
        view_menu.addAction(fit_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_toolbar(self):
        """设置工具栏"""
        toolbar = self.addToolBar("主工具栏")
        toolbar.addAction("🔄 重载", self._reload_all_configs)
        toolbar.addAction("💾 保存", self._save_current_config)
        toolbar.addSeparator()
        toolbar.addAction("+ 精灵", self._add_sprite)
        toolbar.addAction("+ 动画", self._add_animation)
    
    def _apply_theme(self):
        """应用暗色主题"""
        style = """
        QMainWindow, QWidget {
            background-color: #2b2b2b;
            color: #e0e0e0;
            font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
            font-size: 9pt;
        }
        QGroupBox {
            border: 1px solid #4d4d4d;
            border-radius: 4px;
            margin-top: 1.5ex;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            left: 10px;
            color: #aaa;
        }
        QPushButton {
            background-color: #3d3d3d;
            border: 1px solid #555;
            border-radius: 3px;
            padding: 5px 12px;
            min-height: 20px;
        }
        QPushButton:hover {
            background-color: #505050;
            border-color: #666;
        }
        QPushButton:pressed {
            background-color: #252525;
        }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            background-color: #1e1e1e;
            border: 1px solid #444;
            border-radius: 3px;
            padding: 3px;
            color: #fff;
            selection-background-color: #007acc;
        }
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
            border: 1px solid #007acc;
        }
        QListWidget, QTreeWidget {
            background-color: #1e1e1e;
            border: 1px solid #3d3d3d;
            outline: none;
        }
        QListWidget::item, QTreeWidget::item {
            padding: 4px;
        }
        QListWidget::item:selected, QTreeWidget::item:selected {
            background-color: #007acc;
            color: #fff;
        }
        QListWidget::item:hover, QTreeWidget::item:hover {
            background-color: #2d2d2d;
        }
        QTabWidget::pane {
            border: 1px solid #3d3d3d;
            background-color: #2b2b2b;
        }
        QTabBar::tab {
            background-color: #1e1e1e;
            color: #aaa;
            padding: 6px 14px;
            border: 1px solid #3d3d3d;
            border-bottom: none;
            border-top-left-radius: 3px;
            border-top-right-radius: 3px;
        }
        QTabBar::tab:selected {
            background-color: #2b2b2b;
            color: #fff;
        }
        QSplitter::handle {
            background-color: #1e1e1e;
        }
        QSplitter::handle:hover {
            background-color: #007acc;
        }
        QScrollBar:vertical {
            background-color: #1e1e1e;
            width: 14px;
        }
        QScrollBar::handle:vertical {
            background-color: #4d4d4d;
            min-height: 20px;
            border-radius: 2px;
            margin: 2px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #666;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            background-color: #1e1e1e;
            height: 14px;
        }
        QScrollBar::handle:horizontal {
            background-color: #4d4d4d;
            min-width: 20px;
            border-radius: 2px;
            margin: 2px;
        }
        QMenu {
            background-color: #2b2b2b;
            border: 1px solid #4d4d4d;
        }
        QMenu::item {
            padding: 5px 20px;
        }
        QMenu::item:selected {
            background-color: #007acc;
        }
        QMenuBar {
            background-color: #1e1e1e;
            border-bottom: 1px solid #3d3d3d;
        }
        QMenuBar::item:selected {
            background-color: #3d3d3d;
        }
        QToolBar {
            background-color: #1e1e1e;
            border-bottom: 1px solid #3d3d3d;
            spacing: 5px;
            padding: 3px;
        }
        QHeaderView::section {
            background-color: #1e1e1e;
            color: #e0e0e0;
            padding: 4px;
            border: 1px solid #3d3d3d;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #555;
            background: #1e1e1e;
            border-radius: 3px;
        }
        QCheckBox::indicator:checked {
            background: #007acc;
            border-color: #007acc;
        }
        QRadioButton::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #555;
            background: #1e1e1e;
            border-radius: 9px;
        }
        QRadioButton::indicator:checked {
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.4, fx:0.5, fy:0.5, stop:0 #fff, stop:1 #007acc);
            border-color: #007acc;
        }
        """
        self.setStyleSheet(style)
    
    # ==================== 引擎集成 ====================
    
    def _discover_all_configs(self):
        """自动发现所有配置文件"""
        config_patterns = [
            "images/bullet/*.json",
            "images/laser/*.json",
            "images/item/*.json",
            "images/enemy/*.json",
            "images/background/*.json",
            "images/ui/*.json",
            "players/*/*.json",
        ]
        
        for pattern in config_patterns:
            for config_file in ASSETS_ROOT.glob(pattern):
                relative_path = config_file.relative_to(ASSETS_ROOT)
                try:
                    self.engine.load_config(str(relative_path))
                except Exception as e:
                    print(f"加载配置失败 {relative_path}: {e}")
        
        self._update_stats()
    
    def _reload_all_configs(self):
        """重新加载所有配置"""
        # 重建引擎
        self.engine = UnifiedTextureManager(str(ASSETS_ROOT))
        self._discover_all_configs()
        self._refresh_asset_tree()
        self.statusBar().showMessage("已重新加载所有配置")
    
    def _update_stats(self):
        """更新统计信息"""
        stats = (
            f"纹理表: {len(self.engine.sheets)}\n"
            f"精灵: {len(self.engine.all_sprites)}\n"
            f"动画: {len(self.engine.all_animations)}\n"
            f"激光: {len(self.engine.all_lasers)}\n"
            f"曲线激光: {len(self.engine.all_bent_lasers)}\n"
            f"颜色组: {len(self.engine.all_color_groups)}\n"
            f"玩家: {len(self.engine.all_players)}"
        )
        self.stats_label.setText(stats)
    
    def _refresh_asset_tree(self):
        """刷新资产树"""
        self.asset_tree.clear()
        
        # 按纹理表组织
        for sheet_name, sheet in sorted(self.engine.sheets.items()):
            sheet_item = QTreeWidgetItem(self.asset_tree)
            sheet_item.setText(0, f"📦 {sheet_name}")
            sheet_item.setText(1, "纹理表")
            sheet_item.setData(0, Qt.UserRole, ('sheet', sheet_name))
            
            # 精灵
            if sheet.sprites:
                sprites_item = QTreeWidgetItem(sheet_item)
                sprites_item.setText(0, f"精灵 ({len(sheet.sprites)})")
                sprites_item.setData(0, Qt.UserRole, ('category', 'sprites', sheet_name))
                
                for sprite_name, sprite in sorted(sheet.sprites.items()):
                    sprite_item = QTreeWidgetItem(sprites_item)
                    sprite_item.setText(0, sprite_name)
                    sprite_item.setText(1, "精灵")
                    if sprite.region:
                        sprite_item.setText(2, f"{sprite.region.width}x{sprite.region.height}")
                    sprite_item.setData(0, Qt.UserRole, ('sprite', sprite_name, sheet_name))
            
            # 动画
            if sheet.animations:
                anims_item = QTreeWidgetItem(sheet_item)
                anims_item.setText(0, f"动画 ({len(sheet.animations)})")
                anims_item.setData(0, Qt.UserRole, ('category', 'animations', sheet_name))
                
                for anim_name, anim in sorted(sheet.animations.items()):
                    anim_item = QTreeWidgetItem(anims_item)
                    anim_item.setText(0, anim_name)
                    anim_item.setText(1, "动画")
                    anim_item.setText(2, f"{len(anim.frames)}帧")
                    anim_item.setData(0, Qt.UserRole, ('animation', anim_name, sheet_name))
            
            # 激光
            if sheet.lasers:
                lasers_item = QTreeWidgetItem(sheet_item)
                lasers_item.setText(0, f"激光 ({len(sheet.lasers)})")
                lasers_item.setData(0, Qt.UserRole, ('category', 'lasers', sheet_name))
                
                for laser_name, laser in sorted(sheet.lasers.items()):
                    laser_item = QTreeWidgetItem(lasers_item)
                    laser_item.setText(0, laser_name)
                    laser_item.setText(1, "激光")
                    laser_item.setData(0, Qt.UserRole, ('laser', laser_name, sheet_name))
            
            # 曲线激光
            if sheet.bent_lasers:
                bent_item = QTreeWidgetItem(sheet_item)
                bent_item.setText(0, f"曲线激光 ({len(sheet.bent_lasers)})")
                bent_item.setData(0, Qt.UserRole, ('category', 'bent_lasers', sheet_name))
                
                for bent_name, bent in sorted(sheet.bent_lasers.items()):
                    b_item = QTreeWidgetItem(bent_item)
                    b_item.setText(0, bent_name)
                    b_item.setText(1, "曲线激光")
                    b_item.setData(0, Qt.UserRole, ('bent_laser', bent_name, sheet_name))
            
            # 颜色组
            if sheet.color_groups:
                groups_item = QTreeWidgetItem(sheet_item)
                groups_item.setText(0, f"颜色组 ({len(sheet.color_groups)})")
                groups_item.setData(0, Qt.UserRole, ('category', 'color_groups', sheet_name))
                
                for group_name, group in sorted(sheet.color_groups.items()):
                    g_item = QTreeWidgetItem(groups_item)
                    g_item.setText(0, group_name)
                    g_item.setText(1, f"{len(group.variants)}色")
                    g_item.setData(0, Qt.UserRole, ('color_group', group_name, sheet_name))
    
    def _on_search_changed(self, text: str):
        """搜索文本变化"""
        text = text.lower()
        
        def set_visible(item: QTreeWidgetItem, visible: bool):
            item.setHidden(not visible)
        
        def search_item(item: QTreeWidgetItem) -> bool:
            """递归搜索，返回是否匹配"""
            match = text in item.text(0).lower()
            
            child_match = False
            for i in range(item.childCount()):
                if search_item(item.child(i)):
                    child_match = True
            
            visible = match or child_match
            set_visible(item, visible)
            
            if visible:
                item.setExpanded(True)
            
            return visible
        
        if not text:
            # 清空搜索，显示所有
            for i in range(self.asset_tree.topLevelItemCount()):
                item = self.asset_tree.topLevelItem(i)
                set_visible(item, True)
                item.setExpanded(False)
        else:
            for i in range(self.asset_tree.topLevelItemCount()):
                search_item(self.asset_tree.topLevelItem(i))
    
    def _on_asset_tree_clicked(self, item: QTreeWidgetItem, column: int):
        """资产树点击"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        
        if data[0] == 'sheet':
            # 点击纹理表
            sheet_name = data[1]
            self._load_sheet(sheet_name)
        elif data[0] == 'sprite':
            _, sprite_name, sheet_name = data
            self._load_sheet(sheet_name)
            self._select_asset('sprite', sprite_name)
        elif data[0] == 'animation':
            _, anim_name, sheet_name = data
            self._load_sheet(sheet_name)
            self._select_asset('animation', anim_name)
        elif data[0] == 'laser':
            _, laser_name, sheet_name = data
            self._load_sheet(sheet_name)
            self._select_asset('laser', laser_name)
        elif data[0] == 'bent_laser':
            _, bent_name, sheet_name = data
            self._load_sheet(sheet_name)
            self._select_asset('bent_laser', bent_name)
    
    def _on_asset_tree_double_clicked(self, item: QTreeWidgetItem, column: int):
        """资产树双击 - 展开/折叠或聚焦"""
        data = item.data(0, Qt.UserRole)
        if data and data[0] in ('sprite', 'animation', 'laser', 'bent_laser'):
            # 双击聚焦到该资产
            self._fit_view()
    
    def _load_sheet(self, sheet_name: str):
        """加载纹理表"""
        sheet = self.engine.sheets.get(sheet_name)
        if not sheet:
            return
        
        self.current_sheet = sheet
        self.current_sheet_name = sheet_name
        
        # 查找对应的配置文件路径
        self.current_config_path = self._find_config_path(sheet_name)
        
        # 加载纹理图片
        if sheet.surface:
            self._load_texture_from_surface(sheet.surface)
        elif sheet.path:
            self._load_texture_file(sheet.path)
        
        self.info_label.setText(f"纹理表: {sheet_name} ({sheet.width}x{sheet.height})")
    
    def _find_config_path(self, sheet_name: str) -> Optional[str]:
        """查找纹理表对应的配置文件路径"""
        # 根据纹理表名称推断配置文件路径
        possible_paths = [
            f"images/bullet/{sheet_name}.json",
            f"images/laser/{sheet_name}.json",
            f"images/item/{sheet_name}.json",
            f"images/enemy/{sheet_name}.json",
            f"images/background/{sheet_name}.json",
            f"players/reimu/{sheet_name}.json",
            f"players/sakuya/{sheet_name}.json",
        ]
        
        for path in possible_paths:
            full_path = ASSETS_ROOT / path
            if full_path.exists():
                return str(full_path)
        
        # 尝试从纹理路径推断
        if self.current_sheet and self.current_sheet.path:
            tex_path = Path(self.current_sheet.path)
            json_path = tex_path.with_suffix('.json')
            if json_path.exists():
                return str(json_path)
        
        return None
    
    def _load_texture_from_surface(self, surface):
        """从pygame Surface加载纹理"""
        try:
            # 转换pygame surface到QPixmap
            import pygame
            data = pygame.image.tostring(surface, 'RGBA')
            width, height = surface.get_size()
            
            qimage = QImage(data, width, height, QImage.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimage)
            
            self.scene.clear()
            self._rect_items.clear()
            self._center_items.clear()
            
            texture_item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(texture_item)
            self.scene.setSceneRect(0, 0, width, height)
            
            self._refresh_canvas()
        except Exception as e:
            print(f"加载纹理失败: {e}")
    
    def _load_texture_file(self, path: str):
        """从文件加载纹理"""
        if not Path(path).exists():
            return
        
        try:
            pixmap = QPixmap(path)
            
            self.scene.clear()
            self._rect_items.clear()
            self._center_items.clear()
            
            texture_item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(texture_item)
            self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
            
            self._refresh_canvas()
        except Exception as e:
            print(f"加载纹理失败: {e}")
    
    def _select_asset(self, asset_type: str, asset_name: str):
        """选中资产"""
        self.selected_asset_type = asset_type
        self.selected_asset_name = asset_name
        self.animation_frame = 0
        
        self._update_properties_panel()
        self._refresh_canvas()
    
    def _update_properties_panel(self):
        """更新属性面板"""
        # 隐藏所有
        self.sprite_props_group.setVisible(False)
        self.anim_props_group.setVisible(False)
        self.laser_props_group.setVisible(False)
        
        if not self.selected_asset_name or not self.current_sheet:
            self.asset_name_label.setText("-")
            self.asset_type_label.setText("-")
            self.asset_sheet_label.setText("-")
            return
        
        self.asset_name_label.setText(self.selected_asset_name)
        self.asset_sheet_label.setText(self.current_sheet_name or "-")
        
        if self.selected_asset_type == 'sprite':
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite:
                self.asset_type_label.setText("精灵")
                self.sprite_props_group.setVisible(True)
                self._populate_sprite_props(sprite)
        
        elif self.selected_asset_type == 'animation':
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim:
                self.asset_type_label.setText(f"动画 ({len(anim.frames)}帧)")
                self.sprite_props_group.setVisible(True)
                self.anim_props_group.setVisible(True)
                self._populate_animation_props(anim)
        
        elif self.selected_asset_type == 'laser':
            laser = self.current_sheet.lasers.get(self.selected_asset_name)
            if laser:
                self.asset_type_label.setText("激光")
                self.laser_props_group.setVisible(True)
                self._populate_laser_props(laser)
        
        elif self.selected_asset_type == 'bent_laser':
            bent = self.current_sheet.bent_lasers.get(self.selected_asset_name)
            if bent:
                self.asset_type_label.setText("曲线激光")
                self.sprite_props_group.setVisible(True)
                self._populate_bent_laser_props(bent)
    
    def _populate_sprite_props(self, sprite: SpriteAsset):
        """填充精灵属性"""
        self._block_signals(True)
        
        if sprite.region:
            self.rect_x.setValue(sprite.region.x)
            self.rect_y.setValue(sprite.region.y)
            self.rect_w.setValue(sprite.region.width)
            self.rect_h.setValue(sprite.region.height)
            self.center_x.setValue(sprite.region.center_x)
            self.center_y.setValue(sprite.region.center_y)
        
        self.radius_spin.setValue(sprite.radius)
        self.rotate_cb.setChecked(sprite.rotate)
        
        self._block_signals(False)
    
    def _populate_animation_props(self, anim: AnimationAsset):
        """填充动画属性"""
        self._block_signals(True)
        
        self.frame_duration_spin.setValue(anim.frame_duration)
        self.anim_loop_cb.setChecked(anim.loop)
        
        # 帧列表
        self.frame_list.clear()
        for i, frame in enumerate(anim.frames):
            self.frame_list.addItem(f"帧 {i}: [{frame.x}, {frame.y}, {frame.width}, {frame.height}]")
        
        # 当前帧属性
        if 0 <= self.animation_frame < len(anim.frames):
            frame = anim.frames[self.animation_frame]
            self.rect_x.setValue(frame.x)
            self.rect_y.setValue(frame.y)
            self.rect_w.setValue(frame.width)
            self.rect_h.setValue(frame.height)
            self.center_x.setValue(frame.center_x)
            self.center_y.setValue(frame.center_y)
        
        self.frame_info_label.setText(f"帧: {self.animation_frame + 1}/{len(anim.frames)}")
        self._update_preview()
        
        self._block_signals(False)
    
    def _populate_laser_props(self, laser: LaserAsset):
        """填充激光属性"""
        self._block_signals(True)
        
        # 从名称提取颜色
        for color in ColorVariantGroup.STANDARD_COLORS:
            if color in self.selected_asset_name:
                self.laser_color_label.setText(color)
                break
        
        if laser.head:
            self.laser_head_x.setValue(laser.head.x)
            self.laser_head_y.setValue(laser.head.y)
            self.laser_head_w.setValue(laser.head.width)
            self.laser_head_h.setValue(laser.head.height)
        
        if laser.body:
            self.laser_body_x.setValue(laser.body.x)
            self.laser_body_y.setValue(laser.body.y)
            self.laser_body_w.setValue(laser.body.width)
            self.laser_body_h.setValue(laser.body.height)
        
        if laser.tail:
            self.laser_tail_x.setValue(laser.tail.x)
            self.laser_tail_y.setValue(laser.tail.y)
            self.laser_tail_w.setValue(laser.tail.width)
            self.laser_tail_h.setValue(laser.tail.height)
        
        self._block_signals(False)
    
    def _populate_bent_laser_props(self, bent: BentLaserAsset):
        """填充曲线激光属性"""
        self._block_signals(True)
        
        if bent.segment:
            self.rect_x.setValue(bent.segment.x)
            self.rect_y.setValue(bent.segment.y)
            self.rect_w.setValue(bent.segment.width)
            self.rect_h.setValue(bent.segment.height)
            self.center_x.setValue(bent.segment.center_x)
            self.center_y.setValue(bent.segment.center_y)
        
        self._block_signals(False)
    
    def _block_signals(self, block: bool):
        """批量阻止/恢复信号"""
        widgets = [
            self.rect_x, self.rect_y, self.rect_w, self.rect_h,
            self.center_x, self.center_y, self.radius_spin,
            self.rotate_cb, self.frame_duration_spin, self.anim_loop_cb
        ]
        for w in widgets:
            w.blockSignals(block)
    
    # ==================== 属性修改回调 ====================
    
    def _on_rect_changed(self):
        """区域修改"""
        if not self.selected_asset_name or not self.current_sheet:
            return
        
        x, y, w, h = self.rect_x.value(), self.rect_y.value(), self.rect_w.value(), self.rect_h.value()
        
        if self.selected_asset_type == 'sprite':
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite and sprite.region:
                sprite.region.x = x
                sprite.region.y = y
                sprite.region.width = w
                sprite.region.height = h
        
        elif self.selected_asset_type == 'animation':
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and 0 <= self.animation_frame < len(anim.frames):
                frame = anim.frames[self.animation_frame]
                frame.x = x
                frame.y = y
                frame.width = w
                frame.height = h
        
        elif self.selected_asset_type == 'bent_laser':
            bent = self.current_sheet.bent_lasers.get(self.selected_asset_name)
            if bent and bent.segment:
                bent.segment.x = x
                bent.segment.y = y
                bent.segment.width = w
                bent.segment.height = h
        
        self._mark_modified()
        self._refresh_canvas()
    
    def _on_center_changed(self):
        """中心点修改"""
        if not self.selected_asset_name or not self.current_sheet:
            return
        
        cx, cy = self.center_x.value(), self.center_y.value()
        
        if self.selected_asset_type == 'sprite':
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite and sprite.region:
                sprite.region.center_x = cx
                sprite.region.center_y = cy
        
        elif self.selected_asset_type == 'animation':
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and 0 <= self.animation_frame < len(anim.frames):
                frame = anim.frames[self.animation_frame]
                frame.center_x = cx
                frame.center_y = cy
        
        self._mark_modified()
        self._refresh_canvas()
    
    def _on_radius_changed(self):
        """半径修改"""
        if self.selected_asset_type == 'sprite' and self.selected_asset_name:
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite:
                sprite.radius = self.radius_spin.value()
                self._mark_modified()
                self._refresh_canvas()
    
    def _on_rotate_changed(self, checked: bool):
        """旋转修改"""
        if self.selected_asset_type == 'sprite' and self.selected_asset_name:
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite:
                sprite.rotate = checked
                self._mark_modified()
    
    def _on_frame_duration_changed(self):
        """帧时长修改"""
        if self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim:
                anim.frame_duration = self.frame_duration_spin.value()
                self._mark_modified()
    
    def _on_anim_loop_changed(self, checked: bool):
        """循环修改"""
        if self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim:
                anim.loop = checked
                self._mark_modified()
    
    def _center_sprite(self):
        """将中心点设为矩形中心"""
        w, h = self.rect_w.value(), self.rect_h.value()
        self.center_x.setValue(w / 2)
        self.center_y.setValue(h / 2)
    
    def _mark_modified(self):
        """标记已修改"""
        self.is_modified = True
        self.save_status_label.setText("⚠ 有未保存的修改")
        self.save_status_label.setStyleSheet("color: #FFA500;")
    
    # ==================== 帧操作 ====================
    
    def _on_frame_clicked(self, item: QListWidgetItem):
        """帧点击"""
        row = self.frame_list.row(item)
        if self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and 0 <= row < len(anim.frames):
                self.animation_frame = row
                self._update_properties_panel()
                self._refresh_canvas()
    
    def _add_frame(self):
        """添加帧"""
        if self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim:
                anim.frames.append(TextureRegion(0, 0, 32, 32))
                self._update_properties_panel()
                self._mark_modified()
    
    def _delete_frame(self):
        """删除帧"""
        if self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and len(anim.frames) > 1:
                row = self.frame_list.currentRow()
                if 0 <= row < len(anim.frames):
                    anim.frames.pop(row)
                    self.animation_frame = min(self.animation_frame, len(anim.frames) - 1)
                    self._update_properties_panel()
                    self._mark_modified()
    
    # ==================== 动画播放 ====================
    
    def _toggle_animation(self):
        """切换动画播放"""
        if self.animation_playing:
            self.animation_timer.stop()
            self.animation_playing = False
            self.play_btn.setText("▶ 播放")
        else:
            if self.selected_asset_type == 'animation' and self.selected_asset_name:
                anim = self.current_sheet.animations.get(self.selected_asset_name)
                if anim and anim.frames:
                    interval = int(anim.frame_duration * 1000 / 60)  # 转换为毫秒
                    self.animation_timer.start(max(16, interval))
                    self.animation_playing = True
                    self.play_btn.setText("⏸ 暂停")
    
    def _update_animation(self):
        """更新动画帧"""
        if self.selected_asset_type != 'animation' or not self.selected_asset_name:
            return
        
        anim = self.current_sheet.animations.get(self.selected_asset_name)
        if not anim or not anim.frames:
            return
        
        self.animation_frame = (self.animation_frame + 1) % len(anim.frames)
        self.frame_info_label.setText(f"帧: {self.animation_frame + 1}/{len(anim.frames)}")
        self._update_preview()
        self._refresh_canvas()
    
    def _prev_frame(self):
        """上一帧"""
        if self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and anim.frames:
                self.animation_frame = (self.animation_frame - 1) % len(anim.frames)
                self.frame_info_label.setText(f"帧: {self.animation_frame + 1}/{len(anim.frames)}")
                self._update_preview()
                self._refresh_canvas()
    
    def _next_frame(self):
        """下一帧"""
        if self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and anim.frames:
                self.animation_frame = (self.animation_frame + 1) % len(anim.frames)
                self.frame_info_label.setText(f"帧: {self.animation_frame + 1}/{len(anim.frames)}")
                self._update_preview()
                self._refresh_canvas()
    
    def _update_preview(self):
        """更新预览"""
        if not self.current_sheet or not self.current_sheet.surface:
            return
        
        if self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and 0 <= self.animation_frame < len(anim.frames):
                frame = anim.frames[self.animation_frame]
                
                try:
                    import pygame
                    surface = self.current_sheet.surface
                    cropped = surface.subsurface((frame.x, frame.y, frame.width, frame.height))
                    
                    data = pygame.image.tostring(cropped, 'RGBA')
                    qimage = QImage(data, frame.width, frame.height, QImage.Format_RGBA8888)
                    pixmap = QPixmap.fromImage(qimage)
                    
                    preview_size = 128
                    scaled = pixmap.scaled(
                        preview_size, preview_size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.preview_label.setPixmap(scaled)
                except Exception as e:
                    print(f"预览更新失败: {e}")
    
    # ==================== 保存 ====================
    
    def _save_current_config(self):
        """保存当前配置到JSON"""
        if not self.current_sheet or not self.current_config_path:
            QMessageBox.warning(self, "警告", "没有可保存的配置")
            return
        
        try:
            # 读取原始配置
            with open(self.current_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 更新精灵
            if 'sprites' in config:
                for name, sprite in self.current_sheet.sprites.items():
                    if name in config['sprites'] and sprite.region:
                        config['sprites'][name]['rect'] = [
                            sprite.region.x, sprite.region.y,
                            sprite.region.width, sprite.region.height
                        ]
                        config['sprites'][name]['center'] = [
                            sprite.region.center_x, sprite.region.center_y
                        ]
                        config['sprites'][name]['radius'] = sprite.radius
                        config['sprites'][name]['rotate'] = sprite.rotate
            
            # 更新动画
            if 'animations' in config:
                for name, anim in self.current_sheet.animations.items():
                    if name in config['animations']:
                        if 'frames' in config['animations'][name]:
                            # 更新帧数据
                            frame_data = []
                            for frame in anim.frames:
                                frame_data.append({
                                    'rect': [frame.x, frame.y, frame.width, frame.height],
                                    'center': [frame.center_x, frame.center_y]
                                })
                            config['animations'][name]['frames'] = frame_data
                        config['animations'][name]['frame_duration'] = anim.frame_duration
                        config['animations'][name]['loop'] = anim.loop
            
            # 写入文件
            with open(self.current_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.is_modified = False
            self.save_status_label.setText("✓ 已保存")
            self.save_status_label.setStyleSheet("color: #4CAF50;")
            self.statusBar().showMessage(f"已保存: {Path(self.current_config_path).name}")
        
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败:\n{e}")
    
    def _save_all_configs(self):
        """保存所有修改的配置"""
        # TODO: 追踪所有修改过的配置并保存
        self._save_current_config()
    
    def _new_config(self):
        """新建配置文件"""
        path, _ = QFileDialog.getSaveFileName(
            self, "新建配置文件",
            str(IMAGES_ROOT / "new_config.json"),
            "JSON配置 (*.json)"
        )
        if path:
            config = {
                "__image_filename": Path(path).stem + ".png",
                "sprites": {},
                "animations": {}
            }
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # 重新加载
            self._reload_all_configs()
            self.statusBar().showMessage(f"已创建: {Path(path).name}")
    
    # ==================== 添加/删除资产 ====================
    
    def _add_sprite(self):
        """添加精灵"""
        if not self.current_sheet:
            QMessageBox.warning(self, "警告", "请先选择一个纹理表")
            return
        
        name = f"sprite_{len(self.current_sheet.sprites)}"
        while name in self.current_sheet.sprites:
            name = f"sprite_{len(self.current_sheet.sprites) + 1}"
        
        sprite = SpriteAsset(
            name=name,
            asset_type=AssetType.SPRITE,
            texture_path=self.current_sheet.path,
            region=TextureRegion(0, 0, 32, 32)
        )
        
        self.current_sheet.sprites[name] = sprite
        self.engine.all_sprites[name] = sprite
        
        self._refresh_asset_tree()
        self._select_asset('sprite', name)
        self._mark_modified()
    
    def _add_animation(self):
        """添加动画"""
        if not self.current_sheet:
            QMessageBox.warning(self, "警告", "请先选择一个纹理表")
            return
        
        name = f"animation_{len(self.current_sheet.animations)}"
        while name in self.current_sheet.animations:
            name = f"animation_{len(self.current_sheet.animations) + 1}"
        
        anim = AnimationAsset(
            name=name,
            asset_type=AssetType.ANIMATION,
            texture_path=self.current_sheet.path,
            frames=[TextureRegion(0, 0, 32, 32)]
        )
        
        self.current_sheet.animations[name] = anim
        self.engine.all_animations[name] = anim
        
        self._refresh_asset_tree()
        self._select_asset('animation', name)
        self._mark_modified()
    
    def _delete_selected(self):
        """删除选中资产"""
        if not self.selected_asset_name or not self.current_sheet:
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 '{self.selected_asset_name}' 吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.selected_asset_type == 'sprite':
                self.current_sheet.sprites.pop(self.selected_asset_name, None)
                self.engine.all_sprites.pop(self.selected_asset_name, None)
            elif self.selected_asset_type == 'animation':
                self.current_sheet.animations.pop(self.selected_asset_name, None)
                self.engine.all_animations.pop(self.selected_asset_name, None)
            
            self.selected_asset_name = None
            self.selected_asset_type = None
            
            self._refresh_asset_tree()
            self._update_properties_panel()
            self._refresh_canvas()
            self._mark_modified()
    
    # ==================== 批量工具 ====================
    
    def _copy_rect(self):
        """复制当前区域"""
        if self.selected_asset_type == 'sprite' and self.selected_asset_name:
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite and sprite.region:
                self._rect_clipboard = (sprite.region.x, sprite.region.y, sprite.region.width, sprite.region.height)
                self.statusBar().showMessage("已复制区域")
        elif self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and 0 <= self.animation_frame < len(anim.frames):
                frame = anim.frames[self.animation_frame]
                self._rect_clipboard = (frame.x, frame.y, frame.width, frame.height)
                self.statusBar().showMessage("已复制帧区域")
    
    def _paste_rect(self):
        """粘贴区域"""
        if not self._rect_clipboard:
            self.statusBar().showMessage("剪贴板为空")
            return
        
        x, y, w, h = self._rect_clipboard
        
        if self.selected_asset_type == 'sprite' and self.selected_asset_name:
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite and sprite.region:
                sprite.region.x = x
                sprite.region.y = y
                sprite.region.width = w
                sprite.region.height = h
                self._update_properties_panel()
                self._refresh_canvas()
                self._mark_modified()
                self.statusBar().showMessage("已粘贴到精灵")
    
    def _open_grid_dialog(self):
        """打开网格生成对话框"""
        if not self.current_sheet:
            QMessageBox.warning(self, "警告", "请先选择一个纹理表")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("生成网格精灵")
        
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        rows_spin = QSpinBox()
        rows_spin.setRange(1, 200)
        rows_spin.setValue(4)
        cols_spin = QSpinBox()
        cols_spin.setRange(1, 200)
        cols_spin.setValue(4)
        
        start_x = QSpinBox()
        start_x.setRange(0, 99999)
        start_y = QSpinBox()
        start_y.setRange(0, 99999)
        
        cell_w = QSpinBox()
        cell_w.setRange(1, 99999)
        cell_w.setValue(32)
        cell_h = QSpinBox()
        cell_h.setRange(1, 99999)
        cell_h.setValue(32)
        
        gap_x = QSpinBox()
        gap_x.setRange(0, 99999)
        gap_y = QSpinBox()
        gap_y.setRange(0, 99999)
        
        prefix_edit = QLineEdit("tile")
        
        form.addRow("行数", rows_spin)
        form.addRow("列数", cols_spin)
        form.addRow("起点 X", start_x)
        form.addRow("起点 Y", start_y)
        form.addRow("单元宽", cell_w)
        form.addRow("单元高", cell_h)
        form.addRow("间隔 X", gap_x)
        form.addRow("间隔 Y", gap_y)
        form.addRow("名称前缀", prefix_edit)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec_() == QDialog.Accepted:
            self._create_grid(
                rows_spin.value(), cols_spin.value(),
                start_x.value(), start_y.value(),
                cell_w.value(), cell_h.value(),
                gap_x.value(), gap_y.value(),
                prefix_edit.text().strip() or "tile"
            )
    
    def _create_grid(self, rows: int, cols: int, start_x: int, start_y: int,
                     cell_w: int, cell_h: int, gap_x: int, gap_y: int, prefix: str):
        """生成网格精灵"""
        idx = 0
        for r in range(rows):
            for c in range(cols):
                x = start_x + c * (cell_w + gap_x)
                y = start_y + r * (cell_h + gap_y)
                
                name = f"{prefix}_{idx}"
                while name in self.current_sheet.sprites:
                    idx += 1
                    name = f"{prefix}_{idx}"
                
                sprite = SpriteAsset(
                    name=name,
                    asset_type=AssetType.SPRITE,
                    texture_path=self.current_sheet.path,
                    region=TextureRegion(x, y, cell_w, cell_h, cell_w / 2, cell_h / 2)
                )
                
                self.current_sheet.sprites[name] = sprite
                self.engine.all_sprites[name] = sprite
                idx += 1
        
        self._refresh_asset_tree()
        self._refresh_canvas()
        self._mark_modified()
        self._update_stats()
        self.statusBar().showMessage(f"已生成 {rows * cols} 个精灵")
    
    # ==================== 画布渲染 ====================
    
    def _refresh_canvas(self):
        """刷新画布"""
        # 清除旧元素
        for item in list(self._rect_items.values()) + list(self._center_items.values()):
            if item.scene():
                self.scene.removeItem(item)
        self._rect_items.clear()
        self._center_items.clear()
        
        for item in self._grid_items + self._label_items:
            if item.scene():
                self.scene.removeItem(item)
        self._grid_items.clear()
        self._label_items.clear()
        
        if not self.current_sheet:
            return
        
        # 绘制网格
        if self.show_grid_cb.isChecked():
            self._draw_grid()
        
        # 绘制所有区域
        if self.show_all_cb.isChecked():
            self._draw_all_rects()
        
        # 绘制选中项
        if self.selected_asset_name:
            self._draw_selected_item()
        
        self._build_hit_index()
    
    def _draw_grid(self):
        """绘制网格"""
        rect = self.scene.sceneRect()
        grid_size = 32
        
        pen = QPen(QColor(68, 68, 68))
        pen.setWidth(0)
        
        x = 0
        while x < rect.width():
            line = self.scene.addLine(x, 0, x, rect.height(), pen)
            line.setZValue(-10)
            self._grid_items.append(line)
            x += grid_size
        
        y = 0
        while y < rect.height():
            line = self.scene.addLine(0, y, rect.width(), y, pen)
            line.setZValue(-10)
            self._grid_items.append(line)
            y += grid_size
    
    def _draw_all_rects(self):
        """绘制所有区域"""
        pen = QPen(QColor(74, 158, 255))
        pen.setWidth(1)
        
        # 精灵
        for name, sprite in self.current_sheet.sprites.items():
            if name == self.selected_asset_name and self.selected_asset_type == 'sprite':
                continue
            if sprite.region:
                r = sprite.region
                rect_item = self.scene.addRect(r.x, r.y, r.width, r.height, pen)
                rect_item.setZValue(1)
                self._rect_items[f"sprite_{name}"] = rect_item
                
                if self.show_labels_cb.isChecked():
                    text = self.scene.addText(name, QFont("Arial", 8))
                    text.setPos(r.x + 2, r.y + 2)
                    text.setDefaultTextColor(QColor(74, 158, 255))
                    text.setZValue(2)
                    self._label_items.append(text)
        
        # 动画
        anim_pen = QPen(QColor(158, 255, 74))
        anim_pen.setWidth(1)
        
        for name, anim in self.current_sheet.animations.items():
            if name == self.selected_asset_name and self.selected_asset_type == 'animation':
                continue
            for i, frame in enumerate(anim.frames):
                rect_item = self.scene.addRect(frame.x, frame.y, frame.width, frame.height, anim_pen)
                rect_item.setZValue(1)
                self._rect_items[f"anim_{name}_{i}"] = rect_item
        
        # 激光
        laser_pen = QPen(QColor(255, 158, 74))
        laser_pen.setWidth(1)
        
        for name, laser in self.current_sheet.lasers.items():
            if name == self.selected_asset_name and self.selected_asset_type == 'laser':
                continue
            for part, region in [('head', laser.head), ('body', laser.body), ('tail', laser.tail)]:
                if region:
                    rect_item = self.scene.addRect(region.x, region.y, region.width, region.height, laser_pen)
                    rect_item.setZValue(1)
                    self._rect_items[f"laser_{name}_{part}"] = rect_item
    
    def _draw_selected_item(self):
        """绘制选中项"""
        pen = QPen(QColor(255, 100, 100))
        pen.setWidth(2)
        
        center_pen = QPen(QColor(255, 255, 0))
        center_pen.setWidth(2)
        
        radius_pen = QPen(QColor(0, 255, 255))
        radius_pen.setWidth(1)
        radius_pen.setStyle(Qt.DashLine)
        
        if self.selected_asset_type == 'sprite':
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite and sprite.region:
                r = sprite.region
                
                rect_item = self.scene.addRect(r.x, r.y, r.width, r.height, pen)
                rect_item.setZValue(10)
                self._rect_items["selected"] = rect_item
                
                center_item = self.scene.addEllipse(
                    r.x + r.center_x - 3, r.y + r.center_y - 3, 6, 6,
                    center_pen, QBrush(QColor(255, 255, 0))
                )
                center_item.setZValue(11)
                self._center_items["selected_center"] = center_item
                
                if sprite.radius > 0:
                    radius_item = self.scene.addEllipse(
                        r.x + r.center_x - sprite.radius, r.y + r.center_y - sprite.radius,
                        sprite.radius * 2, sprite.radius * 2,
                        radius_pen
                    )
                    radius_item.setZValue(9)
                    self._rect_items["selected_radius"] = radius_item
        
        elif self.selected_asset_type == 'animation':
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and 0 <= self.animation_frame < len(anim.frames):
                frame = anim.frames[self.animation_frame]
                
                rect_item = self.scene.addRect(frame.x, frame.y, frame.width, frame.height, pen)
                rect_item.setZValue(10)
                self._rect_items["selected"] = rect_item
                
                center_item = self.scene.addEllipse(
                    frame.x + frame.center_x - 3, frame.y + frame.center_y - 3, 6, 6,
                    center_pen, QBrush(QColor(255, 255, 0))
                )
                center_item.setZValue(11)
                self._center_items["selected_center"] = center_item
        
        elif self.selected_asset_type == 'laser':
            laser = self.current_sheet.lasers.get(self.selected_asset_name)
            if laser:
                colors = {'head': QColor(255, 100, 100), 'body': QColor(100, 255, 100), 'tail': QColor(100, 100, 255)}
                for part, region in [('head', laser.head), ('body', laser.body), ('tail', laser.tail)]:
                    if region:
                        part_pen = QPen(colors[part])
                        part_pen.setWidth(2)
                        rect_item = self.scene.addRect(region.x, region.y, region.width, region.height, part_pen)
                        rect_item.setZValue(10)
                        self._rect_items[f"selected_{part}"] = rect_item
    
    def _build_hit_index(self):
        """重建点击索引"""
        self._hit_rects.clear()
        
        if not self.current_sheet:
            return
        
        for name, sprite in self.current_sheet.sprites.items():
            if sprite.region:
                r = sprite.region
                self._hit_rects.append((0, 'sprite', name, (r.x, r.y, r.width, r.height), None))
        
        for name, anim in self.current_sheet.animations.items():
            for i, frame in enumerate(anim.frames):
                self._hit_rects.append((1, 'animation', name, (frame.x, frame.y, frame.width, frame.height), i))
        
        for name, laser in self.current_sheet.lasers.items():
            for region in (laser.head, laser.body, laser.tail):
                if region:
                    self._hit_rects.append((2, 'laser', name, (region.x, region.y, region.width, region.height), None))
    
    def _hit_test(self, x: int, y: int) -> Optional[Tuple[int, str, str, Tuple[int, int, int, int], Optional[int]]]:
        """点击测试"""
        hits = []
        for priority, item_type, name, rect, frame_index in self._hit_rects:
            rx, ry, rw, rh = rect
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                area = rw * rh
                hits.append((priority, area, item_type, name, rect, frame_index))
        
        if not hits:
            return None
        
        hits.sort(key=lambda h: (h[0], h[1]))
        priority, _, item_type, name, rect, frame_index = hits[0]
        return (priority, item_type, name, rect, frame_index)
    
    # ==================== 视图操作 ====================
    
    def _on_mode_changed(self, checked: bool):
        """模式改变"""
        if checked:
            btn = self.sender()
            mode = btn.property("mode")
            self._current_mode = mode
            self.view.set_mode(mode)
    
    def _zoom(self, factor: float):
        """缩放"""
        self.view.zoom *= factor
    
    def _on_zoom_changed(self, zoom: float):
        """缩放改变"""
        self.zoom_label.setText(f"{int(zoom * 100)}%")
    
    def _on_mouse_moved(self, x: int, y: int):
        """鼠标移动"""
        self.coord_label.setText(f"坐标: ({x}, {y})")
    
    def _on_rect_drawn(self, rect: QRectF):
        """矩形绘制完成"""
        if self.selected_asset_type == 'sprite' and self.selected_asset_name:
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite and sprite.region:
                sprite.region.x = int(rect.x())
                sprite.region.y = int(rect.y())
                sprite.region.width = int(rect.width())
                sprite.region.height = int(rect.height())
                self._update_properties_panel()
                self._refresh_canvas()
                self._mark_modified()
        elif self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and 0 <= self.animation_frame < len(anim.frames):
                frame = anim.frames[self.animation_frame]
                frame.x = int(rect.x())
                frame.y = int(rect.y())
                frame.width = int(rect.width())
                frame.height = int(rect.height())
                self._update_properties_panel()
                self._refresh_canvas()
                self._mark_modified()
    
    def _on_canvas_clicked(self, x: float, y: float, button: int):
        """画布点击"""
        if self._current_mode == 'edit_center':
            self._set_center_at_point(x, y)
            return
        
        if self._current_mode != 'select':
            return
        
        hit = self._hit_test(int(x), int(y))
        if hit:
            _, hit_type, name, _, frame_index = hit
            self._select_asset(hit_type, name)
            if hit_type == 'animation' and frame_index is not None:
                self.animation_frame = frame_index
                self._update_properties_panel()
    
    def _set_center_at_point(self, x: float, y: float):
        """设置中心点"""
        if self.selected_asset_type == 'sprite' and self.selected_asset_name:
            sprite = self.current_sheet.sprites.get(self.selected_asset_name)
            if sprite and sprite.region:
                cx = x - sprite.region.x
                cy = y - sprite.region.y
                sprite.region.center_x = cx
                sprite.region.center_y = cy
                self._update_properties_panel()
                self._refresh_canvas()
                self._mark_modified()
        elif self.selected_asset_type == 'animation' and self.selected_asset_name:
            anim = self.current_sheet.animations.get(self.selected_asset_name)
            if anim and 0 <= self.animation_frame < len(anim.frames):
                frame = anim.frames[self.animation_frame]
                cx = x - frame.x
                cy = y - frame.y
                frame.center_x = cx
                frame.center_y = cy
                self._update_properties_panel()
                self._refresh_canvas()
                self._mark_modified()
    
    def _fit_view(self):
        """适应视图"""
        self.view.fit_in_view()
    
    # ==================== 其他 ====================
    
    def _show_about(self):
        """显示关于"""
        QMessageBox.about(
            self, "关于",
            "纹理资产管理器 v2.0 - 引擎集成版\n\n"
            "直接使用 UnifiedTextureManager 加载和管理资源\n"
            "所有修改将同步到游戏引擎使用的配置文件\n\n"
            "支持：子弹、激光、曲线激光、玩家、敌人、道具等"
        )
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.is_modified:
            reply = QMessageBox.question(
                self, "确认退出",
                "有未保存的修改，确定要退出吗？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            
            if reply == QMessageBox.Save:
                self._save_current_config()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # 暗色调色板
    palette = app.palette()
    palette.setColor(palette.Window, QColor(53, 53, 53))
    palette.setColor(palette.WindowText, QColor(255, 255, 255))
    palette.setColor(palette.Base, QColor(35, 35, 35))
    palette.setColor(palette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(palette.ToolTipBase, QColor(25, 25, 25))
    palette.setColor(palette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(palette.Text, QColor(255, 255, 255))
    palette.setColor(palette.Button, QColor(53, 53, 53))
    palette.setColor(palette.ButtonText, QColor(255, 255, 255))
    palette.setColor(palette.BrightText, QColor(255, 0, 0))
    palette.setColor(palette.Link, QColor(42, 130, 218))
    palette.setColor(palette.Highlight, QColor(42, 130, 218))
    palette.setColor(palette.HighlightedText, QColor(35, 35, 35))
    app.setPalette(palette)
    
    window = EngineIntegratedAssetManager()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
