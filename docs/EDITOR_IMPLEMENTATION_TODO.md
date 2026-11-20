# 代码驱动关卡编辑器开发进度

本文件记录 PySTG 第二代代码驱动关卡编辑器的阶段完成情况与当前待办事项。产品设计见 [编辑器设计概览](EDITOR_PRODUCT_VISION.md)，工程架构见 [编辑器架构](EDITOR_ARCHITECTURE.md)。

## 阶段总览

| 阶段 | 目标 | 状态 |
| --- | --- | --- |
| CD0 | 基线正确性、无崩溃输入与 Runtime 参数一致性 | 已完成 |
| CD1 | 关卡组织、调用链导航与新手首次创作路径 | 已完成 |
| CD2 | 直接拖拽的线性程序流、就地搜索与「套一层」包裹 | 已完成 |
| CD3 | Inspector 表单、弹幕可视化辅助与显式预览反馈 | 已完成 |
| CD4 | Timeline 节奏/Trace 投影、完整示例工程与反向编辑 | 已完成 |

## 各阶段完成摘要

- **CD0 — 基线与参数对齐**：统一 `unit_accepts_statements` 规则禁止向 `Project`/`Boss` 插入语句；打开工程自动定位 `start_stage`；修复 Inspector 边界值输入崩溃；将批量发射参数显式映射到 DSL 并对齐单发/批量运动语义。
- **CD1 — 关卡组织与引导**：新增欢迎页与普通 DSL 默认示例；左侧提供当前关卡调用链、全部单元、只读源码与资源页；实现步骤主导布局、引用跳转返回、就地新建单元并自动插入。
- **CD2 — 程序流交互**：自定义绘制的紧凑行式程序流（`ProgramFlow`），支持悬停引导线 + 就地搜索、拖动手柄移动、容器内容区插入与「套一层」包裹，全操作进入单一 `QUndoStack`。
- **CD3 — Inspector 与预览反馈**：按 DSL 类型注解动态生成中文分组表单，支持精确浮点文本输入、引用名称解析、资源拖入与弹型缩略图；完善构建事务回滚、源码过期标记与暂停状态独立保留。
- **CD4 — Timeline 与完整示例**：实现静态预计与真实 Trace 并列展示、有界弹幕密度指标、父子独立行与字面量反向编辑（`Wait.frames`、`duration`、`At.frame`）；内置 `game_content/authoring/code_editor_demo` 完整示例工程，支持 Project / Stage / Spell 三种原生嵌入预览。
- **视觉统一维护**：引入 `src/editor/theme.py` 应用级深色主题与统一中性灰紧凑风格，消除顶层对话框和菜单的白底样式不一致。

## 当前待办事项

### 关卡编辑器

- [ ] **真人端到端易用性试用**：由维护者或新作者完整走一遍“新建工程 → 编写波次/敌人/符卡 → 调整参数 → 运行预览 → 阅读 Timeline → 保存重开与 Undo/Redo”，收集真实卡点并持续打磨。
- [ ] **主题 Token 彻底收口**：将 `program_tree.py`、`timeline.py`、`node_palette.py` 中剩余的数值等价硬编码颜色全部切换为读取 `src/editor/theme.py` 中的统一 token。
- [ ] **预览替换速度优化**：缩短重新 Run 时停止旧预览进程的等待时间，避免切换构建时出现数秒阻塞。
- [ ] **大型程序刷新性能**：针对节点数较多的复杂单元优化程序流刷新与布局开销。

### 仓库配套收尾

- [ ] **难度选择菜单收尾**：完成主菜单“开始游戏”后的四难度选择交互（Easy / Normal / Hard / Lunatic）与 Replay 难度记录的最终桌面端实测确认。

## 日常启动与检查

```bash
# 打开示例工程试用编辑器
pystg-editor game_content/authoring/code_editor_demo

# 提交前基础检查
python -m compileall -q main.py src game_content tools
python tools/validate_assets.py
git diff --check
npm run docs:build
```
