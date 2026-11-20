"""Player Bomb orchestration."""

from __future__ import annotations

from .bullet.tags import BOMB_PROTECTED_TAGS


BOMB_INVINCIBLE_SECONDS = 3.0
BOMB_POWER_SECONDS = 5.0


def trigger_player_bomb(player, bullet_pool, item_pool, stage_manager=None, *, context=None, boss=None) -> int:
    """Apply the shared Bomb effect and return the number of canceled bullets."""
    if stage_manager is not None:
        context = stage_manager.current_context
        stage = stage_manager.current_stage
        boss = getattr(stage, '_current_boss', None) if stage is not None else None
    run_state = stage_manager.run_state if stage_manager is not None else (context.run_state if context else None)

    def notify():
        if stage_manager is not None:
            stage_manager.notify_player_event('player.bomb_used')
        elif context is not None:
            run_state.notify('player.bomb_used')
            context.emit_event('player.bomb_used', {'bombs_used': run_state.bombs_used})
        if boss is not None and boss._active:
            boss.on_player_bomb()

    if run_state is not None and run_state.bomb_handler is not None:
        # A content rule replaces the legacy global buff/clear/collect. Player
        # scripts still supply the actual character Bomb visuals/projectiles.
        canceled_count = int(run_state.bomb_handler(player, context))
        notify()
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

    notify()

    return canceled_count
