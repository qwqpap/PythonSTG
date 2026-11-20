"""Shared numeric hit geometry. Sizes are full world-space width/height.

Hitbox is sparse configuration; compiled kernels consume only scalars/arrays.
Angles on the public configuration are degrees, internal angles are radians.
"""

from dataclasses import dataclass
import math
from numba import njit

CIRCLE = 0
BOX = 1


@dataclass(frozen=True)
class Hitbox:
    kind: int = CIRCLE
    radius: float = 0.0
    size: tuple = (0.0, 0.0)
    angle: float = 0.0

    @classmethod
    def circle(cls, radius):
        if radius < 0:
            raise ValueError('hitbox radius must be non-negative')
        return cls(CIRCLE, float(radius))

    @classmethod
    def box(cls, width, height, angle=0.0):
        if width <= 0 or height <= 0:
            raise ValueError('box width/height must be positive')
        return cls(BOX, 0.0, (float(width), float(height)), float(angle))


def hitbox_values(hitbox, radius=0.0):
    if hitbox is None:
        return CIRCLE, float(radius), (0.0, 0.0), 0.0
    return (hitbox.kind, hitbox.radius,
            (hitbox.size[0] * .5, hitbox.size[1] * .5), math.radians(hitbox.angle))


@njit(cache=True, inline='always')
def circle_box(cx, cy, radius, bx, by, hx, hy, angle):
    ca, sa = math.cos(angle), math.sin(angle)
    dx, dy = cx - bx, cy - by
    lx, ly = abs(dx * ca + dy * sa), abs(-dx * sa + dy * ca)
    if radius == 0.0:
        return lx < hx and ly < hy
    qx, qy = max(0.0, lx - hx), max(0.0, ly - hy)
    return qx * qx + qy * qy < radius * radius


@njit(cache=True, inline='always')
def boxes_overlap(ax, ay, ahx, ahy, aa, bx, by, bhx, bhy, ba):
    ca, sa, cb, sb = math.cos(aa), math.sin(aa), math.cos(ba), math.sin(ba)
    dx, dy = bx - ax, by - ay
    for k in range(4):
        if k == 0:
            ux, uy = ca, sa
        elif k == 1:
            ux, uy = -sa, ca
        elif k == 2:
            ux, uy = cb, sb
        else:
            ux, uy = -sb, cb
        ra = ahx * abs(ux * ca + uy * sa) + ahy * abs(-ux * sa + uy * ca)
        rb = bhx * abs(ux * cb + uy * sb) + bhy * abs(-ux * sb + uy * cb)
        if abs(dx * ux + dy * uy) >= ra + rb:
            return False
    return True


@njit(cache=True, inline='always')
def shapes_overlap(ax, ay, akind, aradius, ahx, ahy, aa,
                   bx, by, bkind, bradius, bhx, bhy, ba):
    if akind == CIRCLE and bkind == CIRCLE:
        dx, dy = bx - ax, by - ay
        r = aradius + bradius
        return dx * dx + dy * dy < r * r
    if akind == CIRCLE:
        return circle_box(ax, ay, aradius, bx, by, bhx, bhy, ba)
    if bkind == CIRCLE:
        return circle_box(bx, by, bradius, ax, ay, ahx, ahy, aa)
    return boxes_overlap(ax, ay, ahx, ahy, aa, bx, by, bhx, bhy, ba)


@njit(cache=True)
def polygon_box_overlap(points, bx, by, hx, hy, angle):
    """Convex laser taper/body vs oriented player box (SAT, no circle proxy)."""
    ca, sa = math.cos(angle), math.sin(angle)
    n = len(points)
    for k in range(n+2):
        if k == n:
            ux, uy = ca, sa
        elif k == n+1:
            ux, uy = -sa, ca
        else:
            j = (k+1) % n
            ux, uy = -(points[j, 1]-points[k, 1]), points[j, 0]-points[k, 0]
        if ux*ux+uy*uy < 1e-20:
            continue
        pmin, pmax = math.inf, -math.inf
        for j in range(n):
            p = points[j, 0]*ux+points[j, 1]*uy
            pmin, pmax = min(pmin, p), max(pmax, p)
        center = bx*ux+by*uy
        extent = hx*abs(ux*ca+uy*sa)+hy*abs(-ux*sa+uy*ca)
        if pmin >= center+extent or pmax <= center-extent:
            return False
    return True


@njit(cache=True, inline='always')
def _point_segment_distance_sq(px, py, ax, ay, bx, by):
    dx, dy = bx-ax, by-ay
    d = dx*dx+dy*dy
    t = max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/d)) if d > 1e-20 else 0.0
    return (px-ax-t*dx)**2+(py-ay-t*dy)**2


@njit(cache=True)
def capsule_box(ax, ay, bx, by, radius, cx, cy, hx, hy, angle):
    ca, sa = math.cos(angle), math.sin(angle)
    dx, dy = ax-cx, ay-cy
    x1, y1 = dx*ca+dy*sa, -dx*sa+dy*ca
    dx, dy = bx-cx, by-cy
    x2, y2 = dx*ca+dy*sa, -dx*sa+dy*ca
    tmin, tmax, intersects = 0.0, 1.0, True
    for axis in range(2):
        start = x1 if axis == 0 else y1
        delta = (x2-x1) if axis == 0 else (y2-y1)
        half = hx if axis == 0 else hy
        if abs(delta) < 1e-20:
            if abs(start) > half:
                intersects = False
        else:
            a, b = (-half-start)/delta, (half-start)/delta
            tmin, tmax = max(tmin, min(a, b)), min(tmax, max(a, b))
    if intersects and tmin <= tmax:
        return True
    dist = min(max(0.0, abs(x1)-hx)**2+max(0.0, abs(y1)-hy)**2,
               max(0.0, abs(x2)-hx)**2+max(0.0, abs(y2)-hy)**2)
    for k in range(4):
        px, py = (hx if k & 1 else -hx), (hy if k & 2 else -hy)
        dist = min(dist, _point_segment_distance_sq(px, py, x1, y1, x2, y2))
    return dist < radius*radius


__all__ = ['Hitbox', 'CIRCLE', 'BOX']
