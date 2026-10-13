"""Run-wide gameplay inputs and scoped system time stops.

State persists across stages; time stops belong to a StageContext and are
released on its disposal. These objects never schedule projectiles or create
another game loop. Frame tasks remain the only controller scheduler.
"""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class RunState:
    """Author-visible inputs shared by all stages of one run.

    Rank adjustments are policy, not hidden defaults: the ordinary engine has
    no rank drift. Content may configure event deltas and call adjust_rank.
    TH06 uses 100 subrank units per rank, and keeps the remainder at the bounds.
    """

    difficulty: str = 'normal'
    player_shot: str = 'default'
    rank: int = 16
    min_rank: int = 0
    max_rank: int = 32
    subrank: int = 0
    rank_event_deltas: dict[str, int] = field(default_factory=dict)
    misses: int = 0
    bombs_used: int = 0
    bomb_handler: Callable | None = field(default=None, repr=False)

    def adjust_rank(self, subrank_delta: int):
        steps, self.subrank = divmod(self.subrank + subrank_delta, 100)
        self.rank = min(self.max_rank, max(self.min_rank, self.rank + steps))

    def rank_value(self, low: float, high: float) -> float:
        """TH06's rank influence is rank/32, not a min/max rescaling."""
        return low + (high - low) * self.rank / 32.0

    def notify(self, event: str):
        if event == 'player.missed':
            self.misses += 1
        elif event == 'player.bomb_used':
            self.bombs_used += 1
        self.adjust_rank(self.rank_event_deltas.get(event, 0))


TIME_DOMAINS = {
    'player': 1, 'bullets': 2, 'lasers': 4, 'items': 8,
    'background': 16, 'effects': 32, 'boss_timer': 64,
}
DEFAULT_TIME_STOP = ('player', 'bullets', 'lasers', 'background', 'effects', 'boss_timer')


class TimeStop:
    """A cancellable/context-manager lease; overlapping stops never unpause peers."""

    def __init__(self, control, token):
        self._control = control
        self._token = token

    def release(self):
        self._control.release(self._token)

    cancel = release

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


class TimeControl:
    """Sparse leases with one cached bitmask for the update hot path."""

    def __init__(self):
        self.mask = 0
        self._stops = {}

    def stop(self, *domains):
        mask = 0
        for domain in domains or DEFAULT_TIME_STOP:
            mask |= TIME_DOMAINS[domain]
        token = object()
        self._stops[token] = mask
        self.mask |= mask
        return TimeStop(self, token)

    def release(self, token):
        self._stops.pop(token, None)
        self.mask = 0
        for mask in self._stops.values():
            self.mask |= mask

    def is_stopped(self, domain):
        return bool(self.mask & TIME_DOMAINS[domain])

    def clear(self):
        self._stops.clear()
        self.mask = 0


__all__ = ['RunState', 'TimeControl', 'TimeStop', 'TIME_DOMAINS', 'DEFAULT_TIME_STOP']
