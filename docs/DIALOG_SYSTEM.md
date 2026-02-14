# 对话系统实现文档

## 概述

完整参照 LuaSTG 的对话系统实现，支持：
- ✅ 角色立绘显示（淡入淡出动画）
- ✅ 对话气泡（8种样式）
- ✅ 文本打字机效果
- ✅ 对话管理和流程控制
- ✅ 跳过和快进功能

## 文件结构

```
src/game/stage/
├── dialog_data.py          # 对话数据结构（DialogSentence, DialogSequence）
├── dialog_manager.py       # 对话管理器（DialogManager）
└── dialog_renderer.py      # 渲染器（PortraitRenderer, BalloonRenderer）

assets/
├── images/
│   ├── character/          # 角色立绘
│   │   ├── Hinanawi_Tenshi/
│   │   │   ├── normal.png
│   │   │   └── character.json
│   │   └── Reiuji_Utsuho/
│   │       ├── normal.png
│   │       └── character.json
│   └── ui/
│       ├── dialog_box.png         # 对话框背景
│       ├── dialog_box.json
│       ├── dialog_balloon.png     # 气泡纹理（8种样式）
│       └── dialog_balloon.json
└── fonts/
    ├── wqy-microhei-mono.ttf      # 气泡字体
    └── SourceHanSansCN-Bold.otf   # 对话字体

game_content/stages/stage1/dialogue/
└── boss_dialogue.py        # Stage 1 Boss 对话
```

## 使用方法

### 1. 定义对话数据

```python
from src.game.stage.dialog_data import DialogSequence, DialogSentence

# 创建对话序列
dialogue = DialogSequence(
    sentences=[
        DialogSentence(
            text="你好！我是天子！",
            character="Hinanawi_Tenshi",
            portrait="normal",
            position="left",
            balloon_style=1
        ),
        DialogSentence(
            text="哼，我是空！",
            character="Reiuji_Utsuho",
            portrait="normal",
            position="right",
            balloon_style=2
        ),
    ],
    can_skip=True  # 是否可跳过
)
```

### 2. 在关卡中使用对话

```python
from src.game.stage.dialog_manager import play_dialog
from game_content.stages.stage1.dialogue.boss_dialogue import pre_boss_dialogue

class MyWave(Wave):
    async def run(self):
        # 播放对话
        await play_dialog(pre_boss_dialogue)

        # 对话结束后继续
        self.spawn_boss("boss_utsuho")
```

### 3. 使用对话管理器（高级）

```python
from src.game.stage.dialog_manager import DialogManager

# 创建管理器
manager = DialogManager(dialogue)

# 设置回调
def on_sentence_start(sentence):
    print(f"开始: {sentence.text}")

manager.on_sentence_start = on_sentence_start
manager.on_complete = lambda: print("对话结束")

# 启动对话
manager.start()

# 每帧更新
while manager.update():
    # 处理输入
    manager.handle_input(shoot_pressed=check_shoot_key())

    # 渲染（需要 DialogRenderer）
    # dialog_renderer.render(screen)
```

## 对话参数说明

### DialogSentence 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `text` | str | (必填) | 对话文本 |
| `character` | str | None | 角色ID（如 "Hinanawi_Tenshi"） |
| `portrait` | str | "normal" | 立绘key（表情/姿势） |
| `position` | str | "left" | 立绘位置（"left"/"right"） |
| `balloon_style` | int | 1 | 气泡样式（1-8） |
| `duration` | int | None | 显示时长（帧），None=自动计算 |
| `portrait_scale` | float | 1.0 | 立绘缩放倍数 |

### 气泡样式

- **样式 1-4**: 单行文本气泡
- **样式 5-8**: 多行文本气泡（2行）

### 时长计算

如果未指定 `duration`，按以下公式自动计算：
```python
duration = 60 + len(text) * 5  # 帧数
```

例如：10个字的对话 = 60 + 10×5 = 110帧 ≈ 1.8秒

## 角色配置

在 `assets/images/character/角色名/character.json`:

```json
{
  "__character_name": "Hinanawi Tenshi（比那名居 天子）",
  "portraits": {
    "normal": {
      "file": "Hinanawi_Tenshi/normal.png",
      "center": [0.5, 0.5],
      "scale": 1.0
    },
    "angry": {
      "file": "Hinanawi_Tenshi/angry.png",
      "center": [0.5, 0.5],
      "scale": 1.0
    }
  },
  "default_portrait": "normal",
  "default_position": "left"
}
```

## 渲染参数（参照 LuaSTG）

### 立绘动画

- **淡入**: 16帧，从对角移入
  - 左侧：从右上移入 (+32x, +16y)
  - 右侧：从左上移入 (-32x, +16y)
  - 透明度：sin²(t × π/2)

- **淡出**: 30帧，线性淡出

### 气泡动画

- **缩放**: 10帧，从0放大到1
- **组成**: 头部(26px) + 身体(16px×字符数) + 尾部(4px)
- **文字**: 黑色，16×32px，每3帧显示一个字符（打字机效果）

### 默认位置

```python
立绘位置:
  - 左侧: (80, 128)
  - 右侧: (380, 128)

气泡位置:
  - 左侧: (130, 230)
  - 右侧: (330, 230)
```

## 已测试角色

- **Hinanawi_Tenshi（比那名居 天子）** - 自机
- **Reiuji_Utsuho（灵乌路 空）** - Stage 1 Boss

参见: `game_content/stages/stage1/dialogue/boss_dialogue.py`

## 下一步工作

- [ ] 集成到 Stage 系统（在 Boss 战前自动播放对话）
- [ ] 实现气泡精灵加载和渲染（目前是简化版）
- [ ] 添加音效（对话出现、翻页音效）
- [ ] 支持更多立绘表情
- [ ] 对话选择分支（可选）

## 示例：完整的 Boss 战对话

```python
from src.game.stage.dialog_data import DialogSequence, DialogSentence

pre_boss_dialogue = DialogSequence(
    sentences=[
        DialogSentence(
            text="你就是掌握核融合力量的地狱鸦吗？",
            character="Hinanawi_Tenshi",
            portrait="normal",
            position="left",
            balloon_style=1
        ),
        DialogSentence(
            text="没错！我是灵乌路空！",
            character="Reiuji_Utsuho",
            portrait="normal",
            position="right",
            balloon_style=2
        ),
        DialogSentence(
            text="你这个天界的任性小姐，来地底做什么？",
            character="Reiuji_Utsuho",
            portrait="normal",
            position="right",
            balloon_style=3
        ),
        DialogSentence(
            text="当然是来修行的！正好拿你练练手！",
            character="Hinanawi_Tenshi",
            portrait="normal",
            position="left",
            balloon_style=2
        ),
        DialogSentence(
            text="哼哼，那就让你见识一下核融合的威力！",
            character="Reiuji_Utsuho",
            portrait="normal",
            position="right",
            balloon_style=4
        ),
    ],
    can_skip=True,
    auto_advance=True
)
```

## 技术细节

### 性能优化

- 立绘图片按需加载并缓存
- 气泡精灵复用渲染
- 避免每帧重新创建对象

