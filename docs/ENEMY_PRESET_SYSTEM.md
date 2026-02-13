# 敌人预设系统文档

## 概述

本项目实现了类似 LuaSTG 的敌人预设系统（style system），通过预先定义的配置文件快速创建具有特定外观和行为的敌人。这个系统将**外观配置**和**行为编写**解耦，让内容创作更加高效。

## 核心概念

### 三种预设类型

1. **敌人预设（Enemy Presets）**
   - 定义敌人的外观、生命值、得分等基础属性
   - 类似 LuaSTG 的 style 参数（1-18数字ID）
   - 示例：`fairy_red`, `orb_blue`, `ghost_fire_red`

2. **行为预设（Behavior Presets）**
   - 定义敌人的行动模式（进场-射击-离开等）
   - 可复用的行为流程
   - 示例：`rush_in_shoot_leave`, `side_pass_shoot`, `dive_attack`

3. **攻击预设（Attack Presets）**
   - 定义弹幕发射模式
   - 可组合的攻击方式
   - 示例：`burst_8way`, `aimed_3shot`, `spiral_dense`

## 使用方式

### 方式1: 预设 + 自定义行为（最灵活）

```python
from src.game.stage.preset_enemy import PresetEnemy

class CustomRedFairy(PresetEnemy):
    preset_id = "fairy_red"  # 指定预设ID

    async def run(self):
        # 自定义行为逻辑
        await self.move_to(self.x, 0.3, duration=60)

        # 使用预设的默认参数
        self.fire_circle(
            count=8,
            speed=self.defaults['move_speed'],
            bullet_type=self.defaults['bullet_type'],
            color=self.defaults['bullet_color']
        )

        await self.wait(60)
        await self.move_to(self.x, -0.2, duration=60)
```

**优点**：完全自定义行为，同时享受预设的外观配置
**适用场景**：需要独特行为的敌人

### 方式2: 预设 + 行为预设（最简单）

```python
from src.game.stage.preset_enemy import PresetEnemy

class AutoRedFairy(PresetEnemy):
    preset_id = "fairy_red"
    behavior_preset = "rush_in_shoot_leave"
    # 无需写 run() 方法！
```

**优点**：一行代码创建敌人，零行为代码
**适用场景**：标准的杂兵敌人

### 方式3: 动态创建（最适合编辑器）

```python
from src.game.stage.preset_enemy import create_preset_enemy

# 在编辑器中根据用户选择动态创建
EnemyClass = create_preset_enemy(
    preset_id="fairy_blue",
    behavior="side_pass_shoot",
    overrides={"hp": 50, "score": 200}  # 可选：覆盖默认值
)

enemy = EnemyClass()
```

**优点**：运行时动态创建，适合编辑器/工具使用
**适用场景**：可视化编辑器、关卡生成器

## 配置文件结构

配置文件位置：`assets/configs/enemy_presets.json`

### 敌人预设示例

```json
{
  "fairy_red": {
    "name": "红色妖精",
    "sprite": "enemy_fairy_red",
    "hp": 30,
    "score": 100,
    "hitbox_radius": 0.02,
    "drop": "power_small",
    "defaults": {
      "bullet_type": "ball_s",
      "bullet_color": "red",
      "move_speed": 2.0,
      "fire_rate": 20
    }
  }
}
```

### 行为预设示例

```json
{
  "rush_in_shoot_leave": {
    "name": "冲入-射击-离开",
    "description": "从屏幕顶部飞入，停顿射击，然后飞出",
    "phases": [
      {"action": "move_to", "params": {"target": "y=0.3", "duration": 60}},
      {"action": "shoot_burst", "params": {"count": 3, "interval": 20}},
      {"action": "move_to", "params": {"target": "y=-0.2", "duration": 60}}
    ]
  }
}
```

## 工具脚本

### 列出所有预设

```bash
python tools/enemy/list_presets.py
```

输出：
```
==============================================================
  可用的敌人预设
==============================================================
  • fairy_red           → 红色妖精 (HP:30, 得分:100)
  • fairy_blue          → 蓝色妖精 (HP:30, 得分:100)
  • orb_red             → 红色幽灵球 (HP:50, 得分:200)
  ...

==============================================================
  可用的行为预设
==============================================================
  • rush_in_shoot_leave → 冲入-射击-离开
    从屏幕顶部飞入，停顿射击，然后飞出
  • side_pass_shoot     → 横向掠过射击
    从侧面横向飞过,边移动边射击
  ...
```

### 查看预设详情

```bash
python tools/enemy/list_presets.py --detail fairy_red
```

### 导出为编辑器JSON

```bash
python tools/enemy/list_presets.py --export editor_presets.json
```

生成的JSON可直接用于编辑器UI的下拉菜单。

### 生成使用代码

```bash
python tools/enemy/list_presets.py --usage fairy_red --behavior rush_in_shoot_leave
```

自动生成可复制粘贴的示例代码。

## 预设属性说明

### 敌人预设属性

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `name` | string | 友好名称 | "红色妖精" |
| `sprite` | string | 精灵ID | "enemy_fairy_red" |
| `hp` | int | 生命值 | 30 |
| `score` | int | 击破得分 | 100 |
| `hitbox_radius` | float | 碰撞半径 | 0.02 |
| `drop` | string | 掉落物品 | "power_small" |
| `defaults` | object | 默认参数 | 见下表 |

### defaults 对象

| 属性 | 说明 | 示例 |
|------|------|------|
| `bullet_type` | 弹幕类型 | "ball_s" |
| `bullet_color` | 弹幕颜色 | "red" |
| `move_speed` | 移动速度 | 2.0 |
| `fire_rate` | 射击间隔（帧） | 20 |

### 行为预设阶段动作

| 动作 | 参数 | 说明 |
|------|------|------|
| `move_to` | target, duration | 移动到目标位置 |
| `move_linear` | dx, dy, duration | 线性移动 |
| `move_circle` | radius, duration, center | 圆形移动 |
| `shoot_burst` | count, interval | 连发弹幕 |
| `shoot_continuous` | count, interval | 持续射击 |
| `shoot_pattern` | pattern, count | 发射弹幕模式 |
| `wait` | duration | 等待帧数 |

## 可用的预设列表

### 敌人预设

| ID | 名称 | HP | 得分 | 特点 |
|----|------|-------|------|------|
| `fairy_red` | 红色妖精 | 30 | 100 | 基础杂兵 |
| `fairy_blue` | 蓝色妖精 | 30 | 100 | 基础杂兵 |
| `fairy_green` | 绿色妖精 | 35 | 150 | 稍强杂兵 |
| `orb_red` | 红色幽灵球 | 50 | 200 | 中型敌人 |
| `orb_blue` | 蓝色幽灵球 | 50 | 200 | 中型敌人 |
| `ghost_fire_red` | 红色火焰幽灵 | 80 | 300 | 强敌 |
| `ghost_fire_blue` | 蓝色火焰幽灵 | 80 | 300 | 强敌 |
| `kedama_pink` | 粉色毛玉 | 20 | 50 | 快速小型敌人 |

### 行为预设

| ID | 名称 | 描述 |
|----|------|------|
| `rush_in_shoot_leave` | 冲入-射击-离开 | 最经典的杂兵模式 |
| `side_pass_shoot` | 横向掠过射击 | 从侧面横向飞过 |
| `circle_strafe` | 环绕射击 | 以圆形路径移动 |
| `dive_attack` | 俯冲攻击 | 快速俯冲到底部 |
| `ambush_retreat` | 突袭-撤退 | 快速飞入后撤退 |

## 编辑器集成建议

### UI 组件设计

```
┌─────────────────────────────────┐
│ 敌人创建器                      │
├─────────────────────────────────┤
│                                 │
│ 敌人预设:  [fairy_red ▼]       │   ← 从 enemy_presets.json 加载
│                                 │
│ 行为预设:  [rush_in_shoot_leave│   ← 从 behavior_presets.json 加载
│            ▼]                   │
│                                 │
│ ┌─ 覆盖属性 ──────────────────┐│
│ │                             ││
│ │ HP:    [30 ]  得分: [100 ] ││   ← 可选：覆盖默认值
│ │                             ││
│ │ 位置:  X [0.0] Y [1.0]     ││
│ │                             ││
│ └─────────────────────────────┘│
│                                 │
│      [预览]  [创建]  [取消]    │
└─────────────────────────────────┘
```

### 数据流

```
用户选择 → 加载预设 → 预览属性 → 生成代码 → 保存到文件
   │           │          │          │          │
   │           │          │          │          └→ game_content/stages/.../
   │           │          │          │
   │           │          │          └→ create_preset_enemy(...)
   │           │          │
   │           │          └→ 显示：HP=30, 速度=2.0, 颜色=red
   │           │
   │           └→ 读取 enemy_presets.json
   │
   └→ 下拉菜单: fairy_red
```

## 性能和最佳实践

### ✅ 推荐做法

1. **复用预设**：为常见敌人类型创建预设，避免重复代码
2. **组合优于继承**：使用行为预设组合而非深度继承
3. **预加载配置**：在游戏启动时加载预设文件，而非每次创建敌人时加载
4. **命名规范**：预设ID使用 `snake_case`，类名使用 `PascalCase`

### ❌ 避免做法

1. **过度抽象**：不要为每个细微差别都创建新预设
2. **硬编码配置**：避免在代码中硬编码敌人属性
3. **循环依赖**：行为预设不应相互引用

## 扩展和自定义

### 添加新的敌人预设

1. 编辑 `assets/configs/enemy_presets.json`
2. 在 `presets` 节添加新条目
3. 运行 `python tools/enemy/list_presets.py` 验证

### 添加新的行为预设

1. 编辑 `assets/configs/enemy_presets.json`
2. 在 `behavior_presets` 节添加新条目
3. 如需新动作类型，在 `PresetEnemy._execute_behavior_preset()` 中添加处理逻辑

### 创建自定义动作

```python
# 在 PresetEnemy 类中添加新方法
async def _execute_my_custom_action(self, params: Dict[str, Any]):
    """自定义动作"""
    # 实现你的动作逻辑
    pass

# 然后在 _execute_behavior_preset() 中注册
elif action == 'my_custom_action':
    await self._execute_my_custom_action(params)
```

## 与 LuaSTG 的对比

| 特性 | LuaSTG | 本项目 |
|------|---------|--------|
| 预设标识 | 数字ID (1-18) | 字符串ID ("fairy_red") |
| 配置存储 | Lua代码 | JSON文件 |
| 行为定义 | 手写任务函数 | 预设+类方法 |
| 动态创建 | ✗ | ✓ 支持 |
| 编辑器友好 | ✗ | ✓ 高度友好 |
| 类型安全 | ✗ | ✓ Python类型提示 |

## 示例代码

完整示例请查看：
- `game_content/stages/stage1/enemies/preset_examples.py`

## 故障排除

### 问题：找不到预设

**错误**：`ValueError: 未找到预设: xxx`

**解决**：
1. 确认 `assets/configs/enemy_presets.json` 存在
2. 运行 `python tools/enemy/list_presets.py` 查看可用预设
3. 检查预设ID拼写

### 问题：行为预设不执行

**原因**：子类覆盖了 `run()` 方法

**解决**：
```python
# 错误 ❌
class MyEnemy(PresetEnemy):
    preset_id = "fairy_red"
    behavior_preset = "rush_in_shoot_leave"

    async def run(self):  # 这会覆盖默认行为！
        pass

# 正确 ✅
class MyEnemy(PresetEnemy):
    preset_id = "fairy_red"
    behavior_preset = "rush_in_shoot_leave"
    # 不要覆盖 run()，让基类处理
```

## 未来改进方向

- [ ] 支持预设继承（`base_preset` 字段）
- [ ] 可视化预设编辑器
- [ ] 预设模板导出/导入
- [ ] AI驱动的行为预设生成
- [ ] 性能分析工具（弹幕密度、难度评估）
