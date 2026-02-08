# pystg 关卡脚本编写指南

> 本文档面向**关卡内容创作者**——只需要关心弹幕/敌人/Boss 的设计，不需要了解引擎内部。

---

## 目录

1. [架构概览](#1-架构概览)
2. [目录结构规范](#2-目录结构规范)
3. [快速开始：5 分钟写出你的第一个符卡](#3-快速开始5-分钟写出你的第一个符卡)
4. [核心概念](#4-核心概念)
5. [编写符卡（SpellCard）](#5-编写符卡spellcard)
6. [编写波次（Wave）](#6-编写波次wave)
7. [编写敌人脚本（EnemyScript）](#7-编写敌人脚本enemyscript)
8. [编写 Boss 配置](#8-编写-boss-配置)
9. [编写关卡配置（stage.json）](#9-编写关卡配置stagejson)
10. [弹幕 API 参考](#10-弹幕-api-参考)
11. [坐标系统](#11-坐标系统)
12. [完整示例：Stage 1 逐文件解析](#12-完整示例stage-1-逐文件解析)
13. [常见问题](#13-常见问题)
14. [从零创建一个新关卡](#14-从零创建一个新关卡)
15. [音频系统](#15-音频系统)

---

## 1. 架构概览

pystg 的关卡系统采用**引擎层 / 内容层**分离的设计：

```
┌──────────────────────────────────────────────────┐
│                    引擎层 (src/)                   │
│  提供能力，不关心具体关卡内容                        │
│                                                    │
│  Bullet（子弹池）  Player（玩家）  Renderer（渲染）  │
│  Boss 基类        Enemy 基类     SpellCard 基类    │
│  Wave 基类        Stage 基类     Coroutine（协程）  │
│  StageContext（上下文桥梁）                         │
└─────────────────────┬────────────────────────────┘
                      │ StageContext
                      │ （引擎向内容提供的统一接口）
┌─────────────────────▼────────────────────────────┐
│              内容层 (game_content/)                │
│  只描述"发生什么"，不关心"怎么实现"                   │
│                                                    │
│  波次脚本    敌人定义    Boss配置    符卡脚本        │
│  对话内容    时间线      资源引用                    │
└──────────────────────────────────────────────────┘
```

### 核心原则

| 规则 | 说明 |
|------|------|
| ✅ 内容层只用基类 API | `self.fire()`, `self.wait()`, `self.move_to()` |
| ✅ 内容层通过 `ctx` 与引擎交互 | `ctx.create_bullet()`, `ctx.get_player()` |
| ❌ 内容层不能 import 引擎模块 | 不能出现 `from src.game.bullet import BulletPool` |
| ❌ 内容层不处理渲染/碰撞/物理 | 这些是引擎的事 |

**你需要 import 的只有基类：**

```python
from src.game.stage.spellcard import SpellCard, NonSpell   # 符卡
from src.game.stage.wave_base import Wave                   # 波次
from src.game.stage.enemy_script import EnemyScript         # 敌人脚本
```

---

## 2. 目录结构规范

每个关卡是 `game_content/stages/` 下的一个文件夹：

```
game_content/stages/
├── stage1/                      ← 关卡 1
│   ├── __init__.py              ← 关卡元信息
│   ├── stage.json               ← 时间线（定义关卡流程）
│   │
│   ├── waves/                   ← 道中波次脚本
│   │   ├── opening_wave.py      ← 开场波次
│   │   ├── fairy_wave.py        ← 妖精编队
│   │   └── post_midboss_wave.py ← 道中Boss后收尾
│   │
│   ├── bosses/                  ← Boss 配置
│   │   ├── midboss.json         ← 道中Boss的符卡序列
│   │   └── boss.json            ← 关底Boss的符卡序列
│   │
│   ├── spellcards/              ← 符卡脚本（Boss 的攻击模式）
│   │   ├── nonspell_1.py        ← 第1段非符
│   │   ├── spell_1.py           ← 月符「Moonlight Ray」
│   │   └── spell_2.py           ← 夜符「Night Bird」
│   │
│   ├── enemies/                 ← 可复用的敌人脚本
│   │   └── fairy.py             ← 红/蓝妖精
│   │
│   ├── dialogue/                ← 对话脚本
│   │   └── pre_boss.py          ← Boss前对话
│   │
│   └── audio/                   ← 关卡私有音频（可选）
│       ├── se/                  ← 关卡专属音效
│       └── music/               ← 关卡专属 BGM
│
├── stage2/                      ← 关卡 2（同样结构）
│   ├── stage.json
│   ├── waves/
│   ├── bosses/
│   ├── spellcards/
│   ├── enemies/
│   └── dialogue/
│
└── stage3/                      ← 关卡 3
    └── ...
```

**关键规则：`game_content/` 下的文件不能出现引擎逻辑！**  
只允许出现：弹幕定义、敌人行为、Boss配置、时间线、对话、音频资源、资源引用。

---

## 3. 快速开始：5 分钟写出你的第一个符卡

### 第 1 步：创建符卡脚本

在 `game_content/stages/stage1/spellcards/` 下新建 `my_spell.py`：

```python
"""我的第一个符卡"""
from src.game.stage.spellcard import SpellCard


class MySpell(SpellCard):
    name = "火符「My First Spell」"
    hp = 1000
    time_limit = 45
    bonus = 500000
    
    async def setup(self):
        """Boss 移动到上方中央"""
        await self.boss.move_to(0, 0.5, duration=30)
    
    async def run(self):
        """弹幕逻辑"""
        angle = 0
        while True:
            # 发射 12-way 红色圆弹
            self.fire_circle(
                count=12,
                speed=2.0,
                start_angle=angle,
                bullet_type="ball_m",
                color="red"
            )
            angle += 10  # 每次旋转
            
            await self.wait(15)  # 等 15 帧（0.25秒）


# 必须注册！
spellcard = MySpell
```

### 第 2 步：在 Boss 配置中引用

编辑 `bosses/boss.json`，在 `phases` 数组中添加：

```json
{
    "type": "spellcard",
    "hp": 1000,
    "time": 45,
    "script": "my_spell",
    "name": "火符「My First Spell」",
    "bonus": 500000,
    "practice_unlock": true
}
```

### 第 3 步：运行游戏看效果

就这么简单。不需要改引擎代码，不需要注册任何东西。  
`boss.json` 里的 `script` 字段会自动加载对应的 Python 文件。

---

## 4. 核心概念

### 4.1 协程（Coroutine）——弹幕的"时间控制器"

pystg 使用 Python 的 `async/await` 语法来控制弹幕的时间节奏。**每一帧**游戏会推进你的协程一步。

```python
async def run(self):
    # 这行在第 1 帧执行
    self.fire_circle(count=8, speed=2.0)
    
    # 暂停 30 帧（0.5秒），然后继续
    await self.wait(30)
    
    # 这行在第 31 帧执行
    self.fire_circle(count=16, speed=3.0)
```

**`await self.wait(N)`** = 暂停 N 帧。60帧 = 1秒。

### 4.2 SpellCard（符卡）——Boss 的攻击模式

一个符卡就是 Boss 的一段攻击。它有：
- **HP**：被打多少下结束
- **时间限制**：超时自动结束
- **bonus**：满血击破的奖励分数

```python
class MySpell(SpellCard):
    name = "符卡名"     # 符卡宣言时显示
    hp = 1200           # Boss 在这段的 HP
    time_limit = 60     # 60秒时间限制
    bonus = 1000000     # 击破奖励
```

### 4.3 NonSpell（非符）——Boss 的普通攻击

和符卡类似，但：
- 没有名字显示
- 奖励较少
- 默认不能在练习模式单独练

```python
from src.game.stage.spellcard import NonSpell

class MyNonSpell(NonSpell):
    hp = 800
    time_limit = 30
    
    async def run(self):
        ...
```

### 4.4 Wave（波次）——道中弹幕

不绑定 Boss 的弹幕脚本，用于道中小怪阶段。

```python
from src.game.stage.wave_base import Wave

class MyWave(Wave):
    async def run(self):
        for i in range(8):
            self.fire(x=-0.7 + i*0.2, y=0.9, angle=-90, speed=2.0)
        await self.wait(60)
```

### 4.5 EnemyScript（敌人脚本）——可复用的小怪行为

定义一个敌人从出生到消失的完整行为。

```python
from src.game.stage.enemy_script import EnemyScript

class RedFairy(EnemyScript):
    hp = 30
    score = 100
    
    async def run(self):
        await self.move_to(self.x, 0.3, duration=60)
        self.fire_circle(count=8, speed=2.0, color="red")
        await self.wait(30)
        await self.move_to(self.x, -0.2, duration=60)
```

---

## 5. 编写符卡（SpellCard）

### 5.1 基本模板

```python
"""
符卡名「英文名」

[设计思路简述]
"""
from src.game.stage.spellcard import SpellCard


class MySpellCard(SpellCard):
    # ===== 元信息 =====
    name = "符卡名「English Name」"
    hp = 1200
    time_limit = 60        # 秒
    bonus = 1000000
    
    # ===== 初始化 =====
    async def setup(self):
        """符卡开始前的准备（可选）"""
        await self.boss.move_to(0, 0.5, duration=60)
    
    # ===== 主逻辑 =====
    async def run(self):
        """弹幕主循环"""
        while True:
            # 发弹
            self.fire_circle(count=20, speed=2.5, color="blue")
            # 等待
            await self.wait(30)


# 注册
spellcard = MySpellCard
```

### 5.2 在 `run()` 中可用的 API

#### 发弹

| 方法 | 说明 | 示例 |
|------|------|------|
| `self.fire(...)` | 发射单发子弹 | `self.fire(angle=90, speed=2.0, color="red")` |
| `self.fire_circle(...)` | 发射圆形弹幕 | `self.fire_circle(count=20, speed=2.5)` |
| `self.fire_arc(...)` | 发射扇形弹幕 | `self.fire_arc(count=5, center_angle=-90, arc_angle=60)` |
| `self.fire_at_player(...)` | 发射自机狙 | `self.fire_at_player(speed=3.0)` |
| `self.clear_bullets()` | 清除此符卡的所有子弹 | `self.clear_bullets(to_items=True)` |

#### 时间控制

| 方法 | 说明 | 示例 |
|------|------|------|
| `await self.wait(frames)` | 等待 N 帧 | `await self.wait(30)` |
| `await self.wait_seconds(sec)` | 等待 N 秒 | `await self.wait_seconds(1.5)` |
| `await self.wait_until(cond)` | 等待条件满足 | `await self.wait_until(lambda: self.time > 300)` |
| `self.time` | 当前帧数 | `if self.time % 60 == 0:` |
| `self.time_seconds` | 当前秒数 | `if self.time_seconds > 15:` |
| `self.time_remaining` | 剩余秒数 | `if self.time_remaining < 10:` |

#### Boss 操作

| 方法 | 说明 | 示例 |
|------|------|------|
| `self.boss.x`, `self.boss.y` | Boss 当前位置 | `x = self.boss.x` |
| `await self.boss.move_to(x, y, duration)` | 平滑移动 Boss | `await self.boss.move_to(0.3, 0.5, 60)` |
| `self.boss.move_to_instant(x, y)` | 瞬移 Boss | `self.boss.move_to_instant(0, 0.5)` |

#### 音效

| 方法 | 说明 |
|------|------|
| `self.play_se(name)` | 播放音效（Stage私有优先，fallback全局） |
| `self.play_se(name, volume=0.5)` | 指定音量播放音效 |

#### 辅助

| 方法 | 说明 |
|------|------|
| `self.angle_to_player()` | 计算到玩家的角度（度） |
| `self.ctx.get_player()` | 获取玩家位置（`.x`, `.y`） |

### 5.3 弹幕设计技巧

#### 分阶段难度递增

```python
async def run(self):
    angle = 0
    while True:
        # 基础弹幕
        self.fire_circle(count=16, speed=2.0, start_angle=angle, color="blue")
        
        # 15秒后增加自机狙
        if self.time_seconds > 15:
            self.fire_at_player(speed=3.0, color="red")
        
        # 30秒后增加螺旋臂
        if self.time_seconds > 30:
            for arm in range(4):
                self.fire(angle=angle + arm * 90, speed=1.5, color="purple")
        
        angle += 7
        await self.wait(10)
```

#### Boss 边移动边发弹

```python
async def run(self):
    while True:
        # 随机目标位置
        target_x = random.uniform(-0.5, 0.5)
        target_y = random.uniform(0.3, 0.7)
        
        # 同时移动和发弹
        move_gen = self.boss.move_to(target_x, target_y, duration=90)
        for _ in range(90):
            try:
                next(move_gen)  # 推进移动
            except StopIteration:
                pass
            
            # 每 6 帧发一轮
            if self.time % 6 == 0:
                self.fire_at_player(speed=2.5, color="red")
            
            yield  # ← 注意：并行操作时用 yield 而不是 await
        
        await self.wait(30)
```

#### 抽取辅助方法

```python
class MySpell(SpellCard):
    async def run(self):
        while True:
            await self._wave_attack()
            await self.wait(30)
            await self._spiral_attack()
            await self.wait(30)
    
    async def _wave_attack(self):
        """波浪攻击"""
        for wave in range(5):
            self.fire_circle(
                count=20 + wave * 4,
                speed=1.5 + wave * 0.2,
                start_angle=wave * 7,
                color="blue"
            )
            await self.wait(6)
    
    async def _spiral_attack(self):
        """螺旋攻击"""
        for step in range(60):
            for arm in range(3):
                self.fire(
                    angle=step * 13 + arm * 120,
                    speed=2.0,
                    color="purple"
                )
            await self.wait(2)
```

---

## 6. 编写波次（Wave）

### 6.1 基本模板

```python
"""
波次描述
"""
from src.game.stage.wave_base import Wave


class MyWave(Wave):
    async def run(self):
        # 3波弹幕
        for wave_num in range(3):
            for i in range(8):
                x = -0.7 + i * 0.2
                self.fire(
                    x=x, y=0.9,
                    angle=-90, speed=1.8,
                    bullet_type="rice", color="blue"
                )
            await self.wait(30)
        
        # 等待子弹飞出
        await self.wait(60)


# 注册
wave = MyWave
```

### 6.2 Wave 可用 API

和 SpellCard 类似，但没有 `self.boss`：

| 方法 | 说明 |
|------|------|
| `self.fire(x, y, angle, speed, ...)` | 发射（必须指定 x, y） |
| `self.fire_circle(x, y, count, ...)` | 圆形弹幕 |
| `self.fire_arc(x, y, count, ...)` | 扇形弹幕 |
| `self.fire_at_player(x, y, speed, ...)` | 自机狙 |
| `await self.wait(frames)` | 等待 |
| `self.play_se(name)` | 播放音效 |
| `self.time` / `self.time_seconds` | 当前时间 |

### 6.3 兼容旧版函数风格

如果你觉得类太重，也可以用函数风格（但不推荐用于复杂波次）：

```python
def run(ctx):
    """旧版函数风格，直接操作 ctx"""
    for i in range(8):
        ctx.create_bullet(x=-0.7 + i*0.2, y=0.9, angle=-90, speed=1.8,
                          bullet_type="rice", color="blue")
    for _ in range(60):
        yield
```

---

## 7. 编写敌人脚本（EnemyScript）

### 7.1 基本模板

```python
"""
红色妖精 - 飞入 → 射弹 → 飞走
"""
from src.game.stage.enemy_script import EnemyScript


class RedFairy(EnemyScript):
    hp = 30
    sprite = "enemy_fairy_red"
    score = 100
    
    async def run(self):
        # 飞到 y=0.3
        await self.move_to(self.x, 0.3, duration=60)
        
        # 发射 3 轮 8-way 弹幕
        for _ in range(3):
            self.fire_circle(count=8, speed=2.0, color="red")
            await self.wait(20)
        
        # 飞出屏幕
        await self.move_to(self.x, -0.2, duration=60)
```

### 7.2 EnemyScript 可用 API

#### 移动

| 方法 | 说明 |
|------|------|
| `await self.move_to(x, y, duration)` | 平滑移动（smoothstep） |
| `await self.move_linear(dx, dy, duration)` | 匀速直线移动 |
| `self.set_position(x, y)` | 瞬移 |
| `self.x`, `self.y` | 当前位置 |

#### 发弹

和 SpellCard 完全相同：`self.fire()`, `self.fire_circle()`, `self.fire_at_player()` 等。  
默认从自身位置发射。

---

## 8. 编写 Boss 配置

Boss 用 JSON 配置，定义其符卡序列：

```json
{
  "id": "rumia_boss",
  "name": "ルーミア",
  "texture": "enemy_rumia",
  "animations": {},

  "phases": [
    {
      "type": "nonspell",
      "hp": 800,
      "time": 30,
      "script": "nonspell_1",
      "bonus": 100000,
      "comment": "第1段非符"
    },
    {
      "type": "spellcard",
      "hp": 1200,
      "time": 60,
      "script": "spell_1",
      "name": "月符「Moonlight Ray」",
      "bonus": 1000000,
      "practice_unlock": true,
      "comment": "第1张符卡"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `"nonspell"` / `"spellcard"` | 非符 / 符卡 |
| `hp` | int | 此阶段 Boss 的 HP |
| `time` | int | 时间限制（秒） |
| `script` | string | 脚本文件名（不含 `.py`，在 `spellcards/` 目录下找） |
| `name` | string | 符卡名称（符卡宣言时显示） |
| `bonus` | int | 满血击破奖励 |
| `practice_unlock` | bool | 是否可在练习模式选择 |

---

## 9. 编写关卡配置（stage.json）

`stage.json` 定义关卡的**时间线**——按顺序执行各段落：

```json
{
  "id": "stage1",
  "name": "Stage 1",
  "title": "赤より紅い夢",
  "subtitle": "A Dream More Scarlet than Red",

  "bgm": "stage1.ogg",
  "boss_bgm": "boss1.ogg",
  "background": "stage1_bg",

  "sections": [
    { "type": "wave",     "script": "waves/opening_wave"      },
    { "type": "wait",     "duration": 120                      },
    { "type": "wave",     "script": "waves/fairy_wave"         },
    { "type": "wait",     "duration": 60                       },
    { "type": "midboss",  "boss": "bosses/midboss"             },
    { "type": "wave",     "script": "waves/post_midboss_wave"  },
    { "type": "dialogue", "script": "dialogue/pre_boss"        },
    { "type": "boss",     "boss": "bosses/boss"                }
  ]
}
```

### Section 类型

| type | 说明 | 重要字段 |
|------|------|----------|
| `wave` | 道中波次 | `script`: 波次脚本路径（相对于 stage 目录，不含 `.py`） |
| `wait` | 等待 | `duration`: 帧数（60 = 1秒） |
| `midboss` | 道中 Boss | `boss`: Boss 配置路径（不含 `.json`） |
| `boss` | 关底 Boss | `boss`: 同上。会切换到 boss_bgm |
| `dialogue` | 对话 | `script`: 对话脚本路径 |

---

## 10. 弹幕 API 参考

### `self.fire(...)` - 发射单发子弹

```python
self.fire(
    x=0, y=0.5,           # 位置（SpellCard 默认为 Boss 位置）
    angle=-90,             # 角度（度，0=右，90=上，-90=下）
    speed=2.0,             # 速度
    bullet_type="ball_m",  # 弹幕类型
    color="red",           # 颜色
    accel=0,               # 加速度
    angle_accel=0,         # 角速度（曲线弹）
)
```

### 弹幕类型（bullet_type）

| 类型 | 说明 | 大小 |
|------|------|------|
| `"ball_s"` | 小弹 | 小 |
| `"ball_m"` | 中弹 | 中 |
| `"ball_l"` | 大弹 | 大 |
| `"rice"` | 米弹 | 细长 |
| `"scale"` | 鳞弹 | 中 |
| `"arrowhead"` | 箭头弹 | 中 |
| `"knife"` | 刀弹 | 细长 |
| `"star_s"` | 小星弹 | 小 |
| `"star_m"` | 中星弹 | 中 |
| `"needle"` | 针弹 | 细 |
| `"oval"` | 椭圆弹 | 中 |
| `"bullet"` | 普通弹 | 小 |

### 颜色（color）

| 颜色 | 值 |
|------|-----|
| `"red"` | 红色 |
| `"blue"` | 蓝色 |
| `"green"` | 绿色 |
| `"yellow"` | 黄色 |
| `"purple"` | 紫色 |
| `"white"` | 白色 |
| `"darkblue"` | 深蓝色 |
| `"orange"` | 橙色 |
| `"cyan"` | 青色 |
| `"pink"` | 粉色 |

---

## 11. 坐标系统

pystg 使用**归一化坐标**：

```
         y = 1.0 (屏幕上方)
            ┌──────────┐
            │          │
  x = -1.0  │  (0,0)   │  x = 1.0
            │  中心     │
            │          │
            └──────────┘
         y = -1.0 (屏幕下方)
```

- **x 范围**：约 -1.0 ~ 1.0（实际游戏区域可能更窄）
- **y 范围**：约 -1.0 ~ 1.0
- **(0, 0)** 是屏幕中心
- Boss 通常在 y = 0.3 ~ 0.7 的区域
- 玩家通常在 y = -0.5 ~ -0.8 的区域

### 角度系统

```
           90° (上)
            ↑
  180° ←────┼────→ 0° (右)
            ↓
          -90° (下)
```

- **0°** = 向右
- **90°** = 向上  
- **-90°** = 向下（最常用 - 子弹向下飞向玩家）
- **180°** = 向左

---

## 12. 完整示例：Stage 1 逐文件解析

### 12.1 stage.json - 时间线

```
开场波次 → 等2秒 → 妖精编队 → 等1秒 → 道中Boss → 收尾波次 → 对话 → 关底Boss
```

对应 `game_content/stages/stage1/stage.json`。

### 12.2 waves/opening_wave.py - 开场波次

```python
from src.game.stage.wave_base import Wave

class OpeningWave(Wave):
    async def run(self):
        # 3波，每波8列米弹从上方落下
        for wave_num in range(3):
            for i in range(8):
                x = -0.7 + i * 0.2
                self.fire(x=x, y=0.9, angle=-90, speed=1.8,
                          bullet_type="rice", color="blue")
            await self.wait(30)
        await self.wait(60)

wave = OpeningWave
```

**设计**：最简单的波次。8 列蓝色米弹整齐下落，给玩家"战斗开始"的信号。

### 12.3 spellcards/nonspell_1.py - 第一段非符

```python
from src.game.stage.spellcard import NonSpell

class NonSpell1(NonSpell):
    hp = 800
    time_limit = 30
    
    async def setup(self):
        await self.boss.move_to(0, 0.5, duration=30)
    
    async def run(self):
        angle = 0
        while True:
            # 16-way 红色旋转圆弹
            self.fire_circle(count=16, speed=2.0, start_angle=angle,
                             bullet_type="ball_m", color="red")
            angle += 15
            await self.wait(20)
            
            # 间歇自机狙
            if self.time % 120 < 60:
                self.fire_at_player(speed=2.5, bullet_type="rice", color="white")
            await self.wait(10)

spellcard = NonSpell1
```

**设计**：
- 旋转圆弹是基本盘（rhythm），玩家可以在间隙中穿梭
- 自机狙增加变化，迫使玩家微调走位
- `angle += 15` 让弹幕每次旋转，避免固定安全位

### 12.4 spellcards/spell_1.py - 月符

分三层：圆形扩散 → 自机狙射线 → 15秒后加入螺旋弹幕。  
展示了**分阶段设计**：前半段热身，后半段加压。

### 12.5 spellcards/spell_2.py - 夜符

展示了：
- **Boss 随机移动** + 边移动边射弹
- **抽取辅助方法** (`_fire_bird_pattern`, `_fire_wave_attack`)
- **V字形弹幕**的实现

### 12.6 bosses/boss.json - 关底 Boss 配置

```json
{
  "phases": [
    { "type": "nonspell", "script": "nonspell_1", "hp": 800,  "time": 30 },
    { "type": "spellcard", "script": "spell_1",   "hp": 1200, "time": 60, "name": "月符「Moonlight Ray」" },
    { "type": "spellcard", "script": "spell_2",   "hp": 1500, "time": 60, "name": "夜符「Night Bird」" }
  ]
}
```

Boss 按顺序执行：非符1 → 月符 → 夜符。每段结束后自动进入下一段。

---

## 13. 常见问题

### Q: `await` 和 `yield` 应该用哪个？

**统一使用 `await`**（推荐）：

```python
async def run(self):
    await self.wait(30)          # ✅
    await self.boss.move_to(...) # ✅
```

特殊情况（并行操作）才需要 `yield`：

```python
# 同时移动 Boss 和发弹
move_gen = self.boss.move_to(0.3, 0.5, 60)
for _ in range(60):
    try:
        next(move_gen)
    except StopIteration:
        pass
    self.fire_at_player(speed=2.0)
    yield  # ← 这里必须用 yield
```

### Q: 怎么让弹幕变成白色道具？

```python
self.clear_bullets(to_items=True)
```

通常在 `on_timeout` 或 `on_defeated` 中使用。

### Q: 怎么获取玩家位置？

```python
player = self.ctx.get_player()
px, py = player.x, player.y
```

或者：

```python
angle = self.angle_to_player()  # 计算到玩家的角度
```

### Q: 怎么发射"曲线弹"？

```python
self.fire(
    angle=0, speed=2.0,
    angle_accel=2.0,   # 每帧旋转 2 度 → 螺旋弹
    color="purple"
)
```

### Q: 一个波次脚本可以不用类吗？

可以，用函数风格：

```python
def run(ctx):
    for i in range(8):
        ctx.create_bullet(x=i*0.2, y=0.9, angle=-90, speed=2.0,
                          bullet_type="rice", color="blue")
    for _ in range(60):
        yield
```

但推荐用 `Wave` 类，因为有更多 API 可用。

### Q: 我新增了一个 stage，怎么让游戏加载它？

1. 在 `game_content/stages/stageN/` 创建完整目录结构
2. 在 `levels/` 中创建一个加载脚本（参考 `stage1_level.py`）
3. 在 `main.py` 中切换关卡

---

## 14. 从零创建一个新关卡

### 步骤 1：创建目录

```
game_content/stages/stage2/
├── __init__.py
├── stage.json
├── waves/
│   └── __init__.py
├── bosses/
├── spellcards/
│   └── __init__.py
├── enemies/
│   └── __init__.py
└── dialogue/
```

### 步骤 2：编写 stage.json

```json
{
  "id": "stage2",
  "name": "Stage 2",
  "title": "你的关卡标题",
  "bgm": "stage2.ogg",
  "boss_bgm": "boss2.ogg",
  "background": "stage2_bg",
  "sections": [
    { "type": "wave", "script": "waves/opening_wave" },
    { "type": "wait", "duration": 120 },
    { "type": "boss", "boss": "bosses/boss" }
  ]
}
```

### 步骤 3：编写波次脚本

`waves/opening_wave.py`：

```python
from src.game.stage.wave_base import Wave

class OpeningWave(Wave):
    async def run(self):
        # 你的波次逻辑
        for _ in range(5):
            self.fire_circle(x=0, y=0.9, count=12, speed=2.0, color="green")
            await self.wait(20)
        await self.wait(60)

wave = OpeningWave
```

### 步骤 4：编写符卡

`spellcards/nonspell_1.py`：

```python
from src.game.stage.spellcard import NonSpell

class NonSpell1(NonSpell):
    hp = 600
    time_limit = 25
    
    async def setup(self):
        await self.boss.move_to(0, 0.5, duration=30)
    
    async def run(self):
        while True:
            self.fire_circle(count=8, speed=2.0, color="blue")
            await self.wait(20)

spellcard = NonSpell1
```

### 步骤 5：编写 Boss 配置

`bosses/boss.json`：

```json
{
  "id": "stage2_boss",
  "name": "Boss 名",
  "texture": "enemy_boss",
  "phases": [
    {
      "type": "nonspell",
      "hp": 600,
      "time": 25,
      "script": "nonspell_1"
    }
  ]
}
```

### 步骤 6：创建加载脚本

`levels/stage2_level.py`：

```python
from typing import Generator
from src.game.stage.context import StageContext
from src.game.stage.stage_base import StageBase

def stage2_level(stage_manager, bullet_pool, player) -> Generator:
    ctx = StageContext(
        bullet_pool=bullet_pool,
        player=player,
        enemy_manager=stage_manager.enemy_manager
    )
    stage = StageBase.from_config("game_content/stages/stage2/stage.json", ctx)
    stage.start()
    
    while stage._active:
        stage.update()
        yield
    
    bullet_pool.clear_all()
    for _ in range(120):
        yield
```

完成！运行游戏即可看到你的新关卡。

---

## 15. 音频系统

pystg 采用**两级音频管理**：

```
┌────────────────────────────────────────────┐
│            AudioManager（统一调度）            │
│                                              │
│  查找顺序： Stage私有 → Game全局 → 警告缺失  │
└─────────────┬────────────────┬─────────────┘
              │                │
    ┌────────┴───────┐  ┌─────┴─────────┐
    │ GameAudioBank    │  │ StageAudioBank  │
    │ （全局，始终存在） │  │ （关卡私有，可选）│
    │                  │  │                 │
    │ shoot, graze,    │  │ 可覆盖全局同名 SE│
    │ pldead, bomb...  │  │ 关卡专属 BGM    │
    └──────────────────┘  └─────────────────┘
```

### 15.1 内容作者需要知道的

**你不需要直接操作音频系统。** 基类已经提供了便捷方法：

```python
# 在 SpellCard / Wave / EnemyScript 中
self.play_se("shoot")            # 播放音效
self.play_se("explode", volume=0.7)  # 指定音量

# 通过 ctx 播放 BGM
self.ctx.play_bgm("boss1")       # 播放 BGM
self.ctx.stop_bgm(fade_ms=1000)  # 淡出停止
```

### 15.2 全局音效（GameAudioBank）

全局音效由引擎在启动时加载，文件在 `assets/audio/se/` 目录下。
所有内容脚本均可直接使用以下名称：

| 名称 | 说明 | 对应文件 |
|------|------|----------|
| `"shoot"` | 自机射击 | se_plst00.wav |
| `"graze"` | 擦弹 | se_graze.wav |
| `"pldead"` | 自机死亡 | se_pldead00.wav |
| `"extend"` | 续命 | se_extend.wav |
| `"powerup"` | 满P | se_powerup.wav |
| `"bomb"` | Bomb | se_nep00.wav |
| `"pause"` | 暂停 | se_pause.wav |
| `"select"` | 菜单选择 | se_select00.wav |
| `"cancel"` | 菜单取消 | se_cancel00.wav |
| `"ok"` | 菜单确认 | se_ok00.wav |
| `"cardget"` | 符卡取得 | se_cardget.wav |
| `"timeout"` | 超时 | se_timeout.wav |
| `"item"` | 道具回收 | se_item00.wav |
| `"damage"` | 敌人受伤 | se_damage00.wav |
| `"explode"` | 敌人爆炸 | se_explode.wav |
| `"kira"` | 星星音效 | se_kira00.wav |
| `"lazer"` | 激光 | se_lazer00.wav |
| `"bonus"` | 奖励 | se_bonus.wav |
| `"warning"` | 警告 | se_hyz_warning.wav |
| `"charge"` | 蓄力 | se_hyz_charge00.wav |

### 15.3 关卡私有音频（StageAudioBank）

每个关卡可以有自己的专属音频，放在关卡目录的 `audio/` 子目录下：

```
game_content/stages/stage1/
  audio/
    se/                    ← 关卡专属音效
    │  se_custom_shot.wav  ← 文件名去掉 se_ 前缀和 .wav 后缀 → 名称为 "custom_shot"
    │  se_boss_roar.wav    → 名称为 "boss_roar"
    │
    music/                 ← 关卡专属 BGM
       stage1_road.ogg     → 名称为 "stage1_road"
       boss1.ogg           → 名称为 "boss1"
```

**命名规则：**
- SE 文件名 `se_xxx.wav` 自动去掉 `se_` 前缀 → 音效名为 `"xxx"`
- BGM 文件名去掉扩展名即为 BGM 名称
- 支持格式：`.wav`（SE）、`.ogg` / `.mp3` / `.wav`（BGM）

**覆盖机制：** 如果关卡私有 SE 和全局 SE 同名，则关卡私有优先。例如关卡 `audio/se/se_shoot.wav` 会覆盖全局的 `"shoot"` 音效。

### 15.4 在脚本中使用音频

#### SpellCard / NonSpell 中

```python
class MySpell(SpellCard):
    async def setup(self):
        self.play_se("warning")       # 符卡开始时播放警告音
        await self.boss.move_to(0, 0.5, duration=60)
    
    async def run(self):
        while True:
            self.fire_circle(count=20, speed=2.5, color="red")
            self.play_se("shoot")     # 每次发弹播放射击音
            await self.wait(15)
    
    async def on_defeated(self):
        self.clear_bullets(to_items=True)
        self.play_se("explode")       # Boss 被击败时爆炸音
```

#### Wave 中

```python
class MyWave(Wave):
    async def run(self):
        self.play_se("warning")       # 波次开始提示
        await self.wait(60)
        
        for _ in range(5):
            self.fire_circle(x=0, y=0.9, count=12, speed=2.0)
            self.play_se("shoot")
            await self.wait(20)
```

#### EnemyScript 中

```python
class BigFairy(EnemyScript):
    hp = 100
    
    async def run(self):
        await self.move_to(self.x, 0.3, duration=60)
        self.play_se("charge")        # 蓄力音
        await self.wait(60)
        self.fire_circle(count=24, speed=3.0, color="purple")
        self.play_se("lazer")         # 发射音
```

#### 通过 ctx 控制 BGM

```python
# 在 Wave 或 SpellCard 中直接通过 ctx
self.ctx.play_bgm("boss1")               # 播放 BGM
self.ctx.play_bgm("boss1", fade_ms=2000) # 2秒淡入
self.ctx.stop_bgm(fade_ms=1000)          # 1秒淡出停止
self.ctx.pause_bgm()                     # 暂停
self.ctx.unpause_bgm()                   # 恢复
```

> **注意：** 通常不需要手动控制 BGM。`stage.json` 中配置的 `bgm` 和 `boss_bgm` 会由引擎自动在合适的时机播放。只有在需要特殊音频控制（如符卡中间切换 BGM、对话期间降低音量等）时才需要手动调用。

### 15.5 为新关卡添加音频

1. 在关卡目录下创建 `audio/se/` 和 `audio/music/` 目录
2. 将 SE 文件（`.wav`）放入 `audio/se/`，文件名以 `se_` 开头
3. 将 BGM 文件（`.ogg`/`.mp3`）放入 `audio/music/`
4. 在加载脚本（`levels/stageN_level.py`）中初始化 StageAudioBank：

```python
from src.game.audio import StageAudioBank

def stageN_level(stage_manager, bullet_pool, player, audio_manager=None):
    # 加载关卡私有音频
    stage_bank = StageAudioBank.from_directory("stageN", "game_content/stages/stageN")
    if audio_manager:
        audio_manager.set_stage_bank(stage_bank)
    
    ctx = StageContext(
        bullet_pool=bullet_pool,
        player=player,
        enemy_manager=stage_manager.enemy_manager,
        audio_manager=audio_manager
    )
    # ... 其余逻辑
    
    # 关卡结束时清理
    if audio_manager:
        audio_manager.set_stage_bank(None)
```

5. 完成！脚本中就可以通过 `self.play_se("xxx")` 使用新音效了。

---

## 附录：文件分层一览

```
你需要关心的（内容层）：
  game_content/stages/stageN/
    ├── stage.json          ← 时间线
    ├── waves/*.py          ← 道中弹幕
    ├── spellcards/*.py     ← 符卡脚本
    ├── bosses/*.json       ← Boss 符卡序列
    ├── enemies/*.py        ← 敌人脚本
    ├── dialogue/*.py       ← 对话
    └── audio/              ← 关卡私有音频（可选）
        ├── se/*.wav        ← 关卡音效
        └── music/*.ogg     ← 关卡 BGM

你不需要关心的（引擎层）：
  src/game/stage/
    ├── spellcard.py        ← SpellCard/NonSpell 基类
    ├── wave_base.py        ← Wave 基类
    ├── enemy_script.py     ← EnemyScript 基类
    ├── boss_base.py        ← BossBase（从 JSON 加载）
    ├── stage_base.py       ← StageBase（从 JSON 加载）
    ├── context.py          ← StageContext（引擎桥梁）
    └── practice.py         ← 练习模式
  
  src/game/audio.py           ← 音频系统（AudioBank / AudioManager）
  src/game/bullet/            ← 子弹池（引擎内部）
  src/game/player/            ← 玩家系统（引擎内部）
  src/render/                 ← 渲染系统（引擎内部）
```
