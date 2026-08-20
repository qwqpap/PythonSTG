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
    "State Flow": "关卡流程",
    "Variables": "变量",
    "Midstage Skeleton": "道中关卡模板",
    "Two-phase Boss Skeleton": "两阶段 Boss 模板",
    "Two-phase Boss": "两阶段 Boss",
    "Midstage": "道中关卡",
    "Preset": "预设",
    "Preset Details": "预设详情",
    "Choose Preset": "选择预设",
    "Adjust Parameters": "调整参数",
    "Add Dynamic Changes": "添加动态变化",
    "Edit Nodes": "编辑节点",
    "View Script Source": "查看脚本源码",
    "Make Local Copy": "转为本地副本",
    "Open Script Source": "打开脚本源码",
    "Apply Binding": "应用动态设置",
    "Remove Selected Binding": "删除所选动态设置",
    "Bind an exact Pattern property to a constant, curve, variable, or expression.": "让弹幕参数跟随常量、曲线、变量或表达式变化。",
    "2.0, res://curve…, rank, or expression": "2.0、res://曲线…、rank 或表达式",
    "States": "阶段",
    "Transitions": "阶段切换",
    "StageFlow": "关卡流程",
    "PhaseFlow": "阶段流程",
    "State name": "阶段名称",
    "Apply": "应用",
    "Copy": "复制",
    "Transition": "切换规则",
    "Trigger": "触发方式",
    "After": "经过时间",
    "On complete": "完成时",
    "Prio": "优先级",
    "Set": "更新",
    "Del": "删除",
    "Add transition": "添加切换规则",
    "Apply transition changes": "应用切换规则修改",
    "Delete transition": "删除切换规则",
    "Select a transition, or edit its name before pressing Set": "选择切换规则，或修改名称后点击更新",
    "Frames after entering this state": "进入此阶段后经过的帧数",
    "Scope": "生效范围",
    "Default": "默认值",
    "Writers": "可修改者",
    "Readers": "可读取者",
    "Writer": "修改者",
    "Reader": "读取者",
    "Reducer": "冲突合并",
    "Animatable": "可做动画",
    "Replay": "记录回放",
    "Behavior output": "节点输出",
    "Apply properties": "应用属性",
    "Map": "映射",
    "Runtime: none": "运行值：无",
    "Runtime values: 0 scopes (read-only)": "运行值：0 个范围（只读）",
    "Edit Behavior output mappings": "编辑节点输出映射",
    "JSON default": "JSON 默认值",
    "writers: timeline,safe_action": "例如：timeline,safe_action",
    "readers: pattern,debugger": "例如：pattern,debugger",
    "none": "无",
    "project": "项目",
    "stage": "关卡",
    "state": "阶段",
    "instance": "实例",
    "ring": "圆形",
    "arc": "扇形",
    "line": "直线",
    "spiral": "螺旋",
    "random": "随机",
    "flower": "花形",
    "fixed": "固定方向",
    "player": "朝向玩家",
    "constant": "固定值",
    "curve": "曲线",
    "variable": "变量",
    "expression": "表达式",
    "basic": "基础",
    "rotation": "旋转",
    "advanced": "进阶",
    "ball_s": "小型圆弹",
    "ball_m": "中型圆弹",
    "ball_l": "大型圆弹",
    "knife": "刀弹",
    "star_s": "小星弹",
    "star_m": "中星弹",
    "star_l": "大星弹",
    "arrow_s": "小箭弹",
    "arrow_m": "中箭弹",
    "arrow_l": "大箭弹",
    "square": "方形弹",
    "butterfly": "蝶弹",
    "ellipse": "椭圆弹",
    "kite": "风筝弹",
    "heart": "心形弹",
    "grain_a": "米弹 A",
    "grain_b": "米弹 B",
    "grain_c": "米弹 C",
    "gun": "枪弹",
    "mildew": "菌弹",
    "ball_light": "光球弹",
    "silence": "静默弹",
    "needle": "针弹",
    "scale": "鳞弹",
    "fire": "火焰弹",
    "scale_s": "小鳞弹",
    "rice_s": "小米弹",
    "black": "黑色",
    "blue": "蓝色",
    "cyan": "青色",
    "darkblue": "深蓝色",
    "darkcyan": "深青色",
    "darkgreen": "深绿色",
    "darkorange": "深橙色",
    "darkpurple": "深紫色",
    "darkred": "深红色",
    "darkyellow": "深黄色",
    "gray": "灰色",
    "green": "绿色",
    "orange": "橙色",
    "pink": "粉色",
    "purple": "紫色",
    "red": "红色",
    "white": "白色",
    "yellow": "黄色",
    "bullet": "基础子弹",
    "interval": "定时发射",
    "angle_offset": "逐轮旋转",
    "Every {interval} frames · {bursts} bursts": "每 {interval} 帧 · 共 {bursts} 轮",
    "Speed {value}": "速度 {value}",
    "Rotate each burst": "每轮旋转",
    "{count} bullets": "{count} 发",
    "Expand pattern to graph": "展开为节点编辑",
    "Expand to graph": "展开为节点编辑",
    "Fold back to recipe": "折叠回参数编辑",
    "Reactive": "条件触发",
    "Quick Add": "快速添加",
    "Search nodes, presets, tracks, or objects…": "搜索节点、预设、轨道或对象…",
    "Node editor": "节点编辑",
    "Scene canvas": "场景画布",
    "Preset library": "预设库",
    "Available for: ": "可连接类型：",
    "Nothing can be added here. Select a compatible object, track, or port and try again.": "这里没有可添加的内容。请先选择兼容的对象、轨道或端口。",
    "Input": "输入",
    "Output": "输出",
    "Bullet source": "子弹来源",
    "Emission shape": "发射形状",
    "Aiming mode": "瞄准模式",
    "Aiming": "瞄准方式",
    "Fire rhythm": "发射节奏",
    "Per-burst changes": "每轮变化",
    "Emission points": "发射点集",
    "Direction": "发射方向",
    "Fire timing": "发射时序",
    "Bullet motion": "子弹运动",
    "Final bullets": "最终子弹",
    "Bullet Count": "每轮子弹数",
    "Bullet Speed": "子弹速度",
    "Fire Interval": "发射间隔（帧）",
    "Number of Bursts": "发射轮数",
    "Aim Angle": "瞄准角度",
    "Spin Speed": "旋转速度",
    "Angle Change per Burst": "每轮角度变化",
    "Speed Change per Burst": "每轮速度变化",
    "Random Speed Variation": "随机速度变化",
    "Fixed Value": "固定值",
    "Curve": "曲线",
    "Variable": "变量",
    "Expression": "表达式",
    "Angle Offset Per Burst": "每轮角度变化",
    "Speed Offset Per Burst": "每轮速度变化",
    "Script extension: ": "脚本扩展：",
    "No script extension is attached. This pattern uses the standard editor behavior.": "当前没有脚本扩展，此弹幕使用编辑器的标准行为。",
    "Expand the structure below to learn how the preset works. Parameter changes remain editable.": "下方结构用于理解预设的组成，所有参数仍可直接调整。",
    "PySTG Editor": "PySTG 编辑器",
    "&File": "文件(&F)",
    "&Edit": "编辑(&E)",
    "&Run": "运行(&R)",
    "&Tools": "工具(&T)",
    "&Language": "语言(&L)",
    "New Scene": "新建场景",
    "New Pattern": "新建弹幕",
    "Untitled Scene": "未命名场景",
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
    # Tools menu: external editor plugin titles and their tooltips.
    "Texture Assets": "纹理资产",
    "Player": "玩家",
    "Enemy Aliases": "敌人别名",
    "Danmaku Script": "弹幕脚本",
    "Dialog Balloon": "对话气泡",
    "Dialog Portrait": "对话立绘",
    "Main Menu": "主菜单",
    "Portrait Layout": "立绘布局",
    "Browse project files and JSON sprite/animation subresources.": (
        "浏览工程文件与 JSON 精灵/动画子资源。"
    ),
    "Edit bullet type and color to sprite mappings.": "编辑子弹类型与颜色到精灵的映射。",
    "Edit atlases, sprite regions, animations and laser configuration.": (
        "编辑图集、精灵区域、动画与激光配置。"
    ),
    "Edit player animation, stats, shots and options.": "编辑玩家动画、属性、射击与 Option。",
    "Edit enemy sprite aliases and atlas zones.": "编辑敌人精灵别名与图集区域。",
    "Edit data-driven stage background layers.": "编辑数据驱动的关卡背景层。",
    "Edit bullet patterns, timelines and generated async code.": (
        "编辑弹幕、时间线与生成的异步代码。"
    ),
    "Edit dialog balloon assembly and layout.": "编辑对话气泡的组装与布局。",
    "Edit dialog portrait placement and appearance.": "编辑对话立绘的位置与外观。",
    "Edit the GLFW/ImGui main-menu layout.": "编辑 GLFW/ImGui 主菜单布局。",
    "Edit the GLFW/ImGui portrait render layout.": "编辑 GLFW/ImGui 立绘渲染布局。",
    "Simple Spell Setup": "简单符卡设置",
    "Stage": "关卡",
    "Scene Root": "场景根节点",
    "SceneRoot": "场景根节点",
    "Sprite": "精灵",
    "Enemy Spawner": "敌人生成器",
    "EnemySpawner": "敌人生成器",
    "Spell Card": "脚本符卡",
    "SpellCard": "脚本符卡",
    "Boss": "Boss",
    "Spell": "符卡",
    "Emitter": "发射器",
    "Pattern Instance": "弹幕实例",
    "PatternInstance": "弹幕实例",
    "Create simple Spell": "创建简单符卡",
    "Created Stage/Boss/Spell/Emitter/PatternInstance flow": "已创建关卡、Boss、符卡、发射器和弹幕实例",
    "Create Spell failed": "创建符卡失败",
    "Create Stage template failed": "创建关卡模板失败",
    "Create midstage skeleton": "创建道中关卡模板",
    "Create two-phase Boss skeleton": "创建两阶段 Boss 模板",
    "Add node failed": "添加对象失败",
    "Open a Scene document first": "请先打开场景文档",
    "+ Add": "+ 添加",
    "Delete": "删除",
    "Move/resize timeline clip": "移动或修剪时间线片段",
    "Add timeline track": "添加时间线轨道",
    "Delete timeline track": "删除时间线轨道",
    "Edit timeline track": "编辑时间线轨道",
    "Reorder timeline track": "调整时间线轨道顺序",
    "Add timeline clip": "添加时间线片段",
    "Delete timeline clip": "删除时间线片段",
    "Edit timeline clip": "编辑时间线片段",
    "Add timeline keyframe": "添加时间线关键帧",
    "Delete timeline keyframe": "删除时间线关键帧",
    "Edit timeline keyframe": "编辑时间线关键帧",
    "Track": "轨道",
    "Clip": "片段",
    "BGM": "背景音乐",
    "Stage BGM": "关卡背景音乐",
    "Background transition": "背景转场",
    "On encounter cleared": "敌人全灭后",
    "Continue after all enemies are defeated": "敌人全灭后继续",
    "Boss sweep": "Boss 横向移动",
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
    "Back to Parameters": "返回调整参数",
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
    "Drag between ports to connect. Del removes selection.": "从带有 I/O 标记的端口拖动以连接。按 Delete 键删除选中项。",
    "Drag E/P gizmos. Drop an Assets sprite to assign.": "拖动发射点和玩家位置控制柄。也可以从资源面板拖入精灵。",
    "Choose bullet sprite…": "选择弹幕精灵…",
    "Choose bullet sprite...": "选择弹幕精灵…",
    "This pattern is still described by its parameters. Open it as nodes to edit each step and how they connect.": "此弹幕目前只由参数描述。以节点方式打开后，即可编辑每一步以及它们之间的连接。",
    "No node selected": "未选择节点",
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
    "Delay Frames": "延迟",
    "Interval Frames": "发射间隔",
    "Burst Count": "发射轮数",
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
    "Payload [JSON]": "载荷 [JSON]",
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
    "Bullet": "弹幕",
    "Source": "子弹来源",
    "Shape": "发射形状",
    "Aim": "瞄准方式",
    "Schedule": "发射节奏",
    "Motion": "子弹运动",
    "Modifier": "每轮变化",
    "Modifiers": "每轮变化",
    "Advanced · Modifiers": "每轮变化",
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
    "Connect graph nodes": "连接节点",
    "Remove graph edge": "删除节点连线",
    "Remove graph node": "删除节点",
    "Set graph node property": "修改节点属性",
    "Set graph node properties": "修改节点属性",
    "Move graph node": "移动节点",
    "Add Layer": "添加图层",
    "Delete Layer": "删除图层",
    "Bind": "绑定",
    "Search resources…": "搜索资源…",
    "Search resources...": "搜索资源…",
    "All types": "全部类型",
    # Resource browser kind filter items come from ``kind.title()``.
    "Image": "图片",
    "Animation": "动画",
    "Ui": "界面",
    "Json": "JSON",
    "Font": "字体",
    "Shader": "着色器",
    "Text": "文本",
    # Variable declaration vocabulary: types, scopes, and reducers.
    "bool": "布尔",
    "int": "整数",
    "float": "小数",
    "string": "文本",
    "vector2": "二维向量",
    "color": "颜色",
    "resource": "资源",
    "complex": "复合",
    "clip": "片段",
    "reaction": "反应",
    "behavior": "行为",
    "engine_snapshot": "引擎快照",
    "override": "覆盖",
    "add": "相加",
    "multiply": "相乘",
    "blend": "混合",
    "none": "无",
    # Variable mapping operations.
    "set": "赋值",
    "toggle": "切换",
    "reset": "重置",
    "State Path": "状态路径",
    "Migrate": "升级版本",
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
    "Seed": "随机种子",
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
        return "弹幕预览：" + _translate_zh(text[len("Pattern Preview: ") :])
    if text.startswith("Background: "):
        return "背景：" + text[len("Background: ") :]
    if text.startswith("UI: "):
        return "界面：" + text[len("UI: ") :]
    if text.startswith("Frame "):
        return "帧 " + text[len("Frame ") :]
    timeline_kinds = {
        "Pattern": "弹幕",
        "Movement": "移动",
        "Audio": "音频",
        "Background": "背景",
        "Event": "事件",
        "Property": "属性",
        "ScriptEvent": "脚本事件",
        "Reactive": "条件触发",
    }
    for source, target in timeline_kinds.items():
        if text == f"{source} 轨道":
            return f"{target}轨道"
        if text == f"{source} 片段":
            return f"{target}片段"
    if text.startswith("max ") and text.endswith(" bullets"):
        count = text[len("max ") : -len(" bullets")]
        if count.isdigit():
            return f"最多 {count} 发子弹"
    if text.startswith("Undo "):
        return "撤销 " + _translate_zh(text[len("Undo ") :])
    if text.startswith("Redo "):
        return "重做 " + _translate_zh(text[len("Redo ") :])
    if text.startswith("Add ") and text.endswith(" node"):
        category = text[len("Add ") : -len(" node")]
        return "添加" + _translate_zh(category.title()) + "节点"
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
        ("runtime", "游戏坐标"),
        ("deg/burst", "度/轮"),
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
        tooltip = action.toolTip()
        if not tooltip or tooltip == source.replace("&", ""):
            # Qt derives a menu action's tooltip from its text when none was set.
            # Setting it explicitly here would freeze the English wording onto an
            # otherwise translated action; leaving it implicit keeps it in step.
            continue
        remembered = _remember(action, "_pystg_i18n_tooltip", tooltip)
        translated_tooltip = manager.translate(remembered)
        action.setToolTip(translated_tooltip)
        _set_rendered(action, "_pystg_i18n_tooltip", translated_tooltip)


def _translate_combo(combo: QComboBox, manager: LanguageManager) -> None:
    if combo.isEditable():
        # An editable combo's text is author input that is written straight back
        # into the document, exactly like a line edit's contents.  Translating it
        # would rename whatever the author typed.
        return
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
        if isinstance(widget, QTabWidget):
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
    # Dock tab bars are owned by QMainWindow rather than the dock widgets, so
    # their captions do not appear in findChildren(QTabWidget).  Updating the
    # dock title normally refreshes these tabs, but some Qt builds cache the
    # original text.  Translating generic tab bars keeps tabified side panels
    # consistent without touching document tab titles.
    try:
        from src.qt_compat.QtWidgets import QTabBar

        for tab_bar in root.findChildren(QTabBar):
            if tab_bar.parent() is root or tab_bar.objectName() == "":
                current = [tab_bar.tabText(index) for index in range(tab_bar.count())]
                sources = _remember_list(tab_bar, "_pystg_i18n_tabs", current)
                rendered = []
                for index, source in enumerate(sources):
                    translated = manager.translate(source)
                    tab_bar.setTabText(index, translated)
                    rendered.append(translated)
                _set_rendered(tab_bar, "_pystg_i18n_tabs", rendered)
    except ImportError:
        pass


__all__ = [
    "LANGUAGE_CHINESE",
    "LANGUAGE_ENGLISH",
    "SUPPORTED_LANGUAGES",
    "LanguageManager",
    "translate_widget_tree",
]
