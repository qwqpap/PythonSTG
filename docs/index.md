---
layout: home

hero:
  name: PySTG
  text: Python + OpenGL 弹幕射击游戏引擎
  tagline: 用 async/await 编写关卡脚本，用 ModernGL 和 Numba 驱动弹幕，并配套关卡编辑器、资产工具和 QQ 群弹幕互动。
  image:
    src: /logo.png
    alt: PySTG 徽标
  actions:
    - theme: brand
      text: 快速开始
      link: /getting-started
    - theme: alt
      text: 架构概览
      link: /architecture
    - theme: alt
      text: GitHub
      link: https://github.com/qwqpap/PythonSTG

features:
  - title: 弹幕运行时
    details: 子弹池基于 NumPy 结构化数组和 Numba 编译的更新逻辑，渲染使用 ModernGL 实例化绘制。
  - title: 协程关卡脚本
    details: 用 async/await 描述波次、Boss、符卡和非符的时序，不需要回调。
  - title: STG 玩法
    details: 判定点、擦弹、Power、Bomb、符卡、道具掉落、练习模式和 Debug 跳转。
  - title: 数据驱动资产
    details: 纹理图集、精灵动画、弹幕别名、敌人预设和行为预设都使用 JSON 配置。
  - title: 编辑器工具链
    details: 代码驱动关卡编辑器以声明式 Python 为唯一真源；纹理、自机、敌人、背景、对话和 UI 使用独立工具编辑。
  - title: QQ 群弹幕互动
    details: 内置 UDP 接入层，可通过 NoneBot、Mirai 等外部机器人把群消息转换为游戏中的子弹。
---

## 按任务查文档

| 目标 | 入口 |
| --- | --- |
| 安装、运行游戏或试用关卡编辑器 | [快速开始](getting-started.md) |
| 了解编辑器面向谁、支持什么 | [编辑器产品愿景](EDITOR_PRODUCT_VISION.md) |
| 查看编辑器进度和剩余验收 | [编辑器实施 TODO](EDITOR_IMPLEMENTATION_TODO.md) 的状态表和对应 Evidence |
| 修改编辑器 | TODO 的相关阶段，加上[编辑器架构边界](EDITOR_ARCHITECTURE.md)的对应章节；仓库共享约定见根目录 `AGENTS.md` |
| 编写运行时 Wave、EnemyScript 或 SpellCard | [弹幕脚本开发指南](STAGE_SCRIPTING_GUIDE.md)；仓库内的内容约定见 `game_content/SCRIPTING.md` |
| 单独预览手写符卡 | [开发工具链](DEVTOOLS_PHASE1.md) |
| 管理纹理和敌人资产 | [编辑器工具指南](EDITOR_TOOLS_GUIDE.md)、[纹理资产系统](TEXTURE_ASSET_SYSTEM.md)、[敌人预设系统](ENEMY_PRESET_SYSTEM.md) |
| 修改引擎 | [架构概览](architecture.md)和实际运行时入口 |

产品愿景和架构文档描述产品约束，实施 TODO 记录实施顺序和验收证据。日期报告是历史快照。

技术门禁、真实窗口交互和真人易用性验收使用不同的证据，不能互相替代。未观察的验收类别应标记为未运行。

游戏安装和运行方式见仓库根目录的 [`README.md`](https://github.com/qwqpap/PythonSTG#readme)。
