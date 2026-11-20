"""Run-wide gameplay inputs and scoped system time stops.

State persists across stages; time stops belong to a StageContext and are
released on its disposal. These objects never schedule projectiles or create
another game loop. Frame tasks remain the only controller scheduler.
"""

from dataclasses import dataclass, field
from typing import Callable
import math


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
    'scripts': 128,
}
DEFAULT_TIME_STOP = ('player', 'bullets', 'lasers', 'background', 'effects', 'boss_timer')
DEFAULT_TIME_SCALE = tuple(TIME_DOMAINS)


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
        self._rates = dict.fromkeys(TIME_DOMAINS, 1.0)
        self._scales = {}

    @staticmethod
    def _validate_scale(scale):
        scale = float(scale)
        if not math.isfinite(scale) or not 0.0 <= scale <= 1.0:
            raise ValueError('simulation scale must be between 0 and 1 (slow motion)')
        return scale

    def set_scale(self, scale, *domains):
        scale = self._validate_scale(scale)
        for domain in domains or DEFAULT_TIME_SCALE:
            TIME_DOMAINS[domain]
            self._rates[domain] = scale

    def scale(self, scale, *domains):
        """Scoped multiplicative slow motion. Nested leases restore their peers."""
        scale = self._validate_scale(scale)
        domains = domains or DEFAULT_TIME_SCALE
        for domain in domains:
            TIME_DOMAINS[domain]
        token = object()
        self._scales[token] = (scale, domains)
        return TimeStop(self, token)

    def sample(self):
        """One immutable-in-use snapshot for a complete physical update."""
        rates = self._rates.copy()
        for scale, domains in self._scales.values():
            for domain in domains:
                rates[domain] *= scale
        for domain, bit in TIME_DOMAINS.items():
            if self.mask & bit:
                rates[domain] = 0.0
        return rates

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
        self._scales.pop(token, None)
        self.mask = 0
        for mask in self._stops.values():
            self.mask |= mask

    def is_stopped(self, domain):
        return bool(self.mask & TIME_DOMAINS[domain])

    def clear(self):
        self._stops.clear()
        self._scales.clear()
        self._rates = dict.fromkeys(TIME_DOMAINS, 1.0)
        self.mask = 0


__all__ = ['RunState', 'TimeControl', 'TimeStop', 'TIME_DOMAINS',
           'DEFAULT_TIME_STOP', 'DEFAULT_TIME_SCALE']
