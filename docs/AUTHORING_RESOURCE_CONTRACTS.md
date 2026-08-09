# 作者资源契约

本文冻结 Godot 式编辑器 Phase 0 使用的最小公共协议。弹幕配方、时间轴、UI
布局和背景的领域字段将在后续阶段分别定义；它们不得绕过这里的身份、版本、引用、
坐标、时间和注册表契约。

## 文件与公共资源头

所有版本化作者资源保留 `*.pystg.json` 后缀。资源类型由 JSON 内的 `type`
决定，不依赖文件名猜测：

```json
{
  "schema_version": 1,
  "type": "pystg.pattern",
  "id": "08ac589e-a51a-45dc-beb9-7af6f4e136db",
  "name": "星符「星轨回廊」",
  "symbol_name": "star_corridor",
  "metadata": {}
}
```

M0 注册以下类型：

| `type` | 资源浏览器类别 | 领域正文冻结阶段 |
|---|---|---|
| `pystg.scene` | Scene | v3：内嵌分层状态图与 State 局部时间线 |
| `pystg.pattern` | Pattern | Phase 1 |
| `pystg.ui` | UI | Phase 6 |
| `pystg.background` | Background | Phase 6 |

公共字段语义：

- `schema_version`：该 `type` 的整数 schema 版本，不是应用版本。
- `id`：稳定 UUID，用于引用和对象身份。
- `name`：面向作者的 Unicode 显示名，可直接使用中文。
- `symbol_name`：可选的便携 Python 标识符，仅在代码导出/脚本绑定需要时使用。
- `metadata`：JSON 对象；不能替代需要验证的正式领域字段。

显示名、UUID 和脚本符号是三个不同概念。不得为了生成 Python 而限制显示名。

## 资源引用

新写入的引用统一使用：

```text
res://assets/images/bullet.json#orb
res://game_content/patterns/star-ring.pystg.json
```

- `res://` 后是相对项目根目录的 POSIX 路径。
- `#fragment` 是可选子资源名。
- 禁止绝对路径、盘符、`.` 和 `..` 穿越。
- 读取器在迁移期可接受旧的项目相对路径，但保存的新引用必须规范化为 `res://`。
- 路径解析必须通过 `ResourceReference` 和 `ProjectContext`。

## 迁移

迁移由 `MigrationRegistry` 按 `(resource_type, from_version)` 显式注册，且每次只
允许从 `N` 迁移到 `N+1`。迁移函数：

1. 接收并返回 JSON object；
2. 不得改变 `type`；
3. 必须把 `schema_version` 精确增加 1；
4. 必须有输入 fixture、迁移结果和 round-trip 测试；
5. 遇到未来版本或缺失迁移路径时给出可操作错误，不能猜测降级。

旧无版本场景通过已注册的 `pystg.scene` v0→v1→v2→v3 迁移进入当前模型。
v2 的顶层 `tracks` 会原样迁入一个确定性 UUID 的 `Default` State；Track、Clip、
Keyframe 的 ID、顺序、时长和 payload 不改变。v3 保存后不再写第二份顶层
`tracks`。

## Scene v3 状态图正文

`SceneDocument` 是保存、Undo/Redo 和编译的唯一真源；`state_graph` 是它的内嵌
子结构，不是另一种 Flow/State/Sequence 文件：

```json
{
  "schema_version": 3,
  "type": "pystg.scene",
  "state_graph": {
    "id": "e0f36a27-e0c4-5a99-b044-ad01a3ebfceb",
    "name": "StageFlow",
    "initial_state_id": "d71b4d73-9ecd-5707-a48b-2cbc0c9ca03e",
    "states": [
      {
        "id": "d71b4d73-9ecd-5707-a48b-2cbc0c9ca03e",
        "name": "Default",
        "order": 0,
        "duration_frames": 240,
        "entry_actions": [],
        "exit_actions": [],
        "tracks": [],
        "transitions": [],
        "child_graph": null
      }
    ]
  }
}
```

- 每个 State 直接拥有入口/退出稀疏动作、局部 Timeline、同级 Transition 和可选
  `child_graph`；所有对象继续使用全 Scene 唯一的稳定 UUID。
- `after` 转移的 `after_frames` 是 State 局部帧且必须大于零；`complete` 转移的
  `after_frames` 必须为 `null`。本版本不提前包含变量条件或事件转移。
- Composite State 进入时自动进入子图的 `initial_state_id`；父 State 退出时按
  子级到父级的顺序取消整个活动子树。
- StageFlow 与 PhaseFlow 是根图和子图的编辑器上下文名称，使用同一个 schema、
  compiler、runner、CommandStack 和调试反馈。
- 运行实例、当前 State path 和局部帧只存在于 `StageRunner`/Preview stats；它们
  不写回 `SceneDocument`，也不制造 dirty。
- 完整 JSON 约束见 `docs/schemas/pystg-scene-v3.schema.json`；v2/v3 迁移样本见
  `docs/schemas/fixtures/scene-v2.pystg.json` 与
  `docs/schemas/fixtures/scene-v3.pystg.json`。

## 坐标

作者空间是与实际窗口缩放无关的逻辑画布：

| 项目 | 约定 |
|---|---|
| 基准尺寸 | 384×448 |
| 作者原点 | 左上 |
| 作者 X | 向右 |
| 作者 Y | 向下 |
| 运行时原点 | 画面中心 |
| 运行时 X/Y | `[-1, 1]` |
| 运行时 Y | 向上 |

转换公式由 `src.authoring.coordinates.CoordinateSpace` 唯一实现。视口放大到
768×896 或其他尺寸不能改变最终运行时位置。

## 时间

- 文档主时间使用非负整数帧。
- 默认 tick rate 为 60Hz。
- 秒和拍是编辑器显示/输入单位，由 `Timebase` 转换。
- 时间轴排序、对象身份和确定性回放不得依赖浮点秒相等判断。

## 注册表

`ResourceTypeRegistry` 为每个资源类型提供以下可选 contribution：

- loader；
- validator；
- editor factory；
- compiler；
- preview handler。

`NodeTypeRegistry` 为每个场景节点提供：

- 属性 schema 和 Inspector 提示；
- 父子约束和验证器；
- Viewport 表现；
- editor factory；
- runtime compiler。

编辑器外壳使用注册表查询，不得为了新资源/节点类型继续添加编译或绘制类型分支。

## Phase 0 与后续阶段的边界

M0 只冻结公共契约和贡献入口，不预先虚构 Pattern/UI/Background 正文字段。领域
文档可以由 `GenericResourceDocument` 无损保存，在相应阶段由注册表替换为强类型
loader/validator，并通过新的 schema 迁移演进。

Generated Python 始终是可选导出物，不是作者资源的唯一可运行表示。
