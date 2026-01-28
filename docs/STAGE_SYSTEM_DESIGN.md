# 关卡与弹幕脚本系统设计

## 核心设计原则

1. **符卡是最小可复用单元** - 每张符卡独立，可单独练习
2. **Boss 是符卡的容器** - 定义符卡顺序和切换逻辑
3. **Stage 是道中+Boss 的组合** - 组织完整关卡流程
4. **脚本使用协程** - 用 async/await 或 generator 描述时序逻辑

## 文件结构

```
game_content/
├── stages/
│   ├── stage1/
│   │   ├── stage.json           # Stage 元数据
│   │   ├── midboss.json         # 道中 Boss 配置（可选）
│   │   ├── boss.json            # 关底 Boss 配置
│   │   ├── stage_script.py      # 道中脚本（敌人波次）
│   │   └── spellcards/
│   │       ├── __init__.py
│   │       ├── nonspell_1.py    # 非符1
│   │       ├── spell_1.py       # 符卡1
│   │       ├── spell_2.py       # 符卡2
│   │       └── ...
│   ├── stage2/
│   │   └── ...
│   └── extra/
│       └── ...
│
├── shared/                      # 共享资源
│   ├── patterns/                # 通用弹幕模式
│   │   ├── circle.py
│   │   ├── spiral.py
│   │   └── ...
│   └── enemies/                 # 通用敌人行为
│       ├── fairy.py
│       └── ...
│
└── practice/                    # 练习模式入口
    └── spellcard_list.json      # 所有可练习符卡索引
```

## 配置文件格式

### stage.json
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
    {"type": "wave", "script": "wave_1"},
    {"type": "wave", "script": "wave_2"},
    {"type": "midboss", "boss": "midboss"},
    {"type": "wave", "script": "wave_3"},
    {"type": "boss", "boss": "boss"}
  ]
}
```

### boss.json
```json
{
  "id": "rumia",
  "name": "露米娅",
  "texture": "rumia.png",
  "phases": [
    {
      "type": "nonspell",
      "hp": 800,
      "time": 30,
      "script": "nonspell_1"
    },
    {
      "type": "spellcard",
      "name": "月符「Moonlight Ray」",
      "hp": 1200,
      "time": 60,
      "script": "spell_1",
      "bonus": 1000000,
      "practice_unlock": true
    },
    {
      "type": "nonspell", 
      "hp": 1000,
      "time": 30,
      "script": "nonspell_2"
    },
    {
      "type": "spellcard",
      "name": "夜符「Night Bird」",
      "hp": 1500,
      "time": 60,
      "script": "spell_2",
      "bonus": 1500000,
      "practice_unlock": true
    }
  ]
}
```

## 符卡脚本格式

```python
# spellcards/spell_1.py
"""
月符「Moonlight Ray」
"""
from src.game.danmaku import SpellCard, BulletPattern

class MoonlightRay(SpellCard):
    """符卡类 - 继承 SpellCard 基类"""
    
    # 元数据（可被 boss.json 覆盖）
    name = "月符「Moonlight Ray」"
    hp = 1200
    time_limit = 60
    
    async def setup(self):
        """符卡开始时调用（Boss移动到位置等）"""
        await self.boss.move_to(0, 0.5, duration=60)
    
    async def run(self):
        """主弹幕循环"""
        while True:
            # 发射圆形弹幕
            for i in range(36):
                angle = i * 10 + self.time * 2
                self.fire(
                    x=self.boss.x, y=self.boss.y,
                    angle=angle,
                    speed=2.5,
                    bullet_type="ball_m",
                    color="blue"
                )
            await self.wait(8)  # 等待8帧
            
            # 发射螺旋弹幕
            for j in range(5):
                for i in range(12):
                    angle = i * 30 + j * 6 + self.time
                    self.fire(
                        angle=angle,
                        speed=1.5 + j * 0.3,
                        bullet_type="rice",
                        color="red"
                    )
                await self.wait(3)
            
            await self.wait(30)
    
    async def on_timeout(self):
        """时间结束时调用"""
        self.clear_bullets()
    
    async def on_defeated(self):
        """被击败时调用"""
        self.clear_bullets()
        await self.boss.play_defeat_animation()


# 注册符卡（用于动态加载）
spellcard = MoonlightRay
```

## 练习模式实现

### 方式1：单符卡练习
```python
from src.game.stage import SpellCardPractice

# 从脚本路径加载
practice = SpellCardPractice.from_path(
    "game_content/stages/stage1/spellcards/spell_1.py"
)
practice.start(game_context)

# 游戏循环
while practice.update():
    # 渲染等...
    pass

# 获取结果
result = practice.get_result()
print(f"击破: {result.success}, 用时: {result.time_used:.1f}s")
```

### 方式2：使用练习管理器
```python
from src.game.stage import PracticeManager

# 初始化
manager = PracticeManager("game_content/stages")
manager.load()

# 获取所有可练习符卡
entries = manager.get_all_entries()
for entry in entries:
    print(f"{entry.stage_name} - {entry.display_name}")

# 按关卡分组显示（用于UI）
by_stage = manager.get_entries_by_stage()
for stage_id, spells in by_stage.items():
    print(f"\n{stage_id}:")
    for spell in spells:
        print(f"  - {spell.display_name}")

# 开始练习某张符卡
boss = manager.start_practice(entries[0], game_context)
```

### 方式3：Boss 连续练习
```python
# 连续挑战一个 Boss 的所有符卡
boss = manager.start_boss_practice("stage1", "rumia", game_context)
```

## 关键类设计

```
┌─────────────┐
│   Game      │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│   Stage     │────▶│  StageScript│  (道中脚本)
└──────┬──────┘     └─────────────┘
       │
       ▼
┌─────────────┐
│    Boss     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  SpellCard  │  ◀── 最小可复用单元
└─────────────┘
```

## 实际文件示例

### game_content/stages/stage1/stage.json
```json
{
  "id": "stage1",
  "name": "Stage 1",
  "title": "赤より紅い夢",
  "bgm": "stage1.ogg",
  "boss_bgm": "boss1.ogg",
  "sections": [
    {"type": "wave", "script": "wave_1"},
    {"type": "midboss", "boss": "midboss"},
    {"type": "wave", "script": "wave_2"},
    {"type": "boss", "boss": "boss"}
  ]
}
```

### game_content/stages/stage1/boss.json
```json
{
  "id": "rumia",
  "name": "露米娅",
  "texture": "rumia.png",
  "phases": [
    {"type": "nonspell", "hp": 800, "time": 30, "script": "nonspell_1"},
    {"type": "spellcard", "name": "月符「Moonlight Ray」", "hp": 1200, "time": 60, "script": "spell_1", "bonus": 1000000, "practice_unlock": true},
    {"type": "spellcard", "name": "夜符「Night Bird」", "hp": 1500, "time": 60, "script": "spell_2", "bonus": 1500000, "practice_unlock": true}
  ]
}
```

## 设计优势

1. **符卡独立** - 每张符卡是独立文件，便于：
   - 单独测试和调试
   - 练习模式直接加载
   - 多人协作（不同人写不同符卡）

2. **配置分离** - JSON 配置和 Python 逻辑分开：
   - 修改血量/时间无需改代码
   - 非程序员可调整数值

3. **协程风格** - 用 `async/await` 写弹幕逻辑：
   - 时序清晰（await wait）
   - 易于理解和维护
   - 支持复杂的多阶段模式

4. **练习模式原生支持** - 设计时就考虑练习：
   - `practice_unlock` 标记可练习符卡
   - `PracticeManager` 自动扫描
   - 支持单符/Boss连续/关卡练习
