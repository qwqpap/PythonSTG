# PySTG - Python东方Project风格射击游戏引擎

PySTG是一个正在用Python开发的东方Project风格的射击游戏引擎，使用ModernGL和Pygame实现高性能渲染。

## 主要功能

### 1. 精灵管理系统
- 自动从文件夹加载所有JSON精灵配置文件
- 支持新旧两种配置格式
- 纹理路径智能解析和缓存
- 同时支持`is_rotating`和`rotate`字段兼容旧配置

### 2. 高性能渲染引擎
- 使用ModernGL实现硬件加速渲染
- 支持精灵批处理和实例化渲染
- 透明通道支持和alpha混合
- 按纹理路径分组优化渲染性能

### 3. 子弹系统
- 高效的子弹池管理
- 支持多种子弹类型和运动轨迹
- 碰撞检测系统

### 4. 玩家控制系统
- 玩家角色渲染和控制
- 射击和移动机制
- 生命值和碰撞判定

### 5. 关卡管理系统
- 关卡场景设计和管理
- 敌人和子弹模式配置
- 关卡流程控制

### 6. 精灵配置工具
- 可视化精灵图集编辑
- 支持打开和保存JSON配置文件
- 放大预览子弹外貌
- 实时显示判定点和判定范围
- 精灵属性编辑界面

## 项目结构

```
pystg/
├── image/             # 图片资源文件夹
│   ├── UI/           # UI相关资源
│   ├── bullet/       # 子弹相关资源
│   ├── enemy/        # 敌人相关资源
│   ├── item/         # 道具相关资源
│   ├── laser/        # 激光相关资源
│   ├── misc/         # 杂项资源
│   ├── music/        # 音乐资源
│   └── player/       # 玩家相关资源
├── bullet.py         # 子弹系统
├── player.py         # 玩家系统
├── render.py         # 渲染引擎
├── sprite_manager.py # 精灵管理器
├── stage.py          # 关卡管理
├── sprite_config_tool.py # 精灵配置工具
└── simple_test.py    # 简单测试程序
```

## 如何运行

### 运行主程序
```bash
python render.py
```

### 运行精灵配置工具
```bash
python sprite_config_tool.py
```

### 运行简单测试
```bash
python simple_test.py
```

## 精灵配置格式

JSON配置文件示例：

```json
{
  "__image_filename": "bullet/bullet1.png",
  "sprites": {
    "bullet1": {
      "rect": [0, 0, 16, 16],
      "center": [8, 8],
      "radius": 8.0,
      "is_rotating": true
    },
    "bullet2": {
      "rect": [16, 0, 16, 16],
      "center": [8, 8],
      "radius": 8.0,
      "is_rotating": false
    }
  }
}
```

## 正在开发的功能

1. **UI系统** - 完善用户界面和菜单系统
2. **音效系统** - 添加音效和音乐播放功能
3. **敌人AI** - 实现更复杂的敌人行为模式
4. **弹幕编辑器** - 可视化弹幕模式设计工具
5. **存档系统** - 游戏进度保存和读取
6. **粒子系统** - 特效和粒子效果
7. **关卡编辑器** - 可视化关卡设计工具

## 依赖项

- pygame-ce
- moderngl
- numpy
- pillow
- tkinter

## 开发环境

- Python 3.12+
- Windows系统
## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request来帮助改进这个项目！
