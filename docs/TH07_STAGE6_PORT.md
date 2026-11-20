# TH07 第六面移植说明

本页记录以 PySTG 公开 Python API 移植东方妖妖梦（TH07）第六面的代码结构、Boss 阶段设计、通用引擎接口映射、本地运行方式及已知差异。移植代码位于 `game_content/ports/th07_stage6/`，复用现有运行时与渲染管线，不包含原作虚拟机或版权素材。

## 1. 代码结构

```text
tools/import_th07_stage6_assets.py   # 从本地原版离线导出图集、音频与静态场景
tools/preview_th07_stage6.py         # 启动器，经 main.py 加载 game_content.ports.th07_stage6.entry
game_content/ports/th07_stage6/
├─ entry.py          # 标准内容入口
├─ stage.py          # 整面流程与加载期预热声明
├─ road.py           # 47 个道中敌人出生、死亡残影与背景粒子 owner
├─ youmu.py          # 中 Boss 妖梦（非符 + 一念无量劫 + 击破/超时退场）
├─ yuyuko.py         # 关底幽幽子（10 阶段含墨染与反魂蝶 + 结束演出）
├─ common.py         # 源坐标/单位换算、批量发射辅助与内容规则
├─ background.py     # 六面 3D 场景、镜头与标签 1–5、eff05/eff06 双层符卡背景、三维落樱
├─ titles.py         # 关卡标题、Boss 入场名与 BGM 标题
└─ resources.py      # 本地导出缓存加载与资源注册
```

## 2. 关卡流程与 Boss 阶段表

道中先完成 47 次敌人出场，随后进入中 Boss 妖梦战斗；妖梦退场后触发背景转场并进入幽幽子战与尾声。

| Boss | 阶段 | HP / 切卡阈值 | 时限（帧） |
| --- | --- | --- | --- |
| 妖梦 | 非符 | `15000`（严格 `< 1500` 切符卡；超时直接退场） | `3600` |
| 妖梦 | 符卡「一念无量劫」 | 继承钳回后的 `1500` | `2400` |
| 幽幽子 | 非符 1 → 亡我乡 | `21000` / 阈值 `2100`（继承） | `3600` / `3900` |
| 幽幽子 | 非符 2 → 生者必灭 | `32000` / 阈值 `3000`（继承） | `3600` / `3900` |
| 幽幽子 | 非符 3 → 华胥的永眠 / 蝴蝶 | `32000` / 阈值 `3000`（继承） | `3600` / `3900` |
| 幽幽子 | 非符 4 → 弘川 | `22000` / 阈值 `2200`（继承） | `3600` / `3900` |
| 幽幽子 | 樱符「完全墨染的樱花」 | `6000` | `5940` |
| 幽幽子 | 反魂蝶（耐久） | `1`（不可受伤） | 前奏后重置 `4020` |

## 3. 通用 Runtime 能力映射

六面移植推动补齐并使用了以下通用公开接口：

| 机制需求 | PySTG 公开入口 |
| --- | --- |
| 出生期移动但不碰撞、临时初速与越界宽限 | `ctx.configure_bullet_birth(group, warmup_frames=..., velocity_boost=..., offscreen_grace_frames=...)` |
| 临时速度倍率与角度偏移 | `ctx.set_bullet_behavior(..., stages=[{"velocity_scale_end": ..., "angle_offset": ...}])` |
| 全屏淡出闪光（`ExIns15`） | `ctx.flash_screen(rgba, frames)` |
| 非符 HP 阈值切卡、HP 继承与延迟宣言 | `BossPhase(hp_threshold=..., carry_hp=..., transition_rule=..., auto_declaration=False)` + `boss.declare_spell()` |
| 同帧伤害聚合与主/副受弹区（如幽幽子宽受弹带） | `actor.set_secondary_hitbox(...)` + `DamageHit(source, region)` + `target.damage_batch(hits)` |
| 特殊道具标签与选择性交回默认收取 | `ctx.spawn_item(..., tag=...)` + 收集规则返回 `False` 委派默认逻辑 |
| 3D 静态场景、双层符卡底图与标题文字 | `ctx.background.set_scene / set_camera / set_fog / set_layers`、`ctx.show_title`、`ctx.show_text`、`ParticlePool(motion="manual")` |

## 4. 导出本地素材与运行

素材需从用户本机合法持有的 TH07 1.00b 副本离线导出：

```bash
# 1. 从本机原版导出素材到本地缓存
python tools/import_th07_stage6_assets.py \
  --game-dir "<path-to-th07-game-dir>" \
  --thtk-dir "<path-to-thtk-bin-dir>"

# 2. 启动第六面
python tools/preview_th07_stage6.py

# 3. 跳转到幽幽子指定阶段（--phase 从 1 开始，如 6=蝴蝶、9=墨染、10=反魂蝶）
python tools/preview_th07_stage6.py --start yuyuko --phase 9 --difficulty normal --seed 1337
```

可通过 `--assets <目录>` 或环境变量指定缓存路径，更多导入选项见 `python tools/import_th07_stage6_assets.py --help`。

## 5. 已知差异与未移植部分

- **对话（MSG）**：原版开场、Boss 战前与尾声台词暂未移植，运行到对话处会显式跳过。
- **完整 ANM 与特效细节**：真实原图与主要演出已接入，但部分 ANM 中断、消失淡出动画及原版 400 槽共享特效池尚未逐帧还原。
- **出生结束帧与亚帧调度**：出生期为清晰的两段式控制，且弹转敌产生的新敌人固定从下一控制帧开始执行，与原版个别物理帧边界存在细微差别。
- **计分、擦弹与原版自机**：完整 CherryMax / 结界机制、矩形擦弹区、原版六自机射击与 Bomb 尚未移植。
- **RNG 序列**：未复原全部纯视觉效果对全局 RNG 的消耗，因此不能与原版 replay 逐帧对齐。
