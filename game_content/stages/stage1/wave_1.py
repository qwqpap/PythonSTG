"""开场小怪波次（简化测试）"""
import random


def run(ctx):
    # 简单下落弹
    for _ in range(3):
        for i in range(8):
            x = -0.7 + i * 0.2
            ctx.create_bullet(
                x=x, y=0.9,
                angle=-90,
                speed=1.8,
                bullet_type="rice",
                color="blue"
            )
        for _ in range(30):
            yield
    for _ in range(60):
        yield
