#!/usr/bin/env python3
"""
弹幕背景可视化编辑器

功能:
- 编辑多图层背景配置
- 3D摄像机参数调整
- 雾效配置
- 滚动和视差效果预览
- 实时预览背景效果
- 导出背景配置JSON
"""

import sys
import os
import json
import math
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field, asdict

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QGroupBox, QFormLayout, QScrollArea, QFrame, QTabWidget,
    QFileDialog, QMessageBox, QToolBar, QAction, QStatusBar, QSlider,
    QColorDialog, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem
)
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush, QFont, 
    QIcon, QKeySequence, QTransform, QLinearGradient
)

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ASSETS_ROOT = PROJECT_ROOT / "assets"
IMAGES_ROOT = ASSETS_ROOT / "images" / "background"


# ==================== 数据模型 ====================

@dataclass
class TextureConfig:
    """纹理配置"""
    name: str
    path: str
    rect: Optional[Tuple[int, int, int, int]] = None
    blend_mode: str = "normal"
    alpha: float = 1.0


@dataclass
class Camera3DConfig:
    """3D摄像机配置"""
    eye_x: float = 0.0
    eye_y: float = 0.0
    eye_z: float = -1.0
    at_x: float = 0.0
    at_y: float = 0.0
    at_z: float = 0.0
    up_x: float = 0.0
    up_y: float = 1.0
    up_z: float = 0.0
    fovy: float = 0.6
    z_near: float = 0.01
    z_far: float = 10.0


@dataclass
class FogConfig:
    """雾效配置"""
    enabled: bool = True
    start: float = 3.0
    end: float = 6.0
    color_r: int = 0
    color_g: int = 0
    color_b: int = 0
    color_a: int = 255


@dataclass
class LayerConfig:
    """图层配置"""
    name: str = "layer"
    texture: str = ""
    z_order: int = 0
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    parallax: float = 1.0
    alpha: float = 1.0
    blend_mode: str = "normal"
    tile_x: int = 1
    tile_y: int = 1
    use_3d: bool = False


@dataclass
class BackgroundData:
    """背景数据"""
    name: str = "新背景"
    description: str = ""
    textures: List[TextureConfig] = field(default_factory=list)
    camera: Camera3DConfig = field(default_factory=Camera3DConfig)
    fog: FogConfig = field(default_factory=FogConfig)
    layers: List[LayerConfig] = field(default_factory=list)
    scroll_speed: float = 0.01


# ==================== 预览视图 ====================

class BackgroundPreviewView(QGraphicsView):
    """背景预览视图"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setMinimumSize(400, 500)
        
        # 预览区域尺寸
        self.preview_width = 384
        self.preview_height = 448
        
        # 当前数据
        self.bg_data: Optional[BackgroundData] = None
        self.loaded_textures: Dict[str, QPixmap] = {}
        self.layer_items: List[QGraphicsPixmapItem] = []
        
        # 动画状态
        self.scroll_offset = 0.0
        self.animation_running = False
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_animation)
        
        # 绘制边界
        self._draw_boundary()
    
    def _draw_boundary(self):
        """绘制预览边界"""
        # 背景
        self.scene.setBackgroundBrush(QBrush(QColor(20, 20, 30)))
        
        # 游戏区域边框
        pen = QPen(QColor(100, 100, 150), 2)
        self.scene.addRect(0, 0, self.preview_width, self.preview_height, pen)
    
    def set_background_data(self, data: BackgroundData):
        """设置背景数据"""
        self.bg_data = data
        self._load_textures()
        self._refresh_preview()
    
    def _load_textures(self):
        """加载纹理"""
        if not self.bg_data:
            return
        
        self.loaded_textures.clear()
        
        for tex in self.bg_data.textures:
            path = IMAGES_ROOT / tex.path
            if path.exists():
                pixmap = QPixmap(str(path))
                self.loaded_textures[tex.name] = pixmap
    
    def _refresh_preview(self):
        """刷新预览"""
        # 清除旧图层
        for item in self.layer_items:
            self.scene.removeItem(item)
        self.layer_items.clear()
        
        if not self.bg_data:
            return
        
        # 绘制雾效背景
        if self.bg_data.fog.enabled:
            fog_color = QColor(
                self.bg_data.fog.color_r,
                self.bg_data.fog.color_g,
                self.bg_data.fog.color_b,
                self.bg_data.fog.color_a
            )
            fog_rect = self.scene.addRect(
                0, 0, self.preview_width, self.preview_height,
                QPen(Qt.NoPen), QBrush(fog_color)
            )
            fog_rect.setZValue(-100)
        
        # 按z_order排序绘制图层
        sorted_layers = sorted(self.bg_data.layers, key=lambda l: l.z_order)
        
        for layer in sorted_layers:
            if layer.texture not in self.loaded_textures:
                continue
            
            pixmap = self.loaded_textures[layer.texture]
            
            # 计算滚动偏移
            offset_x = (self.scroll_offset * layer.scroll_x * layer.parallax) % pixmap.width()
            offset_y = (self.scroll_offset * layer.scroll_y * layer.parallax) % pixmap.height()
            
            # 平铺
            for tx in range(layer.tile_x):
                for ty in range(layer.tile_y):
                    item = QGraphicsPixmapItem(pixmap)
                    item.setPos(
                        tx * pixmap.width() - offset_x,
                        ty * pixmap.height() - offset_y
                    )
                    item.setOpacity(layer.alpha)
                    item.setZValue(layer.z_order)
                    
                    self.scene.addItem(item)
                    self.layer_items.append(item)
    
    def start_animation(self):
        """开始动画"""
        self.animation_running = True
        self.timer.start(16)
    
    def stop_animation(self):
        """停止动画"""
        self.animation_running = False
        self.timer.stop()
    
    def _update_animation(self):
        """更新动画"""
        if self.bg_data:
            self.scroll_offset += self.bg_data.scroll_speed * 60
            self._refresh_preview()


# ==================== 图层编辑面板 ====================

class LayerEditorPanel(QWidget):
    """图层编辑面板"""
    
    layer_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_layer: Optional[LayerConfig] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 基本属性
        basic_group = QGroupBox("基本属性")
        basic_layout = QFormLayout(basic_group)
        
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_change)
        basic_layout.addRow("名称:", self.name_edit)
        
        self.texture_combo = QComboBox()
        self.texture_combo.currentTextChanged.connect(self._on_change)
        basic_layout.addRow("纹理:", self.texture_combo)
        
        self.z_order_spin = QSpinBox()
        self.z_order_spin.setRange(-100, 100)
        self.z_order_spin.valueChanged.connect(self._on_change)
        basic_layout.addRow("Z顺序:", self.z_order_spin)
        
        layout.addWidget(basic_group)
        
        # 滚动属性
        scroll_group = QGroupBox("滚动")
        scroll_layout = QFormLayout(scroll_group)
        
        self.scroll_x_spin = QDoubleSpinBox()
        self.scroll_x_spin.setRange(-10, 10)
        self.scroll_x_spin.setSingleStep(0.01)
        self.scroll_x_spin.valueChanged.connect(self._on_change)
        scroll_layout.addRow("X速度:", self.scroll_x_spin)
        
        self.scroll_y_spin = QDoubleSpinBox()
        self.scroll_y_spin.setRange(-10, 10)
        self.scroll_y_spin.setSingleStep(0.01)
        self.scroll_y_spin.valueChanged.connect(self._on_change)
        scroll_layout.addRow("Y速度:", self.scroll_y_spin)
        
        self.parallax_spin = QDoubleSpinBox()
        self.parallax_spin.setRange(0, 5)
        self.parallax_spin.setValue(1.0)
        self.parallax_spin.setSingleStep(0.1)
        self.parallax_spin.valueChanged.connect(self._on_change)
        scroll_layout.addRow("视差系数:", self.parallax_spin)
        
        layout.addWidget(scroll_group)
        
        # 显示属性
        display_group = QGroupBox("显示")
        display_layout = QFormLayout(display_group)
        
        self.alpha_slider = QSlider(Qt.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(100)
        self.alpha_slider.valueChanged.connect(self._on_change)
        display_layout.addRow("透明度:", self.alpha_slider)
        
        self.blend_combo = QComboBox()
        self.blend_combo.addItems(["normal", "additive", "multiply"])
        self.blend_combo.currentTextChanged.connect(self._on_change)
        display_layout.addRow("混合模式:", self.blend_combo)
        
        layout.addWidget(display_group)
        
        # 平铺
        tile_group = QGroupBox("平铺")
        tile_layout = QFormLayout(tile_group)
        
        self.tile_x_spin = QSpinBox()
        self.tile_x_spin.setRange(1, 10)
        self.tile_x_spin.valueChanged.connect(self._on_change)
        tile_layout.addRow("X次数:", self.tile_x_spin)
        
        self.tile_y_spin = QSpinBox()
        self.tile_y_spin.setRange(1, 10)
        self.tile_y_spin.valueChanged.connect(self._on_change)
        tile_layout.addRow("Y次数:", self.tile_y_spin)
        
        layout.addWidget(tile_group)
        
        # 3D选项
        self.use_3d_cb = QCheckBox("使用3D渲染")
        self.use_3d_cb.toggled.connect(self._on_change)
        layout.addWidget(self.use_3d_cb)
        
        layout.addStretch()
    
    def set_layer(self, layer: LayerConfig, textures: List[str]):
        """设置当前图层"""
        self._current_layer = layer
        
        self.blockSignals(True)
        
        # 更新纹理列表
        self.texture_combo.clear()
        self.texture_combo.addItems(textures)
        
        self.name_edit.setText(layer.name)
        self.texture_combo.setCurrentText(layer.texture)
        self.z_order_spin.setValue(layer.z_order)
        self.scroll_x_spin.setValue(layer.scroll_x)
        self.scroll_y_spin.setValue(layer.scroll_y)
        self.parallax_spin.setValue(layer.parallax)
        self.alpha_slider.setValue(int(layer.alpha * 100))
        self.blend_combo.setCurrentText(layer.blend_mode)
        self.tile_x_spin.setValue(layer.tile_x)
        self.tile_y_spin.setValue(layer.tile_y)
        self.use_3d_cb.setChecked(layer.use_3d)
        
        self.blockSignals(False)
    
    def _on_change(self):
        """属性变化"""
        if not self._current_layer:
            return
        
        self._current_layer.name = self.name_edit.text()
        self._current_layer.texture = self.texture_combo.currentText()
        self._current_layer.z_order = self.z_order_spin.value()
        self._current_layer.scroll_x = self.scroll_x_spin.value()
        self._current_layer.scroll_y = self.scroll_y_spin.value()
        self._current_layer.parallax = self.parallax_spin.value()
        self._current_layer.alpha = self.alpha_slider.value() / 100.0
        self._current_layer.blend_mode = self.blend_combo.currentText()
        self._current_layer.tile_x = self.tile_x_spin.value()
        self._current_layer.tile_y = self.tile_y_spin.value()
        self._current_layer.use_3d = self.use_3d_cb.isChecked()
        
        self.layer_changed.emit()


# ==================== 摄像机编辑面板 ====================

class CameraEditorPanel(QWidget):
    """摄像机编辑面板"""
    
    camera_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._camera: Optional[Camera3DConfig] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Eye位置
        eye_group = QGroupBox("摄像机位置 (Eye)")
        eye_layout = QFormLayout(eye_group)
        
        self.eye_x = QDoubleSpinBox()
        self.eye_x.setRange(-10, 10)
        self.eye_x.setSingleStep(0.1)
        self.eye_x.valueChanged.connect(self._on_change)
        eye_layout.addRow("X:", self.eye_x)
        
        self.eye_y = QDoubleSpinBox()
        self.eye_y.setRange(-10, 10)
        self.eye_y.setSingleStep(0.1)
        self.eye_y.valueChanged.connect(self._on_change)
        eye_layout.addRow("Y:", self.eye_y)
        
        self.eye_z = QDoubleSpinBox()
        self.eye_z.setRange(-10, 10)
        self.eye_z.setSingleStep(0.1)
        self.eye_z.valueChanged.connect(self._on_change)
        eye_layout.addRow("Z:", self.eye_z)
        
        layout.addWidget(eye_group)
        
        # 目标位置
        at_group = QGroupBox("目标位置 (At)")
        at_layout = QFormLayout(at_group)
        
        self.at_x = QDoubleSpinBox()
        self.at_x.setRange(-10, 10)
        self.at_x.setSingleStep(0.1)
        self.at_x.valueChanged.connect(self._on_change)
        at_layout.addRow("X:", self.at_x)
        
        self.at_y = QDoubleSpinBox()
        self.at_y.setRange(-10, 10)
        self.at_y.setSingleStep(0.1)
        self.at_y.valueChanged.connect(self._on_change)
        at_layout.addRow("Y:", self.at_y)
        
        self.at_z = QDoubleSpinBox()
        self.at_z.setRange(-10, 10)
        self.at_z.setSingleStep(0.1)
        self.at_z.valueChanged.connect(self._on_change)
        at_layout.addRow("Z:", self.at_z)
        
        layout.addWidget(at_group)
        
        # 投影参数
        proj_group = QGroupBox("投影参数")
        proj_layout = QFormLayout(proj_group)
        
        self.fovy_spin = QDoubleSpinBox()
        self.fovy_spin.setRange(0.1, 3.14)
        self.fovy_spin.setSingleStep(0.1)
        self.fovy_spin.valueChanged.connect(self._on_change)
        proj_layout.addRow("FOV Y:", self.fovy_spin)
        
        self.z_near_spin = QDoubleSpinBox()
        self.z_near_spin.setRange(0.001, 1)
        self.z_near_spin.setDecimals(3)
        self.z_near_spin.setSingleStep(0.01)
        self.z_near_spin.valueChanged.connect(self._on_change)
        proj_layout.addRow("近裁面:", self.z_near_spin)
        
        self.z_far_spin = QDoubleSpinBox()
        self.z_far_spin.setRange(1, 100)
        self.z_far_spin.setSingleStep(1)
        self.z_far_spin.valueChanged.connect(self._on_change)
        proj_layout.addRow("远裁面:", self.z_far_spin)
        
        layout.addWidget(proj_group)
        
        layout.addStretch()
    
    def set_camera(self, camera: Camera3DConfig):
        """设置摄像机"""
        self._camera = camera
        
        self.blockSignals(True)
        
        self.eye_x.setValue(camera.eye_x)
        self.eye_y.setValue(camera.eye_y)
        self.eye_z.setValue(camera.eye_z)
        self.at_x.setValue(camera.at_x)
        self.at_y.setValue(camera.at_y)
        self.at_z.setValue(camera.at_z)
        self.fovy_spin.setValue(camera.fovy)
        self.z_near_spin.setValue(camera.z_near)
        self.z_far_spin.setValue(camera.z_far)
        
        self.blockSignals(False)
    
    def _on_change(self):
        """参数变化"""
        if not self._camera:
            return
        
        self._camera.eye_x = self.eye_x.value()
        self._camera.eye_y = self.eye_y.value()
        self._camera.eye_z = self.eye_z.value()
        self._camera.at_x = self.at_x.value()
        self._camera.at_y = self.at_y.value()
        self._camera.at_z = self.at_z.value()
        self._camera.fovy = self.fovy_spin.value()
        self._camera.z_near = self.z_near_spin.value()
        self._camera.z_far = self.z_far_spin.value()
        
        self.camera_changed.emit()


# ==================== 雾效编辑面板 ====================

class FogEditorPanel(QWidget):
    """雾效编辑面板"""
    
    fog_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fog: Optional[FogConfig] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 启用
        self.enabled_cb = QCheckBox("启用雾效")
        self.enabled_cb.toggled.connect(self._on_change)
        layout.addWidget(self.enabled_cb)
        
        # 距离
        dist_group = QGroupBox("雾效距离")
        dist_layout = QFormLayout(dist_group)
        
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0, 20)
        self.start_spin.setSingleStep(0.5)
        self.start_spin.valueChanged.connect(self._on_change)
        dist_layout.addRow("起始距离:", self.start_spin)
        
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0.1, 20)
        self.end_spin.setSingleStep(0.5)
        self.end_spin.valueChanged.connect(self._on_change)
        dist_layout.addRow("结束距离:", self.end_spin)
        
        layout.addWidget(dist_group)
        
        # 颜色
        color_group = QGroupBox("雾效颜色")
        color_layout = QVBoxLayout(color_group)
        
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(100, 30)
        self.color_preview.setStyleSheet("background-color: black; border: 1px solid #555;")
        color_layout.addWidget(self.color_preview)
        
        btn_color = QPushButton("选择颜色")
        btn_color.clicked.connect(self._choose_color)
        color_layout.addWidget(btn_color)
        
        layout.addWidget(color_group)
        
        layout.addStretch()
    
    def set_fog(self, fog: FogConfig):
        """设置雾效"""
        self._fog = fog
        
        self.blockSignals(True)
        
        self.enabled_cb.setChecked(fog.enabled)
        self.start_spin.setValue(fog.start)
        self.end_spin.setValue(fog.end)
        
        self._update_color_preview()
        
        self.blockSignals(False)
    
    def _update_color_preview(self):
        """更新颜色预览"""
        if self._fog:
            self.color_preview.setStyleSheet(
                f"background-color: rgba({self._fog.color_r},{self._fog.color_g},"
                f"{self._fog.color_b},{self._fog.color_a}); border: 1px solid #555;"
            )
    
    def _choose_color(self):
        """选择颜色"""
        if not self._fog:
            return
        
        color = QColorDialog.getColor(
            QColor(self._fog.color_r, self._fog.color_g, self._fog.color_b),
            self, "选择雾效颜色"
        )
        
        if color.isValid():
            self._fog.color_r = color.red()
            self._fog.color_g = color.green()
            self._fog.color_b = color.blue()
            self._update_color_preview()
            self.fog_changed.emit()
    
    def _on_change(self):
        """参数变化"""
        if not self._fog:
            return
        
        self._fog.enabled = self.enabled_cb.isChecked()
        self._fog.start = self.start_spin.value()
        self._fog.end = self.end_spin.value()
        
        self.fog_changed.emit()


# ==================== 主窗口 ====================

class BackgroundEditor(QMainWindow):
    """背景编辑器主窗口"""
    
    def __init__(self):
        super().__init__()
        
        self.bg_data = BackgroundData()
        self.current_layer_index = -1
        
        self._setup_ui()
        self._setup_menu()
        self._apply_theme()
        
        self.setWindowTitle("弹幕背景编辑器 - PySTG")
        self.setMinimumSize(1300, 850)
        self.resize(1500, 950)
        
        # 扫描可用纹理
        self._scan_textures()
    
    def _setup_ui(self):
        """设置UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧 - 图层列表
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # 中间 - 预览
        center_panel = self._create_center_panel()
        splitter.addWidget(center_panel)
        
        # 右侧 - 属性编辑
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([280, 450, 350])
        
        self.statusBar().showMessage("就绪")
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 背景信息
        info_group = QGroupBox("背景信息")
        info_layout = QFormLayout(info_group)
        
        self.name_edit = QLineEdit(self.bg_data.name)
        self.name_edit.textChanged.connect(self._on_info_changed)
        info_layout.addRow("名称:", self.name_edit)
        
        self.desc_edit = QLineEdit()
        self.desc_edit.textChanged.connect(self._on_info_changed)
        info_layout.addRow("描述:", self.desc_edit)
        
        self.scroll_spin = QDoubleSpinBox()
        self.scroll_spin.setRange(0, 1)
        self.scroll_spin.setSingleStep(0.001)
        self.scroll_spin.setDecimals(3)
        self.scroll_spin.setValue(0.01)
        self.scroll_spin.valueChanged.connect(self._on_info_changed)
        info_layout.addRow("滚动速度:", self.scroll_spin)
        
        layout.addWidget(info_group)
        
        # 纹理列表
        tex_group = QGroupBox("纹理")
        tex_layout = QVBoxLayout(tex_group)
        
        btn_layout = QHBoxLayout()
        btn_add_tex = QPushButton("+ 添加")
        btn_add_tex.clicked.connect(self._add_texture)
        btn_layout.addWidget(btn_add_tex)
        tex_layout.addLayout(btn_layout)
        
        self.texture_list = QListWidget()
        self.texture_list.setMaximumHeight(120)
        tex_layout.addWidget(self.texture_list)
        
        layout.addWidget(tex_group)
        
        # 图层列表
        layer_group = QGroupBox("图层")
        layer_layout = QVBoxLayout(layer_group)
        
        layer_btn_layout = QHBoxLayout()
        btn_add = QPushButton("+ 添加")
        btn_add.clicked.connect(self._add_layer)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._delete_layer)
        btn_up = QPushButton("↑")
        btn_up.setFixedWidth(30)
        btn_up.clicked.connect(self._move_layer_up)
        btn_down = QPushButton("↓")
        btn_down.setFixedWidth(30)
        btn_down.clicked.connect(self._move_layer_down)
        
        layer_btn_layout.addWidget(btn_add)
        layer_btn_layout.addWidget(btn_del)
        layer_btn_layout.addWidget(btn_up)
        layer_btn_layout.addWidget(btn_down)
        layer_layout.addLayout(layer_btn_layout)
        
        self.layer_list = QListWidget()
        self.layer_list.currentRowChanged.connect(self._on_layer_selected)
        layer_layout.addWidget(self.layer_list)
        
        layout.addWidget(layer_group)
        
        return panel
    
    def _create_center_panel(self) -> QWidget:
        """创建中间面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        title = QLabel("背景预览")
        title.setStyleSheet("font-size: 12pt; font-weight: bold;")
        layout.addWidget(title)
        
        self.preview_view = BackgroundPreviewView()
        layout.addWidget(self.preview_view)
        
        # 控制
        ctrl_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.clicked.connect(self._toggle_animation)
        ctrl_layout.addWidget(self.play_btn)
        
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh_preview)
        ctrl_layout.addWidget(btn_refresh)
        
        layout.addLayout(ctrl_layout)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        tabs = QTabWidget()
        
        # 图层标签
        self.layer_editor = LayerEditorPanel()
        self.layer_editor.layer_changed.connect(self._on_layer_changed)
        tabs.addTab(self.layer_editor, "图层")
        
        # 摄像机标签
        self.camera_editor = CameraEditorPanel()
        self.camera_editor.camera_changed.connect(self._on_camera_changed)
        tabs.addTab(self.camera_editor, "摄像机")
        
        # 雾效标签
        self.fog_editor = FogEditorPanel()
        self.fog_editor.fog_changed.connect(self._on_fog_changed)
        tabs.addTab(self.fog_editor, "雾效")
        
        layout.addWidget(tabs)
        
        # 保存按钮
        btn_save = QPushButton("💾 保存配置")
        btn_save.setStyleSheet("font-size: 11pt; padding: 10px; background-color: #4CAF50;")
        btn_save.clicked.connect(self._save_config)
        layout.addWidget(btn_save)
        
        return panel
    
    def _setup_menu(self):
        """设置菜单"""
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件(&F)")
        
        new_action = QAction("新建", self)
        new_action.triggered.connect(self._new_background)
        file_menu.addAction(new_action)
        
        open_action = QAction("打开...", self)
        open_action.triggered.connect(self._open_config)
        file_menu.addAction(open_action)
        
        save_action = QAction("保存", self)
        save_action.triggered.connect(self._save_config)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
    
    def _apply_theme(self):
        """应用暗色主题"""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
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
                color: #aaa;
            }
            QPushButton {
                background-color: #3d3d3d;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
                color: #fff;
            }
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #3d3d3d;
            }
            QListWidget::item:selected {
                background-color: #007acc;
            }
            QTabWidget::pane {
                border: 1px solid #3d3d3d;
            }
            QTabBar::tab {
                background-color: #1e1e1e;
                color: #aaa;
                padding: 6px 14px;
                border: 1px solid #3d3d3d;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #2b2b2b;
                color: #fff;
            }
            QSlider::groove:horizontal {
                background: #1e1e1e;
                height: 6px;
            }
            QSlider::handle:horizontal {
                background: #007acc;
                width: 14px;
                margin: -4px 0;
            }
        """)
    
    def _scan_textures(self):
        """扫描可用纹理"""
        if IMAGES_ROOT.exists():
            for f in IMAGES_ROOT.glob("*.png"):
                self.texture_list.addItem(f.name)
            for f in IMAGES_ROOT.glob("*.jpg"):
                self.texture_list.addItem(f.name)
    
    def _refresh_layer_list(self):
        """刷新图层列表"""
        self.layer_list.clear()
        for layer in self.bg_data.layers:
            self.layer_list.addItem(f"[{layer.z_order}] {layer.name}")
    
    def _add_texture(self):
        """添加纹理"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择纹理",
            str(IMAGES_ROOT),
            "图片 (*.png *.jpg)"
        )
        if path:
            name = Path(path).stem
            tex = TextureConfig(name=name, path=Path(path).name)
            self.bg_data.textures.append(tex)
            self.texture_list.addItem(tex.path)
    
    def _add_layer(self):
        """添加图层"""
        idx = len(self.bg_data.layers)
        layer = LayerConfig(name=f"layer_{idx}", z_order=idx)
        self.bg_data.layers.append(layer)
        self._refresh_layer_list()
        self.layer_list.setCurrentRow(len(self.bg_data.layers) - 1)
    
    def _delete_layer(self):
        """删除图层"""
        row = self.layer_list.currentRow()
        if 0 <= row < len(self.bg_data.layers):
            del self.bg_data.layers[row]
            self._refresh_layer_list()
            self._refresh_preview()
    
    def _move_layer_up(self):
        """上移图层"""
        row = self.layer_list.currentRow()
        if row > 0:
            self.bg_data.layers[row], self.bg_data.layers[row-1] = \
                self.bg_data.layers[row-1], self.bg_data.layers[row]
            self._refresh_layer_list()
            self.layer_list.setCurrentRow(row - 1)
    
    def _move_layer_down(self):
        """下移图层"""
        row = self.layer_list.currentRow()
        if 0 <= row < len(self.bg_data.layers) - 1:
            self.bg_data.layers[row], self.bg_data.layers[row+1] = \
                self.bg_data.layers[row+1], self.bg_data.layers[row]
            self._refresh_layer_list()
            self.layer_list.setCurrentRow(row + 1)
    
    def _on_layer_selected(self, row: int):
        """图层选中"""
        if 0 <= row < len(self.bg_data.layers):
            self.current_layer_index = row
            layer = self.bg_data.layers[row]
            textures = [tex.name for tex in self.bg_data.textures]
            self.layer_editor.set_layer(layer, textures)
    
    def _on_info_changed(self):
        """信息变化"""
        self.bg_data.name = self.name_edit.text()
        self.bg_data.description = self.desc_edit.text()
        self.bg_data.scroll_speed = self.scroll_spin.value()
    
    def _on_layer_changed(self):
        """图层变化"""
        self._refresh_layer_list()
        if self.current_layer_index >= 0:
            self.layer_list.setCurrentRow(self.current_layer_index)
        self._refresh_preview()
    
    def _on_camera_changed(self):
        """摄像机变化"""
        self._refresh_preview()
    
    def _on_fog_changed(self):
        """雾效变化"""
        self._refresh_preview()
    
    def _refresh_preview(self):
        """刷新预览"""
        self.preview_view.set_background_data(self.bg_data)
    
    def _toggle_animation(self):
        """切换动画"""
        if self.preview_view.animation_running:
            self.preview_view.stop_animation()
            self.play_btn.setText("▶ 播放")
        else:
            self.preview_view.start_animation()
            self.play_btn.setText("⏸ 停止")
    
    def _new_background(self):
        """新建背景"""
        self.bg_data = BackgroundData()
        self.name_edit.setText(self.bg_data.name)
        self.desc_edit.setText("")
        self.scroll_spin.setValue(0.01)
        self._refresh_layer_list()
        self._refresh_preview()
        
        # 重置编辑器
        self.camera_editor.set_camera(self.bg_data.camera)
        self.fog_editor.set_fog(self.bg_data.fog)
    
    def _open_config(self):
        """打开配置"""
        path, _ = QFileDialog.getOpenFileName(
            self, "打开背景配置",
            str(GAME_CONTENT_ROOT),
            "JSON文件 (*.json)"
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 解析配置
                self.bg_data = BackgroundData(
                    name=data.get('name', ''),
                    description=data.get('description', ''),
                    scroll_speed=data.get('scroll_speed', 0.01)
                )
                
                # 纹理
                for tex in data.get('textures', []):
                    self.bg_data.textures.append(TextureConfig(
                        name=tex['name'],
                        path=tex['path']
                    ))
                
                # 图层
                for layer in data.get('layers', []):
                    self.bg_data.layers.append(LayerConfig(
                        name=layer.get('name', 'layer'),
                        texture=layer.get('texture', ''),
                        z_order=layer.get('z_order', 0),
                        scroll_x=layer.get('scroll_speed', [0, 0])[0] if isinstance(layer.get('scroll_speed'), list) else 0,
                        scroll_y=layer.get('scroll_speed', [0, 0])[1] if isinstance(layer.get('scroll_speed'), list) else 0,
                        parallax=layer.get('parallax_factor', 1.0),
                        alpha=layer.get('alpha', 1.0)
                    ))
                
                # 更新UI
                self.name_edit.setText(self.bg_data.name)
                self.desc_edit.setText(self.bg_data.description)
                self.scroll_spin.setValue(self.bg_data.scroll_speed)
                self._refresh_layer_list()
                self._refresh_preview()
                
                self.statusBar().showMessage(f"已加载: {path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载失败:\n{e}")
    
    def _save_config(self):
        """保存配置"""
        path, _ = QFileDialog.getSaveFileName(
            self, "保存背景配置",
            str(GAME_CONTENT_ROOT / "stages" / "stage1" / "background.json"),
            "JSON文件 (*.json)"
        )
        if path:
            config = {
                "name": self.bg_data.name,
                "description": self.bg_data.description,
                "scroll_speed": self.bg_data.scroll_speed,
                "textures": [
                    {"name": tex.name, "path": tex.path}
                    for tex in self.bg_data.textures
                ],
                "camera": {
                    "eye": [self.bg_data.camera.eye_x, self.bg_data.camera.eye_y, self.bg_data.camera.eye_z],
                    "at": [self.bg_data.camera.at_x, self.bg_data.camera.at_y, self.bg_data.camera.at_z],
                    "fovy": self.bg_data.camera.fovy,
                    "z_near": self.bg_data.camera.z_near,
                    "z_far": self.bg_data.camera.z_far
                },
                "fog": {
                    "enabled": self.bg_data.fog.enabled,
                    "start": self.bg_data.fog.start,
                    "end": self.bg_data.fog.end,
                    "color": [
                        self.bg_data.fog.color_r,
                        self.bg_data.fog.color_g,
                        self.bg_data.fog.color_b,
                        self.bg_data.fog.color_a
                    ]
                },
                "layers": [
                    {
                        "name": layer.name,
                        "texture": layer.texture,
                        "z_order": layer.z_order,
                        "scroll_speed": [layer.scroll_x, layer.scroll_y],
                        "parallax_factor": layer.parallax,
                        "alpha": layer.alpha,
                        "blend_mode": layer.blend_mode,
                        "tile_repeat": [layer.tile_x, layer.tile_y],
                        "use_3d": layer.use_3d
                    }
                    for layer in self.bg_data.layers
                ]
            }
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.statusBar().showMessage(f"已保存: {path}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = BackgroundEditor()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
