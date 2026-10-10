"""Inspector fields derived from public DSL constructor signatures."""

from __future__ import annotations

import ast
import inspect
import json
import math
import types
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from src.authoring import dsl
from src.authoring.program import (
    Expr,
    Parameter,
    ProgramError,
    Ref,
    find_node,
    numeric_field_range,
    parse_author_value,
    reference_kinds_for_field,
)
from src.qt_compat.QtCore import QPointF, QRect, QRectF, QStringListModel, Qt, QTimer, Signal
from src.qt_compat.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from src.qt_compat.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .session import EditorSession
from .node_palette import entry_for_kind
from .sidebars import RESOURCE_MIME


_EXPR_TOGGLE_TIP = "当前为常量。点击改用表达式，例如 player_x。"


@dataclass(frozen=True)
class _FieldCommit:
    unit_id: str | None
    uid: str | None
    callback: Any

    def __call__(self, value):
        self.callback(value)

_GROUP_ORDER = (
    "basic",
    "emission",
    "position",
    "motion",
    "appearance",
    "sound",
    "lifecycle",
    "advanced",
)
_GROUP_LABELS = {
    "common": "常用参数",
    "basic": "基础",
    "position": "位置",
    "emission": "发射形状",
    "motion": "运动",
    "appearance": "外观",
    "sound": "声音",
    "lifecycle": "生命周期",
    "advanced": "高级",
}
_FIELD_LABELS = {
    "name": "名称", "title": "标题", "subtitle": "副标题",
    "frames": "等待帧数", "frame": "目标帧", "count": "数量",
    "condition": "条件", "iterable": "迭代对象", "target": "目标变量",
    "value": "值", "arguments": "位置参数",
    "keywords": "关键字参数", "function": "函数", "task": "任务",
    "wave_class": "波次", "boss_def": "Boss", "enemy_class": "敌机",
    "is_midboss": "中途 Boss", "x": "横坐标 X", "y": "纵坐标 Y",
    "dx": "水平位移 ΔX", "dy": "垂直位移 ΔY", "duration": "持续帧数",
    "angle": "角度", "start_angle": "起始角", "center_angle": "中心角",
    "arc_angle": "扇形角度", "offset_angle": "瞄准偏移角",
    "angle_offset": "角度偏移", "orbit_radius": "轨道半径",
    "theta": "轨道角", "speed": "速度", "accel": "加速度",
    "angle_accel": "角加速度", "friction": "阻尼", "time_scale": "时间倍率",
    "bounce_x": "水平反弹", "bounce_y": "垂直反弹", "spin": "自转速度",
    "radial_speed": "径向速度", "angular_velocity": "轨道角速度",
    "curve_type": "曲线类型", "curve_params": "曲线参数",
    "bullet_type": "弹型", "color": "颜色", "render_angle": "渲染角度",
    "render_scale": "渲染缩放", "collision_radius": "碰撞半径",
    "render_mode": "渲染模式", "sprite": "精灵资源", "texture": "纹理资源",
    "texture_id": "纹理标识", "animations": "动画映射",
    "width": "宽度", "length": "长度", "l1": "前段长度",
    "l2": "中段长度", "l3": "后段长度", "laser": "激光对象",
    "bgm": "关卡 BGM", "boss_bgm": "Boss BGM", "background": "背景资源",
    "dialogue_list": "对话资源", "play_sound": "播放音效", "volume": "音量",
    "hp": "生命值", "score": "击破分数", "bonus": "符卡奖励",
    "time_limit": "时间限制", "max_lifetime": "最大存在时间",
    "hitbox_radius": "受击半径", "on_time": "启动时间", "off_time": "消隐时间",
    "initial_delay_frames": "首次延迟", "min_interval": "最小间隔",
    "sample_rate": "采样频率", "clear_bullets_on_death": "死亡时清弹",
    "is_survival": "生存符", "is_timeout": "超时符", "drops": "掉落物",
    "tag": "标签", "source": "Python 代码", "node": "控制目标",
    "head": "列表头", "to_items": "转换为道具", "wait": "等待完成",
    "practice_unlock": "练习模式解锁", "stages": "关卡顺序",
    "start_stage": "开始关卡", "phases": "Boss 阶段", "assign": "保存返回值到",
}
_FIELD_UNITS = {
    "frames": "帧", "frame": "帧", "duration": "帧", "time_limit": "秒",
    "initial_delay_frames": "帧", "min_interval": "帧", "on_time": "帧",
    "off_time": "帧", "x": "场地坐标", "y": "场地坐标",
    "dx": "场地坐标", "dy": "场地坐标", "angle": "度",
    "start_angle": "度", "center_angle": "度", "arc_angle": "度",
    "offset_angle": "度", "angle_offset": "度", "theta": "度",
    "speed": "速度单位", "accel": "速度单位/秒", "angle_accel": "度/秒²",
    "spin": "度/秒", "angular_velocity": "度/秒",
}
_FIRE_KINDS = frozenset(
    {"Fire", "FireCircle", "FireArc", "FireAtPlayer", "FirePolar", "FireOrbit"}
)
_COMMON_FIRE_FIELDS = (
    "count", "speed", "angle", "start_angle", "center_angle", "arc_angle",
    "offset_angle", "angle_offset", "theta", "bullet_type", "color",
)

# Presentation only: the full constructor-derived fields remain editable below
# the fold, including values already set in source.  Required inputs are never
# hidden, regardless of their name.
_DETAIL_FIELDS = frozenset({
    "accel", "angle_accel", "friction", "time_scale", "bounce_x", "bounce_y",
    "spin", "radial_speed", "angular_velocity", "curve_type", "curve_params",
    "render_angle", "render_scale", "collision_radius", "render_mode",
    "texture_id", "animations", "l1", "l2", "l3", "tag", "wait", "assign",
    "arguments", "keywords", "max_lifetime", "hitbox_radius", "score", "bonus",
    "initial_delay_frames", "min_interval", "sample_rate", "clear_bullets_on_death",
    "is_survival", "is_timeout", "practice_unlock", "drops",
})
_UNIT_LABELS = {
    "Project": "工程", "Stage": "关卡", "Wave": "波次", "Enemy": "敌人",
    "Boss": "Boss", "Spell": "符卡", "NonSpell": "非符", "Task": "任务",
    "Function": "函数",
}

_POINT_NODE_KINDS = frozenset({
    "Fire", "FireCircle", "FireArc", "FireAtPlayer", "SpawnEnemy",
    "MoveTo", "SetPosition", "CreateLaser", "CreateBentLaser",
})


def _coordinate_spec_kind(node) -> str | None:
    """Which coordinate preview mode applies to this node, if any."""

    if node is None:
        return None
    if node.kind in {"MoveLinear"} and ("dx" in node.arguments or "dy" in node.arguments):
        return "delta"
    if node.kind in _POINT_NODE_KINDS and ("x" in node.arguments or "y" in node.arguments):
        x, y = node.arguments.get("x"), node.arguments.get("y")
        if isinstance(x, Expr) or isinstance(y, Expr):
            return "hint"
        return "point"
    if node.kind in {"Fire", "FireCircle", "FireArc", "FireAtPlayer"}:
        # x/y omitted entirely means the runtime uses the actor position.
        return "hint"
    return None


_UNSET = object()


def _values_equal(candidate: Any, original: Any) -> bool:
    """Type-aware equality so 60 never suppresses a float 60.0 edit."""

    if type(candidate) is not type(original):
        return False
    try:
        return bool(candidate == original)
    except Exception:
        return False


def _range_tooltip(owner_kind, name, annotation, value) -> str:
    kind = _field_type(annotation, value) if annotation is not None else None
    type_text = {int: "int", float: "float", str: "字符串", bool: "bool"}.get(kind)
    if type_text is None:
        type_text = "常量 | 表达式"
    lines = [str(name), f"类型: {type_text}"]
    if (
        value is not inspect.Parameter.empty
        and value is not None
        and not isinstance(value, Expr)
    ):
        default = _runtime_default_label(name) if value is dsl.RUNTIME_DEFAULT else repr(value)
        lines.append(f"默认: {default}"[:80])
    bounds = _field_range(owner_kind or "", name or "")
    if bounds is not None:
        minimum, maximum = bounds
        if maximum is None:
            lines.append(f"范围: ≥ {minimum}")
        elif minimum is None:
            lines.append(f"范围: ≤ {maximum}")
        else:
            lines.append(f"范围: {minimum} ~ {maximum}")
    return chr(10).join(lines)


def _field_range(
    owner_kind: str, name: str
) -> tuple[int | float | None, int | float | None] | None:
    return numeric_field_range(owner_kind, name)


_Y_ASPECT = 384.0 / 448.0  # renderer.py:211 宽高比校正（x 保持 ±1，y × 384/448）


def marker_point(
    x: float, y: float, width: float, height: float
) -> tuple[float, float]:
    """Map authoring coordinates to pixels on a full play-field rectangle."""

    return (x + 1) / 2 * width, (1 - y * _Y_ASPECT) / 2 * height


def _field_group(owner_kind: str, name: str) -> str:
    if name in {"x", "y", "dx", "dy"}:
        return "position"
    if owner_kind in _FIRE_KINDS and name in {
        "count", "angle", "start_angle", "center_angle", "arc_angle",
        "offset_angle", "angle_offset", "orbit_radius", "theta",
    }:
        return "emission"
    if name in {
        "speed", "accel", "angle_accel", "friction", "time_scale",
        "bounce_x", "bounce_y", "spin", "radial_speed", "angular_velocity",
        "duration", "curve_type", "curve_params",
    }:
        return "motion"
    if name in {
        "bullet_type", "color", "render_angle", "render_scale",
        "collision_radius", "render_mode", "sprite", "texture", "texture_id",
        "animations", "width", "length", "l1", "l2", "l3",
    }:
        return "appearance"
    if name in {"bgm", "boss_bgm", "play_sound", "volume"} or (
        owner_kind in {"PlayBGM", "PlaySE"} and name == "name"
    ):
        return "sound"
    if name in {
        "hp", "score", "bonus", "time_limit", "max_lifetime", "hitbox_radius",
        "on_time", "off_time", "initial_delay_frames", "min_interval",
        "sample_rate", "clear_bullets_on_death", "is_survival", "is_timeout",
        "drops",
    }:
        return "lifecycle"
    if name in {
        "tag", "source", "node", "head", "to_items", "wait", "assign",
        "arguments", "keywords", "laser",
    }:
        return "advanced"
    return "basic"


def _field_hint(owner_kind: str, name: str, default: Any, unit_kind: str | None = None) -> str:
    parts: list[str] = []
    unit = _FIELD_UNITS.get(name)
    if unit:
        parts.append(f"单位：{unit}")
    if default is not inspect.Parameter.empty:
        text = _runtime_default_label(name, unit_kind) if default is dsl.RUNTIME_DEFAULT else repr(default)
        parts.append(f"默认：{text[:64]}")
    bounds = _field_range(owner_kind, name)
    if bounds is not None:
        minimum, maximum = bounds
        if maximum is None:
            parts.append(f"范围：≥ {minimum}")
        elif minimum is None:
            parts.append(f"范围：≤ {maximum}")
        else:
            parts.append(f"范围：{minimum} ～ {maximum}")
    return "  ·  ".join(parts)


def _runtime_default_label(name: str, unit_kind: str | None = None) -> str:
    if name in {"x", "y"}:
        return "必须填写坐标" if unit_kind == "Wave" else "使用发射者位置"
    return "沿用默认值"


@dataclass(frozen=True)
class BulletSpriteChoice:
    bullet_type: str
    color: str
    sprite_id: str
    image_path: Path | None = None
    rect: tuple[int, int, int, int] | None = None


class BulletAssetCatalog:
    """Read aliases and atlas rectangles without importing the renderer."""

    def __init__(self, project_root: Path | None) -> None:
        self.project_root = project_root.resolve() if project_root is not None else None
        self.mapping: dict[str, dict[str, str]] = {}
        self._sprites: dict[str, tuple[Path, tuple[int, int, int, int]]] = {}
        self._icons: dict[tuple[str, str], QIcon] = {}
        if self.project_root is not None:
            self._load()

    def _load(self) -> None:
        assets = self.project_root / "assets"
        alias_path = assets / "bullet_aliases.json"
        try:
            payload = json.loads(alias_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        mapping = payload.get("mapping", {}) if isinstance(payload, dict) else {}
        if isinstance(mapping, dict):
            self.mapping = {
                str(kind): {
                    str(color): str(sprite)
                    for color, sprite in colors.items()
                    if isinstance(color, str) and isinstance(sprite, str)
                }
                for kind, colors in mapping.items()
                if isinstance(kind, str) and isinstance(colors, dict)
            }
        image_root = assets / "images"
        if not image_root.is_dir():
            return
        for config in sorted(image_root.rglob("*.json")):
            try:
                atlas = json.loads(config.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if not isinstance(atlas, dict) or not isinstance(atlas.get("sprites"), dict):
                continue
            image_name = atlas.get("__image_filename")
            if not isinstance(image_name, str):
                continue
            image_path = (config.parent / image_name).resolve()
            if not image_path.is_file():
                continue
            for sprite_id, spec in atlas["sprites"].items():
                rect = spec.get("rect") if isinstance(spec, dict) else None
                if (
                    isinstance(sprite_id, str)
                    and isinstance(rect, list)
                    and len(rect) == 4
                    and all(isinstance(value, int) for value in rect)
                ):
                    self._sprites.setdefault(sprite_id, (image_path, tuple(rect)))

    @property
    def bullet_types(self) -> tuple[str, ...]:
        return tuple(sorted(self.mapping))

    def colors(self, bullet_type: str) -> tuple[str, ...]:
        return tuple(sorted(self.mapping.get(bullet_type, {})))

    def choice(self, bullet_type: str, color: str) -> BulletSpriteChoice | None:
        sprite_id = self.mapping.get(bullet_type, {}).get(color)
        if sprite_id is None:
            return None
        source = self._sprites.get(sprite_id)
        return BulletSpriteChoice(
            bullet_type,
            color,
            sprite_id,
            source[0] if source else None,
            source[1] if source else None,
        )

    def icon(self, bullet_type: str, color: str) -> QIcon:
        key = (bullet_type, color)
        cached = self._icons.get(key)
        if cached is not None:
            return cached
        choice = self.choice(bullet_type, color)
        icon = QIcon()
        if choice is not None and choice.image_path is not None and choice.rect is not None:
            source = QPixmap(str(choice.image_path))
            if not source.isNull():
                x, y, width, height = choice.rect
                pixmap = source.copy(QRect(x, y, width, height)).scaled(
                    32,
                    32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                icon = QIcon(pixmap)
        self._icons[key] = icon
        return icon


class BulletPreview(QWidget):
    """Current alias/atlas selection, not a second gameplay renderer."""

    def __init__(
        self,
        catalog: BulletAssetCatalog,
        bullet_type: str,
        color: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("bullet_selection_preview")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        image = QLabel(self)
        image.setObjectName("bullet_selection_thumbnail")
        image.setFixedSize(42, 42)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = catalog.icon(bullet_type, color)
        if not icon.isNull():
            image.setPixmap(icon.pixmap(36, 36))
        else:
            image.setText("？")
        layout.addWidget(image)
        text = QLabel(self)
        text.setObjectName("bullet_selection_text")
        text.setWordWrap(True)
        choice = catalog.choice(bullet_type, color)
        if choice is None:
            text.setText(f"{bullet_type} × {color}\n当前组合没有弹型别名")
            text.setStyleSheet("color: #f85149;")
        else:
            text.setText(f"{bullet_type} × {color}\n精灵：{choice.sprite_id}")
            text.setStyleSheet("color: #8b949e;")
        layout.addWidget(text, 1)


class ResourceLineEdit(QLineEdit):
    resource_dropped = Signal(str)

    def __init__(self, accepts_resource, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accepts_resource = accepts_resource
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        uri = _resource_uri(event.mimeData())
        if uri and self._accepts_resource(uri):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        uri = _resource_uri(event.mimeData())
        if uri and self.drop_resource(uri):
            event.acceptProposedAction()
        else:
            event.ignore()

    def drop_resource(self, uri: str) -> bool:
        if not self._accepts_resource(uri):
            return False
        self.resource_dropped.emit(uri)
        return True


class LiteralTextEdit(QPlainTextEdit):
    """Light structured editor for list/dict literal values."""

    commit_requested = Signal()

    def focusOutEvent(self, event) -> None:
        if self.isVisible():
            self.commit_requested.emit()
        super().focusOutEvent(event)


class CoordinatePreview(QWidget):
    """Miniature of the visible play field for the node's edited point.

    Authoring coordinates are x ∈ [-1, 1] (right positive) and y upward with
    (0, 0) at the field centre; the shaders apply the 384/448 aspect
    correction, which this preview reproduces faithfully.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("coordinate_preview")
        self.setMinimumHeight(120)
        self._reader = lambda: None  # returns a paint spec each repaint

    def configure(self, reader) -> None:
        self._reader = reader
        self.update()

    def paintEvent(self, _event) -> None:
        from src.qt_compat.QtGui import QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#10141a"))
        spec = self._reader()
        border = QRectF(8.0, 6.0, self.width() - 16, self.height() - 12)
        painter.setPen(QPen(QColor("#3a414e"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(border, 4, 4)
        center = QPointF(border.center())
        painter.setPen(QPen(QColor("#262c34"), 1))
        painter.drawLine(
            QPointF(border.left(), center.y()),
            QPointF(border.right(), center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), border.top()),
            QPointF(center.x(), border.bottom()),
        )
        if spec is None or spec[0] == "none":
            painter.setPen(QColor("#6e7681"))
            painter.drawText(border, Qt.AlignmentFlag.AlignCenter, "无坐标参数")
            painter.end()
            return
        if spec[0] == "hint":
            painter.setPen(QColor("#f0883e"))
            painter.drawText(border, Qt.AlignmentFlag.AlignCenter, spec[1])
            painter.end()
            return
        if spec[0] == "delta":
            _kind, dx, dy = spec
            width = border.width() / 2
            height = border.height() / 2
            target = QPointF(
                center.x() + dx / 2 * width,
                center.y() - dy * _Y_ASPECT / 2 * height,
            )
            painter.setPen(QPen(QColor("#3fb950"), 2))
            painter.drawLine(center, target)
            painter.setBrush(QColor("#3fb950"))
            painter.drawEllipse(target, 4, 4)
            painter.setPen(QColor("#c9d1d9"))
            painter.drawText(
                QPointF(target.x() + 6, target.y() - 4), f"Δ({dx:g}, {dy:g})"
            )
            painter.end()
            return
        _kind, x, y = spec
        off_screen = abs(x) > 1.5 or abs(y) > 1.5
        u, v = marker_point(x, y, border.width(), border.height())
        marker = QPointF(border.left() + u, border.top() + v)
        inside = border.adjusted(6, 6, -6, -6).contains(marker)
        color = QColor("#f85149") if off_screen or not inside else QColor("#58a6e7")
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        radius = 6.0
        painter.drawEllipse(marker, radius, radius)
        painter.drawLine(
            QPointF(marker.x() - radius - 3, marker.y()),
            QPointF(marker.x() + radius + 3, marker.y()),
        )
        painter.drawLine(
            QPointF(marker.x(), marker.y() - radius - 3),
            QPointF(marker.x(), marker.y() + radius + 3),
        )
        painter.setPen(QColor(color))
        text = f"({x:g}, {y:g})" + ("（屏外）" if off_screen else "")
        painter.drawText(
            QPointF(min(marker.x() + 8, border.right() - 70), max(marker.y() - 6, border.top() + 12)),
            text,
        )
        painter.end()


class EmissionPreview(QWidget):
    """Parameter geometry for fire shapes; it never simulates gameplay."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("emission_preview")
        self.setMinimumHeight(120)
        self._reader = lambda: None

    def configure(self, reader) -> None:
        self._reader = reader
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#10141a"))
        border = QRectF(8.0, 6.0, self.width() - 16, self.height() - 12)
        painter.setPen(QPen(QColor("#3a414e"), 1))
        painter.drawRoundedRect(border, 4, 4)
        spec = self._reader()
        if spec is None or spec[0] == "hint":
            painter.setPen(QColor("#f0883e"))
            painter.drawText(
                border,
                Qt.AlignmentFlag.AlignCenter,
                spec[1] if spec else "无可预览的发射参数",
            )
            painter.end()
            return
        kind, values = spec
        center = QPointF(border.center())
        radius = min(border.width(), border.height()) * 0.36
        painter.setPen(QPen(QColor("#58a6e7"), 1.6))
        painter.setBrush(QColor("#58a6e7"))
        painter.drawEllipse(center, 3.0, 3.0)

        def ray(angle: float, length: float = radius) -> None:
            radians = math.radians(angle)
            end = QPointF(
                center.x() + math.cos(radians) * length,
                center.y() - math.sin(radians) * length,
            )
            painter.drawLine(center, end)
            painter.drawEllipse(end, 2.5, 2.5)

        if kind == "circle":
            count, start = values
            for index in range(max(1, min(int(count), 24))):
                ray(start + index * 360.0 / max(1, int(count)))
        elif kind == "arc":
            count, center_angle, arc = values
            count = max(1, min(int(count), 24))
            for index in range(count):
                ratio = 0.5 if count == 1 else index / (count - 1)
                ray(center_angle - arc / 2 + arc * ratio)
        elif kind == "orbit":
            orbit_radius, theta, angular_velocity = values
            display_radius = max(10.0, min(radius, abs(orbit_radius) * radius * 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#a371f7"), 1.4, Qt.PenStyle.DashLine))
            painter.drawEllipse(center, display_radius, display_radius)
            radians = math.radians(theta)
            point = QPointF(
                center.x() + math.cos(radians) * display_radius,
                center.y() - math.sin(radians) * display_radius,
            )
            painter.setBrush(QColor("#a371f7"))
            painter.drawEllipse(point, 4.0, 4.0)
            painter.setPen(QColor("#8b949e"))
            painter.drawText(border.adjusted(6, 6, -6, -6), f"ω {angular_velocity:g}°/帧")
        else:
            ray(values[0])
            if kind == "aimed":
                painter.setPen(QPen(QColor("#f0883e"), 1, Qt.PenStyle.DashLine))
                painter.drawText(
                    border.adjusted(6, 6, -6, -6),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                    "朝向玩家",
                )
        painter.end()


class ParameterTable(QWidget):
    """Small explicit table for Task/Function signature parameters."""

    commit_requested = Signal(object)
    error = Signal(str)

    def __init__(self, values: tuple[Parameter, ...], editable: bool, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3, self)
        self.table.setObjectName("parameter_table")
        self.table.setHorizontalHeaderLabels(["名称", "类型", "默认值（留空=必填）"])
        for parameter in values:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(parameter.name))
            self.table.setItem(row, 1, QTableWidgetItem(parameter.annotation))
            default = "" if not parameter.has_default else repr(parameter.default)
            self.table.setItem(row, 2, QTableWidgetItem(default))
        self.table.setEnabled(editable)
        self.table.setMinimumHeight(110)
        layout.addWidget(self.table)
        controls = QHBoxLayout()
        add = QToolButton(self)
        add.setText("＋")
        remove = QToolButton(self)
        remove.setText("－")
        apply = QToolButton(self)
        apply.setText("应用")
        for button in (add, remove, apply):
            button.setEnabled(editable)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        add.clicked.connect(self._add_row)
        remove.clicked.connect(self._remove_row)
        apply.clicked.connect(self._apply)

    def _add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(f"arg{row + 1}"))
        self.table.setItem(row, 1, QTableWidgetItem("Any"))
        self.table.setItem(row, 2, QTableWidgetItem(""))
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))

    def _remove_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def parameters(self) -> tuple[Parameter, ...]:
        values: list[Parameter] = []
        for row in range(self.table.rowCount()):
            name = (self.table.item(row, 0).text() if self.table.item(row, 0) else "").strip()
            annotation = (
                self.table.item(row, 1).text() if self.table.item(row, 1) else "Any"
            ).strip() or "Any"
            default = (
                self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            ).strip()
            values.append(
                Parameter(name, annotation)
                if not default
                else Parameter(name, annotation, _parse_literal(default))
            )
        return tuple(values)

    def _apply(self) -> None:
        try:
            values = self.parameters()
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.error.emit("")
        self.commit_requested.emit(values)


class _ScrollSafeSpinBox(QSpinBox):
    """Let the Inspector scroll without accidentally changing a number."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class InspectorPanel(QWidget):
    """Use constructor annotations as the only field schema."""

    reference_open_requested = Signal(str)

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector_panel")
        self.session = session
        self.form = QFormLayout(self)
        self.form.setContentsMargins(8, 8, 8, 8)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.form.setHorizontalSpacing(8)
        self.form.setVerticalSpacing(5)
        self._suggested_widget: QWidget | None = None
        self._coordinate_preview: CoordinatePreview | None = None
        self._emission_preview: EmissionPreview | None = None
        self._bullet_catalog_root: Path | None = None
        self._bullet_catalog = BulletAssetCatalog(None)
        self._commit_depth = 0
        self._rebuild_scheduled = False
        self._display_key = None
        self._detail_rows: list[int] = []
        self._detail_selection = None
        self._details_open = False
        self._more_button: QToolButton | None = None
        self._preview_button: QToolButton | None = None
        self._preview_rows: list[int] = []
        self._previews_open = False
        self.session.selection_changed.connect(self.refresh)
        self.session.project_changed.connect(self.refresh)
        self.session.program_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the field rows for the current selection.

        A commit that succeeds rebuilds this panel; deferring the rebuild until
        the widget's own signal dispatch has unwound is what keeps typing from
        crashing Qt (deleting the sender mid-signal is use-after-free).
        """

        if self._commit_depth > 0:
            if not self._rebuild_scheduled:
                self._rebuild_scheduled = True
                QTimer.singleShot(0, self._deferred_refresh)
            return
        self._do_refresh()

    def _deferred_refresh(self) -> None:
        self._rebuild_scheduled = False
        if self._commit_depth == 0:
            self._do_refresh()

    def _do_refresh(self) -> None:
        key = self._display_state()
        if key == self._display_key:
            return
        self._display_key = key
        selection = (self.session.current_unit_id, self.session.current_node_uid)
        if selection != self._detail_selection:
            self._detail_selection = selection
            self._details_open = False
            self._previews_open = False
        while self.form.rowCount():
            self.form.removeRow(0)
        self._detail_rows.clear()
        self._more_button = None
        self._preview_button = None
        self._preview_rows.clear()
        self._suggested_widget = None
        self._coordinate_preview = None
        self._emission_preview = None
        node = self.session.current_node
        unit = self.session.current_unit
        self._ensure_bullet_catalog()
        if node is not None:
            constructor = dsl.NODE_CONSTRUCTORS.get(node.kind)
            annotations = get_type_hints(constructor) if constructor is not None else {}
            defaults = _constructor_defaults(constructor)
            label = (
                {"Branch": "并行分支", "TemplateCall": "弹幕模板"}[node.kind]
                if node.kind in {"Branch", "TemplateCall"}
                else entry_for_kind(node.kind).label
            )
            header = QLabel(f"属性 · {label}", self)
            header.setObjectName("inspector_title")
            header.setToolTip(f"Python API：{node.kind}\n节点标识：{node.uid}")
            self.form.addRow(header)
            suggested = self._suggested_field_name(node, constructor)
            fields = _node_fields(node, constructor)
            details = [(name, value) for name, value in fields if self._is_detail(name, defaults)]
            common = [
                (name, value)
                for name in _COMMON_FIRE_FIELDS
                for field, value in fields
                if node.kind in _FIRE_KINDS and field == name
            ]
            if common:
                self._add_section("common")
                self._add_group_fields(
                    node.kind, common, annotations, defaults, suggested,
                    lambda name, value, uid=node.uid: self.session.set_node_argument(uid, name, value),
                )
            common_names = {name for name, _value in common}
            if common:
                self._add_previews(node)
            for group in _GROUP_ORDER:
                grouped = [
                    (name, value)
                    for name, value in fields
                    if name not in common_names
                    and _field_group(node.kind, name) == group
                    and not self._is_detail(name, defaults)
                ]
                if not grouped:
                    continue
                self._add_section(group)
                self._add_group_fields(
                    node.kind, grouped, annotations, defaults, suggested,
                    lambda name, value, uid=node.uid: self.session.set_node_argument(uid, name, value),
                )
            if not common:
                self._add_previews(node)
            self._add_details(
                node.kind, details, annotations, defaults,
                lambda name, value: self.session.set_node_argument(node.uid, name, value),
            )
            return
        if unit is not None:
            constructor = dsl.UNIT_CONSTRUCTORS[unit.kind]
            annotations = get_type_hints(constructor)
            defaults = _constructor_defaults(constructor)
            header = QLabel(f"属性 · {_UNIT_LABELS[unit.kind]}", self)
            header.setObjectName("inspector_title")
            header.setToolTip(f"Python 类型：{unit.kind}\n内容 ID：{unit.id}")
            self.form.addRow(header)
            self._add_section("basic")
            self._add_field(
                "名称",
                unit.name,
                annotations.get("name", str),
                unit.kind,
                defaults.get("name", inspect.Parameter.empty),
                mark_suggested=False,
                field_name="unit_name",
                commit=lambda value, unit_id=unit.id: self.session.set_unit_field(
                    unit_id, "name", value
                ),
            )
            if "parameters" in inspect.signature(constructor).parameters:
                self._add_parameter_field(unit)
            fields = _unit_fields(unit.metadata, constructor)
            details = [(name, value) for name, value in fields if self._is_detail(name, defaults)]
            for group in _GROUP_ORDER:
                grouped = [
                    (name, value)
                    for name, value in fields
                    if _field_group(unit.kind, name) == group and not self._is_detail(name, defaults)
                ]
                if not grouped:
                    continue
                if group != "basic":
                    self._add_section(group)
                self._add_group_fields(
                    unit.kind, grouped, annotations, defaults, None,
                    lambda name, value, unit_id=unit.id: self.session.set_unit_field(unit_id, name, value),
                )
            self._add_details(
                unit.kind, details, annotations, defaults,
                lambda name, value: self.session.set_unit_field(unit.id, name, value),
            )
            return
        self.form.addRow(QLabel("当前文件不可视化编辑"))

    def _display_state(self):
        """Only selected fields and their available choices affect this panel."""

        unit, node = self.session.current_unit, self.session.current_node
        choices = tuple(
            (item.id, item.kind)
            for item in self.session.program.logical_units()
        ) if self.session.is_open else ()
        root = self.session.project_context.root if self.session.project_context else None
        if node is not None:
            fields = (node.uid, node.kind, node.arguments, node.positional_arguments)
        elif unit is not None:
            fields = (unit.id, unit.kind, unit.name, unit.parameters, unit.metadata)
        else:
            fields = None
        return (fields, self.session.can_edit, choices, root)

    def _ensure_bullet_catalog(self) -> None:
        context = self.session.project_context
        root = context.root.resolve() if context is not None else None
        if root == self._bullet_catalog_root:
            return
        self._bullet_catalog_root = root
        self._bullet_catalog = BulletAssetCatalog(root)

    def _add_section(self, group: str) -> None:
        header = QLabel(_GROUP_LABELS[group], self)
        header.setObjectName(f"inspector_group_{group}")
        header.setStyleSheet(
            "color: #58a6e7; font-weight: 600; padding-top: 4px; "
            "border-bottom: 1px solid #30363d;"
        )
        self.form.addRow(header)

    def _add_group_fields(self, owner_kind, fields, annotations, defaults, suggested, commit) -> None:
        values = dict(fields)
        paired_names: set[str] = set()
        for names in (("x", "y"), ("dx", "dy")):
            if not all(name in values for name in names):
                continue
            pair = QWidget(self)
            pair.setObjectName(f"coordinate_pair_{names[0]}_{names[1]}")
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(8)
            for name in names:
                label, container = self._add_field(
                    name, values[name], annotations.get(name, Any), owner_kind,
                    defaults.get(name, inspect.Parameter.empty),
                    mark_suggested=name == suggested,
                    commit=lambda value, key=name: commit(key, value),
                    add_to_form=False,
                    label_override=name.upper().replace("D", "Δ"),
                )
                coordinate = QWidget(pair)
                coordinate_layout = QHBoxLayout(coordinate)
                coordinate_layout.setContentsMargins(0, 0, 0, 0)
                coordinate_layout.setSpacing(4)
                coordinate_layout.addWidget(label)
                coordinate_layout.addWidget(container, 1)
                pair_layout.addWidget(coordinate, 1)
            self.form.addRow(pair)
            paired_names.update(names)
        for name, value in fields:
            if name in paired_names:
                continue
            self._add_field(
                name, value, annotations.get(name, Any), owner_kind,
                defaults.get(name, inspect.Parameter.empty),
                mark_suggested=name == suggested,
                commit=lambda value, key=name: commit(key, value),
            )

    def _add_previews(self, node) -> None:
        has_coordinate = _coordinate_spec_kind(node) is not None
        has_emission = node.kind in _FIRE_KINDS
        if not has_coordinate and not has_emission:
            return
        button = QToolButton(self)
        button.setObjectName("inspector_preview_toggle")
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setToolTip("参数示意图，不是游戏预览。展开或收起不会修改内容。")
        self._preview_button = button
        self.form.addRow(button)
        first_row = self.form.rowCount()
        if has_emission:
            self._add_bullet_preview(node)
            self._add_emission_preview(node)
        if has_coordinate:
            self._add_coordinate_preview(node)
        self._preview_rows = list(range(first_row, self.form.rowCount()))
        button.toggled.connect(self._set_previews_visible)
        button.setChecked(self._previews_open)
        self._set_previews_visible(self._previews_open)

    def _set_previews_visible(self, visible: bool) -> None:
        self._previews_open = visible
        for row in self._preview_rows:
            self.form.setRowVisible(row, visible)
        if self._preview_button is not None:
            self._preview_button.setText("收起示意图" if visible else "形状与位置示意")
            self._preview_button.setArrowType(
                Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
            )

    @staticmethod
    def _is_detail(name: str, defaults: dict) -> bool:
        return name in _DETAIL_FIELDS and name in defaults

    def _add_details(self, owner_kind, fields, annotations, defaults, commit) -> None:
        if not fields:
            return
        button = QToolButton(self)
        button.setObjectName("inspector_more_parameters")
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setToolTip("展开运动细节、生命周期和其它可选参数。已有参数不会被重置。")
        self._more_button = button
        self.form.addRow(button)
        first_row = self.form.rowCount()
        for group in _GROUP_ORDER:
            grouped = [(name, value) for name, value in fields if _field_group(owner_kind, name) == group]
            if not grouped:
                continue
            self._add_section(group)
            self._add_group_fields(owner_kind, grouped, annotations, defaults, None, commit)
        self._detail_rows = list(range(first_row, self.form.rowCount()))
        button.setProperty("parameter_count", len(fields))
        button.toggled.connect(self._set_details_visible)
        button.setChecked(self._details_open)
        self._set_details_visible(self._details_open)

    def _set_details_visible(self, visible: bool) -> None:
        self._details_open = visible
        for row in self._detail_rows:
            self.form.setRowVisible(row, visible)
        if self._more_button is not None:
            count = self._more_button.property("parameter_count")
            self._more_button.setText("收起更多参数" if visible else f"更多参数（{count} 项）")
            self._more_button.setArrowType(Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow)

    def focus_suggested_field(self) -> None:
        """Focus the field the author most likely wants to change next."""

        widget = self._suggested_widget or self._first_editable_widget()
        if widget is None:
            return
        widget.setFocus(Qt.FocusReason.OtherFocusReason)
        scroll = self.window().findChild(QScrollArea, "inspector_scroll")
        container = self._editor_container(widget)
        if container is not None and scroll is not None:
            scroll.ensureWidgetVisible(container, 8, 8)

    def _first_editable_widget(self) -> QWidget | None:
        for editor in self.findChildren(QLineEdit):
            if editor.isVisible() and not editor.isReadOnly():
                return editor
        for editor in self.findChildren(QComboBox):
            if editor.isVisible():
                return editor
        return None

    def _editor_container(self, widget: QWidget) -> QWidget | None:
        current: QWidget | None = widget
        while current is not None and current.parentWidget() is not self:
            current = current.parentWidget()
        return current

    def _suggested_field_name(self, node, constructor) -> str | None:
        """Prefer common emission parameters, then a field at its default value."""

        if constructor is None:
            return None
        if node.kind in _FIRE_KINDS:
            available = {name for name, _value in _node_fields(node, constructor)}
            for name in ("count", "speed"):
                if name in available:
                    return name
        signature = inspect.signature(constructor)
        for name, value in _node_fields(node, constructor):
            parameter = signature.parameters.get(name)
            if parameter is None or parameter.default is inspect.Parameter.empty:
                continue
            if name in _DETAIL_FIELDS:
                continue
            try:
                if value == parameter.default and type(value) is type(parameter.default):
                    return name
            except Exception:
                continue
        return None

    # -- field construction ---------------------------------------------------

    def _add_field(
        self,
        name: str,
        value: Any,
        annotation: Any,
        owner_kind: str,
        default: Any,
        *,
        mark_suggested: bool,
        commit,
        field_name: str | None = None,
        add_to_form: bool = True,
        label_override: str | None = None,
    ) -> tuple[QLabel, QWidget]:
        commit = _FieldCommit(
            self.session.current_unit_id, self.session.current_node_uid, commit
        )
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        editor = self._editor(value, annotation, owner_kind, name, commit)
        editor.setMinimumWidth(0)
        editor.setSizePolicy(QSizePolicy.Policy.Ignored, editor.sizePolicy().verticalPolicy())
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(editor, 1)
        if self._supports_expr(value, annotation, field_name or name):
            row.addWidget(
                self._expr_toggle(editor, value, annotation, name, commit)
            )
        if isinstance(editor, ResourceLineEdit):
            row.addWidget(self._browse_button(editor, name))
        if isinstance(value, Ref) and isinstance(editor, QComboBox):
            reference_ids = {
                editor.itemText(index): str(editor.itemData(index))
                for index in range(editor.count())
            }
            reference_text = [editor.currentText()]
            editor.currentTextChanged.connect(
                lambda text: reference_text.__setitem__(0, text)
            )
            open_button = QToolButton(container)
            open_button.setText("打开")
            open_button.setObjectName(f"open_reference_{field_name or name}")
            open_button.setToolTip("打开引用内容；返回会保留当前步骤位置")
            def open_reference(_checked=False) -> None:
                target = reference_ids.get(reference_text[0], reference_text[0].strip())
                if target:
                    QTimer.singleShot(0, lambda unit_id=target: self.reference_open_requested.emit(unit_id))
            open_button.clicked.connect(open_reference)
            row.addWidget(open_button)
        layout.addLayout(row)
        unit = self.session.current_unit
        hint = _field_hint(owner_kind, name, default, unit.kind if unit is not None else None)
        if hint:
            tooltip = editor.toolTip()
            editor.setToolTip(f"{tooltip}\n{hint}" if tooltip else hint)
        error_label = QLabel("", container)
        error_label.setStyleSheet("color: #f85149;")
        error_label.setWordWrap(True)
        error_label.setObjectName(f"error_{name}")
        error_label.hide()
        layout.addWidget(error_label)
        editor.setObjectName(f"argument_{field_name or name}")
        editor.setProperty("pystg_annotation", str(annotation))
        editor.setProperty("pystg_field", field_name or name)
        visible_name = label_override or _FIELD_LABELS.get(name, name)
        label = QLabel(visible_name, container)
        label.setObjectName(f"label_{field_name or name}")
        label.setWordWrap(False)
        label.ensurePolished()
        text_width = label.sizeHint().width()
        if add_to_form:
            # QFormLayout otherwise treats a wrapped Chinese label's one-glyph
            # width as its minimum and can turn even "数量" into vertical text.
            short_label = text_width <= 80
            label.setWordWrap(not short_label)
            label.setMinimumWidth(max(58, text_width) if short_label else 58)
            label.setMaximumWidth(80)
            if short_label:
                label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            label.setFixedWidth(text_width)
            label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        tooltip = _range_tooltip(owner_kind, name, annotation, default)
        if hint:
            tooltip += f"\n{hint}"
        if mark_suggested:
            tooltip += "\n建议先调整此项。"
        label.setToolTip(tooltip)
        if mark_suggested:
            label.setStyleSheet("color: #f0883e;")
            self._suggested_widget = self._focus_proxy(editor)
        if add_to_form:
            if isinstance(editor, QPlainTextEdit):
                self.form.addRow(label)
                self.form.addRow(container)
            else:
                self.form.addRow(label, container)
        return label, container

    def _add_bullet_preview(self, node) -> None:
        bullet_type = str(node.arguments.get("bullet_type", "ball_m"))
        color = str(node.arguments.get("color", "red"))
        preview = BulletPreview(
            self._bullet_catalog,
            bullet_type,
            color,
            self,
        )
        self.form.addRow(QLabel("当前弹型", self), preview)

    def _add_coordinate_preview(self, node) -> None:
        """Show a mini play field when the node edits a position-like value."""

        spec_kind = _coordinate_spec_kind(node)
        if spec_kind is None:
            self._coordinate_preview = None
            return
        preview = CoordinatePreview(self)
        preview.setObjectName("coordinate_preview_widget")
        preview.configure(lambda: self._coordinate_spec(node))
        self._coordinate_preview = preview
        labels = {"point": "位置", "delta": "增量", "actor": "位置"}
        self.form.addRow(QLabel(labels.get(spec_kind, "位置"), self), preview)

    def _add_emission_preview(self, node) -> None:
        preview = EmissionPreview(self)
        preview.setObjectName("emission_preview_widget")
        preview.configure(lambda: self._emission_spec(node))
        self._emission_preview = preview
        self.form.addRow(QLabel("形状示意", self), preview)

    def _emission_spec(self, node):
        defaults = _constructor_defaults(dsl.NODE_CONSTRUCTORS.get(node.kind))
        def numeric(name: str, default: float) -> float | None:
            original = node.arguments.get(name, defaults.get(name, default))
            editor = self.findChild(QWidget, f"argument_{name}")
            try:
                value = self._current_value(editor, original) if editor is not None else original
            except ValueError:
                return None
            if isinstance(value, Expr) or isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            return float(value)

        if node.kind == "FireCircle":
            count = numeric("count", 12)
            start = numeric("start_angle", 0.0)
            return (
                ("circle", (count, start))
                if count is not None and start is not None
                else ("hint", "发射参数含表达式，无法绘制静态圆环")
            )
        if node.kind == "FireArc":
            count = numeric("count", 5)
            center = numeric("center_angle", -90.0)
            arc = numeric("arc_angle", 60.0)
            return (
                ("arc", (count, center, arc))
                if None not in {count, center, arc}
                else ("hint", "发射参数含表达式，无法绘制静态扇形")
            )
        if node.kind in {"FirePolar", "FireOrbit"}:
            radius = numeric("orbit_radius", 0.1)
            theta = numeric("theta", 0.0)
            angular = numeric("angular_velocity", 0.0)
            return (
                ("orbit", (radius, theta, angular))
                if None not in {radius, theta, angular}
                else ("hint", "轨道参数含表达式，无法绘制静态轨迹")
            )
        if node.kind == "FireAtPlayer":
            offset = numeric("offset_angle", 0.0)
            return (
                ("aimed", (offset,))
                if offset is not None
                else ("hint", "偏移角含表达式，无法绘制静态方向")
            )
        angle = numeric("angle", -90.0)
        return (
            ("ray", (angle,))
            if angle is not None
            else ("hint", "角度含表达式，无法绘制静态方向")
        )

    def _coordinate_spec(self, node):
        """Current paint spec, reading live editor values when present."""

        kind = _coordinate_spec_kind(node)
        if kind is None:
            return None
        if kind == "hint":
            if node.kind in {
                "Fire", "FireCircle", "FireArc", "FireAtPlayer",
            } and "x" not in node.arguments:
                return ("hint", "未填写坐标，使用发射者位置")
            return ("hint", "坐标含表达式，无法预览")
        fields = ("dx", "dy") if kind == "delta" else ("x", "y")
        defaults = _constructor_defaults(dsl.NODE_CONSTRUCTORS.get(node.kind))
        values = []
        for field in fields:
            original = node.arguments.get(field, defaults.get(field))
            editor = self.findChild(QWidget, f"argument_{field}")
            try:
                value = self._current_value(editor, original) if editor is not None else original
            except ValueError:
                return ("hint", "请完成坐标输入后再预览位置")
            if value is None or value is dsl.RUNTIME_DEFAULT:
                return ("hint", "未填写的坐标使用发射者位置")
            if isinstance(value, Expr) or not isinstance(value, (int, float)) or isinstance(value, bool):
                return ("hint", "坐标含表达式，无法预览")
            values.append(float(value))
        return (kind, values[0], values[1])

    def _add_parameter_field(self, unit) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        table = ParameterTable(tuple(unit.parameters), self.session.can_edit, container)
        table.setObjectName("argument_parameters")
        table.commit_requested.connect(
            lambda values, unit_id=unit.id: self._commit_after_event(
                lambda parsed: self.session.set_unit_field(unit_id, "parameters", parsed),
                values,
                "parameters",
            )
        )
        table.error.connect(lambda message: self._show_field_error("parameters", message))
        layout.addWidget(table)
        error = QLabel("", container)
        error.setObjectName("error_parameters")
        error.setStyleSheet("color: #f85149;")
        error.setWordWrap(True)
        layout.addWidget(error)
        self.form.addRow(QLabel("参数表", self))
        self.form.addRow(container)

    def _focus_proxy(self, editor: QWidget) -> QWidget:
        inner = (
            editor.findChild(QLineEdit)
            or editor.findChild(QPlainTextEdit)
            or editor.findChild(QComboBox)
        )
        return inner or editor

    def _editor(
        self,
        value: Any,
        annotation: Any,
        owner_kind: str,
        name: str,
        commit,
    ) -> QWidget:
        if owner_kind in {"FireCircle", "FireArc"} and name in {"x", "y"} and not isinstance(value, Expr):
            return self._optional_coordinate_editor(value, name, commit)
        if value is dsl.RUNTIME_DEFAULT:
            widget = QLineEdit(self)
            unit = self.session.current_unit
            widget.setPlaceholderText(_runtime_default_label(name, unit.kind if unit is not None else None))
            widget.setReadOnly(not self.session.can_edit)
            widget.setToolTip("留空保持现有设置；输入数值后使用自定义值。")
            if self.session.can_edit:
                def submit_default() -> None:
                    text = widget.text().strip()
                    if not text:
                        self._show_field_error(name, "")
                        return
                    try:
                        parsed = _parse_literal(text)
                    except ValueError as exc:
                        self._show_field_error(name, str(exc))
                        return
                    self._commit_after_event(commit, parsed, name, value)
                widget.editingFinished.connect(submit_default)
                widget.textChanged.connect(self._refresh_coordinate_preview)
            return widget
        if owner_kind == "Call" and name == "assign":
            widget = QLineEdit(value or "", self)
            widget.setPlaceholderText("可选：变量名，留空不保存返回值")
            widget.setReadOnly(not self.session.can_edit)
            if self.session.can_edit:
                widget.editingFinished.connect(
                    lambda editor=widget, original=value: self._commit_after_event(
                        commit, editor.text().strip() or None, name, original
                    )
                )
            return widget
        if owner_kind == "RawPython" and name == "source":
            return self._source_text_editor(value, name, commit)
        if owner_kind in _FIRE_KINDS and name in {"bullet_type", "color"}:
            return self._bullet_alias_editor(
                str(value), owner_kind, name, commit
            )
        if isinstance(value, Ref):
            return self._ref_editor(value, owner_kind, name, commit)
        if isinstance(value, Expr):
            return self._expr_editor(value, name, commit)
        literal_options = _literal_options(annotation)
        if literal_options is not None:
            return self._literal_combo(value, literal_options, name, commit)
        field_type = _field_type(annotation, value)
        if field_type is bool:
            widget = QCheckBox(self)
            widget.setChecked(bool(value))
            widget.setEnabled(self.session.can_edit)
            widget.setToolTip(_range_tooltip(owner_kind, name, annotation, value))
            if self.session.can_edit:
                widget.toggled.connect(
                    lambda checked, original=bool(value): self._commit_after_event(
                        commit, checked, name, original
                    )
                )
            return widget
        if field_type is int:
            # QSpinBox stores a signed 32-bit integer.  Values outside that
            # widget range stay editable as text so simply opening Inspector
            # can never replace the source value with a clamped one.
            if not -(2**31) <= int(value) <= 2**31 - 1:
                return self._numeric_text_editor(value, name, commit)
            bounds = _field_range(owner_kind, name) or (None, None)
            if (
                (bounds[0] is not None and int(value) < bounds[0])
                or (bounds[1] is not None and int(value) > bounds[1])
            ):
                return self._numeric_text_editor(value, name, commit)
            widget = _ScrollSafeSpinBox(self)
            minimum = -(2**31) if bounds[0] is None else max(-(2**31), int(bounds[0]))
            maximum = 2**31 - 1 if bounds[1] is None else min(2**31 - 1, int(bounds[1]))
            widget.setRange(minimum, maximum)
            widget.setValue(int(value))
            widget.setReadOnly(not self.session.can_edit)
            widget.setToolTip(_range_tooltip(owner_kind, name, annotation, value))
            if self.session.can_edit:
                widget.editingFinished.connect(
                    lambda editor=widget, original=value: self._commit_after_event(
                        commit, editor.value(), name, original
                    )
                )
                widget.valueChanged.connect(self._refresh_coordinate_preview)
            return widget
        if field_type is float:
            # A decimal-limited spinner rounds *new* input even when the old
            # source value fits.  Parse the complete literal on commit instead.
            widget = self._numeric_text_editor(value, name, commit)
            widget.setToolTip(_range_tooltip(owner_kind, name, annotation, value))
            return widget
        if isinstance(value, (list, tuple, dict)):
            return self._literal_text_editor(value, name, commit)
        is_resource = _is_resource_field(owner_kind, name)
        accepts = lambda uri: resource_field_accepts(owner_kind, name, uri)
        widget = ResourceLineEdit(accepts, self) if is_resource else QLineEdit(self)
        widget.setText(value if isinstance(value, str) else repr(value))
        widget.setReadOnly(not self.session.can_edit)
        if self.session.can_edit:
            widget.editingFinished.connect(
                lambda editor=widget, original=value: self._commit_after_event(
                    commit, _parse_text(editor.text(), original), name, original
                )
            )
            widget.textChanged.connect(self._refresh_coordinate_preview)
            if isinstance(widget, ResourceLineEdit):
                widget.resource_dropped.connect(
                    lambda uri, original=value: self._commit_after_event(
                        commit, uri, name, original
                    )
                )
        return widget

    def _optional_coordinate_editor(self, value: Any, name: str, commit) -> QWidget:
        widget = QLineEdit(self)
        widget.setText("" if value is dsl.RUNTIME_DEFAULT else repr(value))
        unit = self.session.current_unit
        widget.setPlaceholderText(_runtime_default_label(name, unit.kind if unit is not None else None))
        widget.setReadOnly(not self.session.can_edit)
        widget.setToolTip("输入数值使用自定义坐标；清空后恢复默认。波次中必须明确填写坐标。")
        edited = [False]
        widget.textChanged.connect(lambda _text: edited.__setitem__(0, True))
        if self.session.can_edit:
            def submit() -> None:
                if not edited[0]:
                    return
                text = widget.text().strip()
                if not text:
                    reset = _FieldCommit(
                        commit.unit_id, commit.uid,
                        lambda _value: self.session.unset_node_argument(commit.uid, name),
                    )
                    self._commit_after_event(reset, dsl.RUNTIME_DEFAULT, name, value)
                    return
                try:
                    parsed = _parse_literal(text)
                except ValueError as exc:
                    self._show_field_error(name, str(exc))
                    return
                self._commit_after_event(commit, parsed, name, value)
            widget.editingFinished.connect(submit)
            widget.textChanged.connect(self._refresh_coordinate_preview)
        return widget

    def _source_text_editor(self, value: str, name: str, commit) -> QWidget:
        widget = LiteralTextEdit(self)
        widget.setPlainText(value)
        widget.setMinimumHeight(144)
        widget.setReadOnly(not self.session.can_edit)
        widget.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        widget.setPlaceholderText("在此编写当前动作中的多行 Python 代码")
        if self.session.can_edit:
            widget.commit_requested.connect(
                lambda editor=widget, original=value: self._commit_after_event(
                    commit, editor.toPlainText(), name, original
                )
            )
        return widget

    def _numeric_text_editor(self, value: Any, name: str, commit) -> QWidget:
        """Edit a scalar that cannot be represented by Qt's spinbox range."""

        widget = QLineEdit(self)
        widget.setText(repr(value))
        widget.setReadOnly(not self.session.can_edit)
        widget.setToolTip(_range_tooltip(None, name, type(value), value))
        if self.session.can_edit:
            widget.editingFinished.connect(
                lambda editor=widget, original=value: self._commit_after_event(
                    commit, _parse_text(editor.text(), original), name, original
                )
            )
            widget.textChanged.connect(self._refresh_coordinate_preview)
        return widget

    def _bullet_alias_editor(
        self,
        value: str,
        owner_kind: str,
        name: str,
        commit,
    ) -> QWidget:
        del owner_kind
        node = self.session.current_node
        bullet_type = str(
            node.arguments.get("bullet_type", "ball_m") if node is not None else "ball_m"
        )
        color = str(node.arguments.get("color", "red") if node is not None else "red")
        options = (
            self._bullet_catalog.bullet_types
            if name == "bullet_type"
            else self._bullet_catalog.colors(bullet_type)
        )
        if value not in options:
            options = (value, *options)
        widget = QComboBox(self)
        widget.setEditable(True)
        widget.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        widget.setToolTip(
            "输入可搜索；列表只来自 assets/bullet_aliases.json 中真实可用的别名"
        )
        for option in options:
            option_type = option if name == "bullet_type" else bullet_type
            option_color = color if name == "bullet_type" else option
            widget.addItem(
                self._bullet_catalog.icon(option_type, option_color),
                option,
                option,
            )
        current_index = widget.findText(value)
        if current_index >= 0:
            widget.setCurrentIndex(current_index)
        else:
            widget.setEditText(value)
        widget.setEnabled(self.session.can_edit)
        completer = widget.completer()
        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)

        def submit(original=value) -> None:
            selected = widget.currentText().strip()
            if selected not in options:
                self._show_field_error(name, f"未知{_FIELD_LABELS[name]}：{selected}")
                return
            self._commit_after_event(commit, selected, name, original)

        if self.session.can_edit:
            widget.currentIndexChanged.connect(
                lambda index: submit() if index >= 0 else None
            )
            line_edit = widget.lineEdit()
            if line_edit is not None:
                line_edit.editingFinished.connect(submit)
        return widget

    def _literal_combo(self, value, options: tuple, name: str, commit) -> QWidget:
        widget = QComboBox(self)
        for option in options:
            widget.addItem(str(option), option)
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)
        widget.setEnabled(self.session.can_edit)
        widget.setToolTip(_range_tooltip(owner_kind=None, name=name, annotation=None, value=value) or name)
        if self.session.can_edit:
            widget.currentIndexChanged.connect(
                lambda _index, original=value: self._commit_after_event(
                    commit, widget.currentData(), name, original
                )
            )
        return widget

    def _ref_editor(self, value: Ref, owner_kind: str, name: str, commit) -> QWidget:
        """A searchable, explicit reference selector over existing logical units."""

        widget = QComboBox(self)
        expected = reference_kinds_for_field(owner_kind, name)
        candidates = [
            unit
            for unit in sorted(
                self.session.program.logical_units(), key=lambda item: (item.name, item.id)
            )
            if not expected or unit.kind in expected
        ]
        names = [unit.name for unit in candidates]
        for unit in candidates:
            label = f"{unit.name} · {unit.id}" if names.count(unit.name) > 1 else unit.name
            widget.addItem(label, unit.id)
            widget.setItemData(widget.count() - 1, unit.id, Qt.ItemDataRole.ToolTipRole)
        if widget.findData(value.id) < 0:
            widget.insertItem(0, f"未找到 · {value.id}", value.id)
        widget.setCurrentIndex(widget.findData(value.id))
        label_ids = {widget.itemText(index): str(widget.itemData(index)) for index in range(widget.count())}
        widget.setEditable(True)
        widget.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        widget.setEnabled(self.session.can_edit)
        widget.setToolTip(f"选择已有内容，可搜索名称或输入 Python ID\n当前 ID：{value.id}")
        widget.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        if self.session.can_edit:
            # Dropdown selections commit once; typed identifiers commit on
            # Enter/focus-out so partial ids never hit the model.
            widget.currentIndexChanged.connect(
                lambda index, original=value: (
                    self._commit_after_event(
                        commit, Ref(str(widget.itemData(index))), name, original
                    )
                    if index >= 0
                    else None
                )
            )
            line_edit = widget.lineEdit()
            # A combo can delete its child line edit before emitting the last
            # focus-out signal.  Capture input changes while it is still alive.
            entered_text = [line_edit.text()]
            line_edit.textChanged.connect(
                lambda text: entered_text.__setitem__(0, text)
            )
            line_edit.editingFinished.connect(
                lambda original=value: self._commit_after_event(
                    commit,
                    Ref(label_ids.get(entered_text[0], entered_text[0].strip())),
                    name, original
                )
            )
        return widget

    def _expr_editor(self, value: Expr, name: str, commit) -> QWidget:
        widget = QLineEdit(self)
        widget.setText(value.source)
        widget.setPlaceholderText("表达式，如 player_x")
        widget.setReadOnly(not self.session.can_edit)
        if self.session.can_edit:
            candidates = self._expression_candidates()
            completer = QCompleter(QStringListModel(candidates, widget), widget)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            widget.setCompleter(completer)
        if self.session.can_edit:
            node = self.session.current_node
            optional_coordinate = bool(node and node.kind in {"FireCircle", "FireArc"} and name in {"x", "y"})
            edited = [False]
            widget.textChanged.connect(lambda _text: edited.__setitem__(0, True))
            def submit_expression() -> None:
                if optional_coordinate and edited[0] and not widget.text().strip():
                    reset = _FieldCommit(
                        commit.unit_id, commit.uid,
                        lambda _value: self.session.unset_node_argument(commit.uid, name),
                    )
                    self._commit_after_event(reset, dsl.RUNTIME_DEFAULT, name, value)
                else:
                    self._commit_after_event(commit, Expr(widget.text()), name, value)
            widget.editingFinished.connect(submit_expression)
            widget.textChanged.connect(self._refresh_coordinate_preview)
        return widget

    def _expression_candidates(self) -> list[str]:
        """Static authoring names only; no expression is imported or executed."""

        candidates = {
            "player_x",
            "player_y",
            "difficulty",
            "seed",
            "frame",
            "self.x",
            "self.y",
        }
        unit = self.session.current_unit
        if unit is not None:
            candidates.update(parameter.name for parameter in unit.parameters)

            def visit(node) -> None:
                if node.kind == "Set":
                    name = node.arguments.get("name")
                    if isinstance(name, str) and name.isidentifier():
                        candidates.add(name)
                if node.kind == "ForEach":
                    target = node.arguments.get("target")
                    if isinstance(target, str) and target.isidentifier():
                        candidates.add(target)
                for children in node.children.values():
                    for child in children:
                        visit(child)

            for node in unit.body:
                visit(node)
        return sorted(candidates)

    def _expr_toggle(
        self,
        editor: QWidget,
        value: Any,
        annotation: Any,
        name: str,
        commit,
    ) -> QWidget:
        button = QToolButton(self)
        button.setObjectName(f"expression_toggle_{name}")
        button.setText("表达式" if isinstance(value, Expr) else "常量")
        button.setStyleSheet("QToolButton { padding: 2px 4px; margin: 0; }")
        button.setToolTip(
            "当前为表达式。点击改回常量；表达式须为可转换的固定值。"
            if isinstance(value, Expr) else _EXPR_TOGGLE_TIP
        )
        button.setEnabled(self.session.can_edit)

        def switch() -> None:
            if isinstance(value, Expr):
                try:
                    constant = _parse_expr_constant(editor.text(), annotation)
                except ValueError as exc:
                    self._show_field_error(name, str(exc))
                    return
                self._commit_after_event(commit, constant, name, value)
                return
            try:
                current = self._current_value(editor, value)
            except ValueError as exc:
                self._show_field_error(name, str(exc))
                return
            self._commit_after_event(commit, Expr(_expr_source(current)), name, value)

        button.clicked.connect(switch)
        return button

    def _supports_expr(self, value: Any, annotation: Any, field_name: str) -> bool:
        if field_name in {"unit_name", "assign", "source"}:
            return False
        if isinstance(value, (list, tuple, dict, Ref, bool)):
            return False
        if isinstance(value, Expr):
            return True
        return _field_type(annotation, value) in {int, float, str}

    def _current_value(self, editor: QWidget, original: Any) -> Any:
        if isinstance(editor, QSpinBox):
            return editor.value()
        if isinstance(editor, (QLineEdit, ResourceLineEdit)):
            if isinstance(original, Expr):
                return Expr(editor.text())
            if original is dsl.RUNTIME_DEFAULT and not editor.text().strip():
                return original
            return _parse_text(editor.text(), original)
        if isinstance(editor, QComboBox):
            data = editor.currentData()
            return data if data is not None else editor.currentText()
        return original

    def _browse_button(self, editor: ResourceLineEdit, name: str) -> QWidget:
        button = QToolButton(self)
        button.setText("…")
        button.setToolTip("选择工程内文件")

        def browse() -> None:
            context = self.session.project_context
            if context is None:
                return
            path, _filter = QFileDialog.getOpenFileName(self, "选择资源文件", str(context.root))
            if not path:
                return
            try:
                relative = Path(path).resolve().relative_to(context.root).as_posix()
            except ValueError:
                self._show_field_error(name, "文件必须在工程目录内")
                return
            uri = f"res://{relative}"
            editor.setText(uri)
            editor.resource_dropped.emit(uri)

        button.clicked.connect(browse)
        return button

    def _literal_text_editor(self, value: Any, name: str, commit) -> QWidget:
        widget = LiteralTextEdit(self)
        widget.setPlainText(repr(value))
        widget.setFixedHeight(64)
        widget.setReadOnly(not self.session.can_edit)
        widget.setPlaceholderText("Python 字面量，例如 ['a', 1] 或 {'x': 2}")
        if self.session.can_edit:
            widget.commit_requested.connect(
                lambda editor=widget, original=value: self._commit_literal_text(
                    editor, commit, name, original
                )
            )
            widget.textChanged.connect(self._refresh_coordinate_preview)
        return widget

    # -- commit with field-level errors ---------------------------------------

    def _commit_after_event(
        self, callback, value: Any, name: str, original: Any = _UNSET
    ) -> None:
        """Commit after a native editor finishes dispatching its input event.

        A successful commit replaces the immutable model and synchronously
        rebuilds this panel.  Destroying an editor from inside its own
        signal handler is use-after-free, so capture the value now and mutate
        only after control returns to the event loop.
        """

        QTimer.singleShot(
            0, lambda: self._commit(callback, value, name, original)
        )

    def _commit(
        self, callback, value: Any, name: str, original: Any = _UNSET
    ) -> None:
        current = self._current_field_value(name, callback)
        if current is not _UNSET and _values_equal(value, current):
            self._show_field_error(name, "")
            return
        previous_selection = (self.session.current_unit_id, self.session.current_node_uid)
        self._commit_depth += 1
        try:
            callback(value)
        except Exception as exc:
            self._commit_depth -= 1
            self._show_field_error(name, str(exc))
            return
        self._commit_depth -= 1
        if (
            previous_selection == (self.session.current_unit_id, self.session.current_node_uid)
            and name not in {"bullet_type", "color", "parameters"}
            and original is not _UNSET
            and type(value) is type(original)
        ):
            # The focused editor already contains the new value.  Preserve it
            # through a successful same-type commit so Tab and a second edit
            # keep their focus, instead of deleting and recreating the sender.
            self._display_key = self._display_state()
            self._refresh_coordinate_preview()
        self._show_field_error(name, "")

    def _current_field_value(self, name: str, callback):
        node = self.session.current_node
        unit = self.session.current_unit
        if isinstance(callback, _FieldCommit):
            try:
                unit = self.session.program.get_unit(callback.unit_id)
                node = find_node(self.session.program, callback.uid)[1] if callback.uid else None
            except ProgramError:
                return _UNSET
        if node is not None:
            if name in node.arguments:
                return node.arguments[name]
            constructor = dsl.NODE_CONSTRUCTORS.get(node.kind)
            return _constructor_defaults(constructor).get(name, _UNSET)
        if unit is None:
            return _UNSET
        if name == "名称":
            return unit.name
        if name == "parameters":
            return unit.parameters
        if name in unit.metadata:
            return unit.metadata[name]
        return _constructor_defaults(dsl.UNIT_CONSTRUCTORS[unit.kind]).get(name, _UNSET)

    def _refresh_coordinate_preview(self, *_args) -> None:
        if self._coordinate_preview is not None:
            self._coordinate_preview.update()
        if self._emission_preview is not None:
            self._emission_preview.update()

    def _commit_literal_text(
        self, editor: QPlainTextEdit, callback, name: str, original: Any = _UNSET
    ) -> None:
        try:
            value = _parse_literal(editor.toPlainText())
        except ValueError as exc:
            self._show_field_error(name, str(exc))
            return
        # LiteralTextEdit emits from focusOutEvent.  Parsing is safe while Qt
        # dispatches that event, but a successful model commit emits
        # selection_changed and rebuilds this panel.  Queue the mutation so
        # the editor cannot be deleted under its own focus-out handler.
        self._commit_after_event(callback, value, name, original)

    def _show_field_error(self, name: str, message: str) -> None:
        error_label = self.findChild(QLabel, f"error_{name}")
        if error_label is None:
            if message:
                window = self.window()
                if hasattr(window, "statusBar"):
                    window.statusBar().showMessage(f"参数未修改：{message}", 5000)
            return
        error_label.setText(message)
        error_label.setVisible(bool(message))


def resource_field_accepts(owner_kind: str, name: str, uri: str) -> bool:
    path = PurePosixPath(uri.removeprefix("res://").split("#", 1)[0])
    suffix = path.suffix.lower()
    return suffix in _RESOURCE_FIELD_SUFFIXES.get((owner_kind, name), frozenset())


_AUDIO_SUFFIXES = frozenset({".flac", ".mp3", ".ogg", ".wav"})
_IMAGE_SUFFIXES = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"})
_RESOURCE_FIELD_SUFFIXES = {
    ("Stage", "bgm"): _AUDIO_SUFFIXES,
    ("Stage", "boss_bgm"): _AUDIO_SUFFIXES,
    ("PlayBGM", "name"): _AUDIO_SUFFIXES,
    ("PlaySE", "name"): _AUDIO_SUFFIXES,
    ("Stage", "background"): frozenset({".json"}),
    ("SetBackground", "name"): frozenset({".json"}),
    ("Enemy", "sprite"): _IMAGE_SUFFIXES | {".json"},
    ("Boss", "texture"): _IMAGE_SUFFIXES | {".json"},
    ("PlayDialogue", "dialogue_list"): frozenset({".json"}),
}


def _is_resource_field(owner_kind: str, name: str) -> bool:
    return (owner_kind, name) in _RESOURCE_FIELD_SUFFIXES


def _constructor_defaults(constructor) -> dict[str, Any]:
    if constructor is None:
        return {}
    return {
        name: parameter.default
        for name, parameter in inspect.signature(constructor).parameters.items()
    }


def _literal_options(annotation: Any) -> tuple | None:
    if get_origin(annotation) is Literal:
        return tuple(get_args(annotation))
    return None


def _parse_text(text: str, original: Any) -> Any:
    if isinstance(original, str):
        return text
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return text


def _parse_literal(text: str) -> Any:
    try:
        return parse_author_value(text)
    except ProgramError as exc:
        raise ValueError(
            f"不是合法的作者值（字面量/Ref/Expr）：{exc.message}"
        ) from exc


def _expr_source(value: Any) -> str:
    if isinstance(value, str):
        return value if value else "0"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return repr(value)
    return repr(value)


def _parse_expr_constant(source: str, annotation: Any) -> Any:
    """Convert an expression editor back to a literal without executing it."""

    try:
        return ast.literal_eval(source)
    except (SyntaxError, ValueError):
        if _annotation_contains(annotation, str):
            return source
        raise ValueError("只有字面量表达式才能切回常量") from None


def _annotation_contains(annotation: Any, expected: type) -> bool:
    if annotation is expected:
        return True
    origin = get_origin(annotation)
    if origin in {types.UnionType, Union}:
        return any(_annotation_contains(item, expected) for item in get_args(annotation))
    return False


def _resource_uri(mime_data) -> str | None:
    if not mime_data.hasFormat(RESOURCE_MIME):
        return None
    return bytes(mime_data.data(RESOURCE_MIME)).decode("utf-8")


def _node_fields(node, constructor) -> tuple[tuple[str, Any], ...]:
    if constructor is None:
        return tuple(node.arguments.items())
    signature = inspect.signature(constructor)
    values: list[tuple[str, Any]] = []
    for name, parameter in signature.parameters.items():
        if name == "uid" or name in {"body", "else_body", "branches"}:
            continue
        if name in node.arguments:
            values.append((name, node.arguments[name]))
        elif parameter.default is not inspect.Parameter.empty:
            values.append((name, parameter.default))
    for name, value in node.arguments.items():
        if name not in signature.parameters:
            values.append((name, value))
    return tuple(values)


def _unit_fields(
    metadata: dict[str, Any], constructor
) -> tuple[tuple[str, Any], ...]:
    signature = inspect.signature(constructor)
    values: list[tuple[str, Any]] = []
    for name, parameter in signature.parameters.items():
        if name in {"id", "name", "body", "parameters"}:
            continue
        if name in metadata:
            values.append((name, metadata[name]))
        elif parameter.default is not inspect.Parameter.empty:
            values.append((name, parameter.default))
    for name, value in metadata.items():
        if name not in signature.parameters:
            values.append((name, value))
    return tuple(values)


def _field_type(annotation: Any, value: Any) -> type | None:
    """Choose a scalar Qt control from the DSL annotation, then the literal value."""

    if isinstance(value, (Expr, Ref)):
        return None
    if annotation in {bool, int, float, str}:
        return annotation
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in {types.UnionType, Union}:
        scalar_options = [item for item in arguments if item in {bool, int, float, str}]
        for scalar in scalar_options:
            if scalar is bool and type(value) is bool:
                return scalar
            if scalar is int and type(value) is int:
                return scalar
            if scalar is float and not isinstance(value, bool) and isinstance(value, (int, float)):
                return scalar
            if scalar is str and isinstance(value, str):
                return scalar
    if origin is Literal:
        literal_types = {type(item) for item in arguments}
        if len(literal_types) == 1:
            scalar = next(iter(literal_types))
            if scalar in {bool, int, float, str}:
                return scalar
    if type(value) in {bool, int, float, str}:
        return type(value)
    return None


__all__ = [
    "BulletAssetCatalog",
    "BulletPreview",
    "EmissionPreview",
    "InspectorPanel",
    "ParameterTable",
    "ResourceLineEdit",
    "resource_field_accepts",
]
