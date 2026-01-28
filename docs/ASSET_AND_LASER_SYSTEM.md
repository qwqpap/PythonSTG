# Python STG 资产管理和激光系统

## 已完成的工作

### 1. 资产管理系统 (`src/resource/asset_manager.py`)
- 创建了类似 LuaSTG 的资产管理器
- 支持纹理、精灵配置、音频、配置文件的统一管理
- 实现了资源组（Resource Groups）用于批量加载/卸载
- 提供了全局资产管理器实例

**主要功能：**
- `load_texture()` - 加载纹理
- `load_sound()` / `play_sound()` - 音效管理
- `register_music()` / `play_music()` - 背景音乐管理
- `load_config()` - 加载JSON配置
- 资源组管理

### 2. 激光系统 (`src/game/laser.py`)
参考 LuaSTG 的激光实现，创建了两种激光：

#### 直线激光 (`Laser`)
- 三段式结构：头部、身体、尾部
- 支持展开、持续、收缩三个阶段
- 精确的碰撞检测（考虑锥形头尾）
- 可配置宽度、长度、颜色、持续时间

#### 曲线激光 (`BentLaser`)
- 沿路径弯曲的激光
- 记录历史位置形成轨迹
- 可跟随移动对象
- 支持自定义采样率

#### 激光池 (`LaserPool`)
- 统一管理所有激光对象
- 自动更新和清理
- 性能优化

### 3. 激光渲染器 (`src/render/laser_renderer.py`)
- 独立的激光渲染模块
- 支持16种预设颜色
- OpenGL 渲染优化
- 直线和曲线激光的几何体构建

### 4. 资产复制
从 LuaSTG 资源包复制了：
- 激光纹理 (`laser1.png` - `laser5.png`, `laser_bent.png`)
- 额外的子弹资源
- 存放在 `assets/images/laser/` 和 `assets/images/bullet/`

### 5. 集成到主游戏
- 更新了 `Renderer` 类以支持激光渲染
- 更新了 `main.py` 主循环：
  - 添加了 `LaserPool` 初始化
  - 集成了激光更新逻辑
  - 添加了玩家与激光的碰撞检测
- 创建了激光测试关卡 (`levels/laser_test.py`)

### 6. 测试关卡
`levels/laser_test.py` 演示了：
- 直线激光发射
- 多方向旋转激光
- 跟随轨迹的曲线激光
- 追踪玩家的激光

## 使用方法

### 使用资产管理器
```python
from src.resource.asset_manager import AssetManager

# 创建管理器
asset_manager = AssetManager(asset_root="assets")

# 加载纹理
asset_manager.load_texture("laser1", "images/laser/laser1.png")

# 获取纹理
texture = asset_manager.get_texture("laser1")

# 播放音效
asset_manager.load_sound("shoot", "audio/se/shoot.wav")
asset_manager.play_sound("shoot", volume=0.8)

# 播放音乐
asset_manager.register_music("bgm1", "audio/music/stage1.ogg")
asset_manager.play_music("bgm1", loops=-1)
```

### 创建激光
```python
from src.game.laser import LaserPool

# 创建激光池
laser_pool = LaserPool(max_lasers=100)

# 创建直线激光
laser = laser_pool.create_laser(
    x=192, y=400,           # 起点
    angle=270,              # 角度（度）
    length=300,             # 长度
    width=20,               # 宽度
    color_index=1,          # 颜色（1-16）
    expand_time=0.5,        # 展开时间
    sustain_time=2.0,       # 持续时间
    shrink_time=0.3         # 收缩时间
)

# 创建曲线激光
bent_laser = laser_pool.create_bent_laser(
    x=100, y=300,
    length=50,              # 路径点数
    width=25,
    color_index=5,
    sample_rate=4           # 采样率
)

# 更新曲线激光位置（每帧调用）
bent_laser.set_position(new_x, new_y)

# 主循环中更新
laser_pool.update(dt)
```

### 切换到激光测试关卡
在 `main.py` 的 `initialize_game_objects()` 函数中：
```python
# 注释掉原关卡
# stage_manager.add_coroutine(lambda: level_1(stage_manager, bullet_pool, player))

# 启用激光测试关卡
stage_manager.add_coroutine(lambda: laser_test_level(stage_manager, bullet_pool, player, laser_pool))
```

## 运行游戏
```bash
python main.py
```

## 激光颜色表
1. 红色
2. 橙色
3. 黄色
4. 黄绿色
5. 绿色
6. 青绿色
7. 青色
8. 天蓝色
9. 蓝色
10. 蓝紫色
11. 紫色
12. 洋红色
13. 白色
14. 浅灰色
15. 灰色
16. 金色

## 下一步建议
1. 实现激光纹理加载和应用（目前是纯色渲染）
2. 添加激光粒子效果
3. 实现更多激光类型（螺旋、脉冲等）
4. 优化激光碰撞检测性能
5. 添加激光音效
6. 创建激光编辑器工具
7. 完善资产管理器的批量加载功能
