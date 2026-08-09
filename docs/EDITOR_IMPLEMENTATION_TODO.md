# PySTG 下一代编辑器实施 TODO（固定版）

> 状态：Active。本文是仓库唯一的未来实施清单，也是 Agent 的交接协议。
> 产品依据：[EDITOR_PRODUCT_VISION.md](EDITOR_PRODUCT_VISION.md)；工程边界：[EDITOR_ARCHITECTURE.md](EDITOR_ARCHITECTURE.md)。
> 本版固定日期：2026-08-10。

这份清单只描述尚未完成的工作。历史路线图、已完成阶段的长篇日志和只服务交接的测试不再作为任务来源；需要追溯时使用 Git 历史。所有任务使用稳定的 `N<阶段>.<编号>` ID，Agent 只能领取依赖链上最早的未完成任务。

## 0. 当前基线与范围

### 0.1 已冻结、不可重复领取的前置条件

以下内容已经在当前 `main` 分支完成并由行为测试覆盖，后续 Agent 只能依赖它们，不能重新发明第二套语义：

| 基线 | 已固定的运行时协议 | 主要入口 |
| --- | --- | --- |
| N0/N1 | 版本化作者资源、`SceneDocument`、内嵌 State Graph、时间轴稳定 UUID、正式 Pattern/Stage 预览 | `src/editor/document.py`、`src/editor/stage_compile.py` |
| N2 | 类型化变量、六类作用域、单一写入者、reducer、只读 Engine Snapshot、CommandStack、reset/seek/hot-reload | `src/authoring/variables.py`、`src/game/stage/program.py` |
| N3 | 本帧 Outbox→下一帧 Inbox、类型化生命周期事实、批量生命周期事件、`ReactionSpec`、`TaskScope`、State/Background hook | `src/game/events.py`、`src/game/reactions.py`、`src/game/stage/context.py` |

N2/N3 的 focused gate 和全量回归必须保持绿色；它们不是 N4 以后可以删掉的“旧测试”。若契约确实需要改变，先单独提交 contract-revision 并得到维护者确认。

### 0.2 产品与架构决定

以下决定从本版起作为实现前提：

- 短期和中期完全不做自然语言或 Agentic 弹幕生成。弹幕的帧、角度、速度、数量、种子和预算必须由确定性的属性、曲线、预设、上下文搜索或行为图表达。
- 系统有三条正交职责轴：Content（版本化数据和标准组件）、Behavior（动作/事件/脚本的生命周期）和 Tool（编辑器插件）。另有三层信任边界：Safe API、Runtime API、Engine API。
- 状态图回答“当前阶段是什么”；时间线回答“哪些生命周期在何时有效、持续和停止”；行为图/脚本回答“一个行为内部怎样计算、采样、循环和产出事件”。三者只通过类型化变量、事件、资源引用和 owner/cancel token 交流，不互持 Qt 对象、运行时对象或 Clip ID。
- 条件时间线内容是 `ReactiveClip`/`ActivationRule`，不是从蓝图拉出一长串隐形连线。行为发布事实，ReactionResolver 在同一帧快照上决定是否创建实例，创建后仍由时间线拥有其生命周期。
- 事件走本帧 Outbox、下一固定帧 Inbox；一次 dispatch 不重入。高密度子弹和生命周期事实走批量路径，不为每颗子弹创建场景节点、通用 Python Event 或 Python 回调。
- 作者文档是唯一真源。运行时变量、事件、实例和 overlay 不写回作者文档、不制造 dirty；所有编辑修改经过 `CommandStack` 并可 Undo/Redo。
- 时间轴拖动“从头重放到目标帧”的结构性成本本版不解决，只冻结 reset/replay 的正确性和可观察 overlay。

### 0.3 三个必须贯穿验收的例子

| 例子 | 内容作者看到的结构 | 运行时边界 |
| --- | --- | --- |
| 死亡开花 | `DeathBloom` 预设或时间线反应槽，调数量/速度/颜色；展开后才看局部发射器 | 子弹发布 `bullet.expired`/`bullet.death`，反应按密度策略批量生成；不由子弹查找片段 ID |
| 假 Boss 受击反击 | 关底 State 的 `ReactiveClip`，过滤 `target_tag=fake`，显式选择 `count_per_frame`、冷却和最大实例 | 假 Boss 只发布 `enemy.hit`；时间线条件决定反击是否在当前阶段有效；State 退出优先取消旧反应 |
| 击破后背景切换 | 若是阶段变化，在 State Graph 转移；若只是演出，在时间线放 Background cue | 事件只描述 `enemy.defeated`/`encounter.cleared`，背景资源由状态或反应拥有，renderer 不监听网络/Stage 内部对象 |

### 0.4 顶层作者的默认流程

1. 项目向导创建道中或关底 Stage 骨架。
2. State Graph 建立 Intro/Normal/Enrage/End 等阶段；只在阶段边界放转移。
3. 每个 State 的时间线安排敌人、Boss 移动、背景、音频、弹幕和演出；条件反应放 `ReactiveClip` 槽位。
4. Pattern 先选预设并用 Inspector 调精确参数；需要曲线、变量或表达式时局部展开。
5. 行为图只承接局部采样、循环、数学和事件生产；不把阶段关系搬进蓝图。
6. 只有预设、Action、受限表达式和行为图都不足以表达新算法时，玩法开发者才写 Runtime Behavior；普通内容作者不需要写脚本。
7. 预览、调试、seek、reset、保存和重开都走正式 runtime；背景钩子使用资源引用和生命周期 owner。

## 1. Agent 执行协议

每个任务必须严格按 `Read → Audit → Contract → Implement → Verify → Record` 执行：

1. **Read**：先运行 `git status --short`；完整阅读任务列出的产品章节、源码入口、schema、fixture 和回归测试，保护不属于本任务的改动。
2. **Audit**：运行任务已有回归，观察真实 document/compiler/runner/preview 行为；不能从 TODO 推测代码现状。
3. **Contract**：先创建或补强任务列出的测试，使用真实 fixture、可观察断言和错误边界，形成红色预期。禁止只有 import、源码字符串、空 `pass`、宽泛 `except`、`skip` 或 `xfail`。
4. **Implement**：只修改任务边界内的 authoring/compiler/runtime/editor 文件，使 Contract 逐步变绿。不得削弱断言、吞异常、引入第二套预览模拟器、逐弹回调或把运行时状态写回文档。
5. **Verify**：运行 focused gate、N2/N3 回归、全量 suite、`compileall`、资源校验和 `git diff --check`。Native visual、Performance、Usability 必须分别取证，offscreen 不能代替它们。
6. **Record**：只更新本任务的状态和 Evidence；Evidence 写可复制命令、通过数量/报告路径、环境和剩余限制，不粘贴聊天日志。

### 1.1 每次 Agent 交付卡

交接消息或提交说明必须包含：

| 字段 | 内容 |
| --- | --- |
| Task ID / 边界 | 本次处理的 ID；明确不处理哪些相邻任务 |
| Read / Audit | 实际读过的章节、入口、schema/fixture、现有测试和 `git status` |
| Contract | 新增/扩展的测试、真实 fixture、红色基线和错误边界 |
| Implementation | 修改的 authoring/compiler/runtime/editor 文件；owner、取消、迁移和错误路径 |
| Verification | focused、回归、全量、compileall、资源校验、diff-check；额外 native/performance/usability 命令 |
| Evidence / Blocker | 通过数量、环境、报告路径、仍缺的门禁；阻塞时保持 `[ ]` 并说明下一步 |

出现以下情况必须停止扩大范围并请求维护者决定：契约与产品愿景冲突；schema 无法无损迁移；必须逐弹回调、第二套预览、静默 fallback 或绕过 Undo；focused gate 仍红却要开始下一阶段；native、性能或可用性证据在当前环境无法提供；或用户改动无法安全合并。

## 2. 共同验收门禁

每个任务的 focused 命令之外，至少执行：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q main.py src game_content tools tests
python tools/validate_assets.py --format json
git diff --check
```

证据必须标明类别：Structural（schema/命令/序列化）、Runtime（正式 compiler/runner/preview）、Performance（固定环境和 workload）、Native visual（真实 PySide6/GLFW/ModernGL 窗口）和 Usability（未接触 PySTG 的目标用户）。一种证据不能替代另一种。

### 2.1 阶段 focused gate

新 Contract 文件只能在对应任务开始时创建，不能预先提交空文件或把不存在的文件写成“已通过”。

| 阶段 | focused 测试文件 | 额外门禁 |
| --- | --- | --- |
| N2 回归 | `test_typed_variables.py`、`test_variable_runtime.py`、`test_variable_editor.py`、`test_state_graph_document.py`、`test_state_graph_runtime.py`、`test_stage_program.py`、`test_scene_v4_contract.py`、`test_variable_scopes_and_reducers.py`、`test_variable_editor_native.py`、`test_variable_seek.py`、`test_variable_hotreload.py`、`test_replay_determinism.py` | N2 原生窗口和 replay identity/seek trace |
| N3 回归 | `test_lifecycle_events.py`、`test_frame_boundary_events.py`、`test_task_scopes.py`、`test_lifecycle_batching.py`、`test_reactions.py`、`test_reaction_scheduler.py`、`test_lifecycle_timeline_hooks.py`、`test_background_reactions.py` | 正式 Stage/Pattern trace；高密度批处理 profile |
| N4 | `test_reactive_timeline.py`、`test_activation_rules.py`、`test_timeline_instance_trace.py`、`test_reaction_timeline_integration.py`、`test_editor_reactive_clips.py` | 原生时间线交互；reset/replay 等价性 |
| N5 | `test_preset_descriptor.py`、`test_preset_expansion.py`、`test_preset_migration.py`、`test_preset_library.py`、`test_editor_preset_workspace.py` | 预设 workload；Undo/Redo/物化 trace |
| N6 | `test_action_catalog.py`、`test_contextual_search.py`、`test_beginner_workflow.py`、`test_editor_usability.py` | 原生窗口；至少 4/5 新用户门槛 |
| N7 | `test_behavior_descriptor.py`、`test_safe_capabilities.py`、`test_plugin_package_boundaries.py`、`test_behavior_plugin_integration.py`、`test_plugin_sdk.py` | headless 不导入 Qt；Runtime/Tool parity |
| N8 | `test_render_graph.py`、`test_renderer_pass_plugins.py`、`test_render_graph_backend.py`、`test_renderer_pass_editor.py` | GLFW/ModernGL surface；热卸载和资源释放 |
| N9 | `test_editor_debugger.py`、`test_replay_determinism.py`、`test_runtime_profile.py`、`test_editor_next_acceptance.py` | 目标 Windows 硬件 profile、原生窗口、完整发布工作流 |

## 3. 测试清理与保留规则

### 3.1 已完成的历史清理

以下文件已经在历史整理提交中删除或合并，本版不重新添加：

- 文档：`docs/EDITOR_ROADMAP_TODO.md`、`docs/ARCHITECTURE_EVALUATION_AND_ROADMAP.md`。
- 纯交接/演示测试：`tests/test_bottom_layer_smoke.py`、`tests/test_m4_runtime_preview_contract.py`、`tests/test_stage1_opening_media.py`。
- 旧命名已改为行为覆盖：`test_luna_acceptance_bundle.py` → `test_editor_authoring_integration.py`；`test_m5_m7_remediation_gate.py` → `test_editor_regression_contracts.py`。

### 3.2 本次审计结论

本次没有新增可安全删除的测试。`test_editor_app_smoke.py` 虽然名字带 smoke，但覆盖真实窗口命令、Undo 和正式预览入口；M3–M6、Pattern/Stage/UI/Background、事件、插件、资源和恢复测试都有可观察行为断言。删除它们只会降低覆盖，不能作为“让 suite 变绿”的手段。

以后若要删除测试，必须同时满足：测试只验证已经移除的接口或重复的交接流程；对应行为已有更窄、更真实的测试；在同一提交说明中给出替代文件和 suite 数量变化。不得因为测试慢、需要 Qt、名称含 smoke 或断言暂时失败就删除。

## 4. 未完成任务总表

依赖顺序固定为：`N4 → N5 → N6 → N7 → N8 → N9`。同一阶段内按编号顺序领取；未通过当前阶段门禁不得开始下一阶段。

| ID | 主题 | 状态 | 依赖 |
| --- | --- | --- | --- |
| N4.0 | 响应式时间线 Contract | `[ ]` | N3 |
| N4.1 | ReactiveClip 运行时与实例 trace | `[ ]` | N4.0 |
| N4.2 | 时间线槽位、overlay 与冲突编辑器 | `[ ]` | N4.1 |
| N5.0 | 版本化预设 Contract | `[ ]` | N4 |
| N5.1 | 首发预设库 | `[ ]` | N5.0 |
| N5.2 | 虚拟展开 | `[ ]` | N5.1 |
| N5.3 | 参数覆盖与本地物化 | `[ ]` | N5.2 |
| N5.4 | 预设迁移 | `[ ]` | N5.3 |
| N6.0 | Action Catalog/新手流程 Contract | `[ ]` | N5 |
| N6.1 | 上下文搜索 | `[ ]` | N6.0 |
| N6.2 | 道中/关底新手骨架 | `[ ]` | N6.1 |
| N6.3 | 分层展开与连续编辑 | `[ ]` | N6.2 |
| N6.4 | Usability gate | `[ ]` | N6.3 |
| N7.0 | Behavior Descriptor 与权限 Contract | `[ ]` | N6 |
| N7.1 | Safe API | `[ ]` | N7.0 |
| N7.2 | Runtime API | `[ ]` | N7.1 |
| N7.3 | Engine API | `[ ]` | N7.2 |
| N7.4 | 分区插件包与加载回滚 | `[ ]` | N7.3 |
| N7.5 | ComplexMapEmitter 示范插件 | `[ ]` | N7.4 |
| N8.0 | Render Graph Contract | `[ ]` | N7 |
| N8.1 | PassDescriptor 与编译器 | `[ ]` | N8.0 |
| N8.2 | 受限 PassContext 与资源 lease | `[ ]` | N8.1 |
| N8.3 | ModernGL backend adapter | `[ ]` | N8.2 |
| N8.4 | Tool/Runtime parity | `[ ]` | N8.3 |
| N9.0 | 调试/重放/性能 Contract | `[ ]` | N8 |
| N9.1 | 统一 trace 与 why-not 调试器 | `[ ]` | N9.0 |
| N9.2 | 确定性 replay/seek | `[ ]` | N9.1 |
| N9.3 | 性能 profile 与预算 | `[ ]` | N9.2 |
| N9.4 | 最终作者工作流 | `[ ]` | N9.3 |
| N9.5 | 发布门禁 | `[ ]` | N9.4 |

---

## N4 — 响应式时间线与蓝图边界

**阶段目标**：让“某个条件产生的时间线内容”成为可见、可调试、可取消的生命周期，而不是蓝图到时间线的长连线。时间线保存规则和 owner；行为图生产事实；运行时创建实例。

### N4.0 Contract：冻结激活规则

状态：`[ ]`。开始前必须读产品愿景第 7、10、17 节；`src/editor/document.py`、`src/editor/timeline_commands.py`、`src/game/events.py`、`src/game/reactions.py`、N2/N3 测试和 scene schema。

Agent 要做：

- 新建 `tests/test_reactive_timeline.py`、`tests/test_activation_rules.py`、`tests/test_timeline_instance_trace.py`，先写真实失败断言和最小 scene/pattern fixture。
- 冻结 `at_frame`（固定帧/窗口）、`when_variable`（变量路径、比较、边沿）、`on_event`（事件类型/过滤/密度）、`on_lifecycle`（来源、owner、终止原因）四类规则的可序列化表示。
- 冻结 scope（State/Stage/Clip/Reaction/Behavior）、默认 `once_per_scope + max_instances=1 + ignore_while_running`、显式 `restart/parallel`、动态延迟和取消语义；错误必须定位到 Scene/State/Track/Clip/Rule 路径。
- 覆盖死亡开花、假 Boss 受击和背景切换三个 fixture；验证事件描述事实而不是携带 `start_clip` 命令。

完成条件：Contract 在没有新 runtime 实现时形成红色预期；规则 round-trip、未来字段拒绝、边沿语义、重入/取消策略和 owner 诊断均有断言；不改生产代码来绕过红灯。

验收文件：`tests/test_reactive_timeline.py`、`tests/test_activation_rules.py`、`tests/test_timeline_instance_trace.py`。

### N4.1 Runtime：激活、实例、预算与取消

状态：`[ ]`。依赖 N4.0。

Agent 要做：

- 扩展可序列化 `ReactiveClip` 和 `ActivationRule`，接入 Scene → compiler → `StageProgram` → `StageRunner` 的正式路径；不建立编辑器专用模拟器。
- 在同一帧快照上计算变量、事件和生命周期规则，遵循 Inbox → 快照计算 → State 退出/取消优先 → 启动仍有效实例 → 采样轨道的顺序。
- 分离作者 Clip ID 与运行时 Instance ID；trace 至少记录 author clip、instance、trigger kind/source/event、激活快照、实际触发帧、owner、cancel token、开始/停止原因、并发数和预算拒绝原因。
- 实现 `on_rise`、`while_true`、`on_fall`、`on_change`；覆盖固定时间、事件、生命周期、变量条件和动态延迟。实例开始后变量变化不能把它回溯移动到过去。
- 实现固定持续时间、条件变假、收到事件、行为完成、State 退出、显式取消等停止原因；owner 退出传播到 TaskScope、pending reaction 和批量 Action。
- 约束最大实例数、每帧生成数、因果深度和预算；同帧批量事实不得扩展为 O(bullets) Python 对象链。

完成条件：N4.0 Contract 和 `tests/test_reaction_timeline_integration.py` 全绿；三类例子的 trace 能回答“为什么触发、何时开始、为什么停止、归谁所有”；reset+seek 与正常固定帧播放逐帧等价；作者文档序列化和 dirty 状态不变。

验收文件：N4.0 三份 Contract、`tests/test_reaction_timeline_integration.py`；回归 N2/N3 focused gate、`tests/test_reactions.py`、`tests/test_reaction_scheduler.py`、`tests/test_state_graph_runtime.py`、`tests/test_stage_program.py`。

### N4.2 Editor：生命周期槽位、条件徽标和运行时 overlay

状态：`[ ]`。依赖 N4.1。

Agent 要做：

- 在时间线显示固定片段、生命周期槽位、激活规则徽标、owner 和规则摘要；不把 Pattern 内部节点展开到 State Graph。
- 点击槽位只导航到对应 Reaction/Blueprint 资源或局部编辑面，保持状态图、时间线和行为图的领域视图边界；返回路径和当前选择可追踪。
- 用运行时只读 overlay 显示 instance、actual start frame、trigger、stop reason、owner、active count 和预算拒绝；overlay 更新不得改文档、稳定 UUID 或 dirty。
- 按 `target + property + variable` 分组显示冲突；诊断能跳回两个 writer、区间和 reducer。所有增删改通过 `CommandStack`，一个用户动作一个 Undo 事务。
- 完成真实 PySide6 时间线交互、reset/replay 和最小窗口检查；offscreen 结果只能作为 Structural/Runtime 证据。

完成条件：新手能在槽位上理解“何时有效”，高级作者能进入局部行为实现；没有蓝图长连线；运行时 overlay 可观察但不污染作者资源。

验收文件：`tests/test_editor_reactive_clips.py`、`tests/test_reaction_timeline_integration.py`；回归 `tests/test_editor_timeline_model.py`、`tests/test_editor_timeline_workspace.py`、`tests/test_state_graph_editor.py`；另附 native visual 证据。

## N5 — 可展开的版本化预设

**阶段目标**：预设优先于节点堆；参数、插槽、生命周期和 debug identity 稳定，展开是理解结构的连续入口，不是复制一坨脚本。

### N5.0 Contract：预设描述和迁移语义

状态：`[ ]`。阅读产品愿景第 11 节、`src/pattern` 资源/编译器、N4 规则和现有 pattern parity 测试。

Agent 要做：创建 `tests/test_preset_descriptor.py`、`tests/test_preset_expansion.py`、`tests/test_preset_migration.py`，冻结 stable preset ID/version、参数 schema、公开插槽、输入/输出变量、事件、虚拟内部 ID、覆盖优先级、精确版本锁和迁移失败语义。

完成条件：Contract 能验证未知字段/错误类型/缺失版本/循环迁移和稳定身份；预设实例不会因编辑器升级静默改变。

验收文件：上述三份 Contract。

### N5.1 预设库

状态：`[ ]`。依赖 N5.0。

Agent 要做：提供自机狙、奇数弹、偶数弹、圆形开花、扇形扫射、单/双/交错螺旋、加速旋转、延迟转向、子弹分裂、速度层叠、波纹和米弹墙；每个预设有少量有意义的参数、真实 fixture、生命周期策略和高密度性能预算。

完成条件：预设可通过正式 compiler/runner 运行，行为 parity 与基础 Pattern 资源一致，批量路径没有逐弹 Python 回调。

验收文件：`tests/test_preset_library.py`、`tests/test_pattern_parity.py`、`tests/test_pattern_compiler.py`；附固定 workload profile。

### N5.2 虚拟展开

状态：`[ ]`。依赖 N5.1。

Agent 要做：展开只读显示内部发射器、参数和局部行为；虚拟节点 ID 由实例 ID+预设内部 ID 稳定派生；折叠/展开不复制 Scene 节点、不制造新的 runtime 实例，trace 可从外部实例定位内部节点。

完成条件：折叠、展开、保存、重开和 reset 的 authoring/runtime identity 一致；虚拟展开不会产生第二份可漂移文档。

验收文件：`tests/test_preset_expansion.py`、`tests/test_editor_preset_workspace.py`、`tests/test_pattern_graph.py`。

### N5.3 参数覆盖与本地物化

状态：`[ ]`。依赖 N5.2。

Agent 要做：公开参数和插槽可覆盖；“展开为本地结构”是显式、可预览、可 Undo/Redo 的 CommandStack 事务；物化后与上游预设断开且不被升级偷偷改写；取消或失败保留原实例。

完成条件：覆盖优先级和差异报告可解释；物化、撤销、重做、运行和 trace 均可重放。

验收文件：`tests/test_preset_expansion.py`、`tests/test_editor_preset_workspace.py`、`tests/test_editor_authoring_integration.py`。

### N5.4 预设迁移

状态：`[ ]`。依赖 N5.3。

Agent 要做：按精确版本执行参数/插槽迁移，在临时副本生成差异和诊断；迁移失败保留原数据、原版本和定位路径；项目依赖锁定到可重放版本。

完成条件：成功迁移 round-trip；失败可恢复、可 Undo，不能用“最接近版本”静默替代。

验收文件：`tests/test_preset_migration.py`、`tests/test_preset_descriptor.py`、`tests/test_pattern_document.py`。

## N6 — 新手流程与上下文搜索（不包含自然语言）

**阶段目标**：新人从可运行骨架和预设开始，逐层进入曲线、变量、行为图和 Runtime；搜索代替巨大菜单，但每个结果仍是确定性的结构化 Command。

### N6.0 Contract：Action Catalog 与新手工作流

状态：`[ ]`。阅读产品愿景第 10、12、13 节和 N5 预设接口。

Agent 要做：创建 `tests/test_action_catalog.py`、`tests/test_contextual_search.py`、`tests/test_beginner_workflow.py`、`tests/test_editor_usability.py`；冻结 Descriptor→Catalog 的 schema、输入/输出类型、上下文过滤、排序、创建事务、空状态引导和错误定位。

完成条件：Contract 断言实际候选、类型端口、Command/Undo 和空状态，而不是菜单字符串；自然语言生成明确不在范围内。

验收文件：上述四份 Contract。

### N6.1 上下文感知搜索

状态：`[ ]`。依赖 N6.0。

Agent 要做：所有作者上下文按空格打开搜索；PointSet 拉线只显示接受 PointSet 的 Action；时间线只显示轨道/片段；场景画布只显示可创建对象；Catalog 来自 Descriptor，UI 不写死分支；轻按搜索与按住平移的冲突由原生 QA 冻结。

完成条件：无效候选不会出现，搜索结果可解释且稳定排序；创建和连接都经过文档 CommandStack。

验收文件：`tests/test_action_catalog.py`、`tests/test_contextual_search.py`、`tests/test_editor_graph_workspace.py`、`tests/test_editor_timeline_workspace.py`。

### N6.2 道中/关底新手骨架

状态：`[ ]`。依赖 N6.1。

Agent 要做：项目向导生成道中和两阶段 Boss 骨架（State、Timeline、Background、Pattern、音频和预览入口）；模板创建是一个可 Undo 的文档事务；缺资源、条件错误和 runtime error 定位到资源/属性/规则。

完成条件：新人无需理解事件队列、内部 ID 或插件注册即可完成首个 Pattern、清屏后续和背景转场。

验收文件：`tests/test_beginner_workflow.py`、`tests/test_editor_m3_integration.py`、`tests/test_editor_authoring_integration.py`、`tests/test_editor_timeline_workspace.py`。

### N6.3 分层展开与连续编辑

状态：`[ ]`。依赖 N6.2。

Agent 要做：固定 L0 预设卡片→L1 参数→L2 曲线/变量/表达式→L3 行为图→L4 Runtime 源码的入口、返回和权限提示；所有层级共享同一生命周期、类型、owner 和 debug identity；局部替换不要求推倒重写。

完成条件：从调参数到局部实现是连续操作，折叠/展开不复制资源，不产生第二套 runtime。

验收文件：`tests/test_beginner_workflow.py`、`tests/test_editor_graph_workspace.py`、`tests/test_editor_preset_workspace.py`、`tests/test_editor_usability.py`。

### N6.4 Usability gate

状态：`[ ]`。依赖 N6.3。

Agent 要做：邀请至少 5 名没有 PySTG 经验的目标用户，记录首个 Pattern、清屏后续、两阶段 Boss+背景切换、撤销/重开/预览和一次局部展开的时间、失败点和求助次数；维护者不能口头带做。

完成条件：至少 4/5 用户在 10 分钟内完成可运行 Pattern，30 分钟内完成短道中，60 分钟内完成两阶段 Boss、一次背景转场和一次事件反应，全程不写脚本；报告与自动测试分开保存。

验收文件：`tests/test_editor_usability.py`、N6 focused gate、真实 PySide6 窗口截图和人工 Usability 报告。

## N7 — Behavior Descriptor 与 Safe/Runtime/Engine 权限分区

**阶段目标**：一个版本化 Descriptor 同时服务 schema、runtime 和 Tool；普通作者只看到授权能力，玩法开发者可以扩展行为，引擎开发者不把内部接口泄漏给普通项目。

### N7.0 Contract

状态：`[ ]`。阅读产品愿景第 5、14、15 节、插件 SDK、资源 registry 和 N6 Catalog。

Agent 要做：创建 `tests/test_behavior_descriptor.py`、`tests/test_safe_capabilities.py`、`tests/test_plugin_package_boundaries.py`、`tests/test_behavior_plugin_integration.py`，冻结 stable ID/version、typed ports、参数 schema、capabilities、lifecycle/cancel、debug snapshot、Tool contribution 和 manifest 错误。

完成条件：Contract 能在 headless runtime 中拒绝越权，并验证同一 Descriptor 的 schema/runtime/tool 身份一致。

### N7.1 Safe API

状态：`[ ]`。依赖 N7.0。

Agent 要做：只开放批量发射、授权移动、资源播放、只读 snapshot、等待类型事件和局部变量；不返回 Pool/Renderer/Manager，不允许文件、网络、进程或模块访问。进程内 Python 明确属于 Runtime；未来若需要非受信代码，另立独立 IPC 沙箱项目。

完成条件：静态 manifest 和运行时能力检查都拒绝越权；Safe 行为可热重载、可取消、可 debug，不因隐藏 `ctx` 而冒充安全沙箱。

验收文件：`tests/test_safe_capabilities.py`、`tests/test_behavior_descriptor.py`、`tests/test_editor_regression_contracts.py`。

### N7.2 Runtime API

状态：`[ ]`。依赖 N7.1。

Agent 要做：允许注册组件、事件、弹道、碰撞、道具和受限 Renderer Pass；声明线程、所有权、清理和 replay policy；禁止逐弹回调、任意全局状态和未声明输出。

完成条件：Runtime 插件可服务 N4/N5 行为，失败和取消可追踪，headless 不导入 Qt。

验收文件：`tests/test_behavior_plugin_integration.py`、`tests/test_plugin_sdk.py`、`tests/test_safe_capabilities.py`。

### N7.3 Engine API

状态：`[ ]`。依赖 N7.2。

Agent 要做：为调度器、渲染后端、资源类型、编辑器插件和编译器节点提供内部扩展点；明确版本迁移和普通项目不可依赖的边界；不把 Engine API 作为内容作者入口。

完成条件：Engine 扩展可演进，普通项目 schema/Runtime 契约不因内部改动而隐式变化。

验收文件：`tests/test_plugin_package_boundaries.py`、`tests/test_behavior_descriptor.py`、`tests/test_editor_regression_contracts.py`。

### N7.4 分区包、依赖锁和加载回滚

状态：`[ ]`。依赖 N7.3。

Agent 要做：将 manifest、dependency lock、schema/migration、runtime/compiler、tool、assets/examples/presets 分区；加载、热重载、回滚和卸载是事务；Tool 按需加载，headless 不导入 Qt，Runtime 失败清理所有 owner/lease。

完成条件：缺依赖、未知 capability、迁移失败和卸载中异常都有结构化诊断且不污染文档或进程。

验收文件：`tests/test_plugin_package_boundaries.py`、`tests/test_plugin_sdk.py`、`tests/test_behavior_plugin_integration.py`。

### N7.5 ComplexMapEmitter 示范插件

状态：`[ ]`。依赖 N7.4。

Agent 要做：实现真实 `ComplexMapEmitter`，暴露采样域、函数（如 `z²+c`）、采样数、位置映射、颜色、Inspector、画布控制柄、预览和 debug snapshot；普通作者只调参数，高级作者可定位源码。

完成条件：同一实例在 Content、Runtime、Tool 和 debug trace 中 identity 一致；源码扩展不要求普通作者进入 Engine API。

验收文件：`tests/test_behavior_plugin_integration.py`、`tests/test_plugin_sdk.py`、`tests/test_editor_authoring_integration.py`；另附正式预览 native visual parity。

## N8 — Renderer Pass 与 Render Graph

**阶段目标**：Runtime Pass 通过后端中立 IR 和受限上下文进入正式 Render Graph；Tool 复用 Descriptor，不另做 Qt 假渲染。

### N8.0 Contract

状态：`[ ]`。创建 `tests/test_render_graph.py`、`tests/test_renderer_pass_plugins.py`、`tests/test_render_graph_backend.py`、`tests/test_renderer_pass_editor.py`，冻结 attachment、格式/尺寸/sample、依赖、hazard、resource lease、fallback 和错误定位。

### N8.1 PassDescriptor 与编译器

状态：`[ ]`。依赖 N8.0。

Agent 要做：定义后端中立 `PassDescriptor`、输入/输出 attachment、load/store、参数 schema、合并和生命周期；编译期拒绝环、未初始化读取、格式冲突和 capability 不足；IR 不携带 ModernGL 对象。

完成条件：Pass 顺序、资源依赖和失败路径可序列化、可诊断、可重放。

验收文件：`tests/test_render_graph.py`、`tests/test_render_graph_backend.py`。

### N8.2 受限 PassContext 与资源 lease

状态：`[ ]`。依赖 N8.1。

Agent 要做：Runtime 插件只获得 scoped `PassContext`、`CommandEncoder` 和 resource lease；不能取得全局 GL state、持有过期资源或跨 owner 释放资源；热卸载必须结束 lease。

完成条件：越权、跨帧资源和清理错误均显式失败，不靠静默替代。

验收文件：`tests/test_renderer_pass_plugins.py`、`tests/test_render_graph.py`。

### N8.3 ModernGL backend adapter

状态：`[ ]`。依赖 N8.2。

Agent 要做：接入当前正式 ModernGL/GLFW 路径；后端 adapter 将 IR 转成命令；缺能力时仅在 Descriptor 明确允许且语义可接受时 pass-through/替代，否则在编译/导出阶段报错；验证热重载和资源释放。

完成条件：正式 surface 的输出与资源生命周期可追踪；嵌入式/后台路径 parity 通过，Qt 预览不能冒充 renderer 证据。

验收文件：`tests/test_render_graph_backend.py`、`tests/test_renderer_pass_plugins.py`、`tests/test_background_data_driven_parity.py`；附 GLFW/ModernGL native 证据。

### N8.4 Tool/Runtime parity

状态：`[ ]`。依赖 N8.3。

Agent 要做：Tool 复用同一 Descriptor 提供 Inspector、控制柄和缩略预览；缺 Tool contribution 时退化为通用 Inspector；不得另建与正式 Render Graph 不同的效果实现。

完成条件：编辑器参数、正式 renderer 和 debug snapshot 对同一实例保持一致。

验收文件：`tests/test_renderer_pass_editor.py`、`tests/test_editor_authoring_integration.py`、`tests/test_render_graph_backend.py`。

## N9 — 分层调试、确定性重放、性能与发布

**阶段目标**：任何“没触发/被取消/有冲突/seek 不一致/性能超预算”都能在同一套 trace 中定位；最终作者工作流不依赖 offscreen 或 `--help` 伪验收。

### N9.0 Contract

状态：`[ ]`。创建 `tests/test_editor_debugger.py`、`tests/test_replay_determinism.py`、`tests/test_runtime_profile.py`、`tests/test_editor_next_acceptance.py`，先冻结 trace 协议版本和 release workload。

### N9.1 统一 trace 与 why-not 调试器

状态：`[ ]`。依赖 N9.0。

Agent 要做：记录 author resource ID、runtime instance ID、owner/cancel token、State path、Clip/Reaction、事件因果、变量读写、生成数、batch 摘要、CPU/GPU、诊断和版本；调试器显示 Stage/State/frame、激活条件、事件、预算，并支持 pause/step/seek/reset 和 why-not。

完成条件：能回答谁写/谁读、为何未触发、为何取消、为何冲突，并可从 trace 跳回资源/属性/行为节点；不向作者文档写 overlay。

验收文件：`tests/test_editor_debugger.py`、`tests/test_editor_next_acceptance.py`、N4/N7 回归。

### N9.2 确定性 replay/seek

状态：`[ ]`。依赖 N9.1。

Agent 要做：将 seed、外部输入、资源/插件版本、初始变量和副作用 policy 纳入 replay identity；seek 只能 reset+固定帧重放，若加入检查点必须证明逐帧等价并可回退；未记录的外部输入标记为不可复现。

完成条件：同一 identity 的正常播放、reset、seek、热重载兼容路径 trace 逐帧一致；差异能定位到输入、版本、规则或资源。

验收文件：`tests/test_replay_determinism.py`、`tests/test_variable_seek.py`、`tests/test_variable_hotreload.py`、`tests/test_preview_process.py`。

### N9.3 性能 profile 与预算

状态：`[ ]`。依赖 N9.2。

Agent 要做：在明确 Windows 目标硬件上测高密度 Pattern、batch lifecycle、Reaction、复杂 State/Timeline、ComplexMap、Render Graph 和长 seek；固定 workload、时间/内存/批量阈值、首次编译是否计入和报告格式；不得用平均数掩盖峰值。

完成条件：预算随 trace、导出 profile 和诊断记录；超预算阻止发布或给出明确降级，不静默删效果。

验收文件：`tests/test_runtime_profile.py`、`tests/test_replay_determinism.py`、N3 batch tests、N8 backend tests；附目标硬件 Performance 报告。

### N9.4 最终作者工作流

状态：`[ ]`。依赖 N9.3。

Agent 要做：从模板完成短道中和两阶段 Boss，包含全灭后续、假 Boss 受击反击、死亡开花、背景切场、Runtime Behavior 和 Renderer Pass；保存、重开、Undo/Redo、热重载、seek、预览和导出均走正式路径。

完成条件：顶层作者无需接触 Engine API；高级作者能从可视结构进入源码；所有实例和钩子可在调试器定位。

验收文件：`tests/test_editor_next_acceptance.py`、`tests/test_editor_authoring_integration.py`、`tests/test_preview_process.py`、`tests/test_preview_editor_integration.py`、N4–N8 focused gate；附 native visual 和人工 workflow 报告。

### N9.5 发布门禁

状态：`[ ]`。依赖 N9.4。

Agent 要做：在同一 checkout 产生完整 tests、compileall、assets、diff、主游戏、Pattern/Stage preview、PySide6 窗口、正式 renderer、恢复、插件卸载和 profile 报告；明确 Structural/Runtime/Performance/Native visual/Usability 各自结论。

完成条件：所有阶段停止条件关闭，所有 focused gate、迁移、性能、原生窗口和人工可用性证据齐全后，才允许把本路线图标为完成。offscreen、`--help` 或单一“全绿”数字不能替代发布门禁。

验收文件：N2–N9 全部 focused 文件、`tests/test_preview_process.py`、`tests/test_preview_editor_integration.py`、`tests/test_editor_authoring_integration.py`、`tests/test_editor_next_acceptance.py`，以及发布报告。

## 5. 完成记录规则

- 每个子任务完成后只修改对应 `[ ]` 为 `[x]`，并在该任务末尾追加一段 Evidence；不得重写已冻结基线、创建 `*_TODO_v2.md` 或新增完成日志副本。
- Evidence 必须写可复制命令、通过数量或报告路径、Python/Qt/硬件环境，并明确 Structural/Runtime/Performance/Native visual/Usability 哪些仍缺失。
- focused gate、迁移、性能或原生证据缺失时保持 `[ ]`；不得通过删测试、放宽断言、吞异常或把运行时状态写回文档来“完成”任务。
