#!/usr/bin/env python3
"""
弹幕脚本可视化编辑器

功能:
- 可视化编辑符卡脚本 (SpellCard)
- 实时预览弹幕效果
- 节点式弹幕模式编辑
- 时间轴视图
- 代码生成和导出
- 子弹类型预览（显示实际精灵图）
"""

import sys
import os
import json
import math
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QGroupBox, QFormLayout, QScrollArea, QFrame, QTabWidget,
    QFileDialog, QMessageBox, QToolBar, QAction, QStatusBar, QMenu,
    QDialog, QDialogButtonBox, QPlainTextEdit, QSlider, QGraphicsView,
    QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem,
    QHeaderView, QTableWidget, QTableWidgetItem, QColorDialog, QToolBox
)
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QSize, pyqtSignal, QThread
from PyQt5.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush, QFont, 
    QIcon, QKeySequence, QTransform, QRadialGradient, QPainterPath
)

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ASSETS_ROOT = PROJECT_ROOT / "assets"
GAME_CONTENT_ROOT = PROJECT_ROOT / "game_content"


# ==================== 数据模型 ====================

class BulletType(Enum):
    """子弹类型"""
    BALL_S = "ball_s"
    BALL_M = "ball_m"
    BALL_L = "ball_l"
    RICE = "rice"
    SCALE = "scale"
    ARROWHEAD = "arrowhead"
    STAR = "star"
    NEEDLE = "needle"


class BulletColor(Enum):
    """子弹颜色"""
    RED = "red"
    BLUE = "blue"
    GREEN = "green"
    YELLOW = "yellow"
    PURPLE = "purple"
    WHITE = "white"
    ORANGE = "orange"
    CYAN = "cyan"


# 颜色映射到实际 RGB
COLOR_RGB = {
    "red": (255, 80, 80),
    "blue": (80, 150, 255),
    "green": (80, 255, 80),
    "yellow": (255, 255, 80),
    "purple": (200, 80, 255),
    "white": (255, 255, 255),
    "orange": (255, 160, 80),
    "cyan": (80, 255, 255),
}


@dataclass
class BulletPattern:
    """弹幕模式"""
    name: str = "unnamed"
    pattern_type: str = "circle"  # circle, line, spiral, aimed, random
    count: int = 12
    speed: float = 2.0
    speed_var: float = 0.0
    angle: float = 0.0
    angle_spread: float = 360.0
    bullet_type: str = "ball_m"
    color: str = "red"
    delay: int = 0
    interval: int = 5
    repeat: int = 1
    # 高级参数
    accel: float = 0.0
    angular_velocity: float = 0.0
    aim_player: bool = False


@dataclass
class TimelineEvent:
    """时间轴事件"""
    time: int  # 帧
    event_type: str  # "pattern", "wait", "move", "sound"
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpellCardData:
    """符卡数据"""
    name: str = "新符卡"
    hp: int = 1500
    time_limit: int = 60
    bonus: int = 1000000
    boss_x: float = 0.0
    boss_y: float = 0.5
    events: List[TimelineEvent] = field(default_factory=list)
    patterns: Dict[str, BulletPattern] = field(default_factory=dict)


# ==================== 预览视图 ====================

class DanmakuPreviewView(QGraphicsView):
    """弹幕预览视图"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(20, 20, 40)))
        self.setMinimumSize(400, 500)
        
        # 游戏区域 (归一化坐标 -1 到 1)
        self.game_width = 380
        self.game_height = 450
        self.scale_factor = self.game_width / 2
        
        # 绘制边界
        self._draw_boundary()
        
        # Boss 和 Player 标记
        self.boss_item = None
        self.player_item = None
        self.bullet_items: List[QGraphicsEllipseItem] = []
        
        # 初始化位置
        self.boss_pos = (0.0, 0.5)
        self.player_pos = (0.0, -0.7)
        
        self._create_markers()
        
        # 模拟状态
        self.bullets: List[Dict] = []
        self.simulation_running = False
        self.simulation_frame = 0
        
        # 动画定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_simulation)
    
    def _draw_boundary(self):
        """绘制游戏区域边界"""
        pen = QPen(QColor(100, 100, 150), 2)
        # 游戏区域矩形
        self.scene.addRect(
            -self.game_width/2, -self.game_height/2,
            self.game_width, self.game_height,
            pen
        )
        
        # 网格线
        grid_pen = QPen(QColor(40, 40, 60), 1, Qt.DotLine)
        for i in range(-4, 5):
            x = i * (self.game_width / 8)
            self.scene.addLine(x, -self.game_height/2, x, self.game_height/2, grid_pen)
        for i in range(-5, 6):
            y = i * (self.game_height / 10)
            self.scene.addLine(-self.game_width/2, y, self.game_width/2, y, grid_pen)
    
    def _create_markers(self):
        """创建 Boss 和 Player 标记"""
        # Boss
        boss_pen = QPen(QColor(255, 100, 100), 2)
        boss_brush = QBrush(QColor(255, 100, 100, 100))
        self.boss_item = self.scene.addEllipse(-15, -15, 30, 30, boss_pen, boss_brush)
        self._update_boss_pos()
        
        # Player
        player_pen = QPen(QColor(100, 255, 100), 2)
        player_brush = QBrush(QColor(100, 255, 100, 100))
        self.player_item = self.scene.addEllipse(-10, -10, 20, 20, player_pen, player_brush)
        self._update_player_pos()
    
    def _norm_to_screen(self, x: float, y: float) -> Tuple[float, float]:
        """归一化坐标转屏幕坐标"""
        sx = x * self.scale_factor
        sy = -y * self.scale_factor  # Y轴翻转
        return sx, sy
    
    def _update_boss_pos(self):
        """更新 Boss 位置"""
        sx, sy = self._norm_to_screen(*self.boss_pos)
        self.boss_item.setPos(sx, sy)
    
    def _update_player_pos(self):
        """更新 Player 位置"""
        sx, sy = self._norm_to_screen(*self.player_pos)
        self.player_item.setPos(sx, sy)
    
    def set_boss_pos(self, x: float, y: float):
        """设置 Boss 位置"""
        self.boss_pos = (x, y)
        self._update_boss_pos()
    
    def preview_pattern(self, pattern: BulletPattern):
        """预览单个弹幕模式"""
        self.clear_bullets()
        self.bullets = self._generate_bullets(pattern)
        self._draw_bullets()
    
    def _generate_bullets(self, pattern: BulletPattern) -> List[Dict]:
        """根据模式生成子弹"""
        bullets = []
        
        bx, by = self.boss_pos
        px, py = self.player_pos
        
        # 计算基础角度
        if pattern.aim_player:
            base_angle = math.degrees(math.atan2(py - by, px - bx))
        else:
            base_angle = pattern.angle
        
        if pattern.pattern_type == "circle":
            # 圆形弹幕
            angle_step = pattern.angle_spread / max(1, pattern.count)
            start_angle = base_angle - pattern.angle_spread / 2
            
            for i in range(pattern.count):
                angle = start_angle + i * angle_step
                speed = pattern.speed
                
                bullets.append({
                    'x': bx,
                    'y': by,
                    'vx': speed * math.cos(math.radians(angle)) / 60,
                    'vy': speed * math.sin(math.radians(angle)) / 60,
                    'color': pattern.color,
                    'type': pattern.bullet_type,
                    'alive': True
                })
        
        elif pattern.pattern_type == "line":
            # 直线弹幕
            for i in range(pattern.count):
                speed = pattern.speed + i * pattern.speed_var
                angle = base_angle
                
                bullets.append({
                    'x': bx,
                    'y': by,
                    'vx': speed * math.cos(math.radians(angle)) / 60,
                    'vy': speed * math.sin(math.radians(angle)) / 60,
                    'color': pattern.color,
                    'type': pattern.bullet_type,
                    'alive': True,
                    'delay': i * pattern.interval
                })
        
        elif pattern.pattern_type == "spiral":
            # 螺旋弹幕
            for i in range(pattern.count):
                angle = base_angle + i * (pattern.angle_spread / pattern.count)
                speed = pattern.speed
                
                bullets.append({
                    'x': bx,
                    'y': by,
                    'vx': speed * math.cos(math.radians(angle)) / 60,
                    'vy': speed * math.sin(math.radians(angle)) / 60,
                    'color': pattern.color,
                    'type': pattern.bullet_type,
                    'alive': True,
                    'delay': i * pattern.interval
                })
        
        elif pattern.pattern_type == "aimed":
            # 自机狙
            angle = math.degrees(math.atan2(py - by, px - bx))
            for i in range(pattern.count):
                a = angle + (i - pattern.count // 2) * 5
                speed = pattern.speed
                
                bullets.append({
                    'x': bx,
                    'y': by,
                    'vx': speed * math.cos(math.radians(a)) / 60,
                    'vy': speed * math.sin(math.radians(a)) / 60,
                    'color': pattern.color,
                    'type': pattern.bullet_type,
                    'alive': True
                })
        
        elif pattern.pattern_type == "random":
            # 随机弹幕
            import random
            for i in range(pattern.count):
                angle = random.uniform(0, 360)
                speed = pattern.speed + random.uniform(-pattern.speed_var, pattern.speed_var)
                
                bullets.append({
                    'x': bx,
                    'y': by,
                    'vx': speed * math.cos(math.radians(angle)) / 60,
                    'vy': speed * math.sin(math.radians(angle)) / 60,
                    'color': pattern.color,
                    'type': pattern.bullet_type,
                    'alive': True
                })
        
        return bullets
    
    def _draw_bullets(self):
        """绘制所有子弹"""
        # 清除旧子弹
        for item in self.bullet_items:
            self.scene.removeItem(item)
        self.bullet_items.clear()
        
        for bullet in self.bullets:
            if not bullet.get('alive', True):
                continue
            if bullet.get('delay', 0) > self.simulation_frame:
                continue
            
            sx, sy = self._norm_to_screen(bullet['x'], bullet['y'])
            
            # 根据类型确定大小
            size_map = {
                'ball_s': 6, 'ball_m': 10, 'ball_l': 16,
                'rice': 8, 'scale': 12, 'arrowhead': 10,
                'star': 12, 'needle': 4
            }
            size = size_map.get(bullet['type'], 10)
            
            # 颜色
            rgb = COLOR_RGB.get(bullet['color'], (255, 255, 255))
            color = QColor(*rgb)
            
            pen = QPen(color.darker(120), 1)
            brush = QBrush(color)
            
            item = self.scene.addEllipse(
                sx - size/2, sy - size/2, size, size,
                pen, brush
            )
            self.bullet_items.append(item)
    
    def clear_bullets(self):
        """清除所有子弹"""
        for item in self.bullet_items:
            self.scene.removeItem(item)
        self.bullet_items.clear()
        self.bullets.clear()
        self.simulation_frame = 0
    
    def start_simulation(self):
        """开始模拟"""
        self.simulation_running = True
        self.simulation_frame = 0
        self.timer.start(16)  # 约60FPS
    
    def stop_simulation(self):
        """停止模拟"""
        self.simulation_running = False
        self.timer.stop()
    
    def _update_simulation(self):
        """更新模拟"""
        self.simulation_frame += 1
        
        # 更新子弹位置
        for bullet in self.bullets:
            if not bullet.get('alive', True):
                continue
            if bullet.get('delay', 0) > self.simulation_frame:
                continue
            
            bullet['x'] += bullet['vx']
            bullet['y'] += bullet['vy']
            
            # 边界检测
            if abs(bullet['x']) > 1.2 or abs(bullet['y']) > 1.2:
                bullet['alive'] = False
        
        self._draw_bullets()
        
        # 检查是否所有子弹都消失
        if all(not b.get('alive', True) or b.get('delay', 0) > self.simulation_frame 
               for b in self.bullets):
            if self.simulation_frame > 300:  # 5秒后停止
                self.stop_simulation()


# ==================== 模式编辑器面板 ====================

class PatternEditorPanel(QWidget):
    """弹幕模式编辑面板"""
    
    pattern_changed = pyqtSignal(BulletPattern)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_pattern: Optional[BulletPattern] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 模式类型
        type_group = QGroupBox("模式类型")
        type_layout = QFormLayout(type_group)
        
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_change)
        type_layout.addRow("名称:", self.name_edit)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["circle", "line", "spiral", "aimed", "random"])
        self.type_combo.currentTextChanged.connect(self._on_change)
        type_layout.addRow("类型:", self.type_combo)
        
        layout.addWidget(type_group)
        
        # 子弹属性
        bullet_group = QGroupBox("子弹属性")
        bullet_layout = QFormLayout(bullet_group)
        
        self.bullet_type_combo = QComboBox()
        self.bullet_type_combo.addItems([e.value for e in BulletType])
        self.bullet_type_combo.currentTextChanged.connect(self._on_change)
        bullet_layout.addRow("类型:", self.bullet_type_combo)
        
        self.color_combo = QComboBox()
        self.color_combo.addItems([e.value for e in BulletColor])
        self.color_combo.currentTextChanged.connect(self._on_change)
        bullet_layout.addRow("颜色:", self.color_combo)
        
        # 颜色预览
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(60, 20)
        self.color_preview.setStyleSheet("background-color: red; border: 1px solid #555;")
        bullet_layout.addRow("预览:", self.color_preview)
        
        layout.addWidget(bullet_group)
        
        # 数量和速度
        param_group = QGroupBox("参数")
        param_layout = QFormLayout(param_group)
        
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 200)
        self.count_spin.setValue(12)
        self.count_spin.valueChanged.connect(self._on_change)
        param_layout.addRow("数量:", self.count_spin)
        
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 20.0)
        self.speed_spin.setValue(2.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.valueChanged.connect(self._on_change)
        param_layout.addRow("速度:", self.speed_spin)
        
        self.speed_var_spin = QDoubleSpinBox()
        self.speed_var_spin.setRange(0, 5.0)
        self.speed_var_spin.setValue(0)
        self.speed_var_spin.setSingleStep(0.1)
        self.speed_var_spin.valueChanged.connect(self._on_change)
        param_layout.addRow("速度变化:", self.speed_var_spin)
        
        layout.addWidget(param_group)
        
        # 角度
        angle_group = QGroupBox("角度")
        angle_layout = QFormLayout(angle_group)
        
        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(-360, 360)
        self.angle_spin.setValue(0)
        self.angle_spin.valueChanged.connect(self._on_change)
        angle_layout.addRow("起始角度:", self.angle_spin)
        
        self.spread_spin = QDoubleSpinBox()
        self.spread_spin.setRange(0, 360)
        self.spread_spin.setValue(360)
        self.spread_spin.valueChanged.connect(self._on_change)
        angle_layout.addRow("扩散角度:", self.spread_spin)
        
        self.aim_cb = QCheckBox("自机狙")
        self.aim_cb.toggled.connect(self._on_change)
        angle_layout.addRow("", self.aim_cb)
        
        layout.addWidget(angle_group)
        
        # 时间
        time_group = QGroupBox("时间")
        time_layout = QFormLayout(time_group)
        
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 600)
        self.delay_spin.valueChanged.connect(self._on_change)
        time_layout.addRow("延迟(帧):", self.delay_spin)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 120)
        self.interval_spin.setValue(5)
        self.interval_spin.valueChanged.connect(self._on_change)
        time_layout.addRow("间隔(帧):", self.interval_spin)
        
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 100)
        self.repeat_spin.setValue(1)
        self.repeat_spin.valueChanged.connect(self._on_change)
        time_layout.addRow("重复次数:", self.repeat_spin)
        
        layout.addWidget(time_group)
        
        layout.addStretch()
    
    def set_pattern(self, pattern: BulletPattern):
        """设置当前模式"""
        self._current_pattern = pattern
        self._update_ui()
    
    def _update_ui(self):
        """更新UI显示"""
        if not self._current_pattern:
            return
        
        p = self._current_pattern
        
        # 阻止信号
        self.blockSignals(True)
        
        self.name_edit.setText(p.name)
        self.type_combo.setCurrentText(p.pattern_type)
        self.bullet_type_combo.setCurrentText(p.bullet_type)
        self.color_combo.setCurrentText(p.color)
        self.count_spin.setValue(p.count)
        self.speed_spin.setValue(p.speed)
        self.speed_var_spin.setValue(p.speed_var)
        self.angle_spin.setValue(p.angle)
        self.spread_spin.setValue(p.angle_spread)
        self.aim_cb.setChecked(p.aim_player)
        self.delay_spin.setValue(p.delay)
        self.interval_spin.setValue(p.interval)
        self.repeat_spin.setValue(p.repeat)
        
        # 颜色预览
        rgb = COLOR_RGB.get(p.color, (255, 255, 255))
        self.color_preview.setStyleSheet(
            f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]}); border: 1px solid #555;"
        )
        
        self.blockSignals(False)
    
    def _on_change(self):
        """属性变化"""
        if not self._current_pattern:
            return
        
        p = self._current_pattern
        p.name = self.name_edit.text()
        p.pattern_type = self.type_combo.currentText()
        p.bullet_type = self.bullet_type_combo.currentText()
        p.color = self.color_combo.currentText()
        p.count = self.count_spin.value()
        p.speed = self.speed_spin.value()
        p.speed_var = self.speed_var_spin.value()
        p.angle = self.angle_spin.value()
        p.angle_spread = self.spread_spin.value()
        p.aim_player = self.aim_cb.isChecked()
        p.delay = self.delay_spin.value()
        p.interval = self.interval_spin.value()
        p.repeat = self.repeat_spin.value()
        
        # 更新颜色预览
        rgb = COLOR_RGB.get(p.color, (255, 255, 255))
        self.color_preview.setStyleSheet(
            f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]}); border: 1px solid #555;"
        )
        
        self.pattern_changed.emit(p)
    
    def get_pattern(self) -> Optional[BulletPattern]:
        """获取当前模式"""
        return self._current_pattern


# ==================== 时间轴面板 ====================

class TimelinePanel(QWidget):
    """时间轴面板"""
    
    event_selected = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.events: List[TimelineEvent] = []
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        btn_add = QPushButton("+ 添加事件")
        btn_add.clicked.connect(self._add_event)
        toolbar.addWidget(btn_add)
        
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._delete_event)
        toolbar.addWidget(btn_del)
        
        toolbar.addStretch()
        
        self.time_label = QLabel("时间: 0帧 / 0秒")
        toolbar.addWidget(self.time_label)
        
        layout.addLayout(toolbar)
        
        # 事件列表
        self.event_table = QTableWidget()
        self.event_table.setColumnCount(4)
        self.event_table.setHorizontalHeaderLabels(["时间(帧)", "类型", "参数", "备注"])
        self.event_table.horizontalHeader().setStretchLastSection(True)
        self.event_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.event_table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.event_table)
        
        # 时间滑块
        slider_layout = QHBoxLayout()
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 3600)  # 60秒
        self.time_slider.valueChanged.connect(self._on_time_changed)
        slider_layout.addWidget(self.time_slider)
        
        self.time_spin = QSpinBox()
        self.time_spin.setRange(0, 3600)
        self.time_spin.valueChanged.connect(self._on_time_spin_changed)
        slider_layout.addWidget(self.time_spin)
        
        layout.addLayout(slider_layout)
    
    def set_events(self, events: List[TimelineEvent]):
        """设置事件列表"""
        self.events = events
        self._refresh_table()
    
    def _refresh_table(self):
        """刷新表格"""
        self.event_table.setRowCount(len(self.events))
        
        for i, event in enumerate(self.events):
            self.event_table.setItem(i, 0, QTableWidgetItem(str(event.time)))
            self.event_table.setItem(i, 1, QTableWidgetItem(event.event_type))
            self.event_table.setItem(i, 2, QTableWidgetItem(str(event.data)))
            self.event_table.setItem(i, 3, QTableWidgetItem(""))
    
    def _add_event(self):
        """添加事件"""
        time = self.time_slider.value()
        event = TimelineEvent(time=time, event_type="pattern", data={"pattern": "default"})
        self.events.append(event)
        self.events.sort(key=lambda e: e.time)
        self._refresh_table()
    
    def _delete_event(self):
        """删除事件"""
        row = self.event_table.currentRow()
        if 0 <= row < len(self.events):
            del self.events[row]
            self._refresh_table()
    
    def _on_selection_changed(self):
        """选择变化"""
        row = self.event_table.currentRow()
        if 0 <= row < len(self.events):
            self.event_selected.emit(row)
    
    def _on_time_changed(self, value: int):
        """时间滑块变化"""
        self.time_spin.blockSignals(True)
        self.time_spin.setValue(value)
        self.time_spin.blockSignals(False)
        self.time_label.setText(f"时间: {value}帧 / {value/60:.1f}秒")
    
    def _on_time_spin_changed(self, value: int):
        """时间输入变化"""
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(value)
        self.time_slider.blockSignals(False)
        self.time_label.setText(f"时间: {value}帧 / {value/60:.1f}秒")


# ==================== 代码预览面板 ====================

class CodePreviewPanel(QWidget):
    """代码预览面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        btn_copy = QPushButton("复制代码")
        btn_copy.clicked.connect(self._copy_code)
        toolbar.addWidget(btn_copy)
        
        btn_export = QPushButton("导出文件")
        btn_export.clicked.connect(self._export_file)
        toolbar.addWidget(btn_export)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # 代码编辑器
        self.code_edit = QPlainTextEdit()
        self.code_edit.setFont(QFont("Consolas", 10))
        self.code_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3d3d3d;
            }
        """)
        layout.addWidget(self.code_edit)
    
    def set_code(self, code: str):
        """设置代码"""
        self.code_edit.setPlainText(code)
    
    def _copy_code(self):
        """复制代码"""
        QApplication.clipboard().setText(self.code_edit.toPlainText())
    
    def _export_file(self):
        """导出文件"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出符卡脚本",
            str(GAME_CONTENT_ROOT / "stages" / "stage1" / "spellcards" / "new_spell.py"),
            "Python脚本 (*.py)"
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.code_edit.toPlainText())


# ==================== 主窗口 ====================

class DanmakuScriptEditor(QMainWindow):
    """弹幕脚本编辑器主窗口"""
    
    def __init__(self):
        super().__init__()
        
        self.spellcard = SpellCardData()
        self.current_pattern: Optional[BulletPattern] = None
        
        self._setup_ui()
        self._setup_menu()
        self._apply_theme()
        
        self.setWindowTitle("弹幕脚本编辑器 - PySTG")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)
        
        # 创建默认模式
        self._create_default_pattern()
    
    def _setup_ui(self):
        """设置UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧 - 模式列表和编辑
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # 中间 - 预览
        center_panel = self._create_center_panel()
        splitter.addWidget(center_panel)
        
        # 右侧 - 时间轴和代码
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([350, 450, 500])
        
        self.statusBar().showMessage("就绪")
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 符卡基本信息
        info_group = QGroupBox("符卡信息")
        info_layout = QFormLayout(info_group)
        
        self.name_edit = QLineEdit(self.spellcard.name)
        self.name_edit.textChanged.connect(self._on_spellcard_info_changed)
        info_layout.addRow("名称:", self.name_edit)
        
        self.hp_spin = QSpinBox()
        self.hp_spin.setRange(100, 99999)
        self.hp_spin.setValue(self.spellcard.hp)
        self.hp_spin.valueChanged.connect(self._on_spellcard_info_changed)
        info_layout.addRow("HP:", self.hp_spin)
        
        self.time_spin = QSpinBox()
        self.time_spin.setRange(10, 300)
        self.time_spin.setValue(self.spellcard.time_limit)
        self.time_spin.valueChanged.connect(self._on_spellcard_info_changed)
        info_layout.addRow("时限(秒):", self.time_spin)
        
        # Boss 位置
        pos_widget = QWidget()
        pos_layout = QHBoxLayout(pos_widget)
        pos_layout.setContentsMargins(0, 0, 0, 0)
        
        self.boss_x_spin = QDoubleSpinBox()
        self.boss_x_spin.setRange(-1, 1)
        self.boss_x_spin.setValue(0)
        self.boss_x_spin.setSingleStep(0.1)
        self.boss_x_spin.valueChanged.connect(self._on_boss_pos_changed)
        
        self.boss_y_spin = QDoubleSpinBox()
        self.boss_y_spin.setRange(-1, 1)
        self.boss_y_spin.setValue(0.5)
        self.boss_y_spin.setSingleStep(0.1)
        self.boss_y_spin.valueChanged.connect(self._on_boss_pos_changed)
        
        pos_layout.addWidget(QLabel("X:"))
        pos_layout.addWidget(self.boss_x_spin)
        pos_layout.addWidget(QLabel("Y:"))
        pos_layout.addWidget(self.boss_y_spin)
        
        info_layout.addRow("Boss位置:", pos_widget)
        
        layout.addWidget(info_group)
        
        # 模式列表
        pattern_group = QGroupBox("弹幕模式")
        pattern_layout = QVBoxLayout(pattern_group)
        
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("+ 新建")
        btn_add.clicked.connect(self._add_pattern)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._delete_pattern)
        btn_dup = QPushButton("复制")
        btn_dup.clicked.connect(self._duplicate_pattern)
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_del)
        btn_layout.addWidget(btn_dup)
        pattern_layout.addLayout(btn_layout)
        
        self.pattern_list = QListWidget()
        self.pattern_list.currentRowChanged.connect(self._on_pattern_selected)
        pattern_layout.addWidget(self.pattern_list)
        
        layout.addWidget(pattern_group)
        
        # 模式编辑器
        self.pattern_editor = PatternEditorPanel()
        self.pattern_editor.pattern_changed.connect(self._on_pattern_changed)
        layout.addWidget(self.pattern_editor)
        
        return panel
    
    def _create_center_panel(self) -> QWidget:
        """创建中间面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 预览标题
        title = QLabel("弹幕预览")
        title.setStyleSheet("font-size: 12pt; font-weight: bold;")
        layout.addWidget(title)
        
        # 预览视图
        self.preview_view = DanmakuPreviewView()
        layout.addWidget(self.preview_view)
        
        # 控制栏
        ctrl_layout = QHBoxLayout()
        
        btn_preview = QPushButton("▶ 预览当前模式")
        btn_preview.clicked.connect(self._preview_current_pattern)
        ctrl_layout.addWidget(btn_preview)
        
        btn_play = QPushButton("▶ 播放模拟")
        btn_play.clicked.connect(self._toggle_simulation)
        self.play_btn = btn_play
        ctrl_layout.addWidget(btn_play)
        
        btn_clear = QPushButton("清除")
        btn_clear.clicked.connect(self.preview_view.clear_bullets)
        ctrl_layout.addWidget(btn_clear)
        
        layout.addLayout(ctrl_layout)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        tabs = QTabWidget()
        
        # 时间轴标签
        self.timeline_panel = TimelinePanel()
        tabs.addTab(self.timeline_panel, "时间轴")
        
        # 代码预览标签
        self.code_panel = CodePreviewPanel()
        tabs.addTab(self.code_panel, "代码预览")
        
        layout.addWidget(tabs)
        
        # 生成代码按钮
        btn_generate = QPushButton("🔄 生成代码")
        btn_generate.setStyleSheet("font-size: 11pt; padding: 10px;")
        btn_generate.clicked.connect(self._generate_code)
        layout.addWidget(btn_generate)
        
        return panel
    
    def _setup_menu(self):
        """设置菜单"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        new_action = QAction("新建符卡", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_spellcard)
        file_menu.addAction(new_action)
        
        open_action = QAction("打开...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_spellcard)
        file_menu.addAction(open_action)
        
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_spellcard)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 预设菜单
        preset_menu = menubar.addMenu("预设(&P)")
        
        presets = [
            ("圆形扩散", self._preset_circle),
            ("自机狙", self._preset_aimed),
            ("螺旋弹幕", self._preset_spiral),
            ("随机散射", self._preset_random),
        ]
        
        for name, func in presets:
            action = QAction(name, self)
            action.triggered.connect(func)
            preset_menu.addAction(action)
    
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
            QListWidget, QTableWidget {
                background-color: #1e1e1e;
                border: 1px solid #3d3d3d;
            }
            QListWidget::item:selected, QTableWidget::item:selected {
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
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #007acc;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)
    
    # ==================== 事件处理 ====================
    
    def _create_default_pattern(self):
        """创建默认模式"""
        pattern = BulletPattern(name="circle_1", pattern_type="circle")
        self.spellcard.patterns["circle_1"] = pattern
        self._refresh_pattern_list()
        self.pattern_list.setCurrentRow(0)
    
    def _refresh_pattern_list(self):
        """刷新模式列表"""
        self.pattern_list.clear()
        for name in self.spellcard.patterns:
            self.pattern_list.addItem(name)
    
    def _add_pattern(self):
        """添加模式"""
        idx = len(self.spellcard.patterns) + 1
        name = f"pattern_{idx}"
        while name in self.spellcard.patterns:
            idx += 1
            name = f"pattern_{idx}"
        
        pattern = BulletPattern(name=name)
        self.spellcard.patterns[name] = pattern
        self._refresh_pattern_list()
        
        # 选中新模式
        self.pattern_list.setCurrentRow(self.pattern_list.count() - 1)
    
    def _delete_pattern(self):
        """删除模式"""
        row = self.pattern_list.currentRow()
        if row >= 0 and self.pattern_list.count() > 1:
            name = self.pattern_list.item(row).text()
            del self.spellcard.patterns[name]
            self._refresh_pattern_list()
    
    def _duplicate_pattern(self):
        """复制模式"""
        row = self.pattern_list.currentRow()
        if row >= 0:
            name = self.pattern_list.item(row).text()
            pattern = self.spellcard.patterns[name]
            
            new_name = f"{name}_copy"
            idx = 1
            while new_name in self.spellcard.patterns:
                new_name = f"{name}_copy{idx}"
                idx += 1
            
            new_pattern = BulletPattern(
                name=new_name,
                pattern_type=pattern.pattern_type,
                count=pattern.count,
                speed=pattern.speed,
                angle=pattern.angle,
                angle_spread=pattern.angle_spread,
                bullet_type=pattern.bullet_type,
                color=pattern.color
            )
            
            self.spellcard.patterns[new_name] = new_pattern
            self._refresh_pattern_list()
    
    def _on_pattern_selected(self, row: int):
        """模式选中"""
        if row >= 0:
            name = self.pattern_list.item(row).text()
            self.current_pattern = self.spellcard.patterns[name]
            self.pattern_editor.set_pattern(self.current_pattern)
    
    def _on_pattern_changed(self, pattern: BulletPattern):
        """模式修改"""
        # 更新列表显示
        row = self.pattern_list.currentRow()
        if row >= 0:
            old_name = self.pattern_list.item(row).text()
            if old_name != pattern.name:
                # 名称变化，需要更新字典
                del self.spellcard.patterns[old_name]
                self.spellcard.patterns[pattern.name] = pattern
                self.pattern_list.item(row).setText(pattern.name)
        
        # 实时预览
        self.preview_view.preview_pattern(pattern)
    
    def _on_spellcard_info_changed(self):
        """符卡信息变化"""
        self.spellcard.name = self.name_edit.text()
        self.spellcard.hp = self.hp_spin.value()
        self.spellcard.time_limit = self.time_spin.value()
    
    def _on_boss_pos_changed(self):
        """Boss位置变化"""
        x = self.boss_x_spin.value()
        y = self.boss_y_spin.value()
        self.spellcard.boss_x = x
        self.spellcard.boss_y = y
        self.preview_view.set_boss_pos(x, y)
        
        # 刷新预览
        if self.current_pattern:
            self.preview_view.preview_pattern(self.current_pattern)
    
    def _preview_current_pattern(self):
        """预览当前模式"""
        if self.current_pattern:
            self.preview_view.preview_pattern(self.current_pattern)
    
    def _toggle_simulation(self):
        """切换模拟"""
        if self.preview_view.simulation_running:
            self.preview_view.stop_simulation()
            self.play_btn.setText("▶ 播放模拟")
        else:
            if self.current_pattern:
                self.preview_view.preview_pattern(self.current_pattern)
            self.preview_view.start_simulation()
            self.play_btn.setText("⏸ 停止")
    
    # ==================== 预设 ====================
    
    def _preset_circle(self):
        """圆形扩散预设"""
        pattern = BulletPattern(
            name="circle_spread",
            pattern_type="circle",
            count=24,
            speed=2.0,
            angle_spread=360,
            bullet_type="ball_m",
            color="blue"
        )
        self._apply_preset(pattern)
    
    def _preset_aimed(self):
        """自机狙预设"""
        pattern = BulletPattern(
            name="aimed_shot",
            pattern_type="aimed",
            count=5,
            speed=3.0,
            angle_spread=30,
            bullet_type="rice",
            color="red",
            aim_player=True
        )
        self._apply_preset(pattern)
    
    def _preset_spiral(self):
        """螺旋预设"""
        pattern = BulletPattern(
            name="spiral",
            pattern_type="spiral",
            count=36,
            speed=1.5,
            angle_spread=360,
            bullet_type="scale",
            color="purple",
            interval=2
        )
        self._apply_preset(pattern)
    
    def _preset_random(self):
        """随机预设"""
        pattern = BulletPattern(
            name="random_scatter",
            pattern_type="random",
            count=30,
            speed=2.0,
            speed_var=1.0,
            bullet_type="ball_s",
            color="white"
        )
        self._apply_preset(pattern)
    
    def _apply_preset(self, pattern: BulletPattern):
        """应用预设"""
        self.spellcard.patterns[pattern.name] = pattern
        self._refresh_pattern_list()
        
        # 选中新模式
        for i in range(self.pattern_list.count()):
            if self.pattern_list.item(i).text() == pattern.name:
                self.pattern_list.setCurrentRow(i)
                break
    
    # ==================== 代码生成 ====================
    
    def _generate_code(self):
        """生成符卡代码"""
        code = self._build_code()
        self.code_panel.set_code(code)
    
    def _build_code(self) -> str:
        """构建符卡代码"""
        name = self.spellcard.name
        class_name = ''.join(word.title() for word in name.replace('「', '_').replace('」', '').split())
        class_name = ''.join(c for c in class_name if c.isalnum() or c == '_')
        
        if not class_name:
            class_name = "CustomSpellCard"
        
        lines = [
            '"""',
            f'{name}',
            '',
            '自动生成的符卡脚本',
            '"""',
            '',
            'from src.game.stage.spellcard import SpellCard',
            'import math',
            '',
            '',
            f'class {class_name}(SpellCard):',
            f'    """{name}"""',
            '',
            f'    name = "{name}"',
            f'    hp = {self.spellcard.hp}',
            f'    time_limit = {self.spellcard.time_limit}',
            f'    bonus = 1000000',
            '',
            '    def setup(self):',
            f'        """Boss 移动到初始位置"""',
            f'        yield from self.boss.move_to({self.spellcard.boss_x}, {self.spellcard.boss_y}, duration=60)',
            '',
            '    def run(self):',
            '        """主弹幕逻辑"""',
            '        angle_offset = 0',
            '',
            '        while True:',
        ]
        
        # 为每个模式生成代码
        for name, pattern in self.spellcard.patterns.items():
            lines.append(f'            # === {pattern.name} ===')
            
            if pattern.pattern_type == "circle":
                lines.append(f'            self.fire_circle(')
                lines.append(f'                count={pattern.count},')
                lines.append(f'                speed={pattern.speed},')
                lines.append(f'                start_angle=angle_offset,')
                lines.append(f'                bullet_type="{pattern.bullet_type}",')
                lines.append(f'                color="{pattern.color}"')
                lines.append(f'            )')
                lines.append(f'            angle_offset += 10')
            
            elif pattern.pattern_type == "aimed":
                lines.append(f'            for i in range({pattern.count}):')
                lines.append(f'                self.fire_at_player(')
                lines.append(f'                    speed={pattern.speed} + i * 0.2,')
                lines.append(f'                    bullet_type="{pattern.bullet_type}",')
                lines.append(f'                    color="{pattern.color}"')
                lines.append(f'                )')
                lines.append(f'                yield from self.wait({pattern.interval})')
            
            elif pattern.pattern_type == "spiral":
                lines.append(f'            for i in range({pattern.count}):')
                lines.append(f'                self.fire(')
                lines.append(f'                    angle=angle_offset + i * ({pattern.angle_spread} / {pattern.count}),')
                lines.append(f'                    speed={pattern.speed},')
                lines.append(f'                    bullet_type="{pattern.bullet_type}",')
                lines.append(f'                    color="{pattern.color}"')
                lines.append(f'                )')
                if pattern.interval > 0:
                    lines.append(f'                yield from self.wait({pattern.interval})')
            
            elif pattern.pattern_type == "random":
                lines.append(f'            import random')
                lines.append(f'            for i in range({pattern.count}):')
                lines.append(f'                angle = random.uniform(0, 360)')
                lines.append(f'                speed = {pattern.speed} + random.uniform(-{pattern.speed_var}, {pattern.speed_var})')
                lines.append(f'                self.fire(')
                lines.append(f'                    angle=angle,')
                lines.append(f'                    speed=speed,')
                lines.append(f'                    bullet_type="{pattern.bullet_type}",')
                lines.append(f'                    color="{pattern.color}"')
                lines.append(f'                )')
            
            else:  # line or default
                lines.append(f'            for i in range({pattern.count}):')
                lines.append(f'                self.fire(')
                lines.append(f'                    angle={pattern.angle},')
                lines.append(f'                    speed={pattern.speed} + i * {pattern.speed_var},')
                lines.append(f'                    bullet_type="{pattern.bullet_type}",')
                lines.append(f'                    color="{pattern.color}"')
                lines.append(f'                )')
            
            lines.append('')
            lines.append(f'            yield from self.wait({max(30, pattern.interval * pattern.count)})')
            lines.append('')
        
        lines.append('')
        lines.append(f'# 注册符卡')
        lines.append(f'spellcard = {class_name}')
        
        return '\n'.join(lines)
    
    # ==================== 文件操作 ====================
    
    def _new_spellcard(self):
        """新建符卡"""
        self.spellcard = SpellCardData()
        self.name_edit.setText(self.spellcard.name)
        self.hp_spin.setValue(self.spellcard.hp)
        self.time_spin.setValue(self.spellcard.time_limit)
        self.boss_x_spin.setValue(0)
        self.boss_y_spin.setValue(0.5)
        
        self._create_default_pattern()
        self.preview_view.clear_bullets()
    
    def _open_spellcard(self):
        """打开符卡"""
        path, _ = QFileDialog.getOpenFileName(
            self, "打开符卡脚本",
            str(GAME_CONTENT_ROOT / "stages"),
            "Python脚本 (*.py);;JSON文件 (*.json)"
        )
        if path:
            # TODO: 解析现有脚本
            self.statusBar().showMessage(f"打开: {path}")
    
    def _save_spellcard(self):
        """保存符卡"""
        self._generate_code()
        
        path, _ = QFileDialog.getSaveFileName(
            self, "保存符卡脚本",
            str(GAME_CONTENT_ROOT / "stages" / "stage1" / "spellcards" / "new_spell.py"),
            "Python脚本 (*.py)"
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.code_panel.code_edit.toPlainText())
            self.statusBar().showMessage(f"已保存: {path}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = DanmakuScriptEditor()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
