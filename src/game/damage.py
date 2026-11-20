"""Detached attack facts for sparse target reactions and damage policies.

Attack pools store the source as one integer. Strings and these immutable
records are only used at the existing collision-to-actor boundary.
"""

from dataclasses import dataclass
import math
import operator


DAMAGE_SOURCE_SHOT = 0
DAMAGE_SOURCE_BOMB = 1
_SOURCE_NAMES = ('shot', 'bomb')


def damage_source_code(source):
    if isinstance(source, str):
        try:
            return _SOURCE_NAMES.index(source)
        except ValueError:
            raise ValueError("damage source must be 'shot' or 'bomb'") from None
    source = operator.index(source)
    if not 0 <= source < len(_SOURCE_NAMES):
        raise ValueError("damage source must be 'shot' or 'bomb'")
    return source


def damage_source_name(source):
    return _SOURCE_NAMES[damage_source_code(source)]


@dataclass(frozen=True)
class DamageHit:
    """Actual incoming damage, not whether the player currently has a Bomb buff."""

    amount: float
    source: str = 'shot'
    attack_index: int = -1
    attack_generation: int = -1
    region: int = 0

    def __post_init__(self):
        amount = float(self.amount)
        if not math.isfinite(amount) or amount < 0:
            raise ValueError('incoming damage must be finite and non-negative')
        object.__setattr__(self, 'amount', amount)
        object.__setattr__(self, 'source', damage_source_name(self.source))
        object.__setattr__(self, 'attack_index', operator.index(self.attack_index))
        object.__setattr__(self, 'attack_generation', operator.index(self.attack_generation))
        object.__setattr__(self, 'region', operator.index(self.region))


def dispatch_damage_hits(target_hits, *, on_hit=None):
    """Deliver one collision pass, allowing opt-in per-target aggregation.

    Normal actors retain one reaction per hit. A content Boss may implement
    ``damage_batch(tuple[DamageHit, ...])`` when its rules cap the total for a
    simulation frame. Both pool attacks and legacy continuous beams must be
    collected before calling this function; this is not a second update loop.
    """
    batches = {}
    for target, hit in target_hits:
        batch = getattr(target, 'damage_batch', None)
        if batch is None:
            target.damage(hit.amount, source=hit.source,
                          attack_index=hit.attack_index,
                          attack_generation=hit.attack_generation, region=hit.region)
            if on_hit is not None:
                on_hit(target, hit)
        else:
            key = id(target)
            if key not in batches:
                batches[key] = (target, batch, [])
            batches[key][2].append(hit)
    for target, batch, hits in batches.values():
        batch(tuple(hits))
        if on_hit is not None:
            for hit in hits:
                on_hit(target, hit)


__all__ = ['DamageHit', 'DAMAGE_SOURCE_SHOT', 'DAMAGE_SOURCE_BOMB',
           'damage_source_code', 'damage_source_name', 'dispatch_damage_hits']
