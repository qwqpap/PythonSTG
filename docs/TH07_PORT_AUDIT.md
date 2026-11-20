# TH07 API 调研与引擎能力补齐

本文总结面向东方妖妖梦（TH07）机制移植时的前置引擎调研结论，以及据此补齐的四项通用 Runtime 能力。后续单面移植实践见 [TH07 五面移植说明](TH07_STAGE5_PORT.md) 与 [TH07 六面移植说明](TH07_STAGE6_PORT.md)。

## 1. 参考项目与数据来源

调研参考了公开社区资料与工具，PySTG 本身不内置或分发任何原作素材和可执行文件：

- [some100/th07](https://github.com/some100/th07)：TH07 1.00b 匹配反编译参考，用于核对 Player、Enemy、ECL 特殊函数、计时与攻击逻辑。
- [AgentMystia/th07_web](https://github.com/AgentMystia/th07_web)：辅助对照 SHT、结界与自机数据格式。
- [thpatch/thtk](https://github.com/thpatch/thtk)（`thdat` / `thecl`）：用于离线分析用户本地游戏副本中的 PBG4 档案与 ECL 脚本。

## 2. 已确认并补齐的四项引擎能力

初期排查确认了四组会直接阻断 TH07 玩法还原的底层缺口，现均已在通用 Runtime 中实现并接入主循环与独立预览器（示范脚本见 `game_content/examples/th07_api.py`）：

| 原缺口 | 问题本质 | 当前公开入口与实现 |
| --- | --- | --- |
| **玩家受击契约不足** | 旧 `take_damage()` 只返回布尔值，无法区分“被森罗结界吸收”“进入 Deathbomb 救援窗口”和“真正掉命”，容易误记 miss 或破坏符卡捕获判定。 | `src/game/player/hit.py` 引入 `PlayerHit` / `HitDecision` / `HitResult` 与唯一提交点 `commit_player_hits`；`PlayerBase.receive_hit` 支持 `ignored` / `handled` / `pending` / `rescued` / `miss` 五种状态，捕获失败与 miss/Bomb 计数解耦。 |
| **缺少全系统仿真倍率** | 妖梦慢动作（`ExInsYoumuSetGameSpeed`）会影响玩家、自机弹、敌人、计时器、动画和背景，不只是降低敌弹速度。 | `TimeControl` 新增 0–1 分域仿真倍率，`StageContext` 暴露 `slow_motion()`、`set_simulation_scale()` 与 `wait_control()`；每控制帧首部统一采样，控制帧/Trace 保持单调，仿真时间支持分数推进。 |
| **攻击区与碰撞形状不足** | 自机持续激光（如魔理沙 B）、命中爆炸（如魔理沙 A 导弹）、旋转矩形与敌人本体接触不能用简单圆弹与穿透次数替代。 | 新增 `src/core/collision_shapes.py`（圆、旋转盒 SAT、曲线段几何）；`PlayerBulletPool` 扩展锚定激光（`fire_laser`）、逐目标伤害冷却和命中后阶段变化（`ImpactArea`）；敌人支持 `set_hitbox` 与可选 `set_contact_hitbox`。 |
| **BGM 播放与循环参数未落实** | `play_bgm` 的 `loops` / `start` / `fade_ms` 此前未在音频后端真正落地，也缺少前奏 + 样本级无缝循环点支持。 | 新增 `src/core/bgm_stream.py` 接入 `miniaudio` 流式混音，支持按源 PCM 帧设置 `loop_start_frame` / `loop_end_frame`、`loops`、`start`、`seek_bgm` 与淡入淡出，不整首缓存到内存。 |

详细调用写法见 [弹幕脚本开发指南](STAGE_SCRIPTING_GUIDE.md) 第 10 节。

## 3. 无需新增底层机制的部分

以下 TH07 特性可直接基于现有通用接口在内容层组织，无需引入原作虚拟机或第二套运行时：

- **常规发射、波次、多角色在场**：使用现有 `StageScript`、`Wave`、`EnemyScript`、`SpellCard` 和 `RunState`。
- **弹幕分裂、批量改向、沿激光发弹、弹转敌**：使用共享行为阶段表与批量数组接口。
- **Cherry / CherryMax / 森罗结界策略**：计分与结界状态属于内容层规则，通过受击钩子与道具收集回调实现。
- **3D 场景与离线数据**：将 `STD` 几何离线烘焙为 `SceneQuad` 并在普通脚本中控制镜头、雾效和文字，无需运行时 STD/ANM 解释器。

## 4. 离线数据分析参考

若需使用用户本机合法拥有的 TH07 副本与 `thtk` 查看原版 ECL 结构，可在临时目录执行：

```bash
thdat -l7 <path-to-th07.dat>
thdat -x7 <path-to-th07.dat> ecldata5.ecl ecldata6.ecl
thecl -d7 ecldata5.ecl ecldata5.ecl.txt
```

## 5. 后续移植方向

- 逐面补充关卡内容与多难度核对（五面与六面已作为重点实验完成核心流程，见对应文档）。
- 实现六名原版自机配置、高低速 Bomb、完整 CherryMax / 结界计分策略及对话演出（MSG）。
- 持续对比原版视觉细节、碰撞精度与真实游玩手感。
