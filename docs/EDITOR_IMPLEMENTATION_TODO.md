# PySTG 代码驱动关卡编辑器实施 TODO

> 状态：Active。本文是关卡编辑器唯一的实施顺序、Gate 与完成证据记录。
> 产品契约见 [EDITOR_PRODUCT_VISION.md](EDITOR_PRODUCT_VISION.md)，工程边界见
> [EDITOR_ARCHITECTURE.md](EDITOR_ARCHITECTURE.md)。旧 Scene/Pattern/Graph 编辑器只保留在
> Git tag archive/editor-v1-f9e0798，不是兼容目标。

> 2026-10-08 当前修复约定：按维护者要求删除仓库测试套件、原生验证脚本及测试依赖。
> 下文旧 pytest/验证脚本命令只保留为历史证据，已不能作为当前工作树的执行入口或验收结论。
> 本轮通过即时源码编译、真实 Runtime、Qt 输入链和原生预览检查修复具体缺陷；不据此勾选
> 新阶段，也不替代维护者或新用户验收。

**当前维护 Evidence（2026-10-08；不更新阶段勾选）**：

- Structural：删除旧测试及测试入口；新手示例仍由普通 DSL 构成，欢迎页和引导不保存另一份
  作者数据。受影响 Python 模块的 `compileall` 与 `git diff --check` 通过。
- Runtime：独立构建并用真实 StageManager 运行示例关卡及敌人练习场，各生成 288 发／12 轮；
  同时修复导入、模板重建、任务捕获、返回值、局部时钟及受击任务重复推进。
- Native：真实 Windows 欢迎页 → 默认示例 → 数量 24 改 32 → F5 敌人练习场 → 返回关卡 →
  运行整关；两种运行目标均嵌入真实 GLFW 窗口并观察到每轮 32 发的 Trace。960×640 与
  1280×800 保持实际尺寸，引导无堆叠；坐标填写、清空、撤销和重做正常。末轮补验确认数量
  在首屏并直接获得焦点，正常取消构建回到空闲、无错误且日志栏不自动打开。
- Performance：已有局部交互测量不代表全编辑器性能验收；本次末轮新手布局不另作性能通过
  结论。预览替换时停止旧进程仍可能等待约 3 秒，尚非完全异步。
- Usability：维护者／真人新手验收 not run。上述 Agent 操作只证明指定功能链可执行。

人工复查入口：在仓库目录运行 `C:/Users/m1573/anaconda3/python.exe -m src.editor.app`，
从欢迎页按上面的 Native 操作链复查；不再使用下文历史测试脚本。

### 当前维护任务：步骤主导 UI（2026-10-10）

维护者明确选择步骤主导；本任务是 CD1–CD4 的交互维护，不新增阶段、不改历史勾选。
作者格式、Runtime、单一 Session/Undo 和显式 Run 契约保持不变。

| Owner | 允许编辑 | 必须完成 |
| --- | --- | --- |
| 协调 Agent | `src/editor/{window,onboarding,sidebars}.py`，本文、架构、产品愿景 | 步骤默认占主空间；引用打开/返回保留位置；新建并就地放置；按宽度切换预览；统一操作和文案 |
| Inspector Agent | `src/editor/inspector.py` | 常用发射参数首屏；紧凑表单；坐标与示意按需；保留所有参数和 Undo |
| 插入 Agent | `src/editor/{program_tree,node_palette}.py` | 步骤间 +、就地搜索和键盘选择；引用卡片打开；保留原拖放规则 |
| 预览/时间线 Agent | `src/editor/{preview,timeline}.py`、`session.py` 的预览状态字段 | 暂停与源码过期独立；预计/实际来源可见；不兼容目标禁止 seek；紧凑时间线 |
| 独立验证 Agent | 只读 | 复核下面输入链和边界；报告未观察类别，不更改实现 |

末轮集成修复由协调 Agent 接手 `inspector.py` 与 `timeline.py`，限于引用目标解析、
浮点输入、时长手柄命中及循环范围重置；原 owner 交接后不再并行写入这些文件。

共同禁止：`.claude/settings.local.json`、`.zcode/`、用户作者工程、生成产物、
authoring/compiler/runtime 语义、删除记录、测试/验证脚本重建、Graph/第二作者模型。
协调 Agent 独占本文状态与 Evidence。

实施顺序：导航/就地添加 → 参数/运行反馈 → 自适应布局 → 视觉统一 → 独立只读复验。
局部修复可以并行，集成前各 owner 必须交代公开接口；不得用旧历史 Gate 证明新 UI。

验收输入链：

1. 欢迎页创建普通 DSL 示例 → 步骤首屏修改数量/速度 → 坐标填写/清空 → Undo/Redo。
2. 关卡引用卡片打开波次/敌人 → 返回，原选择和滚动位置仍在；新建并放置可一次撤销。
3. 步骤之间点 + → 搜索 → 上下/Enter 插入 → Esc 取消；实际插在所点位置，空容器同样有效。
4. F5 启动真实 GLFW 预览 → 暂停 → 编辑 → 仍显示暂停且源码已改 → 返回步骤，预览不自动重建。
5. 960×640、1280×800、1480×920：默认步骤宽度可用，运行不会长期产生四个窄列，
   常用参数不被示意图挤出首屏；时间线区分当前预计/旧构建实际，不兼容范围不可 seek。
6. 保存重开仍是同一作者源码；单一 UndoStack、明确 Run、无用户内容或遗留进程被修改。

检查方式：即时 Python 编译、Qt 真实输入链、原生 PySide6/GLFW 检查和 diff check；
不添加测试脚本、不运行已删除的 pytest 套件。结果分别记为 Structural、Runtime、Native、
Performance、Usability；真人验收未发生时仍为 not run。

**本任务 Evidence（2026-10-10；交互维护完成，不更新阶段勾选）**：

- Structural：受影响的八个编辑器模块 `compileall`、`pyflakes` 通过；
  `git diff --check` 与 cached check 通过；`npm run docs:build` 成功（19.44s，保留大 chunk
  警告，不据此声明编辑器性能）。未参与实现的验证 Agent 以即时 Qt 输入链复验
  960/1280/1480 三尺寸、常用参数首屏、完整浮点精度保存重解析、引用打开/返回与滚动恢复、
  Before/After/Child 插入、新建定义和引用的一次 Undo/Redo、Task 两种动作与 Boss 阶段。
  同选择参数编辑不跳视口；相邻时间块右缘正确命中，正文拖动不改时长；循环范围只在换内容
  时重置。裸 ID 与重复中文名引用均正确保存 ID 和打开目标。该组检查为 offscreen Qt，
  不冒充 Native。未恢复测试套件或新增验证脚本。
- Runtime：临时普通 DSL 示例由现有构建流程验证后启动真实 Runtime。敌人练习场的
  Trace 观察每轮 `emitted=32`；暂停后改为 40，再明确运行整关观察 `emitted=40`，
  整关正常结束且无错误。生成包保留在临时备份目录，不留在仓库生成目录。
- Native：真实 Windows PySide6 与 GLFW 子窗口操作：1280×800 修改数量、输入
  `1.234567890123`、F5、暂停、返回步骤、修改数量；源码精确保存，暂停/旧构建状态保持，
  子窗口未因编辑被替换。实际 960×640 首屏与插入搜索链也已观察；1480×920 仅 Qt 布局
  检查，不声明该尺寸原生验收。最新补丁的真实相邻 Wait 手柄链 `240 -> 291 -> Undo 240`
  通过。复现入口为下方启动命令及上述六条输入链；Agent 操作不是真人验收。
- Performance：not run（本轮未重新测量整体预算）。已有大型程序刷新与停止旧预览可能
  阻塞的问题仍未纳入本次修复，不声明性能通过。
- Usability：维护者／真人新手验收 not run。现在可交由维护者试用，但不宣称新手已认可。

本轮启动：`C:/Users/m1573/anaconda3/python.exe -m src.editor.app`。
编译／静态检查：分别运行 `python -m compileall -q`、`python -m pyflakes`，参数为
`src/editor/{window,sidebars,inspector,program_tree,node_palette,preview,timeline,session}.py`
展开后的八个路径（PowerShell 不使用花括号展开）。

阅读入口：判断进度先看第 2 节及对应 Evidence；修复具体问题时再读第 3 节、相关阶段的
任务与 Gate。第 1 节描述路线建立时的基线，第 9 节用于阶段/路线最终验收。
整体产品或架构调整仍需完整阅读本文及架构文档。

### 当前维护任务：截图暴露的显示混乱（2026-10-10）

维护者截图证明，上一轮可执行输入链不代表信息含义与绘制已经清晰。此次仅修显示与浏览入口。

| Owner | 路径 allowlist | 必须完成 |
| --- | --- | --- |
| 协调 Agent | `window.py`、`program_tree.py`、`sidebars.py` 的活动页标签及文档 | 源码页说明用途与显示中文内容名称；去重复空槽/无意义标题；保留精确插入与 Undo |
| 资源 Agent | `session.py` 的资源扫描、`sidebars.py` 的资源控件 | 排除开发配置与隐藏缓存；分类/搜索/短名称；不改变 res:// 拖拽及本关显式引用 |
| 时间线 Agent | `timeline.py` | 短块文字不挤入区间；层级分开；初次适应视口；不改真实时间与 seek/编辑语义 |
| 独立验证 Agent | 只读 | 复验实际布局和输入链；不沿用上一轮通过结论 |

denylist：用户工程（包括 `my_game`、`my_game_2`）、`.claude/settings.local.json`、`.zcode/`、
作者/compiler/runtime 语义、生成产物及测试/验证脚本。协调 Agent 独占本文 Evidence。

验收：资源页无截图中的 package/config/隐藏缓存，搜索与分类后 URI 拖拽不变；源码页名称与
文件 tooltip 对应，单击显示只读源码；非空容器不画重复尾槽，空 If/Parallel 分支仍有正确
CHILD 落点；根/容器前后插入与一次 Undo 有效；短等待、同帧动作、父容器与叶节点不再叠字。
Native 必须查看真实 Windows 窗并执行点击/搜索/插入，Qt/offscreen 几何检查独立记录。

**本任务 Evidence（2026-10-10；截图对应修复完成，不更新阶段勾选）**：

- Structural：`window.py`、`program_tree.py`、`sidebars.py`、`session.py`、`timeline.py`
  的 `compileall`、`pyflakes` 通过，diff/cached check 通过。未参与实现的验证 Agent
  独立复验资源扫描、搜索/分类和原始 URI MIME、中文文件名/路径提示/只读导航、根与空
  分支的 Before/After/Child 插入及一次 Undo/Redo。非空容器没有重复尾槽或无意义标题。
  时间线父子独立行，1 帧在 0.25px/帧时仍只绘制 0.25px；Unknown 在非时间区。
  Qt/offscreen 下复验横纵滚动、固定表头命中、Wait/duration/At 拖动及 Undo、同内容
  手动缩放保留；960/1280/1480 三尺寸通过。复核中实际发现 viewport70px、scroll92px
  所有名称消失，修复后同条件可显示完整文字，100×3px 局部重绘也保留正确文字布局。
  这些是 Structural/Qt 证据，不冒充 Native。未恢复测试或新增验证脚本。
- Runtime：临时普通 DSL 示例经现有独立子进程构建验证后启动真实敌人练习场，运行记录
  实际进入时间线且无预览错误；不更改作者/compiler/runtime 语义。临时生成包在结束后
  移至系统 Temp 备份，用户工程保持不变。
- Native：真实 Windows PySide6 960×640 窗口中检查资源页（767 项，`bullet` 搜索
  为 39 项）、中文源码名称单击打开对应只读代码、编辑步骤按钮返回；就地 + → 输入
  “等待” → Enter 在循环内部正确插入 → 单次 Undo 恢复。真实等待右缘
  `30 -> 60 -> Undo 30` 通过。最终补丁重启后，实际滚动到 92px 仍显示完整“等待 30 帧”
  且标尺常驻；展开 320px 后示例五行完整可读。F5 实际嵌入 GLFW 游戏画面，运行橙线
  出现，停止后运行记录保留且子进程退出。其它尺寸只有 Qt 几何检查，不声明原生通过。
- Performance：not run（未重测大型程序刷新、构建、停止预览等预算）。文档构建
  `npm run docs:build` 成功（18.82s，保留大 chunk 警告），不是编辑器性能证据。
- Usability：维护者／真人新手验收 not run；Agent 操作只证明上述输入链与显示。

复查入口：`C:/Users/m1573/anaconda3/python.exe -m src.editor.app`，打开入门示例后依次
检查资源/源码页、循环内 +、等待右缘及 Undo、时间线展开与滚动、F5 和停止。
即时检查：`python -m compileall -q` 与 `python -m pyflakes`，参数为上面五个完整编辑器
文件路径；另运行 `git diff --check`、`git diff --cached --check` 与 `npm run docs:build`。

## 1. 本轮要解决的问题

本轮不再为“有一个节点库、一个时间线或一个预览窗口”而继续堆界面。目标是让第一次打开
编辑器的作者，能连续完成一个小关卡，并且始终知道自己正在编辑什么、下一步可以做什么、
运行后发生了什么。

唯一真源仍是 game_content/authoring/<project_id>/ 下受限的声明式 Python。程序流、节点库、
Inspector、资产选择、预览和 Timeline 都只能生成、解释或运行这份 Python；它们不能变成
Graph、JSON、静态弹幕描述或第二套作者模型。

本轮的产品验收主线固定为：

~~~text
打开工程
  -> 自动进入可执行的开始 Stage
  -> 新建 Wave / Enemy / Spell 等逻辑单元
  -> 把逻辑单元和节点直接拖入线性程序流
  -> 调整弹型、位置、运动、引用和资源
  -> 手动运行真实游戏预览
  -> 用 Timeline 阅读节奏、实际分支和弹幕密度
  -> 保存、重开、Undo/Redo，并再次运行
~~~

任何功能若不能让这条主线更短、更明确或更可靠，就不在本轮加入。

本轮建立时的起点为提交 697d9a5 之后的工作树：声明式 Python、生成器、真实预览、初版程序流、
Inspector 和 Timeline 当时已存在，但尚未完成本轮 Gate。以下问题是基线记录，不能据此判断
当前工作树仍有同一缺陷；后续进度与验收范围见第 2 节及各阶段 Evidence。第三方或实验性改动
不能自动视为正确实现；每个阶段的 owner 必须先逐项理解、测试并只保留符合本契约的部分。
不得为了清理实验改动而覆盖用户已有修改。

基线评审确认的体验问题包括：

- 合法工程可能先落在无执行体的 Project；Project 或 Boss 的悬停插入与真正提交的规则
  不一致；
- 新作者看不到 Stage、Wave、Boss、Enemy、Spell、Task 和 Function 如何共同组成一关；
- 现有拖放把很小的卡片放进大面积的四区猜测面板，引用又会被模态窗口打断；
- Inspector 的数值编辑在输入 0、清空或校验失败时可能在 Qt 信号派发中重建自身并崩溃；
- 发射参数的可发现性和 Runtime 语义不完全一致，批量路径不能静默丢弃作者参数；
- Timeline 混合画父容器、叶节点、零时长动作和动态未知，且实际 Trace 覆盖预计值，无法
  用来判断节奏和弹幕压力。

## 2. 固定顺序与完成规则

~~~text
CD0 -> CD1 -> CD2 -> CD3 -> CD4
~~~

| ID | 任务 | 状态 | 依赖 |
| --- | --- | --- | --- |
| CD0 | 基线正确性、无崩溃输入与 Runtime 参数一致性 | [x] | 697d9a5 |
| CD1 | 关卡组织与首次创作路径 | [x] | CD0 |
| CD2 | 直接拖拽的线性程序流 | [x] | CD1 |
| CD3 | Inspector、弹幕设计与预览反馈 | [x] | CD2 |
| CD4 | Timeline 节奏阅读、复杂弹幕证明与真人验收 | [x] | CD3 |

下列结论来自各阶段所记录的提交、日期和命令，不代表任意后续工作树已复验；Evidence 内的
“当前”“未提交”等措辞均指记录当时。表中勾选保留原有技术验收记录，不代表真人验收完成。

按已有 Evidence，CD0-CD4 的 focused、Runtime 与真实 Windows 原生门禁均已通过独立只读复验。真人 Usability
验收仍为 not run：维护者按第 1 节主线完成真实操作前，不得把 Usability 标为 PASS，也不得
宣称本轮路线"无需维护者验收即完全完成"。

推进新阶段时只能领取最早未完成任务。当前 Gate 有一项为红，不得以“先做 UI”或“先补一个功能”为由
开始下一项。已实现阶段可以开展边界明确的修复和回归验证；全部技术阶段已勾选也不阻止维护，
但修复测试不能替代整阶段复验或补记真人 Usability。协调 Agent 是唯一可以更新本表和 Evidence 的人；未参与实现的验证者执行
最终只读 Gate。

## 3. 全阶段不变契约

1. 不引入 Graph、JSON 作者格式、独立 Timeline 文档、Preset/Descriptor 参数系统、插件
   市场、旧格式 importer、第二运行时或逐子弹 Python callback。
2. src.authoring、src.compiler、Timeline 分析和预览协议保持 headless；不得导入 Qt、
   editor widget 或 renderer。
3. EditorSession 是一个工程的唯一状态所有者。全部编辑都进入同一个 QUndoStack；外部修改
   只能明确 keep/reload，绝不自动合并。
4. 预览只在用户点击 Run 后保存、构建并启动；编辑只标记 stale。新构建失败必须保留上一次
   成功生成包与仍在运行的旧预览。
5. 资源始终是 res:// 项目相对引用，生成包不得复制资源。现有手写 Stage1-Stage3 必须继续
   经 game_content.entry 运行，编辑器不得反向解析它们。
6. 受支持的外部 Python 可以重载；不支持语法只读且逐字节保真，绝不“尽力修复”或覆盖。
7. 首版 UI 只使用简体中文；Python API、逻辑单元 ID、源码和生成代码使用英文。
8. 不用增加面板、名词或配置层掩盖交互问题。需要新参数时先确认它是 Runtime 的真实公开
   能力，再在 DSL、生成器、Inspector 和 parity 测试中一次完成。

每个阶段开始前必须：

1. 执行 git status --short，保护用户修改；尤其不得修改、暂存、还原或提交
   .claude/settings.local.json。
2. 在该阶段记录中写明一个 owner、明确 allowlist、denylist 和与相邻阶段的边界。
3. 先阅读真实 Runtime 调用入口、当前实现和保留测试；第三方新增代码按未验证输入处理。
4. 用最窄的行为测试迭代；不得用大量内部类名测试、skip、xfail、静默 fallback 或假预览
   代替真实路径。
5. 最终由未参与实现者只读复验。通过后只更新本阶段 checkbox 和唯一 Evidence 段。

每个 Evidence 必须分别报告：

- Structural：文件、符号、依赖和唯一真源边界；
- Runtime：真实 compiler/import/StageManager/游戏循环；
- Native：真实 PySide6 + GLFW/ModernGL 窗口、嵌入和交互；
- Performance：构建、预览、测试和交互响应时间；
- Usability：维护者的真实操作；未做则写 not run。

文件存在、import 成功、offscreen Qt、截图或 pytest 总数都不能替代其它类别。

## 4. CD0：基线正确性、无崩溃输入与 Runtime 参数一致性

**Owner**：Authoring/Runtime correctness Agent。

**允许路径**：src/authoring/{program,dsl,python_source}.py、必要的
src/compiler/{codegen,diagnostics}.py、src/game/stage/context.py、
src/game/bullet/optimized_pool.py、最小 src/editor/{session,window,program_tree,inspector}.py、
对应 focused tests、game_content/SCRIPTING.md 中的公开运动单位说明、本文 Evidence。

**禁止路径**：节点库视觉重做、关卡组织重做、Timeline 算法、预览协议、插件或资产编辑器、
作者格式迁移、现有手写 Stage1-Stage3 内容。

**实施**：

1. 用一个 headless 的 unit_accepts_statements(kind) 表达 Runtime 是否执行该逻辑单元的
   body。Project 与 Boss 不能承载 statement；Stage、Wave、Enemy、Spell、NonSpell、Task
   与 Function 可以。校验、真实插入、节点原型和 Qt 只能使用这一条规则。
2. 合法工程打开时选择 Project.start_stage；Project 显示关卡顺序摘要，Boss 显示 phases
   摘要。无效 start stage 必须留下诊断，不能悄悄选错单元或显示假的空画布。
3. 修复 Inspector 的编辑事务：输入 0、负数、清空、撤销、切换 Literal/Expr、失焦校验和
   字段错误都不得在 Qt 正派发信号时替换控件。无效输入保留在字段并显示原因；只有明确、
   有效的提交才改变模型和 Undo。
4. 所有现有批量发射能力使用显式 DSL 参数。弹型、颜色、tag、发射位置、速度、加速度、
   角加速度、阻尼、时间缩放、反弹、自转、渲染角、缩放、生命周期和曲线不能隐藏在通用
   kwargs 中。
5. 定义 accel 与 angle_accel 的单位和运动方程；单发、批量发射和 codegen 必须得到相同
   Pool 字段演化。Runtime 无法支持的公开参数必须构建报错，不能 pop 后丢弃。
6. 现有受支持作者源码须正常 parse/save/build；未知参数进入只读诊断，不加兼容 shim。

**Gate**：

- Project/Boss 的 palette、键盘添加、节点拖放和底层插入全部拒绝 statement；
- 合法工程首次打开直达开始 Stage；
- 0 与其它边界输入不会崩溃、冻结或制造空 Undo，字段级错误可恢复；
- 每个 Fire 变体的显式参数都可 parse/save/build，并在真实 OptimizedBulletPool 中证明单发/
  batch 的运动等价；
- 手写 Stage1-Stage3 和完整声明式示例均保持真实入口，且没有 Qt 到 authoring/compiler 的
  依赖或逐弹 callback。

**Focused evidence**：作者 DSL/源码/模型、codegen/generated-runtime、Inspector 输入、
session/window 与 bullet-motion parity 测试；再运行 compileall、资产校验和 diff check。

**Evidence（2026-09-01，独立只读 Gate APPROVE）**：Structural PASS。未参与实现者完整复核
AGENTS、架构和本阶段 Gate：Program、Session、Window、Palette、ProgramFlow 对 Project/Boss
的 statement 拒绝均调用同一 unit_accepts_statements；合法 start_stage 打开 Stage、无效引用
保留 Project 诊断；authoring/compiler 没有 Qt/editor/renderer 反向 import，作者 DSL 没有
runtime_options，codegen 没有丢弃 accel/angle_accel 的 pop 路径。Runtime PASS。实际解释器
C:\Users\m1573\anaconda3\python.exe 运行 authoring DSL/source/model、codegen/generated
runtime、bullet parity、session/window/palette/program flow/inspector、完整示例和 content entry
focused 集通过（21.307s）；完整示例由真实 StageManager 运行至 dialogue end，手写
game_content.entry 注册 stage1-stage3。0 键入与 LiteralTextEdit 失焦均经 QTest/QApplication
回归；显式 Fire 参数 parse/save/build、single/batch 60 帧 Pool parity 与 delayed spawn 保留
字段均通过。compileall、资产校验（79 JSON、16 sprite configs、745 sprites、142 images，
0 error/0 warning）、git diff --check 与 cached check 全部通过。Native：not run；未启动真实
GLFW/ModernGL 嵌入，Qt 输入回归不冒充该 Gate。Performance：not run；仅记录 focused 集
21.307s，未作本阶段性能预算结论。Usability：not run；没有维护者真人完成工作流。验证者
未改动文件，.claude/settings.local.json、示例作者文件与 .zcode 均未触碰。

## 5. CD1：关卡组织与首次创作路径

**Owner**：Editor navigation Agent。

**允许路径**：src/editor/{window,session,commands,sidebars,program_tree}.py、
src/authoring/program.py 中逻辑单元创建/复制/删除、引用验证和最小查询能力、对应 focused
Qt/headless tests、本文 Evidence。

**禁止路径**：DSL/Runtime 语义、compiler/preview 协议、ProgramFlow 拖放几何、Timeline
算法、Graph、第二作者模型或自动生成资产。

**实施**：

1. 程序结构提供两个明确投影：全部单元用于文件管理；当前 Stage 调用链用于理解这一关。
   调用链显示 Stage 到 Wave、Boss、Enemy、Spell、NonSpell、Task 和 Function 的真实 Ref
   关系，循环只显示链接和诊断，绝不复制单元。
2. 提供新建、复制、删除逻辑单元的单一流程。ID 与固定目录路径创建后不变，显示名可编辑。
   新建 Stage 可加入 Project 顺序，首个 Stage 自动成为 start stage；复制会产生新 ID、新
   路径、新 UID，并只重写指向自身的 Ref。
3. 删除被引用单元必须阻止并列出可跳转的引用位置。删除已注册 Stage 时必须处理顺序；
   删除 start stage 前必须显式选择新的开始关。
4. Project 的关卡顺序和 Boss phases 是各自专用的可拖拽引用列表，不伪装成 statement 树。
   Boss 创建时需要至少一个现有 Spell/NonSpell；没有候选时给出下一步，而不是产生无效对象。
5. 从单元列表拖入可执行程序流时，直接生成唯一合法引用动作：Wave 到 RunWave、Boss 到
   RunBoss、Enemy 到 SpawnEnemy、Function 到 Call。Task 有多个语义时才显示就地锚定选择；
   没有候选时提供“新建对应单元”，不暗中选择工程中的第一个对象。
6. 新建或选择一个单元后，界面应立即进入它实际可编辑的位置，并在状态区显示下一步提示；
   不引入教程覆盖层、第二工作区或强制向导。

**Gate**：

- 新作者不看 UID 就能从空工程创建 Wave、Enemy、Spell/Boss、加入 Stage 并定位到其代码；
- 全部单元和当前 Stage 调用链都可从任意选择稳定返回，引用错误可定位；
- 项目顺序、Boss phases、引用创建、复制、删除阻断和 Undo/Redo 都只使用一个模型和一个
  UndoStack；
- 真实鼠标和键盘路径无模态 Ref 阻断；没有隐式“选择第一个可用引用”。

**Focused evidence**：逻辑单元操作与引用完整性 headless tests、导航/调用链/项目顺序 Qt
tests，以及真实 Windows 窗口中的新建与删除阻断检查。

**Evidence（2026-09-01，独立只读 Gate APPROVE）**：Structural PASS。全部单元与当前 Stage
调用链稳定投影真实 Ref，重复引用显示链接；Project 关卡顺序和 Boss 阶段使用专用引用列表。
新建、复制、删除、首个 Stage 注册、开始关替代与引用阻断都复用唯一作者模型和唯一
`QUndoStack`，authoring 保持 headless；`git diff --check` 与 cached check 通过。Runtime PASS。
实际解释器 `C:\Users\m1573\anaconda3\python.exe` 运行作者模型、逻辑单元管理、窗口、程序流、
session、content entry 与 generated runtime 定向集退出码 0；compileall 与资产校验通过。Native
PASS（CD1 范围）。真实 Windows PySide6 窗口中删除仍被两处引用的 `aimed_fairy` 被阻止并列出
准确引用位置；关闭提示后单元和引用仍存在、标题无 dirty 标记、撤销/重做均 disabled。用最新
工作树重启后，Boss 显示中文“Boss 阶段”、两条真实阶段顺序、可见移除按钮和中文下一步提示；
两个测试进程均 exit 0 且无残留窗口。Performance：not run；17.4 秒定向集只作信息，不作为
预算结论。Usability：not run；尚未由维护者完成完整新手创作主线。验证者未修改文件，
`.claude/settings.local.json`、示例作者文件和 `.zcode` 均未触碰。

## 6. CD2：直接拖拽的线性程序流

**Owner**：Editor interaction Agent。

**允许路径**：src/editor/{window,session,commands,node_palette,program_tree}.py、
src/authoring/program.py 中现有插入/移动/包裹规则的最小公开能力、focused Qt/native tests、
本文 Evidence。

**禁止路径**：逻辑单元文件管理、DSL/Runtime/renderer 语义、compiler/preview 协议、Timeline
算法、Graph 或另一份节点数据模型。

**实施**：

1. 左侧下方常驻节点库：搜索、分类折叠、兼容当前上下文过滤、显示全部、会话内最近使用。
   所有公开 DSL 节点和可解析模板均可发现；显示全部中的不兼容项灰显，并直接说明不能放置
   的原因。
2. 中央 ProgramFlow 是当前单元的从上到下块式代码投影。卡片显示中文名称、关键参数摘要、
   模板/动态/错误标记；UID 只在详情或提示中显示。空单元与空容器提供明确的首节点落点。
3. Repeat、If、At、SpawnTask 和 Parallel 直接显示嵌套内容。If 显示“条件成立/否则”；
   Parallel 在宽窗口并排、窄窗口堆叠。点击卡片同步 Inspector 和 Timeline，双击聚焦首个
   可编辑字段。
4. 彻底删除大面积四区面板和全局“插入模式”。Before/After 通过节点之间的插入线；Child
   通过容器内容区；Wrap 只通过可见包裹手柄或 Alt 拖放。已有节点只能从拖动手柄移动，
   卡片主体只选择。
5. Drop 前调用同一 headless 校验并清楚预览结果。非法目标不能释放并显示原因；Wrap 不能
   隐式吞掉已有复杂子树。多插槽容器在 Child 时显示具体分支；Parallel 支持“新建分支”。
6. 支持拖动边缘自动滚动、450ms 悬停展开、Esc 取消、折叠全部、搜索、复制/粘贴、多选、
   删除和键盘等价操作。每一次释放或粘贴只产生一个可理解的 Undo 命令。
7. 资源拖入兼容 Inspector 字段时赋值；拖到插入线只显示少量明确的动作后才创建节点，
   绝不猜测作者意图。

**Gate**：

- 新作者可连续完成“拖入引用 -> 拖入 Repeat/Wait/Fire -> 包裹 -> 调整 -> Undo/Redo”，不必
  知道四区坐标、插入模式或内部 UID；
- 节点库、ProgramFlow、保存重开和源码视图始终投影同一声明式 Python；
- Qt 测试必须发送真实拖拽事件；Windows native gate 在 1480x920 与 960x640 用物理鼠标验证
  插入线、Child、Wrap、自动滚动、复制和撤销；
- 节点库筛选/刷新小于 50ms，拖拽落点计算 p95 小于 16ms；无旧四区面板、全局插入模式或
  第二 UndoStack 残留。

**Focused evidence**：palette、ProgramFlow、真实 MIME 拖放、Undo/Redo、保存重开和资源拖放
测试；单独运行真实 Windows 拖放 verifier。

**Evidence（2026-09-02，独立只读 Gate APPROVE）**：Structural PASS。当前 ProgramFlow 只把
可见插入线、容器 landing 和专用包裹手柄解析为 Before/After、Child、Wrap；卡片主体只用于
选择，旧四区面板、全局插入模式和第二 UndoStack 均不存在。节点库、ProgramFlow、保存重开
和只读源码继续投影同一声明式 Python；独立验证者复核真实 MIME 拖放、逻辑单元引用、资源
动作、多选、拖动手柄、键盘复制/粘贴/删除及唯一 Undo 路径。Runtime：not run；本次 CD2
只读复验未重复运行 StageManager 或生成关卡，未把 UI 门禁冒充 Runtime 证据。Native PASS。
清除 `QT_QPA_PLATFORM` 后用实际解释器 `C:\Users\m1573\anaconda3\python.exe` 运行
`tools/verify_native_code_editor_dragflow.py --json`：真实 Windows/PySide6 顶层窗口在 1480×920
与 960×640 均保持 Inspector 和永久 Timeline 可见，物理鼠标分别完成插入线、Child、Wrap 和
已有节点边缘自动滚动；Ctrl+C/Ctrl+V、单次 Undo/Redo 均通过；Parallel 在 559px 程序流并排、
264px 程序流纵向堆叠，实际窗口尺寸未被最小宽度撑大。Performance PASS。独立验证者运行
authoring/program、palette、ProgramFlow、session、window 与 external-change focused 集退出码
0；其中节点库刷新 p95 <50ms、落点命中 p95 <16ms 的预算断言通过。`compileall -q src tests
tools`、`git diff --check` 与 `git diff --cached --check` 均退出码 0。Usability：not run；维护者
尚未完成第 1 节完整真人创作主线，自动化和原生物理门禁不替代该结论。验证者保持只读，
`.claude/settings.local.json`、用户示例作者文件和 `.zcode` 均未触碰。

## 7. CD3：Inspector、弹幕设计与预览反馈

**Owner**：Inspector/authoring feedback Agent。

**允许路径**：src/editor/{inspector,node_palette,window,session,preview}.py、只读资产查询、
必要的 DSL 类型注解和既有公开 Runtime 参数映射、focused tests、本文 Evidence。

**禁止路径**：新的 Descriptor/Action Catalog/Preset 系统、资源格式变更、第二 renderer、
自动热重载、Graph、静态弹幕 JSON 或任意表达式执行器。

**实施**：

1. Inspector 用“基础、位置、发射形状、运动、外观、声音、生命周期、高级”分组展示参数；
   每个字段显示单位、默认值、合法范围、错误和建议优先修改项。字段的存在性、默认值、Ref
   类型与合法性仍只来自 DSL/headless，Qt 只持有中文文案和布局。
2. Literal、Ref、Expr、res://、列表、字典和参数表使用结构化控件。Ref 是可搜索的就地
   选择器；Expr 的补全只提供当前参数、局部变量、玩家、难度和固定 seed 随机值，不执行
   表达式。连续数值编辑合并为一个用户可理解的 Undo。
3. 读取现有 bullet alias、精灵注册和图集，为真实可用的“弹型 × 颜色”提供搜索、缩略图、
   颜色筛选和当前选择预览。坐标/圆/扇形/轨迹示意是参数图，不是第二个游戏 renderer。
4. 将“做出华丽弹幕”的基本组合明确暴露为代码工具：发射形状、速度/角速度变化、阻尼、
   反弹、曲线、tag、模板调用、Repeat/Parallel、目标玩家的 Expr 和标准移动 API。先组合
   现有 Runtime 能力；只有确定缺少真实能力时，才在 CD4 以完整 DSL/Runtime parity 增补。
5. 预览始终是显式 Run：可运行 Project、Stage 和标准练习场中的 Wave/Enemy/Spell，固定
   seed，失败从生成/运行错误映射到节点和字段。编辑后清楚标为“预览已过期”，不自动重载。
   当前选择、运行目标、构建状态和错误位置必须可见，不能只埋在日志里。

**Gate**：

- 每个公开 DSL 字段可发现、可编辑、可撤销、可保存重开；0、清空、非法值和 Expr 切换不崩溃；
- 所有可选 bullet alias 与生成 Runtime 对齐；不存在 Inspector 显示却被生成器静默丢弃的
  参数；
- 作者可以从一个 Fire 节点清楚构造圆环、扇形、瞄准、分层重复、并行和模板组合，并在真实
  预览中得到可定位的结果；
- Inspector 不使用 eval、不导入 renderer、不保存第二模型，预览不变成热重载或假 renderer。

**Focused evidence**：Inspector 输入回归、资产/弹型选择、Ref/Expr、预览目标/过期状态与
生成 Runtime parity 测试；Project、Stage、Spell 的真实运行路径。

**Evidence（2026-09-02，独立只读 Gate APPROVE）**：Structural PASS。Inspector 按基础、位置、
发射形状、运动、外观、声音、生命周期和高级分组，由 DSL 签名提供字段、默认值与类型；真实
bullet alias/atlas 只读查询提供搜索、缩略图和几何参数示意，不导入 renderer、不执行 built-in
`eval`、不保存第二模型。预览继续由单一 PreviewOwner 显式 Run，编辑只标记 stale；运行目标、
构建状态与可定位错误在窗口内可见，失败路径保留上次成功构建及旧预览。Runtime PASS。实际
解释器 `C:\Users\m1573\anaconda3\python.exe` 运行 Inspector/palette/preview/session/window、
generated-runtime 与 bullet-motion parity 聚焦集 61 项通过（16.143s）；完整示例与标准练习场
补充集 14 项通过（10.242s）。所有 Runtime alias 均解析到真实 atlas，显式 Fire 参数经生成
Runtime 与 single/batch Pool parity 验证；Project、Stage、Spell 不是仅切换 UI 标签。Native
PASS。清除 `QT_QPA_PLATFORM` 后独立运行 `tools/verify_native_code_editor_preview.py`，真实
Windows/PySide6 + GLFW/ModernGL 分别启动 Project、Stage、Spell 练习场进程，三者均完成
Win32 嵌入、作者 Trace、可见目标/构建反馈和停止清理；pause/resume/restart/seek/stop 通过，
1480×920 与 960×640 letterbox 尺寸通过，`orphan_process=false`。Performance PASS。CD3 聚焦集
16.143s，低于 60s 编辑器预算；日志/Trace 有硬上限。当前未提交工作树相对 `697d9a5` 的 CD3
产品 allowlist 累计为 +1586/-131 行，但 window/session 同时含已验收 CD0-CD2 改动，故不将其
冒充 CD3 独立净值；旧的模态参数阻断、隐藏错误反馈和单 Stage 原生门禁已被替换。`compileall
-q main.py src game_content tools tests`、资产校验（81 JSON、16 sprite configs、745 sprites、
142 images，0 error/0 warning）、`git diff --check` 与 cached check 均通过。Usability：not run；
没有维护者真人完成完整创作主线，自动化、缩略图和真实原生预览均不替代该结论。独立验证者
保持只读，受保护用户文件、`.claude/settings.local.json` 与 `.zcode` 均未触碰。

## 8. CD4：Timeline 节奏阅读、复杂弹幕证明与真人验收

**Owner**：Timeline/Runtime acceptance Agent。

**允许路径**：src/authoring/timeline.py、src/editor/timeline.py、预览 Trace 与有界指标接线、
必要的显式 DSL/compiler/runtime 批量能力、完整声明式示例、focused runtime/Qt/native tests、
产品文档和本文 Evidence。

**禁止路径**：独立 Timeline 作者文档、任意条件/循环重写、逐弹 callback、第二预览模式、
路径 Graph、Preset marketplace、插件 SDK、安全沙箱、自动依赖安装或旧编辑器兼容层。

**实施**：

1. Timeline 只解释代码和本次运行：父容器为章节背景/括号，叶节点为真实区间，零时长动作
   为 milestone，Repeat 为聚合，Parallel 为独立泳道，SpawnTask 不阻塞主游标。动态循环、
   RawPython、动态 Expr 和未知模板明确显示“动态未知”，后续节点仍保留源顺序。
2. 静态预计和同一次 run identity 的实际 Trace 并列显示，不能互相覆盖。Trace 只提供节点
   边界、实际分支和固定采样的 emitted/live/laser 聚合指标；它不改源码、dirty 或 Undo，
   也绝不为每颗子弹安装回调。
3. 让 Timeline 回答作者真正关心的节奏问题：这一段等待多久、哪一段并行、弹幕何时变密、
   当前预览走了哪个分支。加入适应全部/选择、居中播放头、缩放、范围循环及当前单元/当前
   Stage scope，但不把它变成第二个编辑器。
4. 反向编辑仅限已经证明是字面量的 Wait.frames、duration 与 At.frame；其它节点不可拖动，
   不隐式插入 Wait、不改写条件或循环。
5. 仅当真实 Runtime 缺少创作主线必需能力时，补齐 batch tag 操作、easing/Bezier/orbit
   移动或其它明确能力；每一项同时有显式 DSL、生成、Pool/Runtime 实现和单发/批量 parity
   测试。模板用于环、镜像、交错和多层组合；RawPython 只留给真正复杂算法。
6. 提交一个受版本控制的完整声明式工程：至少一个 Stage、两个 Wave、两种 Enemy、一个 Boss、
   一个 NonSpell、一个 Spell、参数化 Task、保留调用的模板、Parallel、RawPython、BGM、
   背景、SE 和对话资源引用。它必须支持 Project/Stage/Spell 预览，并同时含静态可计算与
   动态未知的 Timeline 区间；生成目录不得入库。
7. 维护者按第 1 节主线真实操作：新建 Wave/Enemy/Spell，建立引用，拖出 Repeat/Wait/Fire，
   包裹和调整节点，选择弹型颜色，运行预览，读 Timeline，保存重开，并 Undo/Redo。关键
   阻断、崩溃或无法理解步骤即为 Usability FAIL。

**Gate**：

- 完整示例和手写 Stage1-Stage3 都由真实 StageManager 运行，固定 seed 一致，批量路径零
  逐弹 Python callback；
- Timeline 能同时清楚阅读章节、引用单元、并行、Repeat、动态未知、预计/实际和有界密度；
  节点/Timeline 双向选择和三种反向编辑均可撤销；
- Project、Stage、Spell 的真实 GLFW/ModernGL 窗口在编辑器中嵌入、获得键盘焦点，并可暂停、
  恢复、seek、停止且不遗留进程；
- 维护者完成真实主线后才可将 Usability 标为 PASS；没有真人操作时必须写 not run。

**Focused evidence**：CD0-CD3 focused gates、timeline projection/trace/metrics、完整示例、
生成 Runtime/Pool parity、真实 Windows embedding verifier。最后才运行完整仓库测试。

**Evidence（2026-09-03，两个未参与实现的独立只读验证 Agent 均 APPROVE）**：Structural
PASS。验证者一复核：`src/authoring/timeline.py` 仅依赖标准库与同级 authoring 模块，
`overlay_trace` 只以 `replace()` 写 `observed_*`，静态 `start/end` 永不被 Trace 覆盖；
RawPython/While/动态 Repeat/动态 Expr/未知模板传播 Unknown 且后续节点保持源顺序（headless
与 painted x 顺序双重断言）；Repeat 聚合、Parallel 泳道、SpawnTask 不阻塞、零时长
milestone 均有对应测试。`src/editor/timeline.py` 的 `edit_interval` 只接受字面量
Wait.frames/duration/At.frame 并进入唯一 `QUndoStack`（src/editor 仅 session.py 一处
`QUndoStack` 实例化）；程序流选择经 `_reveal_selected` 自动滚动定位；fit 全部/选择、居中
播放头、缩放、范围循环与当前单元/当前 Stage scope 均在。codegen 仅在作者节点边界
try/finally 包裹 `_pystg_trace`（TemplateCall 整体一次），StageContext/StageManager 为
有界 deque(4096)+丢弃计数；预览进程每 12 帧从 `spawned_total`/`alive.sum()`/laser 计数
聚合出 emitted/live/lasers（无逐弹钩子）；协议保持 64KB 行上限、256 事件批量与固定事件
集。完整示例含 1 Project/Stage/Boss/NonSpell/Spell/Task/Function、2 Wave、2 Enemy、
参数化 Task（经 SpawnTask 传参）、保留 `ring_burst` 模板调用与 `Call`、Parallel、
RawPython、res:// BGM/背景/SE/对话；`stage_intro_wait` 0..30 与 `spell_raw_python`
Unknown 共存；`game_content/generated/` 被 gitignore 且未跟踪；无 Qt/renderer 反向
import、无第二作者模型、无禁止概念回归。Runtime PASS。实际解释器
`C:\Users\m1573\anaconda3\python.exe` 运行 runtime focused 集 47 项通过（11.70s）：完整
示例由真实 StageManager 运行至对话结束，手写 stage1-stage3 经 `game_content.entry` 各真实
运行 180 帧；固定 seed 1337 两次完整 StageManager 运行的 Trace 事件流与弹幕 pos/vel 字节
快照完全一致；demo 与手写关卡 `pool.emitter_callbacks == {}` 且 `batch_spawn_calls > 0`
（批量路径零逐弹 Python callback）。editor focused 集 77 项通过（19.36s）。Native PASS。
清除 `QT_QPA_PLATFORM` 后独立重跑 `tools/verify_native_code_editor_preview.py`：以完整
示例工程 `game_content/authoring/code_editor_demo` 真实启动 Project、Stage、Spell 练习场
三个 GLFW/ModernGL 进程，全部完成 Win32 嵌入、键盘焦点（`focus_game`）、暂停/恢复/
seek(180)/restart/stop，`qt_platform=windows`、`orphan_process=false`，并断言
`stage_intro_wait` 静态 0..30 与 `spell_raw_python` 静态 Unknown 均未被实际 Trace 覆盖。
`tools/verify_native_code_editor_dragflow.py --json` 在 1480×920 与 960×640 完成物理鼠标
after/child/wrap 落点、边缘自动滚动、复制/粘贴与撤销/重做；本次修复了该 verifier 在 125%
显示缩放下 Qt 逻辑坐标与 Win32 物理光标 1.25 倍错位的 DPI 缺陷（`SetCursorPos` 前统一乘
`devicePixelRatioF()`）。Performance PASS。`test_timeline_2000_interval_layout_and_zoom_
p95_is_below_budget` 以 10 次预热加 `gc.collect()` 后采样，2,000 区间缩放/布局 p95 < 33ms
通过；本轮 focused 集 runtime 11.70s、editor 19.36s 均低于预算。当前未提交工作树相对
`697d9a5` 累计 46 文件 +6080/-1667（含已验收 CD0-CD3 改动，不冒充 CD4 独立净值）；CD4
本轮净增：节点→Timeline 自动定位、真实鼠标拖拽反向编辑、动态未知后源顺序、固定 seed
确定性测试、demo 与手写关卡零逐弹断言，以及两个 verifier 的完整示例工程/逐目标控制/静态
保持断言。Usability：not run；没有维护者真人完成第 1 节完整创作主线，自动化与原生门禁
不替代该结论。最终门禁：`python -m pytest -q` 512 项全部通过（0 failed/0 error/
0 skipped）、`compileall -q main.py src game_content tools tests` 通过、资产校验（81
JSON、16 sprite configs、745 sprites、142 images，0 error/0 warning）通过、
`git diff --check` 与 cached check 通过；CD0-CD3 focused 集在本工作树回归通过。验证者
均保持只读，`.claude/settings.local.json` 与 `.zcode` 未触碰。注意：
`game_content/authoring/code_editor_demo/functions/mark_wave.py` 目前未跟踪，需随维护者
提交工作树一并入库，方满足"受版本控制完整工程"的字面要求。

Gate 后补充（2026-09-03，提交 93fa5cf 之后的消融测试与质量修复）：以 14 个破坏性变异
做消融测试，逐一验证实现行为确实被测试捕获：Trace 覆盖静态预计、RawPython 投影为静态、
SpawnTask 阻塞主游标、动态 Wait 标记可编辑、移除字面量反向编辑守卫、reveal 失效、密度
指标丢失、生成代码不发射 Trace、批量计数移除、seed 常量漂移、main.py 接线回退、动态未知
源顺序丢失、确定性测试敏感性（交替分配顺序）——全部 KILLED。两个 survivor 已修复：内联
body 的 SpawnTask 不阻塞规则没有任何测试（新增
`test_inline_spawn_task_body_does_not_block_the_main_cursor` 后重验 KILLED）；
`TimelineCanvas.interval_clicked` 是无连接方的死信号（移除）。质量修复：预览固定 seed
默认值单源化为 `src.core.preview_protocol.PREVIEW_DEFAULT_SEED`（main.py 回退与
`PreviewOwner` 默认共用，配 inspect+接线守卫测试，两个漂移变异均 KILLED）；pyflakes
清理 main.py 未用 import 与死变量（`clock.tick` 保留调用仅去绑定）、preview.py 未用
import、示例工程 crossing_wave 中遗留的机器生成 `Set('i', 0)` 节点。修复后重跑：全量
514 项测试通过（0 failed/0 skipped）、compileall、资产校验、`git diff --check`、两个
真实 Windows 原生 verifier 均再次 PASS。

## 9. 预算、最终门禁与报告格式

目标预算：DSL/compiler 快速集小于 15 秒；编辑器自动化小于 60 秒；PR 主门禁小于 5 分钟。
节点库筛选/刷新小于 50ms，拖拽落点计算 p95 小于 16ms，2,000 个 Timeline 投影元素的平移/
缩放 p95 小于 33ms。每阶段必须报告产品代码净增、净删、删除的旧交互和实际性能变化；
不得通过删断言、skip 或 xfail 把红灯变绿。

以下是阶段/路线最终验收门禁，迭代时先运行相关 focused gate。仅修改文档措辞、链接或导航时，
检查链接、示例入口与文档构建即可；这类检查不改变阶段状态，也不算 Runtime、Native 或 Usability 证据。

最终门禁：

~~~powershell
python -m pytest -q
python -m compileall -q main.py src game_content tools tests
python tools/validate_assets.py --format json
git diff --check
git diff --cached --check
~~~

真实 Windows 门禁必须清除 QT_QPA_PLATFORM 后单独运行；offscreen 和截图不冒充原生嵌入。
记录命令时必须写明实际 Python 解释器，避免 Windows Store 空别名被误报为测试通过。

阶段/路线最终验收报告必须逐项写明：

~~~text
Structural: PASS/FAIL/not run + 命令与结果
Runtime: PASS/FAIL/not run + 手写关卡与生成示例真实路径
Native: PASS/FAIL/not run + 窗口、嵌入、焦点、控制与尺寸
Performance: PASS/FAIL/not run + 时间、交互响应与代码变化
Usability: PASS/FAIL/not run + 维护者真实工作流；不得合成
~~~

任何未观察类别不得暗示通过。
