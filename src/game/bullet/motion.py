"""Optional array-only motion helpers for the existing bullet pool.

There are no per-bullet Python callbacks or objects here.  The default pool
kernel retains its own bounds fast path; this post-step is called only while
wrap counters exist and must run after movement, before out-of-screen culling.
"""

import math

from numba import njit


@njit(cache=True)
def wrap_axis(position, remaining, lower, upper):
    """Transport across as many edges as permitted, retaining travel surplus.

    Merely reaching an edge is not crossing it.  Spending the last permitted
    crossing leaves the bullet at its transported position; only a subsequent
    crossing falls through to the pool's ordinary out-of-screen handling.
    """
    if remaining <= 0:
        return position, remaining
    width = upper - lower
    if position > upper:
        surplus = (position - upper) / width
        crossings = remaining if surplus > remaining else int(math.ceil(surplus))
        return position - crossings * width, remaining - crossings
    if position < lower:
        surplus = (lower - position) / width
        crossings = remaining if surplus > remaining else int(math.ceil(surplus))
        return position + crossings * width, remaining - crossings
    return position, remaining


@njit(cache=True)
def post_bounds(data, wrap_remaining_x=None, wrap_remaining_y=None):
    """Apply finite wrap at the existing playfield edges, then normal culling.

    X uses [-1, 1], Y uses [-1.14, 1], matching existing bounce semantics.
    Normal out-of-screen culling keeps the existing +/-1.5 margin and bounce
    exemption.  The movement kernel must defer its cull when using this step.
    """
    active = 0
    for i in range(len(data)):
        if data[i]['alive'] == 0 or data[i]['flags'] & 20:
            continue
        if wrap_remaining_x is not None and wrap_remaining_x[i] > 0:
            x, count = wrap_axis(data[i]['pos'][0], wrap_remaining_x[i], -1.0, 1.0)
            data[i]['pos'][0] = x
            wrap_remaining_x[i] = count
        if wrap_remaining_y is not None and wrap_remaining_y[i] > 0:
            y, count = wrap_axis(data[i]['pos'][1], wrap_remaining_y[i], -1.14, 1.0)
            data[i]['pos'][1] = y
            wrap_remaining_y[i] = count
        if not data[i]['flags'] & 3:
            x, y = data[i]['pos'][0], data[i]['pos'][1]
            if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
                data[i]['alive'] = 0
        if data[i]['alive'] != 0:
            if wrap_remaining_x is not None and wrap_remaining_x[i] > 0:
                active += 1
            elif wrap_remaining_y is not None and wrap_remaining_y[i] > 0:
                active += 1
    return active
