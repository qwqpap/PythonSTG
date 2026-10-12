# Stage 1 敌人预设

本目录提供 Stage 1 使用的敌人脚本。敌人的生命值、精灵、分数、碰撞半径和弹幕默认值来自 `assets/configs/enemy_presets.json`，不需要在每个敌人类中重复定义。

## 目录内容

| 文件 | 说明 |
| --- | --- |
| `fairy.py` | Stage 1 的敌人类，共 9 个类，其中 5 个使用 `PresetEnemy`。 |
| `preset_examples.py` | 预设用法示例：`AutoRedFairy`、`AutoGreenFairy`、`KedamaDiver`、`ShowcaseBossEnemy` 等。 |
| `__init__.py` | 包标记，不含代码。 |

## 敌人预设

`assets/configs/enemy_presets.json` 定义 14 个敌人预设。

| 预设 ID | 名称 | 生命值 | 分数 | 默认弹型 / 颜色 |
| --- | --- | --- | --- | --- |
| `enemy1` | 红色妖精 | 30 | 100 | `ball_s` / 红 |
| `enemy2` | 蓝色妖精 | 30 | 100 | `ball_s` / 蓝 |
| `enemy3` | 绿色妖精 | 35 | 150 | `ball_m` / 绿 |
| `enemy4` | 黄色妖精 | 35 | 150 | `ball_m` / 黄 |
| `enemy5` | 红色大妖精 | 60 | 250 | `scale_s` / 红 |
| `enemy6` | 蓝色大妖精 | 60 | 250 | `scale_s` / 蓝 |
| `enemy7` | 红色中型敌 | 80 | 300 | `ball_l` / 红 |
| `enemy8` | 蓝色中型敌 | 80 | 300 | `ball_l` / 蓝 |
| `enemy9` | 大型敌 | 150 | 500 | `ball_l` / 紫 |
| `enemy10` | 粉色妖精 | 30 | 100 | `ball_s` / 粉 |
| `enemy11` | 紫色妖精 | 30 | 100 | `ball_s` / 紫 |
| `enemy12` | 青色妖精 | 35 | 150 | `ball_m` / 青 |
| `kedama` | 毛玉 | 20 | 50 | `rice_s` / 粉 |
| `enemy_orb` | 幽灵球 | 50 | 200 | `scale_m` / 紫 |

每个预设还定义 `defaults`，其中包含 `move_speed` 和 `fire_rate`。

### 行为预设

| 预设 ID | 名称 | 行为 |
| --- | --- | --- |
| `rush_in_shoot_leave` | 冲入-射击-离开 | 从屏幕顶部飞入，停顿射击，然后飞出。 |
| `side_pass_shoot` | 横向掠过射击 | 从侧面横向飞过，边移动边射击。 |
| `circle_strafe` | 环绕射击 | 沿圆形路径移动并持续射击。 |
| `dive_attack` | 俯冲攻击 | 快速俯冲到屏幕底部，发射密集弹幕。 |
| `ambush_retreat` | 突袭-撤退 | 快速飞入，发射大量弹幕后迅速撤退。 |

配置文件还提供移动预设（`linear_down`、`sine_wave`、`spiral`）和攻击预设（`burst_8way`、`aimed_3shot`、`spiral_dense`、`random_spray`）。

## 使用预设

`PresetEnemy` 位于 `src/game/stage/preset_enemy.py`。子类通过类属性选择预设。

### 使用预设行为

```python
from src.game.stage.preset_enemy import PresetEnemy


class Enemy1Auto(PresetEnemy):
    preset_id = "enemy1"
    behavior_preset = "rush_in_shoot_leave"
```

可用的类属性：

- `preset_id`：敌人预设 ID，必填。
- `behavior_preset`：行为预设 ID。设置后，基类自动执行预设行为。
- `attack_preset`：攻击预设 ID。

生命值、精灵、分数、碰撞半径、弹幕默认值、动画和掉落物都来自预设。子类可以覆盖 `score` 和 `drops` 等属性，`fairy.py` 中的 `SideFlyFairy` 就是这样做的。

### 自定义行为

不设置 `behavior_preset` 时，脚本自行实现 `run()`，并通过 `self.defaults` 读取预设中的参数：

```python
class Enemy1Custom(PresetEnemy):
    preset_id = "enemy1"

    async def run(self):
        await self.move_to(self.x, 0.3, duration=60)
        self.fire_circle(
            count=8,
            speed=self.defaults["move_speed"],
            bullet_type=self.defaults["bullet_type"],
            color=self.defaults["bullet_color"],
        )
        await self.wait(60)
        await self.move_to(self.x, -0.2, duration=60)
```

### 在波次中生成敌人

波次使用 `Wave.spawn_enemy_class` 生成敌人实例：

```python
from src.game.stage.wave_base import Wave
from game_content.stages.stage1.enemies.fairy import SideFlyFairy


class MyWave(Wave):
    async def run(self):
        self.spawn_enemy_class(SideFlyFairy, x=0.2, y=1.0)
        self.spawn_enemy_class(SideFlyFairy, x=0.8, y=1.0)
        await self.wait(120)
```

方法签名为 `spawn_enemy_class(enemy_class, x=0.0, y=1.0)`，返回敌人实例。`enemy_class` 必须是 `EnemyScript` 的子类。实际用例见 `game_content/stages/stage1/waves/fairy_wave.py`。

也可以使用 `create_preset_enemy(preset_id, behavior=None, attack=None, overrides=None)` 直接创建实例，不需要先定义子类。

## 查询预设

```bash
python tools/enemy/list_presets.py                                  # 列出所有预设
python tools/enemy/list_presets.py --detail enemy1                  # 查看指定预设的详细信息
python tools/enemy/list_presets.py --usage enemy1 --behavior rush_in_shoot_leave
python tools/enemy/list_presets.py --export presets.json            # 导出为 JSON
```

## 纹理映射

| 预设 | 图集文件 | 精灵区域 | 循环动画帧数 |
| --- | --- | --- | --- |
| `enemy1`–`enemy4` | `assets/images/enemy/enemy1.json` | 32 × 32 | 12 |
| `enemy5`、`enemy6` | `assets/images/enemy/enemy1.json` | 48 × 32 | 12 |
| `enemy7`、`enemy8` | `assets/images/enemy/enemy1.json` | 48 × 48 | 12 |
| `enemy9` | `assets/images/enemy/enemy1.json` | 64 × 64 | 12 |
| `kedama` | `assets/images/enemy/enemy1.json` | 32 × 32 | 4 |
| `enemy_orb` | `assets/images/enemy/enemy1.json` | 32 × 32 | 4 |
| `enemy10`–`enemy12` | `assets/images/enemy/enemy2.json` | 32 × 32 | 12 |

`enemy1`–`enemy9` 还提供 `_idle`、`_move_left` 和 `_move_right` 动画，每个 4 帧。`kedama` 和 `enemy_orb` 只有单个循环动画。所有动画的播放速度都是 8 FPS。

`assets/images/enemy/enemy3.json` 提供 Ghost1–Ghost4 精灵，这些精灵不属于预设表。

## 示例与展示

| 文件 | 说明 |
| --- | --- |
| `preset_examples.py` | 四种预设用法、多阶段敌人和动态创建示例。`python game_content/stages/stage1/enemies/preset_examples.py` 可以列出全部预设。 |
| `game_content/stages/stage1/waves/enemy_showcase_wave.py` | 按顺序展示各预设的波次。该波次不参与 Stage 1 的正式流程；需要时在关卡 `run()` 中加入 `await self.run_wave(EnemyShowcaseWave)`。 |

## 注意事项

- 敌人属性来自预设，但子类中的 `hp`、`sprite`、`score` 和 `hitbox_radius` 会覆盖预设值。修改这些类属性会直接改变关卡难度。
- 配置中的 `movement_presets` 节尚未被运行时使用，详见[敌人预设系统](../../../../docs/ENEMY_PRESET_SYSTEM.md)。

## 相关文档

- [敌人预设系统](../../../../docs/ENEMY_PRESET_SYSTEM.md)
- [弹幕脚本开发指南](../../../../docs/STAGE_SCRIPTING_GUIDE.md)
