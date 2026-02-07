"""中Boss后的敌人（简化测试）"""


def run(ctx):
    for _ in range(6):
        ctx.create_bullet(
            x=0.0, y=0.8,
            angle=-90,
            speed=2.0,
            bullet_type="ball_m",
            color="yellow"
        )
        for _ in range(15):
            yield
    for _ in range(90):
        yield
