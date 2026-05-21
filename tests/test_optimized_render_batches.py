import numpy as np

from src.core.config import init_config
from src.core.sprite_registry import init_sprite_registry
from src.game.bullet.optimized_pool import FLAG_IS_EMITTER, OptimizedBulletPool


def test_prepare_render_data_sorted_batches_without_emitters():
    init_config()
    registry = init_sprite_registry(max_sprites=16)
    s_large_a = registry.register("large_a", "tex_a.png", (0, 0, 32, 32), (64, 64), size_category=2)
    s_small_a = registry.register("small_a", "tex_a.png", (0, 0, 8, 8), (64, 64), size_category=4)
    s_small_b = registry.register("small_b", "tex_b.png", (8, 0, 8, 8), (64, 64), size_category=4)

    pool = OptimizedBulletPool(max_bullets=8, sprite_registry=registry)
    pool.data["alive"][:5] = 1
    pool.data["flags"][:5] = 0
    pool.data["flags"][4] = FLAG_IS_EMITTER
    pool.data["sprite_idx"][:5] = [s_small_b, s_large_a, s_small_a, s_small_b, s_large_a]
    pool.data["pos"][:5] = np.array(
        [
            [0.1, 0.1],
            [0.2, 0.2],
            [0.3, 0.3],
            [0.4, 0.4],
            [0.5, 0.5],
        ],
        dtype=np.float32,
    )
    pool.data["render_angle"][:5] = np.arange(5, dtype=np.float32)

    batches = pool.prepare_render_data_sorted()

    assert [(b["category"], b["texture_path"], b["count"]) for b in batches] == [
        (2, "tex_a.png", 1),
        (4, "tex_a.png", 1),
        (4, "tex_b.png", 2),
    ]
    assert sum(b["count"] for b in batches) == 4
    np.testing.assert_allclose(batches[0]["positions"], [[0.2, 0.2]])
    np.testing.assert_allclose(batches[1]["positions"], [[0.3, 0.3]])
    np.testing.assert_allclose(batches[2]["positions"], [[0.1, 0.1], [0.4, 0.4]])
