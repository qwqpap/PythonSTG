"""Data-oriented bullet lifecycle facts and high-density batching gates."""

import numpy as np

from src.game.bullet.optimized_pool import OptimizedBulletPool


def test_expired_bullets_are_one_bounded_batch_with_reason_and_representatives():
    pool = OptimizedBulletPool(max_bullets=256)
    indices = pool.spawn_bullets_batch(
        positions=np.zeros((64, 2), dtype="f4"),
        angles=np.zeros(64, dtype="f4"),
        speeds=np.zeros(64, dtype="f4"),
        tag=17,
        max_lifetime=0.01,
    )
    assert len(indices) == 64
    assert pool.death_handlers == {}

    pool.update(0.02)
    batches = pool.drain_lifecycle_batches()

    assert len(batches) == 1
    batch = batches[0]
    assert batch.event_type == "bullet.terminated"
    assert batch.owner == "17"
    assert batch.reason == "expired"
    assert batch.count == 64
    assert 1 <= len(batch.representative_ids) <= 8
    assert len(pool.death_queue) == 0


def test_tag_clear_and_hit_destroyed_keep_distinct_terminal_reasons():
    pool = OptimizedBulletPool(max_bullets=32)
    cleared = pool.spawn_bullets_batch(
        positions=np.zeros((4, 2), dtype="f4"),
        angles=np.zeros(4, dtype="f4"),
        speeds=np.zeros(4, dtype="f4"),
        tag=3,
    )
    hit = pool.spawn_bullet(0.0, 0.0, 0.0, 0.0, tag=4)
    assert len(cleared) == 4 and hit >= 0

    assert pool.clear_by_tag(3, reason="owner_cancelled") == 4
    pool.kill_bullet(hit, reason="hit_destroyed")
    pool.update(0.0)
    batches = pool.drain_lifecycle_batches()

    reasons = {(batch.owner, batch.reason, batch.count) for batch in batches}
    assert ("3", "owner_cancelled", 4) in reasons
    assert ("4", "hit_destroyed", 1) in reasons


def test_clear_all_does_not_reemit_the_same_deaths_on_next_update():
    pool = OptimizedBulletPool(max_bullets=16)
    pool.spawn_bullets_batch(
        positions=np.zeros((8, 2), dtype="f4"),
        angles=np.zeros(8, dtype="f4"),
        speeds=np.zeros(8, dtype="f4"),
        tag=9,
    )

    pool.clear_all()
    first = pool.drain_lifecycle_batches()
    pool.update(0.016)
    second = pool.drain_lifecycle_batches()

    assert len(first) == 1
    assert first[0].reason == "phase_cleared"
    assert second == ()


def test_stage_context_converts_pool_batches_without_per_bullet_events():
    from src.game.stage.context import StageContext

    class Player:
        pos = (0.0, 0.0)

    pool = OptimizedBulletPool(max_bullets=32)
    context = StageContext(pool, Player())
    pool.spawn_bullets_batch(
        positions=np.zeros((12, 2), dtype="f4"),
        angles=np.zeros(12, dtype="f4"),
        speeds=np.zeros(12, dtype="f4"),
        tag=5,
    )
    pool.clear_by_tag(5, reason="bomb_cancelled")

    events = context.drain_lifecycle_events()
    assert len(events) == 1
    assert events[0].count == 12
    assert events[0].reason == "bomb_cancelled"
    assert events[0].payload["count"] == 12
