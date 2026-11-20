# 开发与预览工具链

本页介绍用于加速日常手写内容开发的三个工具：资源校验、配置热重载以及独立手写符卡预览器。

> 这些工具服务于手写运行时脚本与资产配置。代码驱动关卡编辑器使用独立的显式 Run 预览流程，见 [快速开始](getting-started.md)。

## 1. 资源校验

```bash
python tools/validate_assets.py
python tools/validate_assets.py --format json
```

校验器会自动扫描 `assets/` 与 `game_content/`，检查以下项目：

- JSON 语法合法性
- 图集 JSON 引用的纹理图片是否存在
- 精灵 `rect` 是否越出图片边界
- 动画帧引用是否有效
- `assets/bullet_aliases.json` 中的映射能否解析到已加载精灵
- 敌人预设、玩家、背景与激光配置中的贴图引用

出现 `error` 时返回非零退出码，适合在提交前或 CI 中运行。

## 2. 运行时配置热重载

```bash
python main.py --debug --hot-reload
```

开启 `--hot-reload` 后，主循环会轮询监视以下配置文件，保存后自动刷新：

- `assets/bullet_aliases.json`
- `assets/ui/hud_layout.json`
- `assets/images/laser/laser_config.json`

如果保存的 JSON 有语法错误，引擎会保留旧配置并在控制台打印 `[HotReload:ERROR]`。

## 3. 独立手写符卡预览器

无需启动整面关卡，可以直接在真实 OpenGL 渲染器中预览单张手写 `SpellCard`：

```bash
python tools/preview.py game_content/stages/stage1/spellcards/spell_2.py
python tools/preview.py game_content/stages/stage1/spellcards/spell_2.py --spell SunnySpell1 --boss test_boss --player-pos 0,-0.8 --seed 114514
python tools/preview_spell.py game_content/stages/stage1/spellcards/spell_2.py SunnySpell1
```

`tools/preview.py` 是 `tools/preview_spell.py` 的快捷入口。预览器复用引擎真实的 `StageContext`、`OptimizedBulletPool`、`LaserPool`、`ItemPool`、`ParticlePool` 和渲染器（不含完整自机射击与整关结算流程）。

### 自动重载与错误恢复

默认监视目标脚本文件（安装 `watchdog` 时优先使用事件监视，否则自动退回轮询）。保存文件后会清空弹幕并从第 0 帧重启预览；若重载时存在语法或运行错误，侧栏会显示报错位置，同时保留上一版可运行的画面。

### 预览配置

支持三种配置方式，优先级为 **命令行参数 > 同目录 `.preview.json` > 类内配置 > 默认值**：

1. 同目录放置 `<脚本名>.preview.json`：

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

2. 在符卡类中声明 `preview` 字典或使用装饰器：

```python
from src.devtools.spell_preview import preview


@preview(boss="test_boss", player_pos=(0, -0.8), seed=114514, duration=1800)
class SunnySpell1(SpellCard):
    ...
```

### 快捷键

| 按键 | 功能 |
| --- | --- |
| `R` | 重新加载脚本并从第 0 帧重启 |
| `Space` / `X` | 暂停 / 继续 |
| `.` | 单帧步进 |
| `1` / `2` / `3` | 切换模拟速度为 `0.5x` / `1x` / `2x` |
| `[` / `]` | 向后 / 向前跳转 60 帧 |
| `PageUp` / `PageDown` | 向后 / 向前跳转 300 帧 |
| `Home` / `End` | 跳至开头或配置的结束帧 |
| `H` | 开关 Boss 与玩家判定盒及参考准星 |
| `Z` | 仅清屏，不重启符卡 |
| `Esc` | 退出预览 |

### 编程调用与 VS Code Task

底层封装在 `src/devtools/spell_preview.py`，提供 `load`、`reload`、`reset`、`pause`、`step`、`seek`、`set_speed`、`clear_bullets`、`set_player_pos`、`set_seed`、`get_stats` 等方法。

也可在 `.vscode/tasks.json` 中配置快捷任务，一键预览当前打开的符卡文件：

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "PySTG: Preview Current File",
      "type": "shell",
      "command": "python tools/preview.py ${file}",
      "problemMatcher": []
    }
  ]
}
```

## 推荐开发节奏

1. 编写手写 `SpellCard` 脚本，并配好预览参数。
2. 用 `python tools/preview.py <脚本.py>` 边改代码边看弹幕效果。
3. 弹幕定型后，用 `python main.py --debug --hot-reload` 进入实际关卡联合调试。
4. 改动资产配置后运行 `python tools/validate_assets.py` 检查引用完整性。
