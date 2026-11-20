# Claude Code 仓库入口

仓库共享约定以 [AGENTS.md](AGENTS.md) 为准。

## 常用文档

| 任务 | 参考文档 |
| --- | --- |
| 安装、运行游戏或启动编辑器 | [docs/getting-started.md](docs/getting-started.md) |
| 编写手写关卡、波次、敌人、符卡 | [docs/STAGE_SCRIPTING_GUIDE.md](docs/STAGE_SCRIPTING_GUIDE.md)、[game_content/SCRIPTING.md](game_content/SCRIPTING.md) |
| 关卡编辑器设计与架构 | [docs/EDITOR_PRODUCT_VISION.md](docs/EDITOR_PRODUCT_VISION.md)、[docs/EDITOR_ARCHITECTURE.md](docs/EDITOR_ARCHITECTURE.md)、[docs/EDITOR_IMPLEMENTATION_TODO.md](docs/EDITOR_IMPLEMENTATION_TODO.md) |
| 独立资产工具与预览工具 | [docs/EDITOR_TOOLS_GUIDE.md](docs/EDITOR_TOOLS_GUIDE.md)、[docs/DEVTOOLS_PHASE1.md](docs/DEVTOOLS_PHASE1.md) |
| 引擎内部模块与渲染 | [docs/architecture.md](docs/architecture.md)、[docs/TEXTURE_ASSET_SYSTEM.md](docs/TEXTURE_ASSET_SYSTEM.md) |
| 东方移植机制对照 | [docs/TH06_API_COVERAGE.md](docs/TH06_API_COVERAGE.md)、[docs/TH07_PORT_AUDIT.md](docs/TH07_PORT_AUDIT.md) |

## 常用命令

```bash
python main.py --debug
pystg-editor game_content/authoring/code_editor_demo
python tools/editor_launcher.py
python -m compileall -q main.py src game_content tools
python tools/validate_assets.py
git diff --check
```

改动文档后运行 `npm run docs:build` 检查站点构建与链接。
