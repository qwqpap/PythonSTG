"""第二波敌人（简化测试）"""
import random


def run(ctx):
    for _ in range(5):
        x = random.uniform(-0.7, 0.7)
        ctx.create_bullet(
            x=x, y=0.9,
            angle=-90,
            speed=2.2,
            bullet_type="ball_s",
            color="green"
        )
        for _ in range(20):
            yield
    for _ in range(60):
        yield
