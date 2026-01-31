# STG Asset Preview 扩展开发指南

## 项目结构

```
vscode_in/
├── src/
│   ├── extension.ts      # 扩展入口
│   ├── assetManager.ts   # 资产管理器（解析JSON配置）
│   ├── hoverProvider.ts  # 悬停预览提供者
│   └── completionProvider.ts  # 自动补全提供者
├── package.json          # 扩展清单
└── tsconfig.json         # TypeScript配置
```

## 开发流程

1. 修改代码后运行 `npm run compile`
2. 按 F5 启动扩展开发主机
3. 在新窗口中测试功能

## 资产加载流程

1. 扩展激活时初始化 `AssetManager`
2. 扫描 `assets/images/**/*.json` 和 `assets/players/**/*.json`
3. 解析每个配置文件，提取 sprites、animations、lasers
4. 存储到内存 Map 中供快速查找

## 支持的JSON配置格式

### 精灵配置
```json
{
  "__image_filename": "texture.png",
  "sprites": {
    "name": {
      "rect": [x, y, width, height],
      "center": [cx, cy],
      "radius": 5,
      "rotate": true
    }
  }
}
```

### 动画配置
```json
{
  "animations": {
    "name": {
      "frames": [
        {"rect": [0, 0, 32, 32], "center": [16, 16]},
        {"rect": [32, 0, 32, 32], "center": [16, 16]}
      ],
      "frame_duration": 5,
      "loop": true
    }
  }
}
```

### 激光配置
```json
{
  "lasers": {
    "name": {
      "head": [x, y, w, h],
      "body": [x, y, w, h],
      "tail": [x, y, w, h]
    }
  }
}
```

## 扩展功能

- HoverProvider: 悬停时显示资产详情和图片
- CompletionProvider: 在字符串中提供资产名补全
- 状态栏: 显示已加载资产数量
- 命令: 刷新、搜索、浏览资产

## 发布

```bash
npm install -g @vscode/vsce
vsce package
```
