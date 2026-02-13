"""
Stage 1 敌人 - 使用预设系统

展示了多种使用预设系统的方式来创建敌人。
所有纹理来自 assets/images/enemy/enemy1.json 和 enemy2.json。
"""

from src.game.stage.preset_enemy import PresetEnemy


# ========== 使用预设 + 行为预设（最简单）==========

class Enemy1Auto(PresetEnemy):
    """enemy1 - 红色妖精 (自动行为)"""
    preset_id = "enemy1"
    behavior_preset = "rush_in_shoot_leave"


class Enemy2Auto(PresetEnemy):
    """enemy2 - 蓝色妖精 (自动行为)"""
    preset_id = "enemy2"
    behavior_preset = "side_pass_shoot"


class Enemy3Auto(PresetEnemy):
    """enemy3 - 绿色妖精 (自动行为)"""
    preset_id = "enemy3"
    behavior_preset = "rush_in_shoot_leave"


# ========== 使用预设 + 自定义行为 ==========

class Enemy1Custom(PresetEnemy):
    """enemy1 - 红色妖精 (自定义行为)"""
    preset_id = "enemy1"

    async def run(self):
        # 从上方飞入
        await self.move_to(self.x, 0.3, duration=60)

        # 发射 3 轮圆形弹幕
        for _ in range(3):
            self.fire_circle(
                count=8,
                speed=self.defaults['move_speed'],
                bullet_type=self.defaults['bullet_type'],
                color=self.defaults['bullet_color']
            )
            await self.wait(self.defaults['fire_rate'])

        # 飞出屏幕
        await self.move_to(self.x, -0.2, duration=60)


class Enemy2Custom(PresetEnemy):
    """enemy2 - 蓝色妖精 (横向掠过+自机狙)"""
    preset_id = "enemy2"

    async def run(self):
        # 横向飞入
        target_x = -self.x
        await self.move_to(target_x, self.y, duration=90)

        # 发射自机狙
        for _ in range(5):
            self.fire_at_player(
                speed=self.defaults['move_speed'],
                bullet_type=self.defaults['bullet_type'],
                color=self.defaults['bullet_color']
            )
            await self.wait(10)

        # 继续飞走
        await self.move_linear(dx=target_x * 0.5, dy=-0.3, duration=60)


class Enemy5Custom(PresetEnemy):
    """enemy5 - 红色大妖精 (更强的攻击)"""
    preset_id = "enemy5"

    async def run(self):
        # 飞入
        await self.move_to(self.x, 0.35, duration=50)

        # 停顿
        await self.wait(20)

        # 第一波：圆形弹幕
        self.fire_circle(
            count=12,
            speed=2.0,
            bullet_type=self.defaults['bullet_type'],
            color=self.defaults['bullet_color']
        )
        await self.wait(30)

        # 第二波：扇形弹幕
        self.fire_arc(
            count=10,
            speed=1.8,
            center_angle=-90,
            arc_angle=120,
            bullet_type=self.defaults['bullet_type'],
            color=self.defaults['bullet_color']
        )
        await self.wait(30)

        # 飞出
        await self.move_to(self.x, -0.2, duration=60)


class Enemy7Custom(PresetEnemy):
    """enemy7 - 红色中型敌 (强力攻击) """
    preset_id = "enemy7"

    async def run(self):
        # 缓慢飞入
        await self.move_to(0.0, 0.4, duration=80)

        # 发射 4 轮旋转弹幕
        for i in range(4):
            self.fire_circle(
                count=16,
                speed=1.5,
                start_angle=i * 15,  # 每轮旋转15度
                bullet_type=self.defaults['bullet_type'],
                color=self.defaults['bullet_color']
            )
            await self.wait(25)

        # 飞出
        await self.move_to(self.x, -0.2, duration=70)


class KedamaSwarm(PresetEnemy):
    """kedama - 毛玉 (快速下落)"""
    preset_id = "kedama"

    async def run(self):
        # 快速下落
        await self.move_linear(dx=0, dy=-0.5, duration=100)


# ========== 混合敌人（结合多种攻击模式）==========

class Enemy9Boss(PresetEnemy):
    """enemy9 - 大型敌 (类Boss行为)"""
    preset_id = "enemy9"

    async def run(self):
        # 登场
        await self.move_to(0.0, 0.45, duration=90)
        await self.wait(30)

        # 第一阶段：圆形密集弹幕
        for _ in range(3):
            self.fire_circle(
                count=20,
                speed=1.2,
                bullet_type="ball_m",
                color="purple"
            )
            await self.wait(35)

        # 移动到新位置
        await self.move_to(-0.2, 0.35, duration=60)
        await self.wait(20)

        # 第二阶段：扇形弹幕
        for _ in range(4):
            self.fire_arc(
                count=12,
                speed=1.8,
                center_angle=-90,
                arc_angle=150,
                bullet_type="ball_m",
                color="red"
            )
            await self.wait(30)

        # 移动到另一侧
        await self.move_to(0.2, 0.35, duration=60)
        await self.wait(20)

        # 第三阶段：自机狙弹幕
        for _ in range(8):
            self.fire_at_player(
                speed=2.2,
                bullet_type="ball_m",
                color="blue"
            )
            await self.wait(15)

        # 撤退
        await self.wait(30)
        await self.move_to(0.0, 1.2, duration=90)


# ========== 快捷访问（兼容旧代码）==========

# 向后兼容的别名
RedFairy = Enemy1Custom
BlueFairy = Enemy2Custom
