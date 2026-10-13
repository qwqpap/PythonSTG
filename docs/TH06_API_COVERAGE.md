# TH06 引擎 API 覆盖清单

本文件是机制对照，不是另一份 TODO；实施顺序和唯一状态记录仍在
[EDITOR_IMPLEMENTATION_TODO.md](EDITOR_IMPLEMENTATION_TODO.md)。

目标是用普通 Python 内容脚本表达六关和 Extra，不是引入 ECL VM，也不是声称素材、关卡
内容和像素表现已经复刻。参考源码：
[YomotsuHisami/th06](https://github.com/YomotsuHisami/th06)，核对提交
`fa4d48f66d4701fef6c5e802ca85a738b0d5177c`。这是从此前
`eagler-touhou` 调查延续的 TH06 checkout；不能把其源码指令清单当成原作全部 ECL 文件已执行。

## 1. 支持与验收怎么区分

- **可表达**：普通内容 API 能组合出机制，不需要改 Pool 私有状态或逐弹回调。
- **已实跑**：指定数学、时序或真实 Runtime 路径实际运行通过；不是全部关卡通过。
- **缺口**：仍缺接口、正式接线或规则可配置性。
- **未验收**：缺原作脚本/资源、真实呈现或独立对照，不能算完成。

接口覆盖、生成器覆盖、纯 GUI 可编辑性、完整内容、像素一致性是五件不同的事。本轮不改 GUI；
新增高级规则走 Runtime/RawPython，不把它们写成已经有对应拖拽节点。

## 2. 按机制对照

| 指令范围 | 对应普通 API/结构 | 当前边界 |
| --- | --- | --- |
| 0–3 | Python 空语句、循环、条件、await wait | 1 是参考的未实现槽，不是待造的玩法 |
| 4–12 | 局部变量、seed RNG、actor.x/y | 2D actor 不提供独立 3D z；原作 z 用途仍需内容核对 |
| 13–26 | Python 算术、math/NumPy；批量公式可用 Numba | C 整数截断/负余数须在移植代码中显式保持，不把 Python 运算误称字节级兼容 |
| 27–42 | if/while、普通函数、FrameTask/await | ECL 栈/指令地址不保留；正常玩法可重新组织控制流 |
| 43–51 | set_position、move_linear、move_velocity、RNG/玩家快照 | 归一化单位/秒；运动控制参数可由 actor 任务局部更新 |
| 52–64 | move_to 的 linear、平方/四次方 ease_in/out | 共用 Enemy/Boss；固定 actor 数量使用协程，不逐弹使用 |
| 65–66 | set_movement_bounds、clear_movement_bounds | set_position 与全部标准移动尊重边界 |
| 67–75 | fire_arc/fire_circle、自机角、create_bullets_batch 数组 | 偏移环、随机角/速度、多层为普通数组组合；仍缺逐模式原作金值对照 |
| 76–81 | actor Task 的 wait/循环、可取消句柄、局部 enabled、发射坐标 | 不增加第二个隐藏发射时钟；birth 下一仿真步才移动 |
| 82 | set_bullet_behavior、二维加速度、限次反弹/穿屏、批量变换 | 不是把所有 ECL effect flag 自动翻译；每类参数仍需对应内容证明 |
| 83–84 | clear/tag/group/to_items、play_se | 自然终结与清场/Bomb 原因不同，不默认触发分裂 |
| 85–92 | create_laser、configure_motion/lifecycle、angle/set_position、alive、destroy | 真实 LaserPool/renderer/collision；midpoint 只表达原作过渡轴向框，不承诺完整像素碰撞 |
| 93–94 | BossPhase、SpellCard、end、end_reason、bonus_rule/finish_rule、SpellResult | 奖励读取最终帧；结束前保留规则所需活弹；原作捕获/bonus/掉落策略尚未全部移植 |
| 95–96 | Wave.spawn_enemy、Context.add_enemy_script、Enemy.kill/dispose | 两者语义不同：kill 有击破/掉落反应，dispose 是取消 |
| 97–100 | 现有 EnemyRenderObject 和资源动画 | 缺公开完整的主动画/pose/附属 VM/死亡动画控制；不是原 ANM VM |
| 101–102 | BossDef/run_boss、现有符卡宣言/背景接口 | 装饰特效/颜色参数尚未全覆盖 |
| 103–105 | hitbox_radius/hit_radius、set_interaction(collidable/damageable) | 真自机弹/追踪筛选；不可受伤但可受击适用于假身 |
| 106–108 | play_se、Enemy.kill/dispose、on_death 可由 Context 继续 | 原 deathMode 的“保留同一实体继续行为”仍需逐机制对照 |
| 109–110 | 稀疏事件、on_hit、取消/启动 actor Task | 不保留 ECL 调用栈 ABI；等待/恢复/替换由显式任务组织 |
| 111–116 | hp、wait_until、Spell.set_timer、timer_frames/time_remaining | 控制帧时钟与 Boss 计时分开；HP/计时切换由内容声明，不能读写任务私有时钟 |
| 117 | set_interaction(interactable) | 不可交互时不被追踪/命中，和 visible/damageable 独立 |
| 118–120 | spawn_item/spawn_drop、emit_particles、ParticleEffect | 独立非碰撞粒子已接更新/绘制/清理/时停；缺原作 ANM 内容、actor 动画旋转，掉落表尚未全部移植 |
| 121–123 | 普通函数/整批公式/actor Task/局部时间变量 | 17 个特殊函数见下一节；TIMESET 不重绕正式帧时钟 |
| 124 | spawn_item/spawn_drop、set_item_collection_rule、GameStats 稀疏规则 | 可配置 128P、得点、extend、溢出；示例不是原作完整精确表，Deathbomb 状态机仍未移植 |
| 125 | 背景切换/transition、stop_time('background') | 独立背景暂停已接正式循环；camera/fog/STD scene 编排尚未全覆盖 |
| 126–130 | 当前 Boss HUD、普通 Python 调试/动画/控制流 | 不复制 DEBUGWATCH/调用栈布局；Boss 可变显示 life count 和 ANM 中断缺公开完整接口 |
| 131 | ctx.run_state.rank/subrank/adjust_rank/rank_value | 跨关共享；miss/Bomb 通知及收集/擦弹规则已接线；默认不套 TH06，原作各事件策略尚未全部移植 |
| 132–135 | visible、Spell.set_timer、clear_all_lasers、is_timeout/is_survival、finish_rule | visibility 接正式绘制；可按 SpellResult 区分生存超时/普通击破；示例不是完整原作收符规则 |

难度/机体/rank 是输入，不是弹幕内偷偷硬编码的全局变量。StageManager 持有 RunState，
新关卡复用同一实例；独立预览重启恢复其初始输入。PlayerProxy.is_bombing 读取玩家
Bomb 激活/增伤窗口，`BombAwareBat` 保留同一敌人并在该窗口结束后等 60 帧重新交互；
不是母弹转换为新 Enemy。窗口不保证等于角色视觉 Bomb 生命周期，原作持续时间仍需对照。
游戏换玩家统一通过 `StageManager.bind_player` 同步引用与 shot；当前角色不是原作四机体。
收集、擦弹、得分、miss、continue、Bomb 和符卡结算均有正式稀疏规则入口。未配置时保留
原有默认；`th06_rules.py` 只展示 128P/8P、rank 和生存超时策略，不以演示公式冒充原作表。

## 3. 17 个特殊函数

参考均为 `src/EnemyEclInstr.cpp`，行号以核对提交为准。API 可表达与同公式已实跑分别记录。

| 函数/行 | 核心机制 | 路径与缺口 |
| --- | --- | --- |
| CirnoRainbowBallJank:433 | 停弹→每弹随机二维加速度，220 帧后清加速度 | shared stages、整批 NumPy RNG、vector_accel；原随机序列尚未逐函数验收 |
| ShootAtRandomArea:482 | 每次随机发射原点 | create_bullets_batch positions；内容公式 |
| ShootStarPattern:496 | 星形边插值，保留敌/玩家初始快照 | NumPy positions + 初始玩家快照；完整星形内容尚未实跑 |
| PatchouliShottypeSetVars:569 | 按玩家机体/shot 分支 | ctx.player_shot/difficulty；作者定义标识，不臆造当前角色是原作四机体 |
| Stage56Func4:579 | 世界时停 + 有限数量随机改向 | stop_time 的分系统作用域；数组 mask/选前 N；GUI/特效染色不等同复刻 |
| Stage5Func5:682 | 九组位置矩阵发射 | NumPy positions/angles/speeds；不生成九组逐弹 Task |
| BatWingEffect:762 | 装饰粒子 | th06_particles.wing_pair 使用公开独立粒子 API、递增发射节奏、镜像位置与恒定减速；原贴图/附属动画/随机序列未移植 |
| Stage6Func7:818 | 两组八方向、三层、48 条独立时窗激光 | th06_controls.crossed_lasers；easy/normal 与 hard/lunatic 几何分支 |
| Stage6Func8:934 | 大弹当前位置派生静止小弹 | read_bullets(pos)→批量出生；具体颜色/周期为内容 |
| Stage6Func9:972 | 停弹按距 Boss 的公式启动/加速度 | th06_patterns.distance_turn；前轮已通过独立标量对照 |
| Stage6Func11:1019 | 停弹随机启动加速度，120 帧后清除 | snapshot/select + vector_accel + 整批 actor Task |
| HandleBatTransformation:1055 | Bomb 期间已存在的敌人不交互，结束后 60 帧恢复 | BombAwareBat 和 wing_pair 可组合；激活窗口和独立粒子已接线，原作 Bomb 持续时间/动画/粒子视觉仍未完整对照 |
| Stage4Func12:1089 | 激光方向距敌 64px 的点发射 | Laser.angle + actor 位置 + 批量 positions |
| StageXFunc13:1105 | 每六帧从圆周点发射 | 普通循环/共享局部角度；非逐弹极坐标对象 |
| StageXFunc14:1128 | 当前激光段每 48px 发弹，严格不到 end | Laser.sample_points + fire_along_lasers；随运动段变化 |
| StageXFunc15:1161 | 严格邻域、slot 顺序 first-match 激活 | th06_patterns.neighbor_turn；前轮独立公式/顺序对照 |
| FlandreFinalContextUpdate:1225 | HP/计时影响速度、间隔、随机域 | boss.hp、spell.timer_frames、数组发射；完整最终符内容未实跑 |

## 4. 性能与验证边界

- 大量子弹仍在现有结构化数组/Numba 内核；不把 50k Bullet 变成 50k FrameTask。
- actor/事件/Boss 规则是稀疏控制。48/100 Laser 更新与碰撞单独测量，不借弹池数值宣称激光性能。
- JIT 冷编译、预热后 CPU 更新、GL 提交/实际 GPU 呈现分别记录；Rust 不进入本轮。
- 独立符卡预览拥有正式 Pool/Context/EventBus；成功重启会替换全部池。渲染必须读当前池，
  不能继续读调用者最初传入的旧池。候选 bind/start 发射只影响候选；失败保留旧实例。
- 时停不调用 renderer 当作游戏时钟。主循环按 mask 暂停相关 update，actor 任务继续；
  Boss elapsed timer 独立暂停/重置，不倒退任务时钟/Trace。
  effects 域暂停粒子池和 emoji 系统，不是全部 GUI/装饰动画。
- 当前即时 Runtime/生成子进程/Native/Performance 结果统一记 TODO。本清单不借旧测试
  计数证明新代码，也不宣称 maintainer/new-user Usability 已通过。
- 独立工具绘制真实激光/道具/粒子与当前弹池；转换敌人仍是位置标记，缺完整玩家流程。真正的
  PySide6 嵌入与整关输入链本批 not run，GL 压力帧不能替代它们。

## 5. 尚未关闭的主要缺口

1. 原作六关/Extra、每难度、四机体的实际 ECL/资源内容移植与整体对照；当前是机制清单和样例。
2. Item/得点/extend/rank/Bomb/符卡 bonus/捕获/掉落的原作精确内容策略及完整死亡/Deathbomb
   流程。可配置规则和真实收集/得分/擦弹/miss/continue/Bomb 接线已加入，不等于策略已移植。
3. 主/附属/死亡动画、Boss 演出/HUD 可配置控制；粒子通用 API 已加入，但原作粒子 ANM、
   三维深度和附属动画仍未移植，不要求复制原作 VM。
4. camera/fog/scene 时间编排，以及原作 GUI/时停视觉细节；分系统背景暂停/恢复已接线。
5. 对全部发射模式、effect flags、ExIns 的正常内容样例和独立原作标量/时序/呈现验证。

## 6. 粒子专项边界（2026-10-13）

参考 `src/EffectManager.cpp` 的 20 类粒子：0–2/12 是爆发/停弹闪光，3–11 是随机散射和
恒定减速，17/18 是固定方向的 60/240 帧收拢，19 是给定速度/加速度的双翼颗粒。
这些运动和贴图帧/颜色/alpha/尺寸/旋转由 ParticleEffect 与公开 emit_particles 表达；
原作寿命/视觉来自 ANM，当前示例只验证独立机制，不声称新视觉时序等于 ANM。
13–15 可用整群 transform_particles 表达旋转轨迹的二维投影和 16 帧淡出/放大；示例为
一个 Task 的 NumPy Rodrigues 旋转，不建 48 个粒子回调，也未接原作轴向/radius 控制器
和三维深度。16 属于符卡背景演出，应继续走既有背景编排，不把背景塞进碰撞弹池。

维护者提供的 Steam 本地 `th06c` 中七个 .dat 魔数均为 `PKGL`；参考 checkout 的 PBG3
读取器不能直接使用。当前只读确认了格式，没有解码这些资源，也没有将游戏数据提交到
仓库。源代码开源不代表原作图像/音乐可再分发。通用粒子 API 的真实 GL 验证使用现有
引擎图集，游戏数据的本机抽取/动画时序对照仍是明确待办，不假报资源已复刻。

## 附录：136 项指令索引

下面完整列出枚举，不省略难实现项。短名均省去 `ECL_OPCODE_` 前缀；
序号与上面的范围表对应，索引本身不代表已实现 ECL 兼容层。

| 编号 | 名称 |
| --- | --- |
| 0 | NOP |
| 1 | UNIMP |
| 2 | JUMP |
| 3 | JUMPDEC |
| 4 | SETINT |
| 5 | SETFLOAT |
| 6 | SETINTRAND |
| 7 | SETINTRANDMIN |
| 8 | SETFLOATRAND |
| 9 | SETFLOATRANDMIN |
| 10 | SETVARSELFX |
| 11 | SETVARSELFY |
| 12 | SETVARSELFZ |
| 13 | MATHINTADD |
| 14 | MATHINTSUB |
| 15 | MATHINTMUL |
| 16 | MATHINTDIV |
| 17 | MATHINTMOD |
| 18 | MATHINC |
| 19 | MATHDEC |
| 20 | MATHFLOATADD |
| 21 | MATHFLOATSUB |
| 22 | MATHFLOATMUL |
| 23 | MATHFLOATDIV |
| 24 | MATHFLOATMOD |
| 25 | MATHATAN2 |
| 26 | MATHNORMANGLE |
| 27 | CMPINT |
| 28 | CMPFLOAT |
| 29 | JUMPLSS |
| 30 | JUMPLEQ |
| 31 | JUMPEQU |
| 32 | JUMPGRE |
| 33 | JUMPGEQ |
| 34 | JUMPNEQ |
| 35 | CALL |
| 36 | RET |
| 37 | CALLLSS |
| 38 | CALLLEQ |
| 39 | CALLEQU |
| 40 | CALLGRE |
| 41 | CALLGEQ |
| 42 | CALLNEQ |
| 43 | MOVEPOSITION |
| 44 | MOVEAXISVELOCITY |
| 45 | MOVEVELOCITY |
| 46 | MOVEANGULARVELOCITY |
| 47 | MOVESPEED |
| 48 | MOVEACCELERATION |
| 49 | MOVERAND |
| 50 | MOVERANDINBOUND |
| 51 | MOVEATPLAYER |
| 52 | MOVEDIRTIMEDECELERATE |
| 53 | MOVEDIRTIMEDECELERATEFAST |
| 54 | MOVEDIRTIMEACCELERATE |
| 55 | MOVEDIRTIMEACCELERATEFAST |
| 56 | MOVEPOSITIONTIMELINEAR |
| 57 | MOVEPOSITIONTIMEDECELERATE |
| 58 | MOVEPOSITIONTIMEDECELERATEFAST |
| 59 | MOVEPOSITIONTIMEACCELERATE |
| 60 | MOVEPOSITIONTIMEACCELERATEFAST |
| 61 | MOVETIMEDECELERATE |
| 62 | MOVETIMEDECELERATEFAST |
| 63 | MOVETIMEACCELERATE |
| 64 | MOVETIMEACCELERATEFAST |
| 65 | MOVEBOUNDSSET |
| 66 | MOVEBOUNDSDISABLE |
| 67 | BULLETFANAIMED |
| 68 | BULLETFAN |
| 69 | BULLETCIRCLEAIMED |
| 70 | BULLETCIRCLE |
| 71 | BULLETOFFSETCIRCLEAIMED |
| 72 | BULLETOFFSETCIRCLE |
| 73 | BULLETRANDOMANGLE |
| 74 | BULLETRANDOMSPEED |
| 75 | BULLETRANDOM |
| 76 | SHOOTINTERVAL |
| 77 | SHOOTINTERVALDELAYED |
| 78 | SHOOTDISABLED |
| 79 | SHOOTENABLED |
| 80 | SHOOTNOW |
| 81 | SHOOTOFFSET |
| 82 | BULLETEFFECTS |
| 83 | BULLETCANCEL |
| 84 | BULLETSOUND |
| 85 | LASERCREATE |
| 86 | LASERCREATEAIMED |
| 87 | LASERINDEX |
| 88 | LASERROTATE |
| 89 | LASERROTATEFROMPLAYER |
| 90 | LASEROFFSET |
| 91 | LASERTEST |
| 92 | LASERCANCEL |
| 93 | SPELLCARDSTART |
| 94 | SPELLCARDEND |
| 95 | ENEMYCREATE |
| 96 | ENEMYKILLALL |
| 97 | ANMSETMAIN |
| 98 | ANMSETPOSES |
| 99 | ANMSETSLOT |
| 100 | ANMSETDEATH |
| 101 | BOSSSET |
| 102 | SPELLCARDEFFECT |
| 103 | ENEMYSETHITBOX |
| 104 | ENEMYFLAGCOLLISION |
| 105 | ENEMYFLAGCANTAKEDAMAGE |
| 106 | EFFECTSOUND |
| 107 | ENEMYFLAGDEATH |
| 108 | DEATHCALLBACKSUB |
| 109 | ENEMYINTERRUPTSET |
| 110 | ENEMYINTERRUPT |
| 111 | ENEMYLIFESET |
| 112 | BOSSTIMERSET |
| 113 | LIFECALLBACKTHRESHOLD |
| 114 | LIFECALLBACKSUB |
| 115 | TIMERCALLBACKTHRESHOLD |
| 116 | TIMERCALLBACKSUB |
| 117 | ENEMYFLAGINTERACTABLE |
| 118 | EFFECTPARTICLE |
| 119 | DROPITEMS |
| 120 | ANMFLAGROTATION |
| 121 | EXINSCALL |
| 122 | EXINSREPEAT |
| 123 | TIMESET |
| 124 | DROPITEMID |
| 125 | STDUNPAUSE |
| 126 | BOSSSETLIFECOUNT |
| 127 | DEBUGWATCH |
| 128 | ANMINTERRUPTMAIN |
| 129 | ANMINTERRUPTSLOT |
| 130 | ENEMYFLAGDISABLECALLSTACK |
| 131 | BULLETRANKINFLUENCE |
| 132 | ENEMYFLAGINVISIBLE |
| 133 | BOSSTIMERCLEAR |
| 134 | LASERCLEARALL |
| 135 | SPELLCARDFLAGTIMEOUT |
