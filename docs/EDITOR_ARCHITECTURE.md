# 代码驱动关卡编辑器架构

本文定义 PySTG 代码驱动关卡编辑器的稳定工程边界。产品行为见
[`EDITOR_PRODUCT_VISION.md`](EDITOR_PRODUCT_VISION.md)，实施顺序和证据见
[`EDITOR_IMPLEMENTATION_TODO.md`](EDITOR_IMPLEMENTATION_TODO.md)。

## 1. 依赖方向

```text
Qt widgets
    -> EditorSession + QUndoCommand
    -> authoring program operations
    -> restricted Python source
    -> deterministic package builder
    -> existing StageScript runtime
    -> existing StageManager / renderer / pools / audio
```

预览是独立进程：

```text
Qt PreviewOwner -> QProcess(main.py --content-entry ...)
Qt PreviewHost  <- native GLFW/ModernGL child window
Timeline        <- static program projection + bounded runtime Trace
```

以下方向禁止：

```text
src.authoring -> src.editor | Qt | renderer
src.compiler  -> src.editor | Qt | renderer
runtime       -> src.editor | Qt
generated code -> editor
timeline model -> independent saved document
panel -> second document/session/preview owner
generated package -> copied project assets
```

## 2. 目标目录与职责

```text
src/
├─ authoring/
│  ├─ __init__.py
│  ├─ program.py          # 逻辑单元、节点、值、验证、纯模型操作
│  ├─ dsl.py              # 作者公开构造函数和 @template
│  ├─ python_source.py    # AST/tokenize、加载、稳定写回、冲突状态
│  └─ templates.py        # 显式模板解析、签名、展开、递归检测
├─ compiler/
│  ├─ __init__.py
│  ├─ diagnostics.py      # 稳定 code、source span、uid、相关位置
│  ├─ codegen.py          # 逻辑单元到现有 Runtime Python
│  ├─ package_builder.py  # 临时生成、子进程验证、原子发布
│  └─ content_entry.py    # 动态加载 STAGES/START_STAGE/STAGE_BY_ID
├─ editor/
│  ├─ __init__.py
│  ├─ app.py              # CLI、QApplication、ProjectContext、窗口创建
│  ├─ window.py           # 固定布局和公开动作接线
│  ├─ session.py          # 一个工程的唯一状态所有者
│  ├─ commands.py         # QUndoCommand 模型操作
│  ├─ sidebars.py         # 程序/文件/全局资产/Stage 资产
│  ├─ node_palette.py     # 常驻节点库：搜索、兼容过滤、引用候选、模板
│  ├─ program_tree.py     # 自定义绘制纵向程序流与四区拖拽覆盖层
│  ├─ inspector.py        # 由 DSL 类型注解生成字段编辑器
│  ├─ code_view.py        # 作者/生成 Python 只读查看
│  ├─ output.py           # Problems 和有界运行日志
│  ├─ timeline.py         # 静态区间、Trace overlay、有限反向编辑
│  └─ preview.py          # 单一 QProcess、协议、Win32 嵌入宿主
└─ core/
   └─ expressions.py      # UI/Background Runtime 共用表达式能力

game_content/
├─ authoring/<project_id>/...  # 唯一作者真源
├─ generated/<project_id>/...  # gitignored 构建结果
├─ entry.py                    # 手写 Stage1-Stage3 默认入口
└─ stages/stage1..stage3/      # 既有手写内容，不反向解析
```

实现可以在不增加架构层的前提下合并小文件；不得增加 Coordinator、Service、Port、
Intent、Plugin Registry、多层 DocumentManager 或第二预览模型。

## 3. Headless 作者模型

### 3.1 值

作者值的闭集为：

- `None`、`bool`、`int`、`float`、`str`；
- 上述值组成的 `list`、`tuple` 和字符串键 `dict`；
- `Ref(id: str)`；
- `Expr(source: str)`；
- `res://...` 字符串资源引用；
- `TemplateCall`，其参数仍必须属于本闭集。

模型不执行 `Expr`。生成代码在对应 Runtime 函数上下文原样表达它，并把错误映射回节点。
Inspector 的列表、字典和参数默认值文本必须调用 headless `parse_author_value`；该解析器只
接受上述闭集及 `Ref(...)`/`Expr(...)`，不得由 Qt 使用 `eval` 或维护另一套值语法。

### 3.2 节点

所有节点共享：

```python
uid: str
kind: str
arguments: dict[str, AuthorValue]
children: dict[str, list[Node]]
source_span: SourceSpan | None
comments: NodeComments
```

公开 DSL 可以使用具体 dataclass 或带签名的构造函数，但模型必须能统一遍历、验证、复制和
生成。`uid` 在一个工程内唯一且稳定；移动节点不改变它。

### 3.3 逻辑单元

每个文件恰有一个主逻辑单元赋值。逻辑单元固定保存：

```python
kind: Project | Stage | Wave | Enemy | Boss | Spell | NonSpell | Task | Function
id: str
name: str
body: list[Node]
parameters: tuple[Parameter, ...]
metadata: dict[str, AuthorValue]
source_path: Path
```

`Project` 用引用声明 Stage 顺序和 start stage。其他单元通过 `Ref` 建立显式依赖。
解析器先收集工程内 ID，再验证引用和父子上下文。

### 3.4 纯模型操作

`program.py` 提供无 UI 副作用的操作：

- `insert_node(parent, slot, index, node)`；
- `delete_node(uid)`；
- `move_node(uid, target, placement)`；
- `wrap_node(uid, wrapper, slot)`；
- `set_argument(uid, name, value)`；
- `set_unit_field(unit_id, name, value)`。

操作在副本上先验证，成功后一次提交；失败不部分修改。Qt `QUndoCommand` 只记录操作前后
必要状态并调用这些函数，不复制领域规则。

## 4. DSL 与 Runtime 镜像

`src.authoring.dsl` 是作者唯一公开入口。节点构造函数的参数名、类型和默认值从现有
`StageScript`、`Wave`、`EnemyScript`、`SpellCard` 公共方法派生或显式镜像。

新增或修改 Runtime 公共方法时，必须在同一变更中更新 DSL 签名映射和 parity 测试。
Inspector 读取 Python 类型注解；不得维护单独的 JSON 参数描述器。

控制节点定义允许的 children slot：

| 节点 | children slot | 约束 |
| --- | --- | --- |
| `Repeat` / `While` / `ForEach` / `At` | `body` | 语句节点 |
| `If` | `body`, `else_body` | 语句节点 |
| `Parallel` | `branches` | 每支为语句列表 |
| `SpawnTask` | `body` 或 `task` | 二选一 |
| 动作节点 | 无 | 不接受子节点 |

`Break`/`Continue` 只允许在循环内，`Return` 只允许在 Task/Function 或可返回模板体中。
`RunWave`、`RunBoss` 和 Spawn 类节点验证引用目标类型。

## 5. Python 源码协议

### 5.1 允许的顶层结构

- 模块 docstring；
- 普通 `import` 和 `from ... import ...`；
- `@template` 函数定义；
- 一个主逻辑单元的简单名称赋值；
- 编辑器生成的必要注释和空行。

顶层 `for`、`while`、`if`、`with`、`try`、函数调用表达式、属性赋值、文件/网络/进程
操作以及多个主单元都进入只读诊断模式。

### 5.2 允许的表达式

主单元和节点构造只解析：

- 常量、列表、元组、字典；
- 已知 DSL 构造函数；
- `Ref`、`Expr`；
- 由显式 import 解析到的模板调用；
- 仅为负数所需的一元正负号。

不执行源码来加载工程。模板定义通过 AST 读取签名和返回结构；模板展开在受信任构建阶段
执行显式导入的模板代码。

### 5.3 注释与格式

`tokenize` 把节点前连续注释、行尾注释和逻辑单元头注释关联到稳定 `uid`。写回器采用
确定性格式：UTF-8 无 BOM、LF、四空格、按源顺序保留 import、稳定关键字参数顺序。

不支持文件保存原始字节和诊断，不生成半结构模型。只读文件的任何保存 API 都必须明确
失败，不能落入普通 formatter。

### 5.4 外部修改状态机

```text
clean + supported disk change      -> reload, clear undo
dirty + any disk change            -> conflict, freeze save
conflict + keep memory             -> explicit overwrite after confirmation
conflict + reload disk             -> replace model, clear undo
any + unsupported disk structure   -> readonly diagnostic, preserve bytes
```

新建文件在首次保存前只存在于内存；删除文件先进入可撤销墓碑。墓碑仍参与文件监视，磁盘
变化同样要求 keep/reload 决策。多文件保存保存前快照磁盘和文档元状态，任一写入失败时
两者一起回滚；失败后的再次保存不能漏掉仍在内存中的修改。单文件写入使用同目录临时文件、
flush/fsync（平台支持时）和 `os.replace`。

## 6. 模板解析与展开

`@template` 函数有稳定的 `module + qualname` identity 和 `inspect.Signature`。项目模板与
外部模板都必须由作者文件显式 import。内置模板从 `src.authoring.dsl` 显式导出。

解析阶段创建未展开的 `TemplateCall`：调用 identity、原参数 AST、解析状态、调用 span、
定义 span。保存仍输出原调用。构建阶段：

1. 按签名绑定并验证参数；
2. 将 `(template identity, bound args)` 压入调用栈；
3. 执行模板并验证返回节点；
4. 为展开节点生成只用于构建和时间分析的派生 identity；
5. 退出时弹栈。

同一 identity 在栈中再次出现即递归错误。任何异常诊断都包含调用节点 `uid` 和模板定义
位置。未知外部模板保留调用和参数但阻止构建；Timeline 显示动态未知聚合块。

## 7. 诊断

统一诊断结构：

```python
code: str
severity: error | warning | info
message: str
source_path: str
span: SourceSpan | None
unit_id: str | None
uid: str | None
related: tuple[RelatedLocation, ...]
```

稳定 code 至少覆盖：不支持语法、重复 ID/UID、未解析引用、引用类型错误、非法父子关系、
模板缺失/递归/异常、资源不存在、RawPython 语法错误、生成编译错误、入口注册错误和外部
文件冲突。

Problems 面板显示结构化诊断；Log 只显示有界进程文本。两者不能互相替代。

## 8. 确定性生成

### 8.1 生成布局

每个 Stage 拥有独立包；只把该 Stage 的传递引用闭包生成到对应分类目录。跨 Stage 共用
逻辑单元可以确定性重复生成，不产生运行时跨包隐式状态。文件名由经过验证的逻辑 ID
稳定映射，拒绝路径穿越、关键字和冲突。

根 `entry.py` 固定接口：

```python
STAGES: tuple[type[StageScript], ...]
START_STAGE: type[StageScript]
STAGE_BY_ID: dict[str, type[StageScript]]

def get_stage(stage_id: str | None = None) -> type[StageScript]: ...
```

Stage 顺序等于 `Project.stages`；`START_STAGE` 等于 `Project.start_stage`。重复或缺失 Stage
阻止构建。

### 8.2 代码生成

生成类直接继承现有 Runtime 类，`async def run()` 按节点递归输出现有 API 调用。
控制节点映射为普通 Python 控制流。`RawPython` 只插入当前生成函数体。

高密度发射保持现有批量 API；禁止生成每颗子弹的场景节点、闭包或 Python per-frame
callback。Trace 仅在作者节点边界调用轻量 emitter，并由运行时批量刷新。

### 8.3 Source map

代码生成器在写出每个节点前后记录生成行号。`source_map.json` 按稳定顺序保存：

```text
uid -> author file/start/end -> generated file/start/end
```

模板展开的错误仍映射到调用 `uid`，并在 `related` 中带模板定义。

### 8.4 事务构建

```text
validate memory model
  -> generate sibling temp directory
  -> write Python/manifest/source_map
  -> child process compileall
  -> child process import entry
  -> validate stage registry and references
  -> return prepared build
  -> preview owner stops old process
  -> atomic directory replacement
  -> preview owner starts new process
```

`PackageBuilder.prepare()` 只生成和验证临时目录，不知道 Qt 或预览进程。编辑器收到已验证
的 prepared build 后才停止旧预览并等待退出，再调用 `PackageBuilder.publish()`。发布时先把
旧正式目录原子改名为备份，再把临时目录改名为正式目录；成功后删除备份。验证失败删除临时
目录，正式目录和旧预览均保持不动；发布失败则回滚正式目录并由 preview owner 重新启动旧
构建。Windows 文件占用错误必须明确报告，不静默覆盖。CLI 构建没有预览步骤，直接 publish。

生成哈希只覆盖规范化作者语义、模板版本/源码和生成器版本，不包含绝对路径或时间戳。
同一输入连续构建必须逐字节一致。

## 9. Content entry

`src.compiler.content_entry` 验证入口模块公开接口并返回不可变注册表。`main.py` 使用
`importlib.import_module` 加载 `--content-entry`，默认值为 `game_content.entry`。

入口模块导入错误、空 Stage、重复 Stage ID、无效 start stage 都在游戏初始化前失败。
现有 Stage1-Stage3 只通过 `game_content.entry` 注册；不修改关卡类实现。

## 10. EditorSession

一个窗口恰有一个 `EditorSession`，它直接拥有：

- `ProjectContext` 和打开的作者工程；
- 当前逻辑单元和当前节点选择；
- 文件 dirty/conflict/read-only 状态；
- 一个 `QUndoStack`；
- 最近一次成功构建 identity；
- 一个预览进程状态；
- 静态 Timeline 与 Trace overlay；
- Problems 和有界 Log。

Panel 读取 Session 并调用公开命令工厂；不得自己保存第二份模型、创建第二个 Undo 栈或
直接写文件。命令首次执行和 redo 走同一模型操作，undo 恢复前态；合并连续 Inspector
编辑时必须保持一个可理解的用户动作。

## 11. Qt 布局与交互

`window.py` 组装固定工作区，不实现领域验证。Activity Bar 只切换左侧内容；中央
Editor/Game 是两个独立可关闭组，关闭后有固定菜单动作恢复。Inspector 是右侧辅助栏。
Timeline 永久挂在底部，可调高度但无关闭动作。

左侧为上下分栏：上方保留四视图，下方常驻节点库（`node_palette.py`）。节点库只
保存中文标签和类别；构造函数参数、父子规则与引用候选类型分别由 headless
`node_from_palette`、`validate_insert` 和 `reference_kinds_for_node` 推导。缺少引用候选时
节点库显示明确的新建对应逻辑单元入口。新节点拖拽使用瞬态 MIME
`application/x-pystg-node-prototype`，只携带节点或模板 identity。

中央程序流（`program_tree.py` 的 `ProgramFlow`）是自定义绘制的纵向块式投影：
每个节点一张缩进卡片；`Repeat`/`If`/`At`/`SpawnTask` 直接展示嵌套区域；空容器
显示"拖到这里添加内容"；`If` 显示"条件成立/否则"；`Parallel` 分支在宽视口并排、
窄视口纵向堆叠；支持折叠、边缘自动滚动、悬停 450ms 自动展开、Esc 取消拖动。

程序节点拖拽先计算唯一 `DropPlacement`：`BEFORE`、`AFTER`、`CHILD`、`WRAP`。
拖动期间只显示候选，释放时生成恰一个 `QUndoCommand`。Inspector 和资源拖拽同理。
放置成功后选中新节点、闪烁高亮，并把 Inspector 滚动到建议首先修改的字段。
Inspector 从 DSL 注解生成 Literal、Ref、常量/Expr、资源、列表/字典控件；Task/Function
参数使用名称/类型/默认值三列表格，提交仍进入同一个 Undo 栈。模板原型从已解析签名取得
默认参数，保存时保持模板调用而不展开。显式外部模板的节点库签名通过模块源码静态读取，
编辑/刷新节点库不得 import 或执行外部模块；可信代码只在构建展开阶段执行。
只有明确的 `res://` 语义字段显示资源拖入与文件选择；逻辑单元显示名等普通字符串使用
普通文本框，不伪装为资源字段。

作者源码和生成源码视图使用只读文本控件。受支持文件也不提供任意文本编辑器；外部编辑
由文件监视器加载。首版所有作者可见 UI 字符串为简体中文。

## 12. 资产视图

全局资产从 `ProjectContext` 根扫描稳定支持扩展名，不跟随当前工作目录。Stage 资产集合
算法：

1. 从当前 Stage 开始遍历 `Ref`；
2. 防循环并按逻辑单元 ID 稳定排序；
3. 收集参数值中显式 `res://`；
4. 验证路径仍位于项目根；
5. 不解析 `Expr` 或 `RawPython` 内字符串。

资源拖入字段前根据构造函数注解验证类型。拖入插入线时只显示该资源类型对应的明确动作
列表；用户选择后才创建节点命令。

## 13. 预览所有权与协议

`PreviewOwner` 是唯一 `QProcess` 所有者，状态为：

```text
stopped -> building -> starting -> running <-> paused
running/paused + edit -> stale
any -> stopping -> stopped
any process failure -> error -> stopped
```

Run 在临时构建完成全部验证前不停止旧预览。验证成功后，owner 发送 stop、等待有界超时、
必要时终止旧进程；确认退出后调用 builder 原子发布，再启动新进程。发布失败时 builder
回滚，owner 重新启动旧构建。编辑只把 running/paused 标为 stale。

控制消息只允许：`pause`、`resume`、`restart`、`seek`、`stop`。事件只允许：`ready`、
`state`、`frame`、`trace`、`error`、`stopped`。消息带协议版本和本次 run identity；过期
进程事件丢弃。stdout/stderr 和 Trace 队列都有硬上限。

Windows `PreviewHost` 只负责发现该 QProcess 创建的 GLFW 顶层窗口、验证 PID、保存原
window style/parent、调用 Win32 `SetParent` 和尺寸/焦点同步，并在退出时恢复/释放。
它不拥有进程、不创建备用 renderer，也不把截图当作嵌入成功。

## 14. 练习场与 seek

Project/Stage 直接使用生成入口。Wave、Enemy、Spell 由一个标准生成练习 Stage 包装，
仍通过 `StageManager` 和正式游戏循环运行。

每次 run 记录 seed、目标和构建 hash。seek 必须以相同 identity 重启，从帧 0 快进到目标
帧；快进期间关闭音频和中间帧呈现，但不跳过游戏逻辑。动态外部输入使 seek 明确标记为
不可复现。

## 15. Timeline 分析

Headless Timeline analyzer 输出 `TimelineInterval`，不序列化回作者文件：

```python
uid: str
start: int | Unknown
end: int | Unknown
lane: str
kind: static | branch | parallel | spawned | template | dynamic
editable: none | wait | duration | at
children: tuple[TimelineInterval, ...]
```

静态规则：顺序累加、`Wait` 推进、常量 Repeat 展开时间、Parallel 分泳道且 awaited 取最长、
SpawnTask 不阻塞、If 显示分支范围。动态循环、RawPython、动态 Expr 和未知模板传播
`Unknown`，不猜数值。

Trace overlay 以 run identity 和 `uid` 合并本次实际 start/end/branch。它不修改静态模型、
源文件、dirty 或 Undo。点击区间选择节点，点击节点选择对应区间。

反向编辑必须先证明目标参数是字面量：`Wait.frames`、任意声明为 `duration` 的字面量参数、
`At.frame`。除此之外 Timeline 不产生命令。

## 16. 删除边界

第二代实现不得依赖或保留以下旧产品概念：

- `PatternDocument`、`BehaviorGraph`、`PresetLibrary`；
- `TimelineClip`、`StateGraphSpec`、`ReactiveClip`；
- `StageProgram`、`StageRunner`；
- Scene 文档、变量作者系统、旧 Command/Coordinator/Service/Port/Intent；
- 旧 preview controller/worker/protocol 和 formal/legacy 双模式；
- 旧插件 SDK/Registry、Pattern Lab、Preset/Graph/Beginner workspace；
- `.pystg.json` 编辑器内容、迁移器、兼容 export 和相关测试。

共用表达式迁至 `src/core/expressions.py`，并只服务仍保留的 UI Document 与 Background
Document Runtime。`ResourceReference`/`ResourceStore` 只保留通用资源能力，移除
Pattern/Scene contribution。`src/game.events`、适配器和生命周期批处理保持不动。

## 17. 测试边界

### Headless 快速集

- AST 合法/非法与只读保真；
- UID、引用、父子、注释和稳定 round-trip；
- 外部修改和原子保存；
- 模板绑定、缺失、递归和异常；
- 确定性 codegen/source map/事务回滚；
- entry 顺序和 start stage。

### Runtime 集

- 生成全类型工程真实 import 和 `StageManager` 运行；
- 固定 seed 一致；手写 Stage1-Stage3 仍加载；
- 资产不复制；RawPython 错误映射；
- 批量弹幕路径、零逐弹 callback。

### Qt 集

- 四种侧栏、中央组恢复、Inspector、永久 Timeline；
- Before/After/Child/Wrap；Inspector/资产拖拽；
- 模板调用保留、Undo/Redo、冲突/重开；
- Run/stale/rebuild/stop；三种 Timeline 反向编辑。

### Windows native gate

- 真实 PySide6 窗口与真实 GLFW/ModernGL 子进程；
- Win32 嵌入和游戏键盘焦点；
- pause/resume/seek/stop 无遗留进程；
- 1480x920 和 960x640 都可操作。

## 18. 合并检查与预算

每阶段按 TODO 运行 focused gate。最终合并基线：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q <new fast/editor suites>
python -m compileall -q main.py src game_content tools tests
python tools/validate_assets.py --format json
git diff --check
git diff --cached --check
```

真实 Windows gate 必须清除 `QT_QPA_PLATFORM` 后单独运行。重型完整引擎测试独立执行，
不绑定每次 UI 修改。

预算：DSL/生成器快速集 <15 秒；新编辑器完整自动化 <60 秒；PR 主门禁 <5 分钟；新作者
核心、compiler、editor、preview 支持总代码目标不超过 12,000 行；最终产品代码净删除显著
大于新增。预算失败是性能证据红，不得通过删断言或跳过真实路径变绿。
