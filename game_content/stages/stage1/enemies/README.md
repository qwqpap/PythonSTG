# Stage1 敌人预设系统测试指南

## 已更新的文件

1. **assets/configs/enemy_presets.json** - 敌人预设配置
   - 14种敌人预设 (enemy1-12, kedama, enemy_orb)
   - 5种行为预设
   - 使用实际存在的纹理 (enemy1.json, enemy2.json)

2. **game_content/stages/stage1/enemies/fairy.py** - 敌人实现
   - 使用 PresetEnemy 基类
   - 展示多种使用方式（自动行为、自定义行为）
   - 包含 11 个不同的敌人类

3. **game_content/stages/stage1/waves/enemy_showcase_wave.py** - 展示波次
   - 演示各种敌人类型
   - 目前使用弹幕代替敌人实例（临时）

## 可用的敌人预设

### 小型妖精 (enemy1-4)
- `enemy1` - 红色妖精 (HP: 30)
- `enemy2` - 蓝色妖精 (HP: 30)
- `enemy3` - 绿色妖精 (HP: 35)
- `enemy4` - 黄色妖精 (HP: 35)

### 中型妖精 (enemy5-6)
- `enemy5` - 红色大妖精 (HP: 60, 尺寸更大)
- `enemy6` - 蓝色大妖精 (HP: 60)

### 强力敌人 (enemy7-9)
- `enemy7` - 红色中型敌 (HP: 80, 更大尺寸)
- `enemy8` - 蓝色中型敌 (HP: 80)
- `enemy9` - 大型敌 (HP: 150, Boss级)

### 特殊敌人
- `kedama` - 毛玉 (HP: 20, 快速小型)
- `enemy_orb` - 幽灵球 (HP: 50)
- `enemy10-12` - 更多变种妖精

## 敌人类使用示例

### 方式1: 预设 + 自动行为（最简单，只需2行）

```python
class Enemy1Auto(PresetEnemy):
    preset_id = "enemy1"
    behavior_preset = "rush_in_shoot_leave"  # 自动执行预设行为
```

### 方式2: 预设 + 自定义行为

```python
class Enemy1Custom(PresetEnemy):
    preset_id = "enemy1"

    async def run(self):
        await self.move_to(self.x, 0.3, duration=60)
        self.fire_circle(
            count=8,
            speed=self.defaults['move_speed'],  # 使用预设的参数
            bullet_type=self.defaults['bullet_type'],
            color=self.defaults['bullet_color']
        )
        await self.wait(60)
        await self.move_to(self.x, -0.2, duration=60)
```

## 查看纹理

所有纹理配置在:
- `assets/images/enemy/enemy1.json` - enemy1-9, kedama, enemy_orb等
- `assets/images/enemy/enemy2.json` - enemy10-18

每个敌人都有12帧动画 (8 FPS循环播放)。

## 测试建议

要在游戏中看到这些敌人的纹理，需要：

1. **查看纹理配置**
   ```bash
   # 查看enemy1.json中的动画定义
   cat assets/images/enemy/enemy1.json | grep -A 15 '"animations"'
   ```

2. **测试预设加载**
   ```bash
   # 列出所有可用预设
   python tools/enemy/list_presets.py

   # 查看特定预设的详情
   python tools/enemy/list_presets.py --detail enemy1
   ```

3. **在关卡中使用**（需要引擎支持敌人实例生成）
   - 当前的 `enemy_showcase_wave.py` 使用弹幕模拟
   - 要看到真正的敌人纹理，需要引擎的敌人生成系统

## 纹理映射

| 预设ID | 精灵动画 | 纹理文件 | 尺寸 | 帧数 |
|--------|---------|---------|------|------|
| enemy1 | enemy1 | enemy1.png | 32x32 | 12 |
| enemy2 | enemy2 | enemy1.png | 32x32 | 12 |
| enemy3 | enemy3 | enemy1.png | 32x32 | 12 |
| enemy5 | enemy5 | enemy1.png | 48x32 | 12 |
| enemy7 | enemy7 | enemy1.png | 48x48 | 12 |
| enemy9 | enemy9 | enemy1.png | 64x64 | 12 |
| kedama | kedama | enemy1.png | 32x32 | 4 |
| enemy10 | enemy10 | enemy2.png | 32x32 | 12 |

## 下一步

1. **引擎层面**: 需要在 Wave 或 Stage 中添加 `spawn_enemy_class()` 方法
2. **关卡编辑**: 可以在 stage_script.py 中替换波次来测试
3. **可视化**: 运行游戏查看敌人动画效果

## 与 LuaSTG 的对比

```lua
-- LuaSTG 方式
enemy:init(1, hp, ...)  -- 数字ID不直观

-- PySTG 方式
class MyEnemy(PresetEnemy):
    preset_id = "enemy1"  -- 字符串ID，更清晰
    behavior_preset = "rush_in_shoot_leave"  -- 行为也可预设
```

优势:
- ✅ 使用实际存在的纹理 (enemy1-12动画)
- ✅ 预设ID和行为ID都是可读的字符串
- ✅ 支持行为预设（LuaSTG没有）
- ✅ 类型安全和IDE友好
- ✅ 易于在编辑器中使用
