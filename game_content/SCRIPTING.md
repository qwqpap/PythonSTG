# 弹幕脚本书写须知

> 适用于 `game_content/stages/` 下的手写 Runtime 脚本。先读核心原则，再按所改行为查阅
> Debug、模板或 API 章节。声明式编辑器工程使用 `src.authoring.dsl`，入口见
> [快速开始](../docs/getting-started.md)，不要把这里的类模板放入作者工程。

---

## 核心原则

1. 新增可独立调试的 `Wave`、`SpellCard`、`NonSpell` 类时添加 `DEBUG_BOOKMARK = True`，并确保已按下文挂入对应关卡。
2. 内容通过现有公共 Runtime API 表达行为；池更新和渲染等引擎能力放在引擎层，不能靠逐弹 Python 回调绕过批量路径。
3. 效果缺少公开 API 时，先核对实际实现。若任务已授权引擎扩展，在明确边界后完成实现与验证；若仅授权内容修改，说明缺口和受影响效果。占位 TODO 不算交付。

---

## Debug 工作流

为新的 Wave 或 Boss 攻击类添加：

```python
DEBUG_BOOKMARK = True
```

然后运行：

```bash
python main.py --debug
```

Debug 菜单扫描关卡包 `waves/` 里的 Wave 类，以及 Boss phases 中已注册的攻击类。
仅给普通辅助模块或 EnemyScript 加标记不会产生跳转入口。

**每个脚本单独验证，不要攒在一起。**

---

## 文件结构

```
game_content/stages/stage1/
  stage_script.py          # 关卡总脚本（BossDef、关卡流程）
  spellcards/
    nonspell_1.py          # 非符攻击
    spell_1.py             # 符卡 1
    spell_2.py             # 符卡 2
    ...                    # 继续往后加
  waves/
    fairy_wave.py          # 道中波次
```

新符卡直接在 `spellcards/` 目录下新建 `.py` 文件，然后在 `stage_script.py` 里的 `BossDef` 引用。

---

## 坐标系

| 轴 | 范围 | 说明 |
|----|------|------|
| x  | -1.0 ~ +1.0 | 负=左，正=右，0=中心 |
| y  | 0.0 ~ 1.0（近似） | 0=底部，1=顶部 |

Boss 通常活动在 `y ∈ [0.3, 0.8]`，玩家起始在 `y ≈ 0.1`。

角度单位：**度（°）**，0=右，90=上，-90（270）=下，180=左。

---

## 速度单位

`StageContext.create_bullet()` 的 `speed` 使用作者速度标度，传入池前除以 60；批量接口遵循同一转换。
池层使用归一化单位/帧。内容脚本使用公开接口时不要再自行除以 60。
正常弹幕速度参考：慢弹 ~1.5，普通 ~2.5，快弹 ~4.0+。

---

## 脚本模板

### 非符（NonSpell）

```python
from src.game.stage.spellcard import NonSpell

class MyNonSpell(NonSpell):
    DEBUG_BOOKMARK = True          # ← 必须加

    async def setup(self):
        await self.boss.move_to(0.0, 0.7, duration=40)

    async def run(self):
        angle = 0
        while True:
            self.fire_circle(count=16, speed=2.0, start_angle=angle,
                             bullet_type="ball_m", color="red")
            angle += 10
            await self.wait(30)

spellcard = MyNonSpell
```

### 符卡（SpellCard）

```python
from src.game.stage.spellcard import SpellCard

class MySpell(SpellCard):
    name = "属性「符卡名」"
    hp = 1200
    time_limit = 60
    bonus = 1000000
    DEBUG_BOOKMARK = True          # ← 必须加

    async def setup(self):
        await self.boss.move_to(0.0, 0.65, duration=60)

    async def run(self):
        while True:
            # 弹幕逻辑
            await self.wait(30)

spellcard = MySpell
```

---

## 发弹 API

### `fire()` — 单发

```python
self.fire(
    angle=90,           # 角度（度）
    speed=2.5,          # 速度（作者速度标度）
    bullet_type="ball_m",
    color="blue",
    # 可选扩展：
    accel=0.0,          # 标量加速度（每秒改变 speed）
    angle_accel=0.0,    # 运动角加速度（度/秒²；不影响渲染 spin）
    tag=0,              # 分组标签
    friction=0.0,       # 阻尼（0~1，越大减速越快）
    time_scale=1.0,     # 时间缩放（0=冻结，1=正常）
    bounce_x=False,     # 碰到左右边界反弹
    bounce_y=False,     # 碰到上下边界反弹
    spin=0.0,           # 渲染自转速度（度/秒，不影响运动）
    render_angle=None,  # 初始渲染朝向（None=跟随运动角）
)
```

### `fire_at_player()` — 自机狙

```python
self.fire_at_player(
    speed=3.0,
    offset_angle=0.0,   # 偏转角度（散弹时用）
    bullet_type="rice",
    color="white",
)
```

### `fire_circle()` — 全圆

```python
self.fire_circle(
    count=24,           # 发数
    speed=2.0,
    start_angle=0,      # 起始角度偏移
    bullet_type="ball_m",
    color="red",
)
```

### `fire_arc()` — 扇形

```python
self.fire_arc(
    count=5,
    speed=2.5,
    center_angle=self.angle_to_player(),  # 扇形中心朝向
    arc_angle=60,       # 扇形总角度（度）
    bullet_type="ball_m",
    color="blue",
)
```

### `fire_polar()` / `fire_orbit()` — 极坐标弹

围绕 Boss 做轨道运动的子弹：

```python
self.fire_polar(
    orbit_radius=0.2,       # 初始轨道半径
    theta=0,                # 初始角度（度）
    radial_speed=0.0,       # 径向速度（远离/靠近 Boss）
    angular_velocity=90.0,  # 角速度（度/秒，正=逆时针）
    bullet_type="ball_s",
    color="cyan",
)
```

`fire_orbit()` 是 `fire_polar()` 的语义化别名，完全一样。

### 内置曲线弹（curve_type）

通过 `fire()` 的扩展参数实现：

```python
from src.game.bullet.optimized_pool import (
    CURVE_SIN_SPEED,    # 速度正弦波动
    CURVE_SIN_ANGLE,    # 角度正弦波动（摆弹）
    CURVE_COS_SPEED,    # 速度余弦波动
    CURVE_LINEAR_SPEED, # 线性加减速
)

# 示例：摆弹
self.fire(
    angle=self.angle_to_player(),
    speed=2.0,
    bullet_type="ball_m",
    color="purple",
    curve_type=CURVE_SIN_ANGLE,
    curve_params=(30.0, 2.0, 0.0, 0.0),  # (振幅°, 频率Hz, 初相, 基值)
)
```

---

## Boss 移动 API

```python
# 平滑移动（smoothstep 缓动），duration 单位：帧
await self.boss.move_to(x=0.3, y=0.6, duration=60)

# 瞬移
self.boss.move_to_instant(x=0.0, y=0.5)
```

---

## 等待 API

```python
await self.wait(30)                  # 等待 30 帧（0.5 秒）
await self.wait_seconds(2.0)         # 等待 2 秒
await self.wait_until(lambda: self.time > 300)  # 等待条件
```

---

## 工具方法

```python
self.angle_to_player()          # 从 Boss 当前位置到玩家的角度（度）
self.angle_to_player(x=0, y=0)  # 从指定位置到玩家的角度

self.time          # int, 当前帧数（从符卡开始计算）
self.time_seconds  # float, 当前时间（秒）
self.time_remaining  # float, 剩余时间（秒）
```

---

## 子弹类型表

> **重要**：`bullet_type` 使用的是**别名**（alias），不是内部 sprite ID。
> 例如 `bullet_type="arrow_l"` + `color="red"` 会解析到 sprite `arrow_big2`；
> 直接传 `bullet_type="arrow_big2"` 是错误用法，会回退到默认弹，**不要这样写**。

别名来源：`assets/bullet_aliases.json`，引擎通过 `_resolve_sprite_id(bullet_type, color)` 查表。

| `bullet_type` | 外观 | 支持的颜色组 |
|---------------|------|-------------|
| `ball_s`      | 小圆弹 | 全色（含扩展色） |
| `ball_m`      | 中圆弹 | 基础 8 色 |
| `ball_l`      | 大圆弹 | 基础 8 色 |
| `knife`       | 刀弹 | 基础 8 色 |
| `star_s`      | 小星弹 | 全色（含扩展色） |
| `star_l`      | 大星弹 | 基础 8 色 |
| `arrow_s`     | 小箭头弹 | 全色（含扩展色） |
| `arrow_m`     | 中箭头弹 | 基础 8 色 |
| `arrow_l`     | 大箭头弹 | 见下方详细表 |
| `square`      | 方块弹 | 全色（含扩展色） |
| `butterfly`   | 蝴蝶弹 | 基础 8 色 |
| `ellipse`     | 椭圆弹 | 基础 8 色 |
| `kite`        | 风筝弹 | 全色（含扩展色） |
| `heart`       | 心形弹 | 基础 8 色 |
| `grain_a`     | 米粒弹 A | 全色（含扩展色） |
| `grain_b`     | 米粒弹 B | 全色（含扩展色） |
| `grain_c`     | 米粒弹 C | 全色（含扩展色） |
| `gun`         | 枪弹 | 全色（含扩展色） |
| `mildew`      | 霉弹 | 全色（含扩展色） |
| `ball_light`  | 光球弹 | 基础 8 色 |
| `silence`     | 沉默弹 | 基础 8 色 |

### `arrow_l` 颜色 → sprite ID 对照

| `color`       | 解析 sprite ID |
|---------------|----------------|
| `red`         | `arrow_big2`  |
| `darkred`     | `arrow_big1`  |
| `purple`      | `arrow_big4`  |
| `darkpurple`  | `arrow_big3`  |
| `blue`        | `arrow_big6`  |
| `darkblue`    | `arrow_big5`  |
| `cyan`        | `arrow_big8`  |
| `darkcyan`    | `arrow_big7`  |
| `green`       | `arrow_big10` |
| `darkgreen`   | `arrow_big9`  |
| `yellow`      | `arrow_big13` |
| `orange`      | `arrow_big14` |
| `white`       | `arrow_big16` |
| `gray`        | `arrow_big15` |
| `pink`        | `arrow_big4`  |

---

## 颜色表

### 基础 8 色（所有 bullet_type 均支持）

| `color`    | 说明 |
|------------|------|
| `red`      | 红 |
| `blue`     | 蓝 |
| `green`    | 绿 |
| `yellow`   | 黄 |
| `purple`   | 紫 |
| `white`    | 白 |
| `darkblue` | 深蓝 |
| `orange`   | 橙 |

### 扩展色（仅"全色"类型支持，见类型表"支持的颜色组"列）

| `color`      | 说明 |
|--------------|------|
| `cyan`       | 青 |
| `darkred`    | 深红 |
| `darkgreen`  | 深绿 |
| `darkpurple` | 深紫 |
| `darkorange` | 深橙 |
| `darkyellow` | 深黄 |
| `darkcyan`   | 深青 |
| `black`      | 黑 |

### 特殊色（仅 `arrow_l` 支持）

| `color` | 说明 |
|---------|------|
| `gray`  | 灰 |
| `pink`  | 粉 |

---

## 对话 API

在 `stage_script.py` 的 `run()` 中调用 `await self.play_dialogue([...])` 播放对话。

每条对话支持两种格式：

### 简单格式（无立绘）

```python
("角色ID", "left", "说的话")
```

### 详细格式（推荐，支持立绘和显示名）

```python
{
    "character": "Hinanawi_Tenshi",  # 角色资产文件夹名（必填，用于找立绘）
    "name": "天子",                  # 对话框显示名（可选，不填则用 character.json 的 display_name）
    "position": "left",             # "left" 或 "right"
    "text": "说的话",
    "portrait": "Happy",            # 立绘表情 key，对应 character.json 里的 portraits 键
}
```

`name` 字段的优先级：**脚本里的 `name`** > `character.json` 里的 `display_name` > 原始角色ID。

用 `name` 的场景举例：
- 初次登场用 `"name": "???"` 隐藏角色身份
- 同一角色在不同关卡用不同称呼
- 不想在 JSON 里硬写翻译

### 各角色可用的 portrait key

| 角色 ID | 可用 portrait |
|---------|---------------|
| `Hinanawi_Tenshi` | `Happy` `VeryHappy` `anger` `sad` |
| `Star_Sapphire` | `Happy` `Very_Happy` `Sad` `Anger` `embarrass` `Fail_sad` `Fail_wtf` |
| `Kaenbyou_Rin` | `Happy` `Very_happy` `Sad` `Anger` |
| `Toutetu_Yuma` | `Happy` `VeryHappy` `Sad` `anger` |
| `Sunny_Milk` | `Happy` `VeryHappy` `Sad` `Anger` `Fail_Happy` `Fail_sad` `Fail_Veryhappy` |

`Luna_Child` 暂无立绘文件，写了也不显示（静默跳过，不报错）。

---

## 在 stage_script.py 里注册

```python
from game_content.stages.stage1.spellcards.my_spell import MySpell
from src.game.stage.boss_base import nonspell, spellcard

boss = BossDef(
    id="star_boss",
    name="Star Sapphire",
    texture="star",   # 对应 {texture}_idle / _move_left / _move_right 动画
    phases=[
        nonspell(MyNonSpell, hp=600, time=25),
        spellcard(MySpell, "星符「???」", hp=1000, time=60, bonus=1000000),
    ]
)
```

可用 `texture` 值：`"luna"` / `"star"` / `"sunny"`（精灵已配置好）。

---

## 能力边界与查证

下面区分公开 API 与底层实现，不作为永不过期的能力清单。需要相关效果时，核对
`src/game/stage/spellcard.py`、`context.py` 和本轮即时 Runtime 证据；手写指南中的底层示例不代表声明式 DSL 已支持。

| 功能 | 状态 |
|------|------|
| 子弹击中后变色 | ❌ 不支持 |
| 发射后运动变化 | 支持固定弹群或 tag 的批量速度、方向、一次瞄准、加速度、弹型和时间缩放；支持共享阶段表 |
| 内置 Homing（自动追踪） | 支持共享阶段的持续追踪与转速上限；不是逐弹协程 |
| 激光 | ✅ 支持 `ctx.create_laser()` / `ctx.create_bent_laser()`（含敌方碰撞判定） |
| 子弹终结反应 | 支持批量分裂、完整终结数据转真实 Enemy、聚合生命周期事件；不是逐弹 Python 钩子 |
| 多中心极坐标 | ❌ 不支持 |
| 子弹间互相作用 | 支持整组快照和批量数值规则，包括 first-match 邻域激活；没有通用物理求解器 |
| Boss 血量阶段触发事件 | ❌ 不支持（只有 timeout/defeated） |

新增引擎 API 时同步其内容入口和实际功能检查；若被声明式编辑器公开，还需同步 DSL、生成器与参数映射。
本仓库测试套件已按维护者要求删除，不重建旧套件，也不把旧通过记录当作当前证据。

## 帧任务与稀疏事件（2026-10-12）

Stage、Wave、EnemyScript、SpellCard 继续使用原有协程，不引入 asyncio 或第二套 Runtime。
它们的 `spawn_task(coroutine)` 返回句柄；`await handle.join()` 等待结果，`handle.cancel()`
取消任务，`done/cancelled` 是布尔属性。等待已取消句柄会抛出 `TaskCancelled`，不会伪装成成功。
`await self.parallel([coro_a(), coro_b()])` 等待所有分支；异常会取消未完成分支。
每个 owner 最多 256 个后台任务，已经开始的任务在取消、死亡、结束、停止和异常时执行 `finally`。
普通后台任务在下一次 owner pump 开始；受击和 Parallel 分支可当帧启动，但同帧只推进一次。

受击任务属于当前敌人，死亡时取消。`on_death` 同步回调仍可使用；若返回 awaitable，
引擎把它交给存活的 StageContext，而不是让死去敌人继续 update。在死亡反应里新增后台任务
使用 `self.ctx.spawn_task(...)`，不要调用已关闭的 `self.spawn_task(...)`。
声明式 `OnDeath` 中的引用 Task、SpawnTask 和 Parallel 已自动继承这个存活作用域。
死亡反应仍读取原敌人位置；时间、定时步骤和 Trace 使用存活的任务时钟。
Task/Function 继承实际调用者的动作能力，不凭空拥有所有 Runtime API。构建会检查
Call/SpawnTask 的引用链：Stage 不能借 Task 发弹；Wave 调用发弹 Task 时仍须填写位置或
极坐标中心；Enemy/Spell 可沿用当前对象位置。停止关卡后，已启动步骤的结束 Trace 仍会保留。

```python
class Decoy(EnemyScript):
    hp = 100000

    async def on_hit(self, damage):
        self.fire_circle(count=128, speed=2.0, color="purple")
        # 受击后延迟行为随这个敌人死亡而取消。
        await self.wait(30)
        self.fire_circle(count=32, speed=1.5)

    async def run(self):
        await self.wait(600)
```

声明式 Enemy 根部的 `OnHit([...])` 可用 `Expr("damage")`；`OnDeath([...])` 可用原敌人位置。
钩子不是主流程中的一个顺序步骤，时间线放在独立的动态事件泳道，不占用主流程游标。
Boss 当前仍使用现有 timeout/defeated 阶段入口；没有新增任意血量阈值事件 API。

`await self.ctx.wait_event("enemy.defeated", owner="decoy", timeout=120)` 等待匹配事件，
超时抛 `TimeoutError`，取消或完成自动解绑订阅。`ctx.emit_event(type, data, owner=...)`
发出的事件在下一帧边界派送；同一个派送过程不会递归执行新事件。声明式对应
`WaitEvent/EmitEvent`，任务控制对应 `SpawnTask(assign=...)/JoinTask/CancelTask`。
事件名是双方约定的字符串；Enemy 死亡不会自动发出任意自定义事件，要在钩子里显式 EmitEvent。

## 批量子弹行为

大量子弹使用已有池和 NumPy/Numba，不使用每弹协程。作者入口保持角度为度、速度原标度、
加速度为每秒改变的作者速度。`max_lifetime` 为秒；`delay`、阶段 `frames` 和 `cooldown` 为帧。
底层 Pool 接口则使用弧度、秒和池速度，不要把两层单位混用。

```python
indices = self.fire_circle(count=96, speed=1.5, tag=41)
group = self.ctx.capture_bullets(indices)
self.ctx.set_bullet_behavior(group, stages=[
    {"frames": 30, "speed": 1.5},
    {"frames": 20, "speed": 0},
    {"aim": "player", "speed": 0.6, "accel": 1.2, "bullet_type": "rice", "color": "blue"},
])
```

每组最多 64 个阶段。只有最后阶段可省略 `frames` 持续执行；0 帧阶段立即衔接。
省略 speed/angle 继承当前数值；省略 accel/turn_rate 归零。`aim="player"` 从每颗弹的当前位置
在进入阶段时瞄准一次，不是持续 homing。`turn_rate` 单位度/秒；`bounce_x/bounce_y` 是该轴
剩余反弹次数，区别于发射参数中的无限反弹布尔开关。现有曲线、阻尼等发射参数仍参与运动，
阶段表不是任意脚本解释器。

### 数组读写与连续公式

`create_bullets_batch` 的角度、速度、加速度、时间缩放、弹型索引等数值参数支持标量广播或
每颗弹各不相同的数组。位置为 `(N, 2)`；`vector_accel` 为 `(2,)` 或 `(N, 2)`。
`curve_params` 可为 `(4,)` 或 `(N, 4)`。`bullet_type/color` 仍是整组名称；不同弹型用
`ctx.bullet_sprite_index(type, color)` 解析出索引，再传 `sprite_idx` 数组。容量不足只发同一
输入前缀，所有字段一致截断，返回实际出生索引。没有把未知参数静默丢弃的单发降级。

```python
import numpy as np

snapshot = self.ctx.read_bullets(tag=41, fields=('pos', 'vel', 'acc', 'speed'))
# 快照数组独立、只读。vel/speed 是作者速度标度，acc 是作者速度标度/秒。
acceleration = np.column_stack((-snapshot['pos'][:, 1], snapshot['pos'][:, 0])) * 3.0
self.ctx.transform_bullets(snapshot.group, vector_accel=acceleration)
```

字段名为 `pos/vel/acc/angle/speed/speed_accel/sprite_idx/tag/time_scale/lifetime`；
Context 的 angle 为度、lifetime 为秒，底层 Pool 的 angle 为弧度、速度与加速度是对应
作者值除以 60。只读取需要的字段，避免每帧复制无关数组。二维加速度与沿方向的 `accel`
分别作用于速度向量和速度大小，可同时使用。`positions/velocities/vector_accel/angle_accel`
与数值变换字段均支持数组；`velocities` 不可同时传 speed、angle 或 aim。

固定 group 的数组必须与**原 N 行**对应：中途死弹、区域筛选或冷却剔除不会把第 i 行错写给
别的弹，短到仅存活数量的数组会被拒绝。优先用 `snapshot.group` 写回；即使 await 后旧槽
被复用，也只写原来的 generation。`snapshot.select(bool_mask)` 可保留选中行及其代数。

```python
def swirl(snapshot):
    # 包装函数每组每帧只调用一次；Numba 内核接收提取出来的数组。
    p = snapshot['pos']
    return {'vector_accel': np.column_stack((-p[:, 1], p[:, 0])) * 3.0}

handle = self.spawn_task(self.ctx.run_bullet_rule(
    swirl, group, fields=('pos',), frames=240,
))
```

`run_bullet_rule` 返回现有 Task 可等待的协程，不新增调度器；规则必须同步返回
`transform_bullets` 参数字典，不能在 snapshot→写回之间 await。普通 dataclass/字典不直接
传给 `@njit`：包装函数提取数组，调用 NumPy 或 Numba 数值函数，再返回批量更新。
固定组空了自动结束；动态 tag 暂时没有弹时继续等待后续出生。`clear_all` 使已有及尚未开始的
规则结束，不能对清场后的新弹继续生效。随敌人结束使用 `self.spawn_task`；要在敌人死亡后
继续整个关卡，则用 `ctx.spawn_task`，二者不可混淆。修改按现有“池运动→脚本→碰撞”顺序
写入，下次池运动体现；Context 任务从 Stage 内创建时首算在下一帧，不是隐含 immediate。

### 持续追踪与限次穿屏

```python
self.ctx.set_bullet_behavior(group, stages=[
    {'frames': 90, 'homing': 'player', 'max_turn_rate': 45, 'wrap_x': 2},
    {'frames': 60, 'vector_accel': (0, -6)},
    {'speed': 2, 'wrap_x': 0},
])
```

`homing` 每帧读取玩家位置，也可为固定 `(x, y)`；离开该阶段立即停止追踪。
`max_turn_rate` 必须显式给出，单位度/秒，受 time_scale 影响，使用跨 ±180° 的最短转向。
它只限制**追踪的转向修正**，不是叠加二维力或外部规则后的总方向变化。与同阶段非零
turn_rate 互斥；`aim` 仍是进入阶段时的一次瞄准。省略 vector_accel 的下一段归零。

`wrap_x/wrap_y` 为剩余穿屏次数，省略沿用、0 取消，正值重新设定次数；同轴正反弹与正穿屏
互斥。边界与现有反弹一致：X 为 [-1, 1]，Y 为 [-1.14, 1]；到达边界不算越界。
高速一帧可跨多次，保留超出距离并逐次扣除。花掉最后一次后仍可存活；后续越界按原有
±1.5 出屏回收范围处理，不突然在边缘删除。默认未使用穿屏的弹不增加穿屏扫描，状态数组
只在使用时分配。共享阶段会清理旧曲线、阻尼及极坐标运动，避免隐含双重驱动。

### 完整终结转换

```python
token = self.ctx.convert_bullets_on_end(71, MyFairy, reasons=('expired',))
try:
    self.fire_circle(count=16, tag=71, max_lifetime=1.0)
    await self.wait(180)
finally:
    self.ctx.cancel_bullet_conversion(token)
```

`MyFairy` 是普通无参数 `EnemyScript` 子类。回收母弹前保存**全部**位置、角度和速度，
不会只生成 Trace 的八个样本；Pool 不认识 Enemy。StageManager 在该帧关卡推进结束后
创建、bind/start/add 真正的敌人，出生时 time=0，下次敌人更新才执行 on_spawn/run。
`source_angle/source_velocity` 为作者单位，`source_tag/source_end_reason` 保留来源信息。
每个注册 token 独立取消，取消连尚未消费的批次一并丢弃。默认只接受 expired，Bomb、命中、
出屏和普通清弹不转换；可显式选择原因，但整个 `clear_all` 或关卡停止始终取消注册与队列。
这是少量真实敌人的实体转换，不承诺 50,000 子弹变成 50,000 个 Python 敌人仍高性能。

### 两个 TH06 机制的正常示例

`game_content/examples/th06_patterns.py` 提供可复用的 `distance_turn`、`neighbor_turn`、
`stop_acceleration`，及普通 `BatchMechanicsStage`。前者保留距离平方阈值、共享随机角，
后者保留严格半径、来源槽位顺序首次匹配和不环绕的 2.2 倍角差。例子取 192px 为一坐标单位，
保留机制公式和 120 次加速度积分，不是原版贴图/坐标系的像素级移植或 ECL 解释器。
大小弹通过作者给的群区分，不依赖精灵高度猜测。

数值函数从 `src.content_api` 导入 `distance_acceleration/neighbor_activation`；它们的角度
参数/返回角度为弧度，与 Context 的度不同，写回前用 `np.rad2deg`。邻域计算不分配 M×N
矩阵，但最坏仍是 M×N 次比较；来源很多时要实测并考虑空间索引，不能许诺任意规模。

声明式现有 Fire、FireCircle、FireArc、FireAtPlayer 已映射 vector_accel，TransformBullets
已映射新增批量字段，SetBulletBehavior 的 stages 可用新增字段。完整数值规则和实体转换属于
Runtime 脚本 API；声明式高级作者可用现有 RawPython/函数扩展，没有为此新造节点或蓝图。
本轮不声明这些机制都已能由纯 GUI 拖拽完成。
这些新入口接在 StageContext/StageManager：整关与现有生成练习场走这条路径。
独立 `tools/preview_spell.py` 也推进正式 Context 任务、事件、转换队列和实体敌人。
它先更新已有子弹/激光/道具，再推进控制任务和符卡；新弹次帧才运动。敌人在此工具里仍以
位置标记显示，不是完整贴图预览；实际受击、玩家 Bomb 和关卡结算仍须在正式游戏验证。

固定 `BulletGroup` 保存槽位及代数：母弹死亡且槽位复用后，新弹不会混进旧组。
`ctx.select_bullets(tag=...)` 返回当前快照，`ctx.count_bullets(group)` 只计仍存活的原弹。
每次传 `tag=...` 操作则动态选择当时存活的全部匹配弹。

```python
region = {"kind": "rect", "x": 0.0, "y": 0.4, "width": 0.6, "height": 0.2, "angle": 30}
self.ctx.transform_bullets(tag=41, region=region, aim="player", speed=2.0,
                           cooldown=30, cooldown_key="turning_field")
```

还支持圆区域 `{"kind": "circle", "x": 0, "y": 0.4, "radius": 0.3}`。不同场或规则使用不同 `cooldown_key`；同一个 key
在单颗弹冷却期间不会重复变换。冷却按游戏时间，不按该弹的 time_scale；槽位复用重置冷却。
设置正 cooldown 必须提供 key，不能悄悄共用所有场的计时器。

```python
self.ctx.split_bullets_on_end(51, count=8, speed=1.6, child_tag=52)
self.fire_circle(count=32, speed=1.0, max_lifetime=2.0, tag=51)
```

分裂保存全部母弹的位置和角度，在每个母弹原位生成子弹；Trace 的最多八个样本只用于观察。
默认只因 `expired` 自然寿命结束分裂，Bomb、命中、出屏和阶段清弹不触发。
可显式传 `reasons`，但 `clear_all_bullets()` 是整个弹幕作用域取消：不再生，并撤销反应注册、
待出生队列、阶段定义和冷却规则。默认 child_tag=0，避免无意无限连锁；需要连锁时显式设计。
生成总量受池容量限制，池满会少发，不自动扩容。

所有新弹从下一次池更新开始运动/碰撞。`delay=1` 在一次 update 末尾出生，再下一次才运动。
未出生的延迟弹没有槽位，不能捕获到固定弹群。声明式 `Fire(delay>0, assign=...)` 会报构建错误；
要用 `Wait(...) -> Fire(assign=...)`，或用 tag 管理后续出生的弹。

声明式对应 `SelectBullets/TransformBullets/SetBulletBehavior/SplitBulletsOnEnd/ClearBulletGroup`；
Fire、FireCircle、FireArc、FireAtPlayer 的 `assign` 可保存固定弹群。
编辑器字段和搜索入口已接线，但本轮未进行完整 GUI 创作/原生嵌入验收。

## 敌人、Boss 与移动激光

EnemyScript 和 BossBase 共用移动 API；坐标仍是归一化单位，Y 向上，角度用度。
移动时长是帧；move_velocity 的速度/加速度分别是归一化单位/秒、单位/秒²，不要与
子弹的作者速度标度混用。

```python
# 在 EnemyScript 的 run() 中；符卡改用 actor = self.boss。
actor = self
actor.set_movement_bounds(-0.8, 0.8, -0.4, 0.7)
await actor.move_to(0.5, 0.4, 45, easing='ease_out_fast')
await actor.move_linear(-0.4, 0.0, 30)  # 相对位移，不是目标坐标
motion = self.spawn_task(actor.move_velocity(-90, 0.3, turn_rate=45))
await self.wait(120)  # 移动与当前控制流程并行
motion.cancel()
actor.clear_movement_bounds()
```

easing 可选 linear、smoothstep、ease_in/out（二次方）、ease_in_fast/out_fast（四次方）。
duration=0 是瞬移；取消停在当前位置。标准移动和 set_position 遵守边界；直接赋 x/y
是低层操作，不会经过边界约束。声明式 MoveTo 也有 easing，保存/生成仍走同一 Runtime。

四个交互开关彼此独立：

- collidable：能否成为自机弹/玩家激光的碰撞目标。
- damageable：受击是否扣 HP；关闭后仍可触发 on_hit。
- interactable：能否被命中/追踪；关闭时不触发受击反应。
- visible：是否绘制；不可见不等于无敌。

```python
# EnemyScript 子类方法：可以命中并反击，HP 不扣。
async def on_spawn(self):
    self.set_interaction(damageable=False)

async def on_hit(self, damage):
    self.fire_circle(count=32, speed=12, play_sound=False)
    await self.wait(4)
    self.fire_circle(count=32, speed=18, play_sound=False)
```

on_hit 使用敌人/当前符卡的任务作用域；死亡会取消延迟反击并执行 finally。
on_death、Spell.on_defeated/on_timeout 需要在实体结束后继续的反应由 StageContext 承接，
仍不能跨已停止的关卡。密集命中应在内容中加反击间隔，而不是为每颗敌弹安装回调。

```python
laser = self.ctx.create_laser(-0.8, 0.6, -25, 0.0, 0.5, 0.0, 0.04, color='blue')
if laser is None:
    raise RuntimeError('laser capacity exhausted')
laser.configure_motion(speed=0.6, start_offset=0.0, end_offset=0.1, length=0.5)
laser.configure_lifecycle(warning_frames=24, active_frames=120, fade_frames=16,
                          hitbox_delay=24, hitbox_fade_frames=0)
await self.wait(36)
points = laser.sample_points(0.25)  # 当前段起点、起点+step……严格不到终点
self.ctx.create_bullets_batch(positions=points, angles=-90, speeds=12,
                              bullet_type='grain_a', color='blue')
```

激光长度/宽度/取样间隔用归一化单位，移动速度用单位/秒。警告、持续、消退与碰撞窗口分开；
显示、取样、碰撞共享当前段几何。transition_hitbox='midpoint' 只用于显式表达 TH06
过渡期的短轴向框，不是默认碰撞。turn_on/turn_off 回到手动生命周期；destroy 立即结束，
Pool.clear 使旧句柄也失效。

普通示例 `game_content/examples/th06_controls.py` 包含假身、移动、48 条交错激光、
沿当前激光段批量发射与时停；它不是完整原作符卡。弹型使用现有 grain_a 等别名，
不能把未注册的名字当成可绘制资源。

## 跨关状态与分系统时停

StageManager 持有一个 RunState，各关复用同一实例。宿主可以这样设置输入：

```python
from src.game.state import RunState

state = RunState(difficulty='hard', player_shot='reimuA', rank=16,
                 min_rank=10, max_rank=32)
stage_manager.bind_engine(bullet_pool=pool, player=player, run_state=state,
                          laser_pool=lasers, item_pool=items)
```

内容读取 ctx.difficulty、ctx.player_shot、ctx.rank 或 ctx.run_state。shot 是内容定义的
标识，当前引擎的三个角色不是原作四机体。游戏 C 键切换通过 StageManager.bind_player
同步实际玩家和 shot；更换关卡不会重置 rank。独立符卡预览重启则恢复初始 RunState。
默认不自动套 TH06 rank 策略；state.adjust_rank(delta) 按 100 subrank/rank 进位，
rank_value(low, high) 按 rank/32 插值。rank_event_deltas 可配置 miss/Bomb 等稀疏事件增量。

```python
self.ctx.run_state.rank_event_deltas.update({
    'player.missed': -1600, 'player.bomb_used': -200,
})
with self.ctx.stop_time():
    await self.wait(60)  # 控制协程仍推进，所以能在 60 帧后释放
```

默认停 player、bullets、lasers、background、effects、boss_timer；不停 actor 脚本和 items。
可显式传域名，例如 stop_time('bullets', 'lasers', 'boss_timer')；重叠作用域不能误解除彼此。
with/finally 或 lease.release() 释放；Context.dispose() 释放全部租约。
这不是系统 pause，也不自动产生原作时停染色/GUI 特效。
当前 effects 域暂停粒子池和 emoji 系统更新，不覆盖所有装饰动画、GUI 或角色 Bomb 视觉。

Spell.time 是单调控制帧时钟；timer_frames/elapsed_seconds/time_remaining 是 Boss 计时。
set_timer(elapsed_frames=0) 改变倒计时已走时间，不重绕 Task/Wait/Trace。self.boss.hp 可供
条件任务观察。ctx.get_player().is_bombing 读取玩家的 bomb_power_timer 激活/增伤窗口，
不是角色视觉 Bomb 的统一生命周期；自定义 bomb_handler 必须自己设置它所需的玩家状态。
BombAwareBat 示范同一敌人在该窗口结束后延迟 60 帧恢复交互。移植原作时还需对齐其
实际 Bomb 持续时间，不能把这个窗口直接当成所有机体的原作视觉存续时间。

## 可配置收集、计分和符卡结算

这些规则是稀疏事件入口，不是逐弹运动函数。未配置时仍使用既有默认玩法。

```python
from src.game.item import ItemType

stats = self.ctx.item_stats
stats.max_power, stats.power_scale = 128, 32.0
self.ctx.item_config.auto_collect_requires_full_power = True

def collect(stats, item):
    if item.item_type == ItemType.POWER:
        stats.power = min(stats.max_power, stats.power + 1)
    elif item.item_type == ItemType.POINT:
        stats.add_score(100000)  # 示例，不是原作高度公式

self.ctx.set_item_collection_rule(collect)
self.ctx.spawn_item(0.0, 0.5, ItemType.POWER_LARGE, speed=0.6, angle=90)
```

collect 替换默认收集规则；item 是不可变的 ItemCollection，只有 item_type/x/y/attracting，
不是可写池槽。规则负责它需要的全部物品类别及溢出处理。实际收集项按槽位顺序调用，
移动/吸附仍在 SoA/Numba 内核，不为未收集的道具创建规则对象。spawn_item 的可选 speed
用单位/秒、angle 用度；spawn_drop 继续支持原有组合掉落。

GameStats.add_score/add_graze 接正式命中得分与擦弹；on_score(stats, amount)、
on_graze(stats, count)、on_miss(stats, player)、on_continue(stats, player) 可配置规则。
on_score 中不要递归调用 add_score。hit_score、respawn_bombs 可配置；power_scale 定义
原始 P 与 Player.power 的换算，避免每帧同步把死亡扣掉的 P 恢复。
miss/continue hook 在现有玩家流程之后运行；它们不等于已替换全部原作死亡/Deathbomb 状态机。
rank 的收集/擦弹增量由这些普通内容规则设置，不藏在池内。

run_state.bomb_handler(player, ctx) 是同步规则，返回取消弹数；它替换旧全局无敌/增伤/
清弹/收点策略，内容必须自己设置所需状态。角色 PlayerScript 仍负责实际 Bomb 的弹幕和
视觉。ctx.cancel_bullets_for_bomb(to_items=True) 提供正式清弹/转点入口，保留引擎的
Bomb protected tags；to_items=False 只清弹，不生成道具。

```python
from src.game.stage.boss_base import spellcard

def bonus(boss, spell):
    return int(spell.bonus * max(0.5, spell.time_remaining / spell.time_limit))

def finish(boss, result):
    if result.reason == 'defeated' and result.no_miss and result.no_bomb:
        boss.ctx.add_score(result.bonus)
    boss.ctx.bullets_to_items(boss.ctx.select_bullets())
    boss.ctx.clear_all_lasers()

phase = spellcard(MySpell, '示例符卡', hp=1000, time=30,
                 bonus_rule=bonus, finish_rule=finish)
```

bonus_rule 读取本次 update 后的最终计时/HP，结束帧也计算；finish_rule 收到不可变 SpellResult：
reason、phase_type、hp、elapsed_frames、bonus、no_miss、no_bomb、is_survival。
配置 finish_rule 后不提前清掉结算所需弹幕；规则须明确清弹/掉落/得分。异步 finish 或
结束 hook 使用 StageContext 任务，可跨本符卡但不能跨停止的 Stage。
Boss.collect_items_on_defeat 可禁用最后阶段后的默认吸道具。

`game_content/examples/th06_rules.py` 展示 128P/8P 档位、rank、收集和生存超时结算。
示例的得点/extend/bonus 不是全部原作精确规则；完整内容策略仍需移植并独立对照。

## 非碰撞粒子

粒子是独立装饰池，不用“无碰撞子弹”冒充；不会碰撞、擦弹、掉分或随清弹/Bomb 消失。
关卡停止/切换、预览关闭/重启和 continue 清理粒子。默认容量 8,192，可在绑定引擎时提供
自定义 `ParticlePool`。寿命按 60 Hz 帧计，出生显示 age=0，下一仿真步才运动；到 lifetime 回收。

```python
import numpy as np
from src.game.particle import ParticleEffect

angles = np.deg2rad(np.arange(32) * (360.0 / 32))
velocities = np.column_stack((np.cos(angles), np.sin(angles))) * 1.5
accelerations = -velocities * 3.0
# 使用精灵目录的准确 ID；grain_a16 是本仓库白色米弹贴图，不是 bullet_type 别名。
spark = ParticleEffect(('grain_a16',), lifetime=30,
                       scale=1.2, scale_end=0.2, alpha=1.0, alpha_end=0.0,
                       angular_speed=120.0, blend='add', layer='front')
group = self.ctx.emit_particles(spark, self.boss.x, self.boss.y, count=32,
                               velocity=velocities, acceleration=accelerations,
                               color=(0.4, 0.6, 1.0, 1.0))
```

`velocities`/`accelerations` 为 NumPy `(32, 2)` 数组或统一二维向量。粒子的 velocity 用单位/秒，
acceleration **用单位/秒²**（内部分别除以 60、3600；不要套用历史敌弹加速度约定）。
x/y、rotation 可为标量或长度 count 的数组；rotation 和 direction 用度。color 是 0–1 RGBA
或 `(count, 4)` 数组，乘贴图颜色/alpha；需要任意染色时使用白色贴图。
`group.count` 是实际出生数，`group.dropped` 是满池丢弃数；满池不挤掉旧粒子或敌弹。

`ParticleEffect.sprites` 是一帧或多帧的精灵 ID 元组，`frame_ticks` 定义每帧显示多久；
默认到最后一帧后保持，`loop=True` 循环。scale/scale_end 可为标量或二维尺寸倍率；
alpha 和尺寸在 lifetime 内线性变化，angular_speed 用度/秒。`blend` 为 alpha/add，
`layer` 为 back/front：back 在敌人后、道具前，front 在激光后、判定点/HUD 前。
同层保持出生顺序，只合并相邻同纹理/混合的段，不为了省 draw call 改变半透明叠加顺序。

收拢使用 `motion='radial'`，x/y 为中心、radius 为初始距离、radial_speed 为单位/秒、
direction 为方向；默认线性运动按“位置 += 速度，再速度 += 加速度”积分。
radial 模式也可移动中心；半径不会自动钳在 0，需要在穿过中心前结束时由内容选择寿命。
`clear_particles(group)` 清指定出生代，`clear_particles()` 清全池，`count_particles(group)` 读
当前存活数。旧句柄不会误操作同槽新粒子；全清后共享视觉定义也释放，不能跨关保留句柄。

复杂数值轨迹可用一个普通 Task 驱动整群，不建逐粒子协程：

```python
snapshot = self.ctx.read_particles(group)  # 脱离池的只读数组
positions = my_numpy_formula(snapshot['position'])
self.ctx.transform_particles(snapshot.group, position=positions,
                             scale=(1.0, 1.5), color=(0.5, 0.6, 1.0, 0.8))
```

快照字段为 position、velocity、acceleration、rotation、scale、color、age；单位同发射。
transform 除 age 外接受上述字段，数组与快照 group 的出生行对齐；await 后死亡行自动排除，
不把幸存 N 行错写到原 N 行。scale 是共享动画倍率之外的额外倍率。
rotation 是粒子的基础角度偏移，绘制时再加 effect 的 angular_speed×age/60；快照不把
共享动画的角度/尺寸/alpha 烘焙回基础字段。改变颜色 alpha 同样乘共享动画 alpha。
常规更新/动画打包为
SoA/Numba，GPU 为复用实例缓冲；定义在首次使用时编译，单作用域最多 256 个定义、
65,536 个视觉帧，复用常量定义，不在每帧随机造新定义。

`game_content/examples/th06_particles.py` 包含散射减速、停弹闪光、60/240 帧收拢、双翼颗粒
和整批三维旋转的二维投影。它使用现有贴图及新的视觉时序，不是原作 ANM；三维深度/附属
动画/原随机序列尚未移植。高级接口经现有 RawPython 可用，本轮不新增 GUI 粒子节点。

```powershell
C:/Users/m1573/anaconda3/python.exe tools/preview_spell.py game_content/examples/th06_particles.py ParticleMechanicsSpell
```

## 独立符卡预览的当前边界

```powershell
C:/Users/m1573/anaconda3/python.exe tools/preview_spell.py game_content/examples/th06_controls.py ControlMechanicsSpell --difficulty hard --player-shot reimuA --seed 1337
```

使用正式 Boss/Context/EventBus/Pool 和当前 renderer；真实激光、道具、粒子会显示，转换敌人
目前只有位置标记。结束后会推进明确的异步结束反应及其 awaited 子任务，不等待无关无限
后台任务；关闭/异常会取消作用域并执行 finally。重启准备独立候选池，候选 bind/start
已发射也不污染旧预览；失败保留旧实例/池/RNG，成功替换全部池。外部渲染必须读取
runtime.bullet_pool，不能持有最初传入的旧池。

这个工具预览普通手写脚本，文件监视/重载不改变 GUI 编辑器的“显式 Run、编辑标记 stale”
契约。seek 仍从 0 快进；它没有完整玩家射击/受伤/Bomb/关卡结算，不能替代整关检查。

## 性能边界与 Rust

游戏逻辑固定 60 Hz；慢机器会整体变慢，本轮没有增加补帧 accumulator 或新渲染后端。
正式游戏和符卡预览在 gameplay 前调用 `pool.warmup()`，分别打印 JIT 编译/缓存加载时间；
这个启动开销不能混入预热后每帧数据。渲染复用既有分桶和实例绘制，连续数组直接上传，
不再先复制成 Python bytes；GPU 上传本身仍存在。

2026-10-12 本机池层配对测量：普通 50,000 弹 median 1.148ms；两种四阶段负载 median 2.148/2.503ms；
10,000 母弹终结生成 40,000 子弹的该帧 median 8.642ms，p95 9.251ms。
这些不是整个游戏帧耗时，也不证明任意背景、激光或特效能稳定 60 FPS。
完整负载、GPU 和证据范围见 `docs/EDITOR_IMPLEMENTATION_TODO.md` 当前维护任务。

Rust 小内核暂不加入依赖。只有实测数值热路径持续超预算时，再考虑 PyO3 批量数组接口；
Python 保留关卡、协程、作者 API 和编辑器，Rust 可替换运动、碰撞或批量回收/生成。
不要逐颗跨语言调用，也不要因为换语言就重写整套引擎。

---

## 节奏参考（60 FPS）

| 时间 | 帧数 |
|------|------|
| 0.5 秒 | 30 帧 |
| 1 秒 | 60 帧 |
| 2 秒 | 120 帧 |
| 1 分钟 | 3600 帧 |

符卡默认时限 60 秒。非符通常 20~30 秒。

---

## 最后提醒

- 确认新 Wave 或 Boss 攻击的 Debug 入口可以到达；声明式单元通过编辑器 Run 验证。
- 不确定某个 API 是否支持，先翻 `src/game/stage/spellcard.py` 和 `context.py`。
- 导入实际需要且存在的 API；涉及随机性时保持所测路径的 seed 可复现。
- 报告实现了哪些效果、验证了哪些路径和仍缺少的能力，不把注释 TODO 或未运行的脚本当作完成。
