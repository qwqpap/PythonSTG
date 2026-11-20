# TH07 第五面移植说明

本页记录以 PySTG 公开 Python API 移植东方妖妖梦（TH07）第五面的目录结构、机制映射、本地运行方式以及已知差异。移植内容位于 `game_content/ports/th07_stage5/`，完全复用现有 `StageManager`、NumPy/Numba 弹幕池、激光、道具、粒子与渲染器，不引入原版 ECL/ANM/STD 虚拟机，也不向仓库提交原作素材。

## 1. 代码结构

```text
tools/import_th07_stage5_assets.py   # 离线从本地原版导出图集、音频与静态场景到本地缓存
tools/preview_th07_stage5.py         # 启动器，经 main.py 加载 game_content.ports.th07_stage5.entry
game_content/ports/th07_stage5/
├─ entry.py          # 标准内容入口
├─ stage.py          # 整面流程与 presentation_resources 加载期预热声明
├─ road.py           # 前后道中、幽灵入场与飞升长尾、死亡发弹
├─ youmu.py          # 中 Boss（2 阶段）与关底妖梦（6 阶段）、四难度分支
├─ common.py         # 坐标/单位换算、源 RNG 与共享发射辅助
├─ background.py     # 楼梯静态几何、相机轨迹、移动云组、落樱天气与 eff05 符卡底图
├─ titles.py         # 关卡标题与 BGM 标题演出
└─ resources.py      # 本地导出缓存加载与资源注册
```

## 2. 关卡流程与 Boss 阶段

关卡按原版结构依次推进：道中前半 → 中 Boss 妖梦 → 道中后半 → 关底妖梦 → 退场。关底 6 个阶段顺序如下：

1. 首非符
2. 狱界剑「二百由旬之一闪」
3. 第二非符
4. 畜趣剑「无为无策之冥罚」（Easy / Normal）或 修罗剑「现世妄执」（Hard / Lunatic）
5. 人界剑「悟入幻想」
6. 天上剑「五衰之离别」

击破、HP 阈值切卡与超时分别对应原版分支逻辑，支持 Easy / Normal / Hard / Lunatic 四难度参数。

## 3. 原作机制如何映射到 PySTG API

| 原作机制 | PySTG 实现方式 |
| --- | --- |
| `ExIns12` / `21` 大弹分裂 | 使用 `read_bullets` / `snapshot.select` + `create_bullets_batch`，无额外专用接口 |
| `ExIns13` 框选转弯、`ExIns14` 向自机加速 | 使用 `set_bullet_behavior` 的每弹数组参数（长度 `N` 或 `(N, 2)`），在共享 Numba 内核中为每颗子弹保留独立阶段参数 |
| `ExIns10` / `11` 斩击慢放 | 使用 `ctx.slow_motion(1/3)` / `ctx.slow_motion(1/2)` 与按出生代追踪的弹幕变换 |
| 鳞弹 / 箭弹持续朝向 | 使用弹幕池的 `render_angle_offset` 与 `render_flip_y` 保持转弯时的正确贴图朝向，不改变运动角 |
| 白色幽灵 48 节点长尾 | 使用 `ctx.attach_trail(..., history_frames=48, blend="add", hide_owner=True)` 的连续纹理带 |
| 阶梯、云层、相机与天气 | 离线烘焙 `stage5.std` 为 `SceneQuad`；云层使用 GPU billboard、`group_offsets` 平移 uniform、深度控制和锚点距离雾（`distance_alpha`）；落樱天气由单 Task 批量计算后写入 `ParticlePool(motion="manual")` |
| 天气转场震动（`ExIns9`） | 使用 `ctx.shake_screen(frames=80, amplitude=8)`，仅位移游戏区视口，HUD 与边框不动 |
| 不可射击刀阵 | 通过 `set_interaction(collidable=False, damageable=False, interactable=False)` 控制 |
| 首次出弹/特效防卡顿 | 通过 `StageScript.presentation_resources()` 在加载期预热字形缓存、粒子常量表、拖尾顶点缓冲和 Numba 内核 |

## 4. 导出本地素材与运行

原作图像与音频属于版权内容，需从用户本机合法持有的 TH07 1.00b 副本离线导出到本地临时目录：

```bash
# 1. 从本机原版导出素材到本地缓存（默认输出到系统临时目录）
python tools/import_th07_stage5_assets.py \
  --game-dir "<path-to-th07-game-dir>" \
  --thtk-dir "<path-to-thtk-bin-dir>"

# 2. 启动第五面（默认从道中 Normal 开始）
python tools/preview_th07_stage5.py

# 3. 跳转到指定阶段与难度（--start: road | midboss | youmu；--phase 从 1 开始）
python tools/preview_th07_stage5.py --start youmu --phase 2 --difficulty lunatic
```

可通过 `--assets <目录>` 或环境变量 `PYSTG_TH07_STAGE5_ASSETS` 指定缓存目录；缺素材时会直接报错提示，不静默替换默认贴图。

## 5. 已知差异与未移植部分

- **对话（MSG）**：原版人物对话与分支台词暂未移植，到达对话节点时跳过并记录日志。
- **精细 ANM 与特效池竞争**：已导出原图集并复现核心演出，但完整的 ANM 指令变换、中断和原作 400 槽特效池竞争尚未逐帧对齐。
- **原版全局规则与自机**：完整的 CherryMax / 森罗结界、原版六自机射击与 Bomb、原版计分与全部音效优先级策略尚未移植。
- **RNG 与亚帧精度**：震动使用局部确定性种子，部分视觉效果不消耗玩法共享 RNG，因此与原版录像（replay）并非逐帧等价。
