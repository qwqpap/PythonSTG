"""
Stage 1 敌人
"""

import math
from src.game.stage.preset_enemy import PresetEnemy


class SideFlyFairy(PresetEnemy):
    """
    沿给定方向匀速飞过屏幕、边飞边射自机狙的妖精。

    行为完全由参数决定，wave 负责确定出生位置和方向：
        - 出生位置：spawn 时传入的 x, y
        - fly_angle：飞行方向（度），默认 -60（右上方向左下飞入）
        - fly_speed：飞行速度，默认 0.008（归一化坐标/帧）
        - shoot_interval：每隔多少帧射一发自机狙
        - fly_duration：飞行总帧数，超出后敌人消失
    """
    preset_id = "enemy1"

    # 可在 wave 的 spawn_enemy_class 调用时通过子类覆盖
    fly_angle: float = -60          # 飞行方向（度），0=右，-90=上，180=左
    fly_speed: float = 0.008        # 每帧移动距离（归一化坐标）
    fly_duration: int = 300         # 飞行总帧数（超出后自动消失）
    shoot_interval: int = 15        # 每隔多少帧射一发自机狙
    bullet_speed: float = 45
    bullet_type: str = "ball_s"
    bullet_color: str = "red"

    async def run(self):
        rad = math.radians(self.fly_angle)
        dx = math.cos(rad) * self.fly_speed
        dy = math.sin(rad) * self.fly_speed

        for i in range(self.fly_duration):
            self.x += dx
            self.y += dy

            if i % self.shoot_interval == 0:
                self.fire_at_player(
                    speed=self.bullet_speed,
                    bullet_type=self.bullet_type,
                    color=self.bullet_color,
                )
            await self.wait(1)
