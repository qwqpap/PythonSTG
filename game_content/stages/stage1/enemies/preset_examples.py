"""
使用敌人预设系统的示例

展示了多种使用预设系统的方式：
1. 使用预设ID + 自定义行为
2. 使用预设ID + 预设行为
3. 动态创建预设敌人
4. 覆盖预设属性
"""

from src.game.stage.preset_enemy import PresetEnemy, create_preset_enemy, list_available_presets


# ========== 示例1: 使用预设ID + 自定义行为 ==========
class CustomRedFairy(PresetEnemy):
    """使用 fairy_red 预设，但自定义行为"""

    preset_id = "fairy_red"

    async def run(self):
        # 从顶部飞入
        await self.move_to(self.x, 0.3, duration=60)

        # 发射 3 次圆形弹幕（使用预设的默认参数）
        for _ in range(3):
            self.fire_circle(
                count=8,
                speed=self.defaults['move_speed'],  # 使用预设的速度
                bullet_type=self.defaults['bullet_type'],  # 使用预设的弹幕类型
                color=self.defaults['bullet_color']  # 使用预设的颜色
            )
            await self.wait(self.defaults.get('fire_rate', 20))

        # 飞出屏幕
        await self.move_to(self.x, -0.2, duration=60)


# ========== 示例2: 使用预设ID + 预设行为（最简单）==========
class AutoRedFairy(PresetEnemy):
    """使用 fairy_red 预设 + rush_in_shoot_leave 行为预设"""

    preset_id = "fairy_red"
    behavior_preset = "rush_in_shoot_leave"  # 自动执行预设行为，无需写 run()


class AutoBlueFairy(PresetEnemy):
    """使用 fairy_blue 预设 + side_pass_shoot 行为预设"""

    preset_id = "fairy_blue"
    behavior_preset = "side_pass_shoot"


class AutoGreenFairy(PresetEnemy):
    """使用 fairy_green 预设 + circle_strafe 行为预设"""

    preset_id = "fairy_green"
    behavior_preset = "circle_strafe"


# ========== 示例3: 自定义行为但使用预设的攻击模式 ==========
class MixedOrb(PresetEnemy):
    """混合使用：自定义移动 + 预设攻击"""

    preset_id = "orb_red"
    attack_preset = "spiral_dense"

    async def run(self):
        # 自定义移动
        await self.move_to(0.0, 0.4, duration=60)
        await self.wait(30)

        # 使用预设的攻击模式
        if self._attack_data:
            attack_type = self._attack_data.get('type')
            params = self._attack_data.get('params', {})

            if attack_type == 'spiral':
                # 实现螺旋弹幕
                arms = params.get('arms', 3)
                bullets_per_arm = params.get('bullets_per_arm', 8)

                for _ in range(bullets_per_arm):
                    for i in range(arms):
                        angle = (360 / arms) * i + self.time * params.get('rotation_speed', 10)
                        self.fire(
                            angle=angle,
                            speed=self.defaults['move_speed'],
                            bullet_type=self.defaults['bullet_type'],
                            color=self.defaults['bullet_color']
                        )
                    await self.wait(5)

        # 飞走
        await self.move_to(self.x, -0.2, duration=60)


# ========== 示例4: 动态创建（适合编辑器使用）==========
def create_enemy_from_editor(preset_id: str, behavior_id: str, custom_hp: int = None):
    """
    从编辑器动态创建敌人类

    这个函数模拟编辑器根据用户选择创建敌人的场景：
    1. 用户从下拉菜单选择预设（preset_id）
    2. 用户从下拉菜单选择行为（behavior_id）
    3. 用户可选输入自定义生命值
    """

    overrides = {}
    if custom_hp is not None:
        overrides['hp'] = custom_hp

    # 动态创建类
    EnemyClass = create_preset_enemy(
        preset_id=preset_id,
        behavior=behavior_id,
        overrides=overrides
    )

    return EnemyClass


# ========== 使用示例 ==========
if __name__ == '__main__':
    # 列出所有可用的预设
    available = list_available_presets()
    print("可用的敌人预设:", available['enemies'])
    print("可用的行为预设:", available['behaviors'])
    print("可用的攻击预设:", available['attacks'])

    # 示例：编辑器用法
    # 用户选择了 "fairy_red" 预设 + "rush_in_shoot_leave" 行为
    EnemyClass1 = create_enemy_from_editor("fairy_red", "rush_in_shoot_leave")
    print(f"创建了敌人类: {EnemyClass1.__name__}")

    # 用户选择了 "orb_blue" 预设 + "dive_attack" 行为 + 自定义HP=100
    EnemyClass2 = create_enemy_from_editor("orb_blue", "dive_attack", custom_hp=100)
    print(f"创建了敌人类: {EnemyClass2.__name__}")

    # 实例化并查看属性
    enemy1 = EnemyClass1()
    print(f"敌人1属性: HP={enemy1.hp}, 精灵={enemy1.sprite}, 得分={enemy1.score}")

    enemy2 = EnemyClass2()
    print(f"敌人2属性: HP={enemy2.hp}, 精灵={enemy2.sprite}, 得分={enemy2.score}")


# ========== 在波次中使用预设敌人 ==========
from src.game.stage.wave_base import Wave


class PresetEnemyWave(Wave):
    """使用预设敌人的波次示例"""

    async def run(self):
        # 生成3个自动红色妖精
        for i in range(3):
            self.spawn_enemy_class(
                AutoRedFairy,  # 使用预设敌人类
                x=-0.3 + i * 0.3,
                y=1.0
            )
            await self.wait(30)

        await self.wait(120)

        # 生成5个蓝色妖精（横向掠过）
        for i in range(5):
            self.spawn_enemy_class(
                AutoBlueFairy,
                x=-0.6 if i % 2 == 0 else 0.6,  # 交替从左右出现
                y=0.6 - i * 0.1
            )
            await self.wait(20)

        await self.wait(120)

        # 动态创建强化版绿色妖精
        StrongGreenFairy = create_preset_enemy(
            preset_id="fairy_green",
            behavior="ambush_retreat",
            overrides={"hp": 70, "score": 300}
        )

        self.spawn_enemy_class(StrongGreenFairy, x=0.0, y=1.0)
        await self.wait(180)


# ========== 高级：组合多个预设 ==========
class ComboEnemy(PresetEnemy):
    """组合多个阶段的复杂敌人"""

    preset_id = "ghost_fire_red"

    async def run(self):
        # 阶段1: 进场
        await self.move_to(0.0, 0.4, duration=60)

        # 阶段2: 第一波攻击（圆形弹幕）
        for _ in range(2):
            self.fire_circle(
                count=12,
                speed=2.0,
                bullet_type=self.defaults['bullet_type'],
                color=self.defaults['bullet_color']
            )
            await self.wait(30)

        # 阶段3: 移动到另一个位置
        await self.move_to(-0.3, 0.3, duration=45)

        # 阶段4: 第二波攻击（自机狙）
        for _ in range(5):
            self.fire_at_player(
                speed=2.5,
                bullet_type=self.defaults['bullet_type'],
                color=self.defaults['bullet_color']
            )
            await self.wait(15)

        # 阶段5: 第三波攻击（扇形密集弹幕）
        self.fire_arc(
            count=16,
            speed=1.8,
            center_angle=-90,
            arc_angle=150,
            bullet_type=self.defaults['bullet_type'],
            color=self.defaults['bullet_color']
        )
        await self.wait(60)

        # 阶段6: 撤退
        await self.move_to(self.x, -0.2, duration=60)
