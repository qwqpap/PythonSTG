# Claude Code 仓库入口

共享工作约定以 [AGENTS.md](AGENTS.md) 为准；本文件只提供入口，不另设一套流程或完成标准。

## 按任务查阅

| 任务 | 入口 |
| --- | --- |
| 安装、运行游戏或打开编辑器 | [快速开始](docs/getting-started.md) |
| 编辑器实现或修复 | [实施 TODO](docs/EDITOR_IMPLEMENTATION_TODO.md) 的状态表、不变契约和相关阶段；[架构](docs/EDITOR_ARCHITECTURE.md) 的相关章节 |
| 编辑器整体产品方向或边界调整 | [产品愿景](docs/EDITOR_PRODUCT_VISION.md)，并完整阅读 TODO 与架构 |
| 手写 Wave、EnemyScript、SpellCard | [脚本须知](game_content/SCRIPTING.md) 的核心原则及所需 API；[脚本参考](docs/STAGE_SCRIPTING_GUIDE.md) |
| 纹理、敌人预设、独立资产工具 | [工具指南](docs/EDITOR_TOOLS_GUIDE.md)、对应资产专题 |
| 引擎内部 | [架构概览](docs/architecture.md) 与实际调用入口 |

查阅范围随任务展开，不需要为无关修改通读所有手册。文档中的历史测试结果不证明当前工作树通过；阶段完成仍须执行 AGENTS 和 TODO 规定的验收。

## 常用入口

从仓库根目录运行；安装步骤见快速开始。

```bash
python main.py --debug
pystg-editor game_content/authoring/code_editor_demo
python tools/editor_launcher.py
python tools/validate_assets.py
```

仓库当前不含可运行的 pytest 套件（`tests/` 为空）；提交前至少运行
`python -m compileall -q main.py src game_content tools`、`python tools/validate_assets.py`
和 `git diff --check`，并按修改涉及的行为补充真实运行时检查。阶段和最终合并门禁见 TODO，
文档修改检查链接与文档构建。
