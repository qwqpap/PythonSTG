# 对话系统重构完成 

## 重大改进：面向过程 API

对话系统已重构为**面向过程**的简单 API，就像 `run_wave()` 和 `run_boss()` 一样简单！

## 新的使用方式

### 在 Stage 脚本中直接使用

```python
class Stage1(StageScript):
    async def run(self):
        # 波次
        await self.run_wave(OpeningWave)

        # Boss 战前对话 - 超级简单！
        await self.play_dialogue([
            ("Hinanawi_Tenshi", "left", "你就是掌握核融合力量的地狱鸦吗？"),
            ("Reiuji_Utsuho", "right", "没错！我是灵乌路空！"),
            ("Reiuji_Utsuho", "right", "你这个天界的任性小姐，来地底做什么？"),
            ("Hinanawi_Tenshi", "left", "当然是来修行的！正好拿你练练手！"),
            ("Reiuji_Utsuho", "right", "哼哼，那就让你见识一下核融合的威力！"),
        ])

        # Boss 战
        await self.run_boss(self.boss)

        # Boss 战后对话
        await self.play_dialogue([
            ("Reiuji_Utsuho", "right", "好...好强...！"),
            ("Hinanawi_Tenshi", "left", "这就是天界的实力！"),
        ])
```

### 对话格式

支持两种格式：

**简单格式**（推荐）:
```python
await self.play_dialogue([
    ("角色名", "位置", "文本"),
    ("角色名", "位置", "文本"),
])
```

**详细格式**（可选）:
```python
await self.play_dialogue([
    {
        "character": "Hinanawi_Tenshi",
        "position": "left",
        "text": "你好！",
        "balloon_style": 1  # 气泡样式 1-8
    },
])
```

## 对比：之前 vs 现在

### ❌ 之前（复杂）

```python
# 需要单独定义对话数据文件
# game_content/stages/stage1/dialogue/boss_dialogue.py
from src.game.stage.dialog_data import DialogSequence, DialogSentence

pre_boss_dialogue = DialogSequence(
    sentences=[
        DialogSentence(
            text="你好！",
            character="Hinanawi_Tenshi",
            portrait="normal",
            position="left",
            balloon_style=1
        ),
        # ...
    ],
    can_skip=True
)

# 然后在 stage_script.py 中导入
from game_content.stages.stage1.dialogue.boss_dialogue import pre_boss_dialogue
from src.game.stage.boss_base import dialog

boss = BossDef(
    phases=[
        dialog(pre_boss_dialogue),  # 诡异的符卡方式
        nonspell(...),
        spellcard(...),
    ]
)
```

### ✅ 现在（简单）

```python
# 直接在 run() 中写
async def run(self):
    await self.play_dialogue([
        ("Hinanawi_Tenshi", "left", "你好！"),
        ("Reiuji_Utsuho", "right", "哼！"),
    ])

    await self.run_boss(self.boss)
```

**简洁度对比**:
- 之前: ~30 行代码分散在 3 个文件
- 现在: 3 行代码直接写在流程中

## 如何显示到屏幕

对话文本渲染器已自动创建，只需在游戏渲染循环中添加：

```python
# 在主渲染循环中（main.py 或渲染器）
def render_stage(stage, screen):
    # ... 渲染游戏内容 ...

    # 渲染对话（如果有）
    dialog_renderer = stage.get_dialog_renderer()
    if dialog_renderer:
        dialog_renderer.render(screen)
```

### 集成位置示例

如果你有类似这样的渲染代码：

```python
# 渲染所有内容
stage.ctx.render_bullets(screen)
stage.ctx.render_players(screen)
stage.ctx.render_ui(screen)

# 👇 在最后添加对话渲染
dialog_renderer = stage.get_dialog_renderer()
if dialog_renderer:
    dialog_renderer.render(screen)
```

## 当前效果

### ✅ 已实现
- 简化的对话 API - 3 行代码搞定
- 自动管理对话状态
- 打字机效果（每3帧一个字符）
- 控制台输出
- 半透明对话框背景
- 角色名显示
- 自动换行

### ⚠️ 需要手动集成
在主渲染循环添加 4 行代码即可显示到屏幕

### 🎯 未来优化
- 气泡纹理渲染（8种样式）
- 立绘显示（淡入淡出）
- 输入处理（按键跳过）
- 音效系统

## 优势总结

1. **超级简单** - 像写剧本一样写对话
2. **流程清晰** - 对话、波次、Boss 战一目了然
3. **无需外部文件** - 不需要单独的对话数据文件
4. **易于修改** - 直接在关卡流程中调整对话
5. **自动管理** - 渲染器自动创建和清理

## 测试

运行游戏，Stage 1 Boss 战前会显示对话：
```
[对话] Hinanawi_Tenshi (left): 你就是掌握核融合力量的地狱鸦吗？
[对话] Reiuji_Utsuho (right): 没错！我是灵乌路空！
...
```

如果已经集成渲染，屏幕底部会显示带背景的对话框。

---

**现在对话系统变得非常简单！** 🎉

就像写剧本一样，直接在关卡流程中定义对话内容。
