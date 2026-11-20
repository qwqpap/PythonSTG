# 代码驱动关卡编辑器架构

本文定义 PySTG 代码驱动关卡编辑器的模块分层、数据协议与关键工程约束。产品定位见 [编辑器设计概览](EDITOR_PRODUCT_VISION.md)，引擎运行时结构见 [引擎架构概览](architecture.md)。

## 1. 依赖方向

编辑器核心（解析、模型、编译、Timeline 分析）完全 Headless，与 Qt 和 OpenGL 渲染器彻底解耦：

```text
Qt Widgets (src.editor)
    -> EditorSession + QUndoCommand
    -> Authoring Program & DSL (src.authoring)
    -> Restricted Python Source (game_content/authoring/<id>/)
    -> Deterministic Package Builder (src.compiler)
    -> Existing StageScript / StageManager / Pools / Renderer
```

预览以独立进程运行：

```text
PreviewOwner -> QProcess(main.py --content-entry ...)
PreviewHost  <- Native GLFW/ModernGL child window (Windows SetParent)
Timeline     <- Static program projection + bounded runtime Trace
```

以下反向依赖严格禁止：

- `src.authoring` / `src.compiler` 导入 `src.editor`、Qt 或 `src.render`
- 游戏运行时或生成代码导入 `src.editor` 或 Qt
- Timeline 独立持久化为第二份作者文档
- 面板私有维护第二份文档模型、第二个 `QUndoStack` 或第二条预览通道
- 生成包复制项目素材文件

## 2. 模块布局

```text
src/
├─ authoring/
│  ├─ program.py          # 逻辑单元、节点、值闭集、校验与纯模型操作
│  ├─ dsl.py              # 公开 DSL 构造函数与 @template 装饰器
│  ├─ python_source.py    # AST 解析、tokenize 注释保真、确定性写回与冲突状态
│  ├─ templates.py        # 模板签名绑定、内存展开与递归检测
│  └─ timeline.py         # Headless 静态时间推导与 Trace 叠加
├─ compiler/
│  ├─ diagnostics.py      # 稳定诊断码、源码位置与关联定位
│  ├─ codegen.py          # 逻辑单元到标准 Runtime Python 的代码生成
│  ├─ package_builder.py  # 临时目录构建、子进程验证与原子发布
│  └─ content_entry.py    # 入口模块校验与注册表加载
└─ editor/
   ├─ app.py              # CLI 入口、QApplication、ProjectContext、全局主题挂载
   ├─ window.py           # 主窗口布局、导航与动作接线
   ├─ session.py          # 单个工程的唯一状态所有者
   ├─ commands.py         # QUndoCommand 封装
   ├─ onboarding.py       # 欢迎页与新手引导
   ├─ starter_content.py  # 用普通 DSL 生成默认示例工程
   ├─ project_creation.py # 通过标准写回器创建新工程
   ├─ sidebars.py         # 调用链 / 全部单元 / 只读源码 / 资源侧栏
   ├─ node_palette.py     # 就地搜索弹窗与可选节点库
   ├─ program_tree.py     # 自定义绘制纵向程序流与拖拽落点计算
   ├─ inspector.py        # 基于 DSL 类型注解动态生成属性表单
   ├─ theme.py            # 单一颜色/间距/字号 token 与唯一应用级 QSS
   ├─ code_view.py        # 作者源码与生成代码只读视图
   ├─ output.py           # Problems 面板与有界日志视图
   ├─ timeline.py         # 静态区间、Trace 叠加与有限反向编辑控件
   └─ preview.py          # 单一 QProcess 控制、NDJSON 协议与 Win32 嵌入宿主
```

## 3. Headless 作者模型

### 3.1 值闭集

节点与单元参数只允许以下值类型：

- `None`、`bool`、`int`、`float`、`str`
- 上述类型组成的 `list`、`tuple` 和字符串键 `dict`
- `Ref(id: str)`、`Expr(source: str)`、`res://...` 资源引用、`TemplateCall`

模型在编辑期不执行 `Expr`；Inspector 文本输入统一调用 Headless 的 `parse_author_value`，禁止在 Qt 层使用 `eval`。

### 3.2 节点与逻辑单元

每个节点共享统一元数据：`uid`、`kind`、`arguments`、`children`、`source_span`、`comments`。`uid` 在工程内唯一且稳定，移动节点不改变 `uid`。

每个作者文件只定义一个主逻辑单元，固定字段包括 `kind`、`id`、`name`、`body`、`parameters`、`metadata` 和 `source_path`。`program.py` 暴露统一的 `unit_accepts_statements(kind) -> bool`（`Project` 与 `Boss` 返回 `False`，其余单元返回 `True`），底层校验与 Qt 界面共用这一判断。

### 3.3 纯模型操作

`program.py` 提供无 UI 副作用的操作：`insert_node`、`delete_node`、`move_node`、`wrap_node`、`set_argument`、`set_unit_field`。所有变更先在副本上校验，校验通过后原子提交。`QUndoCommand` 只记录前后状态并调用这些函数，不复制领域校验规则。

## 4. DSL 与 Runtime 镜像

`src.authoring.dsl` 的节点签名（参数名、类型注解与默认值）直接镜像运行时 `StageScript`、`Wave`、`EnemyScript`、`SpellCard` 的公共接口：

- 发射参数的弹型、颜色、tag、加速度、阻尼、反弹、自转、缩放、寿命和曲线均显式写在签名中，不藏在通用 `**kwargs` 里。
- Inspector 直接读取 DSL 构造函数类型注解生成字段控件，不维护单独的参数 JSON。
- 控制节点的子槽位约束：

| 节点 | 子槽位 | 说明 |
| --- | --- | --- |
| `Repeat` / `While` / `ForEach` / `At` | `body` | 语句列表 |
| `If` | `body`、`else_body` | 条件分支语句列表 |
| `Parallel` | `branches` | 多条并行语句列表 |
| `SpawnTask` | `body` 或 `task` | 内联语句块或 `Ref(task)` 二选一 |
| 动作节点 | 无 | 叶子节点 |

`Break`/`Continue` 仅允许位于循环内，`Return` 仅允许位于 `Task`/`Function` 或模板体内；`Call` / `SpawnTask` 的引用链在构建前会校验实际调用者能力（例如 `Stage` 不能借 `Task` 发弹）。

## 5. 源码协议与外部修改状态机

### 5.1 解析与格式化

- 加载工程仅通过 `ast` 静态解析，**不执行作者代码**。
- `tokenize` 负责将节点前注释、行尾注释和文件头注释绑定到稳定 `uid`。
- 写回器固定输出 UTF-8（无 BOM）、LF 换行、4 空格缩进、保留源 `import` 顺序与稳定关键字顺序。
- 不支持的顶层结构或表达式保留原始字节并以只读诊断模式打开，所有保存接口对只读文件必须明确拒绝。

### 5.2 外部文件同步状态机

```text
clean + empty undo + supported change   -> 自动重载
dirty or nonempty undo + disk change    -> 标记冲突并冻结保存
conflict + 用户选择保留内存               -> 确认后覆盖写回
conflict + 用户选择重载磁盘               -> 替换模型并清空 Undo 栈
any + unsupported disk structure        -> 只读诊断模式，保留磁盘原字节
```

单文件写入使用同目录临时文件 + `fsync` + `os.replace`；多文件保存先做磁盘与元状态快照，任一写入失败时整体回滚。删除单元在保存前采用可撤销墓碑标记，并继续接受外部修改监控。

## 6. 模板与诊断

- `@template` 通过 `module + qualname` 标识，`inspect.Signature` 校验参数。节点库展示外部模板签名时通过静态 AST 读取，不直接 `import` 执行外部模块；实际展开仅在受信任构建子进程中进行。
- 展开时维护调用栈检测循环递归；任何模板错误都同时指向调用节点 `uid` 与模板定义位置。
- 统一诊断模型包含 `code`、`severity`、`message`、`source_path`、`span`、`unit_id`、`uid` 与 `related`，展示在 Problems 面板，与进程纯文本日志分离。

## 7. 代码生成与事务构建

### 7.1 确定性生成

- 每个 `Stage` 生成独立子包，包含其传递引用闭包；文件命名基于校验后的逻辑 ID，拒绝路径穿越和关键字冲突。
- 生成代码直接继承标准 Runtime 类，复用 `src/game/tasks.py` 与批量弹幕 API，只在作者节点边界发射轻量 Trace 事件，不产生逐弹回调。
- `source_map.json` 记录 `uid ↔ 作者位置 ↔ 生成行号`；构建哈希仅依赖规范化语义、模板源码与生成器版本，确保相同输入逐字节一致。

### 7.2 事务发布流程

```text
校验内存模型
  -> 独立构建子进程：展开模板、生成代码到同级临时目录
  -> 子进程 compileall + import entry + 校验 Stage 注册表
  -> 准备就绪后停止旧预览进程
  -> 备份旧生成目录并原子替换新目录
  -> 启动新预览进程并完成握手 / 窗口嵌入
  -> 成功后提交删除备份；任一步失败则回滚旧构建并恢复旧预览
```

GUI 中通过异步子进程执行 `PackageBuilder.prepare()`，不阻塞主线程，支持中途取消。

## 8. `EditorSession` 与 Qt 界面

一个主窗口对应唯一一个 `EditorSession`，集中持有：

- `ProjectContext` 与当前打开的作者工程
- 当前逻辑单元与节点选中状态
- 各文件的 dirty / conflict / read-only 状态
- 唯一 `QUndoStack`
- 最近一次成功构建标识与预览进程状态
- 静态 Timeline 投影、Trace 叠加、Problems 与有界 Log

### 界面与视觉约束

- **单一主题源**：`src/editor/theme.py` 定义颜色、间距与字号 token 并生成唯一 QSS，由 `app.py` 挂载到 `QApplication` 级别，确保菜单、对话框与工具提示统一深色风格。
- **程序流交互**：采用中性灰紧凑行式布局（左侧类别色条 + 悬停插入引导线与 `+` 就地搜索）。拖拽计算唯一 `DropPlacement`（`BEFORE` / `AFTER` / `CHILD` / `WRAP`），节点移动只从拖动手柄触发，卡片正文专司选择。
- **Inspector**：基础常用参数首屏可见，浮点字段采用无截断精确文本输入，引用下拉显示中文名称并在底层保存英文 ID，只读资源字段校验 `res://` 类型。
- **资产侧栏**：全局资产基于 `ProjectContext` 扫描并排除缓存与顶层 `docs/`；当前 Stage 资产只收集从当前 Stage 传递引用的显式 `res://` 路径，不猜测 `RawPython` 内的动态字符串。

## 9. 预览进程协议与 Timeline

### 9.1 预览状态与协议

`PreviewOwner` 是唯一的 `QProcess` 所有者，状态机如下：

```text
stopped -> building -> starting -> running <-> paused
running/paused + 编辑源码 -> 保持运行并标记 stale
any -> stopping -> stopped
process failure -> error -> stopped
```

- 控制命令：`pause`、`resume`、`restart`、`seek`、`stop`。
- 上报事件：`ready`、`state`、`frame`、`trace`、`error`、`stopped`（均携带协议版本与 `run_id`，自动丢弃过期进程事件）。
- `seek` 使用同一固定种子重启并在关闭音频与中间帧绘制的情况下快速推进到目标帧。
- Windows `PreviewHost` 按子进程 PID 定位真实 GLFW 顶层窗口，通过 Win32 `SetParent` 嵌入并同步尺寸与键盘焦点，退出时恢复与清理。

### 9.2 Timeline 投影

`src/authoring/timeline.py` 输出只读 `TimelineInterval` 列表：

- 静态预计字段（`start` / `end`）与实测 Trace 字段（`observed_start` / `observed_end`）严格分离。
- 左列固定展示源码顺序的中文名称与层级，右侧按真实帧比例绘制，不用最小宽度冒充时长，未知区间放入专用非时间区。
- 节点与区间双向联动选择；仅在证明目标参数为字面量时允许反向拖动编辑 `Wait.frames`、`duration` 和 `At.frame`。
- 区间循环为临时查看状态，不写回作者源码。

## 10. 验证基线与响应目标

修改编辑器或编译器代码时，按影响范围执行以下检查：

```bash
python -m compileall -q main.py src game_content tools
python tools/validate_assets.py
git diff --check
```

- 修改 `src/authoring` 或 `src/compiler`：额外通过独立 Python 子进程验证保存、解析、生成和 `StageManager` 实际运行。
- 修改 `src/editor` 交互或预览嵌入：在真实桌面窗口（Windows PySide6 + GLFW 子窗口）复现实际用户操作链。
- 交互响应参考目标：节点库筛选 `< 50 ms`、拖拽落点计算 p95 `< 16 ms`、2,000 个 Timeline 元素平移/缩放 p95 `< 33 ms`。
