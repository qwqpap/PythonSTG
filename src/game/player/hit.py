"""Sparse player hit decisions and exactly-once miss settlement."""

from dataclasses import dataclass
from enum import Enum
import operator


class HitStatus(str, Enum):
    IGNORED = 'ignored'
    HANDLED = 'handled'
    PENDING = 'pending'
    MISS = 'miss'
    RESCUED = 'rescued'


@dataclass(frozen=True)
class PlayerHit:
    source: str = 'script'
    position: tuple = (0.0, 0.0)
    source_index: int = -1

    def __post_init__(self):
        # Pool/input coordinates are often NumPy scalars. Events/Trace carry
        # plain JSON scalars; don't relax the shared event schema to accept them.
        object.__setattr__(self, 'position', tuple(float(v) for v in self.position))
        object.__setattr__(self, 'source_index', int(self.source_index))


@dataclass(frozen=True)
class HitDecision:
    status: HitStatus
    invulnerability_frames: int = 0
    window_frames: int = 0
    fail_capture: bool = False

    @classmethod
    def handled(cls, *, invulnerability_frames=0, fail_capture=False):
        return cls(HitStatus.HANDLED, invulnerability_frames, 0, fail_capture)

    @classmethod
    def pending(cls, window_frames, *, fail_capture=False):
        window_frames = operator.index(window_frames)
        if window_frames <= 0:
            raise ValueError('deathbomb window must be positive')
        return cls(HitStatus.PENDING, 0, window_frames, fail_capture)


@dataclass(frozen=True)
class HitResult:
    status: HitStatus
    hit: PlayerHit
    fail_capture: bool = False

    @property
    def missed(self):
        return self.status is HitStatus.MISS


def commit_player_hits(player, stats, stage_manager=None, *, boss=None, context=None):
    """Drain real outcomes once. Handled/pending hits never reset stocks/rank."""
    results = player.drain_hit_results()
    if stage_manager is not None:
        context = stage_manager.current_context
        stage = stage_manager.current_stage
        boss = getattr(stage, '_current_boss', None) if stage is not None else None
    for result in results:
        if result.missed:
            stats.player_missed(player)
            if stage_manager is not None:
                stage_manager.notify_player_event('player.missed')
            elif context is not None:
                context.run_state.notify('player.missed')
                context.emit_event('player.missed', {'source': result.hit.source})
            if boss is not None and boss._active:
                boss.on_player_miss()
        elif result.fail_capture and boss is not None and boss._active:
            boss.invalidate_capture(result.hit.source)
        if context is not None:
            context.emit_event('player.hit.' + result.status.value, {
                'source': result.hit.source, 'position': result.hit.position,
                'source_index': result.hit.source_index,
            })
    return results
