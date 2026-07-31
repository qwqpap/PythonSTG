#!/usr/bin/env python3
"""
弹幕背景可视化编辑器 v2

功能:
- 自动扫描 assets/images/background 文件树
- 实时3D透视预览（与游戏引擎一致的投影）
- 参数修改自动刷新
- 兼容 data_driven_background JSON 格式
- 导出可复用的场景代码
"""

import sys
import os
import json
import math
import re
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QListWidget,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QGroupBox, QFormLayout, QScrollArea, QTabWidget,
    QFileDialog, QMessageBox, QSlider, QSizePolicy,
    QColorDialog, QAction, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer, QPointF, pyqtSignal, QFileSystemWatcher
from PyQt5.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush,
    QPolygonF, QTransform
)

# ==================== 路径常量 ====================

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.core.atomic_io import atomic_write_json

ASSETS_ROOT = PROJECT_ROOT / "assets"
BG_ROOT = ASSETS_ROOT / "images" / "background"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp"}
MANIFEST_NAMES = {"luastg_backgrounds.json"}


def _is_scene_config_path(path: Path) -> bool:
    """Return True when a JSON file looks like an editable background scene."""
    if path.name in MANIFEST_NAMES:
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    return isinstance(data, dict) and "textures" in data and "layers" in data


def _safe_texture_name(raw: str, used: set) -> str:
    name = re.sub(r"\W+", "_", raw, flags=re.UNICODE).strip("_").lower()
    if not name:
        name = "image"
    base = name
    index = 1
    while name in used:
        index += 1
        name = f"{base}_{index}"
    used.add(name)
    return name


def _numbers(text: str) -> List[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]


def _parse_luastg_camera(lua_text: str) -> dict:
    camera = {
        "eye": [0.0, 0.0, 1.0],
        "at": [0.0, 0.0, 0.0],
        "up": [0.0, 1.0, 0.0],
        "fovy": 0.8,
        "z_near": 0.1,
        "z_far": 10.0,
    }
    fog = {
        "enabled": False,
        "color": [0, 0, 0, 255],
        "start": 0.0,
        "end": 10.0,
    }

    for key in ("eye", "at", "up"):
        m = re.search(rf"Set3D\(\s*['\"]{key}['\"]\s*,([^)]+)\)", lua_text)
        if m:
            vals = _numbers(m.group(1))[:3]
            if len(vals) == 3:
                camera[key] = vals

    m = re.search(r"Set3D\(\s*['\"]fovy['\"]\s*,([^)]+)\)", lua_text)
    if m:
        vals = _numbers(m.group(1))
        if vals:
            camera["fovy"] = vals[0]

    m = re.search(r"Set3D\(\s*['\"]z['\"]\s*,([^)]+)\)", lua_text)
    if m:
        vals = _numbers(m.group(1))[:2]
        if len(vals) == 2:
            camera["z_near"], camera["z_far"] = vals

    m = re.search(r"Set3D\(\s*['\"]fog['\"]\s*,([^)]+)\)", lua_text)
    if m:
        vals = _numbers(m.group(1))[:2]
        if len(vals) == 2:
            fog["start"], fog["end"] = vals
            fog["enabled"] = vals[1] > vals[0]

    return {"camera": camera, "fog": fog}


def generate_luastg_json_configs(overwrite: bool = False) -> Tuple[int, List[str]]:
    """
    Create editable data-driven JSON drafts for copied LuaSTG background folders.

    The generated files are named luastg_<folder>.json so they do not shadow the
    engine's hand-written JSON configs or procedural Python background names.
    """
    if not BG_ROOT.exists():
        return 0, []

    generated: List[str] = []
    for bg_dir in sorted([p for p in BG_ROOT.iterdir() if p.is_dir()]):
        out_path = BG_ROOT / f"luastg_{bg_dir.name}.json"
        if out_path.exists() and not overwrite:
            continue

        images = sorted(
            [p for p in bg_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS],
            key=lambda p: p.name.lower(),
        )
        if not images:
            continue

        lua_files = sorted(bg_dir.glob("*.lua"))
        lua_text = ""
        if lua_files:
            try:
                lua_text = lua_files[0].read_text(encoding="utf-8", errors="ignore")
            except Exception:
                lua_text = ""
        parsed = _parse_luastg_camera(lua_text)

        used = set()
        textures = {}
        layers = []
        for idx, image in enumerate(images):
            tex_name = _safe_texture_name(image.stem, used)
            rel = image.relative_to(BG_ROOT).as_posix()
            textures[tex_name] = {
                "path": rel,
                "description": f"Imported from {bg_dir.name}/{image.name}",
            }
            layers.append({
                "name": tex_name,
                "texture": tex_name,
                "z_order": idx,
                "z_depth": -0.05 * idx,
                "blend_mode": "normal",
                "alpha": 1.0 if idx == 0 else 0.85,
                "scroll_multiplier": 1.0,
                "tile": {
                    "x_range": [-1, 1],
                    "y_range": [-4, 7],
                    "size": 1.0,
                },
                "variants": [],
                "enabled": True,
            })

        config = {
            "name": f"luastg_{bg_dir.name}",
            "description": f"Editable draft generated from LuaSTG background '{bg_dir.name}'.",
            "source": {
                "kind": "luastg_stage_background",
                "folder": bg_dir.name,
                "lua": lua_files[0].name if lua_files else "",
            },
            "textures": textures,
            "camera": parsed["camera"],
            "fog": parsed["fog"],
            "scroll": {"base_speed": 0.003, "direction": [0, 1]},
            "layers": layers,
        }

        atomic_write_json(out_path, config)
        generated.append(out_path.name)

    return len(generated), generated


# ==================== 3D 数学工具 ====================

def _look_at(eye, at, up):
    """构建 look-at 视图矩阵 (4x4)"""
    eye = np.array(eye, dtype=np.float64)
    at = np.array(at, dtype=np.float64)
    up = np.array(up, dtype=np.float64)

    f = at - eye
    f_len = np.linalg.norm(f)
    if f_len < 1e-8:
        return np.eye(4)
    f /= f_len

    s = np.cross(f, up)
    s_len = np.linalg.norm(s)
    if s_len < 1e-8:
        alt = np.array([0.0, 1.0, 0.0]) if abs(f[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        s = np.cross(f, alt)
        s /= np.linalg.norm(s)
    else:
        s /= s_len

    u = np.cross(s, f)

    M = np.eye(4)
    M[0, :3] = s
    M[1, :3] = u
    M[2, :3] = -f
    M[0, 3] = -np.dot(s, eye)
    M[1, 3] = -np.dot(u, eye)
    M[2, 3] = np.dot(f, eye)
    return M


def _perspective(fovy, aspect, z_near, z_far):
    """构建透视投影矩阵 (4x4)"""
    f = 1.0 / max(np.tan(fovy / 2.0), 1e-6)
    M = np.zeros((4, 4))
    M[0, 0] = f / max(aspect, 1e-6)
    M[1, 1] = f
    denom = z_near - z_far
    if abs(denom) < 1e-8:
        denom = -1.0
    M[2, 2] = (z_far + z_near) / denom
    M[2, 3] = (2.0 * z_far * z_near) / denom
    M[3, 2] = -1.0
    return M


def _project(mvp, x, y, z, sw, sh):
    """将 3D 世界坐标投影到屏幕坐标, 返回 (sx, sy) 或 None"""
    p = mvp @ np.array([x, y, z, 1.0])
    if p[3] <= 0.001:
        return None
    p /= p[3]
    sx = (p[0] + 1.0) / 2.0 * sw
    sy = (1.0 - p[1]) / 2.0 * sh
    return (sx, sy)


# ==================== 背景预览控件 ====================

class BackgroundPreview(QWidget):
    """带 3D 透视效果的背景预览控件"""

    PREVIEW_W = 384
    PREVIEW_H = 448

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 470)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.config: Optional[dict] = None
        self.textures: Dict[str, QPixmap] = {}
        self.scroll_offset: float = 0.0
        self.animating: bool = False
        self._mvp = None
        self._dirty_mvp = True

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

        self.buffer = QImage(self.PREVIEW_W, self.PREVIEW_H, QImage.Format_ARGB32)
        self.buffer.fill(QColor(20, 20, 30))

    # ---------- 公共接口 ----------

    def set_config(self, config: dict):
        self.config = config
        self._dirty_mvp = True
        self._load_textures()
        self.render_frame()

    def invalidate_mvp(self):
        self._dirty_mvp = True

    def start_animation(self):
        self.animating = True
        self.timer.start(16)

    def stop_animation(self):
        self.animating = False
        self.timer.stop()

    def reset_scroll(self):
        self.scroll_offset = 0.0
        self.render_frame()

    # ---------- 内部方法 ----------

    def _load_textures(self):
        self.textures.clear()
        if not self.config:
            return
        for name, tex_info in self.config.get("textures", {}).items():
            path = BG_ROOT / tex_info.get("path", "")
            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    self.textures[name] = pix

    def _build_mvp(self):
        if not self.config or not HAS_NUMPY:
            self._mvp = np.eye(4) if HAS_NUMPY else None
            return
        cam = self.config.get("camera", {})
        V = _look_at(cam.get("eye", [0, 0, 1]),
                      cam.get("at", [0, 0, 0]),
                      cam.get("up", [0, 1, 0]))
        P = _perspective(cam.get("fovy", 0.8),
                          self.PREVIEW_W / self.PREVIEW_H,
                          cam.get("z_near", 0.1),
                          cam.get("z_far", 10.0))
        self._mvp = P @ V
        self._dirty_mvp = False

    def render_frame(self):
        if self._dirty_mvp:
            self._build_mvp()

        self.buffer.fill(QColor(0, 0, 0, 255))
        if not self.config:
            self.update()
            return

        # 雾底色
        fog = self.config.get("fog", {})
        fog_enabled = fog.get("enabled", False)
        fog_color_vals = fog.get("color", [0, 0, 0, 255])
        if fog_enabled:
            self.buffer.fill(QColor(fog_color_vals[0], fog_color_vals[1],
                                     fog_color_vals[2], 255))

        painter = QPainter(self.buffer)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)

        layers = sorted(self.config.get("layers", []),
                         key=lambda l: l.get("z_order", 0))

        # 雾效参数
        fog_start = fog.get("start", 0)
        fog_end = fog.get("end", 10)
        cam_cfg = self.config.get("camera", {})
        cam_eye = np.array(cam_cfg.get("eye", [0, 0, 1])) if HAS_NUMPY else None
        cam_at = np.array(cam_cfg.get("at", [0, 0, 0])) if HAS_NUMPY else None
        cam_fwd = None
        if HAS_NUMPY and cam_eye is not None and cam_at is not None:
            fwd = cam_at - cam_eye
            fl = np.linalg.norm(fwd)
            cam_fwd = fwd / fl if fl > 1e-6 else np.array([0, 0, -1])

        for layer_cfg in layers:
            if not layer_cfg.get("enabled", True):
                continue
            tex_name = layer_cfg.get("texture", "")
            if tex_name not in self.textures:
                continue
            pix = self.textures[tex_name]
            alpha = layer_cfg.get("alpha", 1.0)
            blend = layer_cfg.get("blend_mode", "normal")
            z_depth = layer_cfg.get("z_depth", 0.0)
            scroll_mul = layer_cfg.get("scroll_multiplier", 1.0)

            tile_cfg = layer_cfg.get("tile", {})
            x_range = tile_cfg.get("x_range", [-1, 1])
            y_range = tile_cfg.get("y_range", [-4, 7])
            tile_size = tile_cfg.get("size", 1.0)

            # 雾效衰减
            fog_factor = 0.0
            if fog_enabled and fog_end > fog_start and HAS_NUMPY and cam_fwd is not None:
                tc = np.array([0, 0, z_depth])
                depth = abs(np.dot(tc - cam_eye, cam_fwd))
                fog_factor = float(np.clip(
                    (depth - fog_start) / (fog_end - fog_start), 0, 1))
            effective_alpha = alpha * (1.0 - fog_factor * 0.8)

            # 混合模式
            if blend == "add":
                painter.setCompositionMode(QPainter.CompositionMode_Plus)
            elif blend == "multiply":
                painter.setCompositionMode(QPainter.CompositionMode_Multiply)
            else:
                painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            scroll_y = self.scroll_offset * scroll_mul
            self._render_tiles(painter, pix, z_depth, tile_size,
                               x_range, y_range, scroll_y, (0, 0),
                               effective_alpha)

            for variant in layer_cfg.get("variants", []):
                vs = self.scroll_offset * variant.get("scroll_multiplier", 1.0)
                vo = variant.get("offset", [0, 0])
                self._render_tiles(painter, pix, z_depth, tile_size,
                                   x_range, y_range, vs, vo, effective_alpha)

        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # 边框
        painter.setPen(QPen(QColor(100, 100, 150, 180), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(0, 0, self.PREVIEW_W - 1, self.PREVIEW_H - 1)
        painter.end()
        self.update()

    def _render_tiles(self, painter, pix, z_depth, tile_size,
                      x_range, y_range, scroll_y, offset, alpha):
        if tile_size <= 0:
            return
        tw, th = pix.width(), pix.height()
        if tw <= 0 or th <= 0:
            return
        y_scroll = (scroll_y % tile_size) if tile_size > 0 else 0.0

        if HAS_NUMPY and self._mvp is not None:
            self._render_tiles_3d(painter, pix, tw, th, z_depth, tile_size,
                                  x_range, y_range, y_scroll, offset, alpha)
        else:
            self._render_tiles_2d(painter, pix, tw, th, tile_size,
                                  x_range, y_range, y_scroll, offset, alpha)

    def _render_tiles_3d(self, painter, pix, tw, th, z_depth, tile_size,
                         x_range, y_range, y_scroll, offset, alpha):
        """3D 透视渲染"""
        mvp = self._mvp
        pw, ph = self.PREVIEW_W, self.PREVIEW_H
        src_quad = QPolygonF([QPointF(0, 0), QPointF(tw, 0),
                              QPointF(tw, th), QPointF(0, th)])

        for i in range(x_range[0], x_range[1]):
            for j in range(y_range[0], y_range[1]):
                x0 = i * tile_size + offset[0]
                x1 = (i + 1) * tile_size + offset[0]
                y0 = (j - y_scroll) * tile_size + offset[1]
                y1 = (j + 1 - y_scroll) * tile_size + offset[1]
                z = z_depth

                corners = [
                    _project(mvp, x0, y0, z, pw, ph),
                    _project(mvp, x1, y0, z, pw, ph),
                    _project(mvp, x1, y1, z, pw, ph),
                    _project(mvp, x0, y1, z, pw, ph),
                ]
                if any(c is None for c in corners):
                    continue

                # 面积检查 (跳过退化四边形)
                d1 = (corners[2][0] - corners[0][0],
                      corners[2][1] - corners[0][1])
                d2 = (corners[3][0] - corners[1][0],
                      corners[3][1] - corners[1][1])
                area = abs(d1[0] * d2[1] - d1[1] * d2[0]) / 2
                if area < 2:
                    continue

                # 视口裁剪
                xs = [c[0] for c in corners]
                ys = [c[1] for c in corners]
                if max(xs) < -100 or min(xs) > pw + 100:
                    continue
                if max(ys) < -100 or min(ys) > ph + 100:
                    continue

                dst_quad = QPolygonF([QPointF(c[0], c[1]) for c in corners])
                transform = QTransform()
                if QTransform.quadToQuad(src_quad, dst_quad, transform):
                    painter.save()
                    painter.setTransform(transform)
                    painter.setOpacity(alpha)
                    painter.drawPixmap(0, 0, pix)
                    painter.restore()

    def _render_tiles_2d(self, painter, pix, tw, th, tile_size,
                         x_range, y_range, y_scroll, offset, alpha):
        """2D 后备渲染 (无 numpy 时)"""
        scale = min(self.PREVIEW_W, self.PREVIEW_H) / max(
            (x_range[1] - x_range[0]) * tile_size,
            (y_range[1] - y_range[0]) * tile_size, 1)
        painter.setOpacity(alpha)
        cx = self.PREVIEW_W / 2
        x_mid = (x_range[0] + x_range[1]) / 2.0
        for i in range(x_range[0], x_range[1]):
            for j in range(y_range[0], y_range[1]):
                x = (i - x_mid + offset[0]) * scale + cx
                y = (j - y_scroll + offset[1]) * scale
                w = tile_size * scale
                h = tile_size * scale
                painter.drawPixmap(int(x), int(y), int(w), int(h), pix)

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        scale = min(w / self.PREVIEW_W, h / self.PREVIEW_H)
        pw = int(self.PREVIEW_W * scale)
        ph = int(self.PREVIEW_H * scale)
        x = (w - pw) // 2
        y = (h - ph) // 2
        p.fillRect(self.rect(), QColor(20, 20, 30))
        p.drawImage(x, y, self.buffer.scaled(
            pw, ph, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _tick(self):
        if self.config:
            speed = self.config.get("scroll", {}).get("base_speed", 0.003)
            self.scroll_offset += speed * 0.016
            self.render_frame()


# ==================== 文件树面板 ====================

class FileTreePanel(QWidget):
    """自动扫描 assets/images/background 的文件树"""

    config_selected = pyqtSignal(str)
    image_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_watcher()
        self.refresh_tree()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        header = QHBoxLayout()
        title = QLabel("背景资源")
        title.setStyleSheet("font-size: 11pt; font-weight: bold; color: #ddd;")
        header.addWidget(title)
        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedWidth(30)
        btn_refresh.setToolTip("刷新文件树")
        btn_refresh.clicked.connect(self.refresh_tree)
        header.addWidget(btn_refresh)
        btn_import = QPushButton("导入")
        btn_import.setFixedWidth(48)
        btn_import.setToolTip("从已复制的 LuaSTG 背景目录生成可编辑 JSON 草稿")
        btn_import.clicked.connect(self._import_luastg_configs)
        header.addWidget(btn_import)
        layout.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["名称", "信息"])
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setAnimated(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

        # 缩略图预览
        thumb_group = QGroupBox("图片预览")
        thumb_layout = QVBoxLayout(thumb_group)
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(200, 160)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setStyleSheet(
            "background-color: #1a1a1a; border: 1px solid #333;")
        self.thumbnail.setText("选择图片查看")
        thumb_layout.addWidget(self.thumbnail)
        self.thumb_info = QLabel("")
        self.thumb_info.setStyleSheet("color: #888; font-size: 9pt;")
        thumb_layout.addWidget(self.thumb_info)
        layout.addWidget(thumb_group)

    def _setup_watcher(self):
        self.watcher = QFileSystemWatcher()
        if BG_ROOT.exists():
            self.watcher.addPath(str(BG_ROOT))
            for sub in BG_ROOT.iterdir():
                if sub.is_dir():
                    self.watcher.addPath(str(sub))
        self.watcher.directoryChanged.connect(lambda _: self.refresh_tree())

    def refresh_tree(self):
        self.tree.clear()
        if not BG_ROOT.exists():
            QTreeWidgetItem(self.tree, ["(目录不存在)", ""])
            return

        # 场景配置 (.json)
        jsons = sorted([p for p in BG_ROOT.glob("*.json") if _is_scene_config_path(p)])
        if jsons:
            root = QTreeWidgetItem(self.tree,
                                   ["📁 场景配置", f"{len(jsons)} 个"])
            root.setExpanded(True)
            for jf in jsons:
                item = QTreeWidgetItem(root, [f"🎬 {jf.stem}", "JSON"])
                item.setData(0, Qt.UserRole, str(jf))
                item.setData(0, Qt.UserRole + 1, "json")
                item.setForeground(0, QBrush(QColor(100, 200, 255)))

        # 图片素材文件夹
        dirs = sorted([d for d in BG_ROOT.iterdir() if d.is_dir()])
        if dirs:
            root = QTreeWidgetItem(self.tree,
                                   ["📁 图片素材", f"{len(dirs)} 组"])
            root.setExpanded(True)
            for d in dirs:
                imgs = sorted(list(d.glob("*.png")) + list(d.glob("*.jpg")))
                dir_item = QTreeWidgetItem(
                    root, [f"📂 {d.name}", f"{len(imgs)} 张"])
                for img in imgs:
                    sz_kb = img.stat().st_size // 1024
                    img_item = QTreeWidgetItem(
                        dir_item, [f"🖼 {img.name}", f"{sz_kb}KB"])
                    img_item.setData(0, Qt.UserRole, str(img))
                    img_item.setData(0, Qt.UserRole + 1, "image")

        # Lua/模型等原始资源
        raw_files = []
        for d in dirs:
            raw_files.extend(
                [p for p in d.iterdir()
                 if p.is_file() and p.suffix.lower() in {".lua", ".obj", ".mtl"}]
            )
        if raw_files:
            root = QTreeWidgetItem(self.tree, ["📁 原始 LuaSTG", f"{len(raw_files)} 个"])
            for d in dirs:
                files = [p for p in sorted(d.iterdir())
                         if p.is_file() and p.suffix.lower() in {".lua", ".obj", ".mtl"}]
                if not files:
                    continue
                dir_item = QTreeWidgetItem(root, [f"📂 {d.name}", f"{len(files)} 个"])
                for file_path in files:
                    item = QTreeWidgetItem(dir_item, [f"📄 {file_path.name}", file_path.suffix])
                    item.setData(0, Qt.UserRole, str(file_path))
                    item.setData(0, Qt.UserRole + 1, "raw")

    def _on_item_clicked(self, item, col):
        itype = item.data(0, Qt.UserRole + 1)
        path = item.data(0, Qt.UserRole)
        if itype == "image" and path:
            self._show_thumbnail(path)
            self.image_selected.emit(path)
        elif itype == "json" and path:
            self.config_selected.emit(path)
        elif itype == "raw" and path:
            self.thumbnail.setText("原始资源")
            self.thumb_info.setText(Path(path).name)

    def _on_item_double_clicked(self, item, col):
        itype = item.data(0, Qt.UserRole + 1)
        path = item.data(0, Qt.UserRole)
        if itype == "json" and path:
            self.config_selected.emit(path)

    def _import_luastg_configs(self):
        try:
            count, files = generate_luastg_json_configs(overwrite=False)
            self.refresh_tree()
            if count:
                sample = ", ".join(files[:5])
                more = "" if len(files) <= 5 else f" 等 {len(files)} 个"
                QMessageBox.information(
                    self, "导入完成",
                    f"已生成 {count} 个可编辑背景配置：{sample}{more}")
            else:
                QMessageBox.information(self, "无需导入", "没有新的 LuaSTG 背景需要生成配置。")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def _show_thumbnail(self, path):
        pix = QPixmap(path)
        if not pix.isNull():
            self.thumbnail.setPixmap(
                pix.scaled(200, 160, Qt.KeepAspectRatio,
                           Qt.SmoothTransformation))
            self.thumb_info.setText(f"{pix.width()} x {pix.height()}")
        else:
            self.thumbnail.setText("无法加载")
            self.thumb_info.setText("")


# ==================== 图层编辑面板 ====================

class LayerEditorPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: Optional[dict] = None
        self._cur_idx = -1
        self._block = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 图层列表
        list_grp = QGroupBox("图层列表")
        ll = QVBoxLayout(list_grp)

        btns = QHBoxLayout()
        for text, slot, tip in [
            ("+ 添加", self._add_layer, "新建空图层"),
            ("⧉ 复制", self._dup_layer, "复制当前选中图层"),
            ("- 删除", self._del_layer, "删除当前选中图层"),
            ("▲", self._move_up, "上移"),
            ("▼", self._move_down, "下移"),
        ]:
            b = QPushButton(text)
            if text in ("▲", "▼"):
                b.setFixedWidth(30)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            btns.addWidget(b)
        ll.addLayout(btns)

        self.layer_list = QListWidget()
        self.layer_list.setMaximumHeight(120)
        self.layer_list.currentRowChanged.connect(self._on_layer_selected)
        ll.addWidget(self.layer_list)
        layout.addWidget(list_grp)

        # 属性滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        pw = QWidget()
        pl = QVBoxLayout(pw)

        # — 基本属性 —
        basic = QGroupBox("基本属性")
        bl = QFormLayout(basic)
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_prop)
        bl.addRow("名称:", self.name_edit)
        self.texture_combo = QComboBox()
        self.texture_combo.currentTextChanged.connect(self._on_prop)
        bl.addRow("纹理:", self.texture_combo)
        self.z_order_spin = QSpinBox()
        self.z_order_spin.setRange(-100, 100)
        self.z_order_spin.valueChanged.connect(self._on_prop)
        bl.addRow("Z顺序:", self.z_order_spin)
        self.z_depth_spin = QDoubleSpinBox()
        self.z_depth_spin.setRange(-10, 10)
        self.z_depth_spin.setSingleStep(0.1)
        self.z_depth_spin.setDecimals(2)
        self.z_depth_spin.valueChanged.connect(self._on_prop)
        bl.addRow("Z深度:", self.z_depth_spin)
        self.enabled_cb = QCheckBox("启用")
        self.enabled_cb.setChecked(True)
        self.enabled_cb.toggled.connect(self._on_prop)
        bl.addRow("", self.enabled_cb)
        pl.addWidget(basic)

        # — 显示属性 —
        disp = QGroupBox("显示")
        dl = QFormLayout(disp)
        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setRange(0, 1)
        self.alpha_spin.setSingleStep(0.05)
        self.alpha_spin.setDecimals(3)
        self.alpha_spin.valueChanged.connect(self._on_prop)
        dl.addRow("透明度:", self.alpha_spin)
        self.blend_combo = QComboBox()
        self.blend_combo.addItems(["normal", "add", "multiply"])
        self.blend_combo.currentTextChanged.connect(self._on_prop)
        dl.addRow("混合模式:", self.blend_combo)
        self.scroll_mul = QDoubleSpinBox()
        self.scroll_mul.setRange(-10, 10)
        self.scroll_mul.setSingleStep(0.05)
        self.scroll_mul.setDecimals(3)
        self.scroll_mul.valueChanged.connect(self._on_prop)
        dl.addRow("滚动系数:", self.scroll_mul)
        pl.addWidget(disp)

        # — 平铺 —
        tile_grp = QGroupBox("平铺配置")
        tl = QFormLayout(tile_grp)
        xr = QHBoxLayout()
        self.tile_x0 = QSpinBox()
        self.tile_x0.setRange(-10, 10)
        self.tile_x0.valueChanged.connect(self._on_prop)
        self.tile_x1 = QSpinBox()
        self.tile_x1.setRange(-10, 10)
        self.tile_x1.valueChanged.connect(self._on_prop)
        xr.addWidget(self.tile_x0)
        xr.addWidget(QLabel("~"))
        xr.addWidget(self.tile_x1)
        tl.addRow("X范围:", xr)
        yr = QHBoxLayout()
        self.tile_y0 = QSpinBox()
        self.tile_y0.setRange(-20, 20)
        self.tile_y0.valueChanged.connect(self._on_prop)
        self.tile_y1 = QSpinBox()
        self.tile_y1.setRange(-20, 20)
        self.tile_y1.valueChanged.connect(self._on_prop)
        yr.addWidget(self.tile_y0)
        yr.addWidget(QLabel("~"))
        yr.addWidget(self.tile_y1)
        tl.addRow("Y范围:", yr)
        self.tile_size = QDoubleSpinBox()
        self.tile_size.setRange(0.1, 10)
        self.tile_size.setSingleStep(0.1)
        self.tile_size.setValue(1.0)
        self.tile_size.valueChanged.connect(self._on_prop)
        tl.addRow("尺寸:", self.tile_size)
        pl.addWidget(tile_grp)

        # — 变体（同一纹理的偏移/滚动克隆） —
        var_grp = QGroupBox("变体 (variants)")
        vl = QVBoxLayout(var_grp)
        vl.setContentsMargins(6, 6, 6, 6)

        var_btns = QHBoxLayout()
        for text, slot, tip in [
            ("+", self._add_variant, "新增变体"),
            ("-", self._del_variant, "删除选中变体"),
        ]:
            b = QPushButton(text)
            b.setFixedWidth(28)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            var_btns.addWidget(b)
        var_btns.addStretch()
        vl.addLayout(var_btns)

        self.variant_list = QListWidget()
        self.variant_list.setMaximumHeight(80)
        self.variant_list.currentRowChanged.connect(self._on_variant_selected)
        vl.addWidget(self.variant_list)

        var_form = QFormLayout()
        self.var_off_x = QDoubleSpinBox()
        self.var_off_x.setRange(-10, 10)
        self.var_off_x.setSingleStep(0.05)
        self.var_off_x.setDecimals(3)
        self.var_off_x.valueChanged.connect(self._on_variant_prop)
        self.var_off_y = QDoubleSpinBox()
        self.var_off_y.setRange(-10, 10)
        self.var_off_y.setSingleStep(0.05)
        self.var_off_y.setDecimals(3)
        self.var_off_y.valueChanged.connect(self._on_variant_prop)
        off_row = QHBoxLayout()
        off_row.addWidget(self.var_off_x)
        off_row.addWidget(self.var_off_y)
        var_form.addRow("偏移 X/Y:", off_row)
        self.var_scroll_mul = QDoubleSpinBox()
        self.var_scroll_mul.setRange(-10, 10)
        self.var_scroll_mul.setSingleStep(0.05)
        self.var_scroll_mul.setDecimals(3)
        self.var_scroll_mul.valueChanged.connect(self._on_variant_prop)
        var_form.addRow("滚动系数:", self.var_scroll_mul)
        vl.addLayout(var_form)

        self._cur_variant_idx = -1
        pl.addWidget(var_grp)

        pl.addStretch()
        scroll.setWidget(pw)
        layout.addWidget(scroll)

    # --- 公共接口 ---

    def set_config(self, config: dict):
        self._config = config
        self._cur_idx = -1
        self._refresh_list()
        self._refresh_texture_combo()

    def _refresh_texture_combo(self):
        self.texture_combo.blockSignals(True)
        self.texture_combo.clear()
        if self._config:
            self.texture_combo.addItems(
                list(self._config.get("textures", {}).keys()))
        self.texture_combo.blockSignals(False)

    # --- 内部 ---

    def _refresh_list(self):
        self.layer_list.clear()
        if not self._config:
            return
        for layer in self._config.get("layers", []):
            en = "✓" if layer.get("enabled", True) else "✗"
            z = layer.get("z_order", 0)
            self.layer_list.addItem(
                f"{en} [{z}] {layer.get('name', '?')}")

    def _on_layer_selected(self, row):
        self._cur_idx = row
        if not self._config or row < 0:
            self._refresh_variant_list()
            return
        layers = self._config.get("layers", [])
        if row >= len(layers):
            return
        L = layers[row]
        self._block = True
        self.name_edit.setText(L.get("name", ""))
        self.texture_combo.setCurrentText(L.get("texture", ""))
        self.z_order_spin.setValue(L.get("z_order", 0))
        self.z_depth_spin.setValue(L.get("z_depth", 0))
        self.enabled_cb.setChecked(L.get("enabled", True))
        self.alpha_spin.setValue(L.get("alpha", 1.0))
        self.blend_combo.setCurrentText(L.get("blend_mode", "normal"))
        self.scroll_mul.setValue(L.get("scroll_multiplier", 1.0))
        tile = L.get("tile", {})
        xr = tile.get("x_range", [-1, 1])
        yr = tile.get("y_range", [-4, 7])
        self.tile_x0.setValue(xr[0])
        self.tile_x1.setValue(xr[1])
        self.tile_y0.setValue(yr[0])
        self.tile_y1.setValue(yr[1])
        self.tile_size.setValue(tile.get("size", 1.0))
        self._block = False
        self._refresh_variant_list()

    def _on_prop(self):
        if self._block or not self._config:
            return
        idx = self._cur_idx
        layers = self._config.get("layers", [])
        if idx < 0 or idx >= len(layers):
            return
        L = layers[idx]
        L["name"] = self.name_edit.text()
        L["texture"] = self.texture_combo.currentText()
        L["z_order"] = self.z_order_spin.value()
        L["z_depth"] = self.z_depth_spin.value()
        L["enabled"] = self.enabled_cb.isChecked()
        L["alpha"] = self.alpha_spin.value()
        L["blend_mode"] = self.blend_combo.currentText()
        L["scroll_multiplier"] = self.scroll_mul.value()
        L.setdefault("tile", {})
        L["tile"]["x_range"] = [self.tile_x0.value(), self.tile_x1.value()]
        L["tile"]["y_range"] = [self.tile_y0.value(), self.tile_y1.value()]
        L["tile"]["size"] = self.tile_size.value()
        self._refresh_list()
        if idx >= 0:
            self.layer_list.setCurrentRow(idx)
        self.changed.emit()

    def _add_layer(self):
        if not self._config:
            return
        layers = self._config.setdefault("layers", [])
        tex_names = list(self._config.get("textures", {}).keys())
        layers.append({
            "name": f"layer_{len(layers)}",
            "texture": tex_names[0] if tex_names else "",
            "z_order": len(layers), "z_depth": 0.0,
            "blend_mode": "normal", "alpha": 1.0,
            "scroll_multiplier": 1.0,
            "tile": {"x_range": [-1, 1], "y_range": [-4, 7], "size": 1.0},
            "variants": [], "enabled": True
        })
        self._refresh_list()
        self.layer_list.setCurrentRow(len(layers) - 1)
        self.changed.emit()

    def _del_layer(self):
        if not self._config:
            return
        layers = self._config.get("layers", [])
        idx = self._cur_idx
        if 0 <= idx < len(layers):
            del layers[idx]
            self._cur_idx = -1
            self._refresh_list()
            self.changed.emit()

    def _dup_layer(self):
        """复制当前选中的图层，插入其后"""
        if not self._config:
            return
        layers = self._config.get("layers", [])
        idx = self._cur_idx
        if not (0 <= idx < len(layers)):
            return
        import copy
        clone = copy.deepcopy(layers[idx])
        base = clone.get("name", "layer")
        existing = {L.get("name", "") for L in layers}
        new_name, i = f"{base}_copy", 1
        while new_name in existing:
            i += 1
            new_name = f"{base}_copy{i}"
        clone["name"] = new_name
        layers.insert(idx + 1, clone)
        self._refresh_list()
        self.layer_list.setCurrentRow(idx + 1)
        self.changed.emit()

    # --- 变体 ---

    def _current_layer(self) -> Optional[dict]:
        if not self._config:
            return None
        layers = self._config.get("layers", [])
        if 0 <= self._cur_idx < len(layers):
            return layers[self._cur_idx]
        return None

    def _refresh_variant_list(self):
        self.variant_list.blockSignals(True)
        self.variant_list.clear()
        L = self._current_layer()
        if L:
            for v in L.get("variants", []):
                off = v.get("offset", [0, 0])
                sm = v.get("scroll_multiplier", 1.0)
                self.variant_list.addItem(
                    f"offset=({off[0]:.2f},{off[1]:.2f})  x{sm:.2f}")
        self.variant_list.blockSignals(False)
        self._cur_variant_idx = -1
        self._block = True
        self.var_off_x.setValue(0)
        self.var_off_y.setValue(0)
        self.var_scroll_mul.setValue(1.0)
        self._block = False

    def _on_variant_selected(self, row):
        self._cur_variant_idx = row
        L = self._current_layer()
        if not L or row < 0:
            return
        variants = L.get("variants", [])
        if row >= len(variants):
            return
        v = variants[row]
        off = v.get("offset", [0, 0])
        self._block = True
        self.var_off_x.setValue(off[0])
        self.var_off_y.setValue(off[1])
        self.var_scroll_mul.setValue(v.get("scroll_multiplier", 1.0))
        self._block = False

    def _on_variant_prop(self):
        if self._block:
            return
        L = self._current_layer()
        if not L:
            return
        variants = L.setdefault("variants", [])
        idx = self._cur_variant_idx
        if not (0 <= idx < len(variants)):
            return
        variants[idx]["offset"] = [self.var_off_x.value(),
                                   self.var_off_y.value()]
        variants[idx]["scroll_multiplier"] = self.var_scroll_mul.value()
        # 只更新列表项文本，不重建避免丢选中
        off = variants[idx]["offset"]
        sm = variants[idx]["scroll_multiplier"]
        item = self.variant_list.item(idx)
        if item:
            item.setText(
                f"offset=({off[0]:.2f},{off[1]:.2f})  x{sm:.2f}")
        self.changed.emit()

    def _add_variant(self):
        L = self._current_layer()
        if not L:
            return
        variants = L.setdefault("variants", [])
        variants.append({"offset": [0.0, 0.0], "scroll_multiplier": 1.0})
        self._refresh_variant_list()
        self.variant_list.setCurrentRow(len(variants) - 1)
        self.changed.emit()

    def _del_variant(self):
        L = self._current_layer()
        if not L:
            return
        variants = L.get("variants", [])
        idx = self._cur_variant_idx
        if 0 <= idx < len(variants):
            del variants[idx]
            self._refresh_variant_list()
            self.changed.emit()

    def _move_up(self):
        if not self._config:
            return
        layers = self._config.get("layers", [])
        idx = self._cur_idx
        if idx > 0:
            layers[idx], layers[idx - 1] = layers[idx - 1], layers[idx]
            self._refresh_list()
            self.layer_list.setCurrentRow(idx - 1)
            self.changed.emit()

    def _move_down(self):
        if not self._config:
            return
        layers = self._config.get("layers", [])
        idx = self._cur_idx
        if 0 <= idx < len(layers) - 1:
            layers[idx], layers[idx + 1] = layers[idx + 1], layers[idx]
            self._refresh_list()
            self.layer_list.setCurrentRow(idx + 1)
            self.changed.emit()


# ==================== 摄像机编辑面板 ====================

class CameraEditorPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: Optional[dict] = None
        self._block = False
        self._setup_ui()

    def _dspin(self, lo, hi, step, decimals=2):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(decimals)
        s.valueChanged.connect(self._on_change)
        return s

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        eye_g = QGroupBox("摄像机位置 (Eye)")
        el = QFormLayout(eye_g)
        self.eye_x = self._dspin(-20, 20, 0.05)
        self.eye_y = self._dspin(-20, 20, 0.05)
        self.eye_z = self._dspin(-20, 20, 0.05)
        el.addRow("X:", self.eye_x)
        el.addRow("Y:", self.eye_y)
        el.addRow("Z:", self.eye_z)
        layout.addWidget(eye_g)

        at_g = QGroupBox("目标位置 (At)")
        al = QFormLayout(at_g)
        self.at_x = self._dspin(-20, 20, 0.05)
        self.at_y = self._dspin(-20, 20, 0.05)
        self.at_z = self._dspin(-20, 20, 0.05)
        al.addRow("X:", self.at_x)
        al.addRow("Y:", self.at_y)
        al.addRow("Z:", self.at_z)
        layout.addWidget(at_g)

        up_g = QGroupBox("上方向 (Up)")
        ul = QFormLayout(up_g)
        self.up_x = self._dspin(-1, 1, 0.1)
        self.up_y = self._dspin(-1, 1, 0.1)
        self.up_z = self._dspin(-1, 1, 0.1)
        ul.addRow("X:", self.up_x)
        ul.addRow("Y:", self.up_y)
        ul.addRow("Z:", self.up_z)
        layout.addWidget(up_g)

        proj_g = QGroupBox("投影参数")
        pl = QFormLayout(proj_g)
        self.fovy = self._dspin(0.1, 3.14, 0.05)
        self.z_near = self._dspin(0.001, 10, 0.01, 3)
        self.z_far = self._dspin(0.1, 100, 0.5)
        pl.addRow("FOV Y:", self.fovy)
        pl.addRow("近裁面:", self.z_near)
        pl.addRow("远裁面:", self.z_far)
        layout.addWidget(proj_g)
        layout.addStretch()

    def set_config(self, config: dict):
        self._config = config
        cam = config.get("camera", {})
        e = cam.get("eye", [0, 0, 1])
        a = cam.get("at", [0, 0, 0])
        u = cam.get("up", [0, 1, 0])
        self._block = True
        self.eye_x.setValue(e[0])
        self.eye_y.setValue(e[1])
        self.eye_z.setValue(e[2])
        self.at_x.setValue(a[0])
        self.at_y.setValue(a[1])
        self.at_z.setValue(a[2])
        self.up_x.setValue(u[0])
        self.up_y.setValue(u[1])
        self.up_z.setValue(u[2])
        self.fovy.setValue(cam.get("fovy", 0.8))
        self.z_near.setValue(cam.get("z_near", 0.1))
        self.z_far.setValue(cam.get("z_far", 10.0))
        self._block = False

    def _on_change(self):
        if self._block or not self._config:
            return
        cam = self._config.setdefault("camera", {})
        cam["eye"] = [self.eye_x.value(), self.eye_y.value(),
                      self.eye_z.value()]
        cam["at"] = [self.at_x.value(), self.at_y.value(),
                     self.at_z.value()]
        cam["up"] = [self.up_x.value(), self.up_y.value(),
                     self.up_z.value()]
        cam["fovy"] = self.fovy.value()
        cam["z_near"] = self.z_near.value()
        cam["z_far"] = self.z_far.value()
        self.changed.emit()


# ==================== 雾效编辑面板 ====================

class FogEditorPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: Optional[dict] = None
        self._block = False
        self._fog_color = QColor(0, 0, 0)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.enabled_cb = QCheckBox("启用雾效")
        self.enabled_cb.toggled.connect(self._on_change)
        layout.addWidget(self.enabled_cb)

        dg = QGroupBox("雾效距离")
        dl = QFormLayout(dg)
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0, 20)
        self.start_spin.setSingleStep(0.1)
        self.start_spin.valueChanged.connect(self._on_change)
        dl.addRow("起始:", self.start_spin)
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0, 20)
        self.end_spin.setSingleStep(0.1)
        self.end_spin.valueChanged.connect(self._on_change)
        dl.addRow("结束:", self.end_spin)
        layout.addWidget(dg)

        cg = QGroupBox("雾效颜色")
        cl = QVBoxLayout(cg)
        self.color_lbl = QLabel()
        self.color_lbl.setFixedSize(120, 30)
        self.color_lbl.setStyleSheet(
            "background-color: black; border: 1px solid #555;")
        cl.addWidget(self.color_lbl)
        btn = QPushButton("选择颜色")
        btn.clicked.connect(self._pick_color)
        cl.addWidget(btn)
        layout.addWidget(cg)
        layout.addStretch()

    def set_config(self, config: dict):
        self._config = config
        fog = config.get("fog", {})
        self._block = True
        self.enabled_cb.setChecked(fog.get("enabled", False))
        self.start_spin.setValue(fog.get("start", 0))
        self.end_spin.setValue(fog.get("end", 10))
        c = fog.get("color", [0, 0, 0, 255])
        self._fog_color = QColor(c[0], c[1], c[2])
        self._update_color()
        self._block = False

    def _update_color(self):
        self.color_lbl.setStyleSheet(
            f"background-color: {self._fog_color.name()}; "
            f"border: 1px solid #555;")

    def _pick_color(self):
        c = QColorDialog.getColor(self._fog_color, self, "选择雾效颜色")
        if c.isValid():
            self._fog_color = c
            self._update_color()
            self._on_change()

    def _on_change(self):
        if self._block or not self._config:
            return
        fog = self._config.setdefault("fog", {})
        fog["enabled"] = self.enabled_cb.isChecked()
        fog["start"] = self.start_spin.value()
        fog["end"] = self.end_spin.value()
        fog["color"] = [self._fog_color.red(), self._fog_color.green(),
                        self._fog_color.blue(), 255]
        self.changed.emit()


# ==================== 滚动编辑面板 ====================

class ScrollEditorPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: Optional[dict] = None
        self._block = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        g = QGroupBox("滚动参数")
        fl = QFormLayout(g)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0, 5)
        self.speed.setSingleStep(0.001)
        self.speed.setDecimals(4)
        self.speed.valueChanged.connect(self._on_change)
        fl.addRow("基础速度:", self.speed)
        dr = QHBoxLayout()
        self.dir_x = QDoubleSpinBox()
        self.dir_x.setRange(-5, 5)
        self.dir_x.setSingleStep(0.1)
        self.dir_x.valueChanged.connect(self._on_change)
        self.dir_y = QDoubleSpinBox()
        self.dir_y.setRange(-5, 5)
        self.dir_y.setSingleStep(0.1)
        self.dir_y.valueChanged.connect(self._on_change)
        dr.addWidget(self.dir_x)
        dr.addWidget(self.dir_y)
        fl.addRow("方向:", dr)
        layout.addWidget(g)
        layout.addStretch()

    def set_config(self, config: dict):
        self._config = config
        s = config.get("scroll", {})
        self._block = True
        self.speed.setValue(s.get("base_speed", 0.003))
        d = s.get("direction", [0, 1])
        self.dir_x.setValue(d[0])
        self.dir_y.setValue(d[1])
        self._block = False

    def _on_change(self):
        if self._block or not self._config:
            return
        sc = self._config.setdefault("scroll", {})
        sc["base_speed"] = self.speed.value()
        sc["direction"] = [self.dir_x.value(), self.dir_y.value()]
        self.changed.emit()


# ==================== 纹理管理面板 ====================

class TexturePanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: Optional[dict] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        g = QGroupBox("纹理列表")
        gl = QVBoxLayout(g)
        btns = QHBoxLayout()
        add_b = QPushButton("+ 添加纹理")
        add_b.clicked.connect(self._add)
        del_b = QPushButton("- 移除")
        del_b.clicked.connect(self._remove)
        btns.addWidget(add_b)
        btns.addWidget(del_b)
        gl.addLayout(btns)
        self.tex_list = QListWidget()
        self.tex_list.setMaximumHeight(160)
        gl.addWidget(self.tex_list)
        layout.addWidget(g)
        layout.addStretch()

    def set_config(self, config: dict):
        self._config = config
        self._refresh()

    def _refresh(self):
        self.tex_list.clear()
        if not self._config:
            return
        for name, info in self._config.get("textures", {}).items():
            p = info.get("path", "")
            d = info.get("description", "")
            label = f"{name}: {p}"
            if d:
                label += f"  ({d})"
            self.tex_list.addItem(label)

    def _add(self):
        if not self._config:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择纹理", str(BG_ROOT), "图片 (*.png *.jpg)")
        if not path:
            return
        self._add_from_path(path)

    def _add_from_path(self, path):
        if not self._config:
            return
        p = Path(path)
        try:
            rel = p.relative_to(BG_ROOT)
        except ValueError:
            rel = Path(p.name)
        name = p.stem
        textures = self._config.setdefault("textures", {})
        base = name
        i = 1
        while name in textures:
            name = f"{base}_{i}"
            i += 1
        textures[name] = {
            "path": str(rel).replace("\\", "/"),
            "description": ""
        }
        self._refresh()
        self.changed.emit()

    def _remove(self):
        if not self._config:
            return
        row = self.tex_list.currentRow()
        if row < 0:
            return
        keys = list(self._config.get("textures", {}).keys())
        if row < len(keys):
            del self._config["textures"][keys[row]]
            self._refresh()
            self.changed.emit()

    def add_from_image_path(self, path: str):
        """外部调用: 从文件树选中的图片添加纹理"""
        if self._config:
            self._add_from_path(path)


# ==================== 主窗口 ====================

class BackgroundEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config: dict = self._new_config()
        self.current_file: Optional[str] = None

        self._setup_ui()
        self._setup_menu()
        self._apply_theme()
        self._connect_signals()

        self.setWindowTitle("弹幕背景编辑器 v2 — PySTG")
        self.setMinimumSize(1300, 850)
        self.resize(1500, 950)

        # 防抖刷新
        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)

        # 文件变更监视
        self._file_watcher = QFileSystemWatcher()
        self._file_watcher.fileChanged.connect(self._on_file_changed)

    @staticmethod
    def _new_config() -> dict:
        return {
            "name": "新背景", "description": "",
            "textures": {},
            "camera": {
                "eye": [0, 0, 1], "at": [0, 0, 0], "up": [0, 1, 0],
                "fovy": 0.8, "z_near": 0.1, "z_far": 10.0
            },
            "fog": {
                "enabled": False, "color": [0, 0, 0, 255],
                "start": 0, "end": 10
            },
            "scroll": {"base_speed": 0.003, "direction": [0, 1]},
            "layers": []
        }

    # ---------- UI 构建 ----------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        ml = QHBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        ml.addWidget(splitter)

        self.file_tree = FileTreePanel()
        splitter.addWidget(self.file_tree)
        splitter.addWidget(self._build_center())
        splitter.addWidget(self._build_right())
        splitter.setSizes([270, 450, 380])

        self.statusBar().showMessage(
            "就绪 — 点击左侧场景配置加载背景")

    def _build_center(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(5, 5, 5, 5)
        title = QLabel("背景预览")
        title.setStyleSheet(
            "font-size: 12pt; font-weight: bold; color: #ddd;")
        l.addWidget(title)
        self.preview = BackgroundPreview()
        l.addWidget(self.preview)
        ctrl = QHBoxLayout()
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.clicked.connect(self._toggle_play)
        ctrl.addWidget(self.play_btn)
        rst = QPushButton("⏹ 重置")
        rst.clicked.connect(self.preview.reset_scroll)
        ctrl.addWidget(rst)
        l.addLayout(ctrl)
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(5, 5, 5, 5)

        info_g = QGroupBox("背景信息")
        il = QFormLayout(info_g)
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_info_changed)
        il.addRow("名称:", self.name_edit)
        self.desc_edit = QLineEdit()
        self.desc_edit.textChanged.connect(self._on_info_changed)
        il.addRow("描述:", self.desc_edit)
        l.addWidget(info_g)

        tabs = QTabWidget()
        self.layer_editor = LayerEditorPanel()
        tabs.addTab(self.layer_editor, "图层")
        self.camera_editor = CameraEditorPanel()
        tabs.addTab(self.camera_editor, "摄像机")
        self.fog_editor = FogEditorPanel()
        tabs.addTab(self.fog_editor, "雾效")
        self.scroll_editor = ScrollEditorPanel()
        tabs.addTab(self.scroll_editor, "滚动")
        self.texture_panel = TexturePanel()
        tabs.addTab(self.texture_panel, "纹理")
        l.addWidget(tabs)

        bl = QHBoxLayout()
        save_btn = QPushButton("💾 保存")
        save_btn.setStyleSheet("padding: 8px; background-color: #4CAF50;")
        save_btn.clicked.connect(self._save)
        bl.addWidget(save_btn)
        sa_btn = QPushButton("另存为...")
        sa_btn.clicked.connect(self._save_as)
        bl.addWidget(sa_btn)
        exp_btn = QPushButton("📋 导出场景代码")
        exp_btn.clicked.connect(self._export_scene_code)
        bl.addWidget(exp_btn)
        l.addLayout(bl)
        return w

    def _setup_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("文件(&F)")
        for label, shortcut, slot in [
            ("新建", "Ctrl+N", self._do_new),
            ("打开...", "Ctrl+O", self._do_open),
            ("保存", "Ctrl+S", self._save),
        ]:
            a = QAction(label, self)
            a.setShortcut(shortcut)
            a.triggered.connect(slot)
            fm.addAction(a)
        fm.addSeparator()
        ea = QAction("退出", self)
        ea.triggered.connect(self.close)
        fm.addAction(ea)

    def _connect_signals(self):
        self.file_tree.config_selected.connect(self._load_config)
        self.file_tree.image_selected.connect(
            self.texture_panel.add_from_image_path)
        self.layer_editor.changed.connect(self._schedule_refresh)
        self.camera_editor.changed.connect(self._on_camera_changed)
        self.fog_editor.changed.connect(self._schedule_refresh)
        self.scroll_editor.changed.connect(self._schedule_refresh)
        self.texture_panel.changed.connect(self._on_textures_changed)

    # ---------- 刷新逻辑 ----------

    def _schedule_refresh(self):
        self._refresh_timer.start(50)

    def _do_refresh(self):
        self.preview.set_config(self.config)

    def _on_camera_changed(self):
        self.preview.invalidate_mvp()
        self._schedule_refresh()

    def _on_textures_changed(self):
        self.layer_editor._refresh_texture_combo()
        self._schedule_refresh()

    def _on_info_changed(self):
        self.config["name"] = self.name_edit.text()
        self.config["description"] = self.desc_edit.text()

    # ---------- 文件操作 ----------

    def _load_config(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.current_file = path

            watched = self._file_watcher.files()
            if watched:
                self._file_watcher.removePaths(watched)
            self._file_watcher.addPath(path)

            self._populate_ui()
            self.preview.set_config(self.config)

            name = Path(path).stem
            self.statusBar().showMessage(f"已加载: {name}  ({path})")
            self.setWindowTitle(f"弹幕背景编辑器 v2 — {name}")
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))

    def _populate_ui(self):
        self.name_edit.blockSignals(True)
        self.desc_edit.blockSignals(True)
        self.name_edit.setText(self.config.get("name", ""))
        self.desc_edit.setText(self.config.get("description", ""))
        self.name_edit.blockSignals(False)
        self.desc_edit.blockSignals(False)
        self.layer_editor.set_config(self.config)
        self.camera_editor.set_config(self.config)
        self.fog_editor.set_config(self.config)
        self.scroll_editor.set_config(self.config)
        self.texture_panel.set_config(self.config)

    def _on_file_changed(self, path):
        if path == self.current_file and os.path.exists(path):
            QTimer.singleShot(300, lambda: self._load_config(path))

    def _do_new(self):
        self.config = self._new_config()
        self.current_file = None
        self._populate_ui()
        self.preview.set_config(self.config)
        self.setWindowTitle("弹幕背景编辑器 v2 — 新建")
        self.statusBar().showMessage("已新建空白配置")

    def _do_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开背景配置", str(BG_ROOT), "JSON (*.json)")
        if path:
            self._load_config(path)

    def _save(self):
        if self.current_file:
            self._write(self.current_file)
        else:
            self._save_as()

    def _save_as(self):
        default = self.config.get("name", "background") + ".json"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存背景配置", str(BG_ROOT / default), "JSON (*.json)")
        if path:
            self._write(path)
            self.current_file = path
            watched = self._file_watcher.files()
            if watched:
                self._file_watcher.removePaths(watched)
            self._file_watcher.addPath(path)
            self.file_tree.refresh_tree()

    def _write(self, path: str):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            watched = self._file_watcher.files()
            if path in (watched or []):
                self._file_watcher.removePath(path)
            atomic_write_json(path, self.config)
            self._file_watcher.addPath(path)
            self.statusBar().showMessage(f"已保存: {path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # ---------- 动画 ----------

    def _toggle_play(self):
        if self.preview.animating:
            self.preview.stop_animation()
            self.play_btn.setText("▶ 播放")
        else:
            self.preview.set_config(self.config)
            self.preview.start_animation()
            self.play_btn.setText("⏸ 暂停")

    # ---------- 场景代码导出 ----------

    def _export_scene_code(self):
        name = self.config.get("name", "background")
        available = sorted(
            [f.stem for f in BG_ROOT.glob("*.json") if _is_scene_config_path(f)]
        ) if BG_ROOT.exists() else []
        code = (
            f'# 在关卡脚本中使用此背景场景:\n'
            f'from src.game.background_render.scene import BackgroundScene\n\n'
            f'# 加载并应用背景\n'
            f'scene = BackgroundScene.load("{name}")\n'
            f'bg = scene.apply(background_renderer)\n\n'
            f'# 所有可用场景: {available}\n'
            f'# scenes = BackgroundScene.list_all()\n'
        )
        QMessageBox.information(self, "场景调用代码", code)

    # ---------- 主题 ----------

    def _apply_theme(self):
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
                color: #ddd;
            }
            QPushButton:hover { background-color: #505050; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
                color: #fff;
            }
            QListWidget, QTreeWidget {
                background-color: #1e1e1e;
                border: 1px solid #3d3d3d;
                color: #ddd;
            }
            QListWidget::item:selected, QTreeWidget::item:selected {
                background-color: #007acc;
            }
            QTabWidget::pane { border: 1px solid #3d3d3d; }
            QTabBar::tab {
                background-color: #1e1e1e;
                color: #aaa;
                padding: 6px 12px;
                border: 1px solid #3d3d3d;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #2b2b2b;
                color: #fff;
            }
            QScrollArea { border: none; }
            QCheckBox { color: #ddd; }
            QHeaderView::section {
                background-color: #2b2b2b;
                color: #aaa;
                border: 1px solid #3d3d3d;
                padding: 3px;
            }
        """)


# ==================== 入口 ====================

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = BackgroundEditor()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
