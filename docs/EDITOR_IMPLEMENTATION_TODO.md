# PySTG 下一代编辑器未来实施 TODO（固定版）

> 状态：Active；N7 已暂停，下一任务是 ER3。本文是仓库唯一的未来实施清单，也是 Agent 的交接协议。
> 产品依据：[EDITOR_PRODUCT_VISION.md](EDITOR_PRODUCT_VISION.md)；工程边界：[EDITOR_ARCHITECTURE.md](EDITOR_ARCHITECTURE.md)。
> 本版固定日期：2026-08-20。历史路线图和完成日志只通过 Git 追溯，不再作为任务来源。

这份文件保留已完成阶段的冻结证据，并详细描述尚未完成的工作。任务 ID 一旦发布就保持稳定；Agent 只能领取依赖链上最早的未完成任务。没有对应测试和证据，不能把“已有一部分代码”当作完成。

## 0. 先读这几条固定结论

### 0.1 产品边界

- 短期和中期不做自然语言或 Agentic 弹幕生成。帧、角度、速度、数量、随机种子、生命周期和预算必须由确定性的属性、曲线、预设、上下文搜索或行为图表达。
- 三条职责轴互相解耦：Content 是版本化数据和标准组件，Behavior 是动作/事件/脚本的生命周期，Tool 是编辑器插件。三者共享类型、资源引用、owner/cancel 和调试协议，但不互持 Qt 对象、运行时对象或 Clip ID。
- 三层权限不是三套对象模型：Safe API 面向内容作者，Runtime API 面向玩法开发者，Engine API 面向引擎开发者。普通项目不能因为使用一个 Runtime 行为而获得 Engine 内部对象。
- 作者文档是唯一真源。运行时变量、事件、实例、trace 和 overlay 不写回文档，不制造 dirty；所有作者编辑都经过 `CommandStack` 并支持 Undo/Redo。

### 0.2 状态图、时间线、行为图的边界

| 视图 | 只回答的问题 | 允许保存的内容 | 不允许承担的内容 |
| --- | --- | --- | --- |
| State Graph | 现在处于哪个阶段，何时转移 | State、转移条件、进入/退出 owner | 逐弹算法、局部采样、隐式长连线 |
| Timeline | 哪些生命周期在何时有效、持续、停止 | 轨道、片段、窗口、激活规则、资源引用 | 复制行为图内部节点、直接调用另一个视图的对象 |
| Behavior Graph/Runtime Behavior | 一个行为内部怎样计算、采样、循环和发布事实 | 局部动作、变量读写、事件输出、取消收尾 | 持有 State/Timeline 内部 ID、偷偷切状态或背景 |

行为、碰撞和对象生命周期只发布“发生了什么”的类型化事实，例如 `enemy.hit`、`bullet.terminated`、`encounter.cleared`。`ReactiveClip`/`ActivationRule` 决定事实在当前 State/时间窗口中是否有效，`TaskScope` 负责启动后的等待、循环、取消和收尾。事件不能携带 `start_clip`、`set_background_scene` 等消费者命令。

### 0.3 必须贯穿所有阶段的三个例子

1. **死亡开花**：子弹自然到期发布 `bullet.terminated(reason=expired)`；反应可以来自子弹预设，也可以来自后半段时间线的 `ReactiveClip`。清场、越界、热重载等原因不能误触发自然死亡开花。
2. **假 Boss 受击反击**：假 Boss 只发布 `enemy.hit(target_tag=fake)`；关底 State 的 `ReactiveClip` 过滤事实，选择 `count_per_frame`、冷却、最大实例和 owner。State 退出优先取消旧反应。
3. **击破后背景切换**：如果击破代表阶段变化，State Graph 处理转移；如果只是演出，时间线上的反应槽处理 Background cue。Boss/行为不持有背景片段 ID。

### 0.4 顶层作者的默认流程

1. 项目向导创建道中或关底 Stage 骨架。
2. State Graph 建立 Intro/Normal/Enrage/End 等阶段，只在阶段边界放转移。
3. 每个 State 的时间线安排敌人、Boss 移动、背景、音频、弹幕和演出；有条件的内容放 `ReactiveClip` 槽位。
4. Pattern 先选预设，在 Inspector 中精确调数量、间隔、角度、速度、曲线和预算；只有局部表达力不足时才展开。
5. 行为图只承接采样、循环、数学和事件生产，不承接整关卡流程。
6. 预设、Action、受限表达式和行为图都不足以表达新算法时，玩法开发者才写 Runtime Behavior；普通内容作者不需要写脚本。
7. 预览、调试、seek、reset、保存、重开和热重载都走正式 runtime；运行时 overlay 只读显示。

时间轴拖动“从头重放到目标帧”的结构性成本本路线不解决，只冻结 reset/replay 的正确性和可观察性。

## 1. 已冻结的仓库基线

这些能力已经在 `main` 上完成，后续任务只能依赖它们，不得重新发明第二套语义：

| 基线 | 冻结内容 | 主要入口 | 回归入口 |
| --- | --- | --- | --- |
| N0/N1 | 版本化作者资源、`SceneDocument`、内嵌 State Graph、稳定 UUID、正式 Pattern/Stage 预览 | `src/editor/document.py`、`src/editor/stage_compile.py` | `tests/test_scene_v4_contract.py`、`tests/test_state_graph_document.py`、`tests/test_state_graph_runtime.py` |
| N2 | 类型化变量、六类作用域、单一写入者、reducer、只读 Engine Snapshot、CommandStack、reset/seek/hot-reload | `src/authoring/variables.py`、`src/game/stage/program.py` | `tests/test_typed_variables.py`、`tests/test_variable_runtime.py`、`tests/test_variable_scopes_and_reducers.py`、`tests/test_variable_seek.py`、`tests/test_variable_hotreload.py` |
| N3 | 本帧 Outbox→下一帧 Inbox、类型化生命周期事实、批量生命周期事件、`ReactionSpec`、`TaskScope`、State/Background hook | `src/game/events.py`、`src/game/reactions.py`、`src/game/stage/context.py` | `tests/test_lifecycle_events.py`、`tests/test_frame_boundary_events.py`、`tests/test_lifecycle_batching.py`、`tests/test_reactions.py`、`tests/test_reaction_scheduler.py`、`tests/test_lifecycle_timeline_hooks.py`、`tests/test_background_reactions.py` |

N2/N3 focused gate 和全量回归必须保持绿色。它们不是后续阶段可以删掉的“旧测试”；若契约必须改变，先提交独立的 contract-revision 并停止后续阶段。

## 2. 每个 Agent 必须遵循的执行协议

每个任务都按 `Read → Audit → Contract → Implement → Verify → Record` 执行，且交接卡必须写明任务边界。

### 2.1 Read

1. 运行 `git status --short`，记录并保护工作树中不属于本任务的改动。
2. 完整阅读任务列出的产品章节、源码入口、schema、fixture 和已有回归；先看真实代码，再看 TODO 的假设。
3. 确认正式运行入口（compiler、runner、preview、editor command），不得把独立模拟器当成实现目标。

### 2.2 Audit

1. 运行该任务依赖的 focused gate，记录当前通过数和失败边界。
2. 用真实 `SceneDocument`/资源 fixture 观察序列化、编译、运行、预览和 reset 行为。
3. 明确本任务不处理的相邻文件、UI 面和 API，避免“顺便重构”。

### 2.3 Contract

1. 只在任务开始时创建列出的 Contract 测试，先形成真实红色基线。
2. 测试必须有可观察的行为、最小真实 fixture、错误路径和稳定诊断位置；禁止只测 import、源码字符串、空 `pass`、宽泛 `except`、`skip` 或 `xfail`。
3. Contract 一旦提交，后续实现不得削弱断言、吞异常、改成第二套预览或把运行时状态写回文档。

### 2.4 Implement

1. 只修改任务边界内的 authoring/compiler/runtime/editor 文件。
2. 保持项目相对资源引用、`ProjectContext`、批量弹幕路径、owner/cancel 传播和正式 runtime 预览。
3. 所有文档修改通过 `CommandStack`；运行时 overlay、trace、预算统计不制造 dirty。

### 2.5 Verify

按任务顺序运行 focused gate、N2/N3 回归、全量 suite、`compileall`、资源校验和 `git diff --check`。证据必须分开标注：Structural、Runtime、Performance、Native visual、Usability。offscreen Qt 或 `--help` 不能替代原生窗口、性能或人工可用性证据。

### 2.6 Record 与停止条件

交接消息或提交说明必须包含：

| 字段 | 必须写明 |
| --- | --- |
| Task ID / 边界 | 领取的 ID，以及明确不处理的相邻任务 |
| Read / Audit | 实际读过的章节、入口、schema/fixture、回归和 `git status` |
| Contract | 新增/扩展的测试、红色基线、真实 fixture 和错误边界 |
| Implementation | 修改的 authoring/compiler/runtime/editor 文件，以及 owner、取消、迁移和错误路径 |
| Verification | focused、回归、全量、compileall、资产校验、diff-check；额外 native/performance/usability 命令 |
| Evidence / Blocker | 通过数量、环境、报告路径和仍缺的门禁；阻塞时保持 `[ ]` |

遇到以下情况必须停止扩大范围并请求维护者决定：产品契约冲突、schema 无法无损迁移、必须逐弹回调/第二套预览/静默 fallback/绕过 Undo、focused gate 仍红却要进入下一阶段、当前环境无法提供 native/performance/usability 证据，或无法安全合并用户改动。

### 2.7 Agent 所有权与独立验收

1. 每个 ER 任务开始前必须写明实现 Agent、验证 Agent、允许路径和禁止路径；默认边界见仓库根 `AGENTS.md`。
2. 同一 Agent 不能既实现又最终验收同一 ER 任务。验证 Agent 对产品代码只读，只能运行门禁和更新当前任务的 Evidence/Blocker。
3. 只有主协调 Agent 可以解决跨目录集成、更新总表状态和宣布进入下一任务；实现 Agent 不得自行勾选完成。
4. 两个 Agent 不得并发编辑同一模块、兼容出口或 Contract。需要跨边界时先停止，由主协调 Agent 明确扩展 allowlist。
5. Contract 修订与产品实现分开审查。实现 Agent 不能删测试、放宽断言、加 `skip`/`xfail`、伪造 native/usability 报告或用直接调用槽函数代替真实交互。

## 3. 测试与文档清理规则

### 3.1 本轮已清理

- 历史路线图 `docs/EDITOR_ROADMAP_TODO.md` 和 `docs/ARCHITECTURE_EVALUATION_AND_ROADMAP.md` 已从当前 Git 历史的工作协议中移除；本文件是唯一 Todo，不创建 `*_TODO_v2.md`。
- N4.0 已将 `tests/test_activation_rules.py`、`tests/test_reactive_timeline.py`、`tests/test_timeline_instance_trace.py` 固定为正式 Contract；它们不再是临时草稿，后续阶段必须保持其断言语义。
- 删除重复的 `tests/test_stage_context_bullet_spawn.py`。它只做 regular/polar spawn 的 smoke 检查；极坐标语义由 `tests/test_polar_motion_unit.py` 覆盖，正式 Pattern/Stage 路径由 `tests/test_pattern_runtime.py`、`tests/test_stage_program.py` 和 `tests/test_preview_controller.py` 覆盖。

### 3.2 保留规则

`test_editor_app_smoke.py`、`test_editor_m3_integration.py`、`test_editor_m4_integration.py`、`test_editor_m5_integration.py`、`test_editor_m6_integration.py`、`test_editor_m6_workspace.py` 以及 `test_editor_authoring_integration.py`、`test_editor_regression_contracts.py` 都有保存/编译/运行/Undo/Redo/原生崩溃或插件行为断言，必须保留。不能因为测试慢、需要 Qt、文件名带 smoke、暂时失败或想让 suite 变绿而删除测试。

以后删除测试必须同时满足：它只验证已经移除的接口或重复交接流程；对应行为已有更窄、更真实的替代测试；提交说明给出替代文件和 suite 数量变化。

### 3.3 共同命令

~~~powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q main.py src game_content tools tests
python tools/validate_assets.py --format json
git diff --check
~~~

### 3.4 2026-08-20 跨阶段工程整改

对 `src/editor/` 57 文件做全量 AST 结构比对与调用链可达性追踪后，确认 9 项「已记 `[x]` 但证据或作者入口不成立」的问题和 7 项冗余。以下改动一律不新增功能、不删测试、不放宽断言。

**门禁与安全网**

- pytest 会话绑定改为 PySide6（`tests/conftest.py` 与 `src/qt_compat/__init__.py`），与 `tools/scene_editor.py` 及三个 native gate 使用同一绑定。此前全部测试跑在 PyQt5(sip) 而生产跑 PySide6(shiboken)，两者 C++ 对象所有权与 GC 时机不同，「拖线过程中重建不崩溃」这类测试在 PyQt5 上通过并不构成 PySide6 上的证据。
- `tools/verify_native_editor_n4.py` 重写为真跑 `compile_stage → StageRunner`，见 N4.2 的 Evidence（2026-08-20 重做）。
- `tests/test_editor_usability.py::test_n6_usability_claim_and_report_must_agree` 取代原先断言「`reports/n6_usability.json` 不存在」的写法。原断言把报告缺席编码成永久不变量，真正提交人工研究报告的当天测试就会因为错误的理由变红；现在断言的是声明与证据必须一致，两种世界下都成立。
- 新增 `tests/test_editor_i18n_coverage.py`：遍历真实编辑器控件树，对 i18n 层声称拥有却译不出的作者可见文案直接失败。此前 458 条以英文源串为键的词条只有点检测试，改动任一英文文案都会让对应中文静默失效且无人发现。

**作者入口补齐（此前属于「写了实现但没接按钮」）**

- Reactive 片段双击进入局部视图：`TimelineEditor._clip_activated` → `navigate_reactive_clip()`，该方法此前全仓零调用者。
- `SetPresetSlotOverrideCommand` 与 `ApplyPresetMigrationCommand` 接入 PatternWorkspace 的插槽表单和迁移按钮，见 N5.3、N5.4 的整改证据。
- `stage_compile` 的 State 动作路径不再静默 `continue` 跳过错误的变量载荷，与 Clip 路径一样发 `invalid_variable_automation` 诊断。

**冗余消除（零行为变化的提取，除一处已标注的收敛）**

- `MergeableCommand`（`src/editor/commands.py`）承载原先 12 处逐字重复的 `merge_with()`；子类只声明 `merge_owner` / `merge_identity` / `merge_same_keys` / `merge_values`。
- `SpaceTapSearchMixin`（`src/editor/action_search.py`）承载 Scene、Graph、Timeline 三份重复的「按住空格平移、轻按空格搜索」状态机。提取过程中修掉一个真实缺陷：`SceneViewport` 在 `setDragMode(RubberBandDrag)` 之前就记下待恢复的拖动模式，一次没有配对按下的空格释放会静默关掉框选。
- 新增 `src/editor/pattern_resolve.py`，承载 Stage 与 Spell 两条编译路径共用的 Pattern 引用解析与出生点规则。此前 `scene_compile` 只认直接父级恰为 `Emitter`，`stage_compile` 走完整祖先链并接受任何带 `x`/`y` 的节点（例如 `Boss`），同一场景在两条路径下会在不同位置出弹。**行为变化**：`Spell > Boss(x,y) > PatternInstance` 这类结构的 M3 预览现在采用 Boss 位置，与正式路径一致。`scene_compile.py` 保留而非删除——`tests/test_editor_scene_compile.py`、`tests/test_editor_m3_integration.py` 覆盖的是 M3 无脚本 Spell 流程，删文件等于删一个受测功能；它现在与正式路径共用同一套解析规则，不再是第二套语义。
- `stage_compile._variable_spec_for` 改为委托 `_variable_candidates`，此前两函数逐行同构。
- 删除死符号 `flat_snapshot`、`set_error_visual`、`set_metadata`、`template_for_emission`，以及仅为兼容测试而隐藏保留的 `mode_switch` 控件（Qt 虚函数覆写如 `mimeTypes` / `filterAcceptsRow` / `drawForeground` 由框架调用，不动）。
- 五个 93–183 语句的 `__init__`（`PatternWorkspace`、`VariableEditor`、`StateGraphEditor`、`PatternPreviewPanel`、`TimelineEditor`）拆为 `_build_*` 私有构建器，抽出的构建器最大 49 语句（`EditorMainWindow._build_ui` 的 195 语句属于下面延后的 R1 范围）；`PatternWorkspace` 六处重复的视图切换收敛为 `_show_view()`。

**当时明确延后、现已被新决策取代**：该轮没有整改 `EditorMainWindow` 的状态所有权、协调器、预览和插件边界。后续提交 `bdd974e` 将窗口按八个 `SlotsMixin` 拆为多个文件，但 Mixin 仍共享同一窗口实例、私有方法、`editor_context` 和全局 `_refresh()`；它只完成物理拆分，不构成架构门禁通过。

**整改门禁（2026-08-20，Python 3.12.7 / PySide6 6.8.1.1）**

- `QT_QPA_PLATFORM=offscreen python -m pytest tests --no-header` → `641 passed in 539.41s`，无 skip/xfail；其中 `test_editor_i18n_coverage.py` 为本次新增，`test_n6_usability_claim_and_report_must_agree` 取代同名位置上的旧断言，其余用例集未删减。
- `python -m compileall -q src tools tests` → 通过。
- `python tools/validate_assets.py --format json` → `issues` 为空。
- `git diff --check` → 无空白错误；改动文件全部保持 LF 行尾（仓库 `core.autocrlf=false`）。

### 3.5 2026-08-20 架构复审与暂停决定

对 `bdd974e` 的只读复审确认：`src/editor/` 当前 51 个 Python 文件、约 21,157 行；`EditorMainWindow` 仍是 `QMainWindow + 8 SlotsMixin`，`app.py` 有 198 个不同 `self` 成员，九个窗口/Mixin 模块共享 `session`，约 69 处调用 `_refresh()`。`ManagedDocument.editor_context` 仍是 `dict[str, Any]`；ER1 Contract 的逐键审计把旧计数 21 更正为 22 个隐式键（18 个文档选择/视图值和 4 个 preview overlay 值）。

同时确认：

- `src.authoring.registry` 和 `src.preview.controller` 反向导入 `src.editor` 文档/编译模块；
- `graph_workspace` 与 `pattern_workspace` 循环导入；
- 窗口同时持有正式 `PatternPreviewProcess` 与旧裸 `QProcess` 预览路径；
- 窗口同时持有 workbench 与 SDK 两套插件 registry；
- `SceneEditorSession` 与 `DocumentManager` 重复文档生命周期；
- `ManagedDocument` 的类型标注未覆盖实际支持的 UI/Background；
- `CURRENT_SCHEMA_VERSION` 通过重载相等比较同时与 3 和 4 相等。

因此维护者决定在 N7 前插入 ER0–ER8。ER 是保持作者语义的架构整改，不是 N7 功能开发，也不重做时间线、行为图、schema、渲染器或正式 runtime。ER8 通过前不得再次执行 N6.4 五人研究；N6.4 通过前不得启动 N7。

## 4. 未完成任务总表

依赖顺序固定为：`N4 → N5 → N6.3 → ER0 → ER1 → ER2 → ER3 → ER4 → ER5 → ER6 → ER7 → ER8 → N6.4 → N7 → N8 → N9`。同一阶段内按编号顺序领取；当前阶段 focused gate 未通过，不得开始下一阶段。

| ID | 主题 | 状态 | 依赖 |
| --- | --- | --- | --- |
| N4.0 | 响应式时间线 Contract | `[x]` | N3 |
| N4.1 | ReactiveClip 正式运行时与实例 trace | `[x]` | N4.0 |
| N4.2 | 时间线槽位、overlay、导航与冲突编辑 | `[x]` | N4.1 |
| N5.0 | 版本化预设 Contract | `[x]` | N4 |
| N5.1 | 首发预设库 | `[x]` | N5.0 |
| N5.2 | 虚拟展开 | `[x]` | N5.1 |
| N5.3 | 参数覆盖与本地物化 | `[x]` | N5.2 |
| N5.4 | 精确版本迁移 | `[x]` | N5.3 |
| N6.0 | Action Catalog 与新手流程 Contract | `[x]` | N5 |
| N6.1 | 上下文感知搜索 | `[x]` | N6.0 |
| N6.2 | 道中/关底骨架模板 | `[x]` | N6.1 |
| N6.3 | 分层展开与连续编辑 | `[x]` | N6.2 |
| ER0 | 文档、边界 Contract 与真实基线 | `[x]` | N6.3 |
| ER1 | 有类型的编辑状态 | `[x]` | ER0 |
| ER2 | Coordinator 与局部失效 | `[x]` | ER1 |
| ER3 | Authoring/Command/Compiler 包边界 | `[x]` | ER2 |
| ER4 | 唯一 PreviewSession | `[x]` | ER3 |
| ER5 | 唯一插件贡献入口 | `[x]` | ER4 |
| ER6 | Panel 边界与图形循环 | `[x]` | ER5 |
| ER7 | 兼容层、schema 与重复生命周期清理 | `[x]` | ER6 |
| ER8 | 架构整体验收 | `[x]` | ER7 |
| N6.4 | Usability gate | `[ ]` | ER8 |
| N7.0 | Behavior Descriptor/权限 Contract | `[ ]` | N6.4 |
| N7.1 | Safe API | `[ ]` | N7.0 |
| N7.2 | Runtime API | `[ ]` | N7.1 |
| N7.3 | Engine API | `[ ]` | N7.2 |
| N7.4 | 分区插件包、依赖锁与回滚 | `[ ]` | N7.3 |
| N7.5 | ComplexMapEmitter 示范插件 | `[ ]` | N7.4 |
| N8.0 | Render Graph Contract | `[ ]` | N7 |
| N8.1 | PassDescriptor 与编译器 | `[ ]` | N8.0 |
| N8.2 | 受限 PassContext 与资源 lease | `[ ]` | N8.1 |
| N8.3 | ModernGL backend adapter | `[ ]` | N8.2 |
| N8.4 | Tool/Runtime parity | `[ ]` | N8.3 |
| N9.0 | 调试、重放、性能 Contract | `[ ]` | N8 |
| N9.1 | 统一 trace 与 why-not 调试器 | `[ ]` | N9.0 |
| N9.2 | 确定性 replay/seek | `[ ]` | N9.1 |
| N9.3 | 性能 profile 与预算 | `[ ]` | N9.2 |
| N9.4 | 最终作者工作流 | `[ ]` | N9.3 |
| N9.5 | 发布门禁 | `[ ]` | N9.4 |

## 5. N4：响应式时间线与蓝图边界

### N4.0 Contract：冻结激活规则

**Agent 要做（按序）**

1. 阅读产品愿景第 7、10、17 节，`src/editor/document.py`、`src/editor/timeline_commands.py`、`src/game/events.py`、`src/game/reactions.py`、N2/N3 回归和 scene schema。
2. 创建 `tests/test_activation_rules.py`、`tests/test_reactive_timeline.py`、`tests/test_timeline_instance_trace.py`，使用最小 Scene/Pattern fixture 先形成红色基线。
3. 冻结 `at_frame`、`when_variable`、`on_event`、`on_lifecycle` 的数据表示；冻结变量路径/比较/边沿、事件过滤/密度、来源/owner/终止原因、delay、scope、窗口和取消语义。
4. 冻结默认 `once_per_scope + max_instances=1 + ignore_while_running`，显式 `restart/parallel`，以及未知字段、类型错误、路径错误和未来字段的结构化诊断。
5. 覆盖死亡开花、假 Boss 受击和背景切换；断言事件只描述事实，不携带 `start_clip` 等命令。

**完成条件**：Contract 在没有新 runtime 实现时保持可解释的红色预期；规则 round-trip、边沿、重入、延迟、窗口结束、State 退出、owner 和诊断路径均有行为断言。

**验收文件**：`tests/test_activation_rules.py`、`tests/test_reactive_timeline.py`、`tests/test_timeline_instance_trace.py`。

**Evidence（2026-08-10）**：Structural/Runtime：`python -m pytest -q tests/test_activation_rules.py tests/test_reactive_timeline.py tests/test_timeline_instance_trace.py`（10 passed）；规则 round-trip、变量边沿、固定帧/delay、窗口取消、owner、预算和 runtime identity 均有断言。

### N4.1 Runtime：激活、实例、预算与取消

**Agent 要做（按序）**

1. 将 `ReactiveClip`/`ActivationRule` 接入 `SceneDocument → src/editor/stage_compile.py → src/game/stage/program.py → StageRunner` 正式路径；不建立编辑器专用模拟器。
2. 按 Inbox → 同帧变量快照 → State 退出/取消优先 → 解析并启动仍有效实例 → 采样轨道的顺序运行；事件 dispatch 不重入。
3. 分离作者 Clip ID 和运行时 Instance ID；trace 记录 trigger kind/source/event、激活快照、实际触发帧、owner/cancel token、开始/停止原因、并发数、预算拒绝原因和 action resolver 诊断。
4. 实现 `on_rise`、`while_true`、`on_fall`、`on_change`、固定帧、动态 delay、事件/生命周期过滤；实例开始后变量变化不能回溯移动实例。
5. 将固定窗口、条件变假、行为完成、State 退出、显式取消、清场/热重载等终止原因区分开；owner 退出必须传播到 TaskScope、pending reaction 和批量 Action。
6. 施加最大实例数、每帧生成数、因果深度和批量预算；高密度生命周期不能扩展为逐弹 Python 对象链。

**完成条件**：正式 StageRunner 能跑三类例子；trace 能回答“为什么触发、何时开始、为什么停止、归谁所有”；reset+seek 与固定帧正常播放逐帧等价；作者 `to_dict()` 和 dirty 状态不变。

**验收文件**：N4.0 三份 Contract、`tests/test_reaction_timeline_integration.py`；回归 `tests/test_reactions.py`、`tests/test_reaction_scheduler.py`、`tests/test_state_graph_runtime.py`、`tests/test_stage_program.py` 及 N2/N3 focused gate。

**Evidence（2026-08-10）**：Runtime：`python -m pytest -q tests/test_reaction_timeline_integration.py tests/test_reactions.py tests/test_reaction_scheduler.py tests/test_state_graph_runtime.py tests/test_stage_program.py`（既有回归与 N4 集成通过）；正式 `SceneDocument → compile_stage → StageRunner → PreviewController` 路径保持 JSON-only authoring，trace/overlay 不写回文档。

### N4.2 Editor：生命周期槽位、徽标、导航、overlay 与冲突

**Agent 要做（按序）**

1. 修改 `src/editor/timeline_workspace.py`、`src/editor/app.py`、`src/editor/document.py`、`src/editor/timeline_commands.py`，让 `Reactive` 成为显式轨道/片段类型并有默认 payload。
2. 在片段上显示 `when/event/lifecycle` 徽标、窗口、scope、owner 和简短过滤摘要；点击槽位只导航到 Reaction/Blueprint 局部视图，不把状态图、时间线、行为图合并成一张万能图。
3. 将 runtime trace 作为只读 overlay 显示 instance、actual start frame、trigger、stop reason、owner、active count、预算拒绝；reset/replay 清理 overlay，不写文档。
4. 按 `target + property + variable` 分组显示冲突，能跳回 writer、区间和 reducer；所有增删改都用一个 `CommandStack` 事务并可 Undo/Redo。
5. 用真实 PySide6 窗口验证最小尺寸、时间线交互、导航、reset/replay 和 overlay；offscreen 只作为 Structural/Runtime 证据。

**完成条件**：新手能在槽位上理解“何时有效”，高级作者能进入局部行为实现；运行时 overlay 可观察但不污染作者资源；没有蓝图到时间线的隐形长连线。

**验收文件**：`tests/test_editor_reactive_clips.py`、`tests/test_reaction_timeline_integration.py`；回归 `tests/test_editor_timeline_model.py`、`tests/test_editor_timeline_workspace.py`、`tests/test_state_graph_editor.py`；另附 native visual 证据。

**Evidence（2026-08-20 重做）**：Structural/Runtime：`$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q tests/test_editor_reactive_clips.py tests/test_reaction_timeline_integration.py tests/test_editor_timeline_workspace.py tests/test_state_graph_editor.py`（通过）；offscreen Qt 仅作为结构和运行证据。Native visual：`Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue; python -u tools/verify_native_editor_n4.py --project . --screenshot $env:TEMP\pystg-n4-native-editor-script.png` 输出 `native_editor_n4_ok`。该门禁 2026-08-20 重写：不再手写 overlay 载荷，也不再直接调用编辑器的下游槽函数——脚本用编辑器自己的命令创作 Reactive 轨道/片段，`compile_stage` + `StageRunner` 真跑一次得到 `runner.reactive_overlay`，再经 `_handle_pattern_preview_event` 走编辑器自身的 runtime feedback 管线，最后用真实双击手势进入局部 Reaction 视图；同时验证 overlay 与导航都不写回文档。此次重写暴露并修好一个真实缺陷：编辑器默认 Reactive 片段的窗口只有 1 帧，而 runtime 在片段起始后的帧边界才判定 armed，因此该默认片段永远不会触发（见 `tests/test_editor_reactive_clips.py::test_default_reactive_clip_actually_arms_on_the_formal_runtime`）。

## 6. N5：可展开的版本化预设

### N5.0 Contract：描述、身份和迁移语义

**Agent 要做**：阅读产品愿景第 11 节、`src/pattern` 资源/编译器和 N4 规则；创建 `tests/test_preset_descriptor.py`、`tests/test_preset_expansion.py`、`tests/test_preset_migration.py`；冻结 stable preset ID/version、参数 schema、公开插槽、输入/输出变量、事件、虚拟内部 ID、覆盖优先级、精确版本锁、未知字段和迁移失败语义。

**完成条件**：Contract 能拒绝错误类型、缺失版本、未知字段和迁移环；预设实例不会因编辑器升级静默改变。

**验收文件**：`tests/test_preset_descriptor.py`、`tests/test_preset_expansion.py`、`tests/test_preset_migration.py`。

**Evidence（2026-08-13）**：Structural：三份 Contract 覆盖严格 JSON schema、stable ID、精确 semver、参数/槽位类型、未知字段、精确依赖锁、稳定虚拟身份、迁移环和失败路径；`python -m pytest -q tests/test_preset_descriptor.py tests/test_preset_expansion.py tests/test_preset_migration.py` 通过。

### N5.1 首发预设库

**Agent 要做**：以真实资源提供自机狙、奇数弹、偶数弹、圆形开花、扇形扫射、单/双/交错螺旋、加速旋转、延迟转向、子弹分裂、速度层叠、波纹、米弹墙；每个预设暴露少量精确参数、生命周期策略和预算，走正式 compiler/runner。

**完成条件**：预设可运行、可展开、可调参；与基础 Pattern 行为 parity；高密度路径无逐弹 Python 回调。

**验收文件**：`tests/test_preset_library.py`、`tests/test_pattern_parity.py`、`tests/test_pattern_compiler.py`；附固定 workload profile。

**Evidence（2026-08-13）**：Runtime/Performance：`game_content/presets/builtin_patterns.pystg.json` 固定 14 个 `1.0.0` 预设；`python tools/profile_n5_presets.py --output C:\Users\m1573\AppData\Local\Temp\pystg-n5-preset-profile.json` 在 Windows 11、Python 3.12.7、Intel64 Family 6 Model 151 上运行正式 compiler/runner，1836 发由 101 次批量写入完成，逐弹回调 0，总耗时 41.988ms（回归上限 2500ms）。延迟转向、加速旋转、速度层叠、波纹使用批量曲线；子弹分裂使用 owner 级批量生命周期 action。

### N5.2 虚拟展开

**Agent 要做**：只读显示内部发射器、参数和局部行为；虚拟节点 ID 由实例 ID+预设内部 ID 稳定派生；折叠/展开不复制 Scene 节点、不制造 runtime 实例，trace 能从外部实例定位内部节点。

**完成条件**：折叠、展开、保存、重开、reset 的 authoring/runtime identity 一致；没有第二份可漂移文档。

**验收文件**：`tests/test_preset_expansion.py`、`tests/test_editor_preset_workspace.py`、`tests/test_pattern_graph.py`。

**Evidence（2026-08-13）**：Structural/Native visual：虚拟 ID 由 instance UUID + internal ID 派生，折叠/展开不写 graph、不改变作者 payload，compiled program/replay identity 保留 preset/version/internal IDs；`python -u tools/verify_native_editor_n5.py --project . --screenshot C:\Users\m1573\AppData\Local\Temp\pystg-n5-native-editor.png` 输出 `native_editor_n5_ok presets=14 virtual_nodes=5`。

### N5.3 参数覆盖与本地物化

**Agent 要做**：公开参数和插槽可覆盖；“展开为本地结构”是可预览、可取消、可 Undo/Redo 的单一 CommandStack 事务；物化后与上游预设断开且不被升级偷偷改写；失败保留原实例。

**完成条件**：覆盖优先级和差异报告可解释；物化、撤销、重做、运行和 trace 可重放。

**验收文件**：`tests/test_preset_expansion.py`、`tests/test_editor_preset_workspace.py`、`tests/test_editor_authoring_integration.py`。

**Evidence（2026-08-13）**：Editor/Runtime：`ApplyPresetCommand`、参数/槽位覆盖和 `MaterializePresetCommand` 全部进入已有 `CommandStack`；本地化移除上游链接但保留来源审计，Undo/Redo 后正式 `PatternCompiler` 结果可重放。N5 focused + Pattern/Graph/editor 回归 `python -m pytest -q tests/test_preset_descriptor.py tests/test_preset_expansion.py tests/test_preset_migration.py tests/test_preset_library.py tests/test_editor_preset_workspace.py tests/test_pattern_document.py tests/test_pattern_compiler.py tests/test_pattern_parity.py tests/test_pattern_graph.py tests/test_pattern_runtime.py tests/test_lifecycle_batching.py tests/test_lifecycle_events.py tests/test_editor_graph_workspace.py tests/test_editor_authoring_integration.py`（103 passed）。

**整改证据（2026-08-20）**：上面这段 Evidence 关于「槽位可覆盖」的部分此前只在命令层成立——`SetPresetSlotOverrideCommand` 实现完整但全仓零调用者、零测试，作者在编辑器里没有任何入口，等于参数覆盖是真的、插槽覆盖是假的。现在 PatternWorkspace 为每个 slot 渲染 `PresetReactionSlotEditor`（`objectName` 为 `presetSlot_<slot.id>`），启用开关与参数经 `presetSlotRequested` → `_preset_slot_requested` 进入同一 `CommandStack`。`tests/test_editor_preset_workspace.py::test_preset_slot_editor_writes_one_undoable_slot_override` 用真实 `EditorMainWindow` 从控件出发断言 `slot_overrides` 写入、表单重建后回显、两级 Undo 分别回到旧值与无覆盖状态。

### N5.4 精确版本迁移

**Agent 要做**：按精确版本执行参数/插槽迁移，在临时副本生成差异和诊断；失败保留原数据、原版本和定位路径；项目依赖锁定到可重放版本，不使用“最接近版本”静默替代。

**完成条件**：成功迁移 round-trip；失败可恢复、可 Undo，原文档不被部分写入。

**验收文件**：`tests/test_preset_migration.py`、`tests/test_preset_descriptor.py`、`tests/test_pattern_document.py`。

**Evidence（2026-08-13）**：Migration：`PresetMigration`、`PresetDependencyLock` 均为严格 JSON round-trip；迁移只在临时 `PresetInstance` 副本生成稳定 diff，缺源字段/缺链/冲突/循环均给出路径且不改原文档，确认由单个 `ApplyPresetMigrationCommand` 完成并可 Undo/Redo；解析只接受锁定的精确版本，不做 nearby fallback。

**整改证据（2026-08-20）**：`ApplyPresetMigrationCommand` 此前只出现在 `tests/test_editor_preset_workspace.py`，`app.py` 无任何接线——命令确实单条可撤销，但作者在界面上找不到触发它的地方。现在 PatternWorkspace 显示当前版本并只把「有精确迁移路径」的版本填进 `preset_migrate_target`，按钮经 `presetMigrateRequested` → `_preset_migrate_requested` 先 `preview_migration()` 再压入一条命令；预览被拒时走 `preset_migration_unavailable` 诊断而不是崩溃或静默。`tests/test_editor_preset_workspace.py::test_preset_migration_button_only_offers_reachable_versions` 用真实窗口断言候选只含 `2.0.0`、点击后实例版本与重命名后的参数正确、到链尾后控件自行禁用、Undo 回到 `1.0.0`。

## 7. N6：上下文搜索与新手连续流程（不含自然语言）

### N6.0 Contract：Action Catalog 与新手流程

**Agent 要做**：阅读产品愿景第 10、12、13 节和 N5 接口；创建 `tests/test_action_catalog.py`、`tests/test_contextual_search.py`、`tests/test_beginner_workflow.py`、`tests/test_editor_usability.py`；冻结 Descriptor→Catalog schema、输入/输出类型、上下文过滤、稳定排序、创建事务、空状态引导和错误定位。自然语言生成明确不在范围。

**完成条件**：Contract 断言实际候选、类型端口、Command/Undo 和空状态，而不是菜单字符串。

**验收文件**：上述四份 Contract。

**Evidence（2026-08-13）**：Structural/UI：`ActionDescriptor`、`ActionCatalog`、`ActionQuery` 和 `ActionExecutor` 使用正式 Graph 端口表、Scene `NodeTypeRegistry`、Timeline 类型和 N5 Preset Descriptor；重复 ID、未知 command、上下文/类型/父节点过滤、确定性排序、空状态和明确排除自然语言生成均有行为断言。N6 focused（含 N6.0–N6.3 与编辑器回归）`python -m pytest -q tests/test_action_catalog.py tests/test_contextual_search.py tests/test_beginner_workflow.py tests/test_editor_usability.py tests/test_editor_preset_workspace.py tests/test_editor_graph_workspace.py tests/test_editor_timeline_workspace.py tests/test_editor_m3_integration.py tests/test_editor_authoring_integration.py`：76 passed。

### N6.1 上下文感知搜索

**Agent 要做**：在任意作者上下文轻按空格打开搜索；PointSet 拉线只显示接受 PointSet 的 Action；时间线只显示轨道/片段；场景画布只显示可创建对象；Catalog 来自 Descriptor，UI 不写死分支；解决空格搜索与画布平移冲突并用原生 QA 固定交互。

**完成条件**：无效候选不出现，结果可解释且排序稳定；创建和连接都进入文档 CommandStack。

**验收文件**：`tests/test_action_catalog.py`、`tests/test_contextual_search.py`、`tests/test_editor_graph_workspace.py`、`tests/test_editor_timeline_workspace.py`；另附 native visual。

**Evidence（2026-08-13）**：Editor/Native visual：Graph、Timeline、Scene 轻按空格打开同一搜索；按住空格配合鼠标恢复 `ScrollHandDrag`，Graph 输出端口空放携带正式 `port_type`；结果通过已有命令入口创建并可 Undo。`python -u tools/verify_native_editor_n6.py --project . --screenshot C:\Users\m1573\AppData\Local\Temp\pystg-n6-native-editor.png` 在真实 PySide6 Windows 窗口通过：`native_editor_n6_ok scene_candidates=8 graph_nodes=6`；截图人工复核 L2 单一渐进导航、精确绑定控件和原生布局可见。

**整改证据（2026-08-14）**：Graph 端口改为高辨识度 `I/O` 标记并扩大边缘命中区；端口代理接管 press/move/release，拖线时显示临时连线和合法/非法目标反馈，不再误移动节点。`tests/test_editor_graph_workspace.py` 使用真实 viewport 鼠标事件验证抓取、指针跟随、合法目标高亮、完整连线、节点位置不变及重建安全；Windows 原生 PySide6 鼠标验收另行验证删除连线、重新连接和 Undo/Redo。上下文搜索仍由正式端口类型过滤并通过同一 `CommandStack` 创建。本项重新关闭。

### N6.2 道中/关底骨架模板

**Agent 要做**：项目向导生成道中和两阶段 Boss 骨架（State、Timeline、Background、Pattern、音频和预览入口）；模板创建是一个可 Undo 的文档事务；缺资源、条件错误和 runtime error 定位到资源/属性/规则。

**完成条件**：新人无需理解事件队列、内部 ID 或插件注册即可完成首个 Pattern、全灭后续和背景转场。

**验收文件**：`tests/test_beginner_workflow.py`、`tests/test_editor_m3_integration.py`、`tests/test_editor_authoring_integration.py`、`tests/test_editor_timeline_workspace.py`。

**Evidence（2026-08-13）**：Runtime/Authoring：Add 菜单提供道中和两阶段 Boss 骨架；`ApplyStageTemplateCommand` 在同一 `SceneDocument` 中一次创建 State、Pattern、Movement、Audio、正式 Background 和 Reactive 轨道并整体 Undo/Redo。`encounter.cleared` 由 `stage.state.complete` 在下一固定帧请求 State Graph 转移；背景通过受限 `request_background_transition`，不伪装脚本。`tests/test_beginner_workflow.py` 5 passed；正式 `compile_stage → StageRunner`、Pattern 资源、背景动作、错误路径和全灭后续均有断言，N6 focused 76 passed。

**整改证据（2026-08-14）**：中文模式创建的两阶段 Boss 直接保存作者可读的“两阶段 Boss、登场、通常阶段、强化阶段、结束、背景、背景音乐、背景转场、关卡背景音乐”，内部 kind/ID/runtime 枚举仍保持稳定英文；模板标题和 Undo 显示“撤销 创建两阶段 Boss 模板”。时间线按常见习惯支持空白定位播放头、主体拖动、左右边缘修剪、`Ctrl+滚轮` 缩放、`Shift+滚轮` 横移及 Undo/Redo，所有几何修改仍进入 `CommandStack`。原生 gate `python -u tools/verify_native_editor_n6.py --project . --screenshot %TEMP%\pystg-n6-native-zh.png --compact-screenshot %TEMP%\pystg-n6-native-zh-960x640.png` 通过，分别验证中文 1480×920 和带真实模板轨道的 960×640；最小窗口保留两行工具栏和可编辑轨道，无面板堆叠。本项重新关闭。

### N6.3 分层展开与连续编辑

**Agent 要做**：以“选择预设→调整参数→添加动态变化→编辑节点→查看脚本源码”的任务语言提供连续入口、返回和权限提示；内部层级 ID 只用于稳定状态，不作为作者界面术语。所有层级共享同一生命周期、类型、owner 和 debug identity；局部替换不要求推倒重写。

**完成条件**：从调参到局部实现是连续操作；折叠/展开不复制资源、不产生第二套 runtime。

**验收文件**：`tests/test_beginner_workflow.py`、`tests/test_editor_graph_workspace.py`、`tests/test_editor_preset_workspace.py`、`tests/test_editor_usability.py`。

**Evidence（2026-08-13）**：Editor/Runtime：PatternWorkspace 以单一 L0–L4 入口显示 Preset、精确参数、Binding、Behavior Graph 与 Runtime 源码定位；旧 Recipe/Graph 控件只保留兼容对象并从作者 UI 隐藏。L2 binding 和 L3 expand 均走 CommandStack；返回 L2 不折叠、不复制 Graph，资源 ID、正式编译 identity、owner/lifecycle 契约保持同一 Pattern。`tests/test_editor_usability.py`、Preset/Graph 回归及 N6 focused 76 passed；原生 N6 gate 通过。

**整改证据（2026-08-14）**：作者导航现只显示“选择预设→调整参数→添加动态变化→编辑节点→查看脚本源码”，不暴露 L0–L4、Behavior Graph 或 Runtime Source；中文动态设置显示“每轮子弹数 / 固定值”等任务词，内部仍保存 `shape.count / constant`。预设、参数、动态设置、节点和脚本入口共用同一 Pattern 资源、正式 compiler identity 与 Undo/Redo，往返不复制 Graph。N6 focused gate（Action、搜索、新手流程、预设、Graph、时间线、中文、M3 与作者集成）88 passed；原生中文 1480×920/960×640 gate 通过。本项重新关闭。

**整改证据（2026-08-20）**：上面这段整改只覆盖了导航控件，主界面文案仍有残留：`GraphPlaceholder` 硬编码 “This pattern is in Recipe mode. Expand it into the typed behavior graph…” 与按钮 “Expand to Graph”，`src/editor/i18n.py` 又把它逐字译成“配方模式 / 类型化行为图 / 展开为行为图”——被声称消灭的术语由 i18n 字典忠实保存了下来；`fold_button` 也还写着 “Fold back to Recipe”。现在两侧一并改为任务语言（占位页说明「此弹幕目前只由参数描述。以节点方式打开后，即可编辑每一步以及它们之间的连接。」，按钮为 “Edit Nodes” / 「编辑节点」，折返按钮为 “Back to Parameters” / 「返回调整参数」），并删除仅为兼容测试而隐藏保留的 `mode_switch`。根因是缺少端到端文案审查，因此新增 `tests/test_editor_i18n_coverage.py::test_chinese_shell_leaves_no_author_facing_string_untranslated`：遍历真实编辑器控件树，凡 i18n 层声称拥有却译不出的作者可见文案即失败，`test_coverage_walk_actually_sees_the_shell` 反向保证这条遍历确实走到了 shell 而不是空转。


## 8. ER：N7 前的编辑器架构整改

ER 的目标结构、允许依赖、状态所有权和目录职责见 [EDITOR_ARCHITECTURE.md](EDITOR_ARCHITECTURE.md)。每项只能按表中路径工作；路径尚不存在时由对应任务创建，禁止提前创建空目录或无调用者占位实现。

ER 不改变作者文档语义、时间线/行为图产品模型、正式 runtime、Renderer API 或 N7 权限模型。任何必须改变这些契约的发现都应停止并请求维护者决定。

### ER0 文档、边界 Contract 与真实基线

**状态/依赖**：`[x]`；依赖 N6.3。

**允许路径**：`AGENTS.md`、`docs/EDITOR_ARCHITECTURE.md`、本文、`tests/test_editor_architecture_boundaries.py`、现有架构/回归测试、现有 native verifier 的验收步骤。

**禁止路径**：`src/`、`game_content/` 和运行时产品实现。

**Agent 要做（按序）**

1. 核对目标目录、允许/禁止依赖、Agent 所有权和 ER0–ER8 顺序，解决文档冲突。
2. 创建 `tests/test_editor_architecture_boundaries.py`，用 AST/import graph 和运行时 Protocol 断言目标边界：`src.authoring`、`src.compiler`、`src.preview` 与 runtime headless 包不导入 editor/Qt，Panel 不导入领域 Command，图形模块无循环，窗口无 SlotsMixin/裸预览进程/双 registry，临时状态有类型。
3. Contract 必须对当前真实问题形成精确红色基线；不允许只搜索一段固定源码字符串或把当前错误加入永久 allowlist。
4. 在同一 checkout 记录 full suite、compileall、assets、diff-check、正式 preview、1480×920/960×640 native 和固定 Pattern workload。无法运行的证据必须写明环境和 blocker。

**完成条件**：三份文档一致；Contract 对当前已知问题逐项失败且没有额外模糊失败；基线证据可复现。ER0 是 Contract 任务，预期红色断言不阻止进入 ER1，但不得合并一个只含红测试、没有后续整改的 `main`。

**验收文件**：`tests/test_editor_architecture_boundaries.py`、`tests/test_architecture_contracts.py`、`tests/test_editor_regression_contracts.py`、`tools/verify_native_editor_n6.py`。

**Evidence（2026-08-20）**：环境为 Windows 11 `10.0.26200`、Python 3.12.7、PySide6 6.8.1.1、Intel64 Family 6 Model 151；PATH 首位 `python.exe` 是不可用的 WindowsApps shim，因此以下命令固定使用 `C:\Users\m1573\anaconda3\python.exe`。Structural：`$env:QT_QPA_PLATFORM='offscreen'; C:\Users\m1573\anaconda3\python.exe -m pytest -o addopts= -q tests/test_editor_architecture_boundaries.py tests/test_architecture_contracts.py tests/test_editor_regression_contracts.py` 得到 125 passed、8 个预期 Contract 红；红项精确对应 authoring/preview 反向依赖、graph/pattern 循环、八个 `SlotsMixin`、裸 preview `QProcess`、双 registry、无类型临时状态和缺失 `AuthoringDocument` Protocol，既有两份验收文件单独为 106/106 passed。Contract 共 27 项，使用 AST/import graph 与运行时 Protocol，覆盖 `from ... import ...` 别名边、`src.authoring.commands.*` 和未注解 preview `QProcess`，没有固定产品源码字符串、永久错误 allowlist、`skip` 或 `xfail`；独立验证 Agent 只读复验后批准 ER0。Runtime：Contract 写入前同一 product checkout 的 `$env:QT_QPA_PLATFORM='offscreen'; C:\Users\m1573\anaconda3\python.exe -m pytest -q` 为既有 641 passed；当前总收集 668（641 既有 + 27 ER0），正式 preview controller/protocol/process/editor integration 为 21/21 passed；`C:\Users\m1573\anaconda3\python.exe -m compileall -q main.py src game_content tools tests` 通过，`validate_assets.py --format json` 检查 74 JSON、16 sprite configs、745 sprites、142 images，0 error/warning，`git diff --check` 通过。Native visual/runtime：清除 `QT_QPA_PLATFORM` 后，`verify_native_editor_n6.py` 的真实 PySide6 1480×920 与 960×640 门禁通过，截图为 `%TEMP%\pystg-er0-native-1480x920.png` 和 `%TEMP%\pystg-er0-native-960x640.png`，人工复核无面板堆叠且时间线可编辑；`verify_native_editor_n4.py` 通过正式 `compile_stage → StageRunner → runtime feedback` 得到 1 条 Reactive trace，截图为 `%TEMP%\pystg-er0-native-n4-preview.png`。Performance：`profile_n5_presets.py --output %TEMP%\pystg-er0-preset-profile.json` 得到 14 presets、1836 spawned、101 batch writes、0 per-bullet callbacks、53.67 ms（上限 2500 ms）。Usability：not run，按顺序须在 ER8 后执行 N6.4。ER0 自身无 blocker；这组预期红 Contract 必须随 ER1–ER7 整改继续保留，不得作为仅含红测试的提交单独合入 `main`。

### ER1 有类型的编辑状态

**状态/依赖**：`[x]`；依赖 ER0。

**允许路径**：`src/editor/state/`、`src/editor/document_manager.py`、当前读取 `editor_context` 的 `src/editor/app.py` 与 `src/editor/main_window_*.py`、focused tests；native 验收发现旧状态访问后，主协调 Agent 将边界单文件扩展到 `tools/verify_native_editor_n4.py`。

**禁止路径**：作者 schema、compiler、runtime、renderer、Panel 产品行为和 N7。

**Agent 要做（按序）**

1. 定义 `SelectionState`、`TimelineViewState`、`PatternViewState`、`DocumentEditorState` 和 `RuntimeOverlayState`；字段类型、默认值和清理时机必须与架构文档一致。
2. 每个 `ManagedDocument` 只拥有选择/视图状态；运行时 overlay 改由活动预览所有者管理，不进入作者文档。
3. 迁移全部 22 个隐式键；删除目标时校正选择，切换文档时恢复各自状态，stop/reset 只清理 overlay。
4. 保持 Undo/Redo、dirty、canonical JSON、autosave/recovery 和文档切换行为不变。

**硬指标**：生产代码中 `editor_context` 和相关字符串键为零；两个文档的选择/播放头互不污染；overlay 不序列化、不制造 dirty；状态错误在构造或赋值边界明确失败。

**验收文件**：新建 `tests/test_editor_state_contract.py`；回归 `tests/test_editor_document_manager.py`、`tests/test_editor_reactive_clips.py`、`tests/test_preview_editor_integration.py`。

**Evidence（2026-08-20）**：环境为 Windows 11 `10.0.26200`、Python 3.12.7、PySide6 6.8.1.1、Intel64 Family 6 Model 151；命令固定使用 `C:\Users\m1573\anaconda3\python.exe`。Structural：新建冻结 `tests/test_editor_state_contract.py`，逐键确认 18 个文档状态和 4 个 preview overlay 状态；`$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -o addopts= -q tests/test_editor_state_contract.py tests/test_editor_document_manager.py tests/test_editor_reactive_clips.py tests/test_preview_editor_integration.py tests/test_contextual_search.py tests/test_editor_authoring_integration.py tests/test_editor_graph_workspace.py tests/test_editor_m3_integration.py tests/test_editor_timeline_workspace.py tests/test_state_graph_editor.py` 为 103 passed，其中 ER1 Contract 为 25/25；`tests/test_editor_architecture_boundaries.py tests/test_architecture_contracts.py tests/test_editor_regression_contracts.py` 为 126 passed、精确保留 7 个 ER2–ER7 预期红项，ER0 的 typed-state 红项已转绿。Runtime：同一 checkout 全量 `python -m pytest -o addopts= -q` 为 686 passed、仅上述 7 个预期 Contract 红项；正式 preview controller/protocol/process/editor integration 为 21/21 passed。`ManagedDocument` 只拥有一个 `DocumentEditorState`；双文档选择/播放头隔离，删除、Undo/Redo、revert/close 会校正或释放 transient state；不可变 `RuntimeOverlayState` 由 preview owner 按文档持有，stop/reset/error/进程或 owner 关闭只清 overlay，不改变作者播放头、canonical JSON、dirty 或 history。生产 `src/editor` 与 N4 verifier 中 `editor_context` 和 22 个旧字符串键为零，无旧 payload fallback、`skip` 或 `xfail`。`python -m compileall -q main.py src game_content tools tests` 通过；资产检查 74 JSON、16 sprite configs、745 sprites、142 images，0 error/warning；`git diff --check` 通过。Native visual/runtime：真实 PySide6 `verify_native_editor_n6.py` 在 1480×920 与 960×640 通过，截图为 `%TEMP%\pystg-er1-native-1480x920.png`、`%TEMP%\pystg-er1-native-960x640.png`，人工复核无面板堆叠且紧凑时间线可编辑；`verify_native_editor_n4.py` 经单文件 typed-state 迁移后，正式 `compile_stage → StageRunner → statistics event` 得到真实 `runner.frame=1` 和 1 条 Reactive trace，真实双击导航通过，截图 `%TEMP%\pystg-er1-native-n4.png` 中激活片段、Frame 1 和检查器可见。Performance：`profile_n5_presets.py --output %TEMP%\pystg-er1-preset-profile.json` 得到 14 presets、1836 spawned、101 batch writes、0 per-bullet callbacks、51.824 ms（上限 2500 ms）。Usability：not run，依赖链规定在 ER8 后执行 N6.4。独立只读验证 Agent 复验 Contract、native N4、N6 双尺寸、性能及工具修复后批准 ER1；无 blocker。工作树位于 `main` 且未提交，既有 `.claude/settings.local.json`、AGENTS/架构文档与 ER0 Contract 改动均保留；ER1 未修改作者 schema、compiler、runtime、renderer、Panel 产品行为或 N7。

### ER2 Coordinator 与局部失效

**状态/依赖**：`[x]`；依赖 ER1。

**允许路径**：`src/editor/application/`、`src/editor/shell/`、`src/editor/app.py`、`src/editor/main_window_*.py`、`src/editor/state/`、focused tests。

**禁止路径**：作者 schema、compiler/runtime、具体 Panel 绘制和交互实现、N7。

**Agent 要做（按序）**

1. 定义不携带 QWidget 的 `EditorIntent`、公开 Panel Port 和有限 `InvalidationSet`。
2. 引入 `EditorCoordinator` 与 `DocumentController`；由 Coordinator 验证意图、创建/提交 Command、更新临时状态并返回局部失效。
3. 将窗口领域槽迁出八个 `SlotsMixin`；`EditorMainWindow` 只组装 Qt、连接公开接口和关闭顶层服务。
4. 普通 mutation 只刷新受影响的 Panel；完整同步只允许在打开/切换文档和迁移后重新绑定。

**硬指标**：窗口不继承 `SlotsMixin`，不导入领域 Command，不调用 Panel 私有方法；mutation handler 不调用全局 `_refresh()`；一次用户提交只产生一个 Command；Undo/Redo 经过同一协调路径。

**验收文件**：新建 `tests/test_editor_coordinator.py`；回归 `tests/test_editor_app_smoke.py`、`tests/test_editor_authoring_integration.py`、`tests/test_editor_scene_commands.py`、`tests/test_editor_timeline_commands.py`。

**Evidence（2026-08-21）**：环境为 Windows 11 `10.0.26200`、Python 3.12.7、PySide6 6.8.1.1、Intel64 Family 6 Model 151；命令固定使用 `C:\Users\m1573\anaconda3\python.exe`。Contract / Structural：新增冻结 `tests/test_editor_coordinator.py`，用真实 `DocumentManager` / `SceneDocument` 验证无 QWidget 的不可变 typed Intent、显式拒绝、一次提交一个 Command、同一路径 Undo/Redo、有限局部失效和受约束 full sync；`$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -o addopts= -q tests/test_editor_coordinator.py tests/test_editor_app_smoke.py tests/test_editor_authoring_integration.py tests/test_editor_scene_commands.py tests/test_editor_timeline_commands.py` 为 32 passed。窗口改为 `QMainWindow` + 组合式 shell service，不继承八个 `SlotsMixin`、不导入领域 Command、不调用 Panel 私有方法；普通 mutation 无 `_refresh()`，唯一全量刷新只响应 `DocumentController` 的 initial open / document activation / schema migration；Command 提交集中在 `EditorCoordinator._submit()`，Undo/Redo 也经 `dispatch()`。`python -m pytest -o addopts= -q tests/test_editor_architecture_boundaries.py tests/test_architecture_contracts.py tests/test_editor_regression_contracts.py` 为 127 passed、仅保留 6 个 ER3–ER6 预期 Contract 红项（headless authoring/preview 与 `AuthoringDocument` 属 ER3、裸 preview `QProcess` 属 ER4、双 registry 属 ER5、graph/pattern 循环属 ER6），ER2 的 SlotsMixin 边界已转绿。Runtime：N2/N3 命令 `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -o addopts= -q tests/test_typed_variables.py tests/test_variable_runtime.py tests/test_variable_scopes_and_reducers.py tests/test_variable_seek.py tests/test_variable_hotreload.py tests/test_lifecycle_events.py tests/test_frame_boundary_events.py tests/test_lifecycle_batching.py tests/test_reactions.py tests/test_reaction_scheduler.py tests/test_lifecycle_timeline_hooks.py tests/test_background_reactions.py` 为 43 passed；全量 `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -o addopts= -q --tb=short` 为 699 passed、仅同一组 6 个后续 ER 预期 Contract failure，无 ER2 或既有产品回归。`python -m compileall -q main.py src game_content tools tests` 通过；`python tools/validate_assets.py --format json` 检查 74 JSON、16 sprite configs、745 sprites、142 images，0 error/warning；`git diff --check`、`git diff --cached --check` 通过；没有 `skip` / `xfail`，没有修改或删除既有测试。Native visual/runtime：清除 `QT_QPA_PLATFORM` 后，`python tools/verify_native_editor_n6.py --screenshot %TEMP%/pystg-er2-final-6081a3b96ec946e8be8730aa3aa86c10/native-1480x920.png --compact-screenshot %TEMP%/pystg-er2-final-6081a3b96ec946e8be8730aa3aa86c10/native-960x640.png` 真实双尺寸通过，独立验证 Agent 人工复核无面板堆叠、紧凑时间线可编辑且中文渐进导航无实现术语；`python tools/verify_native_editor_n4.py --screenshot %TEMP%/pystg-er2-final-6081a3b96ec946e8be8730aa3aa86c10/native-n4.png` 经正式 `compile_stage → StageRunner → runtime feedback` 得到 1 条 Reactive trace。Performance：`python tools/profile_n5_presets.py --output %TEMP%/pystg-er2-final-6081a3b96ec946e8be8730aa3aa86c10/n5-profile.json` 得到 14 presets、1836 spawned、101 batch writes、0 per-bullet callbacks、41.406 ms（上限 2500 ms）。Usability：not run，按依赖顺序在 ER8 后执行 N6.4。独立只读验证 Agent 复验以上全部类别后给出 APPROVE，无 ER2 blocker；实现 checkpoint `cb8f35b`，完成 commit `72a0b00`，无关 `.claude/settings.local.json` 保持未提交且未改动。

### ER3 Authoring、Command 与 Compiler 包边界

**状态/依赖**：`[x]`；依赖 ER2（已完成）。

**允许路径**：`src/authoring/`、新建 `src/compiler/`、现有无 Qt 的 `src/editor/document.py`、`commands.py`、`*_commands.py`、`stage_compile.py`、`scene_compile.py` 及其兼容出口、`src/preview/` 的 import 适配、focused tests。

**禁止路径**：Qt Shell/Panel 行为、runtime 语义、renderer 和 N7。

**Agent 要做（按序）**

1. 定义 `AuthoringDocument` Protocol 和明确的 Scene/Pattern/UI/Background 支持类型。
2. 将 Scene 作者数据移到 `src/authoring/scene/`，领域 Command 移到 `src/authoring/commands/`。
3. 将 Stage/Spell compiler 和诊断移到 `src/compiler/`，提供与现有正式运行路径一致的 facade。
4. 旧 `src/editor/*` 路径先变为无逻辑 re-export；逐个迁移内部调用者，不复制实现。
5. 将 headless 资源 registry 与 Qt editor factory 解耦；Qt contribution 留给 ER5。

**硬指标**：`src.authoring`、`src.compiler`、`src.preview` 不导入 `src.editor` 或 Qt；Command 无 Qt；四类文档都能在无 Qt 环境加载/验证；迁移前后 canonical JSON、编译结果和 runtime identity 一致。

**验收文件**：`tests/test_editor_architecture_boundaries.py`、`tests/test_editor_documents.py`、`tests/test_editor_scene_compile.py`、`tests/test_editor_document_manager.py`、`tests/test_preview_controller.py`。

**Evidence / Blocker（已完成 `[x]`，独立验证 APPROVE）**：

- 环境：`C:\Users\m1573\anaconda3\python.exe`（Python 3.12.7），PySide6 6.8.1.1 offscreen（`QT_QPA_PLATFORM=offscreen`），`pytest -o addopts= -p no:cacheprovider`，Windows 11 10.0.26200。
- **Structural（迁移基线→迁移后）**：迁移前 `pytest tests/test_editor_architecture_boundaries.py tests/test_editor_documents.py tests/test_editor_scene_compile.py tests/test_editor_document_manager.py tests/test_preview_controller.py` → 6 failed, 41 passed；迁移后 → 45 passed, 3 failed。ER3 转绿的 3 项已绿：`test_headless_packages_do_not_import_editor_or_qt[authoring]`、`[preview]`、`test_managed_document_uses_runtime_authoring_document_protocol`。独立验证以 AST 遍历全部 31 个 `.py`（含函数内导入）确认 `src.authoring`/`src.compiler`/`src.preview` 对 `src.editor` 与 `PySide6/PyQt5/PyQt6/shiboken6` 的导入为 **0**；`registry.py:152` 的 `src.editor` 仅为错误信息字符串字面量，非导入节点。`test_headless_packages_do_not_import_editor_or_qt` 全部 10 个参数化通过。
- **Runtime（四类文档 Qt-free）**：独立验证在无 Qt、无 `src.editor` 的进程内构造并 `.validate()` Scene/Pattern/UI/Background 四类文档，`isinstance(_, AuthoringDocument)` 均为 True，`sys.modules` 中 Qt 与 `src.editor` 均为空；Background 先以非 UUID id 触发校验失败，确认 validate 为真实校验。`AuthoringDocument` 确认为 `typing.Protocol` + `@runtime_checkable`，固定 `id/type/schema_version/to_dict/from_dict(classmethod)/validate`。
- **Identity（迁移前后一致）**：独立验证对 15 个迁移模块逐一 diff HEAD 原文，均为**纯 import-path 改动**（3 个字节相同：`commands/base.py`、`scene/document.py`、`scene/node_types.py`；其余仅改相对导入指向新位置），无任何逻辑行变更；identity 敏感 runtime 测试 `test_stage_program`、`test_editor_scene_compile`、`test_replay_determinism`、`test_variable_runtime`、`test_state_graph_runtime` → 28 passed, 0 failed。
- **Scope 纪律**：`git diff -M HEAD -- tests/` 为空，测试零改动/零 skip/xfail；15 个旧路径 shim 均为无逻辑（8 行：docstring + 单行 `from <new_location> import *  # noqa: F401,F403`），git 记录为 rename + 新 shim。
- **editor_factory 决策**：`build_default_resource_type_registry()` 不再导入 Qt；UI/Background 的 `editor_factory` 经 authoring 侧无 Qt 贡献钩子 `register_editor_factory`，由 `src.editor` 导入时按 type ID 注册（§6/§8 贡献反转，方向 editor→authoring 合法，Qt import 惰性；ER5 将其收拢进 EditorPluginRegistry facade）。`test_ui_and_background_registry_entries_are_full_runtime_contributions` 保持绿，未削弱。
- **迁移映射**：`document.py`→`src/authoring/scene/document.py`、`node_types.py`→`src/authoring/scene/node_types.py`、`commands.py`→`commands/base.py`、`*_commands.py`→`src/authoring/commands/{scene,pattern,timeline,graph,ui,background,variables,state_graph,preset}.py`、`pattern_resolve.py`/`stage_compile.py`/`scene_compile.py`→`src/compiler/{pattern_resolve,stage,scene_spell}.py`；旧 `src/editor/*` 路径全部为无逻辑 re-export shim。
- **全量套件**：3 failed, 703 passed（对比 ER2 基线 699 passed + 6 预期 Contract failure：ER3 转绿 3 项 + `[compiler]` 边界参数就位，零回归）。剩余 3 红为 ER4/ER5/ER6 前向标记：`test_editor_main_window_does_not_own_raw_preview_qprocess`、`test_editor_main_window_has_one_plugin_registry_facade`、`test_editor_graph_modules_have_no_import_cycles`。
- **未跑（非 ER3 验收类别）**：Native visual/Interaction 对 ER3 为 N/A（headless 重构，无 Qt UI 行为变更）；Performance/Usability 未跑，按流程延至 ER8/N6.4。
- **独立验证**：由未参与 ER3 实现的只读 Agent（Read/Grep/pytest/git/python 一次性脚本，未改任何产品代码或测试）执行，四项硬指标全部 CONFIRMED，Verdict = APPROVE。

### ER4 唯一 PreviewSession

**状态/依赖**：`[x]`；依赖 ER3。

**允许路径**：`src/editor/preview/`、`src/preview/`、当前 `src/editor/preview_process.py`、`runtime_preview.py`、预览相关 shell 接线与 focused tests。

**禁止路径**：作者 schema、时间线/行为图实现、renderer 语义、插件和 N7。

**Agent 要做（按序）**

1. 建立唯一 `PreviewSession`，明确 `formal_authoring` 与 `legacy_game_run` 模式和共同状态机。
2. 收拢进程、协议、宿主、活动文档 identity、启动/停止/错误/超时/输出上限和关闭。
3. 窗口不再持有裸预览 `QProcess`；`RuntimePreviewHost` 只嵌入，不拥有进程。
4. 外部编辑工具进程保持独立，不伪装成游戏预览。

**硬指标**：同一时间只有一个活动预览；反馈不会路由到错误文档；stop/reset/crash/close 清理进程和 overlay；legacy 结果不标为 formal；正式 Pattern/Stage 仍经 JSON 协议和正式 runtime。

**Evidence / Blocker（已完成 `[x]`，独立验证 APPROVE）**：

- **Structural**：AST 门禁 `test_editor_main_window_does_not_own_raw_preview_qprocess` 单独运行 1 passed；`self._preview_process` 从 `src/editor` 全删（grep `_preview_process\b` 零命中）；裸 legacy `QProcess` 移入 *composed* `PreviewSession`（`src/editor/preview/session.py:166`），窗口经 `self._preview_session = PreviewSession(project, parent=self)`（`app.py:153`）持有，`_window_owner_classes()` 只扫窗口基类层级，故 composed 成员合法不越界；`_pattern_preview_client` 改为委托 `self._preview_session.formal_client` 的 property（`app.py:202-214`），`main_window_preview.py` 删除 `QProcess` 导入。
- **Runtime**：`C:\Users\m1573\anaconda3\python.exe -m pytest -q -o addopts= -p no:cacheprovider tests/test_preview_session.py`（10 passed）；`tests/test_preview_process.py tests/test_preview_protocol.py tests/test_preview_editor_integration.py`（14 passed）；ER4 五文件套件 50 passed / 2 failed，2 红为 ER5/ER6 前向门禁（`test_editor_main_window_has_one_plugin_registry_facade`、`test_editor_graph_modules_have_no_import_cycles`），零回归。正式 Pattern/Stage 仍走 `PatternPreviewProcess`+NDJSON（`preview_process.py` 未改）；legacy 无 authoring identity，`[preview]` 与 `[pattern-preview]` 通道分离，非零退出经 `legacyFinished` 上抛不吞。
- **Native visual**：preview native gate **not run**（headless、`QT_QPA_PLATFORM=offscreen` 环境无法截屏渲染）。
- **Performance / Usability**：**not run**，按依赖顺序延至 ER8/N6.4。
- **环境**：commit `8f85557`（对比 ER3 基线 `4a07614`）；工作树干净（仅 `.claude/settings.local.json` 本地设置改动，非产品代码）；Python 3.12.7 (anaconda3)、PySide6 6.8.1.1、Windows 11 10.0.26200、`QT_QPA_PLATFORM=offscreen`。
- **独立验证**：由未参与 ER4 实现的只读 Agent 执行（Read/Grep/pytest/git，未改任何产品代码或测试），8 项硬指标逐条 CONFIRMED——唯一预览进程所有权、formal↔legacy 互斥、legacy 无 identity、stop/close/自然退出/crash 清理、legacy 结果不标 formal、formal 仍走 JSON 协议+正式 runtime、`RuntimePreviewHost` 仅嵌入不拥有进程、外部编辑工具进程独立于预览。Verdict = **APPROVE**（备注：提交信息写 "11 cases" 实际 10，仅措辞误差，覆盖无缺）。

### ER5 唯一插件贡献入口

**状态/依赖**：`[x]`；依赖 ER4（已完成）。

**允许路径**：`src/editor/plugins/`、当前 `src/editor/plugin_sdk.py`、`workbench.py`、headless registry 的 Tool 适配点、focused tests。

**禁止路径**：窗口私有状态、runtime 内部、作者 schema、Panel 产品行为和 N7。

**Agent 要做（按序）**

1. 窗口只依赖一个 `EditorPluginRegistry` facade。
2. 用适配器接入 headless SDK contribution 和 Qt workbench/external tool contribution。
3. 统一插件 identity、依赖、激活状态、失败回滚、停用和清理；禁止两个互不知情的生命周期。
4. 插件上下文不能取得窗口、内部 registry 或全局 runtime 对象。

**硬指标**：窗口不再同时持有 `plugin_registry` 与 `plugin_sdk_registry`；部分激活失败完整回滚；停用撤销所有 owned contribution；外部工具关闭不影响 formal preview。

**验收文件**：新建或收敛 `tests/test_editor_plugin_registry.py`；回归 `tests/test_plugin_sdk.py`、`tests/test_editor_workbench.py`、`tests/test_editor_regression_contracts.py`。

**Evidence / Blocker（已完成 `[x]`，独立验证 APPROVE）**：

- 环境：`C:\Users\m1573\anaconda3\python.exe`（Python 3.12.7），PySide6 6.8.1.1 offscreen（`QT_QPA_PLATFORM=offscreen`），`pytest -o addopts= -p no:cacheprovider`，Windows 11 10.0.26200。实现提交 `0dc90ac`，基线 `16aa27f`；工作树除启动时既有的 `.claude/settings.local.json` 外干净。
- **Structural（gate 红→绿）**：ER5 gate `test_editor_main_window_has_one_plugin_registry_facade` 在基线 `16aa27f` 为红（`assert 2 == 1`：`self.plugin_registry`@app.py:187 + `self.plugin_sdk_registry`@app.py:124 两个 registry 属性），独立验证在隔离 worktree 亲自复现该红。实现后转绿：窗口仅一个 `self.plugin_registry = EditorPluginRegistry(...)`（Call），`self.plugin_sdk_registry = self.plugin_registry.sdk` 为属性访问（`ast.Attribute`，非 Call，不计入）。facade（`src/editor/plugins/registry.py`）**组合**（非继承，仅继承 `object`）`workbench.PluginRegistry`（视图目录）+ `plugin_sdk.PluginRegistry`（SDK）；两个底层类均保持完整供其直测套件 import。closeEvent 经 `self.plugin_registry.shutdown()`（→ 同一 SDK 对象 `deactivate_all()`）统一停机。
- **Runtime（gate + 契约 + 回归）**：
  - ER5 gate + 新契约 `tests/test_editor_plugin_registry.py` → **8 passed**（1 gate + 7 契约）。
  - spec 回归 `test_plugin_sdk.py`、`test_editor_workbench.py`、`test_editor_regression_contracts.py`、`test_editor_resource_browser.py`、`test_editor_authoring_integration.py` → **123 passed, 0 failed**。
  - 完整架构边界套件 `test_editor_architecture_boundaries.py` → **27 passed, 1 failed**；唯一红为 `test_editor_graph_modules_have_no_import_cycles`（ER6 前向 gate，基线同样为红，非 ER5 回归）。
  - 实现者宽回归：`test_preview_session.py`、`test_preview_editor_integration.py`、`test_editor_app_smoke.py`、`test_editor_hardening.py`、`test_devtools_spell_preview.py` → **35 passed**；`test_editor_m3/m4/m5/m6_integration.py`、`test_editor_m6_workspace.py`、`test_editor_usability.py` → **31 passed**。
- **四条硬指标（各由通过的契约用例佐证）**：
  1. 窗口不再同时独立持有两个 registry —— `test_window_holds_exactly_one_plugin_registry_facade`：`window.plugin_sdk_registry is window.plugin_registry.sdk`（同一对象）、`vars(window)` 无 `WorkbenchPluginRegistry` 类型、registry id 集合 `== {id(facade), id(sdk)}`（无第三 registry）。
  2. 部分激活失败完整回滚 + 隔离 —— `test_partial_sdk_activation_failure_rolls_back_and_isolates`：健康插件 `state=="active"` 且命令可用；broken `state=="failed"`，其崩溃前登记的 `broken.cmd` 被撤销（`pytest.raises(KeyError)`），`errors` 仅记 `["broken"]`。
  3. 停用撤销所有 owned contribution —— `test_shutdown_undoes_owned_sdk_contributions`：`cleaned==[True]`（on_deactivate 跑）、`state=="inactive"`、`command` 抛 KeyError。
  4. 外部工具关闭不影响 formal preview —— `test_external_tool_teardown_does_not_stop_formal_preview`：`_tool_finished` 后工具移除、`_preview_session.is_formal_running` 仍 True、formal client 仍 running。
  附加：`test_facade_owns_one_sdk_component_sharing_the_document_registries` 以 `is` 断言 SDK 组件与 DocumentManager 共享同一 resource/node registry；`test_plugin_context_cannot_reach_window_or_core_registries` 精确锁定 context 公开面（不含 window/registry/resource_types/node_types/runtime/sdk）。
- **Native visual / Interaction**：对 ER5 为 N/A（headless facade 收拢，无 Qt UI 行为变更；外部工具与正式预览的隔离已由 `test_external_tool_teardown_does_not_stop_formal_preview` 在真实 `EditorMainWindow` 上运行时验证）。headless 环境下 **not run**。
- **Performance / Usability**：**not run**，按依赖顺序延至 ER8/N6.4。
- **允许路径扩展说明**：ER5 允许路径列出 `src/editor/plugins/`、`plugin_sdk.py`、`workbench.py`、focused tests，但硬指标定义在窗口上，故按 ER4 先例将窗口插件接线（`app.py` 的 `__init__`/`closeEvent`）纳入本任务范围；未触碰窗口其他私有状态、runtime、作者 schema、Panel 产品行为或 N7。
- **独立验证**：由未参与 ER5 实现的只读 Agent（Read/Grep/pytest/git/隔离 worktree，未改任何产品代码或测试）执行；在基线隔离 worktree 复现 gate 红（`assert 2 == 1`）证明真实红→绿翻转；判定 gate 非规避（静态 AST gate 与运行时 `is`/`vars(window)` id 集合测试合力封死规避空间，契约断言未弱化、跑真实对象）；四条硬指标全部 CONFIRMED，Verdict = APPROVE。

### ER6 Panel 边界与图形循环

**状态/依赖**：`[x]`；依赖 ER5（已完成）。

**允许路径**：`src/editor/panels/`、`src/editor/graphics/`、待迁移的当前 workspace/view/panel 文件、公开 Intent/Port 接线、focused tests。

**禁止路径**：Coordinator 内部、作者 schema、compiler/runtime、preview/plugin 生命周期和 N7；接口不够时必须停止并交回 ER2 所有者修订。

**子任务与独立所有者**

- ER6.0：抽出共享 canvas/graph 图元，消除 `graph_workspace ↔ pattern_workspace` 循环。
- ER6.1：迁移 Scene 与 Inspector。
- ER6.2：迁移 Timeline、State Graph 与 Variables。
- ER6.3：迁移 Pattern 与 Behavior Graph。
- ER6.4：迁移 UI 与 Background。

每个子任务只能由一个 Panel Agent 修改其列出的 Panel；上一个 focused gate 通过后才能领取下一个。

**硬指标**：Panel 之间无具体实现导入和私有调用；Panel 不直接修改文档或 push Command；释放鼠标只提交一次 Intent；图连线、节点拖动、时间线移动/修剪和 UI gizmo 均可 Undo/Redo。

**验收文件**：新建 `tests/test_editor_panel_boundaries.py`；回归 `tests/test_editor_graph_workspace.py`、`tests/test_editor_timeline_workspace.py`、`tests/test_editor_preset_workspace.py`、`tests/test_editor_m6_workspace.py`、`tests/test_editor_m6_integration.py` 及真实鼠标 native gate。

**Evidence / Blocker（已完成 `[x]`，独立验证 APPROVE）**：

- **环境**：`C:\Users\m1573\anaconda3\python.exe`（Python 3.12.7），PySide6 6.8.1.1，Windows 11 10.0.26200；Qt 测试设 `QT_QPA_PLATFORM=offscreen`，pytest flags `-o addopts= -p no:cacheprovider`。实现 checkpoint `3e8faaf → fbc7c44`，门禁 commit `f400b9e`；基线 ER5 docs `b47ffa1`。工作树除启动时既有的 `.claude/settings.local.json` 外干净。
- **子任务（各由独立 Panel Agent 完成，逐 gate 领取）**：ER6.0 `3e8faaf`（抽出共享 `PatternCanvas` 至 `src/editor/graphics/pattern_canvas.py`）+ `68b0fc3`（下沉 graph 图元至 `src/editor/graphics/graph_canvas.py`，消除 `graph_workspace ↔ pattern_workspace` 循环）；ER6.1 `b3adc9f`（迁 Scene + Inspector）；ER6.2 `ae6e917`（迁 Timeline / State Graph / Variables / Variable-mapping）；ER6.3 `41c30c7`（迁 Pattern + Behavior Graph）；ER6.4 `fbc7c44`（迁 UI + Background 至 `src/editor/panels/`）。
- **Structural（硬指标#1：Panel 间无具体实现导入/私有调用）**：新建 `tests/test_editor_panel_boundaries.py`，含 AST-only 结构门 + 运行时行为门（结构辅助函数不 import 产品代码，Qt/产品 import 均为函数内局部，故 AST 测试在无 Qt 环境仍可跑）。结构门 `_import_references` 以自研 `ast.walk` 解析器遍历 `src/editor/panels/**.py`，解析 `from X import Y` 两侧模块名，函数内 import 与相对 import（`.x`/`..x`）与顶层绝对 import 同等归一，`test_panels_do_not_import_sibling_panels` 断言**零** panel→panel 边（双向）。分类器守卫 `test_panel_classifier_finds_the_known_panels` 断言真实见到 `panels.pattern_workspace`/`panels.scene_view`/`panels.inspector_panel`（非空集）。独立验证以合成 sibling import 反证结构门对 `from ..panels.timeline_workspace import ...` 与 `from . import inspector_panel` 两种形式均真红（非空洞）。循环已消除：`src/editor/graph_workspace.py` 降为仅导 `.graphics.graph_canvas` 的 re-export shim，`panels/pattern_workspace.py` 导 `..graphics.graph_canvas` 与 `..graphics.pattern_canvas`、不导任何 sibling。跑 `test_editor_panel_boundaries.py` + `test_editor_architecture_boundaries.py` → **31 passed**（含 `test_editor_graph_modules_have_no_import_cycles` 由红转绿）。
- **Runtime（硬指标#2/#3：Panel 不直接改文档/push Command，释放鼠标只提交一次可 Undo Intent）**：行为门 `test_timeline_clip_drag_commits_exactly_one_undoable_intent_on_release` spy 真实 `EditorCoordinator.dispatch` 单一 chokepoint，对 live `view.viewport()` 打真实 `QTest.mousePress` / `QApplication.sendEvent(QMouseEvent.MouseMove)` / `QTest.mouseRelease`（非直调 slot），断言：press 后与 mid-drag 后 `dispatched == []`（panel 仅持瞬态 pose，拖拽期间不触文档）；释放后 `len == 1` 且 `isinstance(TimelineIntent)`、`action == MOVE_CLIP`；文档 `start_frame` 60→90、`undo()`→60、`redo()`→90。无第二预览路径、无下游 slot 捷径。
- **硬指标#4（图连线 / 节点拖动 / 时间线移动/修剪 / UI gizmo 均可 Undo/Redo）**：由既有回归覆盖——图连线 `test_add_edge_rejects_type_mismatch_and_undo_removes` + `test_real_mouse_port_drag_tracks_pointer_and_connects`；节点拖动 `test_set_node_position_command_coalesces` + `test_window_graph_edits_are_undoable_and_survive_reopen`；时间线移动/修剪 `test_clip_supports_real_mouse_move_and_both_edge_trims` + `test_graphics_timeline_add_duplicate_delete_and_undo` + 上述新 window 门；UI/背景 gizmo `test_ui_node_edits_undo_redo_through_the_window`、`test_ui_canvas_resize_is_a_geometry_commit`、`test_background_transform_command_undo_redo_preserves_all_components`。独立验证跑 §579 完整集（`panel_boundaries` + `architecture_boundaries` + `graph_workspace` + `timeline_workspace` + `preset_workspace` + `m6_workspace` + `m6_integration` + `authoring_integration`）→ **90 passed in 70.63s**；主协调 Agent 另跑含 `m3_integration`/`reactive_clips` 的更大回归集 → **101 passed in 136.80s**（exit 0）。
  - **诚实 caveat**：时间线 **trim** 的端到端 Undo/Redo 未单独断言（仅断言其几何请求），但与 move 共享同一 `clipGeometryRequested → MoveResizeClipCommand` 可逆路径（move 已端到端证明可逆）；独立验证判为非-blocker。
- **Identity / Scope**：`graphics/graph_canvas.py`、`graphics/pattern_canvas.py` 为逐字节抽取（唯一差异为新增 module docstring）；重命名的 panel（`inspector_panel`/`timeline_workspace`/`scene_view`/`variable_workspace`/`state_graph_workspace`）仅相对 import rebase（`.x`→`..x`）+ inspector 下沉重指 `from ..graphics.graph_canvas import GRAPH_NODE_PROPERTY_SPECS`；`ui_workspace.py`/`variable_mapping_workspace.py` 为纯 git rename（0 内容改动）。主协调 Agent 亲自核对：迁移全程 `b47ffa1..fbc7c44` 仅触 `src/editor/{__init__,app,graph_workspace,graphics,main_window_authoring/documents/pattern/preview,panels}` + `tests/` + `tools/`；全程 `b47ffa1..f400b9e` 对 `src/{authoring,compiler,render,game}/` **零触及**（`git diff --name-only ... | grep '^src/(authoring|compiler|render|game)/'` 空）——**未改** 作者 schema、compiler/runtime、renderer API、N7 权限模型。门禁 commit `f400b9e` 仅 `tests/test_editor_panel_boundaries.py` + `tools/verify_native_editor_er6.py`（2 文件）。
- **Native visual / Interaction（真实屏幕）**：`tools/verify_native_editor_er6.py`（真实鼠标 native gate）。**真实屏幕运行**（`QT_QPA_PLATFORM` 未设、`SESSIONNAME=Console`）：同环境探针返回 `platformName = windows`、`window visible on-screen = True`、`windowHandle set = True`（加载真实 Win32 `qwindows` 平台插件，非 offscreen/minimal，stderr 无 fallback/error）；gate 打印 `native_editor_er6_ok clip=3997804b-f64b-4448-8c5e-e41f461b5c35 action=MOVE_CLIP intents=1 start=60->90 screenshot=C:\Users\m1573\AppData\Local\Temp\pystg-er6-native-drag.png`，`EXIT_CODE=0`。截图 **63,532 字节（非空）**，验证者开图确认：底部 Timeline 面板 `Body / Pattern` 轨的紫色 "Ring" clip 右移离原点（约 1.5 s = 60fps 下 frame 90），Inspector 读数 **Start [frame] = 90**（Duration 120，channel `main`，payload `{"pattern":"ring"}`），工具栏 Undo 按钮标签 **"Undo Move/resize timeline clip"**（栈上唯一命令即手势产生的 MOVE_CLIP）。offscreen 复跑亦得 `native_editor_er6_ok … action=MOVE_CLIP intents=1 start=60->90`（exit 0）。该真实屏幕运行取代早前"on-screen not run"caveat，与 ER0–ER2 的 N4/N6 native gate 同一标准。
- **Performance / Usability**：**not run**，按依赖顺序延至 ER8/N6.4。
- **无循环规避**：全部 ER6 验收测试与 native gate 无 `skip`/`xfail`/`pytest.mark` 屏蔽、无吞异常；行为门无法伪造（任何旁路会使 Intent 计数 ≠ 1 而失败），结构门经实证对真实 sibling import 真红。
- **独立验证**：由未参与 ER6 实现的只读 Agent（Read/Grep/pytest/git/自研 AST 脚本，未改任何产品代码或测试）执行；四条硬指标全部 CONFIRMED——迁移为纯 import-path 重定位（逐字节抽取 + 相对 import rebase + 纯 rename + shim），无 panel↔panel 边，行为门 bypass-proof，结构门经反证非空洞；`git show --stat f400b9e` 仅触 tests/tools。Verdict = **APPROVE**。

### ER7 兼容层、schema 与重复生命周期清理

**状态/依赖**：`[x]`；依赖 ER6。

**允许路径**：`src/authoring/`、`src/compiler/`、旧 `src/editor/` 兼容出口、`src/editor/session.py`、`document_manager.py`、schema/migration 和 focused tests。

**禁止路径**：新增产品能力、runtime/renderer 语义、Panel 重新设计和 N7。

**Agent 要做（按序）**

1. 将 `CURRENT_SCHEMA_VERSION` 恢复为普通整数 4；v3 只通过显式 v3→v4 migration 读取。
2. 收敛 `SceneEditorSession`：内部调用者归零后降为兼容工厂或删除，不再保留第二套 open/save/Undo 生命周期。
3. 核对所有旧 re-export 的内部调用者；只删除引用为零且有明确替代路径的出口。
4. 清理 Mixin、重复逻辑和迁移期 allowlist；不删除仍有外部兼容责任的公共入口。

**硬指标**：版本 4 不与 3 相等；旧文档显式迁移且 round-trip；仓库内部不依赖旧 editor 文档/compiler/command 路径；一个文档只有一个生命周期和 CommandStack。

**验收文件**：新建 `tests/test_editor_schema_migration.py`；回归 `tests/test_scene_v4_contract.py`、`tests/test_editor_documents.py`、`tests/test_editor_document_manager.py`、`tests/test_editor_regression_contracts.py`。

**Evidence**（独立验收 Agent，未参与 ER7 实现，产品代码全程只读）：

- **环境**：`C:\Users\m1573\anaconda3\python.exe`（Python 3.12），Qt 测试设 `QT_QPA_PLATFORM=offscreen`，pytest flags `-o addopts= -p no:cacheprovider`；分支 `codex/er2-coordinator-wip`，HEAD `1df2eed`；ER7 实现提交 `98aac38 → cca111d → 6872988 → 1df2eed`，验证基线 ER6 docs `99b15c0`。工作树除会话启动时既有的 `.claude/settings.local.json` 外干净（自研 AST 探针即用即删、无残留、未改任何 tracked 文件）。
- **门禁（全部亲自跑）**：全量套件 `728 passed in 554.59s (0:09:14)`（exit 0，全程无 fail/error/skip/xfail）；ER7 焦点集（`test_editor_schema_migration` + `test_scene_v4_contract` + `test_editor_documents` + `test_editor_document_manager` + `test_editor_regression_contracts`）`118 passed`；边界集（`test_editor_architecture_boundaries` + `test_editor_panel_boundaries`）`29 passed`；`python -m compileall -q src` 干净 exit 0。
- **Schema（硬指标#1：版本 4 ≠ 3、纯 int）**：`git diff 99b15c0..HEAD -- src/authoring/scene/document.py` 显示 `_LegacyCompatibleSchemaVersion(int)` 包装类（其 `__eq__` 曾使 `4==3` 成立）**已整体删除**，`CURRENT_SCHEMA_VERSION = SCENE_RESOURCE_SCHEMA_VERSION`、`self.schema_version = int(schema_version)`。独立断言：`type(CURRENT_SCHEMA_VERSION) is int`、`==4`、`!=3`、`==3` 现为 **False**（毒化等价消除），`SCENE_RESOURCE_SCHEMA_VERSION==4`（int）。`git show 99b15c0:…document.py` 确认包装类曾存在、HEAD 已无。CONFIRMED。
- **Schema（硬指标#2：显式迁移 + round-trip）**：`migrate_document`（document.py:1495）薄封装 `build_default_migration_registry().migrate(data, expected_type=SCENE_DOCUMENT_TYPE)`（`MigrationError`→`DocumentError`），非恒等透传；`MigrationRegistry.migrate` 逐版本 `while version<target` 走查、每步校验 +1 与类型不变、缺步 `MigrationError`、`version>target` 拒未来版本；`build_default_migration_registry` 显式注册 `migrate_scene_v3_to_v4`。独立跑 `docs/schemas/fixtures/scene-v3.pystg.json`（1840B，schema_version=3）：`migrate_document` 得 v4，且仅 `migrate_scene_v3_to_v4` 写入的标记 `_legacy_v3_source=True` / `variable_compatibility=legacy_last_wins` 出现（证明迁移体真跑而非恒等），源 dict 不变（纯函数）；`SceneDocument.from_dict(…,canonical=True).to_canonical_dict()` 再 `from_dict` 为**固定点**（round-trip 稳定于 v4）。CONFIRMED。
- **Boundary/Identity（硬指标#3：内部零依赖旧 editor 文档/compiler/command 路径）**：`git show 6872988 --stat` 列出 **15** 个 `src/editor/*.py` shim 删除，与规格 15 名逐一吻合（commands, document, node_types, scene_commands, pattern_commands, preset_commands, timeline_commands, ui_commands, variable_commands, background_commands, graph_commands, state_graph_commands, scene_compile, stage_compile, pattern_resolve）；`git diff --diff-filter=A 99b15c0..HEAD` 仅新增 `tests/test_editor_schema_migration.py`。全仓 grep（绝对 `from/import src.editor.<shim>`、相对 `from .<shim>` / `..<shim>`、`from . import <shim>`、`importlib.import_module("src.editor.<shim>")`）对 15 shim **零引用**——唯二绝对命中在 `test_editor_architecture_boundaries.py:157/194` 为**注释**；相对命中全部落在其它包真实模块（`src.authoring.scene.document` / `src.compiler.pattern_resolve` / `src.pattern.document`），`src/editor/` 内零 shim 引用；已甄别 `src.editor.document_manager`（真实模块，非 shim）不误判。被删 shim 在 `99b15c0` 均为纯 `from <canonical> import *`（如 `scene_commands`→`src.authoring.commands.scene`、`pattern_resolve`→`src.compiler.pattern_resolve`），故内部调用者从 shim 重指 canonical 为**零语义变更**。`src/editor/__init__.py` 保留全部公共导出名（`Command`/`CommandStack`/`SceneEditorSession`/各命令类/`CURRENT_SCHEMA_VERSION`…），仅将 re-export 来源改指 canonical——**包级公共入口保留**（外部兼容责任），子模块 shim 删除。CONFIRMED。
- **Lifecycle（硬指标#4：一个文档一个生命周期一个 CommandStack）**：`src/editor/session.py` 的 `SceneEditorSession` 已降为**仅** `new_document` 静态工厂——open/save/apply/undo/redo/replace 实例生命周期全删（docstring 明示已并入 `ManagedDocument`、实例化 “intentionally unsupported”）；`ManagedDocument` 为 dataclass，恰持一个 `commands: CommandStack`（`apply/undo/redo/save/revert/release_editor_state` 全经此单栈）；`DocumentManager` 维护 `list[ManagedDocument]`、每文档独立。焦点回归 `test_manager_owns_independent_documents_savepoints_and_state` 与新 `test_opening_a_v3_scene_yields_one_v4_lifecycle_with_one_command_stack`（断言 open v3→v4、`len(manager)==1`、`isinstance(commands, CommandStack)`、二文档 `commands is not` 彼此）覆盖。CONFIRMED。
- **禁止路径 / 不改语义守卫**：`git diff --stat 99b15c0..HEAD -- src/authoring src/compiler src/render src/game` **仅** `src/authoring/scene/document.py`（schema 常量 / 包装类删除，ER7 预授权）+ `src/compiler/scene_spell.py`；`src/render`、`src/game` **零触及**。逐行核对：document.py = 删包装类 + 纯 int 化，无迁移 / schema 语义改动；scene_spell.py = **仅 docstring** 引用修正（`src.editor.pattern_resolve`→`src.compiler.pattern_resolve`）。未触 compiler/runtime、renderer API、N7 权限模型。其余 `src/editor/*`（21 文件，净 +69/-234）为 import 重指 + session 收敛，样本（coordinator/app/`__init__`）无新增非-import 产品逻辑。
- **§13/§2.7.5 反弱化审查**：边界分类器 `_is_command_module` 由“canonical **或** 迁移期 `src.editor.*_commands` allowlist”收紧为**仅** canonical `src.authoring.commands`，并删两行 parametrize（`("src.editor.commands",True)` / `("src.editor.scene_commands",True)`）——判为**合法契约收紧、非 §13 弱化**：ER7 step4 明令“清理迁移期 allowlist”，被删两行断言的模块路径在 shim 删除后**已不存在**（保留即断言死路径），契约系**收紧**而非放松。实证非空洞：直接加载边界测试模块跑其真实分类器——canonical 路径（`src.authoring.commands[.scene]`）仍返 True、死 shim 路径返 False、near-miss（`src.authoring.command_helpers`/`third_party.scene_commands`）仍返 False；并合成一个 `from src.authoring.commands.scene import …` 的 panel、经测试**自身**的 `_panel_paths/_imports/_is_command_module` 链，被正确 **FLAGGED**，证明 `test_panels_do_not_import_domain_commands` 对一切存活路径仍具保护力（探针即用即删）。重指测试为纯 import 路径重定位 + 生命周期适配（`SceneEditorSession(DocumentStore(...))`→`DocumentManager(...).active`，接口一致）；ER7 测试 diff 断言净 **+28/-3**，被删 3 行全为依赖旧毒化等价的 `schema_version==3`，已更正为 `==4`（更诚实/更强）；`test_editor_scene_commands` 一处 reparent 目标 `EnemySpawner`→`Sprite` 系 canonical `ManagedDocument.apply` **新增**父子合法性校验（旧 session 不校验）所致的**更严格**适配、测试意图不变、该文件零删断言。ER7 测试 diff **无新增** skip/xfail/pytest.mark/except/raises。新 `test_editor_schema_migration.py` 四例均非空洞（含 `_LegacyCompatibleSchemaVersion` 复活守卫、迁移标记断言、round-trip 固定点、真实 workbench 单生命周期/单 CommandStack），与 `test_scene_v4_contract.py`（wire-shape / 拒未知与未来版本 / opt-in 兼容 / header-only）**互补不冲突**。
- **独立验证**：由未参与 ER7 实现的只读 Agent（Read/Grep/pytest/git/自研 AST 脚本，未改任何产品/测试/工具代码）执行；四条硬指标全部 CONFIRMED；门禁全绿（全量 728 passed / 焦点 118 / 边界 29 / compileall exit 0）；禁止路径守卫通过（render/game 零触，authoring/compiler 仅预授权 schema 常量 + docstring）；边界收紧经实证判为合法契约收紧而非 §13 弱化。Verdict = **APPROVE**。

### ER8 架构整体验收

**状态/依赖**：`[x]`；依赖 ER7。该任务由未参与 ER1–ER7 实现的验证 Agent 执行，产品代码只读。

**允许路径**：门禁命令、验收报告和本文当前 Evidence/Blocker。任何产品修复必须退回对应 ER 所有者，ER8 不得边验收边修改。

**必须完成的证据**

1. Structural：架构边界 Contract 全绿、无循环、无禁止 import、兼容 allowlist 清空或逐项说明。
2. Runtime：focused + N2/N3 + 全量 suite、compileall、assets、diff-check。
3. Native visual：真实 PySide6 1480×920/960×640，中英文切换，无堆叠，正常启动和关闭。
4. Native interaction：场景选择/拖动、时间线定位/移动/修剪/缩放、Graph 真实拖线、Undo/Redo。
5. Formal preview：Pattern/Stage 加载、play/pause/seek/reset、overlay identity、异常退出和编辑器关闭。
6. Performance：固定 N5 workload 批量写入保持、逐弹回调为零，记录目标硬件、峰值和阈值。
7. Clean checkout：从干净 checkout 重跑，不依赖未提交文件、当前工作目录或手工预热状态。

**完成条件**：所有证据类别分别通过且没有残余 blocker。offscreen、截图、单一 pytest 数字或实现 Agent 自报不能替代对应证据。ER8 通过只允许开始 N6.4，不允许直接开始 N7。

**验收文件**：ER0–ER7 所有 focused 文件、现有 N2/N3/N6 gate、`tools/verify_native_editor_n4.py`、`tools/verify_native_editor_n5.py`、`tools/verify_native_editor_n6.py`、`tools/profile_n5_presets.py`。

**Evidence（独立验收 Agent，未参与 ER1–ER7 实现，产品/测试代码全程只读；七类证据齐备）**：

- **环境 / 身份**：`C:\Users\m1573\anaconda3\python.exe`（Python 3.12.7、PySide6、numba 0.60.0 / numpy 1.26.4），Windows 11 10.0.26200；分支 `codex/er2-coordinator-wip`，HEAD `0271ad7`（ER7 收口）；pre-ER0 diff 基线 `b95fc57`（God-class 拆分之父）。headless 门禁（pytest/compileall/profiler）设 `QT_QPA_PLATFORM=offscreen`、pytest flags `-o addopts= -p no:cacheprovider`；原生 harness 不设该变量（真实 windows 平台）。自研探针与一次性 harness 即用即删，未改任何 tracked 产品/测试文件、未提交。
- **1 Structural**：`pytest tests/test_editor_architecture_boundaries.py tests/test_editor_panel_boundaries.py` = **29 passed, exit 0**。无禁止 import（10 个 headless 包不 import editor/Qt）；compat allowlist 清零——命令边界分类器仅认 `src.authoring.commands*`，`command_helpers`/`src.game.commands`/`third_party.scene_commands` 均 False；`test_editor_graph_modules_have_no_import_cycles` 无环绿；Panel 零越权（不 import 域命令、不直接改文档）；协调者单一化 + 单一插件门面 + 无裸 preview QProcess。与 ER7 基线 29 一致（ER7 清理迁移期 allowlist 删 2 条 parametrize，由 ER6 时的 31 收敛为 29）。
- **2 Runtime**：diff-check `git diff --name-only b95fc57..HEAD -- src/render src/game` = **0 文件**（游戏运行时引擎 render/game 零改动，最强禁止路径结论）；反规避 `git diff --diff-filter=D --name-only b95fc57..HEAD -- tests` = **0**（无删测试）、全 `tests/` 的 `pytest.mark.(skip|xfail)` = **0**；assets `python tools/validate_assets.py --format json` → `ok:true errors:0 warnings:0`（json 74 / sprite_config 16 / sprites 745 / images 142），exit 0；N2/N3 focused（12 文件——N2 变量 8：typed_variables/variable_editor/variable_runtime/variable_scopes_and_reducers/variable_editor_native/variable_seek/variable_hotreload/replay_determinism；N3 事件反应 4：frame_boundary_events/lifecycle_events/reactions/reaction_scheduler）= **42 passed, exit 0**；**全量套件** `pytest -q -ra` = **728 passed in 551.95s (0:09:11), exit 0**（summary 仅 “728 passed”，0 skip/xfail/error）；`python -m compileall -q src` = **exit 0**。
- **3 Native visual**（真实 windows 平台，`QT_QPA_PLATFORM` 未设）：`platformName=windows`、isVisible=True、windowHandle_set=True、topLevel=1；截图字节 1480×920 EN=**44589**、960×640 EN=**39715**、1480×920 CN=**48720**（均真实位图）；语言 EN↔CN `cjk_texts 2→178→2`、菜单 `['&File'..]↔['文件(&F)'..]`；无堆叠（切换后 topLevel=1）；干净关闭 closed=True、visible_toplevels_after_close=0；末行 `er8_native_visual_ok`，EXIT=0。
- **4 Native interaction**（真实 windows 平台；QTest 真实鼠标/滚轮手势 + 包裹 `coordinator.dispatch` 计数 Intent，非直调 slot）：时间线/场景 harness——MOVE intents=1 start 60→90 undo→60 redo→90；TRIM intents=1 duration 120→150 undo/redo；SEEK playhead 0→102(≈100) 仅瞬时 `SetTimelinePlayheadIntent`、authoring_doc 未变；ZOOM(ctrl+wheel) 1.000→1.250 瞬时 `SET_ZOOM`、authoring_doc 未变；SCENE_DRAG intents=1 pos(192,224)→(288,288) undo/redo。teardown `window.close()` 命中产品未保存确认模态（预期守卫，非缺陷）故阻塞→kill（干净启停已由 visual harness 取证）。Graph 端口拖线 harness——移除 shape→aim 边 edges 5→4，真实鼠标 out→in 拖线 → 恰 1 个 `ADD_GRAPH_EDGE` 经 coordinator，edges 4→5，undo→4 redo→5；末行 `er8_native_interaction_B_ok`，`os._exit(0)` 干净退出。
- **5 Formal preview**：pytest（offscreen）`test_preview_session + test_preview_editor_integration + test_devtools_spell_preview + test_preview_controller + test_preview_process` = **40 passed, exit 0**，覆盖 Pattern/Stage 载入、play/pause/seek/reset（fixed-tick 命令契约 + spell seek/restart/pause）、overlay/stats 只读快照与失败回滚不写文档、异常退出+编辑器关闭幂等（QProcess crash 可诉且幂等清理、malformed input 不冻结、close/stop idempotent、runtime error 不逃逸、超额输出有界）。overlay-identity 原生证据 `tools/verify_native_editor_n4.py`（真实平台）：editor 命令 author 出 Reactive clip → formal `compile_stage`（断言未丢 reactive_clip）→ `StageRunner.start/emit/tick`（断言 reaction 真触发）→ overlay 从 `runner.reactive_overlay` **读出**（trace/active_instances 非空，脚本从不写 overlay）→ 经 `_handle_pattern_preview_event` 投递（断言 clip 激活且 `to_dict()==before` 文档未变）→ 真实双击（断言 `reactive_navigation[0]=='reaction'` 且文档未变），末行 `native_editor_n4_ok kind=Reactive traces=1`，`os._exit(0)` 干净退出。
- **6 Performance**：`python tools/profile_n5_presets.py` **exit 0**（脚本内建门禁：`per_bullet_callbacks != 0 或 elapsed_ms >= 2500` 即 exit 1，故 exit 0 强证逐弹回调=0 且总耗时 < 回归上限）。目标硬件 Windows-11-10.0.26200-SP0 / Intel64 Family 6 Model 151（Alder Lake）/ Python 3.12.7；**Numba 启用**（numba 0.60.0，`optimized_pool` 顶层 `from numba import njit`、核函数为已编译 `CPUDispatcher`（`@njit(cache=True)`），非 fallback）。固定 14 预设走正式 `PresetResolver.compile` + `PatternRunner`：spawned=**1836**、batch_writes=**101**、per_bullet_callbacks=**0**、elapsed=**40.447ms**（回归上限 2500ms）；峰值 rice-wall（米弹墙）512 弹 / 8 批写 / 4.895ms。批量写入保持（每预设 batch_writes≥1）、逐弹 Python 回调链=0。
- **7 Clean checkout**：`git worktree add` 全新检出 `0271ad7`，在其中（cwd 与 `PYTHONPATH` 均指向该 worktree，冷 `__pycache__`/Numba 缓存，offscreen）重跑 ER0–ER7 focused 并集（26 文件）+ N2/N3（12 文件）= **338 passed in 176.18s, exit 0**，`compileall -q src` = **exit 0**——证明不依赖未提交文件、主工作目录或预热态；`git worktree remove --force` 清理 exit 0。**caveat（非-blocker、非产品缺陷）**：本地 git 对象库两个 loose blob bit-rot（`assets/audio/music/04.wav`=df975ee5、`05.wav`=a343bb25；`git fsck --full` 仅此二者，无任何 `.py` 损坏），故干净检出用 `--no-checkout` + `git checkout 0271ad7 -- . ':(exclude)…04.wav' ':(exclude)…05.wav'` 绕过——两个损坏音频与全部代码门禁无关，属基础设施 bit-rot 而非 ER1–ER7 产物。
- **独立验证**：七类证据分别取得真实证据、无残余 code/test blocker；offscreen 仅作 Structural/Runtime 证据，Native visual/interaction 与 Formal-preview overlay-identity 均在真实 windows 平台取原生证据，Performance 由脚本门禁强证逐弹回调=0，Clean-checkout 在冷全新检出复现。offscreen、截图、单一 pytest 数字、实现 Agent 自报均未替代对应证据。全程未改任何产品/测试代码、未翻动第 214 行总表与本节状态行、未提交；一次性 harness（`tools/_er8_*`）取证后删除。

Verdict = **APPROVE**

## 9. N6.4：Usability gate

**前置条件**：ER8 已通过。在 ER8 之前不得邀请五名用户，避免在仍会发生结构迁移的版本上浪费人工样本。

**Agent 要做**：邀请至少 5 名没有 PySTG 经验的目标用户，记录首个 Pattern、全灭后续、两阶段 Boss+背景切换、撤销/重开/预览和一次局部展开的时间、失败点和求助次数；维护者不能口头带做。

**完成条件**：至少 4/5 用户在 10 分钟内完成可运行 Pattern、30 分钟内完成短道中、60 分钟内完成两阶段 Boss、一次背景转场和一次事件反应，全程不写脚本。

**验收文件**：`tests/test_editor_usability.py`、N6 focused gate、真实 PySide6 截图和 `reports/n6_usability.json`。

**Evidence / Blocker（尚未完成）**：研究协议已固定在 `docs/N6_USABILITY_PROTOCOL.md`，报告由 `tools/verify_n6_usability.py` 严格校验 5 名唯一、无 PySTG 经验、无维护者口头指导、无脚本及 4/5 时间阈值。此前四类 UI 阻塞已有自动化和原生证据，但 2026-08-20 架构复审新增 ER0–ER8 前置条件；当前没有报告且 ER8 未完成，本项保持 `[ ]`，N7 不得开始。

## 10. N7：Behavior Descriptor 与 Safe/Runtime/Engine 权限

### N7.0 Contract：统一 Descriptor

**Agent 要做**：阅读产品愿景第 5、14、15 节、插件 SDK、资源 registry 和 N6 Catalog；创建 `tests/test_behavior_descriptor.py`、`tests/test_safe_capabilities.py`、`tests/test_plugin_package_boundaries.py`、`tests/test_behavior_plugin_integration.py`；冻结 stable ID/version、typed ports、参数 schema、capabilities、lifecycle/cancel、debug snapshot、Tool contribution 和 manifest 错误。

**完成条件**：headless runtime 能拒绝越权；同一 Descriptor 的 schema/runtime/tool identity 一致。

**验收文件**：上述四份 Contract。

### N7.1 Safe API

**Agent 要做**：只开放批量发射、授权移动、资源播放、只读 snapshot、类型化等待和局部变量；不返回 Pool/Renderer/Manager，不允许文件、网络、进程或模块访问。明确进程内 Python 是受信任 Runtime，不冒充沙箱。

**完成条件**：manifest 和运行时能力检查都拒绝越权；Safe 行为可热重载、可取消、可 debug。

**验收文件**：`tests/test_safe_capabilities.py`、`tests/test_behavior_descriptor.py`、`tests/test_editor_regression_contracts.py`。

### N7.2 Runtime API

**Agent 要做**：允许注册组件、事件、弹道、碰撞、道具和受限 Renderer Pass；声明线程、所有权、清理和 replay policy；禁止逐弹回调、任意全局状态和未声明输出。

**完成条件**：Runtime 插件可服务 N4/N5 行为，失败和取消可追踪，headless 不导入 Qt。

**验收文件**：`tests/test_behavior_plugin_integration.py`、`tests/test_plugin_sdk.py`、`tests/test_safe_capabilities.py`。

### N7.3 Engine API

**Agent 要做**：为调度器、渲染后端、资源类型、编辑器插件和编译器节点提供内部扩展点；明确版本迁移和普通项目不可依赖的边界；不把 Engine API 作为内容作者入口。

**完成条件**：Engine 扩展可演进，普通项目 schema/Runtime 契约不因内部变化隐式改变。

**验收文件**：`tests/test_plugin_package_boundaries.py`、`tests/test_behavior_descriptor.py`、`tests/test_editor_regression_contracts.py`。

### N7.4 分区包、依赖锁、加载与回滚

**Agent 要做**：将 manifest、dependency lock、schema/migration、runtime/compiler、tool、assets/examples/presets 分区；加载、热重载、回滚和卸载是事务；Tool 按需加载，headless 不导入 Qt，Runtime 失败清理所有 owner/lease。

**完成条件**：缺依赖、未知 capability、迁移失败和卸载异常都有结构化诊断，不污染文档或进程。

**验收文件**：`tests/test_plugin_package_boundaries.py`、`tests/test_plugin_sdk.py`、`tests/test_behavior_plugin_integration.py`。

### N7.5 ComplexMapEmitter 示范插件

**Agent 要做**：实现真实 `ComplexMapEmitter`，暴露采样域、`z²+c` 函数、采样数、位置映射、颜色、Inspector、画布控制柄、预览和 debug snapshot；普通作者只调参数，高级作者可定位源码。

**完成条件**：同一实例在 Content、Runtime、Tool 和 trace 中 identity 一致；源码扩展不要求普通作者进入 Engine API。

**验收文件**：`tests/test_behavior_plugin_integration.py`、`tests/test_plugin_sdk.py`、`tests/test_editor_authoring_integration.py`；另附正式预览 native visual parity。

## 11. N8：Renderer Pass 与 Render Graph

### N8.0 Contract：后端中立 IR

**Agent 要做**：创建 `tests/test_render_graph.py`、`tests/test_renderer_pass_plugins.py`、`tests/test_render_graph_backend.py`、`tests/test_renderer_pass_editor.py`；冻结 attachment、格式/尺寸/sample、依赖、hazard、resource lease、fallback 和错误定位。

**完成条件**：Contract 能拒绝环、未初始化读取、格式冲突、过期 lease 和未声明 capability。

**验收文件**：上述四份 Contract。

### N8.1 PassDescriptor 与编译器

**Agent 要做**：定义后端中立 `PassDescriptor`、输入/输出 attachment、load/store、参数 schema、合并和生命周期；编译期拒绝环、未初始化读取、格式冲突和 capability 不足；IR 不携带 ModernGL 对象。

**完成条件**：Pass 顺序、资源依赖和失败路径可序列化、可诊断、可重放。

**验收文件**：`tests/test_render_graph.py`、`tests/test_render_graph_backend.py`。

### N8.2 受限 PassContext 与资源 lease

**Agent 要做**：Runtime 插件只获得 scoped `PassContext`、`CommandEncoder` 和 resource lease；不能取得全局 GL state、持有过期资源或跨 owner 释放资源；热卸载必须结束 lease。

**完成条件**：越权、跨帧资源和清理错误均显式失败，不靠静默替代。

**验收文件**：`tests/test_renderer_pass_plugins.py`、`tests/test_render_graph.py`。

### N8.3 ModernGL backend adapter

**Agent 要做**：接入正式 ModernGL/GLFW 路径；adapter 将 IR 转成命令；缺能力只在 Descriptor 明确允许且语义可接受时 fallback，否则在编译/导出阶段报错；验证热重载和资源释放。

**完成条件**：正式 surface 的输出与资源生命周期可追踪；Qt 预览不冒充 renderer 证据。

**验收文件**：`tests/test_render_graph_backend.py`、`tests/test_renderer_pass_plugins.py`、`tests/test_background_data_driven_parity.py`；附 GLFW/ModernGL native 证据。

### N8.4 Tool/Runtime parity

**Agent 要做**：Tool 复用同一 Descriptor 提供 Inspector、控制柄和缩略预览；缺 Tool contribution 时退化为通用 Inspector；不得另建与正式 Render Graph 不同的效果实现。

**完成条件**：编辑器参数、正式 renderer 和 debug snapshot 对同一实例保持一致。

**验收文件**：`tests/test_renderer_pass_editor.py`、`tests/test_editor_authoring_integration.py`、`tests/test_render_graph_backend.py`。

## 12. N9：分层调试、确定性重放、性能与发布

### N9.0 Contract：trace 与 release workload

**Agent 要做**：创建 `tests/test_editor_debugger.py`、`tests/test_replay_determinism.py`、`tests/test_runtime_profile.py`、`tests/test_editor_next_acceptance.py`；冻结 trace 协议版本、why-not 字段、replay identity 和 release workload。

**完成条件**：Contract 能验证相同输入的 trace identity、未触发/取消/冲突的原因和预算字段。

**验收文件**：上述四份 Contract。

### N9.1 统一 trace 与 why-not 调试器

**Agent 要做**：记录 author resource ID、runtime instance ID、owner/cancel token、State path、Clip/Reaction、事件因果、变量读写、生成数、batch 摘要、CPU/GPU、诊断和版本；调试器支持 pause/step/seek/reset/why-not，并能跳回资源、属性或行为节点。

**完成条件**：能回答谁写/谁读、为何未触发、为何取消、为何冲突；overlay 不写作者文档。

**验收文件**：`tests/test_editor_debugger.py`、`tests/test_editor_next_acceptance.py`、N4/N7 回归。

### N9.2 确定性 replay/seek

**Agent 要做**：将 seed、外部输入、资源/插件版本、初始变量和副作用 policy 纳入 replay identity；seek 只能 reset+固定帧重放，若加入检查点必须证明逐帧等价并可回退；未记录的外部输入标记为不可复现。

**完成条件**：同一 identity 的正常播放、reset、seek、热重载兼容路径 trace 逐帧一致，差异能定位到输入、版本、规则或资源。

**验收文件**：`tests/test_replay_determinism.py`、`tests/test_variable_seek.py`、`tests/test_variable_hotreload.py`、`tests/test_preview_process.py`。

### N9.3 性能 profile 与预算

**Agent 要做**：在明确 Windows 目标硬件上测高密度 Pattern、batch lifecycle、Reaction、复杂 State/Timeline、ComplexMap、Render Graph 和长 seek；固定 workload、时间/内存/批量阈值、首次编译是否计入和报告格式；记录峰值，不用平均数掩盖超预算帧。

**完成条件**：预算随 trace、导出 profile 和诊断记录；超预算阻止发布或给出明确降级，不静默删效果。

**验收文件**：`tests/test_runtime_profile.py`、`tests/test_replay_determinism.py`、N3 batch tests、N8 backend tests；附目标硬件 Performance 报告。

### N9.4 最终作者工作流

**Agent 要做**：从模板完成短道中和两阶段 Boss，包含全灭后续、假 Boss 受击反击、死亡开花、背景切场、Runtime Behavior 和 Renderer Pass；保存、重开、Undo/Redo、热重载、seek、预览和导出均走正式路径。

**完成条件**：顶层作者无需接触 Engine API；高级作者能从可视结构进入源码；所有实例和钩子可在调试器定位。

**验收文件**：`tests/test_editor_next_acceptance.py`、`tests/test_editor_authoring_integration.py`、`tests/test_preview_process.py`、`tests/test_preview_editor_integration.py`、N4–N8 focused gate；附 native visual 和人工 workflow 报告。

### N9.5 发布门禁

**Agent 要做**：在同一 checkout 产生完整 tests、compileall、assets、diff、主游戏、Pattern/Stage preview、PySide6 窗口、正式 renderer、恢复、插件卸载和 profile 报告；分别给出 Structural/Runtime/Performance/Native visual/Usability 结论。

**完成条件**：所有阶段停止条件关闭，focused gate、迁移、性能、原生窗口和人工可用性证据齐全后才允许发布；offscreen、`--help` 或单一“全绿”数字不能替代发布门禁。

**验收文件**：N2–N9 全部 focused 文件、`tests/test_preview_process.py`、`tests/test_preview_editor_integration.py`、`tests/test_editor_authoring_integration.py`、`tests/test_editor_next_acceptance.py`，以及发布报告。

## 13. 完成记录规则

- 每个未完成任务只保留一个 `Evidence / Blocker` 段落。验证完成后原地更新该段落，再由主协调 Agent 把总表和任务状态从 `[ ]` 改为 `[x]`；不得追加交接日记、聊天记录或第二份 Todo。
- Evidence 必须写完整命令、通过数量或报告路径、commit/工作树状态、Python/Qt/硬件环境，并分别标记 Structural、Runtime、Performance、Native visual、Usability。没有观察的类别写 `not run`，不能省略后暗示通过。
- Contract、focused gate、迁移、性能、原生窗口或人工证据缺失时保持 `[ ]`；“代码已写完”“文件已存在”“offscreen 通过”都不构成缺失类别的证据。
- 禁止通过删测试、放宽断言、吞异常、`skip`/`xfail`、第二套预览、直接调用下游槽函数、伪造报告或写回运行时状态来“完成”任务。
- 若 ER 实现发现必须改变冻结产品语义，当前任务保持 `[ ]` 并请求维护者决定；不得在架构整改提交中静默修改契约。
