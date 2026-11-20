# 代码驱动关卡编辑器设计概览

PySTG 第二代关卡编辑器是一个以**受限声明式 Python 为唯一真源**的轻量关卡创作工具。它通过线性程序流组织代码、通过 Inspector 调整参数、通过真实游戏窗口预览效果、通过 Timeline 解释节奏与弹幕密度。

旧版 Scene / Pattern / Graph 编辑器仅封存于 Git 标签 `archive/editor-v1-f9e0798`，不再作为兼容目标。工程实现边界见 [编辑器架构](EDITOR_ARCHITECTURE.md)，阶段进度见 [编辑器开发进度](EDITOR_IMPLEMENTATION_TODO.md)。

## 1. 设计目标与受众

- **新手作者**：通过“选择逻辑单元 → 插入动作或引用 → 调整参数 → 运行预览”完成关卡，无需先熟悉引擎内部实现。
- **进阶作者**：可在外部编辑器直接修改受支持的声明式 Python 源码，也可以通过 `RawPython`、`Expr` 与 `@template` 编写自定义逻辑。
- **引擎维护者**：编辑器生成的关卡直接运行在现有 `StageScript`、`Wave`、`EnemyScript`、`SpellCard` 和 `StageManager` 之上，不引入第二套运行时。

首版界面语言为简体中文；Python API、逻辑单元 ID 和生成代码保持英文。

### 降低首次创作门槛

新建工程默认附带一个可运行的环形弹幕示例（也支持取消勾选创建空白工程）。示例由普通的 `Stage`、`Wave`、`Enemy`、`Repeat`、`FireCircle` 和 `Wait` 组成，不存在第二套预设格式。

界面始终清晰标示“当前正在编辑什么”和“按 F5 会运行什么”。常用动作与必填参数默认优先展示，进阶控制和只读源码视图按需展开。

## 2. 唯一真源与工程结构

作者工程目录固定为：

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

每个文件定义一个主逻辑单元，类型闭集为：`Project`、`Stage`、`Wave`、`Enemy`、`Boss`、`Spell`、`NonSpell`、`Task`、`Function`。顶层仅允许模块文档字符串、常规 `import`、`@template` 定义以及一个主逻辑单元赋值。

`project.py` 示例：

```python
from src.authoring.dsl import Project, Ref

project = Project(
    id="demo",
    name="编辑器完整示例",
    start_stage=Ref("stage_1"),
    stages=[Ref("stage_1")],
)
```

`stages/stage_1.py` 示例：

```python
from src.authoring.dsl import Ref, RunBoss, RunWave, SetBackground, Stage, Wait

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

- 每个节点拥有稳定的 `uid`（手写时可省略，编辑器加载后自动补全并在合法保存时写回）。
- 节点参数仅接受基础字面量、列表、字典、`Ref(...)`、`Expr("...")`、`res://` 路径以及模板参数。
- 发射节点的参数名称、默认值和语义直接镜像运行时公共 API，不维护第二套 JSON 参数描述器。

## 3. 外部编辑与保真边界

允许作者同时使用 VS Code 等外部编辑器编辑工程文件：

- 当文件无未保存改动且 Undo 栈为空时，合法的外部修改会自动重载。
- 当内存存在未保存改动或仍有 Undo 历史时，编辑器会冻结保存并提示用户选择「保留内存版本」或「重载磁盘版本」，不做静默合并或自动清空 Undo 历史。
- 遇到不受支持的 Python 顶层语法时，以**只读诊断模式**打开并完整保留原始文件内容，绝不覆写或“尽力改写”。
- 任意受信任 Python 代码片段通过 `RawPython("""...""")` 显式包裹，只在生成的目标函数体内部执行。

## 4. 程序流与节点语言

中央工作区展示当前逻辑单元的纵向线性程序流（而非场景树或节点连线图）：

- **控制流**：`Wait`、`At`、`Repeat`、`While`、`If`/`Else`、`ForEach`、`Parallel`、`SpawnTask`、`JoinTask`、`CancelTask`、`Break`、`Continue`、`Return`、`Set`、`Call`、`WaitEvent`、`EmitEvent`、`RawPython`
- **关卡流程**：`RunWave`、`RunBoss`、`SetBackground`、`PlayBGM`、`PlayDialogue`、`SpawnEnemy`
- **移动与弹幕**：`MoveTo`、`MoveLinear`、`SetPosition`、`Fire`、`FireCircle`、`FireArc`、`FireAtPlayer`、`FirePolar`、`FireOrbit`、`SelectBullets`、`TransformBullets`、`SetBulletBehavior`、`SplitBulletsOnEnd`、`ClearBulletGroup`、`ClearBullets`、`Kill`
- **音频与激光**：`PlaySE`、`CreateLaser`、`CreateBentLaser`、`RemoveLaser`、`ClearLasers`

所有节点插入、删除、移动、套进容器（「套一层」）、参数编辑、资源拖拽与 Timeline 反向编辑都进入同一个 `QUndoStack`。`Project`（管理关卡顺序）和 `Boss`（管理阶段列表）使用专用引用视图，不伪装成普通语句画布。

## 5. 模板（`@template`）

模板是普通的 Python 函数，用于封装可复用的多层环、镜像或交错弹幕结构：

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

源码中永久保留模板调用（如 `ring_burst(count=20)`），构建阶段才在内存中展开。外部模板需由源码显式 `import`，不提供插件自动发现或依赖自动安装。

## 6. 确定性构建与游戏入口

构建产物输出到 `game_content/generated/<project_id>/`（不提交 Git）：

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

- `entry.py` 暴露标准接口：`STAGES`、`START_STAGE`、`STAGE_BY_ID` 和 `get_stage(stage_id=None)`。
- 资产全部以 `res://` 引用原路径，构建产物绝不复制图片或音频文件。
- 构建先在同级临时目录完成，经独立 Python 子进程编译与导入验证后再原子替换正式目录；构建失败时保留上一次有效构建与正在运行的预览。

生成的工程可通过命令行直接脱离编辑器运行：

```bash
python main.py --content-entry game_content.generated.<project_id>.entry
```

## 7. 工作区布局与真实预览

- **步骤主导布局**：左侧提供当前关卡调用链、全部单元、只读源码与资源视图；中央默认以程序流步骤为主，支持引用跳转与返回；右侧为可切换的 Inspector；底部为紧凑 Timeline；问题列表与运行日志可折叠展开。
- **真实游戏预览**：通过独立 `QProcess` 启动真实 `main.py`（Windows 下嵌入真实 GLFW/ModernGL 子窗口）。
- **显式 Run 机制**：点击运行（`F5`）时自动保存无冲突文件、构建并启动预览；预览运行期间继续编辑源码只标记“预览已过期”，不自动热重载。
- **支持的目标**：运行整个 `Project`、当前 `Stage`，或由标准练习场包装的单个 `Wave`、`Enemy`、`Spell`。支持暂停、继续、重启、固定种子 `seek` 和停止。

## 8. Timeline 投影

Timeline 只解释源码与本次运行的 Trace，本身不是单独保存的文档：

- 顺序节点累加时间，`Wait` 推进游标；常量 `Repeat` 折叠聚合；`Parallel` 独立分泳道；`SpawnTask` 不阻塞主游标。
- `While`、动态循环、`RawPython` 与未知模板标记为“动态未知”，不凭空猜帧数，后续节点保留源码顺序。
- 静态预计与本次运行的实际 Trace 并列展示，互不覆盖，同时显示有界的发弹量/活弹数/激光数指标。
- 允许安全反向编辑的三类字面量参数：`Wait.frames`、字面量 `duration`、`At.frame`；其他节点不在时间线上隐式改写代码结构。

## 9. 明确边界（非目标）

本编辑器专注关卡玩法编排，不包含以下内容：

- 行为图 / 状态图 / 渲染图 / 独立 Timeline 保存格式
- 插件市场、插件 SDK、安全沙箱或依赖自动安装器
- 旧版 `.pystg.json` 兼容层或迁移器
- 任意 Python 代码的完整双向可视编辑
- 多工程工作区或多人协同编辑
