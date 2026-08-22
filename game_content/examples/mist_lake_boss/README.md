# 雾湖灯祭：完整关卡示例

这是一个可以直接在 PySTG 编辑器中打开的两阶段 Boss 关卡。作者资源是唯一真源，
没有配套 Python 关卡脚本。

## 从编辑器查看

1. 启动编辑器并打开项目根目录。
2. 选择“打开资源”。
3. 打开 `game_content/examples/mist_lake_boss/stage.pystg.json`。
4. 依次查看：场景树、关卡流程、时间线、变量和预览。

还可以分别打开：

- `moon_ring.pystg.json`：第一阶段的蓝色花形月轮；
- `purple_tide.pystg.json`：第二阶段的紫色追踪扇形刀弹；
- `background.pystg.json`：三层雾湖背景。

## 关卡结构

```text
登场：湖面点灯（3 秒）
  ├─ 雾湖背景淡入
  ├─ BGM 00 循环播放
  └─ stage.title 事件
       ↓ 时间结束
通常：月轮灯阵（20 秒）
  ├─ 月轮八重奏 Pattern
  ├─ Boss 左右巡游
  ├─ boss.phase = 1
  └─ encounter.cleared → 提前进入下一阶段
       ↓
强化：紫潮追猎（25 秒）
  ├─ 紫潮追猎 Pattern
  ├─ Boss 三角高速移动
  ├─ 背景 90 帧转场
  ├─ boss.phase = 2 / boss.rage = true
  └─ encounter.cleared → 提前结束
       ↓
结束：雾散（2 秒）
  ├─ stage.complete 事件
  └─ BGM 淡出
```

固定时长总计 3000 帧（50 秒，60 FPS）；两个战斗阶段也可以由
`encounter.cleared` 事件提前结束。
