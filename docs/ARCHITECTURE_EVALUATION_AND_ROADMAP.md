# pystg 架构评估与功能改造路线图

> 针对「多自机切换、护盾 Tag、潜入机制、分支对话、场景过渡」等剧本需求的架构评估与改造建议

---

## 一、当前架构评价

### 1.1 优点

| 方面 | 评价 |
|------|------|
| **分层清晰** | core / resource / game / render / ui 分层合理，职责边界明确 |
| **Stage 系统** | StageScript + Wave + SpellCard + EnemyScript 的协程驱动设计灵活，适合剧本化关卡 |
| **Context 抽象** | StageContext 作为引擎与内容的桥梁，内容脚本无需直接依赖 BulletPool 等实现 |
| **配置驱动** | 玩家、敌人预设、弹幕别名均可通过 JSON 配置，便于扩展 |
| **渲染管线** | ModernGL + 分层渲染（背景→敌弹→自机弹→自机→道具）结构清晰 |

### 1.2 需要改进的问题

| 问题 | 影响 |
|------|------|
| **Player 单例化** | `main.py` 直接 `load_player("tenshi")`，无多角色容器，无法做切换与状态保存 |
| **Option 强绑定** | OptionConfig 仅作为 PlayerShotSystem 的偏移配置，子机无法脱离玩家成为独立实体 |
| **碰撞无 Tag** | 玩家子弹只有 `damage`，无 `source_character`；敌人/Boss 无护盾、免疫逻辑 |
| **伤害判定分散** | `check_player_bullets_vs_enemies` 存在但未被主循环调用；enemy_manager 为 None，与 EnemyScript 两套体系并存 |
| **对话全暂停** | `dialog_active` 时跳过 `player.update` 和碰撞，无法实现「对话中并行演出」 |
| **对话线性** | DialogManager 仅支持顺序播放，无分支选项、无选项跳转 |
| **输入无脚本控制** | 无法通过剧本临时屏蔽切换键等输入 |
| **背景切换生硬** | 背景通过 `load_background()` 切换，无渐变、无平滑过渡 API |

---

## 二、功能改造路线图

### 2.1 多自机切换与子机分离 (Player & Option System)

#### 2.1.1 目标

- 实时在 天子 / 饕餮 / 阿燐 间切换
- 未上场角色保存：power、lives、bombs、spellcards
- 剧本可临时屏蔽特定角色的切换（如「阿燐暂时离队」）
- 子机可脱离玩家，成为独立发射实体（终符「饕餮和阿燐离队变子机」）

#### 2.1.2 建议改造

```
【新增】src/game/player/player_squad.py
├── PlayerSquad          # 多角色容器
│   ├── characters: List[PlayerBase]     # 所有可用角色
│   ├── active_index: int                # 当前上场角色索引
│   ├── switch_locked: Set[str]          # 剧本锁定的角色 ID（不可切换）
│   └── switch_character(id) -> bool    # 切换，受 switch_locked 约束
│
└── CharacterState       # 未上场角色的快照
    ├── character_id: str
    ├── power, lives, bombs, spellcards
    └── save_from(player) / restore_to(player)
```

```
【改造】src/game/player/player_shot.py
├── OptionConfig 增加:
│   ├── can_detach: bool = False        # 是否可脱离
│   └── detach_behavior: str = ""       # 脱离后的 AI 类型
│
└── 新增 DetachedOption 实体 (src/game/entity/detached_option.py)
    ├── 继承或组合 Entity
    ├── 独立 pos, 独立 PlayerBulletPool/发射逻辑
    ├── 可被 StageContext 创建与管理
    └── 渲染层需支持「非玩家控制的玩家子弹」渲染
```

```
【改造】main.py / 输入层
├── 将 player 替换为 player_squad: PlayerSquad
├── 切换键（如 C/V）→ player_squad.switch_character()
└── 输入层增加「可屏蔽键」接口，供 StageContext 调用
```

```
【新增】StageContext API
├── lock_character_switch(character_ids: List[str])   # 锁定角色不可切换
├── unlock_character_switch(character_ids: List[str])
└── spawn_detached_option(option_config, x, y, ai_type) -> DetachedOption
```

---

### 2.2 护盾与 Tag 伤害系统 (Damage & Shield System)

#### 2.2.1 目标

- 红/蓝/紫护盾，不同护盾免疫不同来源
- 子弹带 `source_character`（天子/饕餮/阿燐），护盾按 Tag 过滤伤害
- 觉 Boss：受击爆金币，金币归零即击破（非 HP 击破）

#### 2.2.2 建议改造

```
【改造】src/game/player/player_bullet.py (PlayerBulletPool)
├── dtype 增加字段:
│   └── ('source_tag', 'U16')   # 或 int 枚举: 0=天子, 1=饕餮, 2=阿燐
│
└── spawn() 增加参数 source_tag，由 PlayerShotSystem 传入
```

```
【改造】src/game/player/player_shot.py
├── ShotPattern / 发射逻辑 增加 source_tag
└── 从 PlayerBase 或 PlayerSquad 获取当前角色 ID → 映射为 source_tag
```

```
【新增】src/game/stage/damage_system.py
├── ShieldType: Enum (RED, BLUE, PURPLE)
├── ShieldConfig:  # 护盾配置
│   ├── immune_tags: Set[str]   # 免疫的 source_tag
│   └── color: ShieldType
│
├── DamageFilter.apply(bullet_source_tag, target_shield) -> bool  # 是否造成伤害
└── 与 CollisionManager 集成：碰撞后先过滤，再调用 target.damage()
```

```
【改造】EnemyScript / BossBase / SpellCard
├── 增加 shield: Optional[ShieldConfig]
├── 增加 defeat_condition: "hp" | "counter" | "custom"
├── 对于 "counter": defeat_counter, on_hit_decrement
└── damage(amount, source_tag) 内先过 Shield，再根据 defeat_condition 处理
```

```
【改造】src/core/collision.py
├── _check_player_bullets_vs_enemies 返回结果增加 source_tag
├── 或：在 CollisionManager 层，碰撞后调用 DamageFilter，再决定是否调用 target.damage()
└── 注意：Numba JIT 不便于传复杂对象，可考虑「碰撞返回 (b_idx, e_idx, damage, source_tag)」，在 Python 层做过滤
```

---

### 2.3 潜入/视野侦测与触发器 (Stealth & Trigger System)

#### 2.3.1 目标

- 天狗巡逻，玩家需停枪、少动躲避视野
- 敌人有可视化视野区域（圆形）
- 玩家进入视野 → 触发器批量改变 A/B 类敌人 AI

#### 2.3.2 建议改造

```
【新增】src/game/stage/vision_zone.py
├── VisionZone
│   ├── x, y, radius
│   ├── check_player_in(player, is_shooting, is_moving) -> bool
│   └── 渲染：半透明圆（可接入 renderer）
│
└── 与 EnemyScript 或独立 PatrolEnemy 组合
```

```
【新增】src/game/stage/trigger_system.py
├── Trigger
│   ├── condition: Callable[[StageContext], bool]   # 如「玩家在视野内」
│   ├── targets: List[str]   # 敌人 ID 或 "class_a" / "class_b"
│   └── action: Callable     # 改变 AI 状态、发射模式等
│
└── TriggerManager.update(ctx)  # 每帧检查，满足则执行 action
```

```
【改造】StageContext / PlayerProxy
├── PlayerProxy 增加:
│   ├── is_shooting: bool
│   └── is_moving: bool
└── 供 VisionZone 和 Trigger 使用
```

```
【改造】EnemyScript
├── ai_state: str = "idle" | "alert" | "attack"
├── set_ai_state(state)
└── 波次可 spawn 时指定 class_tag: "class_a" / "class_b"
```

---

### 2.4 背面出怪与同屏多 Boss

#### 2.4.1 目标

- 恋恋从屏幕后方出现、向上移动
- 早苗、青蛙子、神奈子同屏多 Boss

#### 2.4.2 建议改造

```
【改造】EnemyScript / PresetEnemy
├── spawn_from: "top" | "bottom" | "left" | "right" | "back"
├── "back" 即 y 从 < -1.2 或屏幕外下方入场，移动至 y=0.3 等
└── 渲染顺序：背面出怪可放在背景层与敌弹层之间
```

```
【改造】BossBase / StageScript
├── run_boss() 支持 run_bosses([boss_def1, boss_def2, boss_def3])
├── 多个 BossBase 同时 _active，共享 ctx
├── SpellCard 可绑定「当前负责伤害的 boss」或「所有 boss 共享 HP」
└── 需明确：多 Boss 时 HP 是独立还是共享，击破条件如何
```

---

### 2.5 分支选项对话 (Dialogue Branch System)

#### 2.5.1 目标

- 犬走椛等场景：A/B/C/D 四个选项
- 选项确认后跳转不同分支，影响后续对话与弹幕战结局

#### 2.5.2 建议改造

```
【改造】src/game/stage/dialog_data.py
├── DialogSentence 增加:
│   └── choices: Optional[List[Choice]]  # 选项列表
│
├── Choice
│   ├── text: str
│   ├── jump_to: str | int   # 跳转目标（节点 ID 或索引）
│   └── on_select: Optional[str]  # 可选，设置 flag
│
└── DialogSequence 改为图结构或显式节点
    ├── nodes: Dict[str, DialogNode]
    └── DialogNode: sentences + choices + next
```

```
【改造】src/game/stage/dialog_manager.py
├── 状态机支持「等待选项」
├── handle_choice(index) -> 跳转到对应分支
└── 与 UI 焦点、上下键、确认键集成
```

```
【新增】src/ui/dialog_choice_renderer.py
├── 渲染选项列表
├── 焦点高亮
└── 回调 on_choice_selected(index)
```

---

### 2.6 对话中并行演出 (Dialogue + Parallel Gameplay)

#### 2.6.1 目标

- 对话进行时，弹幕、物理、碰撞继续运行
- 例：山城高岭对话中，怨灵诱导弹飞来并炸飞角色

#### 2.6.2 建议改造

```
【改造】main.py 主循环
├── 移除「dialog_active 时跳过 player.update 和碰撞」
├── 改为：dialog_active 时仍执行 update 和碰撞，但可配置「对话时玩家是否可操作」
└── 新增 dialogue_blocks_input: bool 配置
```

```
【改造】StageContext / 剧本
├── play_dialogue(..., block_input=False)  # 不阻塞输入
├── play_dialogue(..., pause_game=False)   # 不暂停游戏逻辑（弹幕、碰撞继续）
└── 默认可保持 block_input=True, pause_game=False 以支持「对话中挨打」
```

---

### 2.7 关卡场景平滑过渡 (Smooth Background Transition)

#### 2.7.1 目标

- 道中切换到地灵殿、进入九泉瀑布洞穴等
- 背景贴图渐变或淡入淡出，不打断游戏

#### 2.7.2 建议改造

```
【改造】src/game/background_render/
├── BackgroundRenderer 增加:
│   ├── transition_to(background_id, duration=60, mode="crossfade")
│   └── _transition_progress, _transition_from, _transition_to
│
├── 支持 mode: "crossfade" | "fade_black" | "slide"
└── 每帧更新 _transition_progress，混合两个背景
```

```
【新增】StageContext API
└── transition_background(background_id, duration=60)
```

---

## 三、建议的改造顺序

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **P0** | 补全玩家子弹 vs 敌人/Boss 碰撞与伤害流程 | 无 |
| **P1** | PlayerSquad + 多角色切换 + 状态保存 | 无 |
| **P2** | 子弹 source_tag + 护盾 DamageFilter + 非常规击破 | P0 |
| **P3** | 输入屏蔽 API + lock_character_switch | P1 |
| **P4** | DetachedOption 子机独立化 | P1 |
| **P5** | 对话分支选项 + 选项 UI | 无 |
| **P6** | 对话中并行演出（不暂停游戏） | 无 |
| **P7** | VisionZone + Trigger 系统 | 无 |
| **P8** | 背面出怪 + 同屏多 Boss | 无 |
| **P9** | 背景平滑过渡 | 无 |

---

## 四、需要统一/清理的现状

1. **enemy_manager 与 EnemyScript 双轨**  
   建议：以 `ctx._enemy_scripts` 为主，实现一个 `EnemyScriptAdapter` 满足 `get_active_enemies()` 接口，供 `check_player_bullets_vs_enemies` 使用；或直接在 Stage 更新中做「玩家子弹 vs enemy_scripts」的碰撞与伤害。

2. **BossManager 与 BossBase**  
   当前 `get_active_boss()` 来自 `boss_manager`，而关卡实际用 `_current_boss`。建议统一：要么 Stage 向 boss_manager 注册 BossBase，要么主循环从 `stage.current_stage._current_boss` 取 Boss 做 HUD 与碰撞。

3. **碰撞与伤害调用链**  
   主循环应显式调用「玩家子弹 vs 当前敌人/Boss」的碰撞，并在过滤（护盾等）后调用 `enemy.damage()` / `boss.damage()`。

---

## 五、小结

当前架构在分层和扩展性上基础较好，但要支撑剧本中的多自机、护盾 Tag、潜入、分支对话和演出需求，需要：

1. **Player 层**：引入 PlayerSquad、角色状态快照、输入屏蔽、子机独立化；
2. **伤害层**：子弹 Tag、护盾过滤、非常规击破条件；
3. **Stage 层**：VisionZone、Trigger、多 Boss、背景过渡 API；
4. **对话层**：分支选项、并行演出模式；
5. **主循环**：补全玩家子弹伤害流程，并支持「对话中不暂停游戏」的配置。

按上述路线图分阶段实施，可以逐步满足剧本要求，同时保持现有结构的稳定性。
