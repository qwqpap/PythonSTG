# pystg 弹幕脚本开发指南 (v2)

> 本文档以**当前仓库实际可运行的 API** 为准。  
> 最近更新：2026-04-12，弹幕系统 v2 大改造后。

---

## 目录

1. [当前工作流](#1-当前工作流)
2. [推荐目录结构](#2-推荐目录结构)
3. [快速开始](#3-快速开始)
4. [四层分工](#4-四层分工)
5. [StageScript：整面流程](#5-stagescript整面流程)
6. [Wave：波次编排](#6-wave波次编排)
7. [EnemyScript：小怪行为](#7-enemyscript小怪行为)
8. [SpellCard / NonSpell：Boss 攻击](#8-spellcard--nonspellboss-攻击)
9. [BossDef：Boss 阶段组织](#9-bossdef-boss-阶段组织)
10. [弹幕 API 完整参考（v2）](#10-弹幕-api-完整参考v2)
11. [激光 API](#11-激光-api)
12. [道具 / 得分 / 玩家访问](#12-道具--得分--玩家访问)
13. [v2 新机制详解](#13-v2-新机制详解)
14. [高级模式示例](#14-高级模式示例)
15. [坐标与角度](#15-坐标与角度)
16. [可用弹型与颜色](#16-可用弹型与颜色)
17. [常见问题](#17-常见问题)

---

## 1. 当前工作流

当前仓库使用的是**程序化关卡脚本**流程：

- 整面关卡：继承 `StageScript`
- 道中一段：继承 `Wave`
- 单个小怪行为：继承 `EnemyScript`
- Boss 单张攻击：继承 `SpellCard` 或 `NonSpell`
- Boss 阶段列表：在 `StageScript` 里用 `BossDef` + `nonspell()` / `spellcard()` 组织

---

## 2. 推荐目录结构

```text
game_content/stages/stage1/
├── __init__.py
├── stage_script.py          # 整面流程
├── waves/                   # 道中波次
│   └── *.py
├── enemies/                 # 可复用小怪
│   └── *.py
├── spellcards/              # Boss 攻击
│   └── *.py
├── bosses/                  # Boss 定义（可选）
├── dialogue/                # 对话
└── audio/                   # 关卡私有音频
```

---

## 3. 快速开始

### 3.1 新建一张符卡

```python
from src.game.stage.spellcard import SpellCard


class MySpell(SpellCard):
    name = "火符「Example」"
    hp = 1000
    time_limit = 45
    bonus = 500000

    async def setup(self):
        await self.boss.move_to(0, 0.5, duration=30)

    async def run(self):
        angle = 0
        while True:
            self.fire_circle(
                count=12,
                speed=2.0,
                start_angle=angle,
                bullet_type="ball_m",
                color="red",
            )
            angle += 10
            await self.wait(15)


spellcard = MySpell
```

### 3.2 把它挂到 Boss 上

```python
from src.game.stage.stage_base import StageScript, BossDef
from src.game.stage.boss_base import nonspell, spellcard
from game_content.stages.stage1.spellcards.my_spell import MySpell

class Stage1(StageScript):
    boss = BossDef(
        id="boss1",
        name="Boss Name",
        texture="enemy_boss",
        phases=[
            nonspell(NonSpell1, hp=800, time=30, bonus=100000),
            spellcard(MySpell, "火符「Example」", hp=1000, time=45),
        ],
    )

    async def run(self):
        await self.wait(60)
        await self.run_boss(self.boss)
```

---

## 4. 四层分工

| 层 | 基类 | 职责 |
|---|---|---|
| **StageScript** | `StageScript` | 整面时间线：等待、波次、midboss、对话、boss |
| **Wave** | `Wave` | 一段时间内刷什么敌人、间隔多久 |
| **EnemyScript** | `EnemyScript` | 单个小怪从出生到退场的完整行为 |
| **SpellCard / NonSpell** | `SpellCard` / `NonSpell` | Boss 某一段攻击 |

---

## 5. StageScript：整面流程

```python
class Stage1(StageScript):
    id = "stage1"
    name = "Stage 1"
    title = "标题"
    bgm = "00.wav"
    boss_bgm = "01.wav"
    background = "stage1_bg"

    boss = BossDef(...)

    async def run(self):
        await self.run_wave(OpeningWave)
        await self.wait(60)
        await self.run_boss(self.midboss, is_midboss=True)
        await self.play_dialogue([...])
        await self.run_boss(self.boss)
```

常用 API：`wait()`, `wait_seconds()`, `run_wave()`, `run_boss()`, `play_dialogue()`, `play_bgm()`.

---

## 6. Wave：波次编排

```python
class FairyWave(Wave):
    async def run(self):
        for i in range(5):
            self.spawn_enemy_class(SideFlyFairy, x=-0.8 + i * 0.2, y=1.0)
            await self.wait(20)
        await self.wait(180)
```

---

## 7. EnemyScript：小怪行为

```python
class SideFlyFairy(EnemyScript):
    hp = 30
    sprite = "enemy_fairy"

    async def run(self):
        await self.move_to(self.x, 0.5, duration=40)
        for _ in range(3):
            self.fire_at_player(speed=2.2, bullet_type="ball_s", color="red")
            await self.wait(20)
        await self.move_linear(0.0, -0.8, duration=80)
```

---

## 8. SpellCard / NonSpell：Boss 攻击

### 基本生命周期

```
setup() → run() → (被击败 或 超时) → on_defeated() / on_timeout()
```

### 并行动作（边移动边发弹）

```python
async def run(self):
    while True:
        move_coro = self.boss.move_to(0.4, 0.6, duration=90)
        for _ in range(90):
            try: next(move_coro)
            except StopIteration: pass

            if self.time % 6 == 0:
                self.fire_at_player(speed=2.5, color="red")
            yield
```

### 符卡内常用属性

- `self.time` — 当前帧数
- `self.time_seconds` — 当前时间（秒）
- `self.time_remaining` — 剩余时间（秒）
- `self.boss` — Boss 对象（可访问 `.x`, `.y`）
- `self.ctx` — StageContext（底层 API）

### 生命周期回调

```python
class MySpell(SpellCard):
    async def setup(self):
        """符卡开始前调用，常用于布阵或 Boss 移动到位"""
        await self.boss.move_to(0, 0.5, duration=30)

    async def run(self):
        """主弹幕循环"""
        ...

    def on_defeated(self):
        """玩家击破符卡时调用，可用于触发结算特效或散花弹"""
        self.play_se("cardget")

    def on_timeout(self):
        """符卡超时未被击破时调用"""
        self.clear_bullets()
```

`on_defeated` / `on_timeout` 默认是空实现，重写时不需要 `async`。
若要在结算时发送弹幕或道具，直接在里面调用 `self.fire(...)` / `self.ctx.spawn_drop(...)` 即可。

> **注意**：`wait_until(condition)` 仅在 SpellCard 上可用；
> Wave / EnemyScript 内请用 `await self.wait(N)` 配合手动条件判断实现等价效果。

---

## 9. BossDef：Boss 阶段组织

```python
boss = BossDef(
    id="rumia_boss",
    name="ルーミア",
    texture="enemy_rumia",
    phases=[
        nonspell(NonSpell1, hp=800, time=30, bonus=100000),
        spellcard(MoonlightRay, "月符「Moonlight Ray」", hp=1200, time=60),
        spellcard(NightBird, "夜符「Night Bird」", hp=1500, time=60, bonus=1500000),
    ],
)
```

---

## 10. 弹幕 API 完整参考（v2）

以下所有方法在 `SpellCard`、`NonSpell`、`EnemyScript`、`Wave` 中均可使用。

### 10.1 self.fire(...)

发射单发子弹。

```python
self.fire(
    x=0.0, y=0.5,         # 位置（默认为 Boss/Enemy 位置）
    angle=-90,             # 角度（度）
    speed=2.0,             # 速度

    # 弹型
    bullet_type="ball_m",  # 弹型别名
    color="red",           # 颜色别名

    # ===== v2 新参数 =====
    tag=0,                 # 分组标签（整数，用于按组消弹/时停等）
    friction=0.0,          # 摩擦/阻尼系数（>0 时子弹逐渐减速）
    time_scale=1.0,        # 时间缩放（0=冻结, 0.5=半速, 1.0=正常, 2.0=加速）
    bounce_x=False,        # 碰到左右边界反弹
    bounce_y=False,        # 碰到上下边界反弹
    spin=0.0,              # 贴图自转角速度（度/秒）
    render_angle=None,     # 初始贴图朝向（度，None=跟随运动方向）
    curve_type=0,          # 内置数学曲线（见下方常量表）
    curve_params=None,     # 曲线参数元组 (amplitude, frequency, phase, base_value)
)
```

### 10.2 self.fire_circle(...)

圆形均匀扩散。

```python
self.fire_circle(
    count=36,              # 弹数
    speed=2.0,
    start_angle=0,         # 起始角度
    bullet_type="ball_m",
    color="blue",
    # 也支持所有 v2 参数：tag, friction, bounce_x, ...
)
```

### 10.3 self.fire_arc(...)

扇形弹幕。

```python
self.fire_arc(
    count=7,
    speed=2.5,
    center_angle=-90,      # 扇形中心角度
    arc_angle=60,          # 扇形张角
    bullet_type="rice",
    color="green",
)
```

### 10.4 self.fire_at_player(...)

自机狙。

```python
self.fire_at_player(
    speed=3.0,
    offset_angle=0,        # 偏移角度（度）
    bullet_type="arrow_m",
    color="red",
)
```

### 10.5 self.fire_polar(...) / self.fire_orbit(...)

极坐标运动子弹（围绕中心公转/螺旋）。

```python
self.fire_polar(
    orbit_radius=0.15,         # 初始半径
    theta=0,                   # 初始角度（度）
    radial_speed=0.05,         # 半径变化速率
    angular_velocity=120,      # 角速度（度/秒）
    bullet_type="ball_s",
    color="blue",
    center=None,               # 默认为 Boss；可传 (x,y) / 对象 / callable
    render_mode="velocity",    # velocity / radial / inward / fixed
    angle_offset=0,            # 贴图朝向偏移（度）
    collision_radius=0.0,      # 碰撞半径
)
```

### 10.6 消弹

```python
self.clear_bullets()                      # 清除本符卡/本敌人创建的子弹
self.clear_bullets(to_items=True)         # 转为道具
self.ctx.clear_all_bullets()              # 清屏
self.ctx.clear_bullets_by_tag(1)          # 按标签消弹
self.ctx.bullets_by_tag_to_item(1)        # 按标签转道具
```

### 10.7 时间缩放（时停 / 慢动作）

```python
self.ctx.set_time_scale(0.0)              # 全部冻结
self.ctx.set_time_scale(0.0, tag=1)       # 只冻结 tag=1 的子弹
self.ctx.set_time_scale(1.0)              # 恢复正常
self.ctx.set_time_scale(0.3, tag=2)       # tag=2 减速到 0.3 倍
```

### 10.8 发射器节点（Emitter）

不渲染、不碰撞的隐形移动节点，一边运动一边发弹。

```python
def emitter_logic(pool, idx, x, y, lifetime):
    """每帧回调"""
    if int(lifetime * 60) % 6 == 0:
        pool.spawn_bullet(x, y, angle=-1.57, speed=0.03, sprite_id="ball_mid1")

self.ctx.create_emitter(
    x=0.0, y=0.8,
    angle=-90, speed=1.0,          # 发射器从上往下飞
    callback=emitter_logic,
    tag=10,                        # 可以给发射器也打标签
    max_lifetime=3.0,              # 3 秒后自动消失
    friction=0.5,                  # 发射器可以减速
)
```

### 10.9 辅助方法

```python
self.angle_to_player()            # 返回到自机的角度（度）
self.play_se("kira")              # 播放音效
player = self.ctx.get_player()    # 获取玩家代理 (.x, .y)
```

---

## 11. 激光 API

激光由 `LaserPool` 统一管理，通过 `self.ctx.create_laser()` / `self.ctx.create_bent_laser()` 创建。两种类型：

| 类型 | 说明 |
|---|---|
| 直线激光 | 三段式（头/身/尾），有展开→持续→收缩动画 |
| 曲线激光 | 沿路径弯曲，每帧通过 `update_head(x, y)` 推进头部 |

### 11.1 直线激光

```python
laser = self.ctx.create_laser(
    x=0.0, y=0.6,             # 起点（归一化坐标）
    angle=-90,                 # 角度（度）
    l1=0.05,                   # 头部长度
    l2=1.5,                    # 身体长度
    l3=0.05,                   # 尾部长度
    width=0.04,                # 宽度
    texture_id="laser1",       # 纹理 ID（laser1 ~ laser4）
    color="red",               # 颜色名 或 1~16 索引
    on_time=30,                # 展开时间（帧）
    node=0.0,                  # 起点装饰大小
    head=0.0,                  # 终点装饰大小
)

# 一段时间后关闭（淡出 30 帧）
await self.wait(180)
self.ctx.remove_laser(laser, off_time=30)
```

### 11.2 曲线激光

```python
laser = self.ctx.create_bent_laser(
    x=self.boss.x, y=self.boss.y,
    length=80,                 # 历史采样点上限（决定可见尾巴长度）
    width=0.03,
    color="blue",
    on_time=20,
    sample_rate=4,             # 每多少帧记录一次头部位置
)

# 后续每帧驱动头部，激光会自动连成曲线
import math
for t in range(180):
    nx = self.boss.x + 0.3 * math.sin(t * 0.1)
    ny = self.boss.y - 0.005 * t
    laser.update_head(nx, ny)
    await self.wait(1)

self.ctx.remove_laser(laser, off_time=15)
```

### 11.3 清屏

```python
self.ctx.clear_all_lasers()      # 一次性移除所有激光
```

### 11.4 颜色与纹理

- `color` 接受 16 个索引（1~16）或颜色名 `red / blue / green / purple / orange / darkblue / white / yellow / cyan / pink / ...`
- `texture_id` 对应 `assets/images/laser/` 下的纹理（默认 `laser1`，另有 `laser2/3/4`）

---

## 12. 道具 / 得分 / 玩家访问

### 12.1 手动掉落道具

```python
# 在 (x, y) 处生成一个掉落物
self.ctx.spawn_drop(self.boss.x, self.boss.y, type="power_small")
```

道具类型由 `ItemPool` 决定，常见值：`power_small`, `power_big`, `point`, `life`, `bomb`, `full_power`。

### 12.2 直接加分

```python
self.ctx.add_score(100000)     # 普通用法：杂兵击破奖励
```

> 设计建议：常规掉落由敌人击破自动触发；`spawn_drop` / `add_score` 用于符卡结算特效或自定义事件奖励。

### 12.3 访问玩家与敌人

```python
player = self.ctx.get_player()      # 只读代理：player.x, player.y
enemies = self.ctx.get_enemies()    # 当前活跃敌人列表
```

```python
# 自机狙的便捷写法（已封装）
self.fire_at_player(speed=2.5, color="red")

# 等价于
import math
angle = self.angle_to_player()
self.fire(angle=angle, speed=2.5, color="red")
```

### 12.4 完整 ctx 公共方法清单

`StageContext` 上的所有公共方法（写复杂逻辑时可能用到）：

| 类别 | 方法 |
|------|------|
| 弹幕 | `create_bullet`, `create_polar_bullet`, `create_orbit_bullet`, `create_emitter` |
| 消弹 | `remove_bullet(s)`, `bullet(s)_to_item(s)`, `clear_all_bullets`, `clear_bullets_by_tag`, `bullets_by_tag_to_item` |
| 时停 | `set_time_scale(scale, tag=None)` |
| 激光 | `create_laser`, `create_bent_laser`, `remove_laser`, `clear_all_lasers` |
| 道具 / 分数 | `spawn_drop`, `add_score` |
| 玩家 / 敌人 | `get_player`, `get_enemies`, `add_enemy_script`, `get_enemy_scripts` |
| 音频 | `play_se`, `play_danmaku_se`, `play_bgm`, `stop_bgm`, `pause_bgm`, `unpause_bgm` |
| 背景 | `set_background(name)` |

---

## 13. v2 新机制详解

### 11.1 摩擦力 / 阻尼 (friction)

```python
self.fire(angle=-90, speed=5.0, friction=2.0, bullet_type="ball_m", color="red")
```

效果：子弹每帧速度乘以 `(1 - friction * dt)`，逐渐减速直到停止。

| friction 值 | 效果 |
|---|---|
| 0 | 无摩擦（默认行为） |
| 1.0 | 约 1 秒减速到接近 0 |
| 3.0 | 极快减速（急停弹） |
| 0.3 | 缓慢减速 |

**用途**：减速 → 停顿 → 配合 `on_death` 做散花、制造"粘滞感"弹幕。

### 11.2 反弹 (bounce_x / bounce_y)

```python
self.fire(angle=30, speed=2.5, bounce_x=True, bounce_y=True,
          bullet_type="ball_m", color="green")
```

子弹碰到 `x ∈ [-1, 1]` 或 `y ∈ [-1, 1]` 的边界时速度分量取反。  
反弹弹不会因为飞出屏幕而死亡（普通弹在 ±1.5 时自动消亡）。

**用途**：弹球弹幕、墙壁反射。

### 11.3 自转 (spin / render_angle)

```python
# 弹边飞边自转
self.fire(angle=-90, speed=2.0, spin=360, bullet_type="star_m", color="yellow")

# 固定贴图朝上，不跟运动方向
self.fire(angle=-90, speed=2.0, render_angle=0, bullet_type="knife", color="red")
```

- `spin=N`：贴图每秒转 N 度（运动方向不变）
- `render_angle=X`：初始贴图朝向为 X 度（且不再锁定到运动方向）

**用途**：旋转星弹、固定朝向刀弹。

### 11.4 标签 (tag) + 按组操作

```python
# 发弹时打标签
self.fire(angle=-90, speed=2.0, tag=1, color="blue")
self.fire(angle=-90, speed=2.0, tag=2, color="red")

# 后续操作
self.ctx.clear_bullets_by_tag(1)         # 只消蓝弹
self.ctx.bullets_by_tag_to_item(2)       # 红弹变道具
self.ctx.set_time_scale(0.0, tag=1)      # 冻结蓝弹
```

**用途**：解谜弹幕（打中开关消特定弹）、分色管理、选择性时停。

### 11.5 时间缩放 (time_scale)

每颗子弹拥有独立的 time_scale 乘数，影响：
- 位置更新速度
- 生命周期推进
- 摩擦力衰减
- 曲线演算
- 自转速度

```python
# 发射一颗慢动作弹
self.fire(angle=-90, speed=3.0, time_scale=0.3, bullet_type="ball_l", color="white")

# 全局冻结（咲夜时停）
self.ctx.set_time_scale(0.0)
await self.wait(120)
self.ctx.set_time_scale(1.0)
```

### 11.6 内置数学曲线 (curve_type + curve_params)

在 JIT 内核内执行的高性能参数化运动。

#### 常量导入

```python
from src.game.bullet import (
    CURVE_NONE, CURVE_SIN_SPEED, CURVE_SIN_ANGLE,
    CURVE_COS_SPEED, CURVE_LINEAR_SPEED,
)
```

#### curve_params = (amplitude, frequency, phase, base_value)

| curve_type | 效果公式 |
|---|---|
| `CURVE_SIN_SPEED` (1) | `speed = base + amp * sin(freq * t + phase)` |
| `CURVE_SIN_ANGLE` (2) | `angle += amp * sin(freq * t + phase) * dt` |
| `CURVE_COS_SPEED` (3) | `speed = base + amp * cos(freq * t + phase)` |
| `CURVE_LINEAR_SPEED` (4) | `speed = base + amp * t` |

```python
from src.game.bullet import CURVE_SIN_SPEED

# 波动速度弹：速度在 1.0 ~ 3.0 之间正弦波动
self.fire(
    angle=-90, speed=2.0,
    bullet_type="grain_a", color="cyan",
    curve_type=CURVE_SIN_SPEED,
    curve_params=(1.0, 3.14, 0.0, 2.0),  # amp=1, freq=π, phase=0, base=2
)
```

```python
from src.game.bullet import CURVE_SIN_ANGLE

# 蛇行弹：运动角度正弦摆动
self.fire(
    angle=-90, speed=2.0,
    bullet_type="kite", color="green",
    curve_type=CURVE_SIN_ANGLE,
    curve_params=(2.0, 5.0, 0.0, 0.0),  # amp=2 rad/s, freq=5
)
```

### 11.7 发射器节点 (Emitter)

隐形、不碰撞的移动节点，每帧执行回调函数发射子弹。

```python
def spiral_emitter(pool, idx, x, y, lifetime):
    """发射器回调：一边飞一边旋转发弹"""
    frame = int(lifetime * 60)
    if frame % 4 == 0:
        angle = lifetime * 6.28  # 旋转
        pool.spawn_bullet(x, y, angle=angle, speed=0.02, sprite_id="ball_mid1")

self.ctx.create_emitter(
    x=-0.5, y=0.8,
    angle=-60, speed=1.5,
    callback=spiral_emitter,
    max_lifetime=4.0,
)
```

> **注意**：Emitter 回调中的 `pool.spawn_bullet()` 是底层 API，angle 用弧度，speed 用归一化/帧。  
> 如果想用度和每秒单位，需要自行转换：`angle=math.radians(deg)`, `speed=spd/60`.

---

## 14. 高级模式示例

### 12.1 急停→散花弹

```python
import math

async def run(self):
    while True:
        for i in range(12):
            angle = i * 30
            # 大弹急停
            self.fire(
                angle=angle, speed=4.0,
                friction=3.0,              # 快速减速
                bullet_type="ball_l", color="red",
                tag=100,
            )
        await self.wait(40)

        # 检查急停弹的生命周期，在停住后爆散 —— 用 on_death 回调更好
        # （这里用清弹 + 重新发射的简化写法）
        self.ctx.clear_bullets_by_tag(100)
        # 替换为散花
        bx, by = self.boss.x, self.boss.y
        for i in range(36):
            self.fire(angle=i * 10, speed=2.0,
                      bullet_type="ball_s", color="blue")
        await self.wait(60)
```

### 12.2 弹球弹幕

```python
async def run(self):
    import random
    while True:
        for _ in range(8):
            a = random.uniform(0, 360)
            self.fire(
                angle=a, speed=2.5,
                bounce_x=True, bounce_y=True,
                bullet_type="ball_m", color="green",
            )
        await self.wait(30)
```

### 12.3 咲夜时停

```python
async def run(self):
    while True:
        # 发一波高速弹
        for i in range(24):
            self.fire(angle=i * 15, speed=4.0,
                      bullet_type="knife", color="blue",
                      tag=1)
        await self.wait(30)

        # 时停
        self.ctx.set_time_scale(0.0, tag=1)
        await self.wait(60)

        # 解冻 + 追加
        self.ctx.set_time_scale(1.0, tag=1)
        await self.wait(60)
```

### 12.4 旋转星弹

```python
async def run(self):
    angle = 0
    while True:
        self.fire_circle(
            count=8, speed=1.5,
            start_angle=angle,
            bullet_type="star_l", color="yellow",
            spin=720,  # 每秒自转 2 圈
        )
        angle += 15
        await self.wait(10)
```

### 12.5 流星雨发射器（魔理沙风格）

```python
import math, random

def meteor_emitter(pool, idx, x, y, lifetime):
    frame = int(lifetime * 60)
    if frame % 3 == 0:
        a = -math.pi/2 + random.uniform(-0.3, 0.3)
        pool.spawn_bullet(x, y, angle=a, speed=0.04, sprite_id="star_small3")

async def run(self):
    while True:
        for i in range(5):
            self.ctx.create_emitter(
                x=-0.8 + i * 0.4, y=1.0,
                angle=-90, speed=0.5,
                callback=meteor_emitter,
                max_lifetime=3.0,
            )
        await self.wait(180)
```

### 12.6 正弦蛇行弹

```python
from src.game.bullet import CURVE_SIN_ANGLE

async def run(self):
    while True:
        for i in range(12):
            self.fire(
                angle=-90, speed=2.0,
                bullet_type="grain_a", color="cyan",
                curve_type=CURVE_SIN_ANGLE,
                curve_params=(3.0, 4.0, i * 0.5, 0.0),  # 每条蛇相位偏移
            )
        await self.wait(20)
```

### 12.7 极坐标莲花弹（扩散→收缩→散开）

```python
async def run(self):
    while True:
        for i in range(12):
            self.fire_polar(
                orbit_radius=0.05,
                theta=i * 30,
                radial_speed=0.15,
                angular_velocity=60,
                bullet_type="kite", color="purple",
            )
        await self.wait(120)
```

---

## 15. 坐标与角度

坐标系是归一化坐标：

- `x ≈ -1.0 ~ 1.0`，`y ≈ -1.0 ~ 1.0`
- `(0, 0)` 为屏幕中心

角度（所有脚本层 API 统一用度）：

- `0°` → 向右
- `90°` → 向上
- `-90°` → 向下
- `180°` / `-180°` → 向左

---

## 16. 可用弹型与颜色

### 弹型别名

| 别名 | 说明 |
|---|---|
| `ball_s` | 小弹 |
| `ball_m` | 中弹 |
| `ball_l` | 大弹 |
| `ball_light` | 光晕弹 / 发光玉 |
| `grain_a` / `b` / `c` | 米弹 / 谷物弹 |
| `kite` | 鳞弹 / 菱形弹 |
| `arrow_s` / `m` / `l` | 箭头弹 / 札弹 |
| `knife` | 刀弹 |
| `star_s` | 小星弹 |
| `star_l` | 大星弹 |
| `gun` | 直弹 / 子弹 |
| `ellipse` | 椭圆弹 |
| `square` | 方弹 |
| `butterfly` | 蝶星弹 |
| `heart` | 心形弹 |
| `mildew` | 霉菌弹 / 细菌形弹 |
| `silence` | 寂静弹 / 轮廓弹 |

### 颜色别名

`red`, `blue`, `green`, `yellow`, `purple`, `white`, `darkblue`, `orange`, `cyan`, `pink`

实际映射由 `assets/bullet_aliases.json` 定义。

---

## 17. 常见问题

### Q: `await` 和 `yield` 用哪个？

默认用 `await`。只有同一帧并行推进多个动作时用 `yield`。

### Q: 怎么清掉自己发过的弹？

```python
self.clear_bullets()
self.clear_bullets(to_items=True)
```

### Q: 怎么用 tag 做解谜弹幕？

```python
self.fire(..., tag=1, color="blue")
self.fire(..., tag=2, color="red")

# 玩家达成条件后
self.ctx.bullets_by_tag_to_item(1)    # 蓝弹变道具
self.ctx.clear_bullets_by_tag(2)      # 红弹消除
```

### Q: 怎么做时停？

```python
self.ctx.set_time_scale(0.0)          # 全局冻结
self.ctx.set_time_scale(0.0, tag=1)   # 只冻 tag=1
self.ctx.set_time_scale(1.0)          # 恢复
```

### Q: Emitter 回调里怎么用高层 API？

Emitter 回调直接操作底层 pool，参数用弧度和归一化速度。如果想用友好单位：

```python
import math
pool.spawn_bullet(x, y,
    angle=math.radians(-90),     # 角度转弧度
    speed=2.5 / 60.0,           # 每秒速度转每帧
    sprite_id="ball_mid1",
)
```

### Q: curve_params 四个参数是什么含义？

`(amplitude, frequency, phase, base_value)`

- `amplitude`：振幅
- `frequency`：角频率（弧度/秒）
- `phase`：初始相位
- `base_value`：基础值

例如 `(1.0, 6.28, 0.0, 2.0)` 表示"速度 = 2.0 + 1.0 * sin(2π * t)"，即速度在 1.0~3.0 之间每秒一个周期。

### Q: 如何让子弹出生后中途变色/变型？

直接修改底层数据：

```python
idx = self.fire(...)
self.ctx.bullet_pool.data['sprite_id'][idx] = "ball_mid5"  # 旧版池
# 或
self.ctx.bullet_pool.data['sprite_idx'][idx] = new_idx     # 优化版池
```

### Q: 我新增了 Stage，怎么切过去？

在 `main.py` 里改为加载你的新 Stage 类。

---

## API 速查表

| 方法 | 说明 | 示例 |
|---|---|---|
| `self.fire(...)` | 单发 | `self.fire(angle=-90, speed=2)` |
| `self.fire_circle(...)` | 圆形 | `self.fire_circle(count=24, speed=2)` |
| `self.fire_arc(...)` | 扇形 | `self.fire_arc(count=5, arc_angle=60)` |
| `self.fire_at_player(...)` | 自机狙 | `self.fire_at_player(speed=3)` |
| `self.fire_polar(...)` | 极坐标 | `self.fire_polar(orbit_radius=0.1, theta=0, angular_velocity=120)` |
| `ctx.create_emitter(...)` | 发射器 | `ctx.create_emitter(x, y, angle, speed, callback)` |
| `ctx.create_laser(...)` | 直线激光 | `ctx.create_laser(x, y, angle, l1, l2, l3, width, color="red")` |
| `ctx.create_bent_laser(...)` | 曲线激光 | `ctx.create_bent_laser(x, y, length=80, width=0.03)` |
| `ctx.set_time_scale(s, tag)` | 时停 | `ctx.set_time_scale(0.0, tag=1)` |
| `ctx.clear_bullets_by_tag(t)` | 标签消弹 | `ctx.clear_bullets_by_tag(1)` |
| `ctx.bullets_by_tag_to_item(t)` | 标签转道具 | `ctx.bullets_by_tag_to_item(1)` |
| `ctx.spawn_drop(x, y, type=...)` | 掉落道具 | `ctx.spawn_drop(0, 0.5, type="power_small")` |
| `ctx.add_score(n)` | 加分 | `ctx.add_score(100000)` |
| `await self.wait(N)` | 等 N 帧 | `await self.wait(30)` |
| `self.angle_to_player()` | 自机方向 | `angle = self.angle_to_player()` |
| `self.play_se(name)` | 播放音效 | `self.play_se("kira")` |
