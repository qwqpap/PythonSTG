import pytest


class DummyPlayer:
    def __init__(self, x=0.0, y=0.0):
        self.pos = [x, y]


@pytest.mark.smoke
def test_stage_context_can_spawn_regular_and_polar_bullets():
    from src.game.bullet import BulletPool
    from src.game.stage.context import StageContext

    pool = BulletPool(max_bullets=16)
    ctx = StageContext(bullet_pool=pool, player=DummyPlayer())

    regular_idx = ctx.create_bullet(
        x=0.0,
        y=0.0,
        angle=0.0,
        speed=1.0,
        bullet_type="ball_s",
        color="red",
    )
    polar_idx = ctx.create_polar_bullet(
        center=(0.0, 0.0),
        orbit_radius=0.2,
        theta=90.0,
        radial_speed=0.1,
        angular_velocity=180.0,
        bullet_type="ball_s",
        color="blue",
        collision_radius=0.03,
    )

    assert regular_idx >= 0
    assert polar_idx >= 0

    pool.update(1.0 / 60.0)

    assert pool.data["alive"][regular_idx] == 1
    assert pool.data["alive"][polar_idx] == 1
    assert polar_idx in pool.polar_motions
