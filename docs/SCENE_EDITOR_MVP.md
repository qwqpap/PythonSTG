# 统一场景编辑器 MVP

统一场景编辑器提供一个接近 Godot 工作流的 PyQt5 主窗口，并直接读写版本化
`pystg.scene` 文档。它不会替代现有纹理、立绘等专用工具，而是作为场景编排入口。

当前工作台已经包含 Scene、Inspector、2D Viewport、资源浏览器、Tools 插件入口和只读 Timeline；本页的“当前边界”描述仍然适用于 MVP 阶段。

## 启动

安装开发依赖后，在项目根目录运行：

```bash
python tools/scene_editor.py
```

安装项目后也可以使用：

```bash
pystg-editor
```

VS Code 任务列表中对应 `PythonSTG: Open Scene Editor`。

## 窗口布局

- 左侧 **Scene**：节点层级、添加、删除、重排和父子挂接。
- 中央 **2D Viewport**：画布网格、选择、拖动和网格吸附。
- 右侧 **Inspector**：节点名称和类型化属性。
- 底部 **Output / Timeline**：操作记录、预览进程输出和文档时间轴。

第一批稳定节点类型：

- `SceneRoot`
- `Sprite`
- `EnemySpawner`
- `SpellCard`

场景树支持鼠标拖放，也提供显式的上移、下移、提升和缩进按钮。所有结构与
Inspector 修改都经过统一命令栈，可以 Undo/Redo。

## 文件与保存

新场景默认保存到 `game_content/scenes/*.pystg.json`。编辑器只允许打开和保存
项目根目录以内的文件，写入使用临时文件和原子替换。

窗口标题中的 `*` 表示文档存在未保存修改。新建、打开和关闭前会检查未保存状态。

## 预览

`Run / Preview`（F6）总是启动独立进程，不把 GLFW/ModernGL 窗口嵌入 Qt：

- 选中配置了 `script` 的 `SpellCard` 时，启动真实符卡预览器。
- 选中其他节点时，启动 `metadata.preview_stage` 指定的正式关卡运行时，默认
  `stage1`，并启用热重载。

2D Viewport 是编辑视图，不宣称等同正式渲染结果。游戏画面和弹幕效果以独立预览
进程为准。

## 当前边界

- 高密度子弹不会展开成 Scene Tree 节点。
- 时间轴当前只读，后续再接事件增删和拖动。
- Assets 资源浏览器已接入，支持图片、脚本、JSON 以及 atlas 的 `sprites` / `animations` 子资源；子资源引用使用 `path.json#name`。
- `Sprite.texture` 可由资源浏览器选择图片或 sprite 子资源设置；选中 `SpellCard` 后也可以设置 Python `script`。
- 场景文档到任意 Python 关卡脚本的完整 runtime bridge 尚未实现；正式关卡预览
  当前由 `preview_stage` 选择已有 Stage。
