# PySTG 拖拽式关卡编辑工作流重构

## 1. 目标与固定交互

把当前“树形移动 + 弹出菜单新增”替换为真正以拖拽为主的轻量代码编辑器：

- 左侧常驻分类节点库，中央为从上到下的块式程序流，右侧继续使用 Inspector，底部保留 Timeline。
- 声明式 Python 仍是唯一真源；拖拽只是生成和修改 DSL，不引入 Graph、JSON 作者格式或第二套模型。
- 借鉴 LuaSTG Editor Sharp 的“分类工具箱、明确插入方式、属性区”，不照搬其密集图标和旧式工具栏。
- 不设物理代码行硬上限，但必须替换旧交互，不允许把新旧两套界面叠加保留。

## 2. 完整交互规格

### 常驻节点库

- 左侧区域改为上下分栏：上方保留程序结构、文件、资产等视图，下方始终显示节点库。
- 节点库提供搜索、分类折叠、“兼容当前上下文”默认过滤和“显示全部”开关。
- 不兼容节点在“显示全部”中灰显，悬停直接说明原因，例如“Fire 不能直接放入 Stage”。
- 覆盖全部公开 DSL 节点、项目模板和显式导入模板；模板仍保存为调用，不展开成普通节点。
- 最近使用仅保存在当前编辑器会话，不写入作者工程。
- 主操作是拖拽；双击节点可按当前插入模式添加，作为键盘和无障碍备用入口。
- 当前“添加到后面/添加为子节点”弹出菜单删除，替换为紧凑的 `之前/之后/子项/包裹` 插入模式和一个通用“添加”动作。

### 中央块式程序流

- 每个节点显示为缩进卡片：中文名称、关键参数摘要、模板/动态/错误标记；UID 只在详情或提示中显示。
- Repeat、If、At、SpawnTask 等直接展示嵌套区域；空容器显示“拖到这里添加内容”。
- If 明确显示“条件成立”和“否则”；Parallel 显示独立分支，宽屏并排、小窗口纵向堆叠。
- 空逻辑单元显示覆盖整个内容区的首节点落点。
- 点击卡片选中并同步 Inspector、Timeline；双击聚焦首个可编辑参数。
- 支持折叠、边缘自动滚动、悬停 450ms 自动展开容器、Esc 取消拖动。
- 删除、复制和所有拖动继续进入唯一 `QUndoStack`。

### 四区拖放

拖到节点卡片时显示清晰覆盖层，不再依赖隐形坐标猜测：

- 上四分之一：`放到之前`
- 下四分之一：`放到之后`
- 中间左侧：`作为子项`
- 中间右侧：`包裹目标`

规则：

- 当前激活区高亮，并显示完整结果预览，例如“把 Repeat 包裹在 Wait 外层”。
- 不合法区域灰显且不能释放，附近显示具体原因；失败不产生模型修改或 Undo 记录。
- 多插槽容器进入 Child 区后展开细分落点：If 显示两个分支，Parallel 显示现有分支和“新建分支”。
- Wrap 仅允许从节点库拖入合法容器，或拖动一个空且子插槽明确的现有容器；禁止用已有复杂子树隐式吞入目标。
- Parallel 的新建 Wrap 自动创建一个内部 Branch 并把目标放入该分支。
- 放置成功后选中新节点、短暂闪烁高亮，并将 Inspector 滚动到建议首先修改的字段。

### 参数和引用

- 有安全默认值的节点立即插入，Inspector 标出“建议调整”字段，不先弹完整参数窗口。
- Ref 参数不再偷偷选择工程中的第一个对象。RunWave、RunBoss、SpawnEnemy、Call、SpawnTask 等落下后显示锚定选择器：
  - 只能选择已经存在且类型正确的逻辑单元；
  - 即使只有一个候选也明确显示并预选；
  - 没有候选时节点库项禁用，并提供跳转到“新建对应逻辑单元”；
  - Escape 取消，确认前不修改模型。
- Inspector 继续从 DSL 类型注解生成控件，并补齐：
  - Literal 下拉框；
  - Ref 可搜索选择框；
  - 常量/`Expr` 切换；
  - `res://` 拖入和文件选择；
  - 列表、字典和参数表的轻量结构化编辑；
  - 字段级错误提示。
- 连续数值编辑合并为一个可理解的 Undo 操作。

### 逻辑单元管理

程序结构栏提供“新建、复制、删除”：

- Project 始终只有一个，不允许复制或删除。
- 新建时填写类型、ID、显示名和该类型必要参数；路径固定映射到 `stages/`、`waves/`、`enemies/` 等目录。
- ID 和路径创建后固定；显示名可以随时修改。
- 新建 Stage 默认勾选“加入 Project 关卡顺序”，首个 Stage 自动成为 `start_stage`；用户可取消。
- 复制逻辑单元时生成新 ID、路径和全部新 UID，内部指向原单元自身的 Ref 改为新 ID，其他 Ref 保持不变。
- 复制 Stage 默认不加入 Project，用户可在复制窗口勾选。
- Boss 创建必须选择至少一个现有 Spell/NonSpell；没有候选时阻止创建并引导先创建符卡。
- 删除被引用单元时阻止，并列出所有引用位置供跳转，不做级联删除。
- 删除已注册 Stage 时，窗口同时处理 Project 顺序；若删除 `start_stage`，必须显式选择新的开始关卡。
- 新建、复制、删除先作为内存修改进入 Undo；保存时才原子写入或删除对应 Python 文件。

## 3. 实现边界与接口

### Headless 作者层

在现有作者模型中增加最小公开能力，不建立 Service、Descriptor 或 Action Catalog：

- `validate_insert(...) -> DropCheck`：返回是否合法、原因和可用 child slot。
- `insert_new_node(...)`：统一处理根节点、Before、After、Child、Wrap 和 Parallel 分支。
- `create_unit(...)`、`duplicate_unit(...)`、`delete_unit(...)`：纯模型操作，先在副本验证再提交。
- `node_from_palette(kind, program, unit_kind, reference_id=None)`：唯一默认节点工厂；通过 DSL 签名和上下文生成有效初值。
- UI 分类只保存中文标签和类别，不复制构造函数参数、默认值或父子规则。

Python source project增加未保存文档和删除墓碑状态：

- 新文件在保存前只存在于内存；
- 删除文件在保存前可完整 Undo；
- 保存失败保留原磁盘文件和当前内存状态；
- 外部修改冲突继续沿用现有明确 keep/reload 流程。

### Qt 编辑器层

- 新增一个轻量 `NodePalette`；当前 `ProgramTree` 改造成自定义绘制的纵向 `ProgramFlow`，仍直接投影 `EditorSession`，不拥有第二份模型。
- 新节点拖拽使用瞬态 MIME `application/x-pystg-node-prototype`，只携带节点或模板 identity，不保存作者数据。
- 已有节点移动继续使用 UID MIME；资源拖拽继续使用现有 `res://` MIME。
- ProgramFlow 在 drag move 阶段调用 headless `validate_insert`，只负责绘制四区覆盖层；drop 时只提交一个 `QUndoCommand`。
- 移除当前弹出式 `NODE_PALETTE`、隐形四区判定和资源/节点各自重复的插入代码。
- Timeline、预览和只读源码视图不改变所有权；编辑后仍只标记预览过期，Run 才保存、构建和重启。

## 4. 实施顺序

1. 先把当前已验证的基础新增/删除接口单独 commit 并 push，明确排除 `.claude/settings.local.json`，作为可恢复检查点。
2. 先完成 headless 插入合法性、全部节点默认构造和逻辑单元纯模型操作；Qt 尚不改布局。
3. 替换节点库和中央程序流，一次删除旧弹出菜单与隐形落点实现；完成四区覆盖、空根节点和模板拖入。
4. 加入逻辑单元新建/复制/删除及结构化 Inspector 控件。
5. 串联保存、构建、预览、Timeline 和外部冲突；更新编辑器文档与可复现证据。
6. 由未参与实现的验证者进行只读 gate；任何失败回到本次交互重构修复，不保留新旧模式开关。

## 5. 测试与验收

### 自动化

- 所有公开 DSL 节点至少在一个合法上下文中能从节点库创建、保存、重开和构建。
- Before、After、Child、Wrap、空根节点、If 双插槽、Parallel 新分支和非法落点均有 headless 测试。
- Qt 测试必须发送真实拖拽事件，从节点库拖到可见四区；禁止只调用内部插入方法冒充拖拽。
- 覆盖搜索、兼容过滤、灰显原因、引用选择/无候选、模板保留调用、参数补全和唯一 Undo 栈。
- 覆盖逻辑单元新建、复制、UID 更新、Project Stage 注册、引用阻止删除、保存失败回滚和外部冲突。
- 全仓 `python -m pytest`、compileall、资产校验和 diff checks 必须通过；不得增加 skip/xfail。
- 继续满足 DSL/compiler <15 秒、编辑器自动化 <60 秒、PR 门禁 <5 分钟；不再设置物理总行硬上限，但最终报告净增、净删和删除的旧交互代码。

### 真实 Windows 与人工验收

- 在 1480×920 和 960×640 下用真实 PySide6 窗口完成节点库搜索、真实鼠标拖动、四区切换、自动滚动、Inspector 修改和 Undo/Redo。
- Project、Stage、Spell 真实 GLFW/ModernGL 预览继续成功嵌入、获得焦点并正常停止，无残留进程。
- 维护者必须实际完成一次完整工作流：新建 Wave 和 Enemy、拖出 Repeat/Wait/Fire、把节点包裹进容器、加入 Stage、修改参数、保存重开并运行预览。
- Structural、Runtime、Native、Performance、Usability 分别报告；维护者未实际完成前，Usability 必须写 `not run`，不能用自动化或截图代替。

## 6. 实施与验收证据（2026-08-29）

### 实施顺序执行情况

1. **检查点提交**：`d758990`（feat(editor): headless palette inserts, unit
   lifecycle, and in-memory documents）已提交并推送到
   `codex/code-driven-editor-v2`；`.claude/settings.local.json` 从未暂存。
2. **Headless 层先行**：`validate_insert`/`DropCheck`、`insert_new_node`、
   `node_from_palette`、`create_unit`/`duplicate_unit`/`delete_unit`、
   `duplicate_node`、`unit_reference_locations` 全部先于 Qt 改动完成并有直接
   测试；Python source 工程新增未保存文档与删除墓碑状态
   （`add_unsaved_unit`/`tombstone_unit`/`restore_tombstone`）。
3. **节点库与程序流替换**：旧的弹出式 `NODE_PALETTE`、隐形四区判定、
   `_PALETTE_ARGUMENTS`、QTreeWidget 版程序树已整体删除，未保留新旧双轨。
4. **逻辑单元管理与结构化 Inspector** 已接入窗口与命令层。
5. **保存/构建/预览串联**：新建与删除在保存前只改内存；保存失败回滚磁盘
   快照；外部冲突沿用 keep/reload 流程。
6. **独立只读验证**：见下方各类证据；Usability 等待维护者实操。

### Structural：PASS

- `src/editor/program_tree.py` 重写为自定义绘制的 `ProgramFlow`
  （`QAbstractScrollArea` + 画布），投影 `EditorSession`，不持有第二份模型；
  `Parallel` 分支按视口宽度自动并排/纵向堆叠；空容器显示"拖到这里添加内容"；
  折叠、边缘自动滚动、悬停 450ms 自动展开、落点闪烁高亮。
- `src/editor/node_palette.py` 常驻节点库：搜索、兼容过滤、灰显原因、最近使用
  （仅会话内存）、模板与显式导入模板按调用保留。
- `src/editor/inspector.py`：Literal 下拉框、可搜索 Ref 选择框、常量/表达式
  切换、`res://` 拖入与文件浏览、列表/字典字面量结构化编辑、字段级错误提示、
  "建议调整"标记与聚焦。
- `src/editor/commands.py`：`SetNodeArgumentCommand` 支持 `id()`/`mergeWith`，
  连续数值编辑合并为一个可理解 Undo；新增 `DuplicateNodeCommand`。
- 全部 37 个公开 DSL 节点种类由 `node_from_palette` 工厂覆盖（测试断言与
  `dsl.NODE_CONSTRUCTORS` 一一对应）。

### Runtime：PASS

```text
python -m pytest tests/ -q --tb=no -p no:warnings
=> 438 passed, 0 failed, 38.74s（< 5 分钟 PR 门禁）

DSL/compiler 快速集（7 个文件）：192 passed / 6.84s（< 15 秒预算）
编辑器自动化（15 个文件）：75 passed / 19.52s（< 60 秒预算）
python -m compileall -q main.py src game_content tools tests => 通过
python tools/validate_assets.py --format json => ok=true, 0 errors, 0 warnings
git diff --check / git diff --cached --check => 通过
```

- `tests/test_editor_program_tree.py` 使用真实 `QDragEnterEvent` /
  `QDragMoveEvent` / `QDropEvent` 事件投递到可见画布，从节点库真实 MIME 拖到
  四区（Before/After/Child/Wrap）、空根落点、If 双插槽、Parallel 新建分支、
  非法落点拒绝（无模型修改、无 Undo 记录）、折叠/悬停展开/自动滚动/闪烁。
- `tests/test_editor_palette_nodes.py`：37 个节点种类各自在合法上下文中从
  palette 工厂创建、经会话插入、保存、重开语义等价，并通过
  `PackageBuilder.build` 真实构建（含子进程 compileall/import 验证）。
- `tests/test_editor_unit_manager.py`：新建在保存前不落盘、复制重写全部 UID、
  引用阻止删除并列出跳转位置、删除注册 Stage 处理 Project 顺序、保存失败
  保留最近成功磁盘内容、连续数值编辑合并 Undo。

### Native：PASS

```text
清除 QT_QPA_PLATFORM 后：
python tools/verify_native_code_editor_dragflow.py --json
=> {"platform": "windows",
    "observations": [
      {"size": "1480x920", "parallel_card_width": 754,
       "side_by_side": true, "stacked_mode_reachable": true},
      {"size": "960x640", "parallel_card_width": 535,
       "side_by_side": true, "stacked_mode_reachable": true}]}
```

真实暴露的原生 PySide6 窗口内完成：节点库搜索、真实拖拽事件四区切换、
自动滚动、Inspector 数值修改、Undo/Redo；Parallel 分支在宽视口并排、300px
窄视口纵向堆叠。1480×920 与 960×640 两种尺寸均通过。GLFW/ModernGL 预览嵌入
属于 CD6 既有 gate（`tools/verify_native_code_editor.py`），本次未改动预览链路。

### Performance：PASS

- 全仓 `python -m pytest`：36-43s < 5 分钟；编辑器自动化 19.52s < 60 秒；
  DSL/compiler 快速集 6.84s < 15 秒。
- compileall 0.3s 左右；资产校验 0.5s 左右，79 JSON、0 error、0 warning。
- 代码量：本次交互重构净增约 1,909 行 / 净删 567 行（src + tests + tools，
  相对检查点 `d758990^`）。删除的旧交互代码：弹出式节点菜单与子菜单表、
  隐形四区坐标判定、QTreeWidget 程序树实现、重复的 palette 参数表。

### 卡死与崩溃修复（2026-08-29 追加）

维护者实测发现"选择插入模式并点击添加后长时间冻结、随后崩溃"。定位与修复：

- 根因一：`validate_insert` 每次克隆整个作者工程并做全量语义校验（实测
  21.8ms/次），节点库每次刷新对全部约 40 个条目各执行一次（实测 878ms/次），
  且每次选中/插入都会触发 2-3 层刷新级联，单次点击冻结 2.5 秒以上。
  修复：新增只校验插入点上下文的结构化 dry run（`_check_insert` +
  `_validate_node_in_context`），不克隆、不全量校验。实测 `validate_insert`
  0.1ms（约 218 倍）、节点库刷新 10.6ms（约 83 倍）、`refresh_selection`
  14.9ms（约 57 倍）。
- 根因二：节点库 `clear()` 在 `itemSelectionChanged` 信号派发期间再次重建并
  重入窗口刷新路径，属于 Qt 选择模型的未定义行为，会在反复交互时随机崩溃。
  修复：重建期间阻塞树信号、窗口 `refresh_selection` 增加重入守卫、节点库
  上下文未变化时跳过刷新；`tests/test_editor_palette.py` 新增回归测试断言
  选中节点库条目不会级联刷新、兼容性检查不克隆工程。
- 同步修正原生验证器对 Parallel 分支布局的断言：1480×920 必须并排，
  960×640 是规格中的"小窗口"，必须纵向堆叠。
- 全量门禁复验：439 passed / 40.2s；原生验证器 PASS。

### 预览与拖拽可用性修复（2026-08-30 追加）

维护者反馈四项问题，全部修复：

1. **检查器白色背景**：全局深色样式未覆盖 `QScrollArea` 及其内容部件。已补充
   `QScrollArea` 深色背景与透明内容规则，检查器与全窗一致。
2. **预览超出宿主看不全**：`PreviewHost._sync_size` 之前用 Qt 逻辑像素直接
   `MoveWindow`（物理像素坐标），且无视宽高比。现在按设备像素比换算并以信箱式
   保持宽高比居中适配，游戏窗口任何宿主尺寸下完整可见。原生验证器契约同步更新：
   三个预览目标（Project/Stage/Spell）实测 294×227 信箱适配 294×667 / 294×387
   宿主，`tools/verify_native_code_editor_preview.py` 与
   `tools/verify_native_code_editor.py` PASS。
3. **时间线定位预览**：时间线标尺与泳道空白处支持点击/拖拽选择目标帧（黄色虚线
   幽灵播放头 + 帧号），松开一次提交 seek（从 0 重算快进）；工具栏新增暂停/继续
   按钮与"快进到目标帧 %"进度条（seeking 状态按 frame 事件实时推进，红色播放头
   跟随当前帧）。`main.py` 的 seeking 状态事件接入 `EditorSession` 状态机。
4. **四区命中区太小**：卡片拖拽不再依赖 34px 高卡片内的四分区，改为悬浮
   280×180 放大面板（锚定目标卡片中心、视口内钳制），四区大标签、命中区约
   60-140px；目标卡片同步显示插入指示（前/后=粗线，子项=实线框，包裹=虚线框）。
   光标在面板内时面板优先，避免被下层卡片抢占锚定。

复验：全仓 439 passed / 26.1s；`verify_native_code_editor_dragflow.py`、
`verify_native_code_editor_preview.py`、`verify_native_code_editor.py`、
`verify_native_code_editor_layout.py` 四个真实 Windows 门禁全部 PASS。

### Usability：not run

维护者尚未实际完成完整工作流（新建 Wave/Enemy、拖出 Repeat/Wait/Fire、包裹、
加入 Stage、修改参数、保存重开并运行预览）。所有自动化与原生验证均不可替代
真人操作证据。
