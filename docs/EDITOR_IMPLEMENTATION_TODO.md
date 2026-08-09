# PySTG 下一代编辑器实施 TODO

> 状态：Active / 唯一当前实施清单
>
> 建立日期：2026-08-09
>
> 产品依据：[EDITOR_PRODUCT_VISION.md](EDITOR_PRODUCT_VISION.md) v0.3
>
> 工程边界：[EDITOR_ARCHITECTURE.md](EDITOR_ARCHITECTURE.md)

## 0. 文档职责与当前基线

本文只回答三件事：下一步按什么依赖顺序实施、每个 Agent 必须交付什么、用哪些文件和证据验收。产品为什么这样设计，以产品愿景为准；不可破坏的依赖和运行时边界，以架构文档为准。

旧 `EDITOR_ROADMAP_TODO.md` 已删除。它记录的 M0–M7、R5–R7、自哈希冻结门禁和多轮完成日志已经完成历史职责，不再作为未来 Agent 的操作协议。建立本文前的代码基线为 `0eec58e`，已有版本化作者资源、正式 Pattern/Stage 运行时与预览、可编辑时间线、配方和行为图、表达式、ScriptBehavior、UI/背景资源、事件适配器、插件注册、恢复与 PySide6 发行基础。

本文不重复保存长篇历史。完成一个任务时，只更新该任务的复选框和一条可复现 Evidence；提交、CI 和发布记录保存完整历史。禁止重新加入 Git blob 自哈希、旧文档文本匹配、固定测试文件必须存在之类的元门禁。

### 当前顺序

| 阶段 | 状态 | 依赖 | 主要结果 |
| --- | --- | --- | --- |
| N0 基线重置 | [x] | 当前仓库 | 清理旧路线图和历史元门禁 |
| N1 分层状态图 | [x] | N0 | `SceneDocument` 内嵌 `StateGraphSpec` |
| N2 类型化变量 | [ ] | N1 | 作用域、写权限、迁移和运行时变量存储 |
| N3 帧边界事件与反应运行时 | [ ] | N2 | Inbox/Outbox、LifecycleEvent、ReactionSpec、TaskScope |
| N4 响应式时间线 | [ ] | N3 | ReactiveClip、运行实例 trace、冲突可视化 |
| N5 版本化预设 | [ ] | N4 | 参数/插槽覆盖、虚拟展开、本地物化、版本迁移 |
| N6 新手流程与上下文搜索 | [ ] | N5 | 可运行骨架、首发预设库、Action Catalog、可用性验收 |
| N7 Behavior Descriptor 与权限分区 | [ ] | N6 | Safe/Runtime/Tool 能力边界和分区插件包 |
| N8 Renderer Pass 与 Render Graph | [ ] | N7 | 后端中立 PassDescriptor 和受限运行上下文 |
| N9 调试、重放、性能与发布 | [ ] | N8 | 分层调试器、确定性 seek、目标 profile 和最终验收 |

任何 Agent 只能实施最早的未完成阶段。后续阶段可以只读调研，不得因为 UI 更容易演示而越过依赖。

## 1. Agent 执行协议

### 1.1 每个阶段固定采用六步

1. **Read**：完整阅读本阶段列出的文件、产品愿景对应章节、本文公共规则；执行 `git status --short`，确认并保护用户已有改动。
2. **Audit**：运行本阶段列出的现有回归，定位真实模块、当前公共行为、schema 版本和迁移路径；不得从 TODO 猜测代码现状。
3. **Contract**：先写本阶段列出的行为验收文件，测试必须包含可观察断言和真实 fixture，不得创建空文件、占位 `pass`、只测 import 或只搜源码字符串。新能力的验收测试应在独立 contract commit 中先形成预期红色基线。
4. **Implement**：只修改本阶段允许范围，使 contract 测试逐步变绿。Contract commit 之后，实现 Agent 不得修改该阶段验收断言、添加 skip/xfail、平台排除、宽泛异常吞噬或降低预算来伪造通过。
5. **Verify**：运行 focused tests、全量测试、编译、资源和差异门禁；需要 UI、性能或正式运行时证据时分别执行，不能相互替代。
6. **Record**：更新复选框和 Evidence，写明命令、结果、环境、视觉/性能证据及限制。不得粘贴多轮聊天交接或重复完整测试日志。

如果 contract 本身错误，停止实现，向维护者说明冲突和拟议迁移。只有获得明确同意后，才能用单独的 contract-revision commit 修改断言并重新记录红色基线；不能在实现 diff 中顺手“修测试”。

### 1.2 证据分类

| 证据 | 能证明什么 | 不能替代什么 |
| --- | --- | --- |
| Structural | schema、迁移、序列化、命令、静态边界 | 正式运行行为、画面、性能 |
| Runtime | 正式 compiler/runner/preview trace | 原生窗口视觉和交互 |
| Performance | 固定环境、固定 workload 的时间/内存/批量路径 | 功能正确性和其他硬件结论 |
| Native visual | 真实 PySide6 窗口、正式 GLFW/ModernGL 表面和人工交互 | 可重复的结构与运行时测试 |
| Usability | 未接触 PySTG 的目标用户能否独立完成任务 | 自动 UI 测试和维护者自测 |

任何“完成”声明必须列出任务要求的全部证据类别。Offscreen Qt 只属于 Structural；Qt 画布诊断叠层不是正式弹幕渲染；一次本机 benchmark 不是跨机器性能保证。

### 1.3 公共不可破坏边界

- 作者文档始终是真源；生成 Python 只能是可选导出。
- 高密度子弹、生命周期事实和反应必须批量化；不得增加逐弹场景节点、逐弹 Python update/death callback 或逐弹通用事件对象。
- Preview 必须走正式 compiler/runner/renderer；Qt 只画作者几何、控制柄和只读 runtime overlay。
- 所有 UI 文档修改必须进入当前 document session 的 `CommandStack`，支持 Undo/Redo；运行时反馈不得写回作者文档或制造 dirty 状态。
- 新 schema 必须有显式迁移、旧 fixture、最新 fixture、round-trip 和未知未来版本拒绝测试。
- 所有资源引用使用 `res://`、`ProjectContext` 和项目边界检查；不得增加 cwd 猜测。
- 状态图、时间线、行为、背景和插件只通过类型化变量、事件、资源引用和生命周期所有权交流，不持有其他编辑面的内部对象或 Clip ID。
- 事件采用本帧 Outbox、下一固定帧 Inbox，不允许同一次 dispatch 重入。
- Stage/Timeline seek 的正式语义是 reset 后从作用域入口固定帧重放；检查点只能做逐帧等价的透明优化。
- Safe 层不新增通用 DSL，不提供进程内 Safe Python；任意进程内 Python 属于受信 Runtime。
- 一个插件包可共同交付 schema/runtime/tool，但三个分区使用不同加载环境和能力上下文；headless runtime 不得导入 Qt。
- 不把自然语言或 Agentic 生成加入短期、中期编辑器功能。

### 1.4 公共仓库门禁

每个阶段在 focused tests 之外必须执行：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q main.py src game_content tools tests
python tools/validate_assets.py --format json
git diff --check
```

需要 native visual 的阶段还必须实际启动：

```powershell
python tools/scene_editor.py
python tools/preview_pattern.py --help
python main.py
```

具体交互使用支持的参数或样例资源执行，不能把 `--help` 当作正式运行验收。若自动环境无法显示窗口，阶段保持未完成，并在 Evidence 中明确记录剩余 native gate。

### 1.5 通用停止条件

出现以下任一情况，Agent 必须停止扩大修改范围并报告：

- 需要改变产品愿景已冻结的方向；
- 需要删除或弱化仍验证公共行为的回归测试；
- schema 变化没有确定的旧数据迁移或会丢失未知字段；
- 只能通过第二套预览、逐弹 Python/节点、静默 fallback 或绕过 Undo/Redo 实现；
- focused gate 尚红却需要开始下一阶段；
- native、性能或用户验收是阶段硬门槛但当前环境无法提供；
- 用户改动与计划修改同一代码区域且无法安全合并。

---

## N0 — 新基线与历史门禁清理

### 目标

把未来工作固定为一份可执行 TODO，删除只服务旧交接流程的测试机制，同时保留真实的编辑器、运行时、发行和集成回归。

### Agent 先读

- 旧 `docs/EDITOR_ROADMAP_TODO.md` 全文；
- `docs/EDITOR_PRODUCT_VISION.md`；
- `docs/EDITOR_ARCHITECTURE.md`；
- `AGENTS.md`；
- `tests/test_m4_runtime_preview_contract.py`；
- `tests/test_luna_acceptance_bundle.py`；
- `tests/test_m5_m7_remediation_gate.py`；
- `tests/test_preview_process.py`；
- `tests/test_bottom_layer_smoke.py`；
- `tests/test_stage1_opening_media.py`。

### Agent 要做

- [x] **N0.1 文档重置**：删除旧路线图；建立本文；把 `AGENTS.md`、README、产品愿景和安全边界文档的链接改到本文。
- [x] **N0.2 元门禁删除**：删除 Git blob 自哈希、旧路线图内容检查、固定旧测试文件存在性检查和固定历史 hash 表。
- [x] **N0.3 行为覆盖保留**：
  - 将 `tests/test_luna_acceptance_bundle.py` 重命名为 `tests/test_editor_authoring_integration.py`，仅删除自哈希测试，保留正式 Stage trace、UI/背景 Undo/Redo、renderer delegation 和插件清理测试；
  - 将 `tests/test_m5_m7_remediation_gate.py` 重命名为 `tests/test_editor_regression_contracts.py`，仅删除元门禁，保留表达式、绑定、图、脚本、UI、背景、事件、adapter、plugin、恢复和发行行为测试；
  - 删除 `tests/test_m4_runtime_preview_contract.py`，把其中唯一未重复的 `max_bullets > 600` 行为断言并入 `tests/test_preview_process.py`；
  - 删除只锁定“编辑器开发期间禁用 Stage1 开场媒体”的 `tests/test_stage1_opening_media.py`；
  - 将 `tests/test_bottom_layer_smoke.py` 收敛并重命名为 `tests/test_stage_context_bullet_spawn.py`，删除与公共 `compileall` 重复的纯编译/import 测试，保留普通与极坐标发弹行为。
- [x] **N0.4 术语清理**：移除源码和测试中指向旧 TODO 的悬空引用；现有行为测试称为 regression/contract，不再称为自哈希 frozen gate。
- [x] **N0.5 验证与提交**：完成 focused/full gates，把 `docs/EDITOR_PRODUCT_VISION.md` 一并纳入基线提交。

### 允许修改

`docs/`、`AGENTS.md`、`README.md`、上述测试文件以及只包含旧路线图引用的模块 docstring。不得借本任务修改产品运行行为。

### 验收文件与命令

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_editor_regression_contracts.py tests/test_editor_authoring_integration.py tests/test_preview_process.py tests/test_stage_context_bullet_spawn.py
```

然后执行公共仓库门禁。N0 只需要 Structural/Runtime 回归，不新增 native visual 声明。

### Evidence

2026-08-09：focused gate `116 passed`，完整 suite `486 passed`；`compileall` 和 `git diff --check` 通过；资源校验为 73 JSON、16 sprite configs、745 sprites、142 images、0 errors、0 warnings。该任务只变更文档、测试组织和测试元数据，不声明新的 native visual 结果。下一实施阶段为 N1。

---

## N1 — `SceneDocument` 内嵌分层状态图

### 目标与依赖

在不增加 `FlowDocument`、`StateDocument` 或 `SequenceDocument` 平行真源的前提下，为 Stage、Boss 和 Spell 增加同一种内嵌 `StateGraphSpec`。每个 `StateSpec` 拥有稳定 UUID、局部时间线、局部入口/退出动作、同级转移和可选子状态图。

依赖：N0 全绿。下一阶段不得在 N1 runtime/editor gate 前开始。

### Agent 先读

- 产品愿景第 6、7、8、19、21、22 节；
- `src/editor/document.py`、`src/editor/session.py`、`src/editor/document_manager.py`；
- `src/editor/timeline_commands.py`、`src/editor/timeline_workspace.py`；
- `src/editor/stage_compile.py`、`src/game/stage/program.py`；
- `src/authoring/resources.py`、`src/authoring/migrations.py`、`src/authoring/storage.py`；
- `docs/schemas/pystg-scene-v1.schema.json` 和全部 scene fixture；
- `tests/test_editor_timeline_model.py`、`tests/test_stage_program.py`、`tests/test_editor_timeline_workspace.py`。

### Agent 要做

- [x] **N1.0 Contract pass**：先创建含真实断言的 `tests/test_state_graph_document.py`、`tests/test_state_graph_runtime.py`、`tests/test_state_graph_editor.py`，记录预期红色基线。
- [x] **N1.1 模型**：增加 `StateGraphSpec`、`StateSpec`、`TransitionSpec` 和层级所有权；校验唯一 UUID、唯一初始状态、同级转移、目标存在、子图递归、无悬挂 timeline owner 和有限深度。
- [x] **N1.2 Scene v2→v3 迁移**：现有 `SceneDocument.tracks` 迁入隐式默认 State 或明确兼容父时间线；Track/Clip/Keyframe ID、顺序、时长、payload 和引用必须原样保留；保存后使用 v3，旧文件仍可加载。
- [x] **N1.3 编译**：`SceneDocument -> StageProgram` 编译状态层级、局部时间线、入口/退出和转移；诊断必须包含 Scene/State/Transition UUID 与属性路径。
- [x] **N1.4 运行时**：实现确定性的进入、退出、父级取消和复位；Composite State 进入初始子状态，父状态退出取消整个子树；本阶段只实现状态生命周期和明确的时间/完成转移，不提前发明 N3 的反应队列。
- [x] **N1.5 编辑器**：增加 StageFlow/PhaseFlow 上下文视图；创建、重命名、复制、删除、移动 State 和编辑 Transition 全部通过 CommandStack；选中 State 时显示它自己的局部时间线；Undo/Redo 必须恢复相同 UUID。
- [x] **N1.6 预览反馈**：正式 Stage preview 报告当前状态路径；切换文档、停止和热重载不会把 runtime state 写回文档；owner scene 继续独占 playhead/overlay。
- [x] **N1.7 文档**：增加 scene v3 schema、迁移 fixture 和作者说明；不要复刻运行时内部对象结构。

### 允许修改

`src/editor/document.py`、专用 `state_graph_*` 模块、Scene 命令/工作区、`stage_compile.py`、`src/game/stage/program.py`、authoring migrations/registry、scene schema/fixtures、对应 tests。编辑器外壳只允许增加注册或上下文接线，不允许按具体 State 类型扩散 switch。

### 禁止

- 新建独立 Flow/State/Sequence 文件类型；
- 跨层 Transition 拉线；
- 把 Pattern 内部节点放入状态图；
- 让 runtime transition 改写 SceneDocument；
- 用 Qt-only 状态模拟替代 StageRunner。

### 验收文件与 focused command

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_state_graph_document.py tests/test_state_graph_runtime.py tests/test_state_graph_editor.py tests/test_stage_program.py tests/test_editor_timeline_workspace.py
```

证据要求：Structural + Runtime + native visual。原生检查至少覆盖创建/复制/删除 State、选择 State 后局部时间线切换、Undo/Redo、正式预览中的状态变化和 960×640 可读性。

### 阶段停止条件

若 v2 tracks 无法无损映射、需要改变 UUID、需要跨层连线或 State UI 只能维护第二份模型，停止并提交迁移设计审查，不得继续 N2。

### Evidence

2026-08-09：Contract commit `d2852f9` 保存了预期红色基线；N1 指定 focused gate 为 `41 passed`，连同原生 preview process 回归为 `47 passed`，完整 suite 为 `503 passed`。`compileall`、`git diff --check` 通过；资源校验为 73 JSON、16 sprite configs、745 sprites、142 images、0 errors、0 warnings。Structural 证据覆盖 Scene v2→v3 确定性迁移、v3 schema/fixture/round-trip、全 Scene UUID、递归深度、命令 Undo/Redo 与局部 Timeline；Runtime 证据覆盖正式 worker 中 `Intro@1 → Boss@2`、父子退出/取消、reset/replay、owner-only overlay 且文档和 dirty 不变。Native visual 使用 Windows、PySide6 6.8.1.1、960×640：States/Transitions 两页无需滚动即可操作，完成创建、重命名、复制、删除、Transition 名称/目标/45 帧触发编辑及 Undo→Redo→Undo 同 UUID；截图为 `n1-native-960x640-formal-preview-state-v2.png` 与 `n1-native-960x640-transitions-final.png`。正式 GLFW/ModernGL Pattern renderer 实测 frame 1、24/2048 bullets，`tools/scene_editor.py` 与 `main.py` 均打开真实窗口并正常关闭为 0；未开始 N2。

---

## N2 — 类型化变量、作用域与单一写入者

### 目标与依赖

建立 Project Config、Stage、State、Clip/Reaction、Behavior 和 Engine Snapshot 六类作用域；作者文档只保存声明和默认值，运行值不写回文档。默认单一权威写入者，冲突必须显式解决。

依赖：N1 完成且 scene v3 migration 已稳定。

### Agent 先读

- 产品愿景第 7.1、7.5、7.7、18.3 节；
- N1 的 state graph 文档、编译器和 runtime；
- `src/pattern/bindings.py`、`src/pattern/expressions.py`、`src/pattern/compiler.py`；
- `src/editor/timeline_commands.py`、`src/game/stage/program.py`、`src/game/stage/context.py`；
- `tests/test_pattern_expressions.py`、`tests/test_editor_timeline_commands.py`、N1 tests。

### Agent 要做

- [ ] **N2.0 Contract pass**：创建 `tests/test_typed_variables.py`、`tests/test_variable_runtime.py`、`tests/test_variable_editor.py`，先冻结类型、JSON 表示、作用域、写权限、诊断和回放行为。
- [ ] **N2.1 类型与声明**：提供版本化 `VariableSpec`、`VariableRef` 和类型注册表；首批至少覆盖 bool/int/float/string/vector2/color/resource/complex，complex 使用显式 JSON 实部/虚部表示，禁止 Python 对象进入文档。
- [ ] **N2.2 Scene v3→v4 迁移**：为 Stage/State 增加变量声明和显式输出映射；旧文档迁移为空声明，不改变现有 timeline 行为；提供 v3、v4 fixture 和 round-trip。
- [ ] **N2.3 运行时存储**：按 scope 建立独立 store 和生命周期；跨 State 只通过 Stage 变量或输出映射传值；退出时销毁 State/Clip/Behavior 局部值。
- [ ] **N2.4 写权限**：Engine Snapshot 只读；Timeline 只写 `animatable`；Safe Action 只执行声明的 set/add/toggle/reset；Behavior 只发布 descriptor 中的输出。
- [ ] **N2.5 冲突规则**：静态可知的多写入者在编译期报诊断；作者必须选择有序 override 或类型支持的 reducer/blend；现有 v2/v3 last-wins 只作为迁移兼容标记，不成为新内容默认值。
- [ ] **N2.6 编辑器**：增加变量面板、类型化默认值编辑、作用域/写入者/读者查看和绑定选择；所有编辑可 Undo/Redo；运行值作为只读 overlay，不制造 dirty。
- [ ] **N2.7 热重载/seek**：变量名、类型或作用域不兼容时不猜测迁移，重建作用域并从入口确定性重放。

### 允许修改

authoring 类型/迁移、Scene v4 schema、state/timeline compiler/runtime、受限表达式的类型适配、变量编辑器和对应 tests。不得把全局 Python dict 暴露给 Safe 内容。

### 验收文件与 focused command

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_typed_variables.py tests/test_variable_runtime.py tests/test_variable_editor.py tests/test_pattern_expressions.py tests/test_state_graph_runtime.py
```

证据要求：Structural + Runtime + native visual。原生检查变量声明、绑定搜索、冲突诊断、运行时值只读和 Undo/Redo。

### 阶段停止条件

若类型值不能 JSON round-trip、热重载需要猜测状态、多个写入者会无声覆盖，或变量系统必须取得另一领域内部对象才能工作，停止并修正契约。

### Evidence

未开始。

---

## N3 — 帧边界事件、生命周期反应与 TaskScope

### 目标与依赖

把当前“dispatch 持续排空”的事件行为迁移为固定帧 Inbox/Outbox，建立 `LifecycleEvent`、`ReactionSpec`、稀疏 `TaskScope` 和批量生命周期事实路径。行为只发布事实；声明式反应决定做什么。

依赖：N2 的变量和作用域可作为 Gate/Filter 输入。

### Agent 先读

- 产品愿景第 7.2、7.3、7.4、7.6、17、18 节；
- `src/game/events.py`、`src/game/adapters.py`、`src/game/stage/context.py`；
- `src/pattern/runtime.py`、`src/pattern/script.py`、`src/game/bullet/optimized_pool.py`；
- `tests/test_event_bus.py`、`tests/test_event_adapters.py`、`tests/test_pattern_runtime.py`、`tests/test_editor_regression_contracts.py`。

### Agent 要做

- [ ] **N3.0 Contract pass**：创建 `tests/test_event_frame_boundary.py`、`tests/test_lifecycle_reactions.py`、`tests/test_task_scope.py`、`tests/test_reaction_batch_runtime.py`。若现有 EventBus 公共语义需迁移，在 contract commit 中显式更新对应旧测试并记录兼容策略；实现 pass 不得再改。
- [ ] **N3.1 Inbox/Outbox**：在帧开始封存只读 Inbox；本帧 emit 进入 Outbox，下一固定帧才可见；处理器产生的事件不得在当前 dispatch 重入；外部 adapter 只在帧边界规范化。
- [ ] **N3.2 LifecycleEvent**：定义 type/source/owner/frame/payload/reason/causal 信息；终止原因至少区分 hit_destroyed、expired、out_of_bounds、bomb_cancelled、phase_cleared、owner_cancelled、replaced。
- [ ] **N3.3 ReactionSpec**：实现 Trigger + Filter + Gate + Policy + Action + Scope 的可序列化/可编译模型；静态环和无效类型在编译期诊断。
- [ ] **N3.4 策略**：支持 each、first_per_frame、count_per_frame、debounce、cooldown、max_instances；稀疏事件默认 each，batch 事件默认 count_per_frame。
- [ ] **N3.5 TaskScope**：实现父子所有权、等待、订阅、子行为、完成、stop/cancel 幂等和失败后清理；TaskScope 只管理稀疏跨帧工作，不创建逐弹协程。
- [ ] **N3.6 批量路径**：子弹终止事实以数组/索引/owner/tag/reason 批量收集，过滤和生成进入命令缓冲；禁止为每发子弹分配通用 Python Event 或回调。
- [ ] **N3.7 预算和因果**：加入目标 profile 可配置的链深、每帧生成数、并发实例和队列上限；超限产生确定性抑制和结构化诊断，不能随机丢弃或跨帧摊薄。
- [ ] **N3.8 示例 runtime tests**：覆盖自然结束死亡开花、清场不误触发、同帧聚合、三段延迟开花取消、假 Boss 多次受击聚合。

### 允许修改

事件/adapter、Stage scheduler/context、Pattern/Bullet pool 的批量生命周期接口、新 reaction/task runtime、运行 profile、对应 tests 和文档。不得在本阶段建设 ReactiveClip UI。

### 验收文件与 focused command

```powershell
python -m pytest -q tests/test_event_frame_boundary.py tests/test_lifecycle_reactions.py tests/test_task_scope.py tests/test_reaction_batch_runtime.py tests/test_event_bus.py tests/test_event_adapters.py tests/test_pattern_runtime.py
```

证据要求：Structural + Runtime + Performance。性能证据必须同时记录事件量、生成量、分配/回调边界和目标环境；不能只记录“测试很快”。

### 阶段停止条件

若只能通过同步递归 dispatch、逐弹 Python 对象/协程或无界队列完成例子，立即停止；若预算阈值没有目标硬件证据，只实现可配置 profile 和 benchmark，不凭感觉冻结数值。

### Evidence

未开始。

---

## N4 — ReactiveClip 与时间线运行实例

### 目标与依赖

让时间线既能表达固定片段，也能表达在某个 State/时间窗口内武装的声明式反应；作者定义与运行实例严格分离，并显示触发、取消、抑制和冲突原因。

依赖：N3 的 ReactionSpec、TaskScope 和帧边界事件稳定。

### Agent 先读

- 产品愿景第 6.2、7.3–7.7、8、9、17.1–17.3、18 节；
- N1 state timeline 和 N3 reaction runtime；
- `src/editor/document.py`、`timeline_commands.py`、`timeline_workspace.py`；
- `src/editor/stage_compile.py`、`src/game/stage/program.py`；
- 现有 timeline model/command/workspace/stage tests。

### Agent 要做

- [ ] **N4.0 Contract pass**：创建 `tests/test_reactive_timeline.py`、`tests/test_timeline_runtime_instances.py`、`tests/test_timeline_conflicts.py`、`tests/test_reactive_timeline_editor.py`。
- [ ] **N4.1 Scene v4→v5**：为 Clip 增加版本化 Activation/Stop/InstancePolicy/Reaction 数据；旧固定 start/duration 迁移为固定激活，ID 不变。
- [ ] **N4.2 激活语义**：支持 fixed、relative-to-state、relative-to-marker/event、on_rise、while_true、on_fall、on_change 和事件脉冲；默认 `on_rise + once_per_scope + max_instances=1 + ignore_while_running`。
- [ ] **N4.3 实例策略**：支持 once/retrigger/restart/parallel/max_instances/cooldown；author clip ID 与 runtime instance ID 分开，运行实例绝不写回文档。
- [ ] **N4.4 生命周期顺序**：同一事件引起 State 转移和旧 State 反应时，先提交状态退出/取消；需要保留的演出使用 Exit Action 或新 State Entry Timeline。
- [ ] **N4.5 runtime trace**：正式 preview 发布 Armed/Triggered/Running/Completed/Cancelled/Suppressed 状态、原因、帧、实例数和 owner；切换/停止清空 overlay。
- [ ] **N4.6 编辑器**：ReactiveClip 用虚线/空心区间；触发 trace 叠加而不新增文档 Clip；parallel 展示 ×N/实例列表；冷却、Gate、预算抑制留下可检查标记。
- [ ] **N4.7 冲突可视化**：按 target+property 分组；新内容重叠默认诊断，作者显式选择 override/add/multiply/weighted blend；迁移内容保留兼容 last-wins 标签。
- [ ] **N4.8 场景例子**：死亡开花武装窗口、假 Boss 受击反击、击破局部切背景和击破转下一 State 均能从顶层看到原因与实际帧。

### 允许修改

Scene v5 schema/migration、timeline model/commands/workspace、stage compiler/runtime/preview trace、background cue 接口和对应 tests。

### 禁止

- Behavior 直接调用 Clip ID；
- runtime 触发时复制/保存新 Clip；
- 用行为图替代时间线激活面板；
- 为 UI trace 新建第二套 scheduler。

### 验收文件与 focused command

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_reactive_timeline.py tests/test_timeline_runtime_instances.py tests/test_timeline_conflicts.py tests/test_reactive_timeline_editor.py tests/test_state_graph_runtime.py tests/test_lifecycle_reactions.py
```

证据要求：Structural + Runtime + native visual。原生验收必须演示未触发、触发、restart/parallel、抑制、State 退出取消、冲突修复和 Undo/Redo。

### 阶段停止条件

若 editor trace 必须污染文档、动态 start_frame 会追溯移动、同事件顺序不确定或背景切换需要对象直接调用 renderer，停止并修正 runtime contract。

### Evidence

未开始。

---

## N5 — 版本化预设、插槽与渐进展开

### 目标与依赖

建立一等预设资源，让普通作者从“差不多的效果”开始；查看内部结构、覆盖、物化和重新封装均保持同一正式编译/运行路径。

依赖：N4 能承载 Pattern/Wave/Phase/Background 的固定与反应结构。

### Agent 先读

- 产品愿景第 10、11、17.3、22 节；
- Pattern recipe/graph/compiler、Scene v5、ReactiveClip、ResourceTypeRegistry；
- `src/editor/pattern_workspace.py`、`graph_workspace.py`、resource browser 和 commands；
- authoring resource/migration/storage tests。

### Agent 要做

- [ ] **N5.0 Contract pass**：创建 `tests/test_preset_document.py`、`tests/test_preset_migrations.py`、`tests/test_preset_runtime_parity.py`、`tests/test_preset_editor.py`、`tests/test_preset_library.py`。
- [ ] **N5.1 资源模型**：定义 `pystg.preset` v1，声明 stable ID、精确版本、domain、参数 schema/单位/默认值、资源/行为插槽、输入输出、取消策略、内部结构、来源、标签、本地化和性能等级。
- [ ] **N5.2 依赖锁**：项目记录精确解析版本；内置预设升级也不得静默改变旧项目；缺失版本以保留原数据的诊断模式打开。
- [ ] **N5.3 实例**：预设实例只保存 preset ID/version、参数覆盖和插槽覆盖；编译后与等价本地结构 runtime trace 相同。
- [ ] **N5.4 虚拟查看**：内部节点由 instance ID + preset internal ID 派生稳定调试身份；只读查看不复制节点，不允许修改非公开字段。
- [ ] **N5.5 局部覆盖**：公开参数/插槽可被替换，仍保持预设身份；覆盖必须类型检查、可 Undo/Redo、可诊断。
- [ ] **N5.6 转为本地**：一个可撤销事务物化当前解析结构，生成本地稳定 ID，记录 provenance/ID map，解除上游更新；Undo 恢复原预设实例。
- [ ] **N5.7 迁移**：新版本在临时副本上迁移参数 ID/类型/插槽，显示结构/参数/正式预览差异；作者确认后一个事务更新实例和 lock；失败保留旧版本。
- [ ] **N5.8 项目预设**：把本地结构封装为新的项目预设 ID，不覆盖上游包。
- [ ] **N5.9 首发资源骨架**：为 N6 所需 Pattern/Wave/Phase/Stage/Background 预设提供版本化资源与运行 parity；本阶段不把所有预设塞进首次选择 UI。

### 允许修改

authoring registry/storage、项目 manifest/lock、preset 模型/compiler、Pattern/Scene/Background 实例接口、虚拟视图/commands、assets 或 game_content 中的预设包、对应 tests。

### 禁止

- 展开时复制一份会与源预设漂移的可编辑影子；
- 编辑器升级时自动迁移项目；
- 用内部节点位置作为迁移键；
- 折叠与本地结构走不同 runtime；
- 缺版本时猜测“最接近”版本。

### 验收文件与 focused command

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_preset_document.py tests/test_preset_migrations.py tests/test_preset_runtime_parity.py tests/test_preset_editor.py tests/test_preset_library.py tests/test_pattern_graph.py
```

证据要求：Structural + Runtime + native visual。原生检查参数覆盖、虚拟展开、局部替换、物化/Undo、版本差异与失败回退。

### 阶段停止条件

若无法证明折叠/展开/物化 runtime parity，或升级需要静默丢覆盖，阶段保持未完成。

### Evidence

未开始。

---

## N6 — 新手创建流程、上下文搜索与首发库

### 目标与依赖

让没有 PySTG 经验的作者从可运行骨架和预设完成 Pattern、短道中和两阶段 Boss，不需要空白蓝图、Python 或引擎内部概念。

依赖：N5 的预设和版本锁可正式运行。

### Agent 先读

- 产品愿景第 3、4、8、9、11.5、12、13、15 节；
- `src/editor/app.py`、workbench、resource browser、Pattern/Timeline/State/Background 工作区；
- N5 preset registry/editor；
- `tests/test_editor_m3_integration.py` 和所有新工作区测试。

### Agent 要做

- [ ] **N6.0 Contract pass**：创建 `tests/test_action_catalog.py`、`tests/test_contextual_search.py`、`tests/test_beginner_workflow.py`，覆盖命令、类型过滤、键盘、Undo 和完整保存/重开/预览。
- [ ] **N6.1 创建向导**：提供 Pattern 实验、短道中、标准 Boss 战和背景/UI 入口；所有入口生成可直接正式运行的骨架，不生成空 Scene。
- [ ] **N6.2 首发 Pattern**：自机狙、奇偶数扇形、圆形开花、扇形扫射、单双螺旋、延迟转向、子弹分裂。
- [ ] **N6.3 首发组合**：Wave 的单编队入场/左右交替/编队自机狙/精英中 Boss；Phase 的普通攻击/标准符卡/耐久/击破演出；Stage 的 Pattern 实验/短道中/标准 Boss；Background 的滚动道中/符卡转场。
- [ ] **N6.4 Action Catalog**：每个动作声明上下文、输入输出类型、能力、Command factory、中英文名/别名/拼音/标签、来源、帮助和性能提示。
- [ ] **N6.5 上下文搜索**：端口拉线只显示类型兼容行为；Timeline 只显示轨道/片段/编排动作；Scene 只显示父级允许对象；Inspector 显示绑定/转曲线/重置/暴露参数。
- [ ] **N6.6 空格交互**：实现“轻按空格搜索、按住拖动平移”或经 native QA 冻结的等价可配置方案；焦点在文本输入时不得抢键。
- [ ] **N6.7 渐进展开**：L0 预设卡片→L1 参数→L2 曲线/变量→L3 内部图/时间线→L4 Runtime 源码，升级深度不丢 UUID、引用、诊断、preview 或 instance identity。
- [ ] **N6.8 可用性验收**：邀请至少 5 名未使用过 PySTG 的目标用户，不由维护者带做；记录完成时间、求助、无效点击、撤销、首次脚本冲动和诊断理解。

### 禁止

- 自然语言或 Agentic 生成入口；
- 巨型未过滤菜单；
- 为每个模板复制不可维护数据；
- 让“上一波全灭后继续”等常见关系必须打开行为图；
- 用自动测试代替 5 名用户的可用性门槛。

### 验收文件与 focused command

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_action_catalog.py tests/test_contextual_search.py tests/test_beginner_workflow.py tests/test_preset_library.py tests/test_editor_m3_integration.py
```

证据要求：Structural + Runtime + native visual + Usability。用户门槛：至少 4/5 人在 10 分钟内得到并修改正式预览 Pattern；30 分钟内完成“上一波全灭后继续”的短道中；60 分钟内完成两阶段 Boss、背景转场和事件反应，全程不写脚本。

### 阶段停止条件

若任何用户任务需要解释内部对象 ID、弹池或插件注册，或少于 4/5 人达标，N6 保持未完成；先修流程再进入 N7。

### Evidence

未开始。

---

## N7 — Behavior Descriptor、Safe 节点与插件分区

### 目标与依赖

把运行时行为、编译器、schema、调试快照和编辑器工具用版本化 Descriptor 连接；执行 Safe/Runtime/Engine 权限边界，并用一个分区插件包交付能力。

依赖：N6 已证明顶层流程，避免插件 API 围绕错误 UX 冻结。

### Agent 先读

- 产品愿景第 5、10、14、15、22 节；
- `src/editor/plugin_sdk.py`、authoring/registry、node registry、Pattern graph/compiler/runtime；
- `src/game/stage/context.py`、preview protocol/process；
- `docs/EVENTS_AND_PLUGINS.md` 和 plugin/regression tests。

### Agent 要做

- [ ] **N7.0 Contract pass**：创建 `tests/test_behavior_descriptor.py`、`tests/test_safe_capabilities.py`、`tests/test_plugin_package_boundaries.py`、`tests/test_behavior_plugin_integration.py`。
- [ ] **N7.1 Descriptor**：定义 stable ID/version、typed ports、parameter schema/units/binding、capabilities、execution kind、lifecycle/cancel、compiler、debug snapshot schema 和可选 Tool contribution。
- [ ] **N7.2 Safe 能力**：Safe 节点只获得批量发射、授权句柄移动、注册资源播放、只读 snapshot、等待/发出类型化事件、局部变量和有配额稀疏实例；不能取得 Pool/Renderer/Manager、文件、网络、进程或模块。
- [ ] **N7.3 Runtime 能力**：受信代码可注册稀疏组件、事件、批量运动内核、碰撞组件、机制和受限 Renderer Pass；必须声明线程、所有权、清理和 replay policy。
- [ ] **N7.4 分区插件包**：manifest + dependency lock、schema/migrations、runtime/compiler、tool、assets/examples/presets 分区；各分区事务激活/回滚/卸载。
- [ ] **N7.5 加载边界**：headless 只加载 schema/compiler/runtime，导入图中不得出现 Qt；Editor 按需加载 Tool；schema migration 不依赖 renderer/editor instance。
- [ ] **N7.6 降级**：缺 Tool 使用通用 Inspector；缺必需 Runtime/Compiler 产生定位到资源/descriptor 的编译错误，不能假装 preview 成功。
- [ ] **N7.7 ComplexMapEmitter 样例**：提供批量 runtime、采样域控制柄、Inspector、搜索项、预设和 debug snapshot；普通作者只见函数/采样域/数量/映射/颜色，高级作者可定位源码。
- [ ] **N7.8 安全表述**：进程内 Python 明确标为 trusted Runtime；不得把小 ctx 宣称为沙箱，也不实现通用 Safe DSL。

### 允许修改

plugin SDK/package loader、registries、behavior descriptor/compiler/runtime/tool bridge、preview debug protocol、sample plugin/preset 和 tests。Engine API 只作为内部扩展点，不承诺普通项目稳定性。

### 验收文件与 focused command

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_behavior_descriptor.py tests/test_safe_capabilities.py tests/test_plugin_package_boundaries.py tests/test_behavior_plugin_integration.py tests/test_plugin_sdk.py tests/test_editor_regression_contracts.py
```

证据要求：Structural + Runtime + Performance + native visual。必须分别证明 headless 无 Qt、能力拒绝、事务回滚、卸载清理、批量 ComplexMap 和通用 Inspector fallback。

### 阶段停止条件

若 Tool 可以取得 Engine 活对象、headless 导入 Qt、Safe Python 仍可导入模块/读文件，或自定义 dense 行为只能逐元素 callback，阶段失败。

### Evidence

未开始。

---

## N8 — 后端中立 Renderer Pass 与 Render Graph

### 目标与依赖

允许受信 Runtime 插件注册受约束的渲染阶段，同时避免裸全局 GL callback、资源泄漏和 Qt 近似实现。

依赖：N7 的 Descriptor、插件分区、能力和清理协议。

### Agent 先读

- 产品愿景第 16、19、20、22 节；
- 当前 background renderer、ModernGL preview worker、资源/纹理服务；
- N7 plugin loader/descriptor；
- 正式 preview 和 background parity tests。

### Agent 要做

- [ ] **N8.0 Contract pass**：创建 `tests/test_render_graph.py`、`tests/test_renderer_pass_plugins.py`、`tests/test_render_graph_backend.py`、`tests/test_renderer_pass_editor.py`。
- [ ] **N8.1 PassDescriptor**：定义输入/输出 attachment、格式/尺寸/采样/load-store、阶段/依赖/排序/合并、参数 schema、资源生命周期、后端 capability/fallback、预算和调试标签。
- [ ] **N8.2 Render Graph 编译**：验证依赖环、读写 hazard、格式兼容、未初始化读取、生命周期和 capability；错误在编译/导出阶段定位到 plugin/pass/property。
- [ ] **N8.3 受限执行上下文**：插件只获得 scoped PassContext、CommandEncoder 和 resource lease；不能访问全局 GL 状态或持有过期资源。
- [ ] **N8.4 Backend adapter**：先为当前 ModernGL 正式路径实现 adapter；IR 不包含 ModernGL 对象，为未来后端保留纯数据边界。
- [ ] **N8.5 fallback**：不支持后端默认报错；仅插件显式声明且语义可接受时允许 pass-through/替代实现，不能静默关闭。
- [ ] **N8.6 Tool**：同一 Descriptor 可提供 Inspector、缩略预览和控制柄；Qt 不实现独立效果 renderer，正式 preview 才能声明 parity。
- [ ] **N8.7 生命周期/性能**：热重载、失败和卸载释放 attachment/lease；记录 CPU build、GPU time、临时显存和 pass 合并证据。

### 禁止

- 暴露裸 `moderngl.Context`/全局 GL state 给普通 plugin；
- Qt/QPainter 近似效果冒充正式 pass；
- 不支持后端静默跳过；
- 插件跨帧持有未声明资源。

### 验收文件与 focused command

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_render_graph.py tests/test_renderer_pass_plugins.py tests/test_render_graph_backend.py tests/test_renderer_pass_editor.py tests/test_background_data_driven_parity.py tests/test_editor_authoring_integration.py
```

证据要求：Structural + Runtime + Performance + native visual。至少用一个真实 Pass 在正式 GLFW/ModernGL surface 显示、热重载和卸载；offscreen graph 测试不能关闭 visual gate。

### 阶段停止条件

若无法隔离全局状态、无法检测 hazard、资源释放依赖进程退出，或只有 Qt 预览可见，N8 保持未完成。

### Evidence

未开始。

---

## N9 — 分层调试器、确定性重放、目标性能与发布验收

### 目标与依赖

把前述状态、变量、事件、ReactiveClip、预设、行为和 Renderer Pass 汇合为同一套可复现调试体验，并在目标硬件上冻结性能 profile 和下一代编辑器发布门槛。

依赖：N1–N8 全部完成。

### Agent 先读

- 产品愿景第 7.5–7.7、8.5、18、19、22 节；
- preview controller/protocol/process、Stage/Pattern runner；
- N1–N8 的 debug snapshot、trace 和 profile 数据；
- replay/userdata、正式 renderer、Editor output/preview/timeline panels；
- 全部阶段验收 tests。

### Agent 要做

- [ ] **N9.0 Contract pass**：创建 `tests/test_editor_debugger.py`、`tests/test_replay_determinism.py`、`tests/test_runtime_profile.py`、`tests/test_editor_next_acceptance.py`。
- [ ] **N9.1 统一 trace schema**：记录 author resource ID、runtime instance ID、owner/cancel token、State path、Clip/Reaction 状态、事件因果、变量读写、生成数、CPU/GPU 和诊断；协议版本不兼容要明确拒绝。
- [ ] **N9.2 顶层调试器**：显示当前 Stage/State/frame、活跃/武装片段、触发/抑制原因、主要变量、事件与 batch 摘要、弹量/预算，以及 pause/step/seek/reset。
- [ ] **N9.3 行为实例视图**：显示输入输出、当前子行为、所有权、生成进度、耗时、能力违规，并能定位预设虚拟节点、行为图节点或 Runtime 源码。
- [ ] **N9.4 Why-not 诊断**：回答变量由谁写/读、条件为何未触发、Reaction 是过滤失败/Gate/冷却/并发/预算中的哪一种、属性为何冲突、热重载保留或重建了什么。
- [ ] **N9.5 确定性 seek**：Pattern/Clip/State/Stage 从对应入口 reset 后按固定帧重放至目标；随机种子、输入记录、resource/plugin version 和初始变量进入 replay identity；外部副作用由能力代理抑制/恢复。
- [ ] **N9.6 可选检查点**：只有完整重放 profile 证明需要时才增加缓存；逐帧 trace 必须等价，失效自动回退完整重放，不能改变 authoring 语义。
- [ ] **N9.7 目标 profile**：在明确的最低/推荐 Windows 硬件上测量高密度 Pattern、batch lifecycle、Reaction、复杂 State/Timeline、ComplexMap、Render Graph 和长 seek；据证据冻结链深、生成、队列、内存和帧时间阈值。
- [ ] **N9.8 最终工作流**：从模板创建短道中和两阶段 Boss，包含上一波全灭、假 Boss 受击反击、死亡开花、背景转场、自定义 Behavior 和 Renderer Pass；保存/重开/Undo/Redo/热重载/seek/导出均通过正式路径。
- [ ] **N9.9 发布验证**：完整 tests/compile/assets/diff、主游戏、Pattern/Stage preview、PySide6 编辑器 1480×920 与 960×640、正式 embedded/external renderer、资源恢复、插件卸载和性能报告从同一 checkout 产生。

### 验收文件与 focused command

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_editor_debugger.py tests/test_replay_determinism.py tests/test_runtime_profile.py tests/test_editor_next_acceptance.py
```

随后执行全部 N1–N8 focused tests 和公共仓库门禁。证据要求：Structural + Runtime + Performance + native visual + Usability；任何一类都不能由另一类代替。

### 阶段停止条件

若 replay identity 不完整、seek 结果与正常播放不同、外部输入未记录却宣称可复现、性能阈值没有目标硬件、正式 renderer 未实际显示，禁止标记 N9 完成或宣称发布就绪。

### Evidence

未开始。

---

## 2. TODO 维护规则

- 只保留一份当前实施 TODO；不要为单次 Agent 交接再创建 `*_TODO_v2.md`、冻结 addendum 或临时 gate 文档。
- 产品方向改变时先修改产品愿景和变更记录，再调整本文依赖与任务；实现不得先行。
- 每个任务完成后把 `[ ]` 改为 `[x]`，Evidence 只写一次最终、可复现结果。失败重试留在提交/CI，不堆进本文。
- 完成整个 N0–N9 代际后，用新的下一代 TODO 替换本文；稳定架构结论迁入专门设计文档，已完成清单不无限累积。
- 新测试文件只能在对应 Contract pass 创建，必须从第一版就包含有意义的行为断言；本文列出的未来文件不是要求现在创建空 placeholder。
