# 编辑器架构边界

本文件定义类 Godot 编辑器开发前必须保持的依赖方向。

```text
Editor panels
    ↓ commands
Versioned documents
    ↓ runtime bridge
EngineSession
    ↓
Runtime / renderer / resource service
```

## 项目与路径

- `project.pystg.json` 标识项目并声明内容目录。
- `ProjectContext` 是项目根路径的唯一发现和解析入口。
- 旧代码仍可依赖项目工作目录；主入口会通过 `ProjectContext.activate()` 提供兼容。
- 新代码不得自行猜测 `assets/` 相对于当前进程的位置。

## 文档

- 所有作者资源使用 `*.pystg.json`，由文档内的 `type` 区分
  `pystg.scene`、`pystg.pattern`、`pystg.ui` 和 `pystg.background`。
- 公共资源头、引用、迁移、坐标和时间契约见
  [`AUTHORING_RESOURCE_CONTRACTS.md`](AUTHORING_RESOURCE_CONTRACTS.md)。
- 文档、节点和时间轴事件都有稳定 UUID。
- `DocumentStore` 只允许读写项目目录内文件，并使用原子替换保存。
- 新 schema 必须提供迁移函数和 round-trip 测试。
- 复杂的 Python 行为暂不反向解析；以后由 `ScriptNode` 作为明确的代码扩展点。

## 运行时

- `EngineSession` 持有一次游戏或预览会话的资源生命周期。
- 编辑器不得直接从窗口部件创建全局资源 manager。
- 预览必须复用正式运行时渲染路径；模拟预览只能标记为实验性。
- 高密度子弹继续留在 NumPy/Numba 池中，不能展开成编辑器场景节点。

## 资源

- `ResourceTypeRegistry` 是版本化作者资源的 loader、validator、editor、compiler
  和 preview contribution 入口；编辑器外壳不得按资源类型增加编译分支。
- `ResourceService` 继续负责当前运行时纹理目录和富编辑纹理兼容模型。
- `TextureAssetManager` 是当前正式运行时纹理目录。
- `UnifiedTextureManager` 暂作为富编辑类型兼容模型，由 `ResourceService.editor` 管理。
- 两种内部表示迁移完成前，关键资源必须通过契约测试证明解析结果一致。

## 坐标与时间

- 作者画布使用固定逻辑像素，基准尺寸为 `384x448`，原点在左上，Y 向下。
- 正式运行时坐标以画面中心为原点，X/Y 范围均为 `[-1, 1]`，Y 向上。
- 编辑器、文档编译器和预览只能通过 `CoordinateSpace` 做两者转换。
- 文档时间存储为声明 tick rate 下的非负整数帧；第一版 tick rate 为 60Hz。
- 秒和拍仅为显示/输入单位，通过 `Timebase` 转换，不以浮点秒作为时间轴主键。

## 编辑操作

- Inspector、场景树和时间轴修改必须经过 `CommandStack`，以支持 Undo/Redo。
- 编辑器配置应使用 `atomic_write_json`，避免保存中断导致文件损坏。
- 旧弹幕脚本生成器只能导出当前 async API 代码，不能宣称能无损导入任意 Python。

## 合入门槛

```bash
python -m compileall -q main.py src game_content tools
python -m pytest -q
python tools/validate_assets.py
```

此外还需实际启动主游戏、真实符卡预览和主要编辑器窗口。自动测试通过不等于视觉验收通过。
