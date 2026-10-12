# 纹理资产编辑器（PySide6）

纹理资产编辑器用于编辑精灵图集、动画、激光和自机配置。工具通过 `src.qt_compat` 使用 PySide6，并直接调用引擎的统一纹理系统（`src/resource/unified_texture.py`），因此它的配置文件格式与运行时完全一致。

## 支持的资产类型

| 类型 | 说明 |
| --- | --- |
| 精灵 | 静态图像区域，可编辑区域矩形、中心点和碰撞半径。 |
| 动画 | 多帧动画，可编辑帧序列、帧间隔和循环方式，并实时预览。 |
| 激光 | 三段式激光（头、身、尾），支持 16 色变体。 |
| 曲线激光 | 曲线激光资产（`BentLaserAsset`）。 |
| 颜色变体组 | 同组颜色的管理（`ColorVariantGroup`）。 |
| 自机 | 自机配置，包含动画和属性。 |

## 编辑功能

- 在纹理上绘制精灵区域和动画帧。
- 拖拽中心点，并显示碰撞半径。
- 实时预览动画，可控制播放。
- 缩放、平移视图，并显示网格辅助对齐。
- 复制、粘贴和镜像区域，按 N × M 生成网格区域。
- 保存时通过 `atomic_write_json` 原子写回原 JSON 文件。

## 运行方式

安装开发依赖项后，在存储库根目录运行：

```bash
python -m pip install -r requirements-dev.txt
python -m pip install -e .
python tools/asset/asset_manager_qt.py
```

## 快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Ctrl+R` | 从磁盘重新加载所有配置。 |
| `Ctrl+S` | 保存当前配置。 |
| `Ctrl+Shift+S` | 保存所有修改。当前实现只保存当前配置，见[已知限制](#已知限制)。 |
| `Delete` | 删除选中项。 |
| `=` | 放大。 |
| `-` | 缩小。 |
| `F` | 适应窗口。 |

## 编辑模式

1. **选择**：默认模式。拖拽平移视图，单击选择资产。
2. **绘制矩形**：在纹理上绘制矩形，作为精灵或动画帧的区域。
3. **编辑中心点**：单击设置中心点位置。

## 配置文件

工具读取以下位置的 JSON 文件，并原地写回：

- `assets/images/bullet/`、`assets/images/laser/`、`assets/images/item/`、`assets/images/enemy/`、`assets/images/background/`、`assets/images/ui/`
- `assets/players/*/`

### 子弹配置

```json
{
  "texture": "bullet.png",
  "sprites": {
    "bullet_red": {
      "rect": [0, 0, 16, 16],
      "center": [8, 8],
      "radius": 4.0,
      "rotate": true
    }
  },
  "animations": {
    "bullet_anim": {
      "frames": [
        {"rect": [0, 0, 16, 16], "center": [8, 8]},
        {"rect": [16, 0, 16, 16], "center": [8, 8]}
      ],
      "frame_duration": 0.1,
      "loop": true
    }
  }
}
```

### 激光配置

```json
{
  "laser_textures": {
    "laser1": {
      "file": "laser1.png",
      "head_width": 64,
      "body_width": 128,
      "tail_width": 64,
      "row_height": 16,
      "colors": 16
    }
  }
}
```

## 已知限制

- `Ctrl+Shift+S`（保存所有修改）当前只保存当前配置，未保存其他已修改的配置。
- 工具没有“另存为”功能。
- 颜色变体组只显示已有组的数量，不提供颜色变体的自动生成。
- 自动切割精灵表没有专用功能，可以使用网格生成器（N × M）代替。

## 相关文档

- [编辑器工具指南](../../docs/EDITOR_TOOLS_GUIDE.md)
- [纹理资产系统](../../docs/TEXTURE_ASSET_SYSTEM.md)
