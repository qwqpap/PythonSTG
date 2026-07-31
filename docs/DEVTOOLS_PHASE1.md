# 第一阶段开发工具链

这些工具用于缩短内容开发循环：调参数、看真实引擎内效果、验证资源，然后导出或运行脚本代码。

## 资源验证

```bash
python tools/validate_assets.py
python tools/validate_assets.py --format json
```

验证器会检查：

- `assets/` 和 `game_content/` 下的 JSON 语法。
- 精灵图集 JSON 引用的纹理文件。
- 精灵 `rect` 是否越过图片边界。
- 动画帧引用是否有效。
- `assets/bullet_aliases.json` 是否能解析到已加载精灵。
- 敌人预设中的精灵和默认弹幕别名。
- 玩家、背景、激光相关纹理引用。

当前仓库状态允许 warning 存在；error 会返回非零退出码，适合接入 CI。

## 热重载

```bash
python main.py --debug --hot-reload
```

运行时热重载目前覆盖这些低风险配置：

- `assets/bullet_aliases.json`
- `assets/ui/hud_layout.json`
- `assets/images/laser/laser_config.json`

监听器使用轮询方式，并在主游戏循环中运行。重载失败时会保留旧状态，并打印 `[HotReload:ERROR]`。

## 原生 Pattern Lab

```bash
python tools/pattern_lab_native.py
python tools/pattern_lab_native.py --spec my_pattern.json --export game_content/stages/stage1/spellcards/lab_spell.py
```

这个工具走真实引擎渲染路径：

- `GameWindow`
- `ModernGL`
- `TextureAssetManager`
- `SpriteRegistry`
- `OptimizedBulletPool`
- `StageContext` 弹幕别名解析
- `OptimizedBulletRenderer`

快捷键：

- Up / Down：选择参数。
- Left / Right：修改当前参数。
- R：从第 0 帧重新开始，并清空弹幕。
- Z：只清空弹幕，不改变当前帧。
- X 或 Space：暂停 / 继续。
- C：重置为默认值。
- Enter：导出 `SpellCard` 代码到 stdout；如果传了 `--export`，则写入对应文件。
- Esc：退出。

UI 面板在 gameplay viewport 外侧，不会挡住弹幕。数值显示和导出代码都会做稳定格式化，避免浮点噪声。Pattern 模式包括 `ring`、`arc`、`spiral` 和 `flower`。

旧的浏览器原型已经移除，避免 Pattern Lab 预览效果和真实游戏渲染发生偏差。

## 符卡预览

```bash
python tools/preview_spell.py game_content/stages/stage1/spellcards/spell_2.py SunnySpell1
python tools/preview.py game_content/stages/stage1/spellcards/spell_2.py --spell SunnySpell1 --boss test_boss --player-pos 0,-0.8 --seed 114514
python tools/preview.py game_content/stages/stage1/spellcards/spell_2.py
```

`tools/preview.py` 是 `tools/preview_spell.py` 的短入口。预览器会通过真实 `SpellCard` 运行链路渲染：

- `GameWindow`
- `ModernGL`
- `TextureAssetManager`
- `SpriteRegistry`
- `OptimizedBulletPool`
- `StageContext`
- `OptimizedBulletRenderer`

默认会监听脚本文件。保存文件后，预览器会清空弹幕、重新加载模块、实例化选中的 `SpellCard`，并从第 0 帧重启。安装了 `watchdog` 时优先使用 `watchdog`，否则退回轮询。重载失败时，右侧面板会显示文件、行号和错误信息，同时保留上一版可运行实例。

同目录预览配置会自动加载：

```text
spell_2.py
spell_2.preview.json
```

```json
{
  "spell": "SunnySpell1",
  "boss": "test_boss",
  "player_pos": [0, -0.8],
  "seed": 114514,
  "speed": 1.0,
  "hitbox": true,
  "auto_reload": true,
  "duration": 1800
}
```

预览配置也可以写在符卡类里：

```python
class SunnySpell1(SpellCard):
    preview = {
        "boss": "test_boss",
        "player_pos": (0, -0.8),
        "seed": 114514,
        "duration": 1800,
    }
```

也可以使用辅助装饰器：

```python
from src.devtools.spell_preview import preview

@preview(boss="test_boss", player_pos=(0, -0.8), seed=114514, duration=1800)
class SunnySpell1(SpellCard):
    ...
```

配置优先级为：显式命令行参数 > 同目录 `.preview.json` > 类内元数据 > 默认值。

快捷键：

- R：重载并从第 0 帧重启。
- Space 或 X：暂停 / 继续。
- `.`：推进一帧模拟。
- 1 / 2 / 3：设置模拟速度为 0.5x / 1x / 2x。
- `[` / `]`：向前或向后 seek 60 帧。实现方式是 reset 后快速模拟，不渲染中间帧。
- PageDown / PageUp：向前或向后 seek 300 帧。
- Home / End：跳到开头或配置的结束帧。
- H：显示 boss 和 player 的 hitbox / crosshair。
- Z：只清空弹幕，不重启符卡。
- Esc：退出。

信息面板在 gameplay viewport 外侧，不会覆盖弹幕。运行时错误会暂停预览，并在你修复脚本、再次保存之前保留当前画面。统计面板会显示 FPS、当前帧、弹幕数量、弹幕池占用、seed、重载状态、update 耗时和 render 耗时。

可复用运行时 API 位于 `src/devtools/spell_preview.py`：

```python
runtime.load(file_path, spell_name=None)
runtime.reload()
runtime.reset()
runtime.pause(True)
runtime.step()
runtime.seek(300)
runtime.set_speed(2.0)
runtime.clear_bullets()
runtime.set_player_pos(0, -0.8)
runtime.set_seed(114514)
stats = runtime.get_stats()
```

VSCode task：

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "PythonSTG: Preview Current File",
      "type": "shell",
      "command": "python tools/preview.py ${file}",
      "problemMatcher": []
    },
    {
      "label": "PythonSTG: Preview Current Spell",
      "type": "shell",
      "command": "python tools/preview.py ${file} --spell ${input:spellClass}",
      "problemMatcher": []
    }
  ],
  "inputs": [
    {
      "id": "spellClass",
      "type": "promptString",
      "description": "SpellCard class name to preview"
    }
  ]
}
```

预览器有意和代码编辑器解耦。以后 PyQt 编辑器、VSCode 插件或其他 UI 都可以复用同一套运行时接口；VSCode 继续负责写代码，PythonSTG 工具负责预览、调参和编排。

## 推荐流程

1. 用 `python tools/pattern_lab_native.py` 在真实渲染器里调一个可复用弹幕 pattern。
2. 导出 `SpellCard` 片段，或者直接写完整符卡脚本。
3. 添加 `<script>.preview.json` 或类内 preview 元数据。
4. 在 VSCode 中编辑时运行 `python tools/preview.py <script.py>`。
5. 符卡效果稳定后，运行 `python main.py --debug --hot-reload`，进入实际关卡测试。
6. 提交前运行 `python tools/validate_assets.py` 和 pytest。
