# 弹幕脚本快速参考

本文件是面向 `game_content/stages/` 手写关卡的仓库内速查卡。完整参数说明与高级范例见 [docs/STAGE_SCRIPTING_GUIDE.md](../docs/STAGE_SCRIPTING_GUIDE.md)。

> 声明式关卡编辑器工程放在 `game_content/authoring/<project_id>/`，使用 `src.authoring.dsl`，不要把这里的手写类模板直接放进编辑器工程。

## 开发约定

1. 可独立调试的 `Wave`、`SpellCard`、`NonSpell` 类建议添加 `DEBUG_BOOKMARK = True`，挂入关卡后即可在 `python main.py --debug` 中直接跳转。
2. 通过基类方法与 `self.ctx` 调用公开 Runtime API；大规模弹幕使用批量数组与共享行为阶段，避免逐弹 Python 回调。
3. 单独调试单张符卡可使用 `python tools/preview.py <脚本路径> --spell <类名>`。

## 坐标系与单位

| 项目 | 约定 |
| --- | --- |
| 水平坐标 `x` | `-1.0`（左）~ `+1.0`（右），`0.0` 为中心 |
| 垂直坐标 `y` | `-1.167`（底）~ `+1.167`（顶），`0.0` 为中心；Boss 常在 `y ∈ [0.3, 0.8]` |
| 角度 | 度（°）：`0` 右、`90` 上、`-90` 下、`180` 左 |
| 时间 | 60 Hz 仿真帧（30 帧 = 0.5 秒，60 帧 = 1 秒） |
| 敌弹 `speed` | 作者速度标度（传入池前自动除以 60）；慢弹 ~1.5、普通 ~2.5、快弹 ~4.0+ |
| 移动/粒子/激光速度 | 世界归一化单位/秒 |

## 最小模板

### 符卡 / 非符

```python
from src.game.stage.spellcard import SpellCard


class MySpell(SpellCard):
    name = "属性「符卡名」"
    hp = 1200
    time_limit = 60
    bonus = 1000000
    DEBUG_BOOKMARK = True

    async def setup(self):
        await self.boss.move_to(0.0, 0.65, duration=45)

    async def run(self):
        angle = 0
        while True:
            self.fire_circle(count=16, speed=2.0, start_angle=angle, bullet_type="ball_m", color="red")
            angle += 10
            await self.wait(30)


spellcard = MySpell
```

### 在 `stage_script.py` 注册 Boss

```python
from src.game.stage.stage_base import BossDef
from src.game.stage.boss_base import nonspell, spellcard

boss = BossDef(
    id="star_boss",
    name="Star Sapphire",
    texture="star",  # 对应 {texture}_idle / _move_left / _move_right
    phases=[
        nonspell(MyNonSpell, hp=600, time=25),
        spellcard(MySpell, "星符「示例」", hp=1000, time=60, bonus=1000000),
    ],
)
```

Stage 1 可用 Boss 贴图前缀：`"luna"`、`"star"`、`"sunny"`。

## 高频 API 速查

| 类别 | 常用接口 |
| --- | --- |
| 基础发弹 | `self.fire(...)`、`self.fire_circle(...)`、`self.fire_arc(...)`、`self.fire_at_player(...)`、`self.fire_polar(...)` |
| 批量弹幕 | `ctx.create_bullets_batch(...)`、`ctx.capture_bullets(...)`、`ctx.read_bullets(...)`、`ctx.transform_bullets(...)` |
| 弹幕行为 | `ctx.set_bullet_behavior(group, stages=[...])`、`ctx.configure_bullet_birth(...)`、`ctx.run_bullet_rule(...)`、`ctx.split_bullets_on_end(...)`、`ctx.convert_bullets_on_end(...)` |
| 消弹与标签 | `self.clear_bullets(to_items=False)`、`ctx.clear_all_bullets()`、`ctx.clear_bullets_by_tag(tag)`、`ctx.bullets_by_tag_to_item(tag)`、`ctx.set_time_scale(scale, tag=...)` |
| 任务与事件 | `self.spawn_task(coro)`、`await self.parallel([...])`、`ctx.emit_event(...)`、`await ctx.wait_event(...)` |
| 移动与交互 | `await actor.move_to(x, y, duration, easing=...)`、`await actor.move_linear(dx, dy, duration)`、`actor.move_velocity(...)`、`actor.set_movement_bounds(...)`、`actor.set_interaction(...)` |
| 激光 | `ctx.create_laser(...)`、`laser.configure_motion(...)`、`laser.configure_lifecycle(...)`、`laser.sample_points(step)`、`ctx.create_bent_laser(...)`、`ctx.clear_all_lasers()` |
| 视觉演出 | `ctx.emit_particles(...)`、`actor.play_animation(...)`、`actor.attach_animation(...)`、`actor.set_visual(...)`、`ctx.attach_trail(...)`、`ctx.background.set_scene(...)`、`ctx.show_text(...)`、`ctx.show_title(...)`、`ctx.flash_screen(...)`、`ctx.shake_screen(...)` |
| 玩法与音频 | `with ctx.stop_time():`、`with ctx.slow_motion(scale):`、`await self.wait_control(frames)`、`ctx.set_player_hit_rule(...)`、`ctx.set_item_collection_rule(...)`、`ctx.play_bgm(..., loop_start_frame=..., loop_end_frame=...)` |

## 常用弹型与颜色别名

别名定义位于 `assets/bullet_aliases.json`，不要直接传内部精灵 ID（如 `arrow_big2`）。

- **常见弹型**：`ball_s`、`ball_m`、`ball_l`、`ball_light`、`grain_a`、`grain_b`、`grain_c`、`arrow_s`、`arrow_m`、`arrow_l`、`knife`、`star_s`、`star_m`、`star_l`、`needle`、`scale`、`fire`、`square`、`butterfly`、`ellipse`、`kite`、`heart`、`gun`、`mildew`、`silence`。
- **16 色**：`red`、`darkred`、`purple`、`darkpurple`、`blue`、`darkblue`、`cyan`、`darkcyan`、`green`、`darkgreen`、`yellow`、`darkyellow`、`orange`、`darkorange`、`white`、`black`（部分弹型另支持 `pink` / `gray`）。

## 对话角色立绘 Key

在 `await self.play_dialogue([...])` 中使用字典条目时，`portrait` 可选值如下：

| 角色 ID | 可用 `portrait` |
| --- | --- |
| `Hinanawi_Tenshi` | `Happy` `VeryHappy` `anger` `sad` |
| `Star_Sapphire` | `Happy` `Very_Happy` `Sad` `Anger` `embarrass` `Fail_sad` `Fail_wtf` |
| `Kaenbyou_Rin` | `Happy` `Very_happy` `Sad` `Anger` |
| `Toutetu_Yuma` | `Happy` `VeryHappy` `Sad` `anger` |
| `Sunny_Milk` | `Happy` `VeryHappy` `Sad` `Anger` `Fail_Happy` `Fail_sad` `Fail_Veryhappy` |

`Luna_Child` 暂无立绘文件，配置时会静默跳过显示。
