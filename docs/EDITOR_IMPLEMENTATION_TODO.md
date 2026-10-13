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

### 当前维护任务：文档站构建与版本发布（2026-10-13）

Owner：协调 Agent。允许编辑 `package.json`、`package-lock.json` 与本文，以及
`game_content/examples/th06_patterns.py` 的多余末尾空行；禁止编辑引擎/编辑器代码、
作者工程、`.claude/settings.local.json`、生成包和本地游戏资源。
发布另外核对已有源码、通用示例和文档的暂存范围，不自动合并 main 或创建 PR。
本任务不新增 CD 阶段，不改变历史勾选，也不续做 TH06 内容或动画 API。

诊断：本机 Node 24.11.1、原生 esbuild 0.21.5 的 async/sync transform 在输入超过
1 MiB 时稳定复现临时文件删除 `Access is denied`；低于阈值通过。原生 0.25.12 在独立
目录通过，但相同哈希二进制在仓库仍失败，整站升级重试也失败，故不将升级记为修复。
确切拒绝访问来源未确认；不推断为杀毒、不调整系统权限。WASM 0.21.5 最小对照通过。
修复仅用 npm override 将 Vite 的 `esbuild` 替换为同版本 `esbuild-wasm`，保持
编译 API/目标和压缩；不手工修改依赖源码、TEMP 或全局环境，不关闭压缩和搜索。

验收：锁文件可经 `npm ci` 重新安装；默认 `npm.cmd run docs:build` 完整成功；
已有版本的 compileall、资产检查、diff/cached check 通过；显式暂存、提交并正常推送
当前分支，最后核对远端 SHA。当前状态：构建修复和发布前检查通过；历史失败记录仍保留。
推送结果以 Git 提交及远端分支 SHA 为准，不据此更新 TH06/CD 的完成状态。

**Evidence（2026-10-13；构建维护与发布前检查）**：

- Structural：`npm.cmd ci --no-audit --no-fund` 成功重装 236 个包；VitePress 1.6.4、
  Vite 5.4.21 保持不变，只有 Vite 的 esbuild 依赖替换为 WASM 0.21.5，锁文件中其它
  依赖记录逐项一致。仓库实际使用的后端连续五次完成 2 MiB async transform；sync、
  source map、ES2020 目标及无效语法错误传播通过。默认 `npm.cmd run docs:build`
  完成 client/server bundles 和全部页面渲染（16.35s），保留大 chunk 警告。
  `C:/Users/m1573/anaconda3/python.exe -m compileall -q main.py src game_content tools`、
  `tools/validate_assets.py --format json` 和 `git diff --check` 通过；工作树资源为
  99 JSON/16 configs/745 sprites/142 images，零错误/警告。发布时显式检查暂存区，
  不包含用户已有 `python_source.py` 修改、`stages_1_3` 工程、生成包、本地资源或私有配置。
- Runtime：本轮引擎 Runtime not run；已有机制的即时运行证据仍见下面各维护任务。
  文档构建通过不证明完整 TH06 内容或新增 API 已整体验收。
- Native / Performance / Usability：本轮 not run；没有界面改动，构建耗时不是引擎
  性能数据，也不替代真实编辑器交互或真人验收。

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

### 当前维护任务：任务生命周期与批量子弹行为（2026-10-11）

维护者授权局部整理 Runtime 再补 API，并明确要求 NumPy/Numba 和实际性能证据。
这是已实现阶段的维护，不沿用历史 Gate 作为本轮完成证明，不改 CD 勾选。

| Owner | 允许路径 | 交付边界 |
| --- | --- | --- |
| 任务 Agent | `src/game/tasks.py`、`src/game/stage/{stage_base,wave_base,enemy_script,spellcard,boss_base}.py` | 同一帧协议下的任务句柄、并行、等待、取消；死亡/结束/异常可靠清理 |
| 子弹 Agent | `src/game/bullet/{optimized_pool,behavior,__init__}.py` | 稳定弹群、批量变换、共享阶段、限次反弹、区域冷却和原位分裂；数值热循环使用 Numba |
| 渲染（协调 Agent 接手） | `src/render/optimized_bullet_renderer.py` | 实例数组直接提交；按真实 GLFW/ModernGL 图像与耗时取舍，不改变排序、混合或视觉 |
| 协调 Agent | `main.py`、`src/game/stage/{context,__init__}.py`、`src/core/{engine_session,collision}.py`、`src/content_api/{bullets,__init__}.py`、`src/authoring/{dsl,program,timeline}.py`、`src/compiler/codegen.py`、编辑器节点中文映射、`tools/preview_spell.py`、本文和架构、`game_content/SCRIPTING.md` | 帧时钟/事件接线、单位转换、正式调度 API、显式 JIT 预热、声明式入口与文档；隐藏发射器不参与玩家碰撞 |
| 独立验证 Agent | 只读 | 即时真实 Runtime、生成子进程和负载复核；明确未覆盖的 Native/Usability |

共同禁止：`.claude/settings.local.json`、用户已有 `python_source.py` 改动与
`game_content/authoring/stages_1_3/`、其它用户工程、生成产物入库、测试套件/验证脚本重建、
逐弹 Python Task/callback、第二 Runtime/renderer、Graph、作者格式迁移和 Rust 工具链。

执行顺序：现有错误修复 → 任务/帧时钟整合 → 弹群与终结处理 → 阶段/区域批量执行 →
声明式生成和集成复核。并行实现仅在路径互不交叉时进行；协调 Agent 独占文档状态。

验收要求（全部要有实际运行结果，不以文件存在为完成）：

1. 敌人击杀、符卡结束、关卡停止、异常均执行已启动任务的 `finally`；后台任务同帧不重复推进。
2. 单发/批量参数一致，不静默丢失延迟和终结参数；删除真正回收池槽，旧弹群不命中新槽位。
3. 用真实池完成“飞行 → 停顿 → 从当前位置瞄准 → 加速”、限次反弹、区域冷却变换和全母弹原位分裂。
4. 清场/Bomb 不默认触发自然终结分裂；更新中出生的子弹不因槽位顺序而部分提前更新。
5. 声明式项目保存/解析/生成/独立子进程 import/StageManager 执行走同一 Runtime；无 Qt 反向依赖。
6. 分开报告 JIT 首次编译和预热后负载：10,000/50,000 弹的普通、阶段、区域、分裂；
   与相同容量/负载旧实现比较。渲染 CPU 准备/提交和真实 GPU 路径独立报告，不能以 CPU 数字冒充 GPU。
7. 当前快速合并检查采用架构第 18 节命令；不重建 pytest 或验证脚本。Native/真人验收未发生则 not run。

状态：本轮实现已落地，下列即时检查通过的范围单独记录；完整验收未完成。Rust 不进入本轮依赖。
两个实现 owner 交接后，协调 Agent 接手公开索引快照、出生碰撞资格、生成钩子的帧时钟及 Trace 收尾。

**本任务 Evidence（2026-10-12；不更新阶段勾选）**：

- Structural：`python -m compileall -q main.py src game_content tools`、资产检查和两个 diff check
  退出码 0。独立导入 authoring/compiler 后无 Qt、editor、render 模块；新增公开导出可正常导入。
  即时 offscreen Qt 检查十种新节点的 Inspector/中文入口；子弹阶段字段不再覆盖 Project 的
  「关卡顺序」标签。OnHit/OnDeath 在 Timeline 为 Unknown，且其等待不推进敌人主游标。
  offscreen 不计 Native。聚焦 pyflakes 仍返回 8 条旧的未用变量/import 告警；用 HEAD 源码逐条
  对照一致，没有把它报告为零告警 PASS。产品差异忽略行尾空白并排除用户修改：跟踪代码
  +1423/-477，两份新模块 +503 行；移除生成 `_support` 的独立调度循环，复用正式帧任务。
  文档站点 `npm run docs:build` 两次失败（16.31s / 8.81s）：Windows 下 esbuild
  删除临时文件报 `Access denied`；第二次使用独立 TMP/TEMP 目录仍失败。未确认具体占用者，
  不把它归因于 Markdown，也不记为文档构建通过；未改依赖、系统权限或全局环境。
- Runtime：五个普通声明式作者文件用正式写回器保存，再由 AST 重开、PackageBuilder 的独立
  构建子进程编译/import，然后另一个 Python 子进程经真实 StageManager 运行 260 帧。
  结果：20 母弹 → 60 子弹、假首领受击 8 弹，共 88 弹；取消 finally 执行、事件等待/句柄
  join、死亡引用 Task 的 Parallel、At(6)/At(8) 均正确，死亡事件位于 145/147 帧，
  根钩子 start/end Trace 齐全，共 76 条作者 Trace，逐弹 callback 数 0。
  作者示例保留在系统 Temp 下 `pystg-final-runtime-g_gxvpv7/authoring`，生成包在同目录
  `generated/final_probe`，均未进入仓库。首轮六单元综合场景也实际生成 128 弹。
  真实 ItemPool 确认旧 generation 组不误转新弹，道具只从当前有效弹生成；真实 CollisionManager
  确认控制流程新弹下一次池更新才命中，隐藏发射器不命中。事件处理异常会取消已启动后台/主任务，
  二者 finally 都执行。手写 Stage1 运行 1400 帧（等待真实对话结束）产生 105 弹，Stage2/3
  各 400 帧产生 15/231 弹；这是局部兼容检查，不宣称完整通关、音频或全部 Boss 回归通过。
  未参与实现的验证者另跑 350 帧生成场景，证实受击延迟任务随死亡取消、死亡嵌套任务存活，并
  抓到当帧新弹碰撞漏洞；该漏洞已修。该验证者因额度限制在末轮渲染/Trace 收尾前终止，
  **最终全范围独立复核未完成**，不冒充正式 Gate APPROVE。
  末轮另由只读验证者发现两项缺口并复核修复：Task/Function 不能借引用链调用实际
  Stage/Wave 不具备的动作或省略 Wave 发射位置；停止关卡须在关闭任务后收集 finally Trace。
  协调 Agent 即时验证 Call/SpawnTask × 直连/嵌套 × 五种调用场景，共 20 项；合法结果全模块
  compile，非法调用在 CodeGenerator 构建前给出 `call_context`。受影响模型模块 pyflakes
  退出码 0。验证者用保留的真实生成包复现停止前两个 Running 步骤；修复后 clear 返回两条
  end Trace，全部已启动步骤闭合、任务及当前 Stage/Context 均释放。这是窄 Runtime 复核，
  仍不替代全范围独立 Gate、原生编辑器或真人验收。
  该验证者另确认共享 Task 按 Wave/Enemy 的不同调用能力分别诊断、循环引用遍历正常终止、
  模板展开后的 Task 发弹也不能绕过 `call_context`。即时内存导入完整生成包后经真实
  StageManager 运行 155 帧：Wave → Task → Function 发弹，Enemy → SpawnTask → Task →
  Parallel → Function 默认位置发弹并 Join，共 2 弹、28 条 Trace、callback=0，正常结束。
  此次新增窄检查不包含 PackageBuilder 发布流程，后者证据仍是上面的五文件 260 帧场景。
- Native：完整编辑器 PySide6/GLFW 嵌入、焦点与操作链 not run。下面真实 GLFW GPU 测量只覆盖
  渲染路径，不算编辑器原生交互通过。
- Performance：实际 Python 3.12.7、Intel Family 6 Model 151、GTX 1660 Ti；Numba 预热后，
  固定 seed 1337。普通负载与 HEAD 相同容量交替顺序，240 帧；其余负载见下表。
  两次四阶段测量是不同工作负载，分别保留，不挑更小数作为统一保证。
- Usability：维护者／真人新手验收 not run。

| 池层负载 | median / p95（ms） | 实际范围 |
| --- | --- | --- |
| 普通 10k，HEAD → 当前 | 0.183 / 0.298 → 0.184 / 0.297 | 配对稳态更新 |
| 普通 50k，HEAD → 当前 | 1.124 / 1.631 → 1.148 / 1.674 | 配对稳态更新，median +2.1% |
| 50k 共享四阶段（首轮） | 2.148 / 2.605 | 180 帧 |
| 四阶段 10k / 50k（末轮） | 0.445 / 0.679；2.503 / 2.894 | 240 帧，30 帧预热，全部保持存活 |
| 区域+冷却+四阶段 10k / 50k | 0.574 / 0.859；3.127 / 4.494 | 240 帧，包含查询/变换/更新 |
| 1k 母→4k 子；10k 母→40k 子 | 1.566 / 1.923；8.642 / 9.251 | 12 轮终结生成帧；后者旧路径单次约 30.342ms |

阶段数值状态只在使用时分配：21 字节/弹，50k 为 1.05MB；代数/碰撞资格 5 字节/弹；
每个冷却 key 为 8 字节/弹。默认弹无阶段扫描。本次全新独立 Numba 缓存目录实际首调：
运动 1098.6ms、行为运动 771.3ms、阶段 325.8ms、区域 281.8ms、渲染准备 442.0ms，合计
约 2.92s；第二次调用合计约 0.047ms，数据/代数/计数/时钟不变。这个启动编译成本未混入稳态。

真实 GLFW/ModernGL：384×448、三张现有图集、18 个类别/纹理批次，交替 HEAD/当前顺序，
40 对采样、舍弃前 8 对。10k CPU 提交 median 0.0876 → 0.0753ms；50k 0.2006 → 0.1650ms，
p95 0.3940 → 0.3446ms。50k GPU timer query median 0.5376 → 0.5849ms，p95
1.1313 → 1.0961ms，**不声称 GPU 加速**；非空帧缓冲逐字节一致。50k 的 Python 上传临时峰值
44,529 → 120 bytes（驱动/GPU 内存不在这个计量内），取消额外 Python bytes 复制，GPU 上传仍在。
CPU 分桶准备另测 median 0.361ms。每批 orphan 策略实际更慢（GPU median 约 2.03ms），没有采纳。
这些测量不代表背景、玩家、激光、UI 和呈现合起来稳定 60 FPS。

快速合并命令（仓库目录；本机使用 `C:/Users/m1573/anaconda3/python.exe`）：

```powershell
C:/Users/m1573/anaconda3/python.exe -m compileall -q main.py src game_content tools
C:/Users/m1573/anaconda3/python.exe tools/validate_assets.py --format json
git diff --check
git diff --cached --check
```

临时声明式示例可用公开加载/构建入口复跑保存结果；完整即时 stdin 场景与测量命令保留在本次
会话工具记录，不新建测试或验证脚本。API、单位、可组合例子及限制固定在
`game_content/SCRIPTING.md`。此 Evidence 截止时仍未完成持续 homing、限次穿屏、母弹转敌人；
随后扩展见下一个维护任务。完整 ECL 指令集仍未实现，不把增量 API 当作原作全部兼容。

### 当前维护任务：TH06 难例与批量数值接口（2026-10-12）

维护者授权实现批量参数、二维加速度、持续追踪、穿屏及终结转换；仅扩展正式 Runtime，
不以引擎 API 交付冒充完整 GUI 创作或原作全部脚本兼容。不改 CD 历史勾选。

| Owner | 路径 allowlist | 必须交付 |
| --- | --- | --- |
| 批量 Agent | 新 `src/game/bullet/{batch,termination}.py` | 数值快照、标量/数组对齐、Numba 距离加速度及 first-match 邻域激活；完整终结数据与队列 |
| 运动 Agent | `src/game/bullet/behavior.py`、新 `motion.py` | 共享阶段的二维加速度和限速持续追踪；运动后/销毁前的限次穿屏 |
| DSL Agent（运动 owner 交接后） | `src/authoring/dsl.py` | 四种发射与批量变换的新增字段映射；默认参数不膨胀，无新节点 |
| 协调 Agent | `src/game/bullet/{optimized_pool,__init__}.py`、`src/game/stage/{context,__init__}.py`、`src/content_api/{bullets,__init__}.py`、普通 `game_content/examples/th06_patterns.py`、本文、架构、`game_content/SCRIPTING.md` | 稳定弹群批量读写、单位/容量截断、整批规则、完整终结队列及 Enemy 桥接；公开 API 和文档 |
| 独立验证 Agent | 只读 | 真实 Runtime 与 TH 难例数学/时序对照、负载复核，不代写实现 |

禁止：用户作者工程、已有 `python_source.py` 修改、`.claude/settings.local.json`、生成产物入库、
测试/验证脚本重建、逐弹 Python 回调/Task、第二 Runtime/renderer、Graph、Rust 工具链。
批量规则只允许一组一次调用；Pool 不导入 Enemy/Qt/renderer；终结 Trace 不代替动作数据。

顺序：批量读写/二维加速度 → Stage6Func9/StageXFunc15 运行 → 追踪/穿屏 → 终结转换 → 独立复核。
验收至少包括：旧 generation 的数组参数正确对齐；池满只截断同一出生批次；TH 两个数学公式
及多源 first-match 一致；限速追踪/时间缩放/跨角度边界；高速多次穿屏及次数用完；完整终结
批次产生真实 Enemy，清场/关卡结束不再生；普通/新增能力 10k、50k 测量分开，JIT 与稳态分开。
沿用第 18 节快速合并检查及即时 stdin/独立子进程 Runtime；不重建已删除套件。

状态：引擎 API 实现和下列窄 Runtime 复核完成；不据此宣布 CD 阶段、完整编辑器或整游戏
性能预算通过。Native 和真人 Usability 仍为 not run。协调 Agent 独占本段状态。

各实现 owner 交接后，协调 Agent 接手 batch/behavior/termination 的窄集成修复：快照筛选、
阶段返回穿屏活跃数、失效 token 清理；没有并行写同一文件。连续规则复用既有 Task，
不是 Pool 中再装一套调度器。

**本任务 Evidence（2026-10-12；不更新阶段勾选）**：

- Structural：`python -m compileall -q main.py src game_content tools`、
  `python tools/validate_assets.py --format json`、`git diff --check`、cached check 均退出 0。
  资产检查 99 JSON、16 配置、745 精灵、142 图像，errors/warnings=0。
  新 batch/motion/termination、behavior、Pool、StageManager、content_api 和正常示例的
  pyflakes 无新告警；聚焦总命令仍退出 1，Context 五条和 DSL 两条未用导入已与本轮备份及
  HEAD 逐条对照相同，不冒充零告警。未恢复测试套件、未创建测试/验证脚本；用户
  `python_source.py` SHA256 仍为 `EE9E88A51DF77AE35450CE7F8AB26C38A91CF8B8DE33A05F33960192BF66B226`，
  用户作者工程、`.claude/settings.local.json` 和暂存区未修改。
  文档站点重试 `npm run docs:build` 仍失败（17.55s）：esbuild 删除 Windows Temp 文件
  `Access is denied`。具体占用者未确认，未改依赖/权限；文档构建不是 PASS。
- Runtime：两个公式经正式 Context 读/写与独立标量数学对照通过。独立验证者另用原 TH06
  `EnemyEclInstr.cpp` 对照 66 目标、平方距离阈值、共享 offset、strict 64px、source 顺序
  first-match 与不环绕的角差；不是最近来源替代。原参考仓库 commit 为
  `fa4d48f66d4701fef6c5e802ca85a738b0d5177c`，只对照机制，不运行原作资源或 ECL。
  普通 `BatchMechanicsStage` 经真实 StageManager 正常加载至结束共 1025 次更新、660 发，
  16 母弹产生 16 个真实 Enemy，出生帧 time=0；逐弹 callback=0。独立验证者另跑同示例
  950 步观察结束，以及 12 母弹完整转换、next-frame on_spawn/run、来源速度/方向、取消
  已排队、Bomb/清场/关卡停止均通过。其发现的失效转换 token 残留已修，10 轮直接
  Pool.clear_all→flush 后残留 0，新注册不被误删。
  标量/异构数组、容量一致截断、只读快照、原 N 与 cooldown 对齐、read→await→槽复用
  写回隔离、静止弹保持原方向均实际检查。规则固定空群退出、动态空 tag 等待出生、尚未
  开始就清场也结束；追踪跨 ±π、时间缩放和退出阶段；延后启用穿屏、高速多次穿越、余量
  保留、用完后出屏回收均通过。示例激活→Stage Task 停加速实测恰好 120 次池积分。
  四份普通声明式作者文件从 AST 加载，由正式 PackageBuilder 的独立子进程编译/import/
  Runtime 合同检查后发布，再由另一个 Python 子进程经 StageManager 270 帧运行结束，
  3 发出生、异构速度向量观察到、callback=0，2 条 Trace。源和生成包仅在系统 Temp
  `pystg-batch-probe-20261012`，未进入仓库生成目录。独立验证者另检查 14 个生成模块并
  实际执行生成 Enemy 发射 7 弹，位置/速度/二维加速度/弹型索引/角加速度逐值一致。
  最终独立只读窄 Runtime 复核通过，不代替完整编辑器 Gate。
- Native：not run。本轮没有改 UI、渲染提交或原生嵌入，不沿用上轮 GPU 结果当新证据。
- Performance：下表为 Python 3.12.7、同一台 Intel Family 6 Model 151 机器上的即时池层
  或明确标注的完整数值链路，Numba 预热后 median/p95。普通负载与本轮开始前备份配对，
  240 帧、弃前 30，交替先后顺序；追踪/穿屏 210 帧弃前 30；公式链路 120 帧弃前 30。
  例子关系查询 120 帧弃前 20；终结捕获 30 轮弃前 5；Enemy 创建 35 轮弃前 5。
  表中没有玩家、碰撞、激光、背景、渲染和 UI，也不证明整游戏 60 FPS。
- Usability：维护者／真人新手验收 not run。引擎 API 可用不等于纯 GUI 已覆盖。

| 负载 | 10k median/p95 ms | 50k median/p95 ms |
| --- | --- | --- |
| 普通，本轮备份 → 当前 | 0.178/0.229 → 0.186/0.240 | 1.140/1.691 → 1.182/1.679 |
| 持续追踪，整池更新 | 0.469/0.617 | 2.573/3.158 |
| 有限穿屏，整池更新 | 0.224/0.376 | 1.337/1.832 |
| 距离规则：快照+计算+写回+池更新 | 0.969/1.460 | 5.911/7.720 |
| 4 来源关系规则，每帧全目标写回+池更新 | 1.405/2.058 | 8.124/9.689 |
| 16 来源关系规则，每帧全目标写回+池更新 | 1.537/2.546 | 10.726/16.217 |
| 正常 neighbor_turn：16 来源无匹配，不无效改写，含池更新 | 0.707/1.021 | 4.694/6.237 |
| 全母弹终结捕获+池更新，尚不创建实体 | 0.845/1.009 | 5.030/6.145 |

普通 50k median 相对本轮备份约 +3.7%，默认仍无阶段/穿屏扫描。50k × 16 的持续全量写回
p95 已接近一整帧预算；应限制组规模、只读必要字段/只写匹配项，需要更大来源数量时再按
实测引入空间索引，不把 Numba 标记当作任意负载已加速。真实 Enemy 创建另测：64 个
median/p95 0.339/0.475ms，256 个 1.459/2.023ms（包括终结池更新、构造/bind/start/add，
不含贴图初始化或渲染；使用普通无精灵 EnemyScript 子类），不与 50k 数值弹性能混算。

全新独立 NUMBA_CACHE_DIR 子进程：默认运动 992.8ms、阶段运动 798.0ms、阶段 524.7ms、
穿屏签名与后处理 1750.4ms、区域 295.9ms、距离两种签名 392.9ms、邻域两种签名
1135.4ms、渲染准备 447.4ms，合计约 6.34s；同进程第二次合计约 0.221ms。
`warmup()` 不改出生、时钟或作用域计数，正式启动已在 gameplay 前调用。新增数值公式
预热 float32 点/中心与 bool mask 的常用签名；作者另用不同 dtype/参数类型仍可能新增 JIT
签名，需要在进入 gameplay 前预热。冷编译不计入上表稳态数字；本轮不引入 Rust。

复现入口：正常示例 `game_content/examples/th06_patterns.py`、API 指南
`game_content/SCRIPTING.md`；即时 stdin 与配对测量代码在本会话工具记录，不增加验证脚本。
剩余边界：完整 ECL/全部原作指令不兼容、任意规模通用关系求解器未实现、数值规则与实体
转换尚无专门纯 GUI 节点，Native/真人及整游戏性能验收未完成，文档站点构建仍失败。
另经源码确认：独立 `tools/preview_spell.py` 虽创建 StageContext，但 SpellPreviewSession
的 step_one 不推进 Context 任务、消费转换队列或更新实体敌人，且仍先 Spell 后 Pool；
本轮未扩改该工具，不把正式 StageManager 证据当作它已支持所有新机制的证明。

### 当前维护任务：完整 TH06 的引擎 API 覆盖（2026-10-13）

目标：关卡作者用正式 Python API 表达 TH06 六关及 Extra 的机制，不需要修改 Pool 内部、
逐弹 Python 回调或另一套 ECL 运行时。原作素材/脚本内容、GUI 覆盖和像素级复刻分别验收；
两个难例通过不等于整个目标通过。机制与参考代码对照见 [TH06_API_COVERAGE.md](TH06_API_COVERAGE.md)。
本任务不修改 CD 历史勾选，协调者是唯一状态写者。

| Owner | 路径 allowlist | 本步交付 |
| --- | --- | --- |
| 协调 Agent（唯一实现者） | `src/devtools/spell_preview.py`、`tools/preview_spell.py`、本文、`docs/TH06_API_COVERAGE.md`、`game_content/SCRIPTING.md` | 独立符卡预览走正式帧任务/事件/敌人/转换/激光；记录全机制覆盖和下一步依赖 |
| DeepSeek Harness（只读委派） | 参考 checkout 的 `src/{EclManager,EnemyEclInstr}.{hpp,cpp}` | 机械提取指令及特殊函数名/行号，不判定 PySTG 完成，不修改任何文件 |
| 协调 Agent（第二步，同一写者） | `src/game/stage/{motion,enemy_script,boss_base,spellcard}.py`、`src/game/laser.py`、`src/core/collision.py`、`src/game/player/player_bullet.py`、`src/render/renderer.py` 的目标可见性判断、`src/authoring/dsl.py` 的 MoveTo、`src/compiler/codegen.py` 的 MoveTo、`main.py` 的激光预热调用、`game_content/examples/th06_controls.py`、架构/脚本指南 | 共用移动曲线和边界；独立命中/受伤/交互/可见性；同一 Laser 的定时、移动段和取样；生成入口镜像，不增加 UI 系统 |
| 协调 Agent（第三步，同一写者） | `src/game/state.py`、`src/game/stage/{__init__,context,spellcard,boss_base}.py`、`src/game/bomb.py`、`main.py` 的正式 update/玩家事件接线、`src/render/renderer.py` 的背景推进开关、`src/devtools/spell_preview.py`、`game_content/examples/th06_controls.py`、架构/脚本指南/本文/覆盖清单 | 跨关共享难度/机体/rank；分系统时停作用域；控制协程继续推进，Boss 计时可暂停/重置；Bomb/miss 的稀疏状态通知，不引入第二调度器 |
| 协调 Agent（第四步，同一写者） | `src/game/{item,state,bomb}.py`、`src/game/stage/{context,boss_base,spellcard}.py`、`main.py` 的计分/收集/miss/continue 接线、`src/devtools/spell_preview.py`、`tools/preview_spell.py`、`game_content/examples/th06_rules.py`、架构/脚本指南/本文/覆盖清单 | 开放稀疏收集/计分/擦弹/恢复/Bomb 与符卡奖励/结束规则；默认兼容，普通内容可以配置 128P 等策略；结束 hooks 真正执行，不提前擦掉结束规则所需弹幕；预览使用真实 ItemPool/renderer |
| 协调 Agent（本批收尾，同一写者） | 上述 Runtime/预览路径、`src/game/stage/__init__.py` 的机体同步、`game_content/examples/th06_{controls,patterns}.py` 的真实弹型名、四份说明文档 | 修复独立复核中的同帧命中/最终帧奖励/机体输入；实际收集项批量筛选；配对性能、真实 GL 呈现及文档收尾，不扩改 UI |
| 协调 Agent（真实画面发现的窄接线修复） | `src/core/sprite_registry.py`、`main.py` 的 registry 初始化、`tools/preview_spell.py` 的 registry 初始化、四份说明文档 | 翻转上传的图集使用相同方向的 UV，正确绘制所选弹型/颜色；不变更 shader、排序、混合或资源格式 |
| 协调 Agent（文档/API 对照的窄修复） | `src/game/stage/context.py` 的 spawn_item 参数接线、四份说明文档 | 修复角度重复转换，用真实方向/速度验证；精确标注 Bomb 激活窗口和 effects 暂停范围，不扩建 Bomb/特效系统 |
| 协调 Agent（粒子 API，同一写者） | 新增 `src/game/particle.py`、`src/render/particle_renderer.py`、`src/game/stage/{__init__,context}.py`、`main.py` 的初始化/update/render/continue 接线、`src/render/renderer.py` 的粒子层/cleanup、`src/devtools/spell_preview.py`、`tools/preview_spell.py`、`game_content/examples/th06_particles.py`、架构/脚本指南/本文/覆盖清单 | 独立有限 SoA 粒子池、Numba 批量更新、贴图动画/染色/缩放/旋转/散射/收拢、GL 实例绘制；作用域清理、时停、候选预览隔离；真实 Runtime/GL 和空池/1k/10k 性能分别验证。仅补粒子，不扩建 ANM VM、HUD 或死亡状态机 |

denylist：`.claude/settings.local.json`、用户 `python_source.py` 现有改动、
`game_content/authoring/stages_1_3/` 及其它用户作者工程、生成产物入库、编辑器 UI、
测试/验证脚本重建、第二 Runtime、逐弹 Task/callback、Rust 工具链。
后续实现扩展路径前必须先更新 owner/allowlist，外部 Agent 不能写核心 Runtime 或本文。

顺序与验收（未通过保持未勾选）：

- [ ] 完整提取 136 个 ECL 指令、17 个 ExIns 及关卡/难度/机体分支；每个机制有现有 API、
  缺口或明确不属于游戏机制的解释，不把空实现或直接改私有数组当支持。
- [ ] 独立符卡预览：新弹出生不提前运动；Context 任务/事件每帧一次；转换敌人出生帧为 0、
  次帧执行；真实激光更新/显示；重启、seek、结束、异常执行 finally 且不泄漏旧作用域。
- [ ] 敌人/Boss 控制：移动曲线、边界、受伤与碰撞可独立禁用、受击反应、血量/计时切换；
  真实碰撞及阶段结束验证，不以属性存在代替接线。
- [ ] 发射/运动/激光覆盖：发射模式、延迟/分层、原作特殊变换、移动激光的生命周期/碰撞，
  各机制走真实池及正常脚本，10k/50k 弹与实际激光量分别测量。
- [ ] 游戏状态与演出：难度/机体/动态 rank、掉落/计分/符卡结算、对话/BGM/背景控制，
  明确通用接口与 TH06 内容策略，不能把引擎当前硬编码规则冒充可配置。
- [ ] 综合覆盖：Stage1–6/Extra 的机制样例、独立生成子进程、正式 StageManager、Native
  呈现与整帧 Performance 分开复核；原作全脚本/资源未运行时必须明确未验收。

**当前状态**：进行中。DeepSeek 首次 headless 委派因 provider 未配置而未执行；随后一次
多行命令的目标描述被 Windows `.cmd` 截断，已中断，不计独立验收。凭据不写入配置/仓库。
Windows Computer Use native pipe 不可用，未通过 UI 向 Antigravity 发任务。协调 Agent
用即时源码抽取核对指令清单，继续主线实现；不能记录外部 Agent 已完成。

**Evidence（2026-10-13，本批 Runtime API 收尾；不更新上面六项勾选）**：

- Structural：新增共用 ActorControls、RunState/TimeControl 与稀疏 GameStats/SpellResult
  规则；依旧使用原 StageManager、FrameTask、Pool 和 renderer，没有 ECL VM、第二调度器、
  逐弹 Python Task/callback 或 Rust 依赖。四份文档已校准接口与实际边界。原作 136 项枚举
  和 17 个 ExIns 已列出，但没有完整原作脚本/资源移植和逐难度/机体验收。
- Runtime：独立未参与实现的验证者以正式 StageManager 跑 A→B 共 497 更新；
  timeout timer=3/bonus=1003，击破 timer=2/bonus=1002，结束奖励读最终帧。同帧两颗真实
  自机弹击破带 on_hit 的 Boss 不再崩溃，反应一次、finally 执行；玩家引用/shot/同一 RunState
  跨关同步。异步结束反应及 awaited 子任务完整执行，中途 close 后 pending/mask=0；
  候选预览失败保留旧池/RNG。自定义结算读取 8 颗真实活弹，没有预先清空。
  验证者另外复核道具同帧收取顺序/一次性、尾部 4→2→0、出界与重新生成，Python/Numba
  一致，常用 JIT 签名未增加；激光常用碰撞也保持一个签名。
- Runtime 兼容：协调者从 `game_content.entry.STAGES` 建立正式 Player(`tao`)、StageManager、
  OptimizedBulletPool、LaserPool、ItemPool，不修改旧内容或设跳关。Stage1 1,400 更新：
  活弹 15、峰值 78、峰值敌人 8；Stage2 400 更新：15/15/9；Stage3 400 更新：231/231/5。
  坐标有限、事件无异常、共享状态及 clear 清理通过；音频、物理输入与完整通关 not run。
  文档/API 对照还发现 spawn_item 的角度重复转弧度，已修为 Context 只转换 speed/60；
  正式 Context/ItemPool 的 Python 与 Numba 两路验证 0/90/180/270/-45 度、0.6 单位/秒、
  首步位移和旧默认 pop_speed=0.02 通过。新增 API 的文档限定范围经独立只读复核 PASS。
- Runtime 生成：上一轮六文件声明式工程已完成稳定保存/AST→独立 PackageBuilder→独立
  Runtime（437 更新、16 弹），MoveTo easing 与正式运动一致；本批文档收尾不无故重跑旧
  生成检查。这不是全部原作发射模式、effect flags 和 ExIns 的整体覆盖证明。
- Native：真实 GLFW/ModernGL 窗口 768×896，正式资源与池 renderer；ControlMechanicsSpell
  推进 330 帧，140 帧 48 条激光、290 帧移动段/蓝色 grain_a 米弹，道具实际呈现。
  修复图集上传 flip_y=True 但注册 UV 未翻转的问题；独立验证者对 1,490 个有纹理精灵的
  两种模式与 TextureAssetManager 全量一致，旧默认/位置参数不变；164 个无纹理目录条目
  仍两路一致跳过，没有扩改旧资源 fallback。真实 GL 上七种 grain_a 精灵与 canonical UV
  参考绘制逐字节相同，framebuffer 图像已观察。PySide6 嵌入/编辑器输入链本批 not run。
- Performance：本机 Python 3.12.7、Intel Family 6 Model 151、GTX 1660 Ti；以下为 median/p95
  毫秒，不使用启动 JIT 或池层数字冒充整游戏帧率。

  | 负载与配对口径 | 之前 median/p95 | 当前 median/p95 |
  | --- | --- | --- |
  | 普通 10k 弹池，HEAD→当前；270 帧弃前 30，交替顺序 | 0.3452/0.3965 | 0.3577/0.4401 |
  | 普通 50k 弹池，同上 | 1.8343/2.2745 | 1.8841/2.3370 |
  | 48 条手动激光，批初备份→当前，含全量无命中碰撞 | 0.0408/0.0445 | 0.0632/0.0654 |
  | 48 条移动/定时激光，含全量无命中碰撞 | 无同能力基线 | 0.0949/0.1030 |
  | 100 条手动激光，批初备份→当前，同口径 | 0.0835/0.1325 | 0.1290/0.2006 |
  | 100 条移动/定时激光，同口径 | 无同能力基线 | 0.1949/0.2803 |
  | 256 个未收取道具，本次优化前→后 | 0.2349/0.4124 | 0.0063/0.0193 |
  | 1,000 个未收取道具，同上 | 0.9814/1.6401 | 0.0155/0.0574 |
  | 64 个默认规则收取，含生成/收取 | 0.2966/0.4909 | 0.1785/0.2972 |
  | 64 个自定义规则收取，同上 | 0.2705/0.4437 | 0.1500/0.2369 |
  | 1,000 个默认规则收取，同上 | 4.3294/5.3674 | 2.4256/3.2593 |
  | 1,000 个自定义规则收取，同上 | 4.1709/5.4572 | 2.1188/3.1549 |

  道具 idle 测 270 帧弃前 30，收取测 75 轮弃前 10；后段可能与另一子进程冷编译重叠，
  不宣称隔离整机测量。正式 GL 压力负载各 100 帧弃前 20：10k/50k grain_a 蓝弹，
  加 48 条实际激光和 256 个实际道具，固定 seed=1337、真实更新/玩家弹碰撞/激光全量
  无命中碰撞/池渲染/swap/poll。CPU median/p95 分别为 1.7274/2.3584、3.9093/6.1881；
  GPU render query 分别 0.1941/0.4390、0.8866/0.9832。无完整玩家射击、背景、音频、GUI，
  也不测高密度击中场景；CPU 数字不包含读取 GPU query 结果的等待，不能相加当整游戏预算。
  独立空 NUMBA_CACHE_DIR 的 Pool+激光碰撞+ItemPool 冷编译约 6.33 秒，同进程第二次约
  0.249 毫秒；预热不改变池状态。冷启动、稳态 CPU、GPU 分开记录。
- Usability：维护者/真人新手 not run；本批未改编辑器 UI，不能由样例或压力帧证明纯 GUI
  能完整创作 TH06。Bomb 可配置入口不等于原作 Deathbomb 已移植；is_bombing 目前是玩家
  激活/增伤窗口，effects 暂停目前只接 emoji。camera/fog、主/附属/死亡动画、粒子、Boss
  HUD 演出、原作规则和所有内容仍在覆盖清单的未关闭缺口中。

检查入口（即时 Python/stdin 检查不恢复仓库测试或原生验证脚本）：

~~~powershell
C:/Users/m1573/anaconda3/python.exe -m compileall -q main.py src game_content tools
C:/Users/m1573/anaconda3/python.exe tools/validate_assets.py --format json
C:/Users/m1573/anaconda3/python.exe tools/preview_spell.py game_content/examples/th06_controls.py ControlMechanicsSpell --difficulty hard --player-shot reimuA --seed 1337
git diff --check
git diff --cached --check
npm.cmd run docs:build
~~~

compileall 与 assets 当前通过（99 JSON、16 sprite configs、745 sprites、142 images，零错/警告）。
当前受影响模块的 pyflakes 除 Context 中 HEAD 已存在的 5 个未用导入外通过，未伪报全仓库
零告警。四个受影响 Runtime 文件已机械统一 UTF-8/LF 并去行末空白，未改变语义。
文档站 **FAIL**：默认 `npm.cmd run docs:build` 与单独任务 TEMP 重试均因
`[vite:esbuild-transpile] remove ...esbuild-...: Access is denied` 退出；未修改依赖或把该门禁
伪报通过。最终 diff/暂存区/用户源码 hash 复核记录在本批最终报告；不提交生成产物。

**补充 Evidence（2026-10-13，粒子 API；不更新上述六项或 CD 勾选）**：

- Structural：新增独立 ParticlePool/ParticleEffect/ParticleGroup/ParticleSnapshot 和实例
  ParticleRenderer，接现有 Context/StageManager/正式循环/预览，未增加逐粒子对象/任务、
  第二 Runtime、Qt 依赖或 ANM VM。已有 RawPython 可调用 API，无新 GUI 节点。
  `python -m compileall -q main.py src game_content tools`、资源检查与 diff/cached check
  通过；资源为 99 JSON/16 configs/745 sprites/142 images，零错/警告。受影响模块
  pyflakes 只报告 HEAD 已有 Context 五个未用导入和 main 的 all_sprite_ids，未报全零。
  最新 `npm.cmd run docs:build -- --outDir <本轮外部产物目录>/docs-site` 仍 FAIL（15.59s）：
  esbuild 删除 TEMP 文件 `Access is denied`，与前批相同；未扩改构建依赖或伪报文档站通过。
- Runtime：即时 stdin 通过显式 Euler、Python/Numba 一致、动画/尺寸/alpha/角度、
  60/240 帧收拢、寿命/回收、满池 dropped、代数隔离、只读快照脱离及 transform 原行
  对齐。正式 ParticleMechanicsStage 690 更新结束，峰值 174；不是原作关卡。
  独立未参与实现者另跑正式 StageManager A→B 540 帧，birth age=0、effects 暂停恢复、
  跨关、取消 finally 和异常最终清空。实际目录注册 1,491 项；独立符卡 445 帧结束、
  峰值 174、effects 恰停 20 帧，同 seed 重启后第 150 帧位置逐元素一致。
  候选 bind 先发射再失败时旧池/位置/age/RNG 不变，成功替换整个粒子池；结束/关闭/
  异常清理 Context。预热含 update/pack/compact，实际签名各一个，避免首次 group 清理
  才编译回收内核。粒子与敌弹/道具独立，清敌弹不清粒子；continue 显式清装饰。
- Native：协调者用真实 768×896 GLFW/ModernGL 窗口、现有图集及正式 Renderer/StageManager
  跑完 690 帧，六个实际 framebuffer 帧和 contact sheet 已查看。七个实际 grain_a 精灵
  与原 OptimizedBulletRenderer 单 sprite 绘制逐字节一致；染色/alpha 预期误差最大
  1/255，跨两图集 A→B→A 的三批绘制等于逐次绘制，未为合批重排半透明粒子。
  additive 后恢复标准 alpha，viewport/scissor 不变。独立方未运行 GL；本批 PySide6
  嵌入、物理输入、音频 not run，不拿该窗口当编辑器/原作呈现验收。
- Performance：Python 3.12.7、Intel Family 6 Model 151、GTX 1660 Ti；数值为 median/p95 ms。
  update+两层 pack 270 帧弃前 30：空池 0.0009/0.0010，1k 0.0135/0.0137，
  10k 0.1045/0.1154；另一轮分别 0.0016/0.0017、0.0222/0.0260、0.1723/0.1971，
  不隐藏进程/频率波动。空 update 100 组×1,000 调用平均约 0.0001 ms/次。
  以下是真实 GL 合成负载，不是整游戏；固定 seed=1337，10k 静止米弹，加白色 sprite
  粒子（scale=.6、add、一批），GPU 先预热 240 帧，各测 120 帧弃前 20：

  | 负载 | CPU 更新/提交/swap/poll | GPU clear+绘制 query |
  | --- | --- | --- |
  | 10k 弹，无粒子路径 | 0.5672/0.8339 | 0.1720/0.2074 |
  | 10k 弹，空粒子池 | 0.5503/0.6798 | 0.1597/0.1755 |
  | 10k 弹 + 1k 粒子 | 0.6057/0.8448 | 0.1727/0.2142 |
  | 10k 弹 + 10k 粒子 | 0.7105/1.0361 | 0.2642/0.3292 |
  | 配对复测：空池 / 无粒子 | 0.5462/0.8113 / 0.5543/0.6552 | 0.1594/0.1953 / 0.1599/0.1944 |
  | 复测：1k / 10k 粒子 | 0.5804/0.8697 / 0.7203/1.0386 | 0.1727/0.2130 / 0.2641/0.3255 |

  空池差异在测量噪声内，不声称粒子提升普通弹性能。CPU 不含 query 读取的等待；无
  激光、碰撞、背景、音频、GUI、高密度大贴图过绘和逐帧批量 emission 的整帧预算。
  冷编译/缓存载入与稳态分开：本轮首个 update/pack 约 694/215 ms，末次独立进程
  update/pack/compact 缓存加载约 387/22/21 ms，不用这些数字计算 FPS。
- Usability：维护者/真人新手 not run。示例为普通机制移植，未改 UI，不声明纯 GUI 可做
  完整 TH06。Steam 的 PKGL 游戏包未解码/入库，原作 ANM、深度、附属动画和后续非粒子
  API 缺口仍在 `TH06_API_COVERAGE.md`；不自动扩大到死亡、HUD 或背景相机系统。

复现入口：`C:/Users/m1573/anaconda3/python.exe tools/preview_spell.py
game_content/examples/th06_particles.py ParticleMechanicsSpell`；在一个命令行中运行。
整关入口 `C:/Users/m1573/anaconda3/python.exe main.py --content-entry
game_content/examples/th06_particles.py`，同样合为一行。数值/GL/性能即时 stdin 代码在本会话
记录，不建立新的验证脚本。用户 python_source.py SHA256 与批初一致，暂存区为空，
没有 commit/push，也没有修改 `.claude/settings.local.json` 或用户作者工程。

### 当前维护任务：视觉重做（方案 C，专业 DCC 风）（2026-10-10）

维护者选定方案 C 并明确要求"只改视觉，别改业务逻辑"。本任务是交互与视觉维护，
不新增阶段、不改历史勾选；作者格式、Runtime、单一 Session/Undo、显式 Run 契约不变。

| Owner | 允许编辑 | 必须完成 |
| --- | --- | --- |
| 协调 Agent（唯一写者） | `src/editor/theme.py`（新增）、`app.py`、`window.py`、`sidebars.py`、`inspector.py`、`program_tree.py`、`node_palette.py`、`timeline.py`、`onboarding.py`，本文与架构文档 | 颜色/间距/字号单源化；应用级样式表；程序流紧凑行式；插入点默认只画引导线；面板头统一；白弹窗消失 |
| 独立验证 Agent | 只读 | 复核交互链与视觉 token 覆盖；报告未观察类别，不更改实现 |

denylist：`src/authoring/**`、`src/compiler/**`、`src/core/**`、`src/game/**`、
`game_content/**`、`tests/**`、`.claude/settings.local.json`、生成产物，以及任何信号连接、
命令构造、session 调用与数据语义改动。

验收（严格限定在视觉层）：

1. 深色主题必须在对话框、菜单、工具提示、下拉列表等顶层弹窗同样生效，不得再出现白色弹窗；
2. 编辑器内不再有散落的颜色字面值，颜色/间距/字号只从 `theme.py` 取值；
3. 交互行为不变：选中、拖放命中、插入落点、Undo/Redo、预览控制、Timeline 反向编辑与
   seek 判定都必须与改动前一致；
4. 只有真实 Windows 渲染才能算 Native 证据，offscreen 只记 Structural。

**本任务 Evidence（2026-10-10；视觉重做完成，不更新阶段勾选）**：

- Structural：新增 `src/editor/theme.py`（43 个颜色/几何 token + 由 token 生成的 QSS），
  `app.py` 改为 `app.setStyleSheet(STYLESHEET)` 应用级挂载；`window.py` 删除原 321 行、
  自相矛盾的内联 QSS（原第 280 与 312 行对 `QTreeWidget` 边框、255 与 314 行对
  `QTabWidget::pane` 各写了一次相反规则）。`window.py`、`inspector.py`、`onboarding.py`
  内的颜色字面值已全部改为 token 读取；`program_tree.py`、`timeline.py`、`node_palette.py`
  仍有数值等价字面值未替换（见下方未完成项）。`compileall` 与 `pyflakes` 通过（仅剩
  `commands.py` 一处改动前既有、与本次无关的未用导入）。
- Runtime：not run（本轮只动视觉层，未运行 StageManager 或生成关卡；不冒充 Runtime 证据）。
- Native：真实 Windows `windows` 平台 1:1 渲染取样：主窗口 `rgb(43,43,43)`、
  `_UnitDialog` `rgb(43,43,43)`、`QMenu` `rgb(60,60,60)`、`QMessageBox` `rgb(43,43,43)`
  —— 改动前对话框与菜单实测为 `#f3f3f3` 白底黑字，现已统一为深色。1500×940 实机窗口抓图
  确认程序流为 28px 紧凑行（原 34px）+ 左侧类别色条 + 底部分隔线，默认不再逐缝显示
  "＋ 添加"大按钮，鼠标经过才显示引导线与落点标记；时间线下限 176px、初始 190px
  （原 90/160）。
- Performance：not run（未测量整体预算）。仅记录 1500×940 抓图正常、无布局报错。
- Usability：维护者验收 not run；本轮由维护者选定方向、Agent 实现，未经真人试用确认。

复查入口：`C:/Users/m1573/anaconda3/python.exe -m src.editor.app`，打开入门示例后确认
对话框/菜单为深色、程序流为紧凑行式、插入点悬停才出现、时间线不再被压成一条缝。
即时检查：`python -m compileall -q src/editor`、`python -m pyflakes`（传 `src/editor/*.py`
展开后的路径）、`git diff --check`。

未完成项（不冒充已完成）：`program_tree.py`、`timeline.py`、`node_palette.py` 内仍有约 60 处
与 `theme.py` 数值等价的颜色字面值；它们当前显示正确且集中在自绘控件内，下一轮继续替换为
token 读取后，"颜色只有一个来源"这一条才完全成立。

文案补充（2026-10-10，维护者反馈"包裹"一词难懂）：WRAP 放置的用户可见文案统一改为
「套一层」——卡片手柄标签、工具提示（"拖一个空容器（重复/条件/定时/并行）到这里，把该
步骤套进它里面"）、拖放反馈（"请拖到插入线、容器内容区或卡片右侧的「套一层」区"）与放置
预览（"把 X 套进 Y 里"）。`_HANDLE_WIDTH` 由 36px 调整为 44px，使三字标签不至于顶到热区
边缘；实测拖动热区 (847,26,44,28) 与「套一层」热区 (891,26,44,28) 不重叠，热区中心仍解析
为 `DropPlacement.WRAP`，行为未变。仅在维护者可见 UI 与文档中替换措辞，`DropPlacement.WRAP`、
`wrap_node` 等 Python 标识符保持英文不动。

插入提示补充（2026-10-10，维护者反馈"鼠标停在两个事件之间看不出能加东西"）：改为**悬停即
显**——鼠标停在哪条缝隙，就在该缝隙亮出引导线，并在光标所在 x 位置画一个小 ＋ 圆点和
「添加步骤」提示（`_hover_insertion` / `_last_pointer`）；靠近判定沿用 `_INSERT_HIT_HEIGHT`
(22px)，同一容器内相邻步骤（间隔 14px）也能命中。拖放进行中改为一次亮出全部落点。绘制
不再自行读取光标位置，改由鼠标事件写入的悬停状态驱动，避免命中与绘制判断不一致。实测：
悬停缝隙后该处出现 227 px 的 ＋ 圆点填充与提示文字，移开后同区域归零；悬停换到另一条
缝隙时提示随之切换。修复过程中发现并修掉一处真实缺陷：落点元组每次新建，`!=` 会因对象
身份不同而恒为真，导致圆点被跳过；改为逐字段比较（`_same_insertion`）。`leaveEvent` 与
`wheelEvent` 会收起提示，避免滚动后残留。

拖放未回归的定向复核（2026-10-10，维护者担心视觉改动碰坏拖动；据此专项验证）：

- 启动链（真实 QTest 鼠标事件）：按在卡片正文只进入选择、`_press_drag_handle` 为 False，
  横移 40px 不产生拖动；按在拖动热区 `(847,26,44,28)`，仅移 4px 不越 8px 阈值，松开无任何
  模型改动。
- 几何判定：拖动热区与「套一层」热区中心分别解析为 `None`（不可放置）与
  `DropPlacement.WRAP`，两热区不重叠。
- 提交链（真实 `QDropEvent` + 真实信号 + 真实 `QUndoStack`）：把 `stage_bgm` 拖到
  `stage_at_cue` 之后，顺序精确变为期望序列、栈深 1、Undo 完全还原、dirty 回到 False；
  把 `Repeat` 原型拖到“等待 30”的「套一层」热区，得到外层 `Repeat` 且其 body 恰为该
  `Wait`，顶层数量不变，Undo 后回到原样。
- 未验证（不冒充）：`QDrag.exec()` 的**原生拖放循环**无法在自动化脚本中驱动——它需要真实
  按键/平台拖放事件，无人操作时会一直阻塞（实测会挂住脚本）。因此“物理鼠标从按下到松开
  完成一次平台拖放”这一步仍属 Native not run，需要维护者实际拖一次确认。

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
