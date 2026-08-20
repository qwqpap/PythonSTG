import{c as s,Q as n,j as e,m as p}from"./chunks/framework.DK3sgdKX.js";const u=JSON.parse('{"title":"编辑器架构边界","description":"","frontmatter":{},"headers":[],"relativePath":"EDITOR_ARCHITECTURE.md","filePath":"EDITOR_ARCHITECTURE.md","lastUpdated":1787235170000}'),i={name:"EDITOR_ARCHITECTURE.md"};function l(t,a,o,c,r,d){return n(),e("div",null,[...a[0]||(a[0]=[p(`<h1 id="编辑器架构边界" tabindex="-1">编辑器架构边界 <a class="header-anchor" href="#编辑器架构边界" aria-label="Permalink to &quot;编辑器架构边界&quot;">​</a></h1><p>本文是 PySTG 作者编辑器的稳定工程边界。具体实施顺序、任务状态和验收证据只记录在 <a href="./EDITOR_IMPLEMENTATION_TODO"><code>EDITOR_IMPLEMENTATION_TODO.md</code></a>。</p><p>当前 <code>main</code> 仍处于过渡结构：<code>EditorMainWindow</code> 已按 Mixin 拆文件，但共享状态、全局刷新、预览、插件和无 Qt 模块边界尚未真正分离。N7 已暂停；必须先完成 Todo 中的 ER0–ER8，再进行 N6.4 人工可用性验收。</p><p>本文描述的是整改完成后的目标结构。目标目录在对应 ER 任务开始前可以不存在；不得为了“看起来已经开始”创建空包、占位类或没有调用者的门面。</p><h2 id="_1-固定原则" tabindex="-1">1. 固定原则 <a class="header-anchor" href="#_1-固定原则" aria-label="Permalink to &quot;1. 固定原则&quot;">​</a></h2><ol><li>作者文档是唯一真源；生成的 Python 只是可选导出。</li><li>Qt 控件只显示状态、收集输入并发出有类型的编辑意图，不能直接修改作者文档。</li><li>所有作者修改经过领域 <code>Command</code> 和同一文档的 <code>CommandStack</code>。</li><li>选择、缩放、播放头和运行时 overlay 是临时编辑状态，不序列化、不制造 dirty。</li><li>预览必须复用正式 compiler/runner/renderer；结构模拟不能冒充正式预览。</li><li>高密度弹幕保留在批量池中，不能展开成场景树节点或逐弹 Python 回调。</li><li><code>src.authoring</code>、<code>src.compiler</code>、<code>src.preview</code> 和 runtime 不得依赖 <code>src.editor</code> 或 Qt。</li><li>窗口只拥有一个文档控制入口、一个预览会话入口和一个插件贡献入口。</li><li>迁移期间旧路径可以做无逻辑的兼容导出；新实现不能继续写入旧模块。</li><li>架构整改必须保持现有作者语义，不顺手重做时间线、行为图、schema、渲染器或 N7。</li></ol><h2 id="_2-固定依赖方向" tabindex="-1">2. 固定依赖方向 <a class="header-anchor" href="#_2-固定依赖方向" aria-label="Permalink to &quot;2. 固定依赖方向&quot;">​</a></h2><div class="language-text vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">text</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>Qt Panels</span></span>
<span class="line"><span>    ↓ typed editor intents</span></span>
<span class="line"><span>EditorCoordinator</span></span>
<span class="line"><span>    ↓ domain commands</span></span>
<span class="line"><span>Authoring documents</span></span>
<span class="line"><span>    ↓ compiler facade</span></span>
<span class="line"><span>Runtime programs / formal preview</span></span>
<span class="line"><span>    ↓</span></span>
<span class="line"><span>Runtime / renderer / resource service</span></span></code></pre></div><p>横向服务只允许以下方向：</p><div class="language-text vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">text</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>Qt Shell → EditorCoordinator</span></span>
<span class="line"><span>Qt Shell → PreviewSession</span></span>
<span class="line"><span>Qt Shell → EditorPluginRegistry facade</span></span>
<span class="line"><span></span></span>
<span class="line"><span>Panels → editor/application/intents.py</span></span>
<span class="line"><span>Panels → editor/state read-only snapshots</span></span>
<span class="line"><span></span></span>
<span class="line"><span>Editor preview adapter → src.preview protocol/controller</span></span>
<span class="line"><span>Editor plugin adapter → headless plugin/resource registries</span></span></code></pre></div><p>以下依赖一律禁止：</p><div class="language-text vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">text</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>src.authoring → src.editor</span></span>
<span class="line"><span>src.compiler  → src.editor</span></span>
<span class="line"><span>src.preview   → src.editor</span></span>
<span class="line"><span>runtime       → src.editor or Qt</span></span>
<span class="line"><span>domain Command → Qt</span></span>
<span class="line"><span>Panel → direct AuthoringDocument mutation</span></span>
<span class="line"><span>Panel A → Panel B private method</span></span>
<span class="line"><span>compiler/runtime → editor state</span></span></code></pre></div><h2 id="_3-目标目录" tabindex="-1">3. 目标目录 <a class="header-anchor" href="#_3-目标目录" aria-label="Permalink to &quot;3. 目标目录&quot;">​</a></h2><div class="language-text vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">text</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>src/</span></span>
<span class="line"><span>├─ authoring/</span></span>
<span class="line"><span>│  ├─ document_types.py       # AuthoringDocument Protocol、支持类型和公共能力</span></span>
<span class="line"><span>│  ├─ scene/</span></span>
<span class="line"><span>│  │  ├─ document.py          # SceneDocument 聚合根</span></span>
<span class="line"><span>│  │  ├─ nodes.py             # EditorNode 与场景树数据</span></span>
<span class="line"><span>│  │  ├─ state_graph.py       # State、Transition 和状态图数据</span></span>
<span class="line"><span>│  │  └─ timeline.py          # Track、Clip、Keyframe 和激活数据</span></span>
<span class="line"><span>│  ├─ commands/</span></span>
<span class="line"><span>│  │  ├─ base.py              # Command、CompositeCommand、CommandStack</span></span>
<span class="line"><span>│  │  ├─ scene.py</span></span>
<span class="line"><span>│  │  ├─ timeline.py</span></span>
<span class="line"><span>│  │  ├─ graph.py</span></span>
<span class="line"><span>│  │  ├─ pattern.py</span></span>
<span class="line"><span>│  │  ├─ ui.py</span></span>
<span class="line"><span>│  │  └─ background.py</span></span>
<span class="line"><span>│  ├─ registry.py             # 无 Qt 的资源 loader/validator/compiler/preview 注册</span></span>
<span class="line"><span>│  └─ storage.py              # 项目内加载、保存、迁移、autosave/recovery</span></span>
<span class="line"><span>│</span></span>
<span class="line"><span>├─ compiler/</span></span>
<span class="line"><span>│  ├─ facade.py               # 按正式资源类型分派编译，不按编辑器控件分派</span></span>
<span class="line"><span>│  ├─ diagnostics.py          # 统一、可定位、可序列化的编译诊断</span></span>
<span class="line"><span>│  ├─ stage.py                # SceneDocument → StageProgram</span></span>
<span class="line"><span>│  └─ scene_spell.py          # 无脚本 Spell → Pattern/Stage 正式表示</span></span>
<span class="line"><span>│</span></span>
<span class="line"><span>├─ preview/</span></span>
<span class="line"><span>│  ├─ protocol.py             # 无 Qt 的版本化 JSON 消息</span></span>
<span class="line"><span>│  ├─ controller.py           # compiler/runner 的正式控制器</span></span>
<span class="line"><span>│  └─ server.py               # 预览子进程入口和资源生命周期</span></span>
<span class="line"><span>│</span></span>
<span class="line"><span>└─ editor/</span></span>
<span class="line"><span>   ├─ app.py                  # CLI、ProjectContext 发现、create_window；不放领域逻辑</span></span>
<span class="line"><span>   ├─ shell/</span></span>
<span class="line"><span>   │  ├─ main_window.py       # QMainWindow 组装</span></span>
<span class="line"><span>   │  ├─ actions.py           # 菜单、快捷键和启用状态</span></span>
<span class="line"><span>   │  ├─ docks.py             # Dock/Tab 创建与布局</span></span>
<span class="line"><span>   │  └─ lifecycle.py         # 启动、关闭、窗口布局恢复</span></span>
<span class="line"><span>   ├─ application/</span></span>
<span class="line"><span>   │  ├─ coordinator.py       # 编辑意图、Command 派发、选择同步、局部失效</span></span>
<span class="line"><span>   │  ├─ document_controller.py # 打开、保存、激活、关闭、Undo/Redo</span></span>
<span class="line"><span>   │  ├─ intents.py           # 有类型的 UI 编辑请求；不携带 QWidget</span></span>
<span class="line"><span>   │  ├─ invalidation.py      # 有限的面板更新范围</span></span>
<span class="line"><span>   │  └─ ports.py             # Coordinator 所需的最小公开面板接口</span></span>
<span class="line"><span>   ├─ state/</span></span>
<span class="line"><span>   │  ├─ selection.py         # 每文档选择状态</span></span>
<span class="line"><span>   │  ├─ view_state.py        # 每文档播放头、缩放和工作区模式</span></span>
<span class="line"><span>   │  └─ runtime_overlay.py   # PreviewSession 产生的只读快照</span></span>
<span class="line"><span>   ├─ panels/</span></span>
<span class="line"><span>   │  ├─ scene.py</span></span>
<span class="line"><span>   │  ├─ inspector.py</span></span>
<span class="line"><span>   │  ├─ timeline.py</span></span>
<span class="line"><span>   │  ├─ state_graph.py</span></span>
<span class="line"><span>   │  ├─ graph.py</span></span>
<span class="line"><span>   │  ├─ pattern.py</span></span>
<span class="line"><span>   │  ├─ variables.py</span></span>
<span class="line"><span>   │  ├─ ui.py</span></span>
<span class="line"><span>   │  └─ background.py</span></span>
<span class="line"><span>   ├─ graphics/</span></span>
<span class="line"><span>   │  ├─ canvas.py            # 共享画布交互、坐标和搜索手势</span></span>
<span class="line"><span>   │  └─ graph_items.py       # 共享节点、端口、连线图元</span></span>
<span class="line"><span>   ├─ preview/</span></span>
<span class="line"><span>   │  ├─ session.py           # 唯一的编辑器预览状态机</span></span>
<span class="line"><span>   │  ├─ process.py           # QProcess、超时、输出上限和关闭</span></span>
<span class="line"><span>   │  └─ host.py              # 正式渲染窗口嵌入</span></span>
<span class="line"><span>   └─ plugins/</span></span>
<span class="line"><span>      ├─ registry.py          # 窗口可见的唯一贡献入口和生命周期</span></span>
<span class="line"><span>      ├─ sdk_adapter.py       # 资源/节点/compiler/preview/Inspector contribution</span></span>
<span class="line"><span>      └─ workbench_adapter.py # Qt 工具控件和外部开发工具</span></span></code></pre></div><p><code>src.pattern</code>、<code>src.ui</code>、<code>src.game.background_render</code> 和正式 runtime 继续拥有各自的领域实现；ER 不为了目录对称而搬迁已清晰归属的模块。</p><h2 id="_4-模块职责" tabindex="-1">4. 模块职责 <a class="header-anchor" href="#_4-模块职责" aria-label="Permalink to &quot;4. 模块职责&quot;">​</a></h2><h3 id="_4-1-qt-shell" tabindex="-1">4.1 Qt Shell <a class="header-anchor" href="#_4-1-qt-shell" aria-label="Permalink to &quot;4.1 Qt Shell&quot;">​</a></h3><p><code>src/editor/app.py</code> 只负责参数解析、<code>ProjectContext</code> 和窗口创建。<code>shell/main_window.py</code> 只负责创建窗口、连接公开端口以及关闭顶层服务。</p><p>整改完成后，<code>EditorMainWindow</code>：</p><ul><li>不继承领域 <code>SlotsMixin</code>；</li><li>不导入 Scene/Timeline/Graph/Pattern Command；</li><li>不持有裸预览 <code>QProcess</code>；</li><li>不读写字符串键编辑状态；</li><li>不按资源类型编译或运行；</li><li>不调用面板私有方法。</li></ul><p>窗口语言切换可以请求所有面板重新翻译，但不能借此重新创建作者文档或运行时会话。</p><h3 id="_4-2-editorcoordinator" tabindex="-1">4.2 EditorCoordinator <a class="header-anchor" href="#_4-2-editorcoordinator" aria-label="Permalink to &quot;4.2 EditorCoordinator&quot;">​</a></h3><p>Coordinator 是普通应用对象，不是 Qt 控件，也不是第二套文档模型。职责只有：</p><ol><li>接收 <code>EditorIntent</code>；</li><li>根据活动文档和选择验证请求；</li><li>创建并提交领域 Command；</li><li>更新临时选择/视图状态；</li><li>返回明确的 <code>InvalidationSet</code>；</li><li>将预览只读快照路由给其所属文档。</li></ol><p>Coordinator 不实现绘制、不保存 QWidget、不访问 renderer/pool/manager，也不把运行时状态写入作者文档。</p><h3 id="_4-3-局部失效" tabindex="-1">4.3 局部失效 <a class="header-anchor" href="#_4-3-局部失效" aria-label="Permalink to &quot;4.3 局部失效&quot;">​</a></h3><p>普通编辑不能调用“重建所有面板”的刷新器。失效范围必须是有限集合，例如：</p><div class="language-text vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">text</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span>SCENE_TREE</span></span>
<span class="line"><span>SCENE_CANVAS</span></span>
<span class="line"><span>INSPECTOR</span></span>
<span class="line"><span>TIMELINE</span></span>
<span class="line"><span>STATE_GRAPH</span></span>
<span class="line"><span>VARIABLES</span></span>
<span class="line"><span>PATTERN</span></span>
<span class="line"><span>UI_CANVAS</span></span>
<span class="line"><span>BACKGROUND</span></span>
<span class="line"><span>ACTIONS</span></span>
<span class="line"><span>TITLE</span></span></code></pre></div><p>只有首次打开文档、活动文档切换和 schema 迁移后重新绑定允许请求完整文档同步。语言切换只更新作者可见文本。运行时帧反馈只更新 overlay 消费者。</p><h3 id="_4-4-panel" tabindex="-1">4.4 Panel <a class="header-anchor" href="#_4-4-panel" aria-label="Permalink to &quot;4.4 Panel&quot;">​</a></h3><p>Panel 可以：</p><ul><li>渲染作者文档和只读编辑状态；</li><li>进行局部命中测试、拖动预览和表单校验；</li><li>发出包含稳定资源/节点 ID 和精确值的 <code>EditorIntent</code>；</li><li>暴露 Coordinator 所需的公开更新端口。</li></ul><p>Panel 不可以：</p><ul><li>直接改变文档字段；</li><li>自己 push <code>CommandStack</code>；</li><li>调用另一个 Panel 的私有槽；</li><li>保存另一个视图的对象指针；</li><li>创建 compiler、runner、renderer 或全局资源 manager。</li></ul><p>拖动过程可以保留暂态图元；鼠标释放时只发出一次可撤销提交。真实鼠标手势测试不能用直接调用最终槽函数替代。</p><h2 id="_5-文档与临时状态所有权" tabindex="-1">5. 文档与临时状态所有权 <a class="header-anchor" href="#_5-文档与临时状态所有权" aria-label="Permalink to &quot;5. 文档与临时状态所有权&quot;">​</a></h2><p><code>AuthoringDocument</code> 是结构化能力 Protocol，而不是新的文档基类。它至少固定 <code>id</code>、<code>type</code>、<code>schema_version</code>、<code>to_dict()</code>、<code>from_dict()</code> 和 <code>validate()</code>；Scene、Pattern、UI、Background 可以保留各自实现。</p><p><code>ManagedDocument</code> 只拥有：</p><ul><li>一个受支持的 <code>AuthoringDocument</code>；</li><li>路径、保存快照和 dirty 计算；</li><li>一个 <code>CommandStack</code>；</li><li>一个有类型的 <code>DocumentEditorState</code>，其中只有选择和视图状态。</li></ul><p>状态生命周期固定为：</p><table tabindex="0"><thead><tr><th>状态</th><th>所有者</th><th>是否序列化</th><th>清理时机</th></tr></thead><tbody><tr><td>作者文档</td><td><code>ManagedDocument</code></td><td>是</td><td>关闭文档</td></tr><tr><td>Undo/Redo</td><td><code>ManagedDocument</code></td><td>否</td><td>关闭、替换或明确 reset</td></tr><tr><td>选择状态</td><td><code>DocumentEditorState</code></td><td>否</td><td>关闭文档；删除目标时校正</td></tr><tr><td>视图状态</td><td><code>DocumentEditorState</code></td><td>否</td><td>关闭文档</td></tr><tr><td>运行时 overlay</td><td><code>PreviewSession</code></td><td>否</td><td>stop/reset/进程退出/所有者文档关闭</td></tr><tr><td>窗口布局</td><td>Qt Shell</td><td>编辑器配置</td><td>显式恢复默认布局</td></tr></tbody></table><p>不得再使用 <code>dict[str, Any]</code> 和隐式字符串键混合这些状态。</p><h2 id="_6-authoring-与-compiler" tabindex="-1">6. Authoring 与 Compiler <a class="header-anchor" href="#_6-authoring-与-compiler" aria-label="Permalink to &quot;6. Authoring 与 Compiler&quot;">​</a></h2><ul><li><code>src.authoring.registry</code> 是 headless 注册表，不得导入任何 editor factory。</li><li>loader/validator/compiler/preview handler 以稳定资源 type ID 关联。</li><li>Qt editor factory 属于 <code>src.editor.plugins</code> 的 Tool contribution，通过同一 type ID 关联，但不进入 headless registry 的导入图。</li><li><code>src.compiler.facade</code> 是 Scene/Pattern/UI/Background 编译的统一入口；它选择资源 compiler，不观察当前 Tab 或 QWidget 类型。</li><li>诊断必须包含稳定 code、资源 URI 和属性/节点/规则路径。</li><li>编译器只产生正式 runtime 数据，不创建 Qt 对象或 editor overlay。</li></ul><p>迁移完成前，<code>src/editor/document.py</code>、<code>src/editor/stage_compile.py</code>、<code>src/editor/scene_compile.py</code> 等旧路径可以保留兼容导出。兼容文件只能 import/re-export 新实现和转发公共调用，不得保存第二份逻辑。</p><h2 id="_7-previewsession" tabindex="-1">7. PreviewSession <a class="header-anchor" href="#_7-previewsession" aria-label="Permalink to &quot;7. PreviewSession&quot;">​</a></h2><p>编辑器只有一个活动预览会话状态机。它可以有两种明确模式：</p><ul><li><code>formal_authoring</code>：Pattern/Stage/Scene 作者资源经版本化 JSON 协议进入正式 controller/runner/renderer；</li><li><code>legacy_game_run</code>：明确运行旧 Stage 或脚本入口，用于仍未迁移的内容。</li></ul><p>两种模式共享启动、停止、错误、超时、输出上限、活动文档 identity 和关闭规则，但不能把 legacy 结果标成 formal preview。</p><p><code>PreviewSession</code> 必须：</p><ul><li>拒绝并发启动第二个预览；</li><li>将每条反馈绑定到加载时的文档 identity；</li><li>在 stop/reset/崩溃/关闭时清理 overlay 和子进程；</li><li>通过正式协议报告结构化错误；</li><li>让 <code>RuntimePreviewHost</code> 只负责嵌入，不拥有进程生命周期。</li></ul><p>外部资产编辑工具由独立的 <code>ToolProcessManager</code> 或 workbench adapter 管理，不计入游戏预览状态机。</p><h2 id="_8-插件贡献" tabindex="-1">8. 插件贡献 <a class="header-anchor" href="#_8-插件贡献" aria-label="Permalink to &quot;8. 插件贡献&quot;">​</a></h2><p>窗口只能看到一个 <code>EditorPluginRegistry</code> facade。内部可以适配：</p><ul><li>headless SDK contribution：资源类型、节点类型、compiler、preview handler、命令和 Inspector editor；</li><li>Qt workbench contribution：中心/底部工具控件和外部工具进程。</li></ul><p>Facade 统一插件 identity、依赖、激活状态、失败回滚、停用和清理。适配器不能形成两个互不知情的生命周期。插件注册上下文不能暴露窗口、内部 registry 或全局 runtime 对象。</p><h2 id="_9-图形工作区" tabindex="-1">9. 图形工作区 <a class="header-anchor" href="#_9-图形工作区" aria-label="Permalink to &quot;9. 图形工作区&quot;">​</a></h2><p>Scene、Pattern 和 Behavior Graph 可以复用 <code>editor/graphics</code> 中的画布手势和图元，但不能互相导入具体 Panel。<code>graph.py</code> 与 <code>pattern.py</code> 的组合由 Shell 完成，或通过公开 Port/Intent 协调。</p><p>必须消除当前 <code>graph_workspace ↔ pattern_workspace</code> 循环；不得继续依赖函数内 import 掩盖循环。</p><h2 id="_10-项目、资源、坐标与时间" tabindex="-1">10. 项目、资源、坐标与时间 <a class="header-anchor" href="#_10-项目、资源、坐标与时间" aria-label="Permalink to &quot;10. 项目、资源、坐标与时间&quot;">​</a></h2><ul><li><code>project.pystg.json</code> 标识项目并声明内容目录。</li><li><code>ProjectContext</code> 是项目根路径的唯一发现和解析入口。</li><li>新代码不得依赖当前工作目录推测 <code>assets/</code>、<code>game_content/</code> 或工具路径。</li><li>所有作者资源继续使用 <code>*.pystg.json</code> 和稳定 type ID。</li><li>公共资源头、引用、迁移、坐标和时间契约见 <a href="./AUTHORING_RESOURCE_CONTRACTS"><code>AUTHORING_RESOURCE_CONTRACTS.md</code></a>。</li><li>作者画布使用固定逻辑像素 <code>384x448</code>，左上原点、Y 向下。</li><li>正式运行时以画面中心为原点，X/Y 为 <code>[-1, 1]</code>、Y 向上。</li><li>只能通过 <code>CoordinateSpace</code> 转换坐标。</li><li>文档时间使用声明 tick rate 下的非负整数帧；秒和拍只用于显示/输入。</li><li><code>ResourceService</code> 继续负责正式运行时纹理目录和富编辑兼容模型；窗口不得自己创建全局资源 manager。</li></ul><h2 id="_11-迁移纪律" tabindex="-1">11. 迁移纪律 <a class="header-anchor" href="#_11-迁移纪律" aria-label="Permalink to &quot;11. 迁移纪律&quot;">​</a></h2><ol><li>先由 Contract 固定目标行为和禁止依赖，再移动实现。</li><li>每次只迁移一个明确所有权边界；不进行全仓机械搬家后再修错误。</li><li>旧路径先变为兼容导出，仓库内部引用归零后才能删除。</li><li>移动前后同一作者资源的 canonical JSON、编译结果和 runtime identity 必须一致。</li><li>schema 版本是普通整数；旧版本通过显式 migration，不得重载相等比较。</li><li><code>SceneEditorSession</code> 只能在调用者迁移后降为兼容工厂或删除，不能与 <code>DocumentManager</code> 并存两套保存/Undo 生命周期。</li><li>任何无法无损迁移的 schema、预览或插件生命周期冲突都必须停止并请求维护者决定。</li></ol><h2 id="_12-agent-文件所有权" tabindex="-1">12. Agent 文件所有权 <a class="header-anchor" href="#_12-agent-文件所有权" aria-label="Permalink to &quot;12. Agent 文件所有权&quot;">​</a></h2><p>仓库根 <code>AGENTS.md</code> 固定通用所有权和交付纪律；每个 ER 任务还会在 Todo 中列出允许路径、禁止路径和验收文件。若两者冲突，以更窄的任务边界为准。</p><p>只有主协调 Agent 可以更新任务状态。实现 Agent 不能验收自己的最终门禁；验证 Agent 不得修产品代码或改测试断言。</p><h2 id="_13-合入门槛" tabindex="-1">13. 合入门槛 <a class="header-anchor" href="#_13-合入门槛" aria-label="Permalink to &quot;13. 合入门槛&quot;">​</a></h2><p>共同命令：</p><div class="language-powershell vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">powershell</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">$</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">env:</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">QT_QPA_PLATFORM </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">=</span><span style="--shiki-light:#032F62;--shiki-dark:#9ECBFF;"> &quot;offscreen&quot;</span></span>
<span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">python </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">-</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">m pytest </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">-</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">q</span></span>
<span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">python </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">-</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">m compileall </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">-</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">q main.py src game_content tools tests</span></span>
<span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">python tools</span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">/</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">validate_assets.py </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">--</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">format json</span></span>
<span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">git diff </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">--</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">check</span></span></code></pre></div><p>ER 还必须通过：</p><ul><li><code>tests/test_editor_architecture_boundaries.py</code>：禁止依赖、Qt 边界、循环和兼容出口；</li><li>当前任务的 focused 行为测试；</li><li>真实 PySide6 1480×920 与 960×640 窗口；</li><li>时间线和行为图真实鼠标手势；</li><li>正式 Pattern/Stage 预览启动、反馈、停止、异常退出和编辑器关闭；</li><li>固定弹幕 workload，确认批量写入和逐弹回调没有退化；</li><li>ER8 之后按 <code>N6_USABILITY_PROTOCOL.md</code> 完成 N6.4。</li></ul><p>Structural、Runtime、Native visual、Performance 和 Usability 必须分别报告。自动测试、offscreen Qt、<code>--help</code>、模拟截图或单一“全绿”数字不能替代原生、性能或人工证据。</p>`,72)])])}const m=s(i,[["render",l]]);export{u as __pageData,m as default};
