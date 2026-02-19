#!/usr/bin/env python3
"""
自机行为外貌编辑器

功能:
- 编辑玩家角色配置 (config.json)
- 动画状态机可视化编辑
- 精灵/帧预览
- 射击类型配置
- Option子机配置
- 脚本行为预览
- 键位配置
"""

import sys
import os
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QGroupBox, QFormLayout, QScrollArea, QFrame, QTabWidget,
    QFileDialog, QMessageBox, QToolBar, QAction, QStatusBar, QSlider,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
    QGraphicsEllipseItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QDialogButtonBox, QStackedWidget
)
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush, QFont, 
    QIcon, QKeySequence, QTransform
)

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ASSETS_ROOT = PROJECT_ROOT / "assets"
PLAYERS_ROOT = ASSETS_ROOT / "players"


# ==================== 数据模型 ====================

@dataclass
class SpriteData:
    """精灵数据"""
    name: str
    rect: Tuple[int, int, int, int]  # x, y, w, h
    center: Tuple[float, float] = (0.5, 0.5)
    source: str = 'player'  # 'player' 或 'bullet'


@dataclass
class AnimationData:
    """动画数据"""
    name: str
    frames: List[str] = field(default_factory=list)
    fps: int = 8
    loop: bool = True


@dataclass
class ShotTypeData:
    """射击类型数据"""
    name: str = "main"
    damage: float = 10.0
    speed: float = 0.05
    interval: int = 4
    spread: float = 0.0
    count: int = 1
    sprite: str = ""


@dataclass
class OptionData:
    """子机数据"""
    name: str = "option"
    offset_x: float = 0.0
    offset_y: float = 0.0
    shot_type: str = "homing"
    damage: float = 5.0
    interval: int = 8


@dataclass
class PlayerConfigData:
    """玩家配置数据"""
    name: str = "新角色"
    description: str = ""
    author: str = ""
    texture: str = ""
    bullet_texture: str = ""

    # 渲染
    render_size_px: int = 32
    render_downsample: bool = False
    
    # 属性
    speed_high: float = 0.02
    speed_low: float = 0.008
    hitbox_radius: float = 3.0
    graze_radius: float = 24.0
    hitbox_offset_x: float = 0.0
    hitbox_offset_y: float = 0.0
    
    # 初始值
    lives: int = 3
    bombs: int = 3
    power: float = 1.0
    
    # 精灵
    sprites: Dict[str, SpriteData] = field(default_factory=dict)
    
    # 动画
    animations: Dict[str, AnimationData] = field(default_factory=dict)
    animation_transition_speed: float = 8.0
    full_tilt_frames: int = 8  # 持续移动多少帧后进入完全倾斜(move_left_full/move_right_full)
    
    # 射击
    shot_types: Dict[str, ShotTypeData] = field(default_factory=dict)
    
    # 子机
    options: List[OptionData] = field(default_factory=list)


# ==================== 精灵预览视图 ====================

class SpritePreviewView(QGraphicsView):
    """精灵预览视图"""
    
    sprite_rect_changed = pyqtSignal(int, int, int, int)
    hitbox_offset_changed = pyqtSignal(float, float)
    region_selected = pyqtSignal(int, int, int, int)  # x, y, w, h
    sprite_clicked = pyqtSignal(str)  # 点击精灵名
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        
        self.texture_item: Optional[QGraphicsPixmapItem] = None
        self.rect_items: Dict[str, QGraphicsRectItem] = {}
        self.selected_rect: Optional[QGraphicsRectItem] = None

        self.hitbox_item: Optional[QGraphicsEllipseItem] = None
        self._hitbox_rect: Optional[Tuple[int, int, int, int]] = None
        self._hitbox_radius: float = 0.0
        self._drag_hitbox = False

        # 拖选区域
        self._drag_region = False
        self._region_start: Optional[QPointF] = None
        self._region_rect_item: Optional[QGraphicsRectItem] = None
        
        self._zoom = 2.0
        self.setTransform(QTransform().scale(self._zoom, self._zoom))
    
    def load_texture(self, path: str):
        """加载纹理"""
        if not Path(path).exists():
            return
        
        self.scene.clear()
        self.rect_items.clear()
        self.hitbox_item = None
        self._hitbox_rect = None
        self._hitbox_radius = 0.0
        self._region_rect_item = None
        
        pixmap = QPixmap(path)
        self.texture_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.texture_item)
        self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())

    def set_hitbox(self, rect: Optional[Tuple[int, int, int, int]],
                   radius: float, offset_x: float, offset_y: float,
                   visible: bool = True):
        """设置判定点显示（基于当前精灵 rect）"""
        self._hitbox_rect = rect
        self._hitbox_radius = radius

        if not rect or radius <= 0 or not visible:
            if self.hitbox_item:
                self.hitbox_item.setVisible(False)
            return

        if self.hitbox_item is None:
            pen = QPen(QColor(255, 80, 80), 2)
            brush = QBrush(QColor(255, 80, 80, 40))
            self.hitbox_item = self.scene.addEllipse(0, 0, 1, 1, pen, brush)
            self.hitbox_item.setZValue(20)

        self.hitbox_item.setVisible(True)
        self._update_hitbox_position(offset_x, offset_y)

    def _update_hitbox_position(self, offset_x: float, offset_y: float):
        if not self._hitbox_rect or not self.hitbox_item:
            return
        x, y, w, h = self._hitbox_rect
        cx = x + w / 2 + offset_x
        cy = y + h / 2 + offset_y
        r = self._hitbox_radius
        self.hitbox_item.setRect(cx - r, cy - r, r * 2, r * 2)
    
    def add_sprite_rect(self, name: str, rect: Tuple[int, int, int, int],
                         selected: bool = False, for_anim: bool = False):
        """添加精灵矩形"""
        x, y, w, h = rect
        
        if selected:
            pen = QPen(QColor(255, 100, 100), 2)
        elif for_anim:
            pen = QPen(QColor(100, 255, 100), 2)
        else:
            pen = QPen(QColor(100, 200, 255), 1)
        
        rect_item = self.scene.addRect(x, y, w, h, pen)
        rect_item.setZValue(10)
        self.rect_items[name] = rect_item
        
        if selected:
            self.selected_rect = rect_item
    
    def clear_rects(self):
        """清除矩形"""
        for item in self.rect_items.values():
            self.scene.removeItem(item)
        self.rect_items.clear()
        self.selected_rect = None
    
    def zoom_in(self):
        self._zoom = min(8.0, self._zoom * 1.25)
        self.setTransform(QTransform().scale(self._zoom, self._zoom))
    
    def zoom_out(self):
        self._zoom = max(0.5, self._zoom / 1.25)
        self.setTransform(QTransform().scale(self._zoom, self._zoom))
    
    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def mousePressEvent(self, event):
        # 判定点拖拽（左键）
        if event.button() == Qt.LeftButton:
            if self.hitbox_item and self.hitbox_item.isVisible():
                scene_pos = self.mapToScene(event.pos())
                if self.hitbox_item.contains(self.hitbox_item.mapFromScene(scene_pos)):
                    self._drag_hitbox = True
                    event.accept()
                    return
            # 左键点击精灵矩形
            scene_pos = self.mapToScene(event.pos())
            for name, rect_item in self.rect_items.items():
                if rect_item.rect().contains(scene_pos):
                    self.sprite_clicked.emit(name)
                    event.accept()
                    return
        # 右键拖选区域
        if event.button() == Qt.RightButton:
            self._region_start = self.mapToScene(event.pos())
            self._drag_region = True
            if self._region_rect_item:
                self.scene.removeItem(self._region_rect_item)
                self._region_rect_item = None
            pen = QPen(QColor(80, 160, 255), 1, Qt.DashLine)
            brush = QBrush(QColor(80, 160, 255, 40))
            self._region_rect_item = self.scene.addRect(
                self._region_start.x(), self._region_start.y(), 0, 0, pen, brush)
            self._region_rect_item.setZValue(30)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_hitbox and self._hitbox_rect and self.hitbox_item:
            scene_pos = self.mapToScene(event.pos())
            x, y, w, h = self._hitbox_rect
            cx = x + w / 2
            cy = y + h / 2
            offset_x = scene_pos.x() - cx
            offset_y = scene_pos.y() - cy
            self._update_hitbox_position(offset_x, offset_y)
            self.hitbox_offset_changed.emit(offset_x, offset_y)
            event.accept()
            return
        if self._drag_region and self._region_start and self._region_rect_item:
            cur = self.mapToScene(event.pos())
            x = min(self._region_start.x(), cur.x())
            y = min(self._region_start.y(), cur.y())
            w = abs(cur.x() - self._region_start.x())
            h = abs(cur.y() - self._region_start.y())
            self._region_rect_item.setRect(x, y, w, h)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_hitbox:
            self._drag_hitbox = False
            event.accept()
            return
        if self._drag_region and self._region_start:
            self._drag_region = False
            cur = self.mapToScene(event.pos())
            x = int(min(self._region_start.x(), cur.x()))
            y = int(min(self._region_start.y(), cur.y()))
            w = int(abs(cur.x() - self._region_start.x()))
            h = int(abs(cur.y() - self._region_start.y()))
            if w > 4 and h > 4:
                self.region_selected.emit(x, y, w, h)
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ==================== 动画预览视图 ====================

class AnimationPreviewView(QWidget):
    """动画预览视图"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
        self.texture: Optional[QPixmap] = None
        self.bullet_texture: Optional[QPixmap] = None
        self.sprites: Dict[str, SpriteData] = {}
        self.current_animation: Optional[AnimationData] = None
        self.current_frame = 0
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._next_frame)
        self.playing = False
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 预览标签
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(128, 128)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #1a1a2a; border: 1px solid #444;")
        layout.addWidget(self.preview_label, alignment=Qt.AlignCenter)
        
        # 控制
        ctrl_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(40)
        self.play_btn.clicked.connect(self._toggle_play)
        ctrl_layout.addWidget(self.play_btn)
        
        btn_prev = QPushButton("◀")
        btn_prev.setFixedWidth(30)
        btn_prev.clicked.connect(self._prev_frame)
        ctrl_layout.addWidget(btn_prev)
        
        btn_next = QPushButton("▶")
        btn_next.setFixedWidth(30)
        btn_next.clicked.connect(self._next_frame_manual)
        ctrl_layout.addWidget(btn_next)
        
        layout.addLayout(ctrl_layout)
        
        # 帧信息
        self.frame_label = QLabel("帧: 0/0")
        self.frame_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.frame_label)
    
    def set_texture(self, pixmap: QPixmap):
        """设置自机纹理"""
        self.texture = pixmap
    
    def set_bullet_texture(self, pixmap: Optional[QPixmap]):
        """设置子弹纹理（用于子弹精灵的动画预览）"""
        self.bullet_texture = pixmap
    
    def set_sprites(self, sprites: Dict[str, SpriteData]):
        """设置精灵数据"""
        self.sprites = sprites
    
    def set_animation(self, anim: AnimationData):
        """设置动画"""
        self.current_animation = anim
        self.current_frame = 0
        self._update_display()
        
        # 设置定时器间隔
        if anim.fps > 0:
            self.timer.setInterval(int(1000 / anim.fps))

    def set_frame_index(self, index: int):
        """手动设置当前帧"""
        if not self.current_animation:
            return
        frames = self.current_animation.frames
        if not frames:
            return
        self.current_frame = max(0, min(index, len(frames) - 1))
        self._update_display()
    
    def _update_display(self):
        """更新显示"""
        if not self.current_animation:
            return
        
        frames = self.current_animation.frames
        if not frames:
            return
        
        frame_name = frames[self.current_frame % len(frames)]
        sprite = self.sprites.get(frame_name)
        
        if sprite:
            tex = self.bullet_texture if getattr(sprite, 'source', 'player') == 'bullet' else self.texture
            if tex and not tex.isNull():
                x, y, w, h = sprite.rect
                cropped = tex.copy(x, y, w, h)
                scaled = cropped.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_label.setPixmap(scaled)
        
        self.frame_label.setText(f"帧: {self.current_frame + 1}/{len(frames)}")
    
    def _toggle_play(self):
        """切换播放"""
        if self.playing:
            self.timer.stop()
            self.playing = False
            self.play_btn.setText("▶")
        else:
            self.timer.start()
            self.playing = True
            self.play_btn.setText("⏸")
    
    def _next_frame(self):
        """下一帧"""
        if self.current_animation:
            frames = self.current_animation.frames
            if frames:
                self.current_frame = (self.current_frame + 1) % len(frames)
                self._update_display()
    
    def _next_frame_manual(self):
        """手动下一帧"""
        self._next_frame()
    
    def _prev_frame(self):
        """上一帧"""
        if self.current_animation:
            frames = self.current_animation.frames
            if frames:
                self.current_frame = (self.current_frame - 1) % len(frames)
                self._update_display()


# ==================== 动画状态机视图 ====================

class AnimationStateMachineView(QGraphicsView):
    """动画状态机可视化视图"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(25, 25, 35)))
        self.setMinimumSize(300, 200)
        
        self.state_items: Dict[str, QGraphicsRectItem] = {}
    
    def set_states(self, animations: Dict[str, AnimationData]):
        """设置状态"""
        self.scene.clear()
        self.state_items.clear()
        
        # 预定义位置：idle 中心，左移加速/全速在左，右移加速/全速在右
        positions = {
            'idle': (200, 120),
            'move_left': (80, 60),
            'move_left_full': (80, 180),
            'move_right': (320, 60),
            'move_right_full': (320, 180),
            'death': (200, 240),
            'spawn': (200, 0),
        }
        
        idx = 0
        for name in animations:
            x, y = positions.get(name, (50 + (idx % 4) * 80, 250 + (idx // 4) * 50))
            self._add_state_node(name, x, y)
            idx += 1
        
        # 绘制转换线
        self._draw_transitions(animations)
    
    def _add_state_node(self, name: str, x: float, y: float):
        """添加状态节点"""
        # 节点矩形
        pen = QPen(QColor(100, 150, 255), 2)
        brush = QBrush(QColor(40, 50, 70))
        
        rect = self.scene.addRect(x, y, 80, 40, pen, brush)
        rect.setZValue(10)
        self.state_items[name] = rect
        
        # 标签
        text = self.scene.addText(name[:8], QFont("Arial", 8))
        text.setDefaultTextColor(QColor(200, 200, 200))
        text.setPos(x + 5, y + 10)
        text.setZValue(11)
    
    def _draw_transitions(self, animations: dict = None):
        """绘制转换线 - 两阶段动画：idle↔move_left↔move_left_full"""
        transitions = [
            ('idle', 'move_left'),
            ('idle', 'move_right'),
            ('move_left', 'move_left_full'),
            ('move_right', 'move_right_full'),
            ('move_left_full', 'move_left'),
            ('move_right_full', 'move_right'),
            ('move_left', 'idle'),
            ('move_right', 'idle'),
            ('move_left_full', 'idle'),
            ('move_right_full', 'idle'),
        ]
        
        pen = QPen(QColor(80, 80, 100), 1, Qt.DashLine)
        
        for from_state, to_state in transitions:
            if from_state in self.state_items and to_state in self.state_items:
                from_rect = self.state_items[from_state].rect()
                to_rect = self.state_items[to_state].rect()
                
                self.scene.addLine(
                    from_rect.center().x(), from_rect.center().y(),
                    to_rect.center().x(), to_rect.center().y(),
                    pen
                )


# ==================== 射击类型编辑器 ====================

class ShotTypeEditor(QWidget):
    """射击类型编辑器"""
    
    shot_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shot: Optional[ShotTypeData] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_change)
        form.addRow("名称:", self.name_edit)
        
        self.damage_spin = QDoubleSpinBox()
        self.damage_spin.setRange(1, 1000)
        self.damage_spin.valueChanged.connect(self._on_change)
        form.addRow("伤害:", self.damage_spin)
        
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.001, 0.5)
        self.speed_spin.setDecimals(3)
        self.speed_spin.setSingleStep(0.005)
        self.speed_spin.valueChanged.connect(self._on_change)
        form.addRow("速度:", self.speed_spin)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.valueChanged.connect(self._on_change)
        form.addRow("间隔(帧):", self.interval_spin)
        
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 20)
        self.count_spin.valueChanged.connect(self._on_change)
        form.addRow("弹数:", self.count_spin)
        
        self.spread_spin = QDoubleSpinBox()
        self.spread_spin.setRange(0, 90)
        self.spread_spin.valueChanged.connect(self._on_change)
        form.addRow("扩散角度:", self.spread_spin)
        
        self.sprite_edit = QLineEdit()
        self.sprite_edit.textChanged.connect(self._on_change)
        form.addRow("精灵:", self.sprite_edit)
        
        layout.addLayout(form)
    
    def set_shot(self, shot: ShotTypeData):
        """设置射击类型"""
        self._shot = shot
        
        self.blockSignals(True)
        self.name_edit.setText(shot.name)
        self.damage_spin.setValue(shot.damage)
        self.speed_spin.setValue(shot.speed)
        self.interval_spin.setValue(shot.interval)
        self.count_spin.setValue(shot.count)
        self.spread_spin.setValue(shot.spread)
        self.sprite_edit.setText(shot.sprite)
        self.blockSignals(False)
    
    def _on_change(self):
        if not self._shot:
            return
        
        self._shot.name = self.name_edit.text()
        self._shot.damage = self.damage_spin.value()
        self._shot.speed = self.speed_spin.value()
        self._shot.interval = self.interval_spin.value()
        self._shot.count = self.count_spin.value()
        self._shot.spread = self.spread_spin.value()
        self._shot.sprite = self.sprite_edit.text()
        
        self.shot_changed.emit()


# ==================== 子机编辑器 ====================

class OptionEditor(QWidget):
    """子机编辑器"""
    
    option_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._option: Optional[OptionData] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_change)
        form.addRow("名称:", self.name_edit)
        
        # 偏移
        offset_widget = QWidget()
        offset_layout = QHBoxLayout(offset_widget)
        offset_layout.setContentsMargins(0, 0, 0, 0)
        
        self.offset_x_spin = QDoubleSpinBox()
        self.offset_x_spin.setRange(-1, 1)
        self.offset_x_spin.setSingleStep(0.01)
        self.offset_x_spin.setDecimals(3)
        self.offset_x_spin.valueChanged.connect(self._on_change)
        
        self.offset_y_spin = QDoubleSpinBox()
        self.offset_y_spin.setRange(-1, 1)
        self.offset_y_spin.setSingleStep(0.01)
        self.offset_y_spin.setDecimals(3)
        self.offset_y_spin.valueChanged.connect(self._on_change)
        
        offset_layout.addWidget(QLabel("X:"))
        offset_layout.addWidget(self.offset_x_spin)
        offset_layout.addWidget(QLabel("Y:"))
        offset_layout.addWidget(self.offset_y_spin)
        
        form.addRow("偏移:", offset_widget)
        
        self.shot_type_combo = QComboBox()
        self.shot_type_combo.addItems(["homing", "straight", "spread"])
        self.shot_type_combo.currentTextChanged.connect(self._on_change)
        form.addRow("射击类型:", self.shot_type_combo)
        
        self.damage_spin = QDoubleSpinBox()
        self.damage_spin.setRange(1, 100)
        self.damage_spin.valueChanged.connect(self._on_change)
        form.addRow("伤害:", self.damage_spin)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.valueChanged.connect(self._on_change)
        form.addRow("间隔(帧):", self.interval_spin)
        
        layout.addLayout(form)
    
    def set_option(self, option: OptionData):
        """设置子机"""
        self._option = option
        
        self.blockSignals(True)
        self.name_edit.setText(option.name)
        self.offset_x_spin.setValue(option.offset_x)
        self.offset_y_spin.setValue(option.offset_y)
        self.shot_type_combo.setCurrentText(option.shot_type)
        self.damage_spin.setValue(option.damage)
        self.interval_spin.setValue(option.interval)
        self.blockSignals(False)
    
    def _on_change(self):
        if not self._option:
            return
        
        self._option.name = self.name_edit.text()
        self._option.offset_x = self.offset_x_spin.value()
        self._option.offset_y = self.offset_y_spin.value()
        self._option.shot_type = self.shot_type_combo.currentText()
        self._option.damage = self.damage_spin.value()
        self._option.interval = self.interval_spin.value()
        
        self.option_changed.emit()


# ==================== 主窗口 ====================

class PlayerEditor(QMainWindow):
    """自机编辑器主窗口"""
    
    def __init__(self):
        super().__init__()
        
        self.player_data = PlayerConfigData()
        self.texture_path: Optional[str] = None
        self.texture_pixmap: Optional[QPixmap] = None
        self.bullet_texture_path: Optional[str] = None
        self.bullet_texture_pixmap: Optional[QPixmap] = None
        self._viewing_bullet_tex = False
        self._suppress_sprite_change = False
        self._current_sprite_key: Optional[str] = None
        self._suppress_hitbox_change = False
        
        self._setup_ui()
        self._setup_menu()
        self._apply_theme()
        
        self.setWindowTitle("自机行为外貌编辑器 - PySTG")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)
        
        # 扫描可用玩家
        self._scan_players()
    
    def _setup_ui(self):
        """设置UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧 - 玩家列表和基本信息
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # 中间 - 精灵/动画预览
        center_panel = self._create_center_panel()
        splitter.addWidget(center_panel)
        
        # 右侧 - 属性编辑
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([300, 500, 400])
        
        self.statusBar().showMessage("就绪")
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 玩家选择
        player_group = QGroupBox("玩家角色")
        player_layout = QVBoxLayout(player_group)
        
        self.player_list = QListWidget()
        self.player_list.currentItemChanged.connect(self._on_player_selected)
        player_layout.addWidget(self.player_list)
        
        btn_layout = QHBoxLayout()
        btn_new = QPushButton("新建")
        btn_new.clicked.connect(self._new_player)
        btn_layout.addWidget(btn_new)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._scan_players)
        btn_layout.addWidget(btn_refresh)
        player_layout.addLayout(btn_layout)
        
        layout.addWidget(player_group)
        
        # 基本信息
        info_group = QGroupBox("基本信息")
        info_layout = QFormLayout(info_group)
        
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_info_changed)
        info_layout.addRow("名称:", self.name_edit)
        
        self.desc_edit = QLineEdit()
        self.desc_edit.textChanged.connect(self._on_info_changed)
        info_layout.addRow("描述:", self.desc_edit)
        
        self.author_edit = QLineEdit()
        self.author_edit.textChanged.connect(self._on_info_changed)
        info_layout.addRow("作者:", self.author_edit)
        
        layout.addWidget(info_group)
        
        # 属性
        stats_group = QGroupBox("属性")
        stats_layout = QFormLayout(stats_group)
        
        self.speed_high_spin = QDoubleSpinBox()
        self.speed_high_spin.setRange(0.001, 0.1)
        self.speed_high_spin.setDecimals(3)
        self.speed_high_spin.setSingleStep(0.001)
        self.speed_high_spin.valueChanged.connect(self._on_stats_changed)
        stats_layout.addRow("高速:", self.speed_high_spin)
        
        self.speed_low_spin = QDoubleSpinBox()
        self.speed_low_spin.setRange(0.001, 0.1)
        self.speed_low_spin.setDecimals(3)
        self.speed_low_spin.setSingleStep(0.001)
        self.speed_low_spin.valueChanged.connect(self._on_stats_changed)
        stats_layout.addRow("低速:", self.speed_low_spin)
        
        self.hitbox_spin = QDoubleSpinBox()
        self.hitbox_spin.setRange(0.5, 20)
        self.hitbox_spin.valueChanged.connect(self._on_stats_changed)
        stats_layout.addRow("判定半径:", self.hitbox_spin)
        
        self.graze_spin = QDoubleSpinBox()
        self.graze_spin.setRange(5, 100)
        self.graze_spin.valueChanged.connect(self._on_stats_changed)
        stats_layout.addRow("擦弹半径:", self.graze_spin)

        self.hitbox_offset_x_spin = QDoubleSpinBox()
        self.hitbox_offset_x_spin.setRange(-50, 50)
        self.hitbox_offset_x_spin.setDecimals(2)
        self.hitbox_offset_x_spin.valueChanged.connect(self._on_stats_changed)
        stats_layout.addRow("判定偏移X:", self.hitbox_offset_x_spin)

        self.hitbox_offset_y_spin = QDoubleSpinBox()
        self.hitbox_offset_y_spin.setRange(-50, 50)
        self.hitbox_offset_y_spin.setDecimals(2)
        self.hitbox_offset_y_spin.valueChanged.connect(self._on_stats_changed)
        stats_layout.addRow("判定偏移Y:", self.hitbox_offset_y_spin)
        
        layout.addWidget(stats_group)

        render_group = QGroupBox("渲染")
        render_layout = QFormLayout(render_group)

        self.render_size_spin = QSpinBox()
        self.render_size_spin.setRange(8, 256)
        self.render_size_spin.valueChanged.connect(self._on_stats_changed)
        render_layout.addRow("显示尺寸(px):", self.render_size_spin)

        self.render_downsample_cb = QCheckBox("降采样贴图")
        self.render_downsample_cb.toggled.connect(self._on_stats_changed)
        render_layout.addRow("", self.render_downsample_cb)

        layout.addWidget(render_group)
        
        # 初始值
        init_group = QGroupBox("初始值")
        init_layout = QFormLayout(init_group)
        
        self.lives_spin = QSpinBox()
        self.lives_spin.setRange(1, 9)
        self.lives_spin.valueChanged.connect(self._on_stats_changed)
        init_layout.addRow("残机:", self.lives_spin)
        
        self.bombs_spin = QSpinBox()
        self.bombs_spin.setRange(0, 9)
        self.bombs_spin.valueChanged.connect(self._on_stats_changed)
        init_layout.addRow("符卡:", self.bombs_spin)
        
        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(1.0, 4.0)
        self.power_spin.valueChanged.connect(self._on_stats_changed)
        init_layout.addRow("灵力:", self.power_spin)
        
        layout.addWidget(init_group)
        
        return panel
    
    def _create_center_panel(self) -> QWidget:
        """创建中间面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 精灵预览
        sprite_group = QGroupBox("纹理预览")
        sprite_layout = QVBoxLayout(sprite_group)
        
        # 工具栏
        toolbar = QHBoxLayout()
        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedWidth(30)
        btn_zoom_in.clicked.connect(lambda: self.sprite_view.zoom_in())
        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedWidth(30)
        btn_zoom_out.clicked.connect(lambda: self.sprite_view.zoom_out())
        toolbar.addWidget(btn_zoom_in)
        toolbar.addWidget(btn_zoom_out)
        
        toolbar.addWidget(QLabel("  显示:"))
        self._tex_switch_combo = QComboBox()
        self._tex_switch_combo.addItem("自机纹理", "player")
        self._tex_switch_combo.addItem("子弹纹理", "bullet")
        self._tex_switch_combo.setFixedWidth(100)
        self._tex_switch_combo.currentIndexChanged.connect(self._on_tex_switch)
        toolbar.addWidget(self._tex_switch_combo)
        
        toolbar.addStretch()
        sprite_layout.addLayout(toolbar)
        
        self.sprite_view = SpritePreviewView()
        self.sprite_view.hitbox_offset_changed.connect(self._on_hitbox_dragged)
        self.sprite_view.region_selected.connect(self._region_auto_detect)
        self.sprite_view.sprite_clicked.connect(self._on_preview_sprite_clicked)
        sprite_layout.addWidget(self.sprite_view)
        
        layout.addWidget(sprite_group, stretch=2)
        
        # 动画预览
        anim_group = QGroupBox("动画预览")
        anim_layout = QHBoxLayout(anim_group)
        
        # 动画播放器
        self.anim_preview = AnimationPreviewView()
        anim_layout.addWidget(self.anim_preview)
        
        # 状态机视图
        self.state_machine_view = AnimationStateMachineView()
        anim_layout.addWidget(self.state_machine_view)
        
        layout.addWidget(anim_group, stretch=1)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板 — 向导式"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 步骤指示器
        self._step_labels = []
        step_names = ["① 纹理", "② 切割", "③ 动画", "④ 绑定"]
        step_bar = QHBoxLayout()
        for i, name in enumerate(step_names):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("padding:4px; font-weight:bold;")
            step_bar.addWidget(lbl)
            self._step_labels.append(lbl)
        layout.addLayout(step_bar)
        
        # 步骤页面
        self._wizard_stack = QStackedWidget()
        self._wizard_stack.addWidget(self._create_step_texture())
        self._wizard_stack.addWidget(self._create_step_cut())
        self._wizard_stack.addWidget(self._create_step_animate())
        self._wizard_stack.addWidget(self._create_step_bind())
        layout.addWidget(self._wizard_stack, stretch=1)
        
        # 导航按钮
        nav = QHBoxLayout()
        self._btn_prev = QPushButton("← 上一步")
        self._btn_prev.clicked.connect(self._wizard_prev)
        self._btn_next = QPushButton("下一步 →")
        self._btn_next.clicked.connect(self._wizard_next)
        btn_save = QPushButton("💾 保存")
        btn_save.setStyleSheet("background-color: #4CAF50;")
        btn_save.clicked.connect(self._save_config)
        nav.addWidget(self._btn_prev)
        nav.addWidget(self._btn_next)
        nav.addWidget(btn_save)
        layout.addLayout(nav)
        
        self._update_wizard_step(0)
        return panel
    
    def _update_wizard_step(self, idx: int):
        """更新向导步骤"""
        self._wizard_stack.setCurrentIndex(idx)
        for i, lbl in enumerate(self._step_labels):
            if i == idx:
                lbl.setStyleSheet("padding:4px; font-weight:bold; background:#4a90d9; color:white; border-radius:3px;")
            elif i < idx:
                lbl.setStyleSheet("padding:4px; font-weight:bold; color:#4CAF50;")
            else:
                lbl.setStyleSheet("padding:4px; font-weight:bold; color:#888;")
        self._btn_prev.setEnabled(idx > 0)
        self._btn_next.setEnabled(idx < 3)
        # 进入步骤③时刷新精灵缩略图网格
        if idx == 2:
            self._refresh_sprite_thumb_grid()
        # 进入步骤④时刷新行为绑定下拉框
        if idx == 3:
            self._refresh_behavior_combos()
    
    def _wizard_prev(self):
        idx = self._wizard_stack.currentIndex()
        if idx > 0:
            self._update_wizard_step(idx - 1)
    
    def _wizard_next(self):
        idx = self._wizard_stack.currentIndex()
        if idx < 3:
            self._update_wizard_step(idx + 1)
    
    # ── 步骤① 纹理 ──
    def _create_step_texture(self) -> QWidget:
        """步骤①：选择纹理"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addWidget(QLabel("选择纹理文件，用于后续精灵切割。"))
        
        form = QFormLayout()
        
        # 自机纹理
        tex_w = QWidget()
        tex_l = QHBoxLayout(tex_w)
        tex_l.setContentsMargins(0, 0, 0, 0)
        self.texture_label = QLineEdit()
        self.texture_label.setReadOnly(True)
        self.texture_label.setPlaceholderText("(未选择)")
        tex_l.addWidget(self.texture_label)
        btn_tex = QPushButton("选择...")
        btn_tex.clicked.connect(self._choose_texture)
        tex_l.addWidget(btn_tex)
        form.addRow("自机纹理:", tex_w)
        
        # 子弹纹理
        btex_w = QWidget()
        btex_l = QHBoxLayout(btex_w)
        btex_l.setContentsMargins(0, 0, 0, 0)
        self.bullet_texture_label = QLineEdit()
        self.bullet_texture_label.setReadOnly(True)
        self.bullet_texture_label.setPlaceholderText("(共用自机纹理)")
        btex_l.addWidget(self.bullet_texture_label)
        btn_btex = QPushButton("选择...")
        btn_btex.clicked.connect(self._choose_bullet_texture)
        btex_l.addWidget(btn_btex)
        btn_btex_clr = QPushButton("×")
        btn_btex_clr.setFixedWidth(24)
        btn_btex_clr.clicked.connect(lambda: (
            setattr(self.player_data, 'bullet_texture', ''),
            self.bullet_texture_label.clear()
        ))
        btex_l.addWidget(btn_btex_clr)
        form.addRow("子弹纹理:", btex_w)
        
        layout.addLayout(form)
        
        # 纹理信息
        self._tex_info_label = QLabel("")
        self._tex_info_label.setStyleSheet("color:#aaa;")
        layout.addWidget(self._tex_info_label)
        
        # 纹理预览缩略图
        self._tex_preview_label = QLabel()
        self._tex_preview_label.setFixedHeight(200)
        self._tex_preview_label.setAlignment(Qt.AlignCenter)
        self._tex_preview_label.setStyleSheet("background:#1a1a1a; border:1px solid #333;")
        layout.addWidget(self._tex_preview_label)
        
        layout.addStretch()
        return widget
    
    # ── 步骤② 切割 ──
    def _create_step_cut(self) -> QWidget:
        """步骤②：精灵切割"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addWidget(QLabel("切割纹理为精灵。右键在预览画布拖选区域可自动检测。"))
        
        # 切割工具按钮
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("+ 手动添加")
        btn_add.clicked.connect(self._add_sprite)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._delete_sprite)
        btn_grid = QPushButton("⊞ 网格切割")
        btn_grid.setToolTip("按行列均匀切割纹理，批量生成精灵")
        btn_grid.clicked.connect(self._open_grid_split_dialog)
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_del)
        btn_layout.addWidget(btn_grid)
        layout.addLayout(btn_layout)
        
        # 精灵列表
        self.sprite_list = QListWidget()
        self.sprite_list.currentTextChanged.connect(self._on_sprite_selected)
        layout.addWidget(self.sprite_list)
        
        # 精灵属性
        form = QFormLayout()
        self.sprite_name_edit = QLineEdit()
        self.sprite_name_edit.textChanged.connect(self._on_sprite_changed)
        form.addRow("名称:", self.sprite_name_edit)
        
        rect_widget = QWidget()
        rect_layout = QHBoxLayout(rect_widget)
        rect_layout.setContentsMargins(0, 0, 0, 0)
        self.sprite_x = QSpinBox()
        self.sprite_x.setRange(0, 9999)
        self.sprite_x.valueChanged.connect(self._on_sprite_changed)
        self.sprite_y = QSpinBox()
        self.sprite_y.setRange(0, 9999)
        self.sprite_y.valueChanged.connect(self._on_sprite_changed)
        self.sprite_w = QSpinBox()
        self.sprite_w.setRange(1, 9999)
        self.sprite_w.valueChanged.connect(self._on_sprite_changed)
        self.sprite_h = QSpinBox()
        self.sprite_h.setRange(1, 9999)
        self.sprite_h.valueChanged.connect(self._on_sprite_changed)
        rect_layout.addWidget(QLabel("X:"))
        rect_layout.addWidget(self.sprite_x)
        rect_layout.addWidget(QLabel("Y:"))
        rect_layout.addWidget(self.sprite_y)
        rect_layout.addWidget(QLabel("W:"))
        rect_layout.addWidget(self.sprite_w)
        rect_layout.addWidget(QLabel("H:"))
        rect_layout.addWidget(self.sprite_h)
        form.addRow("区域:", rect_widget)
        
        layout.addLayout(form)
        return widget
    
    # ── 步骤③ 动画 ──
    def _create_step_animate(self) -> QWidget:
        """步骤③：创建动画"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addWidget(QLabel("选择精灵创建动画。可多选缩略图或在预览区左键点击精灵。"))
        
        # 精灵缩略图网格（多选）
        self._sprite_thumb_area = QScrollArea()
        self._sprite_thumb_area.setFixedHeight(120)
        self._sprite_thumb_area.setWidgetResizable(True)
        self._sprite_thumb_container = QWidget()
        self._sprite_thumb_flow = QHBoxLayout(self._sprite_thumb_container)
        self._sprite_thumb_flow.setContentsMargins(2, 2, 2, 2)
        self._sprite_thumb_flow.setSpacing(4)
        self._sprite_thumb_flow.addStretch()
        self._sprite_thumb_area.setWidget(self._sprite_thumb_container)
        layout.addWidget(self._sprite_thumb_area)
        
        self._selected_thumb_names: list = []
        
        # 从选中创建动画
        batch_btn = QHBoxLayout()
        btn_from_sel = QPushButton("🎬 从选中创建动画")
        btn_from_sel.clicked.connect(self._create_anim_from_selected)
        batch_btn.addWidget(btn_from_sel)
        batch_btn.addStretch()
        layout.addLayout(batch_btn)
        
        # 动画列表
        anim_header = QHBoxLayout()
        anim_header.addWidget(QLabel("动画列表:"))
        btn_add_anim = QPushButton("+")
        btn_add_anim.setFixedWidth(30)
        btn_add_anim.clicked.connect(self._add_animation)
        btn_del_anim = QPushButton("-")
        btn_del_anim.setFixedWidth(30)
        btn_del_anim.clicked.connect(self._delete_animation)
        anim_header.addWidget(btn_add_anim)
        anim_header.addWidget(btn_del_anim)
        layout.addLayout(anim_header)
        
        self.animation_list = QListWidget()
        self.animation_list.currentTextChanged.connect(self._on_animation_selected)
        layout.addWidget(self.animation_list)
        
        # 动画属性
        form = QFormLayout()
        self.anim_name_edit = QLineEdit()
        self.anim_name_edit.textChanged.connect(self._on_animation_changed)
        form.addRow("名称:", self.anim_name_edit)
        self.anim_fps_spin = QSpinBox()
        self.anim_fps_spin.setRange(1, 60)
        self.anim_fps_spin.setValue(8)
        self.anim_fps_spin.valueChanged.connect(self._on_animation_changed)
        form.addRow("FPS:", self.anim_fps_spin)
        self.anim_loop_cb = QCheckBox("循环")
        self.anim_loop_cb.setChecked(True)
        self.anim_loop_cb.toggled.connect(self._on_animation_changed)
        form.addRow("", self.anim_loop_cb)
        layout.addLayout(form)
        
        # 帧列表
        layout.addWidget(QLabel("帧:"))
        self.frame_list = QListWidget()
        self.frame_list.setMaximumHeight(80)
        self.frame_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.frame_list.setDefaultDropAction(Qt.MoveAction)
        self.frame_list.model().rowsMoved.connect(self._on_frame_list_reordered)
        self.frame_list.currentRowChanged.connect(self._on_frame_selected)
        layout.addWidget(self.frame_list)
        
        frame_btn = QHBoxLayout()
        btn_add_frame = QPushButton("+ 帧")
        btn_add_frame.clicked.connect(self._add_frame)
        btn_del_frame = QPushButton("- 帧")
        btn_del_frame.clicked.connect(self._delete_frame)
        frame_btn.addWidget(btn_add_frame)
        frame_btn.addWidget(btn_del_frame)
        layout.addLayout(frame_btn)
        
        # 帧预览条
        self.frame_strip_area = QScrollArea()
        self.frame_strip_area.setFixedHeight(70)
        self.frame_strip_area.setWidgetResizable(True)
        self.frame_strip_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.frame_strip_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frame_strip_container = QWidget()
        self.frame_strip_layout = QHBoxLayout(self.frame_strip_container)
        self.frame_strip_layout.setContentsMargins(2, 2, 2, 2)
        self.frame_strip_layout.setSpacing(4)
        self.frame_strip_layout.addStretch()
        self.frame_strip_area.setWidget(self.frame_strip_container)
        layout.addWidget(self.frame_strip_area)
        
        return widget
    
    # ── 步骤④ 绑定 ──
    def _create_step_bind(self) -> QWidget:
        """步骤④：行为绑定 + 射击/子机"""
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        
        # 行为绑定
        bind_group = QGroupBox("行为 → 动画绑定")
        bind_layout = QFormLayout(bind_group)
        
        self._behavior_combos: Dict[str, QComboBox] = {}
        behaviors = [
            ("idle", "待机"),
            ("move_left", "左移(加速)"),
            ("move_left_full", "左移(全速)"),
            ("move_right", "右移(加速)"),
            ("move_right_full", "右移(全速)"),
            ("focus", "低速"),
            ("death", "死亡"),
        ]
        for key, label in behaviors:
            combo = QComboBox()
            combo.addItem("(无)", "")
            combo.currentIndexChanged.connect(lambda idx, k=key: self._on_behavior_bound(k))
            bind_layout.addRow(f"{label}:", combo)
            self._behavior_combos[key] = combo
        
        # 完全倾斜阈值（两阶段动画：加速→全速）
        tilt_row = QHBoxLayout()
        tilt_row.addWidget(QLabel("完全倾斜帧数:"))
        self._full_tilt_spin = QSpinBox()
        self._full_tilt_spin.setRange(1, 60)
        self._full_tilt_spin.setValue(8)
        self._full_tilt_spin.setToolTip("持续移动多少帧后切换到 move_left_full/move_right_full 动画")
        self._full_tilt_spin.valueChanged.connect(self._on_full_tilt_changed)
        tilt_row.addWidget(self._full_tilt_spin)
        tilt_row.addWidget(QLabel("(静止→加速→全速)"))
        tilt_row.addStretch()
        bind_layout.addRow("", tilt_row)
        
        layout.addWidget(bind_group)
        
        # 射击
        shot_group = QGroupBox("射击类型")
        shot_layout = QVBoxLayout(shot_group)
        shot_btn = QHBoxLayout()
        btn_add_shot = QPushButton("+ 添加")
        btn_add_shot.clicked.connect(self._add_shot_type)
        btn_del_shot = QPushButton("删除")
        btn_del_shot.clicked.connect(self._delete_shot_type)
        shot_btn.addWidget(btn_add_shot)
        shot_btn.addWidget(btn_del_shot)
        shot_layout.addLayout(shot_btn)
        
        self.shot_list = QListWidget()
        self.shot_list.currentTextChanged.connect(self._on_shot_selected)
        shot_layout.addWidget(self.shot_list)
        
        self.shot_editor = ShotTypeEditor()
        self.shot_editor.shot_changed.connect(self._on_shot_changed)
        shot_layout.addWidget(self.shot_editor)
        layout.addWidget(shot_group)
        
        # 子机
        opt_group = QGroupBox("子机")
        opt_layout = QVBoxLayout(opt_group)
        opt_btn = QHBoxLayout()
        btn_add_opt = QPushButton("+ 添加")
        btn_add_opt.clicked.connect(self._add_option)
        btn_del_opt = QPushButton("删除")
        btn_del_opt.clicked.connect(self._delete_option)
        opt_btn.addWidget(btn_add_opt)
        opt_btn.addWidget(btn_del_opt)
        opt_layout.addLayout(opt_btn)
        
        self.option_list = QListWidget()
        self.option_list.currentRowChanged.connect(self._on_option_selected)
        opt_layout.addWidget(self.option_list)
        
        self.option_editor = OptionEditor()
        self.option_editor.option_changed.connect(self._on_option_changed)
        opt_layout.addWidget(self.option_editor)
        layout.addWidget(opt_group)
        
        layout.addStretch()
        scroll.setWidget(inner)
        
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return widget
    
    def _setup_menu(self):
        """设置菜单"""
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件(&F)")
        
        new_action = QAction("新建角色", self)
        new_action.triggered.connect(self._new_player)
        file_menu.addAction(new_action)
        
        open_action = QAction("打开...", self)
        open_action.triggered.connect(self._open_config)
        file_menu.addAction(open_action)
        
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.Save)
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
        """)
    
    # ==================== 事件处理 ====================
    
    def _scan_players(self):
        """扫描可用玩家"""
        self.player_list.clear()

        if PLAYERS_ROOT.exists():
            for folder in sorted(PLAYERS_ROOT.iterdir(), key=lambda p: p.name.lower()):
                if not folder.is_dir():
                    continue
                config_file = folder / "config.json"
                has_config = config_file.exists()
                label = folder.name if has_config else f"{folder.name} (未配置)"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, folder.name)
                item.setData(Qt.UserRole + 1, has_config)
                self.player_list.addItem(item)

    def _on_player_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        """玩家选中"""
        if not current:
            return

        self._commit_sprite_edits()

        player_id = current.data(Qt.UserRole)
        if not player_id:
            return

        config_path = PLAYERS_ROOT / player_id / "config.json"
        if not config_path.exists():
            self._create_default_config_for_folder(PLAYERS_ROOT / player_id)

        if config_path.exists():
            self._load_config(str(config_path))

    def _find_texture_candidates(self, folder: Path) -> List[Path]:
        """查找角色目录内的纹理文件"""
        if not folder.exists():
            return []
        patterns = ["*.png", "*.jpg", "*.jpeg"]
        results: List[Path] = []
        for pat in patterns:
            results.extend(sorted(folder.glob(pat)))
        return results

    def _create_default_config_for_folder(self, folder: Path):
        """为未配置的角色目录创建默认 config.json"""
        folder.mkdir(parents=True, exist_ok=True)
        config_path = folder / "config.json"
        if config_path.exists():
            return
        texture_name = ""
        candidates = self._find_texture_candidates(folder)
        if len(candidates) == 1:
            texture_name = candidates[0].name
        elif len(candidates) > 1:
            names = [p.name for p in candidates]
            from PyQt5.QtWidgets import QInputDialog
            choice, ok = QInputDialog.getItem(
                self, "选择纹理", "检测到多个纹理文件，选择一个：", names, 0, False
            )
            if ok:
                texture_name = choice

        config = {
            "version": "2.0",
            "name": folder.name,
            "description": "",
            "author": "",
            "texture": texture_name,
            "render_size_px": 32,
            "render_downsample": False,
            "stats": {
                "speed_high": 0.02,
                "speed_low": 0.008,
                "hitbox_radius": 3,
                "graze_radius": 24,
                "hitbox_offset_x": 0.0,
                "hitbox_offset_y": 0.0
            },
            "initial": {"lives": 3, "bombs": 3, "power": 1.0},
            "sprites": {},
            "animations": {"transition_speed": 8.0, "animations": {}},
            "shot_types": {},
            "options": []
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        if texture_name:
            self._ensure_player_sheet_config(folder, texture_name)
        self._scan_players()

    def _ensure_player_sheet_config(self, folder: Path, texture_name: str):
        """为纹理生成最小的精灵表 JSON，供纹理管理器识别"""
        if not texture_name:
            return
        sheet_name = Path(texture_name).stem
        sheet_path = folder / f"{sheet_name}.json"
        if sheet_path.exists():
            return
        data = {
            "__image_filename": texture_name,
            "sprites": {}
        }
        with open(sheet_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _collect_bullet_sprite_refs(self, data: dict) -> set:
        """从 shot_types/options/animations 收集子弹精灵引用（用于推断 source）"""
        refs = set()
        # 从 shot_types 递归收集 "sprite" 字段
        for st in (data.get('shot_types') or {}).values():
            if isinstance(st, dict):
                self._collect_sprite_refs_rec(st, refs)
        # 从 options 收集
        for opt in (data.get('options') or []):
            if isinstance(opt, dict):
                self._collect_sprite_refs_rec(opt, refs)
        # 从 animations 中非核心动画收集（bullet/coplane 等子弹动画的帧）
        core_anims = {'idle', 'move_left', 'move_right', 'move_left_full', 'move_right_full',
                      'stand', 'left', 'right', 'right_light', 'focus', 'death', 'spawn', 'option'}
        anims = (data.get('animations') or {})
        anim_data = anims.get('animations', anims) if isinstance(anims.get('animations'), dict) else anims
        for anim_name, anim_def in (anim_data or {}).items():
            if anim_name in core_anims or not isinstance(anim_def, dict):
                continue
            for f in anim_def.get('frames', []):
                if isinstance(f, str):
                    refs.add(f)
        return refs

    def _collect_sprite_refs_rec(self, obj, refs: set):
        """递归收集 dict 中所有 "sprite" 键的字符串值"""
        if isinstance(obj, dict):
            if 'sprite' in obj and isinstance(obj['sprite'], str):
                refs.add(obj['sprite'])
            for v in obj.values():
                self._collect_sprite_refs_rec(v, refs)
        elif isinstance(obj, list):
            for v in obj:
                self._collect_sprite_refs_rec(v, refs)

    def _load_config(self, path: str):
        """加载配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 加载后重置纹理视图为自机
            self._viewing_bullet_tex = False
            
            # 基本信息
            self.player_data.name = data.get('name', '')
            self.player_data.description = data.get('description', '')
            self.player_data.author = data.get('author', '')
            self.player_data.texture = data.get('texture', '')
            # 支持新的 textures:{player, bullet} 格式
            if 'textures' in data:
                tex_map = data['textures']
                self.player_data.texture = tex_map.get('player', self.player_data.texture)
                self.player_data.bullet_texture = tex_map.get('bullet', '')
            else:
                self.player_data.bullet_texture = ''
            self.player_data.render_size_px = int(data.get('render_size_px', 32))
            self.player_data.render_downsample = bool(data.get('render_downsample', False))
            
            # 属性
            stats = data.get('stats', {})
            self.player_data.speed_high = stats.get('speed_high', 0.02)
            self.player_data.speed_low = stats.get('speed_low', 0.008)
            self.player_data.hitbox_radius = stats.get('hitbox_radius', 3)
            self.player_data.graze_radius = stats.get('graze_radius', 24)
            self.player_data.hitbox_offset_x = stats.get('hitbox_offset_x', 0.0)
            self.player_data.hitbox_offset_y = stats.get('hitbox_offset_y', 0.0)
            
            # 初始值
            initial = data.get('initial', {})
            self.player_data.lives = initial.get('lives', 3)
            self.player_data.bombs = initial.get('bombs', 3)
            self.player_data.power = initial.get('power', 1.0)
            
            # 精灵（根据 source 或 shot_types 推断归属）
            self.player_data.sprites.clear()
            bullet_sprite_names = self._collect_bullet_sprite_refs(data)
            has_bullet_tex = bool(data.get('bullet_texture') or
                                  (data.get('textures') or {}).get('bullet'))
            for name, sprite_data in data.get('sprites', {}).items():
                rect = tuple(sprite_data.get('rect', [0, 0, 64, 64]))
                src = sprite_data.get('source')
                if src is None and has_bullet_tex and name in bullet_sprite_names:
                    src = 'bullet'
                elif src is None:
                    src = 'player'
                self.player_data.sprites[name] = SpriteData(name=name, rect=rect, source=src)
            
            # 动画
            self.player_data.animations.clear()
            anim_config = data.get('animations', {})
            self.player_data.animation_transition_speed = anim_config.get('transition_speed', 8.0)
            self.player_data.full_tilt_frames = anim_config.get('full_tilt_frames', 8)
            for name, anim_data in anim_config.get('animations', anim_config).items():
                if not isinstance(anim_data, dict):
                    continue
                # 支持 fps 或 frame_duration（游戏帧/动画帧）
                fps_val = anim_data.get('fps', 8)
                if 'frame_duration' in anim_data:
                    fd = anim_data['frame_duration']
                    fps_val = max(1, int(60 / fd)) if fd > 0 else 8
                self.player_data.animations[name] = AnimationData(
                    name=name,
                    frames=anim_data.get('frames', []),
                    fps=fps_val,
                    loop=anim_data.get('loop', True)
                )
            
            # 更新UI
            self._update_ui()
            
            # 加载纹理
            config_dir = Path(path).parent
            if self.player_data.texture:
                tex_path = config_dir / self.player_data.texture
                if tex_path.exists():
                    self.texture_path = str(tex_path)
                    self.texture_pixmap = QPixmap(str(tex_path))
                    self.sprite_view.load_texture(str(tex_path))
                    self.anim_preview.set_texture(self.texture_pixmap)
                    self.anim_preview.set_sprites(self.player_data.sprites)
                    self.anim_preview.set_bullet_texture(self.bullet_texture_pixmap)
            else:
                # 没有指定纹理时，自动选择目录内第一个图片
                candidates = self._find_texture_candidates(config_dir)
                if candidates:
                    tex_path = candidates[0]
                    self.player_data.texture = tex_path.name
                    self.texture_label.setText(self.player_data.texture)
                    self.texture_path = str(tex_path)
                    self.texture_pixmap = QPixmap(str(tex_path))
                    self.sprite_view.load_texture(str(tex_path))
                    self.anim_preview.set_texture(self.texture_pixmap)
                    self.anim_preview.set_sprites(self.player_data.sprites)
                    self.anim_preview.set_bullet_texture(self.bullet_texture_pixmap)
                else:
                    self.texture_path = None
                    self.texture_pixmap = None
            
            if hasattr(self, '_tex_switch_combo'):
                self._tex_switch_combo.blockSignals(True)
                self._tex_switch_combo.setCurrentIndex(0)
                self._tex_switch_combo.blockSignals(False)
            # load_texture 会 scene.clear() 导致精灵矩形和判定点标记丢失，需重建
            self._refresh_sprite_rects()
            self._refresh_hitbox_marker()
            
            # 子弹纹理
            self.bullet_texture_label.setText(self.player_data.bullet_texture)
            if not self.player_data.bullet_texture:
                self.bullet_texture_path = None
                self.bullet_texture_pixmap = None
                self.anim_preview.set_bullet_texture(None)
            elif self.player_data.bullet_texture:
                btex_path = config_dir / self.player_data.bullet_texture
                if btex_path.exists():
                    self.bullet_texture_path = str(btex_path)
                    self.bullet_texture_pixmap = QPixmap(str(btex_path))
                    self.anim_preview.set_bullet_texture(self.bullet_texture_pixmap)
            
            # 更新步骤①预览缩略图
            if hasattr(self, '_tex_preview_label') and self.texture_pixmap:
                preview = self.texture_pixmap.scaled(
                    300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._tex_preview_label.setPixmap(preview)
            if hasattr(self, '_tex_info_label') and self.texture_pixmap:
                self._tex_info_label.setText(
                    f"尺寸: {self.texture_pixmap.width()} × {self.texture_pixmap.height()} px")
            
            self.statusBar().showMessage(f"已加载: {path}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载失败:\n{e}")
    
    def _update_ui(self):
        """更新UI"""
        # 基本信息
        self.name_edit.setText(self.player_data.name)
        self.desc_edit.setText(self.player_data.description)
        self.author_edit.setText(self.player_data.author)
        self.texture_label.setText(self.player_data.texture)
        
        # 在设置 spinbox 值时，抑制 _on_stats_changed 回调
        # 否则前面的 setValue 会读取后面 spinbox 尚未更新的旧值，覆盖 player_data
        self._suppress_hitbox_change = True
        try:
            # 属性
            self.speed_high_spin.setValue(self.player_data.speed_high)
            self.speed_low_spin.setValue(self.player_data.speed_low)
            self.hitbox_spin.setValue(self.player_data.hitbox_radius)
            self.graze_spin.setValue(self.player_data.graze_radius)
            self.hitbox_offset_x_spin.setValue(self.player_data.hitbox_offset_x)
            self.hitbox_offset_y_spin.setValue(self.player_data.hitbox_offset_y)

            self.render_size_spin.setValue(self.player_data.render_size_px)
            self.render_downsample_cb.setChecked(self.player_data.render_downsample)
            
            # 初始值
            self.lives_spin.setValue(self.player_data.lives)
            self.bombs_spin.setValue(self.player_data.bombs)
            self.power_spin.setValue(self.player_data.power)
        finally:
            self._suppress_hitbox_change = False
        
        # 精灵列表（按当前纹理过滤）
        self._refresh_sprite_list_for_view()

        self._current_sprite_key = None
        
        # 动画列表
        self.animation_list.clear()
        for name in self.player_data.animations:
            self.animation_list.addItem(name)
        
        # 状态机
        self.state_machine_view.set_states(self.player_data.animations)
        
        # 完全倾斜帧数
        if hasattr(self, '_full_tilt_spin'):
            self._full_tilt_spin.setValue(self.player_data.full_tilt_frames)
        
        # 更新精灵显示
        self._refresh_sprite_rects()
        self._refresh_hitbox_marker()
    
    def _refresh_sprite_list_for_view(self):
        """按当前纹理选项刷新精灵列表，只显示对应 source 的精灵"""
        view_source = 'bullet' if self._viewing_bullet_tex else 'player'
        self.sprite_list.clear()
        for name, sprite in self.player_data.sprites.items():
            if getattr(sprite, 'source', 'player') == view_source:
                self.sprite_list.addItem(name)

    def _refresh_sprite_rects(self):
        """刷新精灵矩形显示"""
        self.sprite_view.clear_rects()
        
        # 根据当前查看的纹理过滤精灵框
        view_source = 'bullet' if self._viewing_bullet_tex else 'player'
        
        selected = self.sprite_list.currentItem()
        selected_name = selected.text() if selected else None
        
        for name, sprite in self.player_data.sprites.items():
            if getattr(sprite, 'source', 'player') != view_source:
                continue
            anim_sel = hasattr(self, '_selected_thumb_names') and name in self._selected_thumb_names
            self.sprite_view.add_sprite_rect(
                name, sprite.rect,
                selected=(name == selected_name),
                for_anim=anim_sel)

        self.anim_preview.set_sprites(self.player_data.sprites)
    
    def _on_info_changed(self):
        """信息变化"""
        self.player_data.name = self.name_edit.text()
        self.player_data.description = self.desc_edit.text()
        self.player_data.author = self.author_edit.text()
    
    def _on_stats_changed(self):
        """属性变化"""
        if self._suppress_hitbox_change:
            return
        self.player_data.speed_high = self.speed_high_spin.value()
        self.player_data.speed_low = self.speed_low_spin.value()
        self.player_data.hitbox_radius = self.hitbox_spin.value()
        self.player_data.graze_radius = self.graze_spin.value()
        self.player_data.hitbox_offset_x = self.hitbox_offset_x_spin.value()
        self.player_data.hitbox_offset_y = self.hitbox_offset_y_spin.value()
        self.player_data.lives = self.lives_spin.value()
        self.player_data.bombs = self.bombs_spin.value()
        self.player_data.power = self.power_spin.value()
        self.player_data.render_size_px = self.render_size_spin.value()
        self.player_data.render_downsample = self.render_downsample_cb.isChecked()
        self._refresh_hitbox_marker()
    
    def _choose_texture(self):
        """选择纹理"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择纹理",
            str(PLAYERS_ROOT),
            "图片 (*.png *.jpg)"
        )
        if path:
            self.texture_path = path
            self.player_data.texture = Path(path).name
            self.texture_label.setText(self.player_data.texture)
            
            self.texture_pixmap = QPixmap(path)
            self.sprite_view.load_texture(path)
            self.anim_preview.set_texture(self.texture_pixmap)
            self.anim_preview.set_sprites(self.player_data.sprites)
            
            # 更新纹理信息和预览
            if hasattr(self, '_tex_info_label'):
                self._tex_info_label.setText(
                    f"尺寸: {self.texture_pixmap.width()} × {self.texture_pixmap.height()} px")
            if hasattr(self, '_tex_preview_label'):
                preview = self.texture_pixmap.scaled(
                    300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._tex_preview_label.setPixmap(preview)
    
    def _choose_bullet_texture(self):
        """选择子弹纹理"""
        start_dir = str(PLAYERS_ROOT)
        if self.texture_path:
            start_dir = str(Path(self.texture_path).parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "选择子弹纹理",
            start_dir,
            "图片 (*.png *.jpg)"
        )
        if path:
            self.player_data.bullet_texture = Path(path).name
            self.bullet_texture_label.setText(self.player_data.bullet_texture)
            self.bullet_texture_path = path
            self.bullet_texture_pixmap = QPixmap(path)
            self.anim_preview.set_bullet_texture(self.bullet_texture_pixmap)
            self.statusBar().showMessage(f"子弹纹理: {Path(path).name}")
    
    def _on_tex_switch(self, idx: int):
        """切换预览区显示的纹理"""
        kind = self._tex_switch_combo.currentData()
        if kind == "bullet":
            if self.bullet_texture_path and self.bullet_texture_pixmap:
                self.sprite_view.load_texture(self.bullet_texture_path)
                self._viewing_bullet_tex = True
                self._refresh_sprite_list_for_view()
                self._refresh_sprite_rects()
                self._refresh_hitbox_marker()
                self.statusBar().showMessage("预览: 子弹纹理")
            else:
                self.statusBar().showMessage("请先在步骤①选择子弹纹理")
        else:
            if self.texture_path:
                self.sprite_view.load_texture(self.texture_path)
                self._viewing_bullet_tex = False
                self._refresh_sprite_list_for_view()
                self._refresh_sprite_rects()
                self._refresh_hitbox_marker()
                self.statusBar().showMessage("预览: 自机纹理")
    
    # 精灵操作
    def _add_sprite(self):
        idx = len(self.player_data.sprites)
        name = f"sprite_{idx}"
        src = 'bullet' if self._viewing_bullet_tex else 'player'
        self.player_data.sprites[name] = SpriteData(name=name, rect=(0, 0, 64, 64), source=src)
        self.sprite_list.addItem(name)
        self._refresh_sprite_rects()
    
    def _open_grid_split_dialog(self):
        """打开网格切割对话框，批量生成精灵"""
        dialog = QDialog(self)
        dialog.setWindowTitle("网格切割 — 批量生成精灵")
        dlg_layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        rows_spin = QSpinBox()
        rows_spin.setRange(1, 200)
        rows_spin.setValue(1)
        cols_spin = QSpinBox()
        cols_spin.setRange(1, 200)
        cols_spin.setValue(1)
        
        start_x = QSpinBox()
        start_x.setRange(0, 99999)
        start_y = QSpinBox()
        start_y.setRange(0, 99999)
        
        cell_w = QSpinBox()
        cell_w.setRange(1, 99999)
        cell_w.setValue(64)
        cell_h = QSpinBox()
        cell_h.setRange(1, 99999)
        cell_h.setValue(64)
        
        # 如果已有纹理，用纹理尺寸做默认值参考
        if self.texture_pixmap and not self.texture_pixmap.isNull():
            tw, th = self.texture_pixmap.width(), self.texture_pixmap.height()
            cell_w.setValue(min(tw, 64))
            cell_h.setValue(min(th, 64))
        
        gap_x = QSpinBox()
        gap_x.setRange(0, 99999)
        gap_y = QSpinBox()
        gap_y.setRange(0, 99999)
        
        prefix_edit = QLineEdit("sprite")
        
        form.addRow("行数:", rows_spin)
        form.addRow("列数:", cols_spin)
        form.addRow("起点 X:", start_x)
        form.addRow("起点 Y:", start_y)
        form.addRow("单元宽:", cell_w)
        form.addRow("单元高:", cell_h)
        form.addRow("间隔 X:", gap_x)
        form.addRow("间隔 Y:", gap_y)
        form.addRow("名称前缀:", prefix_edit)
        
        dlg_layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)
        
        if dialog.exec_() == QDialog.Accepted:
            self._create_grid_sprites(
                rows_spin.value(), cols_spin.value(),
                start_x.value(), start_y.value(),
                cell_w.value(), cell_h.value(),
                gap_x.value(), gap_y.value(),
                prefix_edit.text().strip() or "sprite"
            )
    
    def _create_grid_sprites(self, rows, cols, sx, sy, cw, ch, gx, gy, prefix):
        """按网格生成精灵"""
        idx = 0
        for r in range(rows):
            for c in range(cols):
                x = sx + c * (cw + gx)
                y = sy + r * (ch + gy)
                name = f"{prefix}_{idx}"
                while name in self.player_data.sprites:
                    idx += 1
                    name = f"{prefix}_{idx}"
                src = 'bullet' if self._viewing_bullet_tex else 'player'
                self.player_data.sprites[name] = SpriteData(name=name, rect=(x, y, cw, ch), source=src)
                self.sprite_list.addItem(name)
                idx += 1
        self._refresh_sprite_rects()
        self.statusBar().showMessage(f"已生成 {rows * cols} 个精灵")
    
    def _region_auto_detect(self, rx: int, ry: int, rw: int, rh: int):
        """对拖选区域进行自动检测精灵"""
        # 使用当前预览的纹理
        tex_path = self.bullet_texture_path if self._viewing_bullet_tex else self.texture_path
        if not tex_path or not os.path.isfile(tex_path):
            QMessageBox.warning(self, "警告", "请先选择纹理文件")
            return
        
        try:
            import cv2
            import numpy as np
        except ImportError:
            QMessageBox.warning(
                self, "缺少依赖",
                "区域检测需要 OpenCV。\n请安装: pip install opencv-python")
            return
        
        img = cv2.imread(tex_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            QMessageBox.warning(self, "错误", "无法读取纹理文件")
            return
        
        ih, iw = img.shape[:2]
        # 坐标钳位到图像范围
        rx = max(0, min(rx, iw - 1))
        ry = max(0, min(ry, ih - 1))
        rw = min(rw, iw - rx)
        rh = min(rh, ih - ry)
        if rw < 2 or rh < 2:
            self.statusBar().showMessage("选区太小")
            return
        
        region = img[ry:ry + rh, rx:rx + rw]
        
        # 生成检测mask：优先Alpha通道，否则用灰度
        if len(img.shape) >= 3 and img.shape[2] >= 4:
            alpha = region[:, :, 3]
            _, mask = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)
        else:
            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if len(region.shape) == 3 else region
            # 用背景色判断：取四角平均作为背景
            corners = [gray[0, 0], gray[0, -1], gray[-1, 0], gray[-1, -1]]
            bg = int(np.mean(corners))
            diff = cv2.absdiff(gray, np.full_like(gray, bg))
            _, mask = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
        
        # 形态学膨胀，合并紧邻像素
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.dilate(mask, kernel, iterations=2)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        bboxes = []
        for cnt in contours:
            bx, by, bw, bh = cv2.boundingRect(cnt)
            if bw >= 4 and bh >= 4:
                bboxes.append((bx + rx, by + ry, bw, bh))
        
        if not bboxes:
            self.statusBar().showMessage(
                f"选区({rx},{ry},{rw}×{rh})内未检测到精灵 "
                f"[contours={len(contours)}]")
            return
        
        bboxes.sort(key=lambda b: (b[1], b[0]))
        
        # 按Y邻近度分行
        rows_of_bb = [[bboxes[0]]]
        for bb in bboxes[1:]:
            ref_y = sum(b[1] for b in rows_of_bb[-1]) / len(rows_of_bb[-1])
            ref_h = sum(b[3] for b in rows_of_bb[-1]) / len(rows_of_bb[-1])
            if abs(bb[1] - ref_y) < max(ref_h * 0.5, 8):
                rows_of_bb[-1].append(bb)
            else:
                rows_of_bb.append([bb])
        
        # 每个contour直接作为一个精灵
        idx = len(self.player_data.sprites)
        count = 0
        for row_bbs in rows_of_bb:
            row_bbs.sort(key=lambda b: b[0])
            for bx, by, bw, bh in row_bbs:
                name = f"auto_{idx}"
                while name in self.player_data.sprites:
                    idx += 1
                    name = f"auto_{idx}"
                src = 'bullet' if self._viewing_bullet_tex else 'player'
                self.player_data.sprites[name] = SpriteData(name=name, rect=(bx, by, bw, bh), source=src)
                self.sprite_list.addItem(name)
                idx += 1
                count += 1
        
        self._refresh_sprite_rects()
        self.statusBar().showMessage(f"选区内检测到 {count} 个精灵")
    
    def _update_frame_strip(self):
        """更新动画帧预览条（按精灵 source 使用对应纹理）"""
        # 清除旧缩略图
        while self.frame_strip_layout.count() > 0:
            item = self.frame_strip_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        
        anim_item = self.animation_list.currentItem()
        if not anim_item:
            return
        name = anim_item.text()
        anim = self.player_data.animations.get(name)
        if not anim:
            return
        
        for frame_name in anim.frames:
            sprite = self.player_data.sprites.get(frame_name)
            if not sprite:
                # 占位
                lbl = QLabel("?")
                lbl.setFixedSize(60, 60)
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("background:#333; border:1px solid #555; color:#999;")
                lbl.setToolTip(f"{frame_name} (未找到)")
                self.frame_strip_layout.addWidget(lbl)
                continue
            
            tex = self._get_tex_for_sprite(sprite)
            if not tex or tex.isNull():
                lbl = QLabel("?")
                lbl.setFixedSize(60, 60)
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("background:#333; border:1px solid #555; color:#999;")
                lbl.setToolTip(f"{frame_name} (纹理缺失)")
                self.frame_strip_layout.addWidget(lbl)
                continue
            
            x, y, w, h = sprite.rect
            cropped = tex.copy(x, y, w, h)
            scaled = cropped.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl = QLabel()
            lbl.setPixmap(scaled)
            lbl.setFixedSize(60, 60)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("background:#222; border:1px solid #555;")
            lbl.setToolTip(frame_name)
            self.frame_strip_layout.addWidget(lbl)
        
        self.frame_strip_layout.addStretch()
    
    def _get_tex_for_sprite(self, sprite: SpriteData):
        """根据精灵 source 返回对应纹理"""
        if getattr(sprite, 'source', 'player') == 'bullet':
            return self.bullet_texture_pixmap if self.bullet_texture_pixmap and not self.bullet_texture_pixmap.isNull() else self.texture_pixmap
        return self.texture_pixmap
    
    def _refresh_sprite_thumb_grid(self):
        """刷新步骤③的精灵缩略图网格（按当前纹理选项过滤）"""
        # 清除旧缩略图
        while self._sprite_thumb_flow.count() > 0:
            item = self._sprite_thumb_flow.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        
        self._selected_thumb_names.clear()
        
        view_source = 'bullet' if self._viewing_bullet_tex else 'player'
        tex = self.bullet_texture_pixmap if self._viewing_bullet_tex else self.texture_pixmap
        if not tex or tex.isNull():
            return
        
        for name, sprite in self.player_data.sprites.items():
            if getattr(sprite, 'source', 'player') != view_source:
                continue
            x, y, w, h = sprite.rect
            cropped = tex.copy(x, y, w, h)
            scaled = cropped.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            btn = QPushButton()
            btn.setIcon(QIcon(scaled))
            btn.setIconSize(scaled.size())
            btn.setFixedSize(60, 60)
            btn.setCheckable(True)
            btn.setToolTip(name)
            btn.setStyleSheet("""
                QPushButton { background:#222; border:1px solid #555; }
                QPushButton:checked { border:2px solid #4a90d9; background:#2a3a5a; }
            """)
            btn.toggled.connect(lambda checked, n=name: self._on_thumb_toggled(n, checked))
            self._sprite_thumb_flow.addWidget(btn)
        
        self._sprite_thumb_flow.addStretch()
    
    def _on_thumb_toggled(self, name: str, checked: bool):
        """缩略图选中/取消"""
        if checked:
            if name not in self._selected_thumb_names:
                self._selected_thumb_names.append(name)
        else:
            if name in self._selected_thumb_names:
                self._selected_thumb_names.remove(name)
    
    def _on_preview_sprite_clicked(self, name: str):
        """预览区左键点击精灵 → 切换动画选中状态"""
        if name in self._selected_thumb_names:
            self._selected_thumb_names.remove(name)
        else:
            self._selected_thumb_names.append(name)
        
        # 同步缩略图按钮的checked状态（如果在步骤③）
        for i in range(self._sprite_thumb_flow.count()):
            item = self._sprite_thumb_flow.itemAt(i)
            btn = item.widget() if item else None
            if btn and hasattr(btn, 'toolTip') and btn.toolTip() == name:
                btn.blockSignals(True)
                btn.setChecked(name in self._selected_thumb_names)
                btn.blockSignals(False)
                break
        
        # 高亮选中的精灵矩形
        self._refresh_sprite_rects()
        
        sel = len(self._selected_thumb_names)
        self.statusBar().showMessage(
            f"{'选中' if name in self._selected_thumb_names else '取消'} {name}  "
            f"(已选 {sel} 个精灵)")
    
    def _create_anim_from_selected(self):
        """从选中的精灵缩略图批量创建动画"""
        if not self._selected_thumb_names:
            self.statusBar().showMessage("请先在上方点选精灵缩略图")
            return
        
        # 生成动画名
        idx = len(self.player_data.animations)
        anim_name = f"anim_{idx}"
        while anim_name in self.player_data.animations:
            idx += 1
            anim_name = f"anim_{idx}"
        
        anim = AnimationData(
            name=anim_name,
            frames=list(self._selected_thumb_names),
            fps=8,
            loop=True
        )
        self.player_data.animations[anim_name] = anim
        self.animation_list.addItem(anim_name)
        self.animation_list.setCurrentRow(self.animation_list.count() - 1)
        self.statusBar().showMessage(f"已创建动画 '{anim_name}' ({len(anim.frames)} 帧)")
        self._update_frame_strip()
    
    def _refresh_behavior_combos(self):
        """刷新步骤④的行为绑定下拉框"""
        anim_names = list(self.player_data.animations.keys())
        
        for key, combo in self._behavior_combos.items():
            combo.blockSignals(True)
            current_data = combo.currentData()
            combo.clear()
            combo.addItem("(无)", "")
            for an in anim_names:
                combo.addItem(an, an)
            # 恢复之前的选择
            if current_data:
                idx = combo.findData(current_data)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            # 检查 player_data.animations 中是否已有此行为名
            if key in self.player_data.animations:
                idx = combo.findData(key)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)
    
    def _on_behavior_bound(self, behavior_key: str):
        """行为绑定变更"""
        combo = self._behavior_combos.get(behavior_key)
        if not combo:
            return
        anim_name = combo.currentData()
        if anim_name and anim_name in self.player_data.animations:
            # 复制动画数据到行为名
            src = self.player_data.animations[anim_name]
            self.player_data.animations[behavior_key] = AnimationData(
                name=behavior_key,
                frames=list(src.frames),
                fps=src.fps,
                loop=src.loop
            )
        self.statusBar().showMessage(f"行为 '{behavior_key}' 已绑定")
    
    def _on_full_tilt_changed(self, value: int):
        """完全倾斜帧数变更"""
        self.player_data.full_tilt_frames = value
    
    def _delete_sprite(self):
        item = self.sprite_list.currentItem()
        if item:
            name = item.text()
            del self.player_data.sprites[name]
            self.sprite_list.takeItem(self.sprite_list.row(item))
            self._refresh_sprite_rects()
    
    def _on_sprite_selected(self, name: str):
        self._commit_sprite_edits()
        if name and name in self.player_data.sprites:
            sprite = self.player_data.sprites[name]
            self._suppress_sprite_change = True
            try:
                self.sprite_name_edit.setText(sprite.name)
                self.sprite_x.setValue(sprite.rect[0])
                self.sprite_y.setValue(sprite.rect[1])
                self.sprite_w.setValue(sprite.rect[2])
                self.sprite_h.setValue(sprite.rect[3])
            finally:
                self._suppress_sprite_change = False
            self._current_sprite_key = name
            self._refresh_sprite_rects()
            self._refresh_hitbox_marker()
        else:
            self._current_sprite_key = None
            self._refresh_hitbox_marker()
    
    def _on_sprite_changed(self):
        if self._suppress_sprite_change:
            return
        item = self.sprite_list.currentItem()
        if item:
            old_name = item.text()
            new_name = self.sprite_name_edit.text()
            
            if old_name in self.player_data.sprites:
                sprite = self.player_data.sprites[old_name]
                sprite.name = new_name
                sprite.rect = (
                    self.sprite_x.value(),
                    self.sprite_y.value(),
                    self.sprite_w.value(),
                    self.sprite_h.value()
                )
                
                if old_name != new_name:
                    del self.player_data.sprites[old_name]
                    self.player_data.sprites[new_name] = sprite
                    item.setText(new_name)

                    # 同步动画帧中引用的精灵名称
                    for anim in self.player_data.animations.values():
                        anim.frames = [new_name if f == old_name else f for f in anim.frames]
                
                self._refresh_sprite_rects()

    def _commit_sprite_edits(self):
        """在切换选择或保存前，提交当前精灵编辑"""
        if not self._current_sprite_key:
            return
        if self._current_sprite_key not in self.player_data.sprites:
            return
        old_name = self._current_sprite_key
        new_name = self.sprite_name_edit.text()

        sprite = self.player_data.sprites[old_name]
        sprite.name = new_name
        sprite.rect = (
            self.sprite_x.value(),
            self.sprite_y.value(),
            self.sprite_w.value(),
            self.sprite_h.value()
        )

        if old_name != new_name:
            del self.player_data.sprites[old_name]
            self.player_data.sprites[new_name] = sprite
            for anim in self.player_data.animations.values():
                anim.frames = [new_name if f == old_name else f for f in anim.frames]
            self._current_sprite_key = new_name

    def _refresh_hitbox_marker(self):
        item = self.sprite_list.currentItem()
        if not item:
            self.sprite_view.set_hitbox(None, 0, 0, 0, visible=False)
            return
        name = item.text()
        sprite = self.player_data.sprites.get(name)
        if not sprite:
            self.sprite_view.set_hitbox(None, 0, 0, 0, visible=False)
            return
        self.sprite_view.set_hitbox(
            sprite.rect,
            self.player_data.hitbox_radius,
            self.player_data.hitbox_offset_x,
            self.player_data.hitbox_offset_y,
            visible=True,
        )

    def _on_hitbox_dragged(self, offset_x: float, offset_y: float):
        self._suppress_hitbox_change = True
        try:
            self.hitbox_offset_x_spin.setValue(offset_x)
            self.hitbox_offset_y_spin.setValue(offset_y)
            self.player_data.hitbox_offset_x = offset_x
            self.player_data.hitbox_offset_y = offset_y
        finally:
            self._suppress_hitbox_change = False
    
    # 动画操作
    def _add_animation(self):
        idx = len(self.player_data.animations)
        name = f"anim_{idx}"
        self.player_data.animations[name] = AnimationData(name=name)
        self.animation_list.addItem(name)
        self.state_machine_view.set_states(self.player_data.animations)
    
    def _delete_animation(self):
        item = self.animation_list.currentItem()
        if item:
            name = item.text()
            del self.player_data.animations[name]
            self.animation_list.takeItem(self.animation_list.row(item))
            self.state_machine_view.set_states(self.player_data.animations)
    
    def _on_animation_selected(self, name: str):
        if name and name in self.player_data.animations:
            anim = self.player_data.animations[name]
            self.anim_name_edit.setText(anim.name)
            self.anim_fps_spin.setValue(anim.fps)
            self.anim_loop_cb.setChecked(anim.loop)
            
            self.frame_list.clear()
            for frame in anim.frames:
                self.frame_list.addItem(frame)
            
            self.anim_preview.set_animation(anim)
            self._update_frame_strip()
    
    def _on_animation_changed(self):
        item = self.animation_list.currentItem()
        if item:
            old_name = item.text()
            new_name = self.anim_name_edit.text()
            
            if old_name in self.player_data.animations:
                anim = self.player_data.animations[old_name]
                anim.name = new_name
                anim.fps = self.anim_fps_spin.value()
                anim.loop = self.anim_loop_cb.isChecked()
                
                if old_name != new_name:
                    del self.player_data.animations[old_name]
                    self.player_data.animations[new_name] = anim
                    item.setText(new_name)
                
                self.anim_preview.set_animation(anim)
    
    def _add_frame(self):
        item = self.animation_list.currentItem()
        if item:
            name = item.text()
            if name in self.player_data.animations:
                # 从精灵列表选择
                sprites = list(self.player_data.sprites.keys())
                if not sprites:
                    QMessageBox.information(self, "提示", "当前没有可用精灵，请先添加精灵。")
                    return
                from PyQt5.QtWidgets import QInputDialog
                frame, ok = QInputDialog.getItem(
                    self, "添加帧", "选择精灵:", sprites, 0, False
                )
                if ok:
                    self.player_data.animations[name].frames.append(frame)
                    self.frame_list.addItem(frame)
                    self.anim_preview.set_animation(self.player_data.animations[name])
                    self._update_frame_strip()

    def _add_frame_from_sprite(self, item: QListWidgetItem):
        anim_item = self.animation_list.currentItem()
        if not anim_item:
            QMessageBox.information(self, "提示", "请先选择一个动画。")
            return
        name = anim_item.text()
        if name not in self.player_data.animations:
            return
        frame_name = item.text()
        self.player_data.animations[name].frames.append(frame_name)
        self.frame_list.addItem(frame_name)
        self.anim_preview.set_animation(self.player_data.animations[name])
        self._update_frame_strip()
    
    def _delete_frame(self):
        item = self.animation_list.currentItem()
        frame_item = self.frame_list.currentItem()
        if item and frame_item:
            name = item.text()
            if name in self.player_data.animations:
                row = self.frame_list.row(frame_item)
                self.player_data.animations[name].frames.pop(row)
                self.frame_list.takeItem(row)
                self.anim_preview.set_animation(self.player_data.animations[name])
                self._update_frame_strip()

    def _on_frame_selected(self, row: int):
        anim_item = self.animation_list.currentItem()
        if not anim_item:
            return
        name = anim_item.text()
        if name not in self.player_data.animations:
            return
        self.anim_preview.set_frame_index(row)

    def _on_frame_list_reordered(self, *args):
        anim_item = self.animation_list.currentItem()
        if not anim_item:
            return
        name = anim_item.text()
        if name not in self.player_data.animations:
            return
        frames = []
        for i in range(self.frame_list.count()):
            frames.append(self.frame_list.item(i).text())
        self.player_data.animations[name].frames = frames
        self.anim_preview.set_animation(self.player_data.animations[name])
        self._update_frame_strip()
    
    # 射击操作
    def _add_shot_type(self):
        idx = len(self.player_data.shot_types)
        name = f"shot_{idx}"
        self.player_data.shot_types[name] = ShotTypeData(name=name)
        self.shot_list.addItem(name)
    
    def _delete_shot_type(self):
        item = self.shot_list.currentItem()
        if item:
            name = item.text()
            del self.player_data.shot_types[name]
            self.shot_list.takeItem(self.shot_list.row(item))
    
    def _on_shot_selected(self, name: str):
        if name and name in self.player_data.shot_types:
            self.shot_editor.set_shot(self.player_data.shot_types[name])
    
    def _on_shot_changed(self):
        pass
    
    # 子机操作
    def _add_option(self):
        idx = len(self.player_data.options)
        option = OptionData(name=f"option_{idx}")
        self.player_data.options.append(option)
        self.option_list.addItem(option.name)
    
    def _delete_option(self):
        row = self.option_list.currentRow()
        if 0 <= row < len(self.player_data.options):
            del self.player_data.options[row]
            self.option_list.takeItem(row)
    
    def _on_option_selected(self, row: int):
        if 0 <= row < len(self.player_data.options):
            self.option_editor.set_option(self.player_data.options[row])
    
    def _on_option_changed(self):
        pass
    
    # 文件操作
    def _new_player(self):
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "新建角色", "角色文件夹名称:")
        if not ok or not name:
            return

        folder = PLAYERS_ROOT / name
        folder.mkdir(parents=True, exist_ok=True)

        tex_path, _ = QFileDialog.getOpenFileName(
            self, "选择角色纹理",
            str(folder),
            "图片 (*.png *.jpg)"
        )

        texture_name = ""
        if tex_path:
            tex_path = Path(tex_path)
            if tex_path.parent != folder:
                target = folder / tex_path.name
                shutil.copy2(str(tex_path), str(target))
                tex_path = target
            texture_name = tex_path.name

        self.player_data = PlayerConfigData()
        self.player_data.name = name
        self.player_data.texture = texture_name

        self.texture_path = str(folder / texture_name) if texture_name else None
        self.texture_label.setText(texture_name)
        self._update_ui()

        if self.texture_path and Path(self.texture_path).exists():
            self.texture_pixmap = QPixmap(self.texture_path)
            self.sprite_view.load_texture(self.texture_path)
            self.anim_preview.set_texture(self.texture_pixmap)

        self._create_default_config_for_folder(folder)
        self._scan_players()
        for i in range(self.player_list.count()):
            item = self.player_list.item(i)
            if item.data(Qt.UserRole) == name:
                self.player_list.setCurrentItem(item)
                break
    
    def _open_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开玩家配置",
            str(PLAYERS_ROOT),
            "JSON文件 (*.json)"
        )
        if path:
            self._load_config(path)
    
    def _save_config(self):
        self._commit_sprite_edits()
        # 确定保存路径
        player_item = self.player_list.currentItem()
        if player_item:
            player_id = player_item.data(Qt.UserRole) or player_item.text()
            save_dir = PLAYERS_ROOT / player_id
        else:
            save_dir = PLAYERS_ROOT / "new_player"
            save_dir.mkdir(exist_ok=True)
        
        path, _ = QFileDialog.getSaveFileName(
            self, "保存玩家配置",
            str(save_dir / "config.json"),
            "JSON文件 (*.json)"
        )
        
        if path:
            # 确保纹理在角色目录内
            if self.texture_path:
                tex_path = Path(self.texture_path)
                if tex_path.exists() and tex_path.parent != Path(path).parent:
                    target = Path(path).parent / tex_path.name
                    shutil.copy2(str(tex_path), str(target))
                    self.player_data.texture = target.name
            config = {
                "version": "2.0",
                "name": self.player_data.name,
                "description": self.player_data.description,
                "author": self.player_data.author,
            }
            # 纹理字段：如果有子弹纹理则用 textures dict，否则沿用旧的 texture string
            if self.player_data.bullet_texture:
                config["textures"] = {
                    "player": self.player_data.texture,
                    "bullet": self.player_data.bullet_texture
                }
            else:
                config["texture"] = self.player_data.texture
            config.update({
                "render_size_px": self.player_data.render_size_px,
                "render_downsample": self.player_data.render_downsample,
                "stats": {
                    "speed_high": self.player_data.speed_high,
                    "speed_low": self.player_data.speed_low,
                    "hitbox_radius": self.player_data.hitbox_radius,
                    "graze_radius": self.player_data.graze_radius,
                    "hitbox_offset_x": self.player_data.hitbox_offset_x,
                    "hitbox_offset_y": self.player_data.hitbox_offset_y
                },
                "initial": {
                    "lives": self.player_data.lives,
                    "bombs": self.player_data.bombs,
                    "power": self.player_data.power
                },
                "sprites": {
                    name: {"rect": list(sprite.rect), "source": getattr(sprite, 'source', 'player')}
                    for name, sprite in self.player_data.sprites.items()
                },
                "animations": {
                    "transition_speed": self.player_data.animation_transition_speed,
                    "full_tilt_frames": self.player_data.full_tilt_frames,
                    "animations": {
                        name: {
                            "frames": anim.frames,
                            "frame_duration": max(1, round(60 / anim.fps)) if anim.fps > 0 else 5,
                            "loop": anim.loop
                        }
                        for name, anim in self.player_data.animations.items()
                    }
                },
                "shot_types": {
                    "unfocused": {
                        "damage": 10,
                        "speed": 0.05,
                        "interval": 4,
                        "spread": 5,
                        "count": 2,
                        "sprite": "player_bullet"
                    }
                },
                "options": [
                    {
                        "offset": [opt.offset_x, opt.offset_y],
                        "shot_type": opt.shot_type,
                        "damage": opt.damage,
                        "interval": opt.interval
                    }
                    for opt in self.player_data.options
                ]
            })
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # 生成供纹理管理器使用的精灵表 JSON
            self._ensure_player_sheet_config(Path(path).parent, self.player_data.texture)
            
            self.statusBar().showMessage(f"已保存: {path}")
            self._scan_players()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = PlayerEditor()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
