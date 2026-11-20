# 纹理资产系统

PySTG 的纹理资产系统（`src/resource/texture_asset.py`）统一管理游戏内的静态图集与帧动画，核心概念分为三层：

- **纹理图集（`TextureAtlas`）**：一张包含多个子区域的大图。
- **静态精灵（`Sprite`）**：图集中的一个矩形裁切区域，附带中心点、碰撞半径和旋转标记。
- **动画精灵（`AnimatedSprite`）**：按固定帧时长循环或单次播放的精灵帧序列。

## 核心数据结构

### `Sprite`

```python
@dataclass
class Sprite:
    name: str                        # 精灵名称
    texture_path: str                # 所属纹理路径
    rect: Tuple[int, int, int, int]  # (x, y, width, height)
    center: Tuple[float, float]      # 旋转/绘制中心点
    radius: float                    # 碰撞半径
    rotate: bool                     # 是否跟随运动方向旋转
    scale: Tuple[float, float]       # 默认缩放
    metadata: Dict[str, Any]         # 扩展元数据
```

### `AnimatedSprite`

```python
@dataclass
class AnimatedSprite:
    name: str                        # 动画名称
    texture_path: str                # 所属纹理路径
    frames: List[SpriteFrame]        # 帧列表
    center: Tuple[float, float]      # 中心点
    radius: float                    # 碰撞半径
    rotate: bool                     # 是否跟随运动方向旋转
    frame_duration: float            # 每帧时长（秒）
    loop: bool                       # 是否循环播放
```

常用查询方法：

- `get_frame_at_time(time)`：返回指定时刻对应的 `SpriteFrame`
- `get_frame_index_at_time(time)`：返回当前帧索引
- `get_frame_uv_at_time(time, texture_size)`：返回当前帧的 UV 坐标

## JSON 配置格式（v2.0）

```json
{
  "version": "2.0",
  "texture": "spritesheet.png",
  "sprites": {
    "bullet_red": {
      "rect": [0, 0, 32, 32],
      "center": [16, 16],
      "radius": 8.0,
      "rotate": true,
      "metadata": {
        "damage": 10
      }
    }
  },
  "animations": {
    "bullet_spin": {
      "frames": [
        {"rect": [0, 64, 32, 32]},
        {"rect": [32, 64, 32, 32]},
        {"rect": [64, 64, 32, 32]},
        {"rect": [96, 64, 32, 32]}
      ],
      "center": [16, 16],
      "frame_duration": 0.1,
      "loop": true
    },
    "bullet_pulse": {
      "strip": {
        "x": 0,
        "y": 128,
        "width": 32,
        "height": 32,
        "count": 8,
        "direction": "horizontal",
        "spacing": 0
      },
      "center": [16, 16],
      "frame_duration": 0.1,
      "loop": true
    }
  }
}
```

不规则排布的动画使用 `frames` 显式列出每帧 `rect`；等距排布的动画可直接用 `strip` 自动切分（支持 `horizontal` / `vertical` 与可选 `spacing`）。

## 代码用法

### 基本加载与 UV 查询

```python
from src.resource.texture_asset import TextureAssetManager

manager = TextureAssetManager("assets")
manager.load_atlas_config("images/bullet/bullet_atlas.json")

sprite = manager.get_sprite("bullet_red")
uv = manager.get_sprite_uv("bullet_red")  # (u_left, v_top, u_right, v_bottom)
```

对于 OpenGL 渲染管线，纹理上传采用 `flip_y=True` 时，向 `SpriteRegistry` 注册 UV 也保持同步翻转，确保采样方向一致。

### 动画帧查询

```python
anim = manager.get_animation("bullet_spin")
time_elapsed = 0.0

# 在 60 Hz 更新循环中推进
time_elapsed += 1.0 / 60.0
frame_idx = anim.get_frame_index_at_time(time_elapsed)
uv = manager.get_animation_frame_uv("bullet_spin", time_elapsed)
```

### 全局访问与旧配置兼容

```python
from src.resource.texture_asset import init_texture_asset_manager, get_texture_asset_manager

init_texture_asset_manager("assets")
manager = get_texture_asset_manager()

# 兼容加载旧版图集配置
manager.load_legacy_config("images/bullet1.json")
```

## 命名与制作建议

- **短名与全名**：可用 `manager.get_sprite("bullet_red")` 直接查找，跨图集重名时用 `atlas_name.bullet_red` 消歧。
- **按类别拆分图集**：子弹、敌人、道具、背景分开打包，便于批处理与按需加载。
- **保留边缘留白**：相邻精灵之间建议留 1–2 像素透明边距，减少线性采样时的边缘渗色。

常见资产目录布局：

| 路径 | 用途 |
| --- | --- |
| `assets/images/bullet/` | 弹幕纹理图集与 JSON 配置 |
| `assets/images/enemy/` | 敌人精灵与动画配置 |
| `assets/images/laser/` | 直线与曲线激光纹理配置 |
| `assets/images/item/` | 道具图集与配置 |
| `assets/images/background/` | 关卡背景纹理 |
| `assets/images/ui/` | HUD、字体与界面元素 |
