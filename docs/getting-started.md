# 快速开始

## 环境要求

- Python 3.10+
- 支持 OpenGL 3.3+ 的显卡

## 安装依赖

```bash
pip install pygame-ce moderngl numpy numba pillow
```

编辑器工具额外需要：

```bash
pip install PyQt5
```

## 运行游戏

```bash
python main.py
```

## 项目结构

```
pystg/
├── main.py                  # 游戏入口
│
├── src/                     # 引擎代码（不要动，除非你在改引擎）
│   ├── core/                # 配置、碰撞检测、接口定义
│   ├── game/                # 游戏逻辑
│   │   ├── bullet/          # 子弹池（Numba 加速）
│   │   ├── player/          # 玩家系统
│   │   ├── stage/           # 关卡系统核心（基类都在这里）
│   │   ├── boss/            # Boss 管理
│   │   ├── laser.py         # 激光系统
│   │   ├── item.py          # 道具系统
│   │   └── audio.py         # 音频系统
│   ├── render/              # 渲染管线
│   ├── resource/            # 纹理和精灵管理
│   └── ui/                  # HUD、菜单、对话框渲染
│
├── game_content/            # 关卡内容（写弹幕在这里）
│   └── stages/
│       ├── stage1/          # 第 1 面（完整示例）
│       ├── stage2/          # 第 2 面（骨架）
│       └── stage3/          # 第 3 面（骨架）
│
├── assets/                  # 游戏资源
│   ├── images/              # 纹理图集（子弹、激光、敌人、道具等）
│   ├── audio/               # 全局音效和 BGM
│   ├── fonts/               # 字体
│   ├── players/             # 自机配置
│   ├── configs/             # 敌人预设等配置
│   └── bullet_aliases.json  # 弹幕类型→精灵映射表
│
├── tools/                   # PyQt5 编辑器工具
│   ├── editor_launcher.py   # 统一启动器
│   ├── bullet/              # 弹幕别名管理器
│   ├── asset/               # 纹理资产编辑器
│   ├── player/              # 自机编辑器
│   └── ...
│
└── levels/                  # 关卡加载脚本
```

## 核心概念

pystg 把**引擎**和**内容**彻底分开：

- `src/` 是引擎，提供子弹池、渲染、碰撞等底层能力
- `game_content/` 是内容，只描述「发生什么」——弹幕怎么飞、敌人怎么动、Boss 出什么招

你写弹幕脚本时，只需要和几个基类打交道：

```python
from src.game.stage.spellcard import SpellCard, NonSpell   # 符卡 / 非符
from src.game.stage.wave_base import Wave                   # 道中波次
from src.game.stage.enemy_script import EnemyScript         # 敌人脚本
```

所有弹幕逻辑通过 Python 协程（`async/await`）编写，`await self.wait(N)` 暂停 N 帧：

```python
class MySpell(SpellCard):
    name = "火符「Example」"
    hp = 1000
    time_limit = 45

    async def run(self):
        angle = 0
        while True:
            self.fire_circle(count=12, speed=2.0, start_angle=angle, color="red")
            angle += 10
            await self.wait(15)
```

详细的脚本编写方法见 [弹幕脚本开发指南](STAGE_SCRIPTING_GUIDE.md)。

## 一个关卡长什么样

每个关卡是 `game_content/stages/` 下的一个文件夹：

```
stage1/
├── __init__.py
├── stage_script.py          # 关卡主脚本（定义流程）
├── waves/                   # 道中波次
│   ├── opening_wave.py
│   └── fairy_wave.py
├── spellcards/              # Boss 符卡
│   ├── nonspell_1.py
│   ├── spell_1.py
│   └── spell_2.py
├── enemies/                 # 敌人定义
│   └── fairy.py
├── dialogue/                # 对话脚本
│   └── boss_dialogue.py
└── audio/                   # 关卡私有音频（可选）
    ├── se/
    └── music/
```

`stage_script.py` 控制整个关卡的流程：

```python
class Stage1(StageScript):
    id = "stage1"
    name = "Stage 1"
    bgm = "00.wav"
    boss_bgm = "01.wav"

    async def run(self):
        await self.run_wave(OpeningWave)     # 道中波次
        await self.run_wave(FairyWave)

        await self.play_dialogue([           # Boss 前对话
            ("Hinanawi_Tenshi", "left", "准备好了吗？"),
            ("Reiuji_Utsuho", "right", "来吧！"),
        ])

        await self.run_boss(self.boss)       # Boss 战
```

## 下一步

- **写弹幕** → [弹幕脚本开发指南](STAGE_SCRIPTING_GUIDE.md)
- **用预设快速出杂兵** → [敌人预设系统](ENEMY_PRESET_SYSTEM.md)
- **用编辑器管理资源** → [编辑器工具](EDITOR_TOOLS_GUIDE.md)
- **了解引擎内部** → [架构概览](architecture.md)
