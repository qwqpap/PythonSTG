"""Player Bomb orchestration."""

from __future__ import annotations

from .bullet.tags import BOMB_PROTECTED_TAGS


BOMB_INVINCIBLE_SECONDS = 3.0
BOMB_POWER_SECONDS = 5.0


def trigger_player_bomb(player, bullet_pool, item_pool, stage_manager=None) -> int:
    """Apply the shared Bomb effect and return the number of canceled bullets."""
    if stage_manager is not None and stage_manager.run_state.bomb_handler is not None:
        # A content rule replaces the legacy global buff/clear/collect. Player
        # scripts still supply the actual character Bomb visuals/projectiles.
        canceled_count = int(stage_manager.run_state.bomb_handler(
            player, stage_manager.current_context,
        ))
        stage_manager.notify_player_event('player.bomb_used')
        if stage_manager.current_stage and stage_manager.current_stage._current_boss:
            stage_manager.current_stage._current_boss.on_player_bomb()
        return canceled_count
    player.invincible_timer = max(player.invincible_timer, BOMB_INVINCIBLE_SECONDS)
    player.spell_cooldown = max(player.spell_cooldown, BOMB_POWER_SECONDS)
    player.bomb_power_timer = max(
        getattr(player, "bomb_power_timer", 0.0),
        BOMB_POWER_SECONDS,
    )

    canceled_positions = bullet_pool.cancel_for_bomb(BOMB_PROTECTED_TAGS)
    canceled_count = int(canceled_positions.shape[0])
    if canceled_count > 0:
        item_pool.spawn_points_from_positions(canceled_positions, attract=True)

    item_pool.collect_all(player.pos[0], player.pos[1])

    if stage_manager:
        stage_manager.notify_player_event('player.bomb_used')

    if stage_manager and stage_manager.current_stage and stage_manager.current_stage._current_boss:
        boss = stage_manager.current_stage._current_boss
        if boss._active:
            boss.on_player_bomb()

    return canceled_count
