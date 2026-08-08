# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

PySTG 是一个东方 Project 风格的弹幕射击（STG）游戏引擎，使用 Python + OpenGL 开发，支持 50000+ 颗子弹同屏 60fps 运行（Numba JIT 加速）。

## 常用命令

```bash
# 运行游戏（默认 Stage1）
python main.py

# 以资产预览模式运行
python main.py --stage=asset_preview

# Debug 模式（可快速跳转至任意 Wave/Boss/符卡）
python main.py --debug

# 性能分析
python main.py --profile

# 运行测试
python -m pytest -q

# 安装依赖（开发环境）
pip install -r requirements-dev.txt

# 生成子弹/敌人图片画廊
python tools/asset/generate_combat_gallery.py

# 启动统一场景编辑器工作台
python tools/scene_editor.py

# 旧版独立工具启动器仍可用
python tools/editor_launcher.py
```

## 整体架构

分层结构：

```
main.py                         ← 入口、主循环、游戏状态机
├── src/core/                   ← 配置(config.py)、碰撞(collision.py)、窗口/帧时钟、输入
├── src/resource/               ← 纹理资产、精灵图集管理
├── src/game/
│   ├── bullet/                 ← 子弹池（Numba JIT，NumPy 结构数组）
│   ├── stage/                  ← 关卡系统核心（stage_base, context, wave_base, spellcard, boss_base）
│   ├── player/                 ← 玩家、射击系统、Option、动画状态机
│   ├── background_render/      ← 数据驱动背景与正式预览渲染
│   ├── emoji_danmaku/          ← 外部弹幕输入与子弹桥接
│   ├── laser.py                ← 直线/曲线激光
│   ├── item.py                 ← 道具系统
│   └── audio.py                ← 双层音频（全局 bank + 关卡私有 bank）
├── src/render/                 ← OpenGL 渲染管线（实例化渲染）
├── src/ui/                     ← HUD、对话框、主菜单
└── game_content/stages/        ← 关卡内容脚本（与引擎解耦）
```

## 关卡内容系统（StageContext 架构）

内容脚本通过 `StageContext` 与引擎通讯，避免直接依赖引擎内部。关卡脚本完全用 `async/await` 协程驱动，每帧由 `StageManager.update()` 推进。

**新建关卡目录结构**：
```
game_content/stages/stageN/
├── stage_script.py     ← StageScript 子类，定义 boss 阶段列表、async run()
├── waves/              ← Wave 子类（道中波次）
├── spellcards/         ← SpellCard / NonSpell 子类
├── enemies/            ← EnemyScript / PresetEnemy 子类
├── dialogue/           ← 对话文本
└── audio/se/ music/    ← 关卡私有音效（覆盖全局同名音效）
```

**关键脚本基类**：
- `StageScript` (src/game/stage/stage_base.py) — 关卡主脚本
- `Wave` (src/game/stage/wave_base.py) — 道中波次
- `SpellCard` / `NonSpell` (src/game/stage/spellcard.py) — 符卡/非符
- `EnemyScript` / `PresetEnemy` (src/game/stage/enemy_script.py) — 敌人脚本
- `BossBase` (src/game/stage/boss_base.py) — Boss 管理器

**标记 `DEBUG_BOOKMARK = True` 的 Wave/SpellCard 会出现在 `--debug` 跳转菜单中。**

## 坐标系

| 轴 | 范围 | 备注 |
|----|------|------|
| x | -1.0 ~ +1.0 | 负=左，正=右，0=中央 |
| y | 0.0 ~ ~1.0 | 0=底部，1=顶部 |
| 角度 | 0°~360° | 0°=右，90°=上，180°=左，270°=下 |
| 子弹速度 | 游戏单位/秒 | 引擎内部自动除以 60 转帧速；慢弹≈1.5，普通≈2.5，快弹≈4.0+ |

## 子弹系统

`OptimizedBulletPool` (src/game/bullet/optimized_pool.py) 使用 NumPy 结构化数组 + Numba `@njit` 实现批量位置更新，避免 Python 循环。修改子弹更新逻辑时须保持 Numba 兼容的类型（`np.float32` / `np.uint8` / `np.uint16`），不能使用 Python 对象。

`OptimizedBulletRenderer` 使用 OpenGL 实例化渲染（一次 draw call 绘制所有同类型子弹）。

## 音频双层设计

`AudioManager.play_se(name)` 先查关卡私有 bank (`game_content/stages/stageN/audio/se/`)，未找到再查全局 bank (`assets/audio/se/`)。BGM 同理。

## 相关文档

- `game_content/SCRIPTING.md` — 脚本编写规范（**写新关卡前必读**）
- `docs/STAGE_SCRIPTING_GUIDE.md` — 完整 API 参考与示例
- `docs/ENEMY_PRESET_SYSTEM.md` — 预设敌人配置说明
- `docs/TEXTURE_ASSET_SYSTEM.md` — 精灵/图集管理原理
- `docs/SCENE_EDITOR_MVP.md` — 场景编辑器当前能力与边界
- `docs/EDITOR_TOOLS_GUIDE.md` — 工作台与专用编辑器入口
