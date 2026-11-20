# 弹幕脚本开发指南

本文面向在 `game_content/` 下手写关卡、波次、敌人与 Boss 符卡的开发者，涵盖从基础协程写法到批量弹幕行为、视觉演出和玩法规则扩展的完整公开 API。

> 声明式关卡编辑器工程使用 `src.authoring.dsl`，详见 [快速开始](getting-started.md) 和 [编辑器设计概览](EDITOR_PRODUCT_VISION.md)。两者共用同一套引擎运行时。

---

## 1. 四层内容结构

手写关卡按职责拆为四个层次：

| 层级 | 基类 | 职责 |
| --- | --- | --- |
| 整面流程 | `StageScript` | 串联道中波次、中 Boss、对话、关底 Boss 与 BGM |
| 道中波次 | `Wave` | 编排一段时间内敌人的出场节奏与位置 |
| 单个敌人 | `EnemyScript` | 描述一个小怪从出生、移动、发弹到退场的完整行为 |
| Boss 攻击 | `SpellCard` / `NonSpell` | 描述 Boss 单个非符或符卡阶段的攻击逻辑 |

推荐目录布局：

| 路径 | 作用 |
| --- | --- |
| `game_content/stages/stage1/__init__.py` | 关卡包入口 |
| `game_content/stages/stage1/stage_script.py` | 整面流程与 `BossDef` 定义 |
| `game_content/stages/stage1/waves/*.py` | 道中波次脚本 |
| `game_content/stages/stage1/enemies/*.py` | 可复用敌人脚本 |
| `game_content/stages/stage1/spellcards/*.py` | Boss 非符与符卡脚本 |
| `game_content/stages/stage1/dialogue/` | 对话脚本 |
| `game_content/stages/stage1/audio/` | 关卡私有音频（可覆盖全局同名音效） |

新增 `StageScript` 后，在 `game_content/entry.py` 中将其加入 `STAGES`（确保 `id` 唯一），即可通过 `python main.py --stage=<id>` 启动；也可以通过 `--content-entry <模块路径>` 加载独立入口模块。

---

## 2. 坐标系、角度与单位约定

游戏逻辑区域按东方经典比例 `384 × 448`（宽高比 `6:7`）映射到归一化世界坐标：

| 维度 | 范围 / 约定 | 说明 |
| --- | --- | --- |
| `x` | `-1.0 ~ +1.0` | `-1.0` 为左边界，`+1.0` 为右边界，`0.0` 为水平中心 |
| `y` | `-1.167 ~ +1.167` | `-1.167` 为底边界，`+1.167` 为顶边界，`0.0` 为垂直中心；Boss 常在 `y ∈ [0.3, 0.8]` 活动，玩家初始位于底部附近 |
| 角度 | **度（°）** | `0°` 向右、`90°` 向上、`-90°`（`270°`）向下、`180°` 向左 |
| 时间 | **帧（60 Hz）** | `await self.wait(60)` 等于 1 秒；`max_lifetime` 等秒级字段会特别注明 |

### 速度与加速度单位

不同系统的单位有明确区分，编写时不要混用：

- **敌弹作者接口（`fire` / `create_bullet` / `create_bullets_batch` / `set_bullet_behavior`）**：
  - `speed` 使用作者速度标度（传入底层池前自动除以 `60`），一般慢弹约 `1.5`、普通约 `2.5`、快弹 `4.0+`。
  - `accel` 为每秒改变的作者速度；`angle_accel` 为 `度/秒²`；`turn_rate` / `max_turn_rate` / `spin` 为 `度/秒`。
  - `configure_bullet_birth` 的 `velocity_boost` 是世界归一化单位/秒。
- **敌人 / Boss 移动、激光移动、道具、粒子**：
  - 速度为归一化世界单位/秒，粒子加速度为归一化世界单位/秒²。
- **底层池直接调用（如 `pool.spawn_bullet` 或 `src.content_api` 数值内核）**：
  - 角度使用弧度，速度使用世界单位/帧。

---

## 3. 关卡、波次与敌人

### 3.1 整面流程（`StageScript`）

```python
from src.game.stage.stage_base import StageScript, BossDef
from src.game.stage.boss_base import nonspell, spellcard


class Stage1(StageScript):
    id = "stage1"
    name = "Stage 1"
    title = "第一面标题"
    bgm = "00.wav"
    boss_bgm = "01.wav"
    background = "stage1_bg"

    boss = BossDef(
        id="boss1",
        name="Boss Name",
        texture="star",
        phases=[
            nonspell(NonSpell1, hp=800, time=30, bonus=100000),
            spellcard(MySpell, "火符「Example」", hp=1000, time=45, bonus=500000),
        ],
    )

    async def run(self):
        await self.run_wave(OpeningWave)
        await self.wait(60)
        await self.run_boss(self.midboss, is_midboss=True)
        await self.play_dialogue([
            {
                "character": "Hinanawi_Tenshi",
                "name": "天子",
                "position": "left",
                "text": "准备好了吗？",
                "portrait": "Happy",
            },
        ])
        await self.run_boss(self.boss)
```

常用方法：`wait(frames)`、`wait_seconds(sec)`、`run_wave(WaveClass)`、`run_boss(boss_def, is_midboss=False)`、`play_dialogue(lines)`、`play_bgm(name)`。

对话条目支持简写元组 `("角色ID", "left", "台词")` 和带立绘的字典格式（`character`、`name`、`position`、`text`、`portrait`）。显示名优先级为 `脚本 name > character.json 的 display_name > 角色 ID`。

### 3.2 波次与敌人（`Wave` / `EnemyScript`）

```python
from src.game.stage.wave_base import Wave
from src.game.stage.enemy_script import EnemyScript


class SideFlyFairy(EnemyScript):
    hp = 30
    sprite = "enemy_fairy"

    async def run(self):
        await self.move_to(self.x, 0.5, duration=40)
        for _ in range(3):
            self.fire_at_player(speed=2.2, bullet_type="ball_s", color="red")
            await self.wait(20)
        await self.move_linear(0.0, -0.8, duration=80)


class FairyWave(Wave):
    DEBUG_BOOKMARK = True  # 加入 --debug 跳转菜单

    async def run(self):
        for i in range(5):
            self.spawn_enemy_class(SideFlyFairy, x=-0.8 + i * 0.2, y=1.0)
            await self.wait(20)
        await self.wait(180)
```

`DEBUG_BOOKMARK = True` 对关卡 `waves/` 中的 `Wave` 以及注册进 `BossDef.phases` 的攻击类生效，方便在 `python main.py --debug` 中直接跳转测试。

---

## 4. Boss 与符卡生命周期

### 4.1 基本写法与回调

```python
from src.game.stage.spellcard import SpellCard


class MySpell(SpellCard):
    name = "火符「Example」"
    hp = 1000
    time_limit = 45
    bonus = 500000
    DEBUG_BOOKMARK = True

    async def setup(self):
        await self.boss.move_to(0.0, 0.5, duration=30)

    async def run(self):
        angle = 0
        while True:
            self.fire_circle(count=12, speed=2.0, start_angle=angle, color="red")
            angle += 10
            await self.wait(15)

    def on_defeated(self):
        self.play_se("cardget")

    def on_timeout(self):
        self.clear_bullets()
```

常用属性与等待：

- `self.time`：当前仿真时间（慢速下为浮点数）；未缩放控制帧可读取 `self.ctx.runtime_frame`。
- `self.time_seconds` / `self.time_remaining` / `self.timer_frames`：Boss 阶段计时；可用 `self.set_timer(elapsed_frames=0)` 重置倒计时而不影响协程时钟。
- `self.boss`：Boss 对象（`x`、`y`、`hp` 及移动/动画方法）。
- `await self.wait_until(condition)`：在符卡中等待条件成立。

### 4.2 阶段切换、HP 阈值与自定义结算

`nonspell()` / `spellcard()`（即 `BossPhase`）支持丰富的阶段策略：

```python
from src.game.stage.boss_base import nonspell, spellcard


def custom_bonus(boss, spell):
    return int(spell.bonus * max(0.5, spell.time_remaining / spell.time_limit))


def custom_finish(boss, result):
    if (
        result.reason == "defeated"
        and result.no_miss
        and result.no_bomb
        and result.capture_failure_reason is None
    ):
        boss.ctx.add_score(result.bonus)
    boss.ctx.bullets_to_items(boss.ctx.select_bullets())
    boss.ctx.clear_all_lasers()


phases = [
    nonspell(
        NonSpell1,
        hp=15000,
        time=60,
        hp_threshold=1500,   # HP 严格小于 1500 时切入下一阶段
        carry_hp=True,       # 下一阶段继承剩余 HP
    ),
    spellcard(
        MySpell,
        "火符「Example」",
        hp=1500,
        time=45,
        auto_declaration=False,          # 手动在演出后调用 boss.declare_spell()
        declaration_blocks_spell=False,  # 宣言不阻塞弹幕脚本启动
        bonus_rule=custom_bonus,
        finish_rule=custom_finish,
    ),
]
```

- `BossPhase` 还支持 `transition_rule`（决定击破/阈值/超时后的分支跳转）和 `damage_rule`（自定义同帧伤害聚合，如伤害上限、减伤或副受弹区加权）。
- `BossDef.boss_class` 允许指定自定义 `BossBase` 子类；自定义目标可实现 `damage_batch(hits)` 接收同帧全部 `DamageHit`（包含 `source`、`region`、`attack_index`、`attack_generation`）。
- 配置 `finish_rule` 后，引擎不会在回调前自动清屏，方便结算逻辑读取当前活弹。

---

## 5. 基础发弹 API 与内置曲线

以下方法在 `SpellCard`、`NonSpell`、`EnemyScript` 和 `Wave` 中均可调用：

### 5.1 发射方法

```python
# 单发
self.fire(
    x=0.0, y=0.5,            # 默认为当前 Boss / 敌人位置
    angle=-90,               # 角度（度）
    speed=2.0,               # 作者速度标度
    bullet_type="ball_m",
    color="red",
    accel=0.0,               # 标量加速度（每秒改变 speed）
    angle_accel=0.0,         # 运动角加速度（度/秒²）
    tag=0,                   # 分组标签
    friction=0.0,            # 摩擦/阻尼系数（>0 逐渐减速）
    time_scale=1.0,          # 单弹时间倍率
    bounce_x=False,          # 左右边界反弹（x ∈ [-1.0, 1.0]）
    bounce_y=False,          # 上下边界反弹（y ∈ [-1.14, 1.0]）
    spin=0.0,                # 贴图自转角速度（度/秒）
    render_angle=None,       # 固定贴图朝向（None=跟随运动角）
    render_angle_offset=0.0, # 持续叠加的贴图角度偏移（度）
    render_flip_y=False,     # 局部翻转贴图 V 方向
    curve_type=0,            # 内置曲线类型
    curve_params=None,       # (amplitude, frequency, phase, base_value)
)

# 圆形均匀扩散
self.fire_circle(count=24, speed=2.0, start_angle=0, bullet_type="ball_m", color="blue")

# 扇形
self.fire_arc(
    count=7,
    speed=2.5,
    center_angle=self.angle_to_player(),
    arc_angle=60,
    bullet_type="grain_a",
    color="green",
)

# 自机狙
self.fire_at_player(speed=3.0, offset_angle=0.0, bullet_type="arrow_m", color="red")

# 极坐标 / 轨道弹（fire_orbit 为别名）
self.fire_polar(
    orbit_radius=0.15,
    theta=0,
    radial_speed=0.05,
    angular_velocity=120,
    bullet_type="ball_s",
    color="cyan",
    center=None,             # 默认跟随 Boss；可传 (x, y) / 对象 / callable
    render_mode="velocity",  # velocity / radial / inward / fixed
)
```

### 5.2 内置数学曲线

内置曲线在 Numba 内核中直接计算：

```python
from src.game.bullet import (
    CURVE_NONE,
    CURVE_SIN_SPEED,     # speed = base + amp * sin(freq * t + phase)
    CURVE_SIN_ANGLE,     # angle += amp * sin(freq * t + phase) * dt
    CURVE_COS_SPEED,     # speed = base + amp * cos(freq * t + phase)
    CURVE_LINEAR_SPEED,  # speed = base + amp * t
)

self.fire(
    angle=-90,
    speed=2.0,
    bullet_type="kite",
    color="green",
    curve_type=CURVE_SIN_ANGLE,
    curve_params=(2.0, 5.0, 0.0, 0.0),
)
```

### 5.3 消弹与标签控制

```python
self.clear_bullets()                      # 清除本对象发射的子弹
self.clear_bullets(to_items=True)         # 清除并转为道具
self.ctx.clear_all_bullets()              # 清屏（同时撤销终结反应、延迟队列与行为定义）
self.ctx.clear_bullets_by_tag(1)          # 按标签清弹
self.ctx.bullets_by_tag_to_item(1)        # 按标签转道具
self.ctx.set_time_scale(0.0, tag=1)       # 冻结 tag=1 的敌弹
self.ctx.set_time_scale(1.0, tag=1)       # 恢复正常速度
```

### 5.4 隐形发射器（Emitter）

需要沿轨迹持续产弹的隐形移动节点时可使用 `create_emitter`。注意回调直接操作底层池，角度为弧度、速度为每帧归一化位移：

```python
import math


def spiral_emitter(pool, idx, x, y, lifetime):
    if int(lifetime * 60) % 4 == 0:
        pool.spawn_bullet(x, y, angle=lifetime * 6.28, speed=0.02, sprite_id="ball_mid1")


self.ctx.create_emitter(
    x=-0.5, y=0.8,
    angle=-60, speed=1.5,
    callback=spiral_emitter,
    max_lifetime=4.0,
)
```

---

## 6. 批量弹幕与高级行为

对于大规模变向、多阶段弹幕、追踪、穿屏、区域变换和弹转敌，应使用批量数组和共享行为 API，而不是为每颗子弹创建协程。

### 6.1 批量发射与弹群快照

`create_bullets_batch` 支持标量广播或按子弹区分的 NumPy 数组（如 `(N, 2)` 位置、`vector_accel`、每弹 `angles` / `speeds` / `sprite_idx`）：

```python
import numpy as np

indices = self.fire_circle(count=96, speed=1.5, tag=41)
group = self.ctx.capture_bullets(indices)  # 绑定槽位与出生代，槽位复用不会误操作新弹

snapshot = self.ctx.read_bullets(tag=41, fields=("pos", "vel", "speed"))
acc = np.column_stack((-snapshot["pos"][:, 1], snapshot["pos"][:, 0])) * 3.0
self.ctx.transform_bullets(snapshot.group, vector_accel=acc)
```

- 可用读取字段：`pos`、`vel`、`acc`、`angle`、`speed`、`speed_accel`、`sprite_idx`、`tag`、`time_scale`、`lifetime`、`render_angle`、`render_angle_offset`、`render_flip_y`、`collision_shape`、`hitbox_size`、`hitbox_angle`、`radius`。
- 传入固定 `group` 的数组长度必须与该组**原始 N 行**对齐；中途有子弹死亡不会导致行错位。可用 `snapshot.select(bool_mask)` 筛选子集。
- 动态按 `tag` 批量操作使用 `self.ctx.select_bullets(tag=...)` 或直接传 `tag=`。

### 6.2 多阶段行为、持续追踪与限次穿屏

```python
self.ctx.set_bullet_behavior(group, stages=[
    {"frames": 30, "speed": 1.5},
    {"frames": 20, "speed": 0.0},
    {"frames": 90, "homing": "player", "max_turn_rate": 45, "wrap_x": 2},
    {"aim": "player", "speed": 0.6, "accel": 1.2, "bullet_type": "grain_a", "color": "blue"},
])
```

- 每组最多 64 个阶段；只有最后一段可省略 `frames` 表示持续执行。传 `stages=[]` 可取消行为并恢复中性速度倍率，同时清理旧行为设置的有限反弹轴。
- `aim="player"` 在进入该阶段时瞄准一次；`homing="player"`（或固定 `(x, y)`）每帧按 `max_turn_rate`（度/秒）持续转向。
- `bounce_x` / `bounce_y` 与 `wrap_x` / `wrap_y` 在阶段表中表示剩余次数（`0` 表示取消），同轴正反弹与正穿屏互斥。
- 支持的每弹数组参数：`frames`、`speed`、`angle`、`angle_offset`、`accel`、`turn_rate`、`max_turn_rate`、`velocity_scale_end`（长度 N）及 `vector_accel`（`(N, 2)`）。
- `velocity_scale_end` 提供临时速度倍率插值，不覆盖基础速度，阶段结束或取消后自动恢复为 `1.0`。

### 6.3 出生期、区域冷却与连续规则

```python
# 出生期：移动但不碰撞，延迟进入行为，附加初速与越界宽限
self.ctx.configure_bullet_birth(
    group,
    warmup_frames=12,
    motion_factor=1.0,
    velocity_boost=0.4,
    boost_frames=16,
    offscreen_grace_frames=30,
)

# 区域变换 + 单弹冷却（支持 rect 和 circle）
region = {"kind": "rect", "x": 0.0, "y": 0.4, "width": 0.6, "height": 0.2, "angle": 30}
self.ctx.transform_bullets(
    tag=41,
    region=region,
    aim="player",
    speed=2.0,
    cooldown=30,
    cooldown_key="turning_field",
)

# 整组连续数值规则（每组每帧只调用一次）
def swirl(snap):
    p = snap["pos"]
    return {"vector_accel": np.column_stack((-p[:, 1], p[:, 0])) * 3.0}

handle = self.spawn_task(self.ctx.run_bullet_rule(swirl, group, fields=("pos",), frames=240))
```

### 6.4 终结分裂与子弹转敌人

```python
# 自然寿命结束时在每颗母弹原位分裂
self.ctx.split_bullets_on_end(51, count=8, speed=1.6, child_tag=52)
self.fire_circle(count=32, speed=1.0, max_lifetime=2.0, tag=51)

# 母弹终结时转为真正的 EnemyScript 实例
token = self.ctx.convert_bullets_on_end(71, MyFairy, reasons=("expired",))
try:
    self.fire_circle(count=16, tag=71, max_lifetime=1.0)
    await self.wait(180)
finally:
    self.ctx.cancel_bullet_conversion(token)
```

默认仅在 `expired`（自然寿命到期）时触发，Bomb、命中和清屏不触发；取消注册或调用 `clear_all_bullets()` 会同时清理尚未消费的转换队列。

---

## 7. 协程任务与稀疏事件

`StageScript`、`Wave`、`EnemyScript` 和 `SpellCard` 均支持结构化帧任务：

```python
# 并行执行多条协程
await self.parallel([
    self.boss.move_to(0.4, 0.6, duration=90),
    self.shoot_pattern(),
])

# 启动可等待/可取消的后台任务
handle = self.spawn_task(self.helper_loop())
await self.wait(60)
handle.cancel()   # 或 await handle.join()
```

- 每个对象最多拥有 256 个活跃后台任务；对象死亡、阶段结束、关卡取消或异常时都会自动取消子任务并执行 `finally`。
- 敌人可定义 `async def on_hit(self, damage)`（随敌人死亡自动取消）和 `async def on_death(self)`（自动托管到存活的 `StageContext`，死亡反应中如需继续派生后台任务，请调用 `self.ctx.spawn_task(...)`）。
- 稀疏事件通信：

```python
self.ctx.emit_event("phase.signal", {"step": 1}, owner="boss")
event = await self.ctx.wait_event("phase.signal", owner="boss", timeout=120)
```

- 需要在关卡中清理全部杂兵时调用 `self.ctx.clear_enemy_scripts()`（取消既有敌人，不触发击破掉落）。

---

## 8. 敌人移动、交互控制与激光

### 8.1 移动与边界

`EnemyScript` 和 `BossBase` 共用同一套移动 API（坐标为归一化世界单位，时长为帧，速度为单位/秒）：

```python
actor = self  # 符卡中使用 self.boss
actor.set_movement_bounds(-0.8, 0.8, -0.4, 0.7)
await actor.move_to(0.5, 0.4, duration=45, easing="ease_out_fast")
await actor.move_linear(-0.4, 0.0, duration=30)  # 相对位移
motion = self.spawn_task(actor.move_velocity(-90, 0.3, turn_rate=45))
await self.wait(120)
motion.cancel()
actor.clear_movement_bounds()
```

支持的 `easing`：`linear`、`smoothstep`、`ease_in`、`ease_out`（二次方）、`ease_in_fast`、`ease_out_fast`（四次方）。

### 8.2 交互开关与受弹区

```python
self.set_interaction(
    collidable=True,    # 能否与自机弹/玩家激光碰撞
    damageable=False,   # 受击是否扣血（False 时仍可触发 on_hit，适合假身）
    interactable=True,  # 能否被追踪和命中
    visible=True,       # 是否渲染
)
self.set_hitbox(Hitbox.box(0.18, 0.18))
self.set_secondary_hitbox(Hitbox.box(1.85, 0.16))  # 可选副受弹区（如幽幽子宽受弹带）
self.set_contact_hitbox(Hitbox.circle(0.05))        # 显式启用本体接触判定（默认关闭）
```

### 8.3 直线激光与曲线激光

```python
# 直线激光（支持动态移动段、独立警告/生效/碰撞窗口与沿线采样）
laser = self.ctx.create_laser(
    x=-0.8, y=0.6, angle=-25,
    l1=0.0, l2=0.5, l3=0.0, width=0.04,
    texture_id="laser1", color="blue",
)
laser.configure_motion(speed=0.6, start_offset=0.0, end_offset=0.1, length=0.5)
laser.configure_lifecycle(warning_frames=24, active_frames=120, fade_frames=16, hitbox_delay=24)
await self.wait(36)
points = laser.sample_points(0.25)
self.ctx.create_bullets_batch(positions=points, angles=-90, speeds=2.5, bullet_type="grain_a", color="blue")

# 曲线激光
bent = self.ctx.create_bent_laser(x=self.boss.x, y=self.boss.y, length=80, width=0.03, color="purple")
bent.update_head(nx, ny)
self.ctx.remove_laser(bent, off_time=15)
```

---

## 9. 视觉演出：粒子、动画、拖尾、背景与屏幕特效

### 9.1 非碰撞粒子池

粒子与敌弹完全隔离，不参与碰撞、擦弹或清弹，适合爆发闪光、星屑和三维天气投影：

```python
import numpy as np
from src.game.particle import ParticleEffect

angles = np.deg2rad(np.arange(32) * (360.0 / 32))
velocities = np.column_stack((np.cos(angles), np.sin(angles))) * 1.5
spark = ParticleEffect(
    ("grain_a16",),
    lifetime=30,
    scale=1.2, scale_end=0.2,
    alpha=1.0, alpha_end=0.0,
    angular_speed=120.0,
    blend="add",
    layer="front",  # back 或 front
)
group = self.ctx.emit_particles(
    spark, self.boss.x, self.boss.y,
    count=32,
    velocity=velocities,
    acceleration=-velocities * 3.0,
    color=(0.4, 0.6, 1.0, 1.0),
)
```

支持 `motion="linear"`（默认）、`motion="radial"`（收拢效果）和 `motion="manual"`（由内容脚本通过 `read_particles` / `transform_particles` 自行批量驱动位置，例如三维落樱投影）。

### 9.2 主动画与附属动画

```python
aura = self.boss.attach_animation("enemy_aura", layer="back", scale=2.2, color=(0.3, 0.5, 1.0, 0.65))
cast = self.boss.play_animation("enemy1_move_left", loop=False, speed=2.0)
await cast
if cast.finished:
    self.fire_circle(count=32, speed=2.0)
aura.remove()

# 视觉变换（不影响碰撞盒）
self.boss.set_visual(offset=(0.0, 0.02), rotation=15, scale=1.2, alpha=0.8, blend="alpha")

# 独立位置播放（如死亡特效）
self.ctx.play_animation("enemy_orb", enemy.x, enemy.y, loop=False, blend="add")
```

附属句柄支持 `pause()`、`resume()`、`stop()`、`detach()`（脱离主人冻结在世界坐标继续播放至结束）与 `remove()`。

### 9.3 连续纹理拖尾

适合幽灵长尾等连续带状视觉效果：

```python
trail = self.ctx.attach_trail(
    self,
    "my_ghost_sprite",
    history_frames=48,
    node_step=1,
    width=32 / 192,
    blend="add",
    hide_owner=True,
)
trail.cancel()
```

### 9.4 3D 背景场景、文字叠加与屏幕特效

```python
from src.game.background import SceneQuad, ScreenLayer
from src.core.project_context import get_project_context

tex = str(get_project_context().resolve("res://assets/images/background/lake/lake_3.png"))
self.ctx.background.set_scene([
    SceneQuad(tex, ((-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)), group="clouds"),
])
self.ctx.background.set_camera(eye=(0, 0, 5), at=(0, 0, 0), fovy=0.8, z_near=0.1, z_far=100)
self.ctx.background.set_fog(color=(0.2, 0.1, 0.3, 1.0), start=4, end=10, enabled=True)
self.ctx.background.set_layers([ScreenLayer(tex, alpha=0.4, uv_velocity=(0, 0.001), blend="add")])
self.ctx.background.group_offsets["clouds"] = (dx, dy, dz)  # 更新平移 uniform，不重传顶点

# 文字与标题（默认使用 384×448 游戏区左上角像素坐标；layer="hud" 使用整窗坐标）
title = self.ctx.show_title("第一面", "示例副标题", duration_frames=240)
label = self.ctx.show_text("剩余 256 发", x=16, y=24, size=18, key="status")
label.update(text="剩余 192 发")
label.hide(fade_out_frames=30)

# 屏幕闪光与游戏区震动（只震动游戏区域，不影响 HUD）
self.ctx.flash_screen((1.0, 1.0, 1.0, 0.6), frames=20)
shake = self.ctx.shake_screen(frames=80, amplitude=8, seed=1337)
```

`SceneQuad` 还支持 `billboard_center`、`depth_test`、`depth_write` 与 `fog_mode="depth" | "distance_alpha"`。

### 9.5 关卡加载期预热声明

在 `StageScript` 中重写 `presentation_resources()` 可以提前声明本关已知的文字、BGM 提示、粒子效果和拖尾顶点预算，避免首次出场时触发临时资源准备或文字栅格化：

```python
def presentation_resources(self):
    return {
        "spell_names": ("火符「Example」",),
        "texts": ({"text": "关底", "size": 22, "stroke_width": 1},),
        "bgm_names": ("stage_bgm", "boss_bgm"),
        "particle_effects": (self.weather_effect,),
        "trail_vertices": 16 * 47 * 6,
    }
```

---

## 10. 玩法规则、时停慢速、受击契约与音频

### 10.1 跨关状态（`RunState`）与分系统慢速 / 时停

`StageManager` 持有跨关共享的 `RunState`（包含 `difficulty`、`player_shot`、`rank`、`subrank`、`bomb_handler` 等），脚本可通过 `self.ctx.difficulty`、`self.ctx.player_shot`、`self.ctx.rank` 和 `self.ctx.run_state` 访问。

```python
# 分系统时停（默认停 player / bullets / lasers / background / effects / boss_timer，不停脚本与道具）
with self.ctx.stop_time():
    await self.wait(60)

# 全系统或局部慢动作（支持 0~1 倍率）
with self.ctx.slow_motion(1 / 3):
    await self.wait(30)          # 按仿真时间等待（对应 90 个控制帧）
    await self.wait_control(10)  # 按真实控制帧等待（不受慢速或 0 倍率影响）
```

### 10.2 受击结果与救援窗口（Deathbomb / 结界）

`PlayerBase.receive_hit()` 返回明确的 `HitResult.status`（`ignored` / `handled` / `pending` / `rescued` / `miss`），避免已消耗的命中被误判为 miss。关卡或自机脚本可以挂载自定义受击规则：

```python
from src.game.player.hit import HitDecision


def hit_rule(player, hit):
    if border_active:
        self.ctx.clear_all_bullets(to_items=True)
        return HitDecision.handled(invulnerability_frames=60, fail_capture=True)
    return HitDecision.pending(window_frames=8, fail_capture=True)


self.ctx.set_player_hit_rule(hit_rule)
```

`fail_capture=True` 会独立标记符卡捕获失败而不误增 miss 计数。

### 10.3 自机激光、旋转矩形碰撞与命中爆炸

```python
from src.core.collision_shapes import Hitbox
from src.game.player.player_bullet import ImpactArea

# 持续锚定激光
beam = self.fire_laser(angle=90, length=2.0, width=0.04, damage=12, hit_interval=6, sprite_id="beam")
beam.cancel()

# 命中后原地展开爆炸的导弹
self.fire(
    angle=90, speed=2.0, damage=20, sprite_id="missile",
    hitbox=Hitbox.box(0.025, 0.05),
    impact=ImpactArea(
        Hitbox.circle(0.04),
        damage=5,
        frames=30,
        hit_interval=6,
        end_hitbox=Hitbox.circle(0.18),
        sprite_id="explosion",
    ),
)
```

### 10.4 道具收集与计分规则

```python
from src.game.item import ItemType


def collect_rule(stats, item):
    if item.item_type == ItemType.POINT:
        stats.add_score(100000)
        return True
    return False  # 返回 False 交回默认收集规则


self.ctx.set_item_collection_rule(collect_rule)
self.ctx.spawn_item(0.0, 0.5, ItemType.POWER_LARGE, speed=0.6, angle=90, tag=1)
self.ctx.spawn_drop(self.boss.x, self.boss.y, type="power_small")
```

`GameStats` 同时开放 `on_score`、`on_graze`、`on_miss`、`on_continue` 等稀疏回调入口。

### 10.5 BGM 前奏与样本级无缝循环

```python
self.ctx.play_bgm(
    "stage_track",
    loops=-1,                    # -1 无限循环，0 不循环，正数为额外循环次数
    start=0.0,
    fade_ms=150,
    loop_start_frame=44100 * 8,  # 源文件 PCM 帧索引
    loop_end_frame=44100 * 120,
)
self.ctx.seek_bgm(10.0)
pos = self.ctx.get_bgm_position()
```

---

## 11. 可用弹型与颜色别名

`bullet_type` 和 `color` 使用 `assets/bullet_aliases.json` 中定义的别名，不要直接传入内部图集精灵 ID（如 `ball_mid1`）。

| 弹型别名 | 外观 | 颜色支持 |
| --- | --- | --- |
| `ball_s` / `ball_m` / `ball_l` | 小 / 中 / 大圆弹 | 16 色 |
| `ball_light` | 光球弹 | 16 色 |
| `grain_a` / `grain_b` / `grain_c` | 米粒弹 A / B / C | 16 色 |
| `arrow_s` / `arrow_m` | 小 / 中箭头弹 | 16 色 |
| `arrow_l` | 大箭头弹 | 15 色（含 `gray`、`pink`，无 `darkyellow` / `darkorange` / `black`） |
| `knife` | 刀弹 | 16 色 |
| `star_s` / `star_l` | 小 / 大星弹 | 16 色 |
| `star_m` / `needle` / `scale` / `fire` | 中星 / 针弹 / 鳞弹 / 炎弹 | 17 色（16 色 + `pink`） |
| `square` / `butterfly` / `ellipse` / `kite` / `heart` | 方块 / 蝴蝶 / 椭圆 / 风筝 / 心形 | 16 色 |
| `gun` / `mildew` / `silence` | 枪弹 / 细菌弹 / 轮廓弹 | 16 色 |
| `scale_s` / `scale_m` / `rice_s` | 兼容别名 | 10 色 |

常用 16 色：`red`、`darkred`、`purple`、`darkpurple`、`blue`、`darkblue`、`cyan`、`darkcyan`、`green`、`darkgreen`、`yellow`、`darkyellow`、`orange`、`darkorange`、`white`、`black`。

---

## 12. 常见问题

- **`await` 与 `parallel` 怎么选？** 顺序步骤直接用 `await`；需要一边移动一边发弹时优先用 `await self.parallel([...])` 或 `self.spawn_task(...)`。
- **为什么子弹在发出的那一帧没立刻移动？** 引擎按「弹幕池更新 → 关卡脚本 → 碰撞检测」顺序推进，当前帧新发射的子弹从下一帧开始运动与碰撞，保证发射顺序不会受池槽编号影响。
- **更多完整可运行范例在哪里？**
  - 标准手写关卡：`game_content/stages/stage1/`
  - 高级运行时 API 示范：`game_content/examples/`（`th06_patterns.py`、`th06_controls.py`、`th06_rules.py`、`th06_particles.py`、`th06_animations.py`、`th07_api.py`）
