---
layout: home

hero:
  name: PySTG
  text: Python + OpenGL 弹幕射击游戏引擎
  tagline: 用 async/await 编写关卡脚本，用 ModernGL 和 Numba 驱动弹幕，配套代码驱动关卡编辑器、资产工具箱与 QQ 群弹幕互动。
  image:
    src: /logo.png
    alt: PySTG 徽标
  actions:
    - theme: brand
      text: 快速开始
      link: /getting-started
    - theme: alt
      text: 弹幕脚本指南
      link: /STAGE_SCRIPTING_GUIDE
    - theme: alt
      text: GitHub
      link: https://github.com/qwqpap/PythonSTG

features:
  - title: 高性能弹幕运行时
    details: 基于 NumPy 结构化数组与 Numba JIT 批量更新，ModernGL 实例化绘制，支持批量行为阶段与分系统慢速。
  - title: 协程关卡脚本
    details: 使用 async/await 自然表达波次、敌人、Boss 与符卡时序，无需繁琐回调。
  - title: 完整 STG 玩法
    details: 判定点、擦弹、Power、Bomb、受击救援窗口、符卡、道具掉落、难度选择、练习模式与 Debug 跳转。
  - title: 数据驱动资产
    details: 纹理图集、精灵动画、弹幕别名、敌人预设与行为预设均使用 JSON 配置。
  - title: 关卡编辑器与资产工具
    details: 代码驱动关卡编辑器以声明式 Python 为唯一真源；纹理、自机、弹幕别名、立绘与背景提供独立可视化工具。
  - title: QQ 群弹幕互动
    details: 内置 UDP 监听服务，可对接 NoneBot、Mirai 等外部机器人把群消息实时转为游戏弹幕。
---

## 按任务查文档

| 我想做什么 | 推荐入口 |
| --- | --- |
| 安装环境、运行游戏或试用编辑器 | [快速开始](getting-started.md) |
| 编写手写关卡、波次、敌人或符卡脚本 | [弹幕脚本开发指南](STAGE_SCRIPTING_GUIDE.md) |
| 用 JSON 预设快速配置杂兵 | [敌人预设系统](ENEMY_PRESET_SYSTEM.md) |
| 单独预览手写符卡或校验资产 | [开发与预览工具链](DEVTOOLS_PHASE1.md) |
| 编辑纹理图集、弹幕别名、自机或背景 | [独立资产工具指南](EDITOR_TOOLS_GUIDE.md)、[纹理资产系统](TEXTURE_ASSET_SYSTEM.md) |
| 了解代码驱动关卡编辑器的设计与架构 | [编辑器设计概览](EDITOR_PRODUCT_VISION.md)、[编辑器架构](EDITOR_ARCHITECTURE.md) |
| 查看引擎模块分层与数据流 | [引擎架构概览](architecture.md) |
| 参考东方机制映射与移植实践 | [TH06 机制对照](TH06_API_COVERAGE.md)、[TH07 移植参考](TH07_PORT_AUDIT.md) |
