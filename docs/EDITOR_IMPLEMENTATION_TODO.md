# PySTG 下一代编辑器未来实施 TODO（固定版）

> 状态：Active。本文是仓库唯一的未来实施清单，也是 Agent 的交接协议。
> 产品依据：[EDITOR_PRODUCT_VISION.md](EDITOR_PRODUCT_VISION.md)；工程边界：[EDITOR_ARCHITECTURE.md](EDITOR_ARCHITECTURE.md)。
> 本版固定日期：2026-08-10。历史路线图和完成日志只通过 Git 追溯，不再作为任务来源。

这份文件只描述尚未完成的工作。任务 ID 一旦发布就保持稳定；Agent 只能领取依赖链上最早的未完成任务。没有对应测试和证据，不能把“已有一部分代码”当作完成。

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

## 4. 未完成任务总表

依赖顺序固定为：`N4 → N5 → N6 → N7 → N8 → N9`。同一阶段内按编号顺序领取；当前阶段 focused gate 未通过，不得开始下一阶段。

| ID | 主题 | 状态 | 依赖 |
| --- | --- | --- | --- |
| N4.0 | 响应式时间线 Contract | `[x]` | N3 |
| N4.1 | ReactiveClip 正式运行时与实例 trace | `[x]` | N4.0 |
| N4.2 | 时间线槽位、overlay、导航与冲突编辑 | `[ ]` | N4.1 |
| N5.0 | 版本化预设 Contract | `[ ]` | N4 |
| N5.1 | 首发预设库 | `[ ]` | N5.0 |
| N5.2 | 虚拟展开 | `[ ]` | N5.1 |
| N5.3 | 参数覆盖与本地物化 | `[ ]` | N5.2 |
| N5.4 | 精确版本迁移 | `[ ]` | N5.3 |
| N6.0 | Action Catalog 与新手流程 Contract | `[ ]` | N5 |
| N6.1 | 上下文感知搜索 | `[ ]` | N6.0 |
| N6.2 | 道中/关底骨架模板 | `[ ]` | N6.1 |
| N6.3 | 分层展开与连续编辑 | `[ ]` | N6.2 |
| N6.4 | Usability gate | `[ ]` | N6.3 |
| N7.0 | Behavior Descriptor/权限 Contract | `[ ]` | N6 |
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

**Evidence（2026-08-10）**：Structural/Runtime：`python -m pytest -q tests/test_editor_reactive_clips.py tests/test_reaction_timeline_integration.py tests/test_editor_timeline_workspace.py tests/test_state_graph_editor.py`（通过）；offscreen Qt 只作为结构和运行证据。Native visual gate 未关闭：当前 Windows 会话的真实 `EditorMainWindow` smoke 在构造阶段异常退出，不能用 offscreen 结果替代，因此本项保持 `[ ]`。

## 6. N5：可展开的版本化预设

### N5.0 Contract：描述、身份和迁移语义

**Agent 要做**：阅读产品愿景第 11 节、`src/pattern` 资源/编译器和 N4 规则；创建 `tests/test_preset_descriptor.py`、`tests/test_preset_expansion.py`、`tests/test_preset_migration.py`；冻结 stable preset ID/version、参数 schema、公开插槽、输入/输出变量、事件、虚拟内部 ID、覆盖优先级、精确版本锁、未知字段和迁移失败语义。

**完成条件**：Contract 能拒绝错误类型、缺失版本、未知字段和迁移环；预设实例不会因编辑器升级静默改变。

**验收文件**：`tests/test_preset_descriptor.py`、`tests/test_preset_expansion.py`、`tests/test_preset_migration.py`。

### N5.1 首发预设库

**Agent 要做**：以真实资源提供自机狙、奇数弹、偶数弹、圆形开花、扇形扫射、单/双/交错螺旋、加速旋转、延迟转向、子弹分裂、速度层叠、波纹、米弹墙；每个预设暴露少量精确参数、生命周期策略和预算，走正式 compiler/runner。

**完成条件**：预设可运行、可展开、可调参；与基础 Pattern 行为 parity；高密度路径无逐弹 Python 回调。

**验收文件**：`tests/test_preset_library.py`、`tests/test_pattern_parity.py`、`tests/test_pattern_compiler.py`；附固定 workload profile。

### N5.2 虚拟展开

**Agent 要做**：只读显示内部发射器、参数和局部行为；虚拟节点 ID 由实例 ID+预设内部 ID 稳定派生；折叠/展开不复制 Scene 节点、不制造 runtime 实例，trace 能从外部实例定位内部节点。

**完成条件**：折叠、展开、保存、重开、reset 的 authoring/runtime identity 一致；没有第二份可漂移文档。

**验收文件**：`tests/test_preset_expansion.py`、`tests/test_editor_preset_workspace.py`、`tests/test_pattern_graph.py`。

### N5.3 参数覆盖与本地物化

**Agent 要做**：公开参数和插槽可覆盖；“展开为本地结构”是可预览、可取消、可 Undo/Redo 的单一 CommandStack 事务；物化后与上游预设断开且不被升级偷偷改写；失败保留原实例。

**完成条件**：覆盖优先级和差异报告可解释；物化、撤销、重做、运行和 trace 可重放。

**验收文件**：`tests/test_preset_expansion.py`、`tests/test_editor_preset_workspace.py`、`tests/test_editor_authoring_integration.py`。

### N5.4 精确版本迁移

**Agent 要做**：按精确版本执行参数/插槽迁移，在临时副本生成差异和诊断；失败保留原数据、原版本和定位路径；项目依赖锁定到可重放版本，不使用“最接近版本”静默替代。

**完成条件**：成功迁移 round-trip；失败可恢复、可 Undo，原文档不被部分写入。

**验收文件**：`tests/test_preset_migration.py`、`tests/test_preset_descriptor.py`、`tests/test_pattern_document.py`。

## 7. N6：上下文搜索与新手连续流程（不含自然语言）

### N6.0 Contract：Action Catalog 与新手流程

**Agent 要做**：阅读产品愿景第 10、12、13 节和 N5 接口；创建 `tests/test_action_catalog.py`、`tests/test_contextual_search.py`、`tests/test_beginner_workflow.py`、`tests/test_editor_usability.py`；冻结 Descriptor→Catalog schema、输入/输出类型、上下文过滤、稳定排序、创建事务、空状态引导和错误定位。自然语言生成明确不在范围。

**完成条件**：Contract 断言实际候选、类型端口、Command/Undo 和空状态，而不是菜单字符串。

**验收文件**：上述四份 Contract。

### N6.1 上下文感知搜索

**Agent 要做**：在任意作者上下文轻按空格打开搜索；PointSet 拉线只显示接受 PointSet 的 Action；时间线只显示轨道/片段；场景画布只显示可创建对象；Catalog 来自 Descriptor，UI 不写死分支；解决空格搜索与画布平移冲突并用原生 QA 固定交互。

**完成条件**：无效候选不出现，结果可解释且排序稳定；创建和连接都进入文档 CommandStack。

**验收文件**：`tests/test_action_catalog.py`、`tests/test_contextual_search.py`、`tests/test_editor_graph_workspace.py`、`tests/test_editor_timeline_workspace.py`；另附 native visual。

### N6.2 道中/关底骨架模板

**Agent 要做**：项目向导生成道中和两阶段 Boss 骨架（State、Timeline、Background、Pattern、音频和预览入口）；模板创建是一个可 Undo 的文档事务；缺资源、条件错误和 runtime error 定位到资源/属性/规则。

**完成条件**：新人无需理解事件队列、内部 ID 或插件注册即可完成首个 Pattern、全灭后续和背景转场。

**验收文件**：`tests/test_beginner_workflow.py`、`tests/test_editor_m3_integration.py`、`tests/test_editor_authoring_integration.py`、`tests/test_editor_timeline_workspace.py`。

### N6.3 分层展开与连续编辑

**Agent 要做**：固定 L0 预设卡片→L1 参数→L2 曲线/变量/表达式→L3 行为图→L4 Runtime 源码的入口、返回和权限提示；所有层级共享同一生命周期、类型、owner 和 debug identity；局部替换不要求推倒重写。

**完成条件**：从调参到局部实现是连续操作；折叠/展开不复制资源、不产生第二套 runtime。

**验收文件**：`tests/test_beginner_workflow.py`、`tests/test_editor_graph_workspace.py`、`tests/test_editor_preset_workspace.py`、`tests/test_editor_usability.py`。

### N6.4 Usability gate

**Agent 要做**：邀请至少 5 名没有 PySTG 经验的目标用户，记录首个 Pattern、全灭后续、两阶段 Boss+背景切换、撤销/重开/预览和一次局部展开的时间、失败点和求助次数；维护者不能口头带做。

**完成条件**：至少 4/5 用户在 10 分钟内完成可运行 Pattern、30 分钟内完成短道中、60 分钟内完成两阶段 Boss、一次背景转场和一次事件反应，全程不写脚本。

**验收文件**：`tests/test_editor_usability.py`、N6 focused gate、真实 PySide6 截图和独立 Usability 报告。

## 8. N7：Behavior Descriptor 与 Safe/Runtime/Engine 权限

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

## 9. N8：Renderer Pass 与 Render Graph

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

## 10. N9：分层调试、确定性重放、性能与发布

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

## 11. 完成记录规则

- 子任务完成后只把该任务的 `[ ]` 改为 `[x]`，并在任务末尾追加一段可复制的 Evidence；不得重写冻结基线、创建副本 Todo 或粘贴聊天日志。
- Evidence 必须写命令、通过数量或报告路径、Python/Qt/硬件环境，并区分 Structural/Runtime/Performance/Native visual/Usability。
- focused gate、迁移、性能、原生窗口或人工证据缺失时保持 `[ ]`。禁止通过删测试、放宽断言、吞异常、第二套预览或写回运行时状态来“完成”任务。
