# pystg 文档

Python 东方 Project 风格弹幕射击游戏引擎。

---

## 给内容开发者

想写弹幕、做关卡？只需要看这些：

| 文档 | 内容 |
|------|------|
| [快速开始](getting-started.md) | 环境搭建、运行游戏、项目结构 |
| [弹幕脚本开发指南](STAGE_SCRIPTING_GUIDE.md) | 符卡、波次、敌人、Boss 的编写方法和完整 API |
| [敌人预设系统](ENEMY_PRESET_SYSTEM.md) | 用 JSON 预设快速创建杂兵 |

## 给引擎开发者

想了解或修改引擎本身？

| 文档 | 内容 |
|------|------|
| [架构概览](architecture.md) | 引擎分层、模块依赖、核心数据流 |
| [纹理资产系统](TEXTURE_ASSET_SYSTEM.md) | 图集加载、精灵定义、动画配置 |
| [编辑器工具](EDITOR_TOOLS_GUIDE.md) | 弹幕别名管理器、纹理编辑器、自机编辑器 |

## 技术栈

- **pygame-ce** + **ModernGL** — 渲染
- **Numba** — 子弹池 JIT 加速
- **Python async/await** — 协程驱动的弹幕脚本
- **PyQt5** — 编辑器工具

## 源码

- GitHub: [qwqpap/PythonSTG](https://github.com/qwqpap/PythonSTG)
