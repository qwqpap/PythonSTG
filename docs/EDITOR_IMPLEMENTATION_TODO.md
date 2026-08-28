# PySTG 代码驱动关卡编辑器实施 TODO

> 状态：Active。本文是编辑器唯一实施清单和完成证据记录。
> 产品契约见 [EDITOR_PRODUCT_VISION.md](EDITOR_PRODUCT_VISION.md)，工程边界见
> [EDITOR_ARCHITECTURE.md](EDITOR_ARCHITECTURE.md)。旧路线只在 Git 标签
> `archive/editor-v1-f9e0798` 中保留。

## 1. 固定顺序

```text
CD0 -> CD1 -> CD2 -> CD3 -> CD4 -> CD5 -> CD6 -> CD7
```

| ID | 任务 | 状态 | 依赖 |
| --- | --- | --- | --- |
| CD0 | 契约重置与安全点 | `[x]` | `f9e0798` |
| CD1 | 拆除旧静态作者链 | `[x]` | CD0 |
| CD2 | 声明式 Python 核心 | `[x]` | CD1 |
| CD3 | 生成器与统一入口 | `[x]` | CD2 |
| CD4 | 最小 Qt 编辑器 | `[x]` | CD3 |
| CD5 | 固定布局、程序树与资源拖拽 | `[x]` | CD4 |
| CD6 | 真实预览与 Trace | `[x]` | CD5 |
| CD7 | Timeline 与完整关卡证明 | `[x]` | CD6 |

Agent 只能领取最早未完成任务。当前 gate 红时不得开始下一项。协调 Agent 是唯一可以更新
本表的人；实现者之外的只读验证 Agent 执行最终 gate。

## 2. 通用执行协议

每个任务按以下顺序执行：

1. `git status --short`，保护用户修改，特别是永不触碰
   `.claude/settings.local.json`。
2. 写明 owner、允许路径、禁止路径和与相邻任务的边界。
3. 阅读真实调用入口和被保留的 Runtime 测试，先建立可观察契约。
4. 实现时不加 Legacy 开关、兼容 shim、第二模型、第二预览、`skip` 或 `xfail`。
5. 运行 focused gate、阶段回归、compileall、资产校验和 diff check。
6. 由未参与实现的 Agent 只读复验；失败返回当前阶段修复。
7. 只更新本任务的 checkbox 和唯一 Evidence / Blocker 段落。

完成证据必须分开报告：

- Structural：文件、符号、依赖、生成布局和静态边界；
- Runtime：真实 compiler/import/StageManager/游戏循环；
- Native：真实 PySide6 + GLFW/ModernGL 窗口和交互；
- Performance：加载、构建、预览、测试时间与代码体积；
- Usability：维护者真实操作；没有真人就写 `not run`。

文件存在、import 成功、offscreen Qt、截图或一个 pytest 总数不能替代其他证据类别。

## 3. CD0：契约重置与安全点

**Owner**：架构/协调 Agent。

**允许路径**：`AGENTS.md`、`README.md`、`docs/` 中编辑器愿景、架构、TODO、旧专用
契约和它们的文档引用；Git tag/branch。

**禁止路径**：`src/`、`tests/`、`tools/`、`game_content/`、Runtime 和产品实现。

**实施**：

1. 验证 HEAD 为 `f9e0798`，创建并推送 annotated tag
   `archive/editor-v1-f9e0798`。
2. 从该提交创建并推送 `codex/code-driven-editor-v2`。
3. 重写 `AGENTS.md`，固定 CD0-CD7 顺序、唯一 Python 真源、无兼容策略和证据分类。
4. 完整替换 `EDITOR_PRODUCT_VISION.md`、`EDITOR_ARCHITECTURE.md` 和本文。
5. 删除旧 N6.4、Scene、Pattern、Preview、插件和 JSON 作者资源专用契约；清除引用。
6. 确认新 TODO 不出现 ER/N4-N9 双轨任务。

**Gate**：

- tag 和远端分支都指向预期提交；
- 三份文档对唯一真源、删除范围、生成入口、预览、Timeline、测试预算和无兼容策略一致；
- 文档链接检查通过；
- `rg` 不再找到旧专用契约引用；
- 工作树只包含 CD0 文档变更和既有 `.claude/settings.local.json`。

**Evidence（2026-08-24，独立只读验收 APPROVE）**：Structural PASS。远端 annotated
tag `archive/editor-v1-f9e0798` peeled target 与远端分支
`codex/code-driven-editor-v2` 均为 `f9e0798b33879d9dc29effd16addf24d6a8f4732`；TODO
任务表和章节只含 CD0-CD7，六份旧专用契约已删除且 `AGENTS.md`、`README.md`、`docs/`
对旧文件名零引用。验证者逐项核对三份契约的一致性，解析 36 个 Markdown 相对链接和全部
VitePress 内部导航，缺失 0；`npm run docs:build -- --outDir
C:\Users\m1573\AppData\Local\Temp\pystg-docs-cd0` 使用 VitePress 1.6.4 成功构建当前树，
10.41 秒，仅有非阻断的 chunk-size warning；`git diff --check` 与
`git diff --cached --check` 通过。暂存区为空，既有 `.claude/settings.local.json` 未修改、
未暂存。Runtime：not run；Native：not run；产品 Performance：not run；Usability：not run。

## 4. CD1：拆除旧静态作者链

**Owner**：架构拆除 Agent；最终删除清单由协调 Agent确认。

**允许路径**：旧 `src/editor/`、`src/pattern/`、`src/compiler/`、`src/preview/`、
`src/authoring/` 旧命令/Scene/Timeline/StateGraph/variables/registry contribution、
`src/game/stage/program.py`、`src/game/reactions.py`、相关 `tests/`、旧验证工具、旧
`.pystg.json` 内容、`main.py`、`game_content/entry.py`、`src/core/expressions.py`、通用
资源导入适配、`.gitignore` 和脚本入口。

**禁止路径**：`StageScript`、`Wave`、`EnemyScript`、`SpellCard`、`StageManager`、
renderer、BulletPool、Laser、音频、正式游戏循环、Stage1-Stage3 实现、
`ProjectContext`、`src/game/events.py`、事件适配器/生命周期批处理、独立资产/菜单/立绘/
对话/背景工具、`src/devtools/spell_preview.py`、hot reload、资产校验、`src/qt_compat/`。

**实施顺序**：

1. 将 `src/pattern/expressions.py` 的通用表达式能力迁至
   `src/core/expressions.py`，更新 UI Document 与 Background Document Runtime 导入。
2. 瘦身 `ResourceReference`/`ResourceStore`，只移除 Pattern/Scene contribution。
3. 新增 `game_content/entry.py` 注册手写 Stage1-Stage3；`main.py` 先改为默认动态入口。
4. 整体删除旧 `src/editor/`，暂时移除 `pystg-editor` 脚本入口。
5. 删除 `src/pattern/`、旧 Scene/Pattern compiler、StageProgram preview 链、作者 Command/
   Scene/Timeline/StateGraph/variables/migration/registry contribution。
6. 删除 `src/game/stage/program.py`、`src/game/reactions.py` 及其 re-export。
7. 删除 Pattern Lab/Preview/Preset builder、旧 N4/N5/N6/ER verifier、旧 JSON 示例和作者
   内容。
8. 删除只验证上述接口的测试，不留 shim、skip、xfail 或空壳断言。
9. 保留 Runtime、资源、UI/Background Runtime、事件、生命周期、池、手写关卡和独立工具
   测试，并逐个修正真实导入。

**Gate**：

```powershell
rg -n "PatternDocument|BehaviorGraph|PresetLibrary|TimelineClip|StateGraphSpec|ReactiveClip|StageProgram|StageRunner" src game_content tools
python -m compileall -q main.py src game_content tools tests
python tools/validate_assets.py --format json
python -m pytest -q <retained-runtime-resource-tool-tests>
python main.py --content-entry game_content.entry --help
git diff --check
```

首条必须零命中；手写 Stage1-Stage3 通过新默认入口加载。删除测试时提交说明必须列出每类
测试对应的已删除产品接口与保留替代覆盖。

**Evidence（2026-08-24，独立只读验收 APPROVE）**：Structural PASS。旧八个禁用符号、
旧模块导入、skip/xfail 均零命中，旧 tracked editor/pattern/compiler/preview、作者 JSON、
StageProgram/Reaction、插件/变量/Timeline/StateGraph 产品链和对应验证工具已清零；
`pystg-editor` 暂时移除。删除的旧 editor/pattern/preset/preview/graph/变量/兼容测试对应的
产品接口已删除；保留的表达式、UI/Background 资源、events/lifecycle、批量渲染/池、资产、
hot reload 和手写符卡工具由 146 项当前测试直接覆盖。Runtime PASS（CD1 范围）：
`python -m pytest -q` 146 passed；`game_content.entry` 精确注册 Stage1-Stage3，`get_stage`
和 `python main.py --content-entry game_content.entry --help` 通过。Performance PASS：独立
复验 compileall 0.21s、资产校验 0.48s、pytest 3.35s、入口 0.97s；资产校验 71 JSON、
16 sprite configs、745 sprites、142 images，0 error/0 warning。`git diff --check` 与 cached
check 通过，`.claude/settings.local.json` 未暂存。Native：not run，本阶段不要求；
Usability：not run，本阶段不要求。

## 5. CD2：声明式 Python 核心

**Owner**：Authoring Agent。

**允许路径**：`src/authoring/program.py`、`dsl.py`、`python_source.py`、`templates.py`、
包导出、focused headless tests 和最小作者 fixtures。

**禁止路径**：Qt、`src/editor/`、renderer、Runtime 实现、生成 package、游戏入口。

**实施**：

1. 建立 Project/Stage/Wave/Enemy/Boss/Spell/NonSpell/Task/Function、节点、`Ref`、
   `Expr`、`RawPython` 和验证诊断。
2. 完成所有列定控制/动作节点，签名镜像现有 Runtime 公共 API。
3. 完成插入、删除、移动、Before/After/Child/Wrap、包裹和参数修改的纯模型操作。
4. 用 `ast` 解析受支持结构，用 `tokenize` 关联注释；不执行文件加载。
5. 自动补 UID，拒绝重复 ID/UID、坏引用和非法父子。
6. 稳定写回 UTF-8/LF/四空格并使用原子保存。
7. 实现 clean reload、dirty conflict、明确 keep/reload 和不支持语法只读保真。
8. 建立 `@template`、显式 import、签名绑定、缺包保留、递归检测和调用/定义双定位。

**Gate**：一个包含非平凡 Stage、Enemy、Spell、Task、模板、Parallel 和 RawPython 的工程可
加载、修改、保存、重开，语义等价且注释/UID 稳定。不支持文件逐字节不变。Headless 快速
集目标 15 秒以内，且导入图中无 Qt/editor/renderer。

**Focused tests**：

- `tests/test_authoring_program.py`
- `tests/test_authoring_dsl.py`
- `tests/test_authoring_python_source.py`
- `tests/test_authoring_templates.py`

**Evidence（2026-08-28，独立只读验收 APPROVE）**：Structural PASS。增量仅在 CD2
allowlist：`src/authoring/{__init__,program,dsl,python_source,templates}.py` 与四个 focused
tests；四个核心模块不导入 Qt、editor、renderer 或 Runtime，focused tests 无 skip/xfail。
受限 AST、稳定 UID/注释/格式、原子保存、外部冲突/只读保真、纯模型操作、全部逻辑单元与
节点、模板保留/展开/递归/异常及赋值时 import binding/shadowing 均有回归覆盖。Runtime PASS
（CD2 范围）：`python -m pytest -q tests/test_authoring_program.py
tests/test_authoring_dsl.py tests/test_authoring_python_source.py
tests/test_authoring_templates.py` 为 155 passed，非平凡 Project/Stage/Wave/Enemy/Boss/
NonSpell/Spell/参数 Task、Parallel、RawPython 工程可 load-modify-save-reopen 且语义等价；
真实生成包/StageManager 属于 CD3，not run。Performance PASS：focused 2.77s，全仓
`python -m pytest -q` 为 301 passed/3.93s，compileall 0.279s；资产校验 71 JSON、16 sprite
configs、745 sprites、142 images，0 error/0 warning；diff/cached check 通过。Native：not run，
本阶段不要求；Usability：not run，本阶段不要求。`.claude/settings.local.json` 未修改、未暂存。

## 6. CD3：生成器与统一入口

**Owner**：Compiler/Runtime integration Agent。

**允许路径**：`src/compiler/diagnostics.py`、`codegen.py`、`package_builder.py`、
`content_entry.py`、`main.py`、`game_content/entry.py`、`.gitignore`、
`src/game/stage/context.py` 中仅 `create_bullets_batch(render_angle=...)` 的现有批量 API
等价透传，以及 focused compiler/runtime tests。

**禁止路径**：Qt editor、renderer 语义、现有 Stage1-Stage3 实现、作者源码自动迁移。

**实施**：

1. 按 Stage 传递闭包生成固定包布局和根 entry 接口。
2. 生成类直接继承现有 Runtime 类型；控制/动作节点映射到现有 async/public API。
3. 实现确定性输出、manifest、source map、RawPython 和模板错误定位。
4. 在同级临时目录生成，用独立 Python 子进程执行 compileall、入口 import、Stage 注册与
   引用验证。
5. 验证成功才停止旧预览并原子替换；失败删除临时目录并保留上次成功结果。
6. `main.py --content-entry` 动态加载；默认 `game_content.entry`。
7. `game_content/generated/` 整体加入 `.gitignore`。

**Gate**：

- 完整生成包由普通 `main.py` 和现有 `StageManager` 加载运行；
- 连续两次生成逐字节一致；
- 构建失败和发布中断都回滚；
- Stage 顺序/start stage/source map 正确；
- 资产只引用不复制；
- 固定 seed 重复运行一致；
- 手写 Stage1-Stage3 仍加载；
- 批量弹幕路径且零逐弹 callback。

**Focused tests**：

- `tests/test_compiler_codegen.py`
- `tests/test_compiler_package_builder.py`
- `tests/test_content_entry.py`
- `tests/test_generated_runtime.py`

**Evidence（2026-08-28，独立只读验收 APPROVE）**：Structural PASS。CD3 增量仅在
compiler/entry、`.gitignore`、`src/game/stage/context.py` 的批量 `render_angle` 等价透传和
四个 focused tests；`src/compiler` 无 Qt/editor/renderer 导入，旧八符号、focused
skip/xfail 和 tracked generated 文件均为零，diff/cached check 通过。Runtime PASS：
`python -m pytest -q tests/test_compiler_codegen.py tests/test_compiler_package_builder.py
tests/test_content_entry.py tests/test_generated_runtime.py` 为 41 passed/6.275s，全仓为 342
passed/9.069s；生成包真实继承现有 Runtime 并由 `StageManager` 跑完，固定 seed 一致，真实
`OptimizedBulletPool` 使用 batch 路径且 emitter callback 为零；独立 compile/import 子进程、
确定性生成、事务回滚、资源不复制、source map、模板与 RawPython 双定位均通过，手写
Stage1-Stage3 和 `main.py --content-entry` 两种参数形式实测加载。Performance PASS：focused
6.275s <15s、全仓 9.069s、compileall 0.283s；资产校验 71 JSON、16 sprite configs、745
sprites、142 images，0 error/0 warning。Native：not run，本阶段不要求；Usability：not run，
本阶段不要求。`.claude/settings.local.json` 未修改、未暂存。

## 7. CD4：最小 Qt 编辑器

**Owner**：Editor shell Agent。

**允许路径**：新 `src/editor/`、`tools/scene_editor.py` 或新的唯一启动薄包装、
`pyproject.toml` 脚本入口、focused Qt tests。

**禁止路径**：Authoring schema/compiler/runtime/renderer 语义、插件系统、Timeline 完整算法、
自动预览或第二个文档模型。

**实施**：

1. 建立 `app.py`、`window.py`、`session.py`、`commands.py`。
2. 一个窗口打开一个工程；`EditorSession` 唯一拥有模型、当前单元、选择、dirty、一个
   `QUndoStack`、构建和预览状态。
3. 建立最小程序/文件/资产侧栏、程序树、Inspector、只读代码、Problems/Log、Timeline
   占位和 Preview host 占位。
4. 所有 UI 修改走 `QUndoCommand`；外部重载在明确确认后清空整栈。
5. 恢复唯一 `pystg-editor` 入口，不提供旧/新选择。

**Gate**：真实工程可以打开、导航、修改参数、Undo/Redo、保存、处理外部冲突、关闭重开；
不支持 Python 只读且不能覆盖。Qt 测试不依赖旧类名或架构层数。

**Focused tests**：

- `tests/test_editor_session.py`
- `tests/test_editor_commands.py`
- `tests/test_editor_window.py`
- `tests/test_editor_external_changes.py`

**Evidence（2026-08-28，独立只读验收 APPROVE）**：Structural PASS。增量仅
`pyproject.toml`、`src/editor/{__init__,app,window,session,commands}.py` 和四个 focused
tests；唯一 `pystg-editor = src.editor.app:main` 入口。一个 `EditorWindow` 只持有一个
`EditorSession`，Session 唯一拥有工程、选择、dirty、build/preview 占位状态和单一
`QUndoStack`；Coordinator/Service/Port/Intent/Plugin Registry/DocumentManager、QProcess、
自动预览及 Runtime/renderer/compiler 依赖均为零，UI 为简体中文且源码只读。Runtime PASS
（CD4 工作流）：真实 authoring 工程 open/navigate/edit/undo/redo/save/new-session reopen、
窗口 Inspector 修改、clean reload、dirty conflict、显式 keep/reload、删除文件和 unsupported
只读保真均通过；`python -m pytest -q tests/test_editor_session.py
tests/test_editor_commands.py tests/test_editor_window.py tests/test_editor_external_changes.py` 为 11
passed/1.814s，全仓为 353 passed/10.461s。外部冲突只有明确点击 keep/reload 才授权，取消
保持 pending/conflict 且 Save 可再次决策；reload 清空整个 Undo 栈，keep 后可继续编辑并原子
保存。Performance PASS：focused 1.814s、全仓 10.461s、compileall 0.242s；资产校验 71
JSON、16 sprite configs、745 sprites、142 images，0 error/0 warning；diff/cached check 通过。
Native：not run，本轮未做真实可见 Windows 人工交互，offscreen Qt 不冒充 Native；Usability：
not run，无真人维护者实操。generated 未 tracked，`.claude/settings.local.json` 未修改、未暂存。

## 8. CD5：固定布局、程序树与资源拖拽

**Owner**：Editor interaction Agent。

**允许路径**：`src/editor/window.py`、`session.py` 中仅交互命令入口与派生资产查询、
sidebars/program_tree/inspector/code_view/output/timeline UI、commands、focused Qt tests、
`tools/verify_native_code_editor_layout.py`。

**禁止路径**：Authoring/compiler/runtime/renderer 语义、preview process、资产编辑器、插件。

**实施**：

1. 固定 Activity Bar 四视图、中央 Editor/Game 两组、右侧 Inspector、永久底部
   Timeline 和可折叠 Problems/Log。
2. 中央组可关闭、恢复和调宽；Timeline 可调高但不可关闭。
3. 程序结构仅导航 Project/Stage/Unit；中央显示当前单元真实节点树。
4. 节点拖拽精确实现 Before/After/Child/Wrap，一次释放一个可撤销命令。
5. Inspector 由构造函数类型注解生成控件。
6. 全局资产扫描工程；Stage 资产遍历显式 `Ref` 和 `res://`，不猜 RawPython 字符串。
7. 兼容字段拖入直接赋值；插入线拖入先显示少量明确动作，再提交命令。

**Gate**：1480x920 与 960x640 的 Qt 自动布局和真实原生窗口均可操作；四侧栏、中央组恢复、
Inspector、Timeline、四种拖拽、参数和资源编辑、模板调用保留及 Undo/Redo 通过。

**Focused tests**：

- `tests/test_editor_layout.py`
- `tests/test_editor_program_tree.py`
- `tests/test_editor_inspector.py`
- `tests/test_editor_assets.py`

**Evidence（2026-08-28，独立只读验收 APPROVE）**：Structural PASS。CD5 增量仅在
`src/editor/{window,session,commands,sidebars,program_tree,inspector}.py`、既有窗口测试、
四个 focused tests、native layout verifier 和本阶段 allowlist；Authoring/compiler/runtime/
renderer 未改，Gemini 隔离目录未接入。四 Activity views、独立可关闭/恢复/调宽的 Editor/
Game、右 Inspector、不可关闭且不被输出区替代的底部 Timeline、真实 Before/After/Child/
Wrap drop、typed Inspector、全局/Stage 传递资产、RawPython/Expr 不猜资产、明确资源动作、
模板聚合保留及单一 Undo/Redo 均有直接覆盖，禁用架构和 skip/xfail 零命中。Runtime PASS
（CD5 交互路径）：`python -m pytest -q tests/test_editor_layout.py
tests/test_editor_program_tree.py tests/test_editor_inspector.py tests/test_editor_assets.py` 为 12
passed/2.296s；CD4+CD5 focused 为 23 passed，本仓 `python -m pytest -q` 为 365 passed/
12.079s，真实 Qt drop、Inspector/资源修改、保存重开与 Undo/Redo 均执行。Native PASS（CD5
范围）：清除 `QT_QPA_PLATFORM` 后 `python tools/verify_native_code_editor_layout.py` 为
1.228s，Qt platform `windows`、真实 exposed native window；1480x920 的 Editor/Game 宽度
468/467px，960x640 为 208/207px，四侧栏、中央组恢复、Inspector 和永久 Timeline 均通过；
显式 offscreen 被 verifier exit 1 拒绝。本阶段不声称 CD6 GLFW 嵌入。Performance PASS：
focused 2.296s、全仓 12.079s、compileall 0.254s、资产校验 0.567s 且 0 error/0 warning；
authoring+compiler+editor 9270 行，低于最终 12000 当前预算。Usability：not run，无真人维护者
实操。diff/cached check 通过，generated 未 tracked，`.claude/settings.local.json` 未暂存。

## 9. CD6：真实预览与 Trace

**Owner**：Preview Agent。

**允许路径**：`src/editor/preview.py`、预览相关 session/window 接线、`main.py` 控制入口、
生成 Trace 支持、标准练习场、focused preview/runtime/native tests。

**禁止路径**：作者 schema、Timeline 静态规则、renderer 语义、第二预览模式、热重载。

**实施**：

1. 单一 QProcess 启动真实 `main.py`，复用并瘦身 Win32 嵌入逻辑。
2. Run 自动保存无冲突文件并构建；成功后才替换旧预览。
3. 编辑后只标记 stale；再次 Run 才重建。
4. 实现限定控制/事件协议、run identity、输出/Trace 上限和异常清理。
5. 支持 Project、Stage 和由标准练习场包装的 Wave/Enemy/Spell。
6. 固定 seed；seek 以相同 seed 重启并关闭音频/中间帧呈现快速推进。
7. 生成代码在节点边界批量 Trace，不附加逐弹 callback。

**Gate**：真实 Windows PySide6 + GLFW/ModernGL 子进程成功嵌入；键盘焦点进入游戏；
pause/resume/restart/seek/stop 可用且无遗留子进程；构建失败保留旧预览；stale 行为正确；
Trace 不阻塞帧。

**Focused tests**：

- `tests/test_preview_protocol.py`
- `tests/test_editor_preview.py`
- `tests/test_preview_practice.py`
- `tests/test_preview_trace.py`
- `tools/verify_native_code_editor_preview.py`

**Evidence（2026-08-29，独立只读验收 APPROVE）**：Structural PASS。CD6 增量仅在
preview/session/window 接线、`main.py` 控制入口、compiler 练习场与 Trace、StageContext/
StageManager 有界批处理、focused tests 和真实 native verifier；单一 `QProcess` owner、固定
五控制/七事件协议、run identity、stdout/stderr/Trace 硬上限、stale 不热重载、prepare 成功
前保留旧预览、发布失败回滚、Win32 PID/style/`SetParent`/focus/release 均有直接覆盖。旧八
符号、旧 preview formal/legacy 双模式、skip/xfail 和逐弹 Trace callback 零命中；Gemini 代码
仅在被 `/trash/` 忽略的隔离目录，生产零导入、零 tracked 文件。Runtime PASS：focused
`python -m pytest tests/test_preview_protocol.py tests/test_editor_preview.py
tests/test_preview_practice.py tests/test_preview_trace.py tests/test_editor_window.py
tests/test_editor_layout.py tests/test_compiler_package_builder.py` 为 42 passed/10.981s，全仓为
395 passed/18.070s；Project/Stage/Wave/Enemy/Spell、固定 seed restart/seek、真实生成包、
`StageManager` 稀疏 Trace 和批量弹幕路径通过。Native PASS：清除 `QT_QPA_PLATFORM` 后
`python tools/verify_native_code_editor_preview.py` 为 PASS/19.660s，Qt platform `windows`，
真实 GLFW/ModernGL 子窗口成功嵌入并取得键盘焦点；1480x920 时 host/child 均 447x696，
960x640 时均 390x416；pause/resume/restart/seek/stop、Trace 和无孤儿进程通过。Performance
PASS：compileall 0.232s；资产校验 0.475s，73 JSON、16 sprite configs、745 sprites、142
images，0 error/0 warning；相关产品代码 10538 行，低于 12000 行预算；diff/cached check
通过。Usability：not run，无真人维护者实操。generated 和 `.claude/settings.local.json` 未暂存。

## 10. CD7：Timeline 与完整关卡证明

**Owner**：Timeline/acceptance Agent。

**允许路径**：headless Timeline analyzer、`src/editor/timeline.py`、timeline commands、完整
声明式示例工程、focused timeline/acceptance/native/performance tests、本文证据。

**禁止路径**：独立 Timeline 文档、任意条件/循环重写、旧格式兼容、renderer 语义、新插件
或资产工具。

**实施**：

1. 从程序模型生成顺序、Wait、awaited duration、Repeat、Parallel、SpawnTask、If、动态未知
   和模板聚合区间。
2. 用实际 Trace 覆盖本次分支和持续时间，不写作者文件。
3. 节点/区间双向选择。
4. 唯一反向编辑：字面量 `Wait`、字面量 `duration`、字面量 `At.frame`；其他拖动拒绝。
5. 提交完整示例：1 Stage、2 Wave、2 Enemy、1 Boss、1 NonSpell、1 Spell、参数化 Task、
   保留调用模板、Parallel、RawPython、BGM/背景/SE/对话引用、三类预览、静态与动态区间。
6. 运行最终 Structural、Runtime、Native、Performance 门禁；维护者实际操作前，Usability
   明确写 not run。

**Gate**：

- 旧符号、模块、内容、入口和兼容层为零；
- 完整示例保存/重开/构建确定，Project/Stage/Spell 经真实 Runtime 运行；
- Timeline 静态/动态/Trace 和三种反向编辑正确且可撤销；
- 真实嵌入在 1480x920、960x640 可操作且无遗留进程；
- DSL/生成器 <15s，编辑器自动化 <60s，PR 主门禁 <5min；
- 新相关产品代码目标 <=12,000 行，产品代码净删除显著大于新增；
- `.claude/settings.local.json` 和生成目录均未暂存。

**Focused tests**：

- `tests/test_timeline_analysis.py`
- `tests/test_editor_timeline.py`
- `tests/test_code_editor_acceptance.py`
- CD2-CD6 全部 focused gates
- `tools/verify_native_code_editor.py`

**Evidence（2026-08-29，独立只读验收 APPROVE）**：Structural PASS。CD7 增量只包含
headless Timeline、Qt Timeline 及必要的 session/preview/window 接线、完整声明式示例、
focused tests 和最终 native verifier；顺序、Wait/At/duration、Repeat、Parallel、SpawnTask、
If、动态未知、引用单元、项目/显式外部/缺失模板聚合和同 run identity Trace 均有直接覆盖。
动态 Wait 不宣称可编辑，未解析 Call 保留 Problems 并投影 Unknown；三种反向编辑全部进入
唯一 Undo 栈。旧八符号、旧模块/作者内容、skip/xfail、独立 Timeline 文档、生产 Gemini
导入和 tracked trash/generated 均为零；`.claude/settings.local.json` 未暂存，diff checks 通过。
Runtime PASS：CD7 focused 21 passed；CD2-CD7 focused 270 passed/19.94s；全仓
`python -m pytest -q` 为 416 passed/21.50s。完整示例可解析、保存重开、确定性构建并由现有
`StageManager` 使用真实 `OptimizedBulletPool` 跑到对话结束，保留批量弹幕且逐弹 callback
为零；Project/Stage/Spell 三目标走真实生成/运行路径，手写 Stage1-Stage3 默认入口保持。
Native PASS：清除 `QT_QPA_PLATFORM` 后 `python tools/verify_native_code_editor.py` 为
PASS/39.657s，Qt platform `windows`；Project/Stage/Spell 的真实 GLFW/ModernGL 子窗口均
成功 Win32 嵌入并取得键盘焦点，host/child 分别为 449x663、390x383、390x383；
Wait/duration/At、pause/resume/restart/seek/stop、Trace run identity 和停止清理通过，无遗留
进程。1480x920 与 960x640 的原生布局另行验证 Editor/Game、Inspector 和永久 Timeline
均可操作。Performance PASS：DSL/compiler 197 passed/6.24s <15s，编辑器自动化
63 passed/14.652s <60s，主门禁 <5min；compileall 0.232s，资产校验 0.441s，79 JSON、
16 sprite configs、745 sprites、142 images，0 error/0 warning；保守按 authoring/compiler/
editor 物理总行与 preview Runtime 支持净增计 11889 行 <=12000，归档基线产品代码净删除
约 31266 行，显著大于新增。Usability：not run，没有真人维护者完成实际工作流。

## 11. 最终报告格式

最终报告不得只给一个“全部通过”。必须分别写：

```text
Structural: PASS/FAIL + 命令/结果
Runtime: PASS/FAIL + 手写关卡和生成示例真实路径
Native: PASS/FAIL/not run + 窗口、嵌入、焦点、控制、尺寸
Performance: PASS/FAIL/not run + 时间、代码量、目标硬件
Usability: PASS/FAIL/not run + 真实维护者操作；不得合成
```

任何未观察类别不得暗示通过。完整实现完成后，生成目录仍不入 Git。
