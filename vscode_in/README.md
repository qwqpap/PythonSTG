# STG Asset Preview

在编写 STG（弹幕射击游戏）代码时，实时预览子弹、激光、精灵等资产的图片。

## 功能

### 🎯 悬停预览
当鼠标悬停在资产名称（如 `"bullet_red_1"`）上时，自动显示：
- 资产图片预览
- 类型（精灵/动画/激光）
- 纹理区域信息
- 碰撞半径等属性

### ✨ 智能补全
在字符串中输入时，自动提供资产名称补全：
- 按名称模糊搜索
- 显示资产类型和尺寸
- 选择后自动插入

### 🔍 资产浏览器
- `Ctrl+Shift+G` - 查看所有资产列表
- `Ctrl+Alt+G` - 搜索资产
- 状态栏显示已加载资产数量

## 支持的语言
- Python
- Lua
- JavaScript / TypeScript
- JSON

## 支持的资产类型
- 🎯 精灵 (Sprite)
- 🎬 动画 (Animation)
- ⚡ 激光 (Laser)
- 🌀 曲线激光 (Bent Laser)

## 配置

在 `settings.json` 中可配置：

```json
{
  "stg-asset-preview.enableHover": true,
  "stg-asset-preview.enableCompletion": true,
  "stg-asset-preview.maxPreviewSize": 128
}
```

## 资产配置格式

插件自动扫描工作区中的 `assets/images/**/*.json` 和 `assets/players/**/*.json` 文件。

配置文件格式示例：

```json
{
  "__image_filename": "bullet1.png",
  "sprites": {
    "bullet_red_1": {
      "rect": [0, 0, 16, 16],
      "center": [8, 8],
      "radius": 4,
      "rotate": true
    }
  },
  "animations": {
    "bullet_spin": {
      "frames": [
        {"rect": [0, 0, 16, 16], "center": [8, 8]},
        {"rect": [16, 0, 16, 16], "center": [8, 8]}
      ],
      "frame_duration": 5,
      "loop": true
    }
  }
}
```

## 命令

| 命令 | 快捷键 | 说明 |
|------|--------|------|
| STG: 查看所有资产 | `Ctrl+Shift+G` | 显示资产选择器 |
| STG: 搜索资产 | `Ctrl+Alt+G` | 搜索并插入资产名 |
| STG: 刷新资产缓存 | - | 重新加载配置文件 |

## 开发调试

1. 按 `F5` 启动扩展开发主机
2. 在新窗口中打开包含 `assets` 文件夹的项目
3. 在 Python/Lua 文件中输入 `"` 触发补全

## 更新日志

### 0.0.1
- 初始版本
- 支持悬停预览
- 支持自动补全
- 支持资产搜索
