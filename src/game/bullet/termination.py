"""Complete termination data for sparse gameplay reactions, not debug Trace.

The pool captures subscribed tags before recycling slots.  Context consumes
these batches through the existing frame/task lifecycle.  No bullet owns a
Python callback and this module never creates gameplay objects.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, eq=False)
class FullTerminationBatch:
    """Detached termination facts; positions/velocities use the pool's units."""

    tag: int
    reason: str
    positions: np.ndarray
    angles: np.ndarray
    velocities: np.ndarray

    def __post_init__(self):
        positions = np.array(self.positions, dtype=np.float32, copy=True, order='C')
        angles = np.array(self.angles, dtype=np.float32, copy=True, order='C')
        velocities = np.array(self.velocities, dtype=np.float32, copy=True, order='C')
        if positions.ndim != 2 or positions.shape[1] != 2:
            raise ValueError('termination positions require shape (N, 2)')
        count = len(positions)
        if angles.shape != (count,) or velocities.shape != (count, 2):
            raise ValueError('termination angles and velocities must align with positions')
        for name, array in (('positions', positions), ('angles', angles),
                            ('velocities', velocities)):
            array.flags.writeable = False
            object.__setattr__(self, name, array)

    def __len__(self):
        return len(self.positions)


class TerminationQueue:
    """Token-scoped subscriptions to complete, batched bullet termination data.

    Default subscriptions accept only natural ``expired`` termination.  Each
    distinct tag/reason capture is copied once and the same immutable batch is
    shared by its subscribers.  Draining one token never consumes another's
    pending batches; unregistering or clearing discards pending work.
    """

    def __init__(self):
        self._subscriptions = {}
        self._pending = {}

    def register(self, tag, reasons=('expired',)):
        if not isinstance(tag, (int, np.integer)):
            raise TypeError('termination subscription tag must be an integer')
        if isinstance(reasons, str):
            raise TypeError('termination reasons must be a sequence of reason strings')
        reasons = frozenset(reasons)
        if not reasons or any(not isinstance(reason, str) or not reason for reason in reasons):
            raise ValueError('termination reasons must contain non-empty strings')
        token = object()
        self._subscriptions[token] = (int(tag), reasons)
        self._pending[token] = []
        return token

    def unregister(self, token):
        existed = token in self._subscriptions
        self._subscriptions.pop(token, None)
        self._pending.pop(token, None)
        return existed

    def __contains__(self, token):
        return token in self._subscriptions

    def capture(self, data, indices, reason):
        """Copy matched pool rows before recycling; return distinct tag batches."""
        if not self._subscriptions or len(indices) == 0:
            return 0
        subscribers = {}
        for token, (tag, reasons) in self._subscriptions.items():
            if reason in reasons:
                subscribers.setdefault(tag, []).append(token)
        if not subscribers:
            return 0
        indices = np.asarray(indices, dtype=np.intp)
        if indices.ndim != 1:
            raise ValueError('termination capture requires a one-dimensional index array')
        tags = data['tag'][indices]
        captured = 0
        for tag, tokens in subscribers.items():
            selected = indices[tags == tag]
            if len(selected) == 0:
                continue
            batch = FullTerminationBatch(tag, reason, data['pos'][selected],
                                         data['angle'][selected], data['vel'][selected])
            for token in tokens:
                self._pending[token].append(batch)
            captured += 1
        return captured

    def drain(self, token):
        """Return this token's pending batches, or empty after cancellation."""
        batches = self._pending.get(token)
        if not batches:
            return ()
        result = tuple(batches)
        batches.clear()
        return result

    def clear(self):
        self._subscriptions.clear()
        self._pending.clear()
