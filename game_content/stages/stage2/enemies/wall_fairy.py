import random

from src.game.bullet.tags import TAG_BOMB_PROTECTED_WALL
from src.game.stage.enemy_script import EnemyScript


class WallBigFairy(EnemyScript):
    """Large side fairy for the narrow-lane wall pattern."""

    hp = 120
    sprite = "enemy2"
    score = 1500
    hitbox_radius = 0.04
    drops = {"power": 2, "point": 2}

    async def run(self):
        target_y = 0.65
        await self.move_to(self.x, target_y, duration=60)

        for frame in range(240):
            offsets = [-0.1, -0.05, 0.0, 0.05, 0.1]
            for dx in offsets:
                self.fire(
                    x=self.x + dx,
                    y=self.y,
                    angle=-90,
                    speed=40.0,
                    bullet_type="ellipse",
                    color="darkblue",
                    render_angle=-90,
                    tag=TAG_BOMB_PROTECTED_WALL,
                )

            if frame % 4 == 0:
                self.play_se("laser1", volume=0.2)

            await self.wait(4)

        await self.move_linear(0, 0.75, duration=120)


class LaneSmallFairy(EnemyScript):
    """Small lane fairy that drifts down and leaves before the next wave."""

    hp = 45
    sprite = "enemy1"
    score = 200

    async def run(self):
        move_coro = self.move_linear(0, -2.6, duration=300)

        frame = 0
        while True:
            moving = True
            try:
                next(move_coro)
            except StopIteration:
                moving = False

            if frame % 40 == 0 and frame > 10 and self.y > -0.8:
                self.play_se("tan00", volume=0.3)
                a = -90 + random.uniform(-55, 55)
                speed = random.uniform(12.2, 24.0)
                self.fire(
                    angle=a,
                    speed=speed,
                    bullet_type="ball_s",
                    color="purple",
                )

            if not moving or self.y <= -1.3:
                break

            await self.wait(1)
            frame += 1
