---
layout: home

hero:
  name: PySTG
  text: Python + OpenGL 弹幕射击游戏引擎
  tagline: 用 async/await 编写关卡脚本，用 ModernGL 与 Numba 驱动高密度弹幕，并配套编辑器、资产系统和 QQ 群弹幕互动。
  image:
    src: /logo.png
    alt: PySTG Logo
  actions:
    - theme: brand
      text: 快速开始
      link: /getting-started
    - theme: alt
      text: 项目简介
      link: /architecture
    - theme: alt
      text: GitHub
      link: https://github.com/qwqpap/PythonSTG

features:
  - title: 高性能弹幕
    details: 基于 NumPy 结构化数组、Numba JIT 与 ModernGL 实例化渲染，面向海量子弹同屏的稳定运行。
  - title: 协程化关卡脚本
    details: 使用 Python async/await 描述 Wave、Boss、符卡和非符，让时间轴、等待与并行动作更接近弹幕设计思路。
  - title: 完整 STG 玩法
    details: 覆盖判定、擦弹、Power、Bomb、符卡、道具掉落、练习模式、Debug 跳转等核心体验。
  - title: 数据驱动资产
    details: 纹理图集、精灵动画、弹幕别名、敌人预设和行为预设都可以通过 JSON 配置维护。
  - title: 编辑器工具链
    details: 代码驱动关卡编辑器以声明式 Python 为唯一真源，并保留纹理、自机、敌人、背景、对话和 UI 等独立资产工具。
  - title: QQ 群弹幕互动
    details: 内置 UDP 接入层，可通过 NoneBot、Mirai 等外部机器人把弹幕消息转化为实际游戏子弹。
---

## 按任务查文档

| 你要做什么 | 从哪里开始 |
| --- | --- |
| 安装、运行游戏、试用关卡编辑器 | [快速开始](getting-started.md) |
| 理解编辑器面向谁、支持什么 | [产品愿景](EDITOR_PRODUCT_VISION.md) |
| 查看编辑器进度和验收缺口 | [实施 TODO](EDITOR_IMPLEMENTATION_TODO.md) 的状态表及对应 Evidence |
| 修改编辑器 | TODO 的相关阶段，加上[架构](EDITOR_ARCHITECTURE.md)对应章节；仓库共享约定见根目录 `AGENTS.md` |
| 写运行时 Wave、EnemyScript、SpellCard | [脚本指南](STAGE_SCRIPTING_GUIDE.md)；仓库内 `game_content/SCRIPTING.md` 提供内容约定 |
| 快速预览手写符卡 | [开发工具链](DEVTOOLS_PHASE1.md) |
| 管理纹理和敌人资产 | [工具指南](EDITOR_TOOLS_GUIDE.md)、[纹理系统](TEXTURE_ASSET_SYSTEM.md)、[敌人预设](ENEMY_PRESET_SYSTEM.md) |
| 修改引擎 | [架构概览](architecture.md)与实际 Runtime 入口 |

产品愿景和架构描述约束，TODO 独立记录实施顺序与验收证据。日期报告是历史快照；
技术门禁、真实窗口交互和真人易用性验收各有证据，不能互相替代。
