# PySTG 代码驱动关卡编辑器产品愿景

本文冻结 PySTG 第二代关卡编辑器的产品方向。实施顺序和状态只记录在
[`EDITOR_IMPLEMENTATION_TODO.md`](EDITOR_IMPLEMENTATION_TODO.md)，工程边界见
[`EDITOR_ARCHITECTURE.md`](EDITOR_ARCHITECTURE.md)。旧编辑器只保留在 Git 标签
`archive/editor-v1-f9e0798`，不是兼容目标。

## 1. 一句话目标

建立一个以声明式 Python 为唯一真源、以程序树帮助组织代码、以 Inspector
帮助填写参数、以真实游戏窗口预览结果、以 Timeline 解释时间的轻量关卡编辑器。

它是 LuaSTG 轻量程序树编辑器的增强版，不是把 Scene、Graph、Preset、Timeline
分别做成第二套静态数据模型。

## 2. 面向谁

- 新作者通过“选择逻辑单元 → 插入节点 → 调整参数 → 运行预览”完成关卡，不必先学习引擎内部对象。
- 熟悉 PySTG 的作者可以直接查看并编辑受支持的声明式 Python。
- 高级作者可以在 `RawPython`、`Expr`、项目模板和显式外部模板中写受信任代码。
- 引擎开发者继续维护现有 `StageScript`、`Wave`、`EnemyScript`、`SpellCard`、
  `StageManager` 和渲染/资源系统；编辑器不复制这些语义。

首版界面只有简体中文。Python API、类名、模块名和生成代码保持英文。

## 3. 唯一真源

作者工程位于：

```text
game_content/authoring/<project_id>/
├─ project.py
├─ stages/
├─ waves/
├─ enemies/
├─ bosses/
├─ spells/
├─ tasks/
└─ functions/
```

一个逻辑单元一个文件。逻辑单元只有：

- `Project`
- `Stage`
- `Wave`
- `Enemy`
- `Boss`
- `Spell`
- `NonSpell`
- `Task`
- `Function`

文件使用受限 AST 和 `src.authoring.dsl`。普通 `import` 与 `from ... import ...`
允许；顶层只允许导入、模板定义和一个主逻辑单元赋值。循环、条件、文件写入或其他
任意执行语句不能直接放在顶层。

```python
from src.authoring.dsl import Project, Ref, RunBoss, RunWave, SetBackground, Stage, Wait

project = Project(
    id="demo",
    name="编辑器完整示例",
    start_stage=Ref("stage_1"),
    stages=[Ref("stage_1")],
)

stage = Stage(
    id="stage_1",
    name="第一关",
    bgm="res://assets/audio/stage.ogg",
    body=[
        Wait(60, uid="node_intro_wait"),
        RunWave(Ref("opening_wave"), uid="node_opening"),
        SetBackground("res://assets/backgrounds/boss.json", uid="node_background"),
        RunBoss(Ref("demo_boss"), uid="node_boss"),
    ],
)
```

每个节点有稳定 `uid`。手写时可以省略，编辑器加载后在内存生成，并在下一次合法保存时
补齐。重复 `uid`、重复逻辑单元 ID、未解析引用或非法父子关系阻止保存和构建。

节点参数只接受字面量、列表、字典、`Ref(...)`、`Expr("...")`、`res://` 引用和
签名已声明的模板参数。参数名称、默认值和含义直接镜像现有 Runtime 公共 API，不维护
Descriptor、Action Catalog、Preset 参数或其他第二套语义。

## 4. 外部源码与保真边界

作者可以用外部编辑器修改受支持的声明式 Python：

- 合法且当前无未保存修改时自动重载；
- 内存有未保存修改时冻结保存，由用户选择保留内存版本或重载磁盘版本；
- 不做自动三方合并；
- 外部重载清空整个 Undo 栈并明确提示；
- 不支持的 Python 结构保留原始文本，以只读诊断模式打开；
- 只读诊断模式绝不覆盖、格式化或“尽力修复”源文件。

标准 `ast` 负责语义解析，`tokenize` 用于保留节点附近的注释。编辑器写回固定为
UTF-8、LF、四空格和稳定格式。注释不能改变语义模型。

任意受信任 Python 语句必须放入 `RawPython("""...""")`。它只在当前生成函数
内部执行，不把任意顶层 Python 伪装成可视节点。

## 5. 程序树与节点语言

中央程序编辑器显示当前逻辑单元的真实节点树，而不是 Scene Tree、蓝图或时间片集合。
首版节点语言为：

- 控制：`Wait`、`At`、`Repeat`、`While`、`If`/`Else`、`ForEach`、`Parallel`、
  `SpawnTask`、`Break`、`Continue`、`Return`、`Set`、`Call`、`RawPython`；
- 流程：`RunWave`、`RunBoss`、`SetBackground`、`PlayBGM`、`PlayDialogue`、
  `SpawnEnemy`；
- 对象与弹幕：`MoveTo`、`MoveLinear`、`SetPosition`、`Fire`、`FireCircle`、
  `FireArc`、`FireAtPlayer`、`FirePolar`、`FireOrbit`、`ClearBullets`、`Kill`；
- 音频和激光：`PlaySE`、`CreateLaser`、`CreateBentLaser`、`RemoveLaser`、
  `ClearLasers`。

拖拽节点只有四个明确结果：`Before`、`After`、`Child`、`Wrap`。非法目标在提交前
拒绝。所有插入、删除、移动、包裹、参数编辑、资源赋值和时间线反向编辑都可撤销。

## 6. 模板

模板是普通 Python 函数：

```python
from src.authoring.dsl import FireCircle, Repeat, Wait, template

@template
def ring_burst(count: int = 12, interval: int = 6):
    return [
        Repeat(
            count,
            body=[FireCircle(count=24, speed=2.0), Wait(interval)],
        )
    ]
```

源码永久保留 `ring_burst(count=20)` 这一调用，不自动物化为普通节点。构建时只在
内存展开。Timeline 把模板调用显示为一个聚合区间，不提供内部虚拟节点编辑。

内置模板、项目模板和外部模板共用同一 API。外部模板必须由源码显式 import；编辑器
不扫描目录、不使用 entry point、不安装依赖。依赖版本只写现有 `pyproject.toml`。
缺少外部包时保留调用名和原参数，但阻止构建。模板递归、签名错误和执行错误同时定位到
调用节点与定义位置。所有模板代码均被视为受信任项目代码，不增加沙箱。

## 7. 构建产物

构建目录是：

```text
game_content/generated/<project_id>/
├─ __init__.py
├─ entry.py
├─ manifest.json
├─ source_map.json
└─ stages/
   └─ <stage_id>/
      ├─ __init__.py
      ├─ stage.py
      ├─ waves/
      ├─ enemies/
      ├─ bosses/
      ├─ spells/
      ├─ tasks/
      └─ functions/
```

`entry.py` 固定公开 `STAGES`、`START_STAGE`、`STAGE_BY_ID` 和
`get_stage(stage_id=None)`。生成代码直接继承现有 Runtime 类型，不引入第二套执行器。

`manifest.json` 只记录项目 ID、构建哈希、入口模块和 Stage 列表；
`source_map.json` 只记录 `uid ↔ 作者位置 ↔ 生成行号`。它们是生成元数据，不是
作者逻辑。资产始终使用 `res://` 项目相对引用，不复制进生成包。

生成目录可查看、可运行、可删除，但整体不提交 Git。构建必须在同级临时目录完成，
经独立子进程 compile/import/注册验证后原子发布。失败保留上一次成功构建。

## 8. 游戏入口

`main.py` 支持：

```text
python main.py --content-entry game_content.generated.<project_id>.entry
```

不指定时加载 `game_content.entry`。该手写入口只注册现有 Stage1-Stage3，消除
`main.py` 中的硬编码导入，但不改变三关实现。编辑器不会反向解析这些手写关卡。

## 9. 编辑器布局

一个窗口只打开一个工程：

- 左侧 Activity Bar：程序结构、文件目录、全局资产、当前 Stage 资产；
- 中央两个可关闭、恢复和调宽的编辑组：可视化程序编辑器、嵌入式游戏画面；
- 右侧可切换辅助栏：Inspector；
- 底部：永久 Timeline，可调高度但不能关闭；
- 可折叠输出区：Problems 和运行日志，不替代 Timeline；
- 作者 DSL 与生成 Runtime Python 以只读中央标签打开。

程序结构侧栏只负责 Project、Stage 和逻辑单元导航。文件侧栏反映真实作者工程。
全局资产扫描项目；当前 Stage 资产只汇总 Stage 及传递引用单元中显式出现的 `res://`
引用。`RawPython` 内的动态字符串不猜测为资产。

资产拖到兼容 Inspector 字段时赋值；拖到节点插入线时提供少量明确动作选项，不自动猜测
作者意图。Inspector 根据 DSL 构造函数类型注解生成控件。

`EditorSession` 是唯一状态所有者：工程、当前单元、选择、dirty、`QUndoStack`、
构建状态和预览状态。首版不建立 Coordinator、Service、Port、Intent、Plugin Registry
或多层 DocumentManager。

## 10. 真实预览

预览由一个 `QProcess` 启动真实 `main.py`，Windows 下把真实 GLFW/ModernGL 子窗口
嵌入编辑器。不存在 formal/legacy 双模式。

Run 的固定行为：

1. 自动保存所有无冲突 dirty 文件；
2. 构建并验证工程；
3. 构建成功后停止旧预览并启动新预览；
4. 构建失败时保留旧生成包和仍在运行的旧预览。

修改源码后，旧预览继续运行但显示“预览已过期”。只有再次点击 Run 才重建和启动。

控制协议只有 `pause`、`resume`、`restart`、`seek`、`stop`；事件只有 `ready`、
`state`、`frame`、`trace`、`error`、`stopped`。支持运行整个 Project、当前 Stage，
以及由标准练习场包装的当前 Wave、Enemy、Spell。

预览使用固定 seed。seek 通过相同 seed 重启并在关闭音频和中间帧渲染时快速推进。
Trace 只在节点边界批量发送，长度有上限，不阻塞游戏帧，也不给每颗子弹安装回调。

## 11. Timeline

Timeline 永久可见，但只解释代码，不拥有代码：

- 顺序节点累加时间，`Wait` 推进游标；
- awaited Move、Dialogue、RunWave、RunBoss 使用明确或实际持续时间；
- 常量 `Repeat` 计算重复区间；
- `Parallel` 使用独立泳道，等待型并行取最长分支；
- `SpawnTask` 不阻塞主游标；
- `If` 显示分支范围；
- `While`、动态循环、`RawPython` 和未知外部模板显示“动态未知”；
- 运行后 Trace 覆盖本次实际分支和持续时间；
- 模板调用只显示聚合区间。

节点与区间双向选择。Timeline 唯一允许的反向编辑是：拖动 `Wait` 修改字面量帧数、
缩放带字面量 `duration` 的节点、拖动 `At(frame=...)` 修改固定帧。其他节点不可拖动；
不得隐式插入 Wait、重写条件或循环。

## 12. 完整示例的产品证明

仓库必须提交一个新的声明式示例工程，至少包括一个 Stage、两个 Wave、两种 Enemy、
一个 Boss、一个 NonSpell、一个 Spell、一个参数化 Task、一个保留调用的模板、一个
`Parallel`、一个 `RawPython`，以及 BGM、背景、SE、对话资源引用。

示例必须支持 Project、Stage、Spell 三种预览，并同时出现可静态计算与动态未知的
Timeline 区间。生成结果由测试或用户本地构建，不入库。

## 13. 明确非目标

本轮不建设：

- Recipe、Behavior Graph、State Graph、Render Graph 或独立 Timeline 文档；
- 插件市场、插件 SDK 或自动发现机制；
- 安全沙箱、依赖自动安装器或外部模板隔离；
- 旧 `.pystg.json` importer、兼容层、Legacy 菜单或隐藏开关；
- 任意 Python 的完整双向可视编辑；
- 新的资产、HUD、菜单、立绘、对话或背景编辑器；
- 非 Windows 的原生游戏窗口嵌入实现；
- 多工程工作区或多人协同编辑。

## 14. 成功标准

最终结果必须分别证明：

- Structural：旧符号、旧模块、旧内容和旧入口为零；新依赖方向成立；
- Runtime：手写 Stage1-Stage3 与新生成完整示例均走真实引擎运行；
- Native：真实 PySide6 + GLFW/ModernGL 嵌入、焦点和控制通过；
- Performance：加载、构建、预览、测试和代码体积符合预算；
- Usability：只记录维护者真实打开并完成示例流程的结果；没有真人操作就明确未验证。

DSL/生成器快速集目标 15 秒以内，新编辑器完整自动化 60 秒以内，PR 主门禁 5 分钟
以内。新作者核心、生成器、编辑器和预览支持总代码目标不超过 12,000 行，最终产品代码
净删除必须显著大于新增。测试数量不是目标；可观察行为和真实运行证据才是目标。
