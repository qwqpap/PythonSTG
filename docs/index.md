# PySTG 文档

Python + OpenGL 实现的东方 Project 风格弹幕射击游戏引擎。

引擎层提供高性能子弹池、激光、碰撞、渲染、音频；
内容层用 Python 协程编写关卡、波次、Boss 符卡；
两层通过 `StageContext` 桥接，互相解耦。

---

## 我是新手，从哪开始？

1. 先看 [快速开始](getting-started.md)：装环境、跑游戏、了解项目布局。
2. 再看 [弹幕脚本开发指南](STAGE_SCRIPTING_GUIDE.md)：写第一张符卡。
3. 想做杂兵就翻 [敌人预设系统](ENEMY_PRESET_SYSTEM.md)。
4. 想用编辑器管理资产看 [编辑器工具](EDITOR_TOOLS_GUIDE.md)。

---

## 文档导航

### 给内容开发者（写关卡 / 弹幕 / Boss）

| 文档 | 内容 |
|------|------|
| [快速开始](getting-started.md) | 环境搭建、运行游戏、项目结构 |
| [弹幕脚本开发指南](STAGE_SCRIPTING_GUIDE.md) | 完整 API 参考 — 符卡、波次、敌人、Boss、激光、时停、标签 |
| [敌人预设系统](ENEMY_PRESET_SYSTEM.md) | 用 JSON 预设快速创建杂兵 |
| [编辑器工具](EDITOR_TOOLS_GUIDE.md) | 弹幕别名管理器、纹理编辑器、自机编辑器、对话立绘编辑器 |

### 给引擎开发者（修引擎 / 加新模块）

| 文档 | 内容 |
|------|------|
| [架构概览](architecture.md) | 引擎分层、模块依赖、核心数据流 |
| [纹理资产系统](TEXTURE_ASSET_SYSTEM.md) | 图集加载、精灵定义、动画配置 |

---

## 技术栈

| 类别 | 选型 |
|------|------|
| 窗口 / 事件 | **glfw** |
| 渲染 | **ModernGL** + GLSL（实例化绘制） |
| 子弹池 | **NumPy** 结构化数组 + **Numba** JIT |
| 音频 | **miniaudio** |
| 字体 | **freetype-py**（位图字体） |
| 关卡脚本 | Python `async/await` 协程 |
| 编辑器 GUI | **PyQt5** |

---

## 仓库与版本

- 源码：[github.com/qwqpap/PythonSTG](https://github.com/qwqpap/PythonSTG)
- 协议：[MIT License](https://github.com/qwqpap/PythonSTG/blob/main/LICENSE)
- 资源版权：见仓库根目录 README 的"资源版权"说明
