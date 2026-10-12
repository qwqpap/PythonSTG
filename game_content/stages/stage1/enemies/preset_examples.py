"""
敌人预设系统用法示例

预设配置位于 assets/configs/enemy_presets.json。本模块演示四种用法：

1. 预设外观 + 自定义行为
2. 预设外观 + 行为预设
3. 预设外观 + 攻击预设
4. 运行时动态创建敌人类（适合编辑器）

本模块只提供示例类，不参与正式关卡流程。波次示例见
game_content/stages/stage1/waves/enemy_showcase_wave.py。
"""

from src.game.stage.preset_enemy import (
    PresetEnemy,
    create_preset_enemy,
    list_available_presets,
)


# ========== 用法1：预设外观 + 自定义行为 ==========
class CustomRedFairy(PresetEnemy):
    """使用 enemy1 预设，自行编写 run()。"""

    preset_id = "enemy1"

    async def run(self):
        # 从顶部飞入
        await self.move_to(self.x, 0.3, duration=60)

        # 发射 3 轮圆形弹幕，参数取自预设
        for _ in range(3):
            self.fire_circle(
                count=8,
                speed=self._default_bullet_speed(),
                bullet_type=self.defaults["bullet_type"],
                color=self.defaults["bullet_color"],
            )
            await self.wait(self.defaults.get("fire_rate", 20))

        # 飞出屏幕
        await self.move_to(self.x, -0.2, duration=60)


# ========== 用法2：预设外观 + 行为预设 ==========
class AutoRedFairy(PresetEnemy):
    """enemy1 + 冲入-射击-离开。基类执行全部行为，不需要写 run()。"""

    preset_id = "enemy1"
    behavior_preset = "rush_in_shoot_leave"


class AutoBlueFairy(PresetEnemy):
    """enemy2 + 横向掠过射击。"""

    preset_id = "enemy2"
    behavior_preset = "side_pass_shoot"


class AutoGreenFairy(PresetEnemy):
    """enemy3 + 环绕射击。"""

    preset_id = "enemy3"
    behavior_preset = "circle_strafe"


class KedamaDiver(PresetEnemy):
    """kedama + 俯冲攻击。"""

    preset_id = "kedama"
    behavior_preset = "dive_attack"


class AutoLargeRedFairy(PresetEnemy):
    """enemy5 + 突袭-撤退。"""

    preset_id = "enemy5"
    behavior_preset = "ambush_retreat"


class AutoMidRedEnemy(PresetEnemy):
    """enemy7 + 俯冲攻击。"""

    preset_id = "enemy7"
    behavior_preset = "dive_attack"


# ========== 用法3：预设外观 + 攻击预设 ==========
class MixedOrb(PresetEnemy):
    """enemy_orb + spiral_dense：自定义移动，复用预设的攻击参数。"""

    preset_id = "enemy_orb"
    attack_preset = "spiral_dense"

    async def run(self):
        await self.move_to(0.0, 0.4, duration=60)
        await self.wait(30)

        attack = self._attack_data or {}
        params = attack.get("params", {})

        if attack.get("type") == "spiral":
            arms = params.get("arms", 3)
            bullets_per_arm = params.get("bullets_per_arm", 8)
            rotation_speed = params.get("rotation_speed", 10)

            for _ in range(bullets_per_arm):
                for i in range(arms):
                    angle = (360 / arms) * i + self.time * rotation_speed
                    self.fire(
                        angle=angle,
                        speed=self._default_bullet_speed(),
                        bullet_type=self.defaults["bullet_type"],
                        color=self.defaults["bullet_color"],
                    )
                await self.wait(5)

        await self.move_to(self.x, -0.2, duration=60)


# ========== 多阶段敌人 ==========
class ComboEnemy(PresetEnemy):
    """enemy7：进场、圆形弹幕、横向移动、自机狙、扇形弹幕、撤退。"""

    preset_id = "enemy7"

    async def run(self):
        # 阶段1：进场
        await self.move_to(0.0, 0.4, duration=60)

        # 阶段2：圆形弹幕
        for _ in range(2):
            self.fire_circle(
                count=12,
                speed=2.0,
                bullet_type=self.defaults["bullet_type"],
                color=self.defaults["bullet_color"],
            )
            await self.wait(30)

        # 阶段3：移动到另一侧
        await self.move_to(-0.3, 0.3, duration=45)

        # 阶段4：自机狙
        for _ in range(5):
            self.fire_at_player(
                speed=2.5,
                bullet_type=self.defaults["bullet_type"],
                color=self.defaults["bullet_color"],
            )
            await self.wait(15)

        # 阶段5：扇形弹幕
        self.fire_arc(
            count=16,
            speed=1.8,
            center_angle=-90,
            arc_angle=150,
            bullet_type=self.defaults["bullet_type"],
            color=self.defaults["bullet_color"],
        )
        await self.wait(60)

        # 阶段6：撤退
        await self.move_to(self.x, -0.2, duration=60)


class ShowcaseBossEnemy(PresetEnemy):
    """enemy9：资源预览用的 Boss 级敌人，血量高、弹幕密。"""

    preset_id = "enemy9"

    async def run(self):
        await self.move_to(0.0, 0.6, duration=90)

        for cycle in range(3):
            self.fire_circle(
                count=24,
                speed=1.6,
                start_angle=cycle * 7,
                bullet_type=self.defaults["bullet_type"],
                color=self.defaults["bullet_color"],
            )
            await self.wait(60)

        await self.move_to(self.x, -0.4, duration=90)


# ========== 用法4：运行时动态创建（适合编辑器） ==========
def create_enemy_from_editor(preset_id: str, behavior_id: str, custom_hp: int = None):
    """模拟编辑器按用户选择动态创建敌人类。

    1. 用户从下拉菜单选择预设（preset_id）
    2. 用户从下拉菜单选择行为（behavior_id）
    3. 用户可选输入自定义生命值

    overrides 会覆盖预设中的同名属性。
    """

    overrides = {}
    if custom_hp is not None:
        overrides["hp"] = custom_hp

    return create_preset_enemy(
        preset_id=preset_id,
        behavior=behavior_id,
        overrides=overrides,
    )


# ========== 命令行演示 ==========
if __name__ == "__main__":
    available = list_available_presets()
    print("可用的敌人预设:", available["enemies"])
    print("可用的行为预设:", available["behaviors"])
    print("可用的攻击预设:", available["attacks"])

    # 编辑器用法：预设 + 行为
    EnemyClass1 = create_enemy_from_editor("enemy1", "rush_in_shoot_leave")
    print(f"创建了敌人类: {EnemyClass1.__name__}")

    # 编辑器用法：预设 + 行为 + 自定义生命值
    EnemyClass2 = create_enemy_from_editor("enemy_orb", "dive_attack", custom_hp=100)
    print(f"创建了敌人类: {EnemyClass2.__name__}")

    enemy1 = EnemyClass1()
    print(f"敌人1属性: HP={enemy1.hp}, 精灵={enemy1.sprite}, 得分={enemy1.score}")

    enemy2 = EnemyClass2()
    print(f"敌人2属性: HP={enemy2.hp}, 精灵={enemy2.sprite}, 得分={enemy2.score}")
