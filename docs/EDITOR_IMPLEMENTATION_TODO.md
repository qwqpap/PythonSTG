# PySTG 下一代编辑器实施 TODO

> 状态：Active；本文是仓库中唯一的未来实施清单，也是 Agent 的交接协议。
> 产品依据：[EDITOR_PRODUCT_VISION.md](EDITOR_PRODUCT_VISION.md)  v0.3
> 工程边界：[EDITOR_ARCHITECTURE.md](EDITOR_ARCHITECTURE.md)
> 建立：2026-08-09；最近整理：2026-08-09

## 0. 文档边界与已冻结基线

这份文件只保留尚未完成的工作。旧路线图和 N0/N1 的长篇完成日志已经从工作协议中移除；它们的提交历史仍可从 Git 查阅，但不能重新变成 Agent 的任务清单。N0 的资源/编辑器基线清理和 N1 的 `SceneDocument` 内嵌状态图已经验收，后续 Agent 从 N2 开始，不能因某个 UI 容易演示而跳过依赖。

每个任务都使用稳定的 `N<阶段>.<编号>` ID。Agent 只能领取当前依赖链上最早的未完成 ID；“看起来已经有代码”不等于任务完成，必须以该 ID 列出的行为测试和证据门禁为准。

以下决定已冻结，改变它们必须先修改产品愿景并得到维护者确认：

- 短期不做自然语言或 Agentic 弹幕生成。弹幕参数要精确、可复现；上下文搜索和预设是确定性的编辑入口。
- 系统同时有两条正交的轴：Content（数据和标准组件）、Behavior（协程/事件/脚本的生命周期）和 Tool（编辑器插件），以及 Safe API、Runtime API、Engine API 三层信任边界。
- 状态图回答“现在是哪一个阶段”；时间线回答“该阶段何时启动、持续和停止哪些生命周期”；行为图/脚本回答“一个行为内部如何运行”。三者只能通过类型化变量、事件、资源引用和生命周期所有权交流，不能互持 Qt 对象、运行时对象或 Clip ID。
- 时间线中的条件内容是一个可触发生命周期（`ReactiveClip`/`ActivationRule`），不是把所有条件拆成连线。变量快照和事件由运行时提供，反应解析器决定是否创建实例；实例创建后仍由时间线负责其生命周期。
- 事件采用本帧 Outbox、下一固定帧 Inbox；同一次 dispatch 不重入。高密度子弹和生命周期事件必须批量化，不得为每颗子弹创建场景节点或 Python 回调。
- 作者文档是唯一真源；运行时变量、事件和实例不能写回作者文档或制造 dirty。seek 的正确性是 reset 后从作用域入口按固定帧重放；检查点只能是透明优化。
- 拖动时间轴“从头重放到目标帧”的结构性问题暂不在本清单解决；本清单只冻结确定性语义和可观察 overlay。

### 当前依赖顺序

| 阶段 | 状态 | 依赖 | 本阶段完成后必须存在 |
| --- | --- | --- | --- |
| N2 类型化变量、作用域、单一写入者 | 已完成（N2.0–N2.7） | N1 | v4 声明、运行时 store、写权限和只读 overlay |
| N3 帧边界事件、生命周期和反应 | 已完成（N3.0–N3.3） | N2 | Inbox/Outbox、`LifecycleEvent`、`ReactionSpec`、`TaskScope` |
| N4 响应式时间线与蓝图边界 | 未开始 | N3 | `ReactiveClip`、激活规则、实例 trace、冲突可视化 |
| N5 可展开的版本化预设 | 未开始 | N4 | 参数/插槽覆盖、虚拟展开、本地物化和迁移 |
| N6 新手流程与上下文搜索 | 未开始 | N5 | 阶段骨架、首发预设库、Action Catalog、可用性证据 |
| N7 Behavior Descriptor 与权限分区 | 未开始 | N6 | Safe/Runtime/Engine 能力边界和分区插件包 |
| N8 Renderer Pass 与 Render Graph | 未开始 | N7 | 后端中立 PassDescriptor 和受限渲染上下文 |
| N9 调试、重放、性能与发布 | 未开始 | N8 | 统一调试器、确定性 seek、profile 和最终工作流验收 |

## 1. 每个 Agent 必须遵守的执行协议

每个编号任务都必须按以下顺序执行，并在交付说明中明确本次任务的编号和边界：

1. **Read**：完整阅读该任务列出的文件、产品愿景对应章节、本文公共规则；先运行 `git status --short`，保护工作树中不属于本任务的改动。
2. **Audit**：运行该任务已有的回归，查看真实 compiler/runner/document 行为、schema 版本和迁移路径；不能从 TODO 推测代码现状。
3. **Contract**：先建立或补强列出的验收测试。测试必须有可观察断言、真实 fixture 和错误边界；禁止只有 import、源码字符串、空 `pass`、宽泛 `except`、`skip` 或 `xfail`。Contract 先形成红色预期，再实现。
4. **Implement**：只改允许范围，使 Contract 测试逐步变绿。不得在实现 diff 中削弱断言、提高容错到吞错、替换正式 runtime 为第二套模拟器，或把 UI 状态写回文档。
5. **Verify**：运行 focused tests、完整回归、`compileall`、资源校验和 `git diff --check`。需要 native visual、Performance 或 Usability 的任务必须分别取得对应证据，不能用 offscreen Qt 代替。
6. **Record**：只更新本任务的复选框和一段可复现 Evidence（命令、结果、环境、剩余限制）；不要把聊天记录或整段测试日志粘回本文。

以下任一情况出现时立即停止扩大范围并报告：契约与产品愿景冲突；schema 变化没有无损迁移；必须逐弹回调/第二套预览/静默 fallback/绕过 Undo 才能实现；focused gate 仍为红色却要开始下一阶段；native、性能或用户门槛无法在当前环境提供；或用户改动与计划修改无法安全合并。

### 1.1 Agent 交付卡（每个编号任务必须填写）

每次 Agent 交付必须在提交说明或交接消息中逐项给出以下内容，不能只说“实现了”：

| 字段 | 必须写明 |
| --- | --- |
| Task ID / 边界 | 本次只处理哪些 `N<阶段>.<编号>`，明确不处理哪些相邻任务 |
| Read / Audit | 实际阅读的产品章节、源码入口、schema/fixture 和现有测试；`git status --short` 结果 |
| Contract | 新增或扩展的验收测试、真实 fixture、预期红色基线；不得只测 import 或源码字符串 |
| Implementation | 修改的 authoring/compiler/runtime/editor 文件，以及生命周期、所有权和错误路径 |
| Verification | focused、全量、compileall、资源校验、diff-check；额外的 native/performance/usability 命令 |
| Evidence / Blocker | 通过数量、环境、报告路径和仍缺的证据；有阻塞时保持 `[ ]` 并说明下一步 |

Contract 测试一旦形成红色基线，后续实现不得编辑断言、添加 `skip`/`xfail`、吞掉异常、替换正式运行时或把运行时反馈写回作者文档。若契约确实错误，必须先停止并由维护者批准独立的 contract-revision 提交。

## 2. 通用验收门禁

每个阶段的 focused command 之外，必须执行：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q main.py src game_content tools tests
python tools/validate_assets.py --format json
git diff --check
```

需要原生窗口的阶段还要实际启动 `python tools/scene_editor.py`、正式预览入口和 `python main.py`，使用真实样例完成交互；`--help` 只能证明参数注册，不能证明预览完成。自动环境不能显示窗口时，任务保持未完成，并在 Evidence 中留下 native gate。

证据类型必须分开记录：Structural（schema/命令/序列化）、Runtime（正式 compiler/runner/preview）、Performance（固定环境和 workload）、Native visual（真实 PySide6/GLFW/ModernGL 窗口）和 Usability（未接触 PySTG 的目标用户）。一种证据不能替代另一种。

### 2.1 阶段 focused gate 索引

下面的命令是阶段门禁的最小入口；任务正文列出的新增 Contract 文件必须和对应回归一起执行。没有列出的测试不能被 Agent 自行宣布为替代门禁。

| 阶段 | focused gate（PowerShell） | 额外证据 |
| --- | --- | --- |
| N2 | `python -m pytest -q tests/test_typed_variables.py tests/test_variable_runtime.py tests/test_variable_editor.py tests/test_state_graph_document.py tests/test_state_graph_runtime.py tests/test_stage_program.py tests/test_scene_v4_contract.py tests/test_variable_scopes_and_reducers.py tests/test_variable_editor_native.py tests/test_variable_seek.py tests/test_variable_hotreload.py tests/test_replay_determinism.py` | N2.6 原生窗口；N2.7 replay identity/seek trace |
| N3 | `python -m pytest -q tests/test_lifecycle_events.py tests/test_frame_boundary_events.py tests/test_task_scopes.py tests/test_lifecycle_batching.py tests/test_reactions.py tests/test_reaction_scheduler.py tests/test_lifecycle_timeline_hooks.py tests/test_background_reactions.py` | 正式 Stage/Pattern runtime trace；高密度批处理 profile |
| N4 | `python -m pytest -q tests/test_reactive_timeline.py tests/test_activation_rules.py tests/test_timeline_instance_trace.py tests/test_reaction_timeline_integration.py tests/test_editor_reactive_clips.py` | 时间线原生交互和 reset/replay 等价性 |
| N5 | `python -m pytest -q tests/test_preset_descriptor.py tests/test_preset_expansion.py tests/test_preset_migration.py tests/test_preset_library.py tests/test_editor_preset_workspace.py` | 预设 workload profile；Undo/Redo/物化 trace |
| N6 | `python -m pytest -q tests/test_action_catalog.py tests/test_contextual_search.py tests/test_beginner_workflow.py tests/test_editor_usability.py` | 原生窗口和至少 4/5 新用户 Usability 记录 |
| N7 | `python -m pytest -q tests/test_behavior_descriptor.py tests/test_safe_capabilities.py tests/test_plugin_package_boundaries.py tests/test_behavior_plugin_integration.py tests/test_plugin_sdk.py` | headless 不导入 Qt；正式预览中的 Runtime/Tool parity |
| N8 | `python -m pytest -q tests/test_render_graph.py tests/test_renderer_pass_plugins.py tests/test_render_graph_backend.py tests/test_renderer_pass_editor.py` | GLFW/ModernGL surface、热卸载和资源释放 |
| N9 | `python -m pytest -q tests/test_editor_debugger.py tests/test_replay_determinism.py tests/test_runtime_profile.py tests/test_editor_next_acceptance.py` | 目标 Windows 硬件 profile、原生窗口、完整工作流和发布报告 |

新增 Contract 文件只在对应 Agent 开始时创建；不要预先提交空文件，也不要把当前不存在的文件加入“已通过”证据。

## 3. 测试清理规则

历史清理已经删除只服务交接流程的旧测试：`tests/test_m4_runtime_preview_contract.py`、`tests/test_stage1_opening_media.py`、`tests/test_bottom_layer_smoke.py`，并将原 `tests/test_luna_acceptance_bundle.py`、`tests/test_m5_m7_remediation_gate.py` 改成行为覆盖文件 `tests/test_editor_authoring_integration.py`、`tests/test_editor_regression_contracts.py`。它们不应被重新添加。

同一轮整理删除了 `test_declared_runtime_versions_match_the_active_acceptance_environment`：它只比较当前机器的 NumPy/Numba 版本，不验证 PySTG 行为，环境锁定应由发布/CI 负责。`test_public_editor_uses_pyside6_not_pyqt5` 等加载边界测试仍保留，因为它们验证公开入口的依赖边界。

当前没有其他可安全删除的测试：`test_editor_app_smoke.py` 虽然名字含 smoke，但验证真实窗口命令、Undo 和正式预览入口；`test_editor_m3/m4/m5/m6_integration.py` 与 `test_editor_m6_workspace.py` 验证资源保存、编译、运行、UI/背景或 Qt 崩溃回归；Pattern/Stage/UI/背景/事件/插件测试均有可观察行为断言。删除这些会降低真实覆盖，违反本清单的“不得为了变绿删除公共行为测试”规则。

本次整理基线（2026-08-09）：完整 suite `533` 项通过；N2 focused gate `56` 项通过；`python -m compileall -q main.py src game_content tools tests`、`python tools/validate_assets.py --format json`（73 JSON、16 sprite configs、745 sprites、142 images，0 errors/0 warnings）和 `git diff --check` 通过。N2.6 另有真实 PySide6 窗口证据：`build/visual_qa_native_qt_1480x920_final.png` 与 `build/visual_qa_native_qt_960x640_final.png`；后者在最小窗口自动将 Bottom Panel 收缩到 80px，Variables dock 仍显示 Apply、表格水平滚动条、runtime overlay、Delete、Bind 和 Map。证据只覆盖 N2 的 Structural/Runtime/Native visual 门禁，不替代后续 Performance 或 Usability gate。

---

## N2 — 类型化变量、作用域与单一写入者（当前阶段；N2.0/N2.1 为冻结基线）

N2.0 和 N2.1 只作为已验收契约供后续 Agent 阅读，不再领取或重复实现；N2.0–N2.7 已全部固定，后续 Agent 从 N3 开始。

### N2.0 Contract：先冻结公共语义

状态：`[x]` 第一版 Contract 已建立；补充断言仍必须先于实现。

**Agent 要读**：产品愿景第 7.1、7.5、7.7、18.3 节；`src/authoring/resources.py`、`src/authoring/migrations.py`、`src/editor/document.py`、`src/editor/stage_compile.py`、`src/game/stage/program.py`、`src/pattern/bindings.py` 和现有 N1 测试。

**Agent 要做/交付**：在实现前固定 JSON 类型表示、变量引用格式、作用域 owner、读写者、`set/add/toggle/reset`、Engine Snapshot 只读、单一写入者诊断和运行时 snapshot 的断言。错误必须指出 Scene/State/Track/Clip/Variable 路径。

**验收文件**：`tests/test_typed_variables.py`、`tests/test_variable_runtime.py`、`tests/test_variable_editor.py`。这些文件已包含第一版真实断言；后续扩展仍须保持契约先行。

**完成条件**：测试能在没有 Qt 的 headless runtime 中证明声明和权限，在真实 `compile_stage + StageRunner` 路径中证明写入、reset 和 snapshot；不能只测类是否存在。

### N2.1 类型注册与声明

状态：`[x]` 首批类型、声明、引用和插件 normalizer 已有实现；保持 headless 边界和未知字段测试。

**Agent 要做**：完善 `VariableSpec`、`VariableRef`、`VariableOutputMapping` 和 `VariableTypeRegistry`；首批类型为 `bool/int/float/string/vector2/color/resource/complex`，`complex` 只能用 `{real, imag}` JSON。插件类型必须提供 JSON normalizer，拒绝 NaN、Python 对象、cwd 资源引用和未知字段。声明的 `readers`、`writable_by`、`animatable`、`reducer`、`record_in_replay` 必须经过同一验证器。

**验收文件**：`tests/test_typed_variables.py`、`tests/test_authoring_resources.py`、`tests/test_pattern_bindings.py`（若新增绑定类型测试）。

**完成条件**：JSON dump/load round-trip 后值和 UUID 不变；非法值在 authoring 边界被拒绝；自定义类型调用自身 normalizer；类型系统不导入 Qt、Renderer 或游戏对象。

### N2.2 Scene v3→v4 迁移

状态：`[x]` canonical v4 loader、显式迁移、兼容 shim 边界和未来版本拒绝已完成；旧 timeline ID/metadata 保持不变。

**Agent 要做**：为 Scene 顶层和每个 State 增加变量声明/输出映射；v3 迁移新增空容器，不改变旧 timeline、Track/Clip/Keyframe ID 和 metadata；提供未来版本拒绝、未知字段策略、rootless 兼容和显式 canonical v4 loader。逐步移除当前仅为旧 N1 断言保留的兼容 shim，但不得修改冻结 N1 行为断言，需先提出单独迁移契约。

**验收文件**：`tests/test_scene_v4_contract.py`、`tests/test_typed_variables.py`、`tests/test_state_graph_document.py`、`tests/test_editor_documents.py`、`docs/schemas/pystg-scene-v3.schema.json`、`docs/schemas/pystg-scene-v4.schema.json`、`docs/schemas/fixtures/scene-v3.pystg.json`、`docs/schemas/fixtures/scene-v4.pystg.json`。

**完成条件**：v3 fixture 可加载；显式迁移得到 v4；v4 fixture 通过 jsonschema 并可 round-trip；旧 timeline 行为逐项相等；schema 未来版本以结构化错误拒绝。

**Evidence（2026-08-09）**：`tests/test_scene_v4_contract.py`、`tests/test_typed_variables.py`、`tests/test_state_graph_document.py`、`tests/test_editor_documents.py` 通过；canonical round-trip、未知顶层字段、future schema version、rootless/legacy wire 兼容均走真实 `SceneDocument`/schema 路径。

### N2.3 运行时作用域和生命周期

状态：`[x]` project/stage/state/clip/reaction/behavior/engine_snapshot store、owner 生命周期和正式 Stage/Pattern runner 接线已完成。

**Agent 要做**：实现 project/stage/state/clip/reaction/behavior/engine_snapshot 的独立 store；State 进入创建、退出销毁，Stage reset 重建，Clip/Reaction/Behavior 运行实例有 owner 和取消路径；跨 State 只通过 Stage 或显式 output mapping。Pattern/行为绑定只能通过 `VariableRef` 读取，不能抓取另一个领域的内部对象。

**验收文件**：`tests/test_variable_scopes_and_reducers.py`、`tests/test_variable_runtime.py`、`tests/test_state_graph_runtime.py`、`tests/test_stage_program.py`、`tests/test_pattern_runtime.py`。

**完成条件**：同名变量在不同 scope 不串值；State 退出后局部读写失败；重置后默认值和写入 trace 清空；正式 StageRunner 和 PatternRunner 共享同一变量协议。

**Evidence（2026-08-09）**：`tests/test_variable_scopes_and_reducers.py`、`tests/test_variable_runtime.py`、`tests/test_state_graph_runtime.py`、`tests/test_stage_program.py`、`tests/test_pattern_runtime.py` 通过；scope owner 创建/销毁、active owner、behavior output 和 reset 清理均由正式 store/runner 断言。

### N2.4 写权限和输出映射

状态：`[x]` Safe Action、Timeline、Behavior output mapping 和 Engine Snapshot 只读边界已接入 compiler/runner；越权与类型不兼容会结构化失败。

**Agent 要做**：将 Safe Action、Timeline automation、Behavior output 和 Engine Snapshot publish 接到正式 compiler/runner；静态检查 writer 是否被声明、Timeline 是否 animatable、Behavior 是否是 descriptor 输出、mapping source/target 类型是否兼容。运行时对越权写入报结构化错误，不能靠 fallback 写入。

**验收文件**：`tests/test_variable_runtime.py`、`tests/test_variable_scopes_and_reducers.py`、`tests/test_stage_program.py`、`tests/test_pattern_bindings.py`、`tests/test_editor_regression_contracts.py`。

**完成条件**：Engine Snapshot 对内容只读；Safe Action 只允许声明操作；Behavior 只能发布声明输出并通过 mapping 写入目标；所有错误包含 writer、scope、variable 和 owner。

**Evidence（2026-08-09）**：`tests/test_variable_runtime.py`、`tests/test_variable_scopes_and_reducers.py`、`tests/test_stage_program.py`、`tests/test_pattern_bindings.py`、`tests/test_editor_regression_contracts.py` 通过；mapping source/target、operation、owner 和 writer 权限均在 compile/runtime 错误路径验证。

### N2.5 单一写入者与 reducer

状态：`[x]` compile-time overlap 诊断、legacy last-wins 标记和 deterministic numeric/vector2/complex reducer 已完成；编辑器专用诊断视图留给后续 N4/N6。

**Agent 要做**：编译期按 `scope + name + active interval` 分组写入者；新内容的重叠写入必须选择有序 `override` 或类型支持的 `add/multiply/blend`；迁移来的旧内容显式标记 `legacy_last_wins`。实现 reducer 的运行时合并、数值/向量/复数类型检查、冲突可视化数据，不增加逐帧 Python 回调。

**验收文件**：`tests/test_variable_scopes_and_reducers.py`、`tests/test_variable_runtime.py`、`tests/test_state_graph_runtime.py`；后续若拆分 conflict/reducer/diagnostic UI 契约，应新增独立文件而不是删除现有行为覆盖。

**完成条件**：无 reducer 的重叠写入在 compile 阶段失败；显式 reducer 的结果在固定顺序下确定；诊断能定位两个 writer；高密度场景的变量写入仍是批量/稀疏路径。

**Evidence（2026-08-09）**：N2 focused gate 中 56 项通过；`test_stage_compiler_applies_declared_reducer_in_fixed_track_order` 验证正式 compiler/StageRunner，冲突诊断包含两个 writer、路径和区间；未新增逐弹 Python 回调。

### N2.6 编辑器变量面板和只读 overlay

状态：`[x]` 文档命令、类型化属性、mapping API、候选过滤、只读 overlay 和原生 PySide6 窗口门禁已完成。

**Agent 要做**：把变量声明、类型化默认值、scope、writer、reader、animatable、reducer 和 output mapping 编辑接入当前 `CommandStack`；提供可搜索的绑定选择器，候选只来自兼容类型/作用域/owner，并把 mapping 对话框的增删改作为一个 Undo 事务提交；完成绑定选择/搜索和冲突定位；运行值、写入者、frame 只在只读 overlay 显示，不修改 document 或 dirty 状态。补齐 native PySide6 窗口在 1480×920 与 960×640 的布局检查。

**验收文件**：`tests/test_variable_editor.py`、新增 `tests/test_variable_editor_native.py`、`tests/test_editor_app_smoke.py`、`tests/test_editor_authoring_integration.py`。

**完成条件**：添加/编辑/删除/绑定全部可 Undo/Redo 且稳定 UUID 不变；runtime overlay 变化不改变序列化结果；绑定搜索只显示兼容类型/作用域；真实窗口可读、无控件重叠，最小窗口保留表格水平滚动和 overlay/Bind 入口，offscreen 结果不能冒充 native visual。

**Evidence（2026-08-09）**：`tests/test_variable_editor.py`、`tests/test_variable_editor_native.py`、`tests/test_editor_app_smoke.py`、`tests/test_editor_authoring_integration.py` 的 headless/offscreen 行为通过；N2 focused gate `56 passed`，完整 suite `533 passed`。变量面板的 Bind 入口打开 `VariableBindingDialog`，Map 入口打开 `VariableMappingDialog`；映射增删改通过 `CommandStack` 的单一 `Edit output mappings` 事务提交，取消或未解析引用不会静默删除作者数据。真实 PySide6 `EditorMainWindow` 在 1480×920 和 960×640 均完成布局检查，证据文件为 `build/visual_qa_native_qt_1480x920_final.png`、`build/visual_qa_native_qt_960x640_final.png`；960×640 时 Bottom Panel 自适应为 80px，Variables dock 的字段、Apply、表格水平滚动条、runtime overlay、Delete、Bind、Map 均可见且无控件重叠。测试环境为 Windows/PySide6，截图由正式 `create_window(ProjectContext)` 路径生成。

### N2.7 热重载与 seek

状态：`[x]` compatibility key、兼容值恢复/丢弃决定、Stage/Pattern seek 和 replay identity 已接入；外部副作用仍按 dispatch policy 抑制。

**Agent 要做**：定义变量声明变化的 compatibility key（name/type/scope/owner）；不兼容时丢弃局部运行值并从入口重放，兼容时也必须记录迁移决定；记录初始变量、资源版本、随机种子和实际触发帧。补充 StageRunner 的 Stage/State/Clip 层 reset/seek API，以及 PatternRunner 的 Clip 层别名；每层仍通过正式 fixed-tick runner 重放，不建立第二套预览模拟器。

**验收文件**：新增 `tests/test_variable_hotreload.py`、`tests/test_variable_seek.py`、`tests/test_replay_determinism.py`；回归 `tests/test_devtools_hotreload.py`、`tests/test_preview_process.py`。

**完成条件**：同一输入和 seed 的 reset+seek 与正常播放逐帧相等；改名/改类型/改 scope 不会猜测旧值；旧 preview 进程不会把 overlay 写回 authoring document；测试覆盖 stop、restart、State transition 和 hot reload。

**Evidence（2026-08-09）**：`tests/test_variable_hotreload.py`、`tests/test_variable_seek.py`、`tests/test_replay_determinism.py`、`tests/test_devtools_hotreload.py`、`tests/test_preview_process.py` 通过；`test_state_and_clip_seek_replay_through_the_same_formal_runner` 覆盖 StageRunner 的 State/Clip 入口，PatternRunner 保持同一 fixed-tick `seek` 并提供 `seek_clip`/`reset_clip` 别名；formal StageRunner/PatternRunner 记录初始变量、seed、program hash、compatibility decision 和实际触发帧。

**N2 focused command（每次 N2 子任务都要先跑）**：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_typed_variables.py tests/test_variable_runtime.py tests/test_variable_editor.py tests/test_state_graph_document.py tests/test_state_graph_runtime.py tests/test_stage_program.py tests/test_scene_v4_contract.py tests/test_variable_scopes_and_reducers.py tests/test_variable_editor_native.py tests/test_variable_seek.py tests/test_variable_hotreload.py tests/test_replay_determinism.py
```

**N2 阶段完成门槛**：`[x]` N2.0–N2.7 的 focused tests、通用门禁和所需 native visual 全部通过；可以开始 N3，但必须继续遵守依赖顺序和本文件的 Contract→Implement→Verify→Record 协议。

---

## N3 — 帧边界事件、生命周期和反应运行时

### N3.0 Contract 与事件模型

状态：`[x]`

**Agent 要读**：产品愿景第 7.2、7.4、7.6、17 节；`src/game/events.py`、`src/game/adapters.py`、`src/game/stage/program.py`、`src/game/stage/context.py`、`tests/test_event_bus.py`、`tests/test_event_adapters.py`。

**Agent 要做**：建立版本化 `EventSpec/LifecycleEvent`，字段至少为 type/source/owner/frame/payload/causal_chain；规范化外部 adapter；实现本帧 Outbox→下一帧 Inbox、FIFO、overflow、取消和关闭语义。事件描述“发生了什么”，不直接携带 `start_clip` 命令。

**验收文件**：新增 `tests/test_lifecycle_events.py`、`tests/test_frame_boundary_events.py`、`tests/test_task_scopes.py`；回归 `tests/test_event_bus.py`、`tests/test_event_adapters.py`。

**完成条件**：同帧 dispatch 不重入；网络线程不能直接改 Stage；事件 payload 只含类型化 JSON；owner 退出会取消其 task 和 pending reaction。

### N3.1 生命周期事实与批量路径

状态：`[x]`

**Agent 要做**：从发射器/子弹池/对象生命周期发布 `spawned/hit/death/expired` 等事实，聚合相同来源和帧，保留 count/representative IDs；禁止每颗子弹场景节点、逐弹 Python death callback 和通用事件对象。

**验收文件**：新增 `tests/test_lifecycle_batching.py`；回归 `tests/test_stage_context_bullet_spawn.py`、`tests/test_pattern_runtime.py`、`tests/test_optimized_render_batches.py`。

**完成条件**：假 Boss 被击中、子弹死亡等例子都能产生可追踪事件；固定高密度 workload 不创建 O(bullets) 的 Python 对象链。

### N3.2 ReactionSpec 与 TaskScope

状态：`[x]`

**Agent 要做**：实现事件匹配、变量 guard、cooldown、`once_per_scope`/`ignore_while_running`/`restart`/`parallel`、最大实例数和因果深度；反应启动/停止/取消统一走 `TaskScope`。状态退出优先于旧 State 的新反应。

**验收文件**：`tests/test_reactions.py`、`tests/test_task_scopes.py`、新增 `tests/test_reaction_scheduler.py`。

**完成条件**：死亡开花、假 Boss 受击超量弹幕、击破后背景切场三例均可由事件驱动；重入策略和取消在 trace 中可见且确定。

### N3.3 Timeline/Background/State 接口

状态：`[x]`

**Agent 要做**：把反应绑定到时间线的“可触发生命周期”槽位；背景切换用资源引用和生命周期，不让背景 renderer 直接监听网络或持有 Stage 内部对象；State entry/exit、Clip stop/cancel 和 Reaction owner 统一。

**验收文件**：新增 `tests/test_lifecycle_timeline_hooks.py`、`tests/test_background_reactions.py`；回归 `tests/test_background_document.py`、`tests/test_background_data_driven_parity.py`、`tests/test_state_graph_runtime.py`。

**阶段门槛**：事件、反应、任务取消和背景切场的 Runtime trace 全绿；否则停止，不开始 N4。

**Evidence（2026-08-09）**：N3 focused gate `python -m pytest -q tests/test_lifecycle_events.py tests/test_frame_boundary_events.py tests/test_task_scopes.py tests/test_lifecycle_batching.py tests/test_reactions.py tests/test_reaction_scheduler.py tests/test_lifecycle_timeline_hooks.py tests/test_background_reactions.py` 通过 `27` 项；N2 focused gate 通过 `56` 项；完整 suite 通过 `560` 项。`python -m compileall -q main.py src game_content tools tests`、`python tools/validate_assets.py --format json`（73 JSON、16 sprite configs、745 sprites、142 images，0 errors/0 warnings）和 `git diff --check` 通过。固定 50,000 子弹 workload 的批处理 profile 产生 `1` 个 lifecycle batch、`50,000` count、`0` death handlers，耗时约 `550 ms`（Windows/Python 当前 checkout，首次 Numba 编译包含在测量内）。正式 runtime trace 覆盖死亡开花、假 Boss 受击反击、击破后资源背景切换；State exit 先取消旧 Reaction，Clip 窗口结束记录 `clip_window_end`。Native visual、Performance release threshold 和 Usability gate 仍留给 N6/N9，不作为 N3 的伪完成证据。

---

## N4 — 响应式时间线与蓝图边界

**固定边界**：时间线只保存可见编排、激活规则和生命周期拥有者；行为图负责局部计算、采样、循环和事件生产；ReactionResolver 根据同一帧快照决定实例是否出现。条件表达式不生成一堆隐形连线，事件匹配也不把 Pattern 内部节点暴露到状态图。

### N4.0–N4.2 Agent 任务

状态：`[ ]`

- **N4.0 Contract**：创建 `tests/test_reactive_timeline.py`、`tests/test_activation_rules.py`、`tests/test_timeline_instance_trace.py`，冻结 `at_frame`、`when_variable`、`on_event`、`on_lifecycle`、scope、重入和取消。
- **N4.1 Runtime**：实现 `ReactiveClip`、激活快照、实际触发帧、实例 ID、owner/cancel token、最大实例和预算；已经开始的实例不因变量回溯移动。
- **N4.2 Editor**：在时间线显示生命周期槽和条件徽标；点开槽位可跳到 Reaction/Blueprint，但仍保持各自领域视图；冲突按 target/property/variable 分组。

**验收文件**：上述三份测试、新增 `tests/test_reaction_timeline_integration.py`、`tests/test_editor_reactive_clips.py`；回归 `tests/test_editor_timeline_model.py`、`tests/test_editor_timeline_workspace.py`、`tests/test_state_graph_editor.py`。

**完成条件**：固定“条件产生”例子不需要蓝图到时间线的长连线；运行时 instance trace 能回答触发原因、开始帧、停止原因和 owner；时间线拖动仍遵循正式 reset/replay 语义。

---

## N5 — 可展开的版本化预设

### N5.0 Contract

状态：`[ ]`

创建 `tests/test_preset_descriptor.py`、`tests/test_preset_expansion.py`、`tests/test_preset_migration.py`，冻结参数 schema、公开插槽、输入/输出变量和事件、精确预设版本、虚拟内部 ID 与覆盖规则。

### N5.1–N5.4 Agent 任务

状态：`[ ]`

- **N5.1 预设库**：首发提供自机狙、奇/偶数弹、圆形开花、扇形扫射、单/双/交错螺旋、加速旋转、延迟转向、分裂、速度层叠、波纹和米弹墙；每个预设有真实 fixture 和性能预算。
- **N5.2 虚拟展开**：展开只读显示内部发射器、参数和局部行为，实例 ID 由“实例 ID+预设内部 ID”稳定派生；折叠/展开不复制 Scene 节点。
- **N5.3 覆盖与物化**：公开参数/插槽可覆盖；“展开为本地结构”是显式、可 Undo/Redo 的事务；本地物化后上游预设升级不会偷偷改写。
- **N5.4 迁移**：预设版本升级提供参数迁移和差异报告，失败时保留原实例并给出定位诊断。

**验收文件**：上述三份 Contract、`tests/test_preset_library.py`、`tests/test_editor_preset_workspace.py`、`tests/test_pattern_parity.py`、`tests/test_pattern_compiler.py`。

**完成条件**：新人可以只调参数完成示例；高级作者能展开并替换局部实现；物化和升级均可重放、撤销和定位，不生成不可理解的脚本堆。

---

## N6 — 新手流程与上下文搜索（不包含自然语言）

### N6.0 Contract

状态：`[ ]`

创建 `tests/test_action_catalog.py`、`tests/test_contextual_search.py`、`tests/test_beginner_workflow.py`、`tests/test_editor_usability.py`。Contract 必须测试上下文过滤、类型端口、搜索结果排序、创建事务和空状态引导，不能只检查菜单字符串。

### N6.1–N6.4 Agent 任务

状态：`[ ]`

- **N6.1 Action Catalog**：所有空白上下文按空格打开快速搜索；从 PointSet 拉线只显示接受 PointSet 的 Action；时间线只显示轨道/片段；场景画布只显示可创建对象。Catalog 来自 Descriptor，不由 UI 写死分支。
- **N6.2 新手骨架**：项目向导→道中/关底 Stage 骨架→State/Timeline→Pattern 预设→正式预览；模板创建是一个可 Undo 的文档事务，预览错误能定位到资源/属性。
- **N6.3 渐进展开**：L0 预设卡片、L1 参数、L2 曲线/变量/表达式、L3 行为图、L4 Runtime 源码。任何层级都共享生命周期、类型和调试器。
- **N6.4 Usability gate**：邀请未接触 PySTG 的用户，记录“首个 Pattern、清屏后续、两阶段 Boss+背景切换、撤销/重开/预览”的完成时间和失败点；自动测试不能替代 4/5 用户门槛。

**验收文件**：N6 Contract 文件、`tests/test_editor_m3_integration.py`、`tests/test_editor_authoring_integration.py`、`tests/test_editor_graph_workspace.py`、`tests/test_editor_timeline_workspace.py`，以及原生窗口和人工 Usability 记录。

**完成条件**：用户不必理解内部对象 ID、事件队列或插件注册即可完成常见道中/关底；搜索上下文不会展示无效选项；失败时仍能 Undo 并查看正式 runtime 诊断。

---

## N7 — Behavior Descriptor、Safe/Runtime/Engine 权限分区

### N7.0 Contract

状态：`[ ]`

创建 `tests/test_behavior_descriptor.py`、`tests/test_safe_capabilities.py`、`tests/test_plugin_package_boundaries.py`、`tests/test_behavior_plugin_integration.py`；先冻结 stable ID/version、typed ports、参数 schema、capabilities、lifecycle/cancel、debug snapshot 和 Tool contribution。

### N7.1–N7.5 Agent 任务

状态：`[ ]`

- **N7.1 Safe**：只提供批量发射、授权移动、资源播放、只读 snapshot、等待类型事件和局部变量；不返回 Pool/Renderer/Manager，不许文件/网络/进程/模块访问。若需要任意 Python，改为独立进程能力代理；进程内 Python 明确归 Runtime。
- **N7.2 Runtime**：允许注册组件/事件/弹道/碰撞/道具/受限 Renderer Pass；声明线程、所有权、清理和 replay policy；不许逐弹回调。
- **N7.3 Engine**：内部接口允许调度器、后端、资源类型、编辑器插件和编译器节点扩展；Engine API 不进入普通项目稳定契约。
- **N7.4 分区包与加载**：manifest、dependency lock、schema/migration、runtime/compiler、tool、assets/examples/presets 分区事务化加载/回滚/卸载；headless 不导入 Qt，Tool 按需加载。
- **N7.5 ComplexMapEmitter**：用一个真实插件示范采样域、函数、映射、颜色、Inspector、控制柄、预览和 debug snapshot；普通作者看参数，高级作者可定位源码。

**验收文件**：N7 Contract 文件、`tests/test_plugin_sdk.py`、`tests/test_editor_regression_contracts.py`；native visual 需启动正式预览验证 Tool/Runtime parity。

**完成条件**：越权能力在加载和运行时都被拒绝；插件失败会回滚并清理；同一 Descriptor 同时服务 schema、runtime 和 Tool，headless runtime 不依赖 Qt。

---

## N8 — Renderer Pass 与 Render Graph

### N8.0 Contract

状态：`[ ]`

创建 `tests/test_render_graph.py`、`tests/test_renderer_pass_plugins.py`、`tests/test_render_graph_backend.py`、`tests/test_renderer_pass_editor.py`，覆盖 attachment、格式/尺寸/sample、依赖排序、hazard、resource lease、fallback 和错误定位。

### N8.1–N8.4 Agent 任务

状态：`[ ]`

- 定义后端中立 `PassDescriptor`、输入/输出 attachment、load/store、参数 schema、合并和生命周期；编译期拒绝环、未初始化读取和 capability 不足。
- 给 Runtime 插件只发放 scoped `PassContext`、`CommandEncoder` 和 resource lease；不能拿全局 GL state 或持有过期资源。
- 先实现当前 ModernGL 正式路径的 backend adapter；IR 不包含 ModernGL 对象。缺能力时仅在 Descriptor 明确允许时 pass-through/替代，否则报错。
- Tool 复用同一 Descriptor 提供 Inspector/控制柄/缩略预览；Qt 画面不能冒充正式 Pass。

**验收文件**：N8 Contract 文件、`tests/test_background_data_driven_parity.py`、`tests/test_editor_authoring_integration.py`；必须有真实 GLFW/ModernGL surface、热重载、卸载和资源释放证据。

**完成条件**：Pass 顺序和资源生命周期可追踪；后台/嵌入式正式渲染 parity 通过；插件不能泄漏全局状态或跨帧资源。

---

## N9 — 分层调试器、确定性重放、性能与发布

### N9.0 Contract

状态：`[ ]`

创建 `tests/test_editor_debugger.py`、`tests/test_replay_determinism.py`、`tests/test_runtime_profile.py`、`tests/test_editor_next_acceptance.py`；先冻结 trace 协议版本和 release workload，不得用“测试全绿”替代性能或 native gate。

### N9.1–N9.6 Agent 任务

状态：`[ ]`

- **统一 trace**：记录 author resource ID、runtime instance ID、owner/cancel token、State path、Clip/Reaction、事件因果、变量读写、生成数、CPU/GPU 和诊断；协议版本不兼容要显式拒绝。
- **调试器**：显示 Stage/State/frame、活跃生命周期、触发条件、变量和事件、batch 摘要、弹量预算；支持 pause/step/seek/reset 和 why-not（谁写/谁读/为何未触发/为何取消/为何冲突）。
- **确定性 replay**：将 seed、外部输入、资源/插件版本、初始变量和副作用 policy 纳入 identity；seek 只能 reset+固定帧重放，检查点若加入必须逐帧等价并可回退。
- **性能 profile**：在明确 Windows 目标硬件上测高密度 Pattern、batch lifecycle、Reaction、复杂 State/Timeline、ComplexMap、Render Graph 和长 seek，冻结时间/内存/批量阈值。
- **最终工作流**：从模板做短道中和两阶段 Boss，包含全灭后续、假 Boss 受击反击、死亡开花、背景切场、Runtime Behavior 和 Renderer Pass；保存、重开、Undo/Redo、热重载、seek 和导出均走正式路径。
- **发布门禁**：同一 checkout 产生完整 tests/compile/assets/diff、主游戏、Pattern/Stage preview、PySide6 窗口、正式 renderer、恢复、插件卸载和 profile 报告；不能把 offscreen 或 `--help` 写成发布验收。

**验收文件**：N9 Contract 文件、N2–N8 全部 focused tests、`tests/test_preview_process.py`、`tests/test_preview_editor_integration.py`、`tests/test_editor_authoring_integration.py`，另附 Performance、Native visual、Usability 和发布报告。

**完成条件**：任何 trace/seek/replay 差异可定位；性能阈值有目标硬件和 workload；正式 renderer 和原生编辑器窗口人工验收；所有阶段的停止条件均关闭后才能宣布下一代完成。

---

## 4. 完成记录规则

- 每个 N2–N9 子任务完成后，只把对应 `[ ]` 改为 `[x]`，在该阶段末尾追加一段 Evidence；不要重写已完成阶段，也不要创建 `*_TODO_v2.md`、临时 gate 或“完成日志”副本。
- Evidence 必须给出可复制命令、通过数量或报告路径、使用的 Python/Qt/硬件环境，并明确 Structural/Runtime/Performance/Native visual/Usability 哪些仍缺失。
- 未通过 focused gate、缺少迁移、性能或原生证据时保持未完成；不要为了让清单变绿而删除仍验证公共行为的测试。
