# TH06 引擎机制覆盖清单

本文对照东方红魔乡（TH06）的 ECL 机制，梳理哪些玩法可以直接使用 PySTG 现有公开 Python API 表达，哪些能力仍在缺口中。目标是验证引擎通用表达力，不引入原版 ECL/ANM 虚拟机，也不包含任何原作素材或版权资源。

机制参考自公开反编译源码 [YomotsuHisami/th06](https://github.com/YomotsuHisami/th06)。高级用法示例见 `game_content/examples/th06_*.py`，脚本 API 详见 [弹幕脚本开发指南](STAGE_SCRIPTING_GUIDE.md)。

## 1. 按 ECL 指令范围对照

| 指令范围 | 对应 PySTG 公开 API / 写法 | 说明与边界 |
| --- | --- | --- |
| `0–3` | Python 控制流与 `await self.wait(n)` | `1`（`UNIMP`）为原版空槽 |
| `4–12` | 局部变量、定种 RNG、`actor.x` / `actor.y` | 2D 角色不维护独立 3D `z` 轴 |
| `13–26` | Python / NumPy / Numba 运算 | C 风格的整数截断与负余数需在内容脚本中显式处理 |
| `27–42` | `if` / `while`、普通函数、`spawn_task` / `parallel` | 不保留 ECL 栈帧地址，按协程结构重写 |
| `43–51` | `set_position`、`move_linear`、`move_velocity` | 坐标与速度使用世界归一化单位/秒 |
| `52–64` | `move_to(..., easing=...)` | 支持线性及二次/四次缓入缓出 |
| `65–66` | `set_movement_bounds` / `clear_movement_bounds` | `set_position` 与标准移动均遵守边界 |
| `67–75` | `fire_arc` / `fire_circle` / `create_bullets_batch` | 偏移环、随机角与多层弹用 NumPy 数组批量生成 |
| `76–81` | 角色 `Task` 循环与可取消句柄 | 不增加隐藏发射时钟，新弹次帧运动 |
| `82` | `set_bullet_behavior`、二维加速度、限次反弹/穿屏、批量变换 | 常用弹幕效果已覆盖，复杂组合由内容组装 |
| `83–84` | `clear_bullets_by_tag` / `bullets_by_tag_to_item` / `play_se` | 清场与自然到期语义分开 |
| `85–92` | `create_laser`、`configure_motion` / `configure_lifecycle`、`destroy` | 支持动态移动段与独立警告/碰撞窗口 |
| `93–94` | `BossPhase`、`SpellCard`、`bonus_rule`、`finish_rule`、`SpellResult` | 原作全部收符公式需由内容策略实现 |
| `95–96` | `spawn_enemy_class`、`add_enemy_script`、`kill` / `dispose` | `kill` 触发掉落，取消用 `dispose` |
| `97–100` | `play_animation`、`set_visual`、`attach_animation`、`ctx.play_animation` | 通用主/附属动画控制已具备，不含原作 ANM 数据 |
| `101–102` | `BossDef` / `run_boss` 与符卡宣言接口 | 宣言装饰特效可继续扩充 |
| `103–105` | `set_hitbox`、`set_interaction(collidable, damageable)` | 支持不可受伤但可触发 `on_hit` 的假身 |
| `106–108` | `play_se`、`on_death`（托管至存活 `StageContext`） | 死亡后可继续异步发弹或放特效 |
| `109–110` | `on_hit`、`emit_event` / `wait_event`、取消或替换 `Task` | 按稀疏事件和结构化任务表达中断 |
| `111–116` | `hp`、`hp_threshold`、`wait_until`、`set_timer`、`timer_frames` | 支持 HP 阈值切卡与独立 Boss 计时 |
| `117` | `set_interaction(interactable=...)` | 独立控制是否参与命中与自机追踪 |
| `118–120` | `spawn_item` / `spawn_drop`、`emit_particles`、`set_visual` | 独立粒子池与视觉变换已接入 |
| `121–123` | 普通函数、批量数值公式、角色 Task | 17 个特殊函数见第 2 节 |
| `124` | `set_item_collection_rule`、`GameStats` 回调 | 可配置 128P、得点、Extend 等规则 |
| `125` | `ctx.background`、`stop_time("background")` | 支持 3D 静态场景、雾效与独立背景暂停 |
| `126–130` | Boss HUD 与动画替换接口 | Boss 动态残机段数显示接口待细化 |
| `131` | `ctx.run_state.rank` / `adjust_rank` / `rank_value` | 跨关共享 Rank，支持稀疏事件增减 |
| `132–135` | `visible`、`set_timer`、`clear_all_lasers`、`finish_rule` | 支持耐久/超时分支结算 |

## 2. 17 个特殊函数对照

参考 `src/EnemyEclInstr.cpp`：

| 函数 | 核心机制 | PySTG 对应方案 |
| --- | --- | --- |
| `CirnoRainbowBallJank` | 停弹后施加每弹随机二维加速度，220 帧后清零 | 共享阶段 + NumPy `vector_accel` |
| `ShootAtRandomArea` | 每次随机发射原点 | `create_bullets_batch` 传 `(N, 2)` 位置数组 |
| `ShootStarPattern` | 星形边插值，保留初始玩家快照 | NumPy 批量生成位置数组 |
| `PatchouliShottypeSetVars` | 按玩家机体/武器分支 | 读取 `ctx.player_shot` 与 `ctx.difficulty` |
| `Stage56Func4` | 世界时停 + 有限数量随机改向 | `ctx.stop_time()` + 批量筛选改向 |
| `Stage5Func5` | 九组位置矩阵发射 | NumPy 位置/角度/速度数组一次批量发射 |
| `BatWingEffect` | 镜像双翼装饰粒子 | `emit_particles` + `ParticleEffect`（见 `th06_particles.py`） |
| `Stage6Func7` | 两组八方向、三层、48 条交错激光 | `create_laser` + `configure_lifecycle`（见 `th06_controls.py`） |
| `Stage6Func8` | 从大弹当前位置派生静止小弹 | `read_bullets(fields=("pos",))` + `create_bullets_batch` |
| `Stage6Func9` | 停弹按距 Boss 距离公式启动与加速 | `distance_acceleration` + `transform_bullets`（见 `th06_patterns.py`） |
| `Stage6Func11` | 停弹后施加随机加速度，120 帧后清除 | `snapshot.select` + `vector_accel` |
| `HandleBatTransformation` | Bomb 期间敌人不可交互，结束后延迟 60 帧恢复 | 观察 `player.is_bombing` + `set_interaction`（见 `th06_controls.py`） |
| `Stage4Func12` | 沿激光方向距敌 64px 处发弹 | 读取 `laser.angle` 与角色位置批量发射 |
| `StageXFunc13` | 每 6 帧从圆周点发射 | 普通协程循环 + 局部角度 |
| `StageXFunc14` | 沿移动激光当前段每 48px 发弹 | `laser.sample_points(step)` + 批量发射 |
| `StageXFunc15` | 严格邻域、按槽序首次匹配激活改向 | `neighbor_activation`（见 `th06_patterns.py`） |
| `FlandreFinalContextUpdate` | 按 HP 与计时动态调整速度、间隔和随机域 | 读取 `boss.hp` 与 `spell.timer_frames` 批量发射 |

## 3. 主要剩余缺口

- **内容与策略层面**：原作六关 + Extra 的具体关卡脚本、128P/得点/Extend/Rank 精确数值表、完整 Deathbomb 策略均属于游戏内容层工作，引擎仅提供通用钩子。
- **视觉与演出层面**：原作 ANM 精细时序、三维深度排序、Boss 宣言/时停滤镜与 HUD 特殊样式尚未完全覆盖。
- **GUI 编辑器覆盖**：上述批量数组规则、自定义受击/结算规则和粒子/动画高级接口目前面向手写 Python 脚本（或编辑器内 `RawPython`），尚未全部做成拖拽节点。

## 附录：136 项 ECL 指令编号索引

以下列出原版枚举名称（省略 `ECL_OPCODE_` 前缀），便于对照第 1 节：

| 编号 | 名称 | 编号 | 名称 | 编号 | 名称 |
| --- | --- | --- | --- | --- | --- |
| 0 | `NOP` | 46 | `MOVEANGULARVELOCITY` | 92 | `LASERCANCEL` |
| 1 | `UNIMP` | 47 | `MOVESPEED` | 93 | `SPELLCARDSTART` |
| 2 | `JUMP` | 48 | `MOVEACCELERATION` | 94 | `SPELLCARDEND` |
| 3 | `JUMPDEC` | 49 | `MOVERAND` | 95 | `ENEMYCREATE` |
| 4 | `SETINT` | 50 | `MOVERANDINBOUND` | 96 | `ENEMYKILLALL` |
| 5 | `SETFLOAT` | 51 | `MOVEATPLAYER` | 97 | `ANMSETMAIN` |
| 6 | `SETINTRAND` | 52 | `MOVEDIRTIMEDECELERATE` | 98 | `ANMSETPOSES` |
| 7 | `SETINTRANDMIN` | 53 | `MOVEDIRTIMEDECELERATEFAST` | 99 | `ANMSETSLOT` |
| 8 | `SETFLOATRAND` | 54 | `MOVEDIRTIMEACCELERATE` | 100 | `ANMSETDEATH` |
| 9 | `SETFLOATRANDMIN` | 55 | `MOVEDIRTIMEACCELERATEFAST` | 101 | `BOSSSET` |
| 10 | `SETVARSELFX` | 56 | `MOVEPOSITIONTIMELINEAR` | 102 | `SPELLCARDEFFECT` |
| 11 | `SETVARSELFY` | 57 | `MOVEPOSITIONTIMEDECELERATE` | 103 | `ENEMYSETHITBOX` |
| 12 | `SETVARSELFZ` | 58 | `MOVEPOSITIONTIMEDECELERATEFAST` | 104 | `ENEMYFLAGCOLLISION` |
| 13 | `MATHINTADD` | 59 | `MOVEPOSITIONTIMEACCELERATE` | 105 | `ENEMYFLAGCANTAKEDAMAGE` |
| 14 | `MATHINTSUB` | 60 | `MOVEPOSITIONTIMEACCELERATEFAST` | 106 | `EFFECTSOUND` |
| 15 | `MATHINTMUL` | 61 | `MOVETIMEDECELERATE` | 107 | `ENEMYFLAGDEATH` |
| 16 | `MATHINTDIV` | 62 | `MOVETIMEDECELERATEFAST` | 108 | `DEATHCALLBACKSUB` |
| 17 | `MATHINTMOD` | 63 | `MOVETIMEACCELERATE` | 109 | `ENEMYINTERRUPTSET` |
| 18 | `MATHINC` | 64 | `MOVETIMEACCELERATEFAST` | 110 | `ENEMYINTERRUPT` |
| 19 | `MATHDEC` | 65 | `MOVEBOUNDSSET` | 111 | `ENEMYLIFESET` |
| 20 | `MATHFLOATADD` | 66 | `MOVEBOUNDSDISABLE` | 112 | `BOSSTIMERSET` |
| 21 | `MATHFLOATSUB` | 67 | `BULLETFANAIMED` | 113 | `LIFECALLBACKTHRESHOLD` |
| 22 | `MATHFLOATMUL` | 68 | `BULLETFAN` | 114 | `LIFECALLBACKSUB` |
| 23 | `MATHFLOATDIV` | 69 | `BULLETCIRCLEAIMED` | 115 | `TIMERCALLBACKTHRESHOLD` |
| 24 | `MATHFLOATMOD` | 70 | `BULLETCIRCLE` | 116 | `TIMERCALLBACKSUB` |
| 25 | `MATHATAN2` | 71 | `BULLETOFFSETCIRCLEAIMED` | 117 | `ENEMYFLAGINTERACTABLE` |
| 26 | `MATHNORMANGLE` | 72 | `BULLETOFFSETCIRCLE` | 118 | `EFFECTPARTICLE` |
| 27 | `CMPINT` | 73 | `BULLETRANDOMANGLE` | 119 | `DROPITEMS` |
| 28 | `CMPFLOAT` | 74 | `BULLETRANDOMSPEED` | 120 | `ANMFLAGROTATION` |
| 29 | `JUMPLSS` | 75 | `BULLETRANDOM` | 121 | `EXINSCALL` |
| 30 | `JUMPLEQ` | 76 | `SHOOTINTERVAL` | 122 | `EXINSREPEAT` |
| 31 | `JUMPEQU` | 77 | `SHOOTINTERVALDELAYED` | 123 | `TIMESET` |
| 32 | `JUMPGRE` | 78 | `SHOOTDISABLED` | 124 | `DROPITEMID` |
| 33 | `JUMPGEQ` | 79 | `SHOOTENABLED` | 125 | `STDUNPAUSE` |
| 34 | `JUMPNEQ` | 80 | `SHOOTNOW` | 126 | `BOSSSETLIFECOUNT` |
| 35 | `CALL` | 81 | `SHOOTOFFSET` | 127 | `DEBUGWATCH` |
| 36 | `RET` | 82 | `BULLETEFFECTS` | 128 | `ANMINTERRUPTMAIN` |
| 37 | `CALLLSS` | 83 | `BULLETCANCEL` | 129 | `ANMINTERRUPTSLOT` |
| 38 | `CALLLEQ` | 84 | `BULLETSOUND` | 130 | `ENEMYFLAGDISABLECALLSTACK` |
| 39 | `CALLEQU` | 85 | `LASERCREATE` | 131 | `BULLETRANKINFLUENCE` |
| 40 | `CALLGRE` | 86 | `LASERCREATEAIMED` | 132 | `ENEMYFLAGINVISIBLE` |
| 41 | `CALLGEQ` | 87 | `LASERINDEX` | 133 | `BOSSTIMERCLEAR` |
| 42 | `CALLNEQ` | 88 | `LASERROTATE` | 134 | `LASERCLEARALL` |
| 43 | `MOVEPOSITION` | 89 | `LASERROTATEFROMPLAYER` | 135 | `SPELLCARDFLAGTIMEOUT` |
| 44 | `MOVEAXISVELOCITY` | 90 | `LASEROFFSET` | | |
| 45 | `MOVEVELOCITY` | 91 | `LASERTEST` | | |
