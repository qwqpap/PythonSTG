# 编辑器架构边界

本文是 PySTG 作者编辑器的稳定工程边界。具体实施顺序、任务状态和验收证据只记录在
[`EDITOR_IMPLEMENTATION_TODO.md`](EDITOR_IMPLEMENTATION_TODO.md)。

当前 `main` 仍处于过渡结构：`EditorMainWindow` 已按 Mixin 拆文件，但共享状态、全局刷新、预览、插件和无 Qt 模块边界尚未真正分离。N7 已暂停；必须先完成 Todo 中的 ER0–ER8，再进行 N6.4 人工可用性验收。

本文描述的是整改完成后的目标结构。目标目录在对应 ER 任务开始前可以不存在；不得为了“看起来已经开始”创建空包、占位类或没有调用者的门面。

## 1. 固定原则

1. 作者文档是唯一真源；生成的 Python 只是可选导出。
2. Qt 控件只显示状态、收集输入并发出有类型的编辑意图，不能直接修改作者文档。
3. 所有作者修改经过领域 `Command` 和同一文档的 `CommandStack`。
4. 选择、缩放、播放头和运行时 overlay 是临时编辑状态，不序列化、不制造 dirty。
5. 预览必须复用正式 compiler/runner/renderer；结构模拟不能冒充正式预览。
6. 高密度弹幕保留在批量池中，不能展开成场景树节点或逐弹 Python 回调。
7. `src.authoring`、`src.compiler`、`src.preview` 和 runtime 不得依赖 `src.editor` 或 Qt。
8. 窗口只拥有一个文档控制入口、一个预览会话入口和一个插件贡献入口。
9. 迁移期间旧路径可以做无逻辑的兼容导出；新实现不能继续写入旧模块。
10. 架构整改必须保持现有作者语义，不顺手重做时间线、行为图、schema、渲染器或 N7。

## 2. 固定依赖方向

```text
Qt Panels
    ↓ typed editor intents
EditorCoordinator
    ↓ domain commands
Authoring documents
    ↓ compiler facade
Runtime programs / formal preview
    ↓
Runtime / renderer / resource service
```

横向服务只允许以下方向：

```text
Qt Shell → EditorCoordinator
Qt Shell → PreviewSession
Qt Shell → EditorPluginRegistry facade

Panels → editor/application/intents.py
Panels → editor/state read-only snapshots

Editor preview adapter → src.preview protocol/controller
Editor plugin adapter → headless plugin/resource registries
```

以下依赖一律禁止：

```text
src.authoring → src.editor
src.compiler  → src.editor
src.preview   → src.editor
runtime       → src.editor or Qt
domain Command → Qt
Panel → direct AuthoringDocument mutation
Panel A → Panel B private method
compiler/runtime → editor state
```

## 3. 目标目录

```text
src/
├─ authoring/
│  ├─ document_types.py       # AuthoringDocument Protocol、支持类型和公共能力
│  ├─ scene/
│  │  ├─ document.py          # SceneDocument 聚合根
│  │  ├─ nodes.py             # EditorNode 与场景树数据
│  │  ├─ state_graph.py       # State、Transition 和状态图数据
│  │  └─ timeline.py          # Track、Clip、Keyframe 和激活数据
│  ├─ commands/
│  │  ├─ base.py              # Command、CompositeCommand、CommandStack
│  │  ├─ scene.py
│  │  ├─ timeline.py
│  │  ├─ graph.py
│  │  ├─ pattern.py
│  │  ├─ ui.py
│  │  └─ background.py
│  ├─ registry.py             # 无 Qt 的资源 loader/validator/compiler/preview 注册
│  └─ storage.py              # 项目内加载、保存、迁移、autosave/recovery
│
├─ compiler/
│  ├─ facade.py               # 按正式资源类型分派编译，不按编辑器控件分派
│  ├─ diagnostics.py          # 统一、可定位、可序列化的编译诊断
│  ├─ stage.py                # SceneDocument → StageProgram
│  └─ scene_spell.py          # 无脚本 Spell → Pattern/Stage 正式表示
│
├─ preview/
│  ├─ protocol.py             # 无 Qt 的版本化 JSON 消息
│  ├─ controller.py           # compiler/runner 的正式控制器
│  └─ server.py               # 预览子进程入口和资源生命周期
│
└─ editor/
   ├─ app.py                  # CLI、ProjectContext 发现、create_window；不放领域逻辑
   ├─ shell/
   │  ├─ main_window.py       # QMainWindow 组装
   │  ├─ actions.py           # 菜单、快捷键和启用状态
   │  ├─ docks.py             # Dock/Tab 创建与布局
   │  └─ lifecycle.py         # 启动、关闭、窗口布局恢复
   ├─ application/
   │  ├─ coordinator.py       # 编辑意图、Command 派发、选择同步、局部失效
   │  ├─ document_controller.py # 打开、保存、激活、关闭、Undo/Redo
   │  ├─ intents.py           # 有类型的 UI 编辑请求；不携带 QWidget
   │  ├─ invalidation.py      # 有限的面板更新范围
   │  └─ ports.py             # Coordinator 所需的最小公开面板接口
   ├─ state/
   │  ├─ selection.py         # 每文档选择状态
   │  ├─ view_state.py        # 每文档播放头、缩放和工作区模式
   │  └─ runtime_overlay.py   # PreviewSession 产生的只读快照
   ├─ panels/
   │  ├─ scene.py
   │  ├─ inspector.py
   │  ├─ timeline.py
   │  ├─ state_graph.py
   │  ├─ graph.py
   │  ├─ pattern.py
   │  ├─ variables.py
   │  ├─ ui.py
   │  └─ background.py
   ├─ graphics/
   │  ├─ canvas.py            # 共享画布交互、坐标和搜索手势
   │  └─ graph_items.py       # 共享节点、端口、连线图元
   ├─ preview/
   │  ├─ session.py           # 唯一的编辑器预览状态机
   │  ├─ process.py           # QProcess、超时、输出上限和关闭
   │  └─ host.py              # 正式渲染窗口嵌入
   └─ plugins/
      ├─ registry.py          # 窗口可见的唯一贡献入口和生命周期
      ├─ sdk_adapter.py       # 资源/节点/compiler/preview/Inspector contribution
      └─ workbench_adapter.py # Qt 工具控件和外部开发工具
```

`src.pattern`、`src.ui`、`src.game.background_render` 和正式 runtime 继续拥有各自的领域实现；ER 不为了目录对称而搬迁已清晰归属的模块。

## 4. 模块职责

### 4.1 Qt Shell

`src/editor/app.py` 只负责参数解析、`ProjectContext` 和窗口创建。`shell/main_window.py` 只负责创建窗口、连接公开端口以及关闭顶层服务。

整改完成后，`EditorMainWindow`：

- 不继承领域 `SlotsMixin`；
- 不导入 Scene/Timeline/Graph/Pattern Command；
- 不持有裸预览 `QProcess`；
- 不读写字符串键编辑状态；
- 不按资源类型编译或运行；
- 不调用面板私有方法。

窗口语言切换可以请求所有面板重新翻译，但不能借此重新创建作者文档或运行时会话。

### 4.2 EditorCoordinator

Coordinator 是普通应用对象，不是 Qt 控件，也不是第二套文档模型。职责只有：

1. 接收 `EditorIntent`；
2. 根据活动文档和选择验证请求；
3. 创建并提交领域 Command；
4. 更新临时选择/视图状态；
5. 返回明确的 `InvalidationSet`；
6. 将预览只读快照路由给其所属文档。

Coordinator 不实现绘制、不保存 QWidget、不访问 renderer/pool/manager，也不把运行时状态写入作者文档。

### 4.3 局部失效

普通编辑不能调用“重建所有面板”的刷新器。失效范围必须是有限集合，例如：

```text
SCENE_TREE
SCENE_CANVAS
INSPECTOR
TIMELINE
STATE_GRAPH
VARIABLES
PATTERN
UI_CANVAS
BACKGROUND
ACTIONS
TITLE
```

只有首次打开文档、活动文档切换和 schema 迁移后重新绑定允许请求完整文档同步。语言切换只更新作者可见文本。运行时帧反馈只更新 overlay 消费者。

### 4.4 Panel

Panel 可以：

- 渲染作者文档和只读编辑状态；
- 进行局部命中测试、拖动预览和表单校验；
- 发出包含稳定资源/节点 ID 和精确值的 `EditorIntent`；
- 暴露 Coordinator 所需的公开更新端口。

Panel 不可以：

- 直接改变文档字段；
- 自己 push `CommandStack`；
- 调用另一个 Panel 的私有槽；
- 保存另一个视图的对象指针；
- 创建 compiler、runner、renderer 或全局资源 manager。

拖动过程可以保留暂态图元；鼠标释放时只发出一次可撤销提交。真实鼠标手势测试不能用直接调用最终槽函数替代。

## 5. 文档与临时状态所有权

`AuthoringDocument` 是结构化能力 Protocol，而不是新的文档基类。它至少固定 `id`、`type`、`schema_version`、`to_dict()`、`from_dict()` 和 `validate()`；Scene、Pattern、UI、Background 可以保留各自实现。

`ManagedDocument` 只拥有：

- 一个受支持的 `AuthoringDocument`；
- 路径、保存快照和 dirty 计算；
- 一个 `CommandStack`；
- 一个有类型的 `DocumentEditorState`，其中只有选择和视图状态。

状态生命周期固定为：

| 状态 | 所有者 | 是否序列化 | 清理时机 |
| --- | --- | --- | --- |
| 作者文档 | `ManagedDocument` | 是 | 关闭文档 |
| Undo/Redo | `ManagedDocument` | 否 | 关闭、替换或明确 reset |
| 选择状态 | `DocumentEditorState` | 否 | 关闭文档；删除目标时校正 |
| 视图状态 | `DocumentEditorState` | 否 | 关闭文档 |
| 运行时 overlay | `PreviewSession` | 否 | stop/reset/进程退出/所有者文档关闭 |
| 窗口布局 | Qt Shell | 编辑器配置 | 显式恢复默认布局 |

不得再使用 `dict[str, Any]` 和隐式字符串键混合这些状态。

## 6. Authoring 与 Compiler

- `src.authoring.registry` 是 headless 注册表，不得导入任何 editor factory。
- loader/validator/compiler/preview handler 以稳定资源 type ID 关联。
- Qt editor factory 属于 `src.editor.plugins` 的 Tool contribution，通过同一 type ID 关联，但不进入 headless registry 的导入图。
- `src.compiler.facade` 是 Scene/Pattern/UI/Background 编译的统一入口；它选择资源 compiler，不观察当前 Tab 或 QWidget 类型。
- 诊断必须包含稳定 code、资源 URI 和属性/节点/规则路径。
- 编译器只产生正式 runtime 数据，不创建 Qt 对象或 editor overlay。

迁移完成前，`src/editor/document.py`、`src/editor/stage_compile.py`、`src/editor/scene_compile.py` 等旧路径可以保留兼容导出。兼容文件只能 import/re-export 新实现和转发公共调用，不得保存第二份逻辑。

## 7. PreviewSession

编辑器只有一个活动预览会话状态机。它可以有两种明确模式：

- `formal_authoring`：Pattern/Stage/Scene 作者资源经版本化 JSON 协议进入正式 controller/runner/renderer；
- `legacy_game_run`：明确运行旧 Stage 或脚本入口，用于仍未迁移的内容。

两种模式共享启动、停止、错误、超时、输出上限、活动文档 identity 和关闭规则，但不能把 legacy 结果标成 formal preview。

`PreviewSession` 必须：

- 拒绝并发启动第二个预览；
- 将每条反馈绑定到加载时的文档 identity；
- 在 stop/reset/崩溃/关闭时清理 overlay 和子进程；
- 通过正式协议报告结构化错误；
- 让 `RuntimePreviewHost` 只负责嵌入，不拥有进程生命周期。

外部资产编辑工具由独立的 `ToolProcessManager` 或 workbench adapter 管理，不计入游戏预览状态机。

## 8. 插件贡献

窗口只能看到一个 `EditorPluginRegistry` facade。内部可以适配：

- headless SDK contribution：资源类型、节点类型、compiler、preview handler、命令和 Inspector editor；
- Qt workbench contribution：中心/底部工具控件和外部工具进程。

Facade 统一插件 identity、依赖、激活状态、失败回滚、停用和清理。适配器不能形成两个互不知情的生命周期。插件注册上下文不能暴露窗口、内部 registry 或全局 runtime 对象。

## 9. 图形工作区

Scene、Pattern 和 Behavior Graph 可以复用 `editor/graphics` 中的画布手势和图元，但不能互相导入具体 Panel。`graph.py` 与 `pattern.py` 的组合由 Shell 完成，或通过公开 Port/Intent 协调。

必须消除当前 `graph_workspace ↔ pattern_workspace` 循环；不得继续依赖函数内 import 掩盖循环。

## 10. 项目、资源、坐标与时间

- `project.pystg.json` 标识项目并声明内容目录。
- `ProjectContext` 是项目根路径的唯一发现和解析入口。
- 新代码不得依赖当前工作目录推测 `assets/`、`game_content/` 或工具路径。
- 所有作者资源继续使用 `*.pystg.json` 和稳定 type ID。
- 公共资源头、引用、迁移、坐标和时间契约见
  [`AUTHORING_RESOURCE_CONTRACTS.md`](AUTHORING_RESOURCE_CONTRACTS.md)。
- 作者画布使用固定逻辑像素 `384x448`，左上原点、Y 向下。
- 正式运行时以画面中心为原点，X/Y 为 `[-1, 1]`、Y 向上。
- 只能通过 `CoordinateSpace` 转换坐标。
- 文档时间使用声明 tick rate 下的非负整数帧；秒和拍只用于显示/输入。
- `ResourceService` 继续负责正式运行时纹理目录和富编辑兼容模型；窗口不得自己创建全局资源 manager。

## 11. 迁移纪律

1. 先由 Contract 固定目标行为和禁止依赖，再移动实现。
2. 每次只迁移一个明确所有权边界；不进行全仓机械搬家后再修错误。
3. 旧路径先变为兼容导出，仓库内部引用归零后才能删除。
4. 移动前后同一作者资源的 canonical JSON、编译结果和 runtime identity 必须一致。
5. schema 版本是普通整数；旧版本通过显式 migration，不得重载相等比较。
6. `SceneEditorSession` 只能在调用者迁移后降为兼容工厂或删除，不能与 `DocumentManager` 并存两套保存/Undo 生命周期。
7. 任何无法无损迁移的 schema、预览或插件生命周期冲突都必须停止并请求维护者决定。

## 12. Agent 文件所有权

仓库根 `AGENTS.md` 固定通用所有权和交付纪律；每个 ER 任务还会在 Todo 中列出允许路径、禁止路径和验收文件。若两者冲突，以更窄的任务边界为准。

只有主协调 Agent 可以更新任务状态。实现 Agent 不能验收自己的最终门禁；验证 Agent 不得修产品代码或改测试断言。

## 13. 合入门槛

共同命令：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q main.py src game_content tools tests
python tools/validate_assets.py --format json
git diff --check
```

ER 还必须通过：

- `tests/test_editor_architecture_boundaries.py`：禁止依赖、Qt 边界、循环和兼容出口；
- 当前任务的 focused 行为测试；
- 真实 PySide6 1480×920 与 960×640 窗口；
- 时间线和行为图真实鼠标手势；
- 正式 Pattern/Stage 预览启动、反馈、停止、异常退出和编辑器关闭；
- 固定弹幕 workload，确认批量写入和逐弹回调没有退化；
- ER8 之后按 `N6_USABILITY_PROTOCOL.md` 完成 N6.4。

Structural、Runtime、Native visual、Performance 和 Usability 必须分别报告。自动测试、offscreen Qt、`--help`、模拟截图或单一“全绿”数字不能替代原生、性能或人工证据。
