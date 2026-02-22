# strata/core/collision_groups.py
# Named collision groups — maps human-readable names to pymunk bitmask bits.
#
# Usage:
#   groups = CollisionGroups()
#   player_bit = groups.get("player")      # allocates bit 1
#   enemy_bit  = groups.get("enemy")       # allocates bit 2
#   groups.layer("player")                 # bitmask with only "player" bit
#   groups.mask("player", "ground")        # bitmask with "player" + "ground"
#
# Used by Sprite factory: Sprite.circle(..., group="player", collides_with=["enemy", "ground"])

from __future__ import annotations


class CollisionGroups:
    """Registry that maps string group names to pymunk ShapeFilter bitmask bits.

    Bits are allocated on first use, starting from bit 0.  Up to 32 unique
    groups are supported (pymunk uses unsigned 32-bit bitmasks).

    The special name ``"all"`` is reserved and always equals ``0xFFFFFFFF``
    (matches everything).  Passing ``"all"`` to ``layer()`` or ``mask()``
    returns the full bitmask.
    """

    MAX_GROUPS: int = 32

    def __init__(self) -> None:
        self._name_to_bit: dict[str, int] = {}
        self._next_bit: int = 0

    # ------------------------------------------------------------------
    # Bit allocation
    # ------------------------------------------------------------------

    def get(self, name: str) -> int:
        """Return the single-bit mask for *name*, allocating a new bit if needed."""
        if name == "all":
            return 0xFFFFFFFF
        bit = self._name_to_bit.get(name)
        if bit is not None:
            return bit
        if self._next_bit >= self.MAX_GROUPS:
            raise RuntimeError(
                f"CollisionGroups: exceeded {self.MAX_GROUPS} unique groups"
            )
        bit = 1 << self._next_bit
        self._name_to_bit[name] = bit
        self._next_bit += 1
        return bit

    # ------------------------------------------------------------------
    # Convenience: build combined bitmasks
    # ------------------------------------------------------------------

    def layer(self, *names: str) -> int:
        """Return a bitmask with bits set for each named group.

        ``layer("player")`` → single bit.
        ``layer("player", "projectile")`` → both bits ORed.
        """
        mask = 0
        for n in names:
            mask |= self.get(n)
        return mask

    def mask(self, *names: str) -> int:
        """Alias for ``layer()`` — returns an OR of the named group bits.

        Reads better when building a collision mask:
        ``collides_with = groups.mask("enemy", "ground")``.
        """
        return self.layer(*names)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def names(self) -> list[str]:
        """Return all registered group names in allocation order."""
        return sorted(self._name_to_bit, key=self._name_to_bit.get)  # type: ignore[arg-type]

    def __contains__(self, name: str) -> bool:
        return name in self._name_to_bit or name == "all"

    def __repr__(self) -> str:
        items = ", ".join(f"{n}={b:#06x}" for n, b in self._name_to_bit.items())
        return f"CollisionGroups({items})"
