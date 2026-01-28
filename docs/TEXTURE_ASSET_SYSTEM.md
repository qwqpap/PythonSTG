# 纹理资产管理系统

## 概述

本系统提供统一的纹理资产管理，支持：
- **纹理图集 (TextureAtlas)** - 一张大图包含多个子纹理区域
- **静态精灵 (Sprite)** - 纹理中的一个静态区域
- **动画精灵 (AnimatedSprite)** - 连续多帧组成的伪动画

## 核心类

### Sprite - 静态精灵

```python
@dataclass
class Sprite:
    name: str                           # 精灵名称
    texture_path: str                   # 所属纹理路径
    rect: Tuple[int, int, int, int]     # (x, y, width, height)
    center: Tuple[float, float]         # 中心点
    radius: float                       # 碰撞半径
    rotate: bool                        # 是否跟随方向旋转
    scale: Tuple[float, float]          # 缩放
    metadata: Dict[str, Any]            # 额外元数据
```

### AnimatedSprite - 动画精灵

```python
@dataclass
class AnimatedSprite:
    name: str                           # 动画名称
    texture_path: str                   # 所属纹理路径
    frames: List[SpriteFrame]           # 帧列表
    center: Tuple[float, float]         # 动画中心点
    radius: float                       # 碰撞半径
    rotate: bool                        # 是否跟随方向旋转
    frame_duration: float               # 每帧持续时间（秒）
    loop: bool                          # 是否循环播放
```

关键方法：
- `get_frame_at_time(time)` - 根据时间获取当前帧
- `get_frame_index_at_time(time)` - 获取当前帧索引
- `get_frame_uv_at_time(time, texture_size)` - 获取当前帧UV坐标

## JSON配置格式

### 新格式 (v2.0)

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

### 动画定义方式

#### 方式1: 显式帧列表
适合不规则排列的帧：

```json
"animation_name": {
  "frames": [
    {"rect": [0, 0, 32, 32]},
    {"rect": [32, 0, 32, 32]},
    {"rect": [64, 0, 32, 32]}
  ],
  "frame_duration": 0.1,
  "loop": true
}
```

#### 方式2: 连续帧带 (Strip)
适合规则排列的动画帧：

```json
"animation_name": {
  "strip": {
    "x": 0,           // 起始X
    "y": 0,           // 起始Y
    "width": 32,      // 帧宽度
    "height": 32,     // 帧高度
    "count": 8,       // 帧数量
    "direction": "horizontal",  // horizontal 或 vertical
    "spacing": 0      // 帧间距（可选）
  },
  "frame_duration": 0.1,
  "loop": true
}
```

## 使用示例

### 基本使用

```python
from src.resource.texture_asset import TextureAssetManager

# 创建管理器
manager = TextureAssetManager("assets")

# 加载配置
manager.load_atlas_config("images/bullet/bullet_atlas.json")

# 获取精灵
sprite = manager.get_sprite("bullet_red")
print(f"精灵大小: {sprite.width}x{sprite.height}")

# 获取精灵Surface
surface = manager.get_sprite_surface("bullet_red")

# 获取UV坐标（用于GPU渲染）
uv = manager.get_sprite_uv("bullet_red")
print(f"UV: {uv}")  # (u_left, v_top, u_right, v_bottom)
```

### 使用动画

```python
# 获取动画
anim = manager.get_animation("bullet_spin")

# 游戏循环中
time_elapsed = 0.0
while running:
    dt = clock.tick(60) / 1000.0
    time_elapsed += dt
    
    # 获取当前帧索引
    frame_idx = anim.get_frame_index_at_time(time_elapsed)
    
    # 获取当前帧UV（用于GPU渲染）
    uv = manager.get_animation_frame_uv("bullet_spin", time_elapsed)
```

### 兼容旧格式

```python
# 加载旧格式配置
manager.load_legacy_config("images/bullet1.json")
```

### 全局实例

```python
from src.resource.texture_asset import (
    init_texture_asset_manager,
    get_texture_asset_manager
)

# 初始化（通常在游戏启动时）
init_texture_asset_manager("assets")

# 在其他地方获取
manager = get_texture_asset_manager()
```

## 精灵命名规范

- 精灵可以通过短名称访问: `manager.get_sprite("bullet_red")`
- 也可以通过完整名称访问: `manager.get_sprite("atlas_name.bullet_red")`
- 当多个图集有同名精灵时，使用完整名称避免冲突

## 性能优化

1. **Surface缓存**: `get_sprite_surface()` 自动缓存裁剪后的Surface
2. **按需加载**: 只加载实际使用的图集
3. **卸载功能**: `unload_atlas(name)` 释放不需要的资源

## 与现有系统集成

新的 `TextureAssetManager` 可以与现有的 `SpriteManager` 并行使用：

```python
# 逐步迁移
old_manager = SpriteManager()
new_manager = TextureAssetManager()

# 新资产使用新系统
new_manager.load_atlas_config("images/new_bullet_atlas.json")

# 旧资产继续使用旧系统或转换
new_manager.load_legacy_config("images/bullet1.json")
```

## 图集制作建议

1. **按类型分图集**: 子弹、敌人、道具等分开
2. **合理的帧尺寸**: 统一尺寸便于批量处理
3. **留白边距**: 避免渲染时边缘采样问题
4. **2的幂次尺寸**: GPU优化（可选）

## 文件结构示例

```
assets/
├── images/
│   ├── bullet/
│   │   ├── bullet_atlas.png      # 纹理图集
│   │   └── bullet_atlas.json     # 配置文件
│   ├── enemy/
│   │   ├── enemy_atlas.png
│   │   └── enemy_atlas.json
│   └── item/
│       ├── item.png
│       └── item.json
```
