# 弹幕脚本书写须知

> 给所有参与弹幕内容创作的 Agent 阅读。**先读完再动手。**

---

## 核心原则

1. **每写一个新脚本，必须加 `DEBUG_BOOKMARK = True`**，这是硬性规定，见下文。
2. **只用引擎现有 API**，绝对不要在脚本里硬搓引擎功能。
3. **发现某个效果用现有 API 无法实现，停下来报告，等人改引擎**，不要绕路。

---

## Debug 工作流（必读）

每次写完一个新脚本，在类里加上：

```python
DEBUG_BOOKMARK = True
```

然后运行：

```bash
python main.py --debug
```

Debug 菜单会列出所有带 `DEBUG_BOOKMARK` 的脚本，可以直接跳进去测试，不用从头打关卡。

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

`speed` 参数的单位是**游戏单位/秒**，引擎内部自动除以 60 转为每帧。  
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

## 已知限制（遇到请报告，不要绕路）

| 功能 | 状态 |
|------|------|
| 子弹击中后变色 | ❌ 不支持 |
| 子弹发射后改变 speed/angle | ❌ 不支持（tag 批量删除可用） |
| 内置 Homing（自动追踪） | ❌ 不支持 |
| 激光 | ✅ 支持 `ctx.create_laser()` / `ctx.create_bent_laser()`（含敌方碰撞判定） |
| 子弹清除特效回调 | ❌ 不支持 |
| 多中心极坐标 | ❌ 不支持 |
| 子弹间互相作用 | ❌ 不支持 |
| Boss 血量阶段触发事件 | ❌ 不支持（只有 timeout/defeated） |

遇到上表以外的限制，**先确认是否真的不支持**（搜索 `spellcard.py` 和 `context.py`），再报告。

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

- `DEBUG_BOOKMARK = True` — 加了就能从 debug 菜单直接跳，**没有借口不加**。
- 不确定某个 API 是否支持，先翻 `src/game/stage/spellcard.py` 和 `context.py`。
- 不要加自己没把握的 import，尤其是 `import random` 之外的标准库。
- 脚本里遇到不能实现的效果，直接在代码注释里写 `# TODO: 需要引擎支持 XXX` 并在回复里说明。
