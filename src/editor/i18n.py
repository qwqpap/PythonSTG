"""Small runtime language layer for the Qt authoring workbench.

The editor deliberately keeps authoring documents, resource names, node types,
and runtime protocol messages as data.  This module only translates UI-owned
labels and actions, so changing language cannot change a saved document or an
internal enum value.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.qt_compat.QtCore import QObject, pyqtSignal
try:
    from src.qt_compat.QtGui import QAction
except ImportError:  # The legacy Qt binding keeps QAction in QtWidgets.
    from src.qt_compat.QtWidgets import QAction
from src.qt_compat.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDockWidget,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMenu,
    QTableWidget,
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QWidget,
)


LANGUAGE_ENGLISH = "en"
LANGUAGE_CHINESE = "zh-CN"
SUPPORTED_LANGUAGES = (LANGUAGE_ENGLISH, LANGUAGE_CHINESE)


# English is the source language.  Keeping the keys in English makes the
# existing editor API and tests stable while allowing the UI to be translated
# without putting presentation text into authoring resources.
_ZH_CN: dict[str, str] = {
    "PySTG Editor": "PySTG 编辑器",
    "&File": "文件(&F)",
    "&Edit": "编辑(&E)",
    "&Run": "运行(&R)",
    "&Tools": "工具(&T)",
    "&Language": "语言(&L)",
    "New Scene": "新建场景",
    "New Pattern": "新建弹幕",
    "Open Resource…": "打开资源…",
    "Open Resource...": "打开资源…",
    "Save": "保存",
    "Save As…": "另存为…",
    "Save As...": "另存为…",
    "Revert": "还原",
    "Close Document": "关闭文档",
    "Undo": "撤销",
    "Redo": "重做",
    "Delete Node": "删除节点",
    "Rename Node": "重命名节点",
    "Move Up": "上移",
    "Move Down": "下移",
    "Move to Parent": "移到父节点",
    "Make Child of Previous": "设为前一节点的子节点",
    "Run / Preview": "运行 / 预览",
    "Frame Canvas": "画布聚焦",
    "Main": "主工具栏",
    "Scene": "场景",
    "Inspector": "检查器",
    "Output": "输出",
    "Timeline": "时间线",
    "Preview": "预览",
    "Bottom Panel": "底部面板",
    "Runtime Preview": "运行时预览",
    "Assets": "资源",
    "Bullet Aliases": "弹幕别名",
    "Simple Spell Setup": "简单符卡设置",
    "+ Add": "+ 添加",
    "Delete": "删除",
    "Move up (Alt+Up)": "上移（Alt+Up）",
    "Move down (Alt+Down)": "下移（Alt+Down）",
    "Move to parent (Alt+Left)": "移到父节点（Alt+Left）",
    "Make child of previous node (Alt+Right)": "设为前一节点的子节点（Alt+Right）",
    "English": "English",
    "简体中文": "简体中文",
    "Pattern": "弹幕",
    "Movement": "移动",
    "Audio": "音频",
    "Event": "事件",
    "Property": "属性",
    "ScriptEvent": "脚本事件",
    "Recipe": "配方",
    "Graph": "行为图",
    "Authoring mode: Recipe (fields) or Graph (behavior nodes)": "创作模式：配方（字段）或行为图（行为节点）",
    "Fold back to Recipe": "折叠回配方",
    "Guides": "辅助线",
    "Formal Preview": "正式预览",
    "Bullet": "弹幕",
    "Template": "模板",
    "Assign Bullet": "指定弹幕",
    "Apply Template": "应用模板",
    "Starter Ring": "起始环形",
    "Aimed Arc": "瞄准弧形",
    "Spiral": "螺旋",
    "Bullet sprite resource (#fragment)": "弹幕精灵资源（#片段）",
    "Add Node": "添加节点",
    "Tip": "提示",
    "Drag between ports to connect. Del removes selection.": "在端口之间拖动以连接。按 Del 删除选中项。",
    "Drag E/P gizmos. Drop an Assets sprite to assign.": "拖动 E/P 控制柄。将资源中的精灵拖入以指定。",
    "Choose bullet sprite…": "选择弹幕精灵…",
    "Choose bullet sprite...": "选择弹幕精灵…",
    "This pattern is in Recipe mode. Expand it into the typed behavior graph to edit nodes, ports, and connections.": "此弹幕处于配方模式。展开为类型化行为图后即可编辑节点、端口和连接。",
    "Expand to Graph": "展开为行为图",
    "No node selected": "未选择节点",
    "No graph node selected": "未选择行为图节点",
    "No UI node selected": "未选择 UI 节点",
    "Name": "名称",
    "Type": "类型",
    "Other": "其他",
    "X": "X",
    "Y": "Y",
    "Canvas Width": "画布宽度",
    "Canvas Height": "画布高度",
    "Grid Size": "网格大小",
    "Tick Rate": "帧率",
    "Texture": "纹理",
    "Scale": "缩放",
    "Rotation": "旋转",
    "Visible": "可见",
    "Enemy Script": "敌人脚本",
    "Start Frame": "开始帧",
    "Interval": "间隔",
    "Count": "数量",
    "Script": "脚本",
    "Class": "类",
    "Boss X": "Boss X",
    "Boss Y": "Boss Y",
    "Bullet Type": "弹幕类型",
    "Color": "颜色",
    "Resource": "资源",
    "Origin X": "起点 X",
    "Origin Y": "起点 Y",
    "Angle Span": "角度范围",
    "Line Length": "线段长度",
    "Line Angle": "线段角度",
    "Angle": "角度",
    "Delay Frames": "延迟帧数",
    "Interval Frames": "间隔帧数",
    "Burst Count": "爆发次数",
    "Speed": "速度",
    "Friction": "摩擦",
    "Spin": "旋转速度",
    "Time Scale": "时间缩放",
    "Max Lifetime": "最大寿命",
    "Render Scale": "渲染缩放",
    "Bounce X": "X 轴反弹",
    "Bounce Y": "Y 轴反弹",
    "Speed Expression": "速度表达式",
    "Angle Offset / Burst": "每次爆发角度偏移",
    "Speed Offset / Burst": "每次爆发速度偏移",
    "Random Speed Var": "随机速度变化",
    "Kind": "种类",
    "Start [frame]": "开始帧",
    "Duration [frame]": "持续帧数",
    "Loop Count": "循环次数",
    "Order": "顺序",
    "Enabled": "启用",
    "Target": "目标",
    "Channel": "通道",
    "Payload": "载荷",
    "Apply Payload": "应用载荷",
    "Keyframes": "关键帧",
    "Frame": "帧",
    "Value": "值",
    "Interpolation": "插值",
    "Muted": "静音",
    "(none)": "（无）",
    "(inherit / none)": "（继承 / 无）",
    "Pattern Preview: ": "弹幕预览：",
    "Advanced · ": "高级 · ",
    "Advanced · Modifiers": "高级 · 修改器",
    "Bullet": "弹幕",
    "Shape": "形状",
    "Aim": "瞄准",
    "Schedule": "调度",
    "Motion": "运动",
    "Modifiers": "修改器",
    "Camera": "相机",
    "Fog": "雾效",
    "Scroll": "滚动",
    "Layers": "图层",
    "Layer": "图层",
    "Background": "背景",
    "UI": "界面",
    "Viewport": "视口",
    "Node": "节点",
    "Add": "添加",
    "Add Layer": "添加图层",
    "Delete Layer": "删除图层",
    "Bind": "绑定",
    "Search resources…": "搜索资源…",
    "Search resources...": "搜索资源…",
    "All types": "全部类型",
    "Refresh": "刷新",
    "All resources": "全部资源",
    "Select a resource": "选择资源",
    "Type: ": "类型：",
    "Path: ": "路径：",
    "Rect: ": "矩形：",
    "Size: ": "大小：",
    "Frames: ": "帧数：",
    "FPS: ": "帧率：",
    "Runtime": "运行时",
    "Mode": "模式",
    "State": "状态",
    "Duration": "时长",
    "Active Clips": "活动片段",
    "Events": "事件",
    "Bullets": "弹幕数",
    "Seed": "种子",
    "Update": "更新",
    "Render": "渲染",
    "Target / diagnostics": "目标 / 诊断",
    "Player X/Y": "玩家 X/Y",
    "Set player": "设置玩家",
    "Set seed": "设置种子",
    "Grid, emitter and player gizmos": "网格、发射器和玩家控制柄",
    "Live Inspector property": "实时检查器属性",
    "Edit Scene clips in Timeline": "在时间线中编辑场景片段",
    "Apply / reload": "应用 / 重载",
    "Path": "路径",
    "JSON value": "JSON 值",
    "No authoring resource selected": "未选择创作资源",
    "Launch Preview": "启动预览",
    "Play": "播放",
    "Pause": "暂停",
    "Step": "单步",
    "Reset": "重置",
    "Stop": "停止",
    "Seek": "跳转",
    "Preview process is stopped": "预览进程已停止",
    "Starting preview process…": "正在启动预览进程…",
    "Starting preview process...": "正在启动预览进程…",
    "Seed must be an integer": "种子必须是整数",
    "Property path is required": "必须填写属性路径",
    "Preview error": "预览错误",
    "Drop a sprite from Assets": "从资源中拖入精灵",
    "Drop a compatible resource from Assets": "从资源中拖入兼容资源",
    "Connected (protocol ": "已连接（协议 ",
    "This editor is ready": "编辑器已就绪",
    "Snap": "吸附",
    "+ Track": "+ 轨道",
    "- Track": "- 轨道",
    "Track Up": "轨道上移",
    "Track Down": "轨道下移",
    "Mute": "静音",
    "+ Clip": "+ 片段",
    "Duplicate": "复制",
    "+ Key": "+ 关键帧",
    "- Key": "- 关键帧",
    "No tracks. Choose a kind and add the first track.": "暂无轨道。选择种类并添加第一条轨道。",
    "Edit failed": "编辑失败",
    "Save PySTG Resource": "保存 PySTG 资源",
    "Open PySTG Resource": "打开 PySTG 资源",
    "Save failed": "保存失败",
    "Open failed": "打开失败",
    "Tool failed": "工具运行失败",
    "No-code Spell preview unavailable": "无代码符卡预览不可用",
    "Revert document": "还原文档",
    "Discard all changes to ": "放弃对以下文档的全部修改：",
    "Unsaved changes": "未保存的修改",
    "Save changes to ": "保存对以下文档的修改：",
    "Tool unavailable": "工具不可用",
    "Preview unavailable": "预览不可用",
    "Preview failed": "预览失败",
    "Preview is already running": "预览已经在运行",
    "Formal preview uses the game renderer in a separate process.\nThe native window will appear here when embedding is available.": "正式预览在独立进程中使用游戏渲染器。\n支持嵌入时，原生窗口会显示在这里。",
    "Formal preview is running in its external game window on this platform.": "正式预览正在此平台的外部游戏窗口中运行。",
    "Waiting for the formal game renderer…": "正在等待正式游戏渲染器…",
    "Waiting for the formal game renderer...": "正在等待正式游戏渲染器…",
    "Formal preview is stopped. Launch Preview to start the game renderer.": "正式预览已停止。点击启动预览以运行游戏渲染器。",
}


def _translate_zh(text: str) -> str:
    """Translate one UI-owned string while preserving dynamic values."""

    exact = _ZH_CN.get(text)
    if exact is not None:
        return exact
    if text.startswith("Pattern Preview: "):
        return "弹幕预览：" + text[len("Pattern Preview: ") :]
    if text.startswith("Background: "):
        return "背景：" + text[len("Background: ") :]
    if text.startswith("UI: "):
        return "界面：" + text[len("UI: ") :]
    if text.startswith("Frame "):
        return "帧 " + text[len("Frame ") :]
    if text.startswith("Undo "):
        return "撤销 " + _translate_zh(text[len("Undo ") :])
    if text.startswith("Redo "):
        return "重做 " + _translate_zh(text[len("Redo ") :])
    if text.startswith("Discard all changes to "):
        return "放弃对以下文档的全部修改：" + text[len("Discard all changes to ") :]
    if text.startswith("Save changes to "):
        return "保存对以下文档的修改：" + text[len("Save changes to ") :]
    if text.startswith("Started "):
        return "已启动 " + text[len("Started ") :]
    if text.startswith("Preview exited (") and text.endswith(")"):
        return "预览已退出（" + text[len("Preview exited (") : -1] + "）"
    if text.endswith(" layers") and text[:-7].isdigit():
        return text[:-7] + " 个图层"
    if text.endswith(" resources") and text[:-10].isdigit():
        return text[:-10] + " 个资源"
    for unit, translated_unit in (
        ("runtime", "运行时"),
        ("deg/burst", "度/爆发"),
        ("unit/s", "单位/秒"),
        ("deg/s", "度/秒"),
        ("frame", "帧"),
        ("fps", "帧/秒"),
        ("deg", "度"),
        ("s", "秒"),
    ):
        suffix = f" [{unit}]"
        if text.endswith(suffix):
            return f"{_translate_zh(text[:-len(suffix)])} [{translated_unit}]"
    if " invalid JSON files skipped" in text:
        count, _, _tail = text.partition(" invalid JSON files skipped")
        if count.isdigit():
            return f"{count} 个资源 · 跳过无效 JSON 文件"
    for source, target in (
        ("Camera ", "相机 "),
        ("Fog ", "雾效 "),
        ("Scroll ", "滚动 "),
        ("Layer ", "图层 "),
    ):
        if text.startswith(source):
            return target + _translate_zh(text[len(source) :])
    if text.startswith("Connected (protocol ") and text.endswith(")"):
        return "已连接（协议 " + text[len("Connected (protocol ") : -1] + "）"
    return text


class LanguageManager(QObject):
    """Per-editor language state with a deliberately small public API."""

    languageChanged = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None, language: str = LANGUAGE_ENGLISH):
        super().__init__(parent)
        self._language = LANGUAGE_ENGLISH
        self.set_language(language, emit=False)

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str, *, emit: bool = True) -> bool:
        language = str(language)
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported editor language: {language!r}")
        if language == self._language:
            return False
        self._language = language
        if emit:
            self.languageChanged.emit(language)
        return True

    def toggle(self) -> str:
        language = (
            LANGUAGE_CHINESE
            if self._language == LANGUAGE_ENGLISH
            else LANGUAGE_ENGLISH
        )
        self.set_language(language)
        return language

    def translate(self, text: object) -> str:
        value = str(text)
        return value if self._language == LANGUAGE_ENGLISH else _translate_zh(value)


def _remember(obj: QObject, property_name: str, current: str) -> str:
    stored = obj.property(property_name)
    rendered = obj.property(property_name + "_rendered")
    if stored is None or (rendered is not None and str(rendered) != current):
        obj.setProperty(property_name, current)
        return current
    return str(stored)


def _remember_list(obj: QObject, property_name: str, current: list[str]) -> list[str]:
    stored = obj.property(property_name)
    rendered = obj.property(property_name + "_rendered")
    rendered_list = list(rendered) if isinstance(rendered, (list, tuple)) else None
    if (
        not isinstance(stored, (list, tuple))
        or len(stored) != len(current)
        or (rendered_list is not None and rendered_list != current)
    ):
        obj.setProperty(property_name, list(current))
        return current
    return [str(value) for value in stored]


def _set_rendered(obj: QObject, property_name: str, value: object) -> None:
    obj.setProperty(property_name + "_rendered", value)


def _translate_actions(root: QWidget, manager: LanguageManager) -> None:
    actions: list[QAction] = list(root.findChildren(QAction))
    actions.extend(action for action in root.actions() if action not in actions)
    for action in actions:
        source = _remember(action, "_pystg_i18n_text", action.text())
        translated = manager.translate(source)
        action.setText(translated)
        _set_rendered(action, "_pystg_i18n_text", translated)
        if action.toolTip():
            tooltip = _remember(action, "_pystg_i18n_tooltip", action.toolTip())
            translated_tooltip = manager.translate(tooltip)
            action.setToolTip(translated_tooltip)
            _set_rendered(action, "_pystg_i18n_tooltip", translated_tooltip)


def _translate_combo(combo: QComboBox, manager: LanguageManager) -> None:
    sources = combo.property("_pystg_i18n_items")
    current = [combo.itemText(index) for index in range(combo.count())]
    sources = _remember_list(combo, "_pystg_i18n_items", current)
    selected = combo.currentIndex()
    combo.blockSignals(True)
    translated_items = []
    for index, source in enumerate(sources):
        translated = manager.translate(source)
        translated_items.append(translated)
        combo.setItemText(index, translated)
    combo.setCurrentIndex(selected)
    combo.blockSignals(False)
    _set_rendered(combo, "_pystg_i18n_items", translated_items)


def translate_widget_tree(root: QWidget, manager: LanguageManager) -> None:
    """Re-translate static Qt labels below ``root`` in place.

    Source strings are stored as QObject dynamic properties, making the
    operation reversible even when toggled repeatedly.  Tree/list data and
    line-edit contents are intentionally not translated because they belong to
    authoring documents or user input.
    """

    widgets: Iterable[QWidget] = (root, *root.findChildren(QWidget))
    for widget in widgets:
        if isinstance(widget, (QLabel, QAbstractButton)):
            source = _remember(widget, "_pystg_i18n_text", widget.text())
            translated = manager.translate(source)
            widget.setText(translated)
            _set_rendered(widget, "_pystg_i18n_text", translated)
        if isinstance(widget, QGroupBox):
            source = _remember(widget, "_pystg_i18n_title", widget.title())
            translated = manager.translate(source)
            widget.setTitle(translated)
            _set_rendered(widget, "_pystg_i18n_title", translated)
        if isinstance(widget, (QDockWidget, QToolBar)):
            source = _remember(widget, "_pystg_i18n_title", widget.windowTitle())
            translated = manager.translate(source)
            widget.setWindowTitle(translated)
            _set_rendered(widget, "_pystg_i18n_title", translated)
        if isinstance(widget, QLineEdit):
            placeholder = widget.placeholderText()
            if placeholder:
                source = _remember(
                    widget,
                    "_pystg_i18n_placeholder",
                    placeholder,
                )
                translated = manager.translate(source)
                widget.setPlaceholderText(translated)
                _set_rendered(widget, "_pystg_i18n_placeholder", translated)
        if isinstance(widget, QComboBox):
            _translate_combo(widget, manager)
        if isinstance(widget, QTabWidget) and widget.objectName() == "bottomWorkbench":
            current = [widget.tabText(index) for index in range(widget.count())]
            sources = _remember_list(widget, "_pystg_i18n_tabs", current)
            translated_tabs = []
            for index, source in enumerate(sources):
                translated = manager.translate(source)
                translated_tabs.append(translated)
                widget.setTabText(index, translated)
            _set_rendered(widget, "_pystg_i18n_tabs", translated_tabs)
        if isinstance(widget, QTreeWidget):
            header = widget.headerItem()
            if header is not None:
                current = [header.text(index) for index in range(widget.columnCount())]
                sources = _remember_list(widget, "_pystg_i18n_headers", current)
                translated_headers = []
                for index, source in enumerate(sources):
                    translated = manager.translate(source)
                    translated_headers.append(translated)
                    header.setText(index, translated)
                _set_rendered(widget, "_pystg_i18n_headers", translated_headers)
        if isinstance(widget, QTableWidget):
            current = [
                widget.horizontalHeaderItem(index).text()
                if widget.horizontalHeaderItem(index) is not None
                else ""
                for index in range(widget.columnCount())
            ]
            sources = _remember_list(widget, "_pystg_i18n_headers", current)
            translated_headers = []
            for index in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(index)
                if item is None:
                    continue
                translated = manager.translate(sources[index])
                translated_headers.append(translated)
                item.setText(translated)
            _set_rendered(widget, "_pystg_i18n_headers", translated_headers)
        if isinstance(widget, QMenu):
            source = _remember(widget, "_pystg_i18n_title", widget.title())
            translated = manager.translate(source)
            widget.setTitle(translated)
            _set_rendered(widget, "_pystg_i18n_title", translated)
    _translate_actions(root, manager)


__all__ = [
    "LANGUAGE_CHINESE",
    "LANGUAGE_ENGLISH",
    "SUPPORTED_LANGUAGES",
    "LanguageManager",
    "translate_widget_tree",
]
