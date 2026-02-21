# strata/rigs/chain.py
# ChainRig — a series of rectangular links connected by PinJoints.

from __future__ import annotations

from strata.rigs.base import Rig, JointHandle
from strata.shapes.factory import Sprite


_DEFAULT_COLOR: tuple = (180, 150, 100, 230)


class ChainRig(Rig):
    """A chain of rectangular links hanging vertically from an anchor.

    Links are stacked downward from ``start_y`` so the chain starts near
    its equilibrium position.  Adjacent links are connected at their
    top/bottom edges by PinJoints (distance = 0 → free pivot).  An
    optional ``anchor`` pins the first link's top edge to a world point
    via a PivotJoint.

    Parameters
    ----------
    length      : number of links.
    link_width  : visual width of each link.
    link_height : height of each link (controls spacing down the chain).
    start_x/y   : world X and Y of the **top edge** of the first link.
    anchor      : if given, pins the first link to this world point.
    density     : mass density of each link.
    color       : RGBA fill colour.

    Attributes
    ----------
    links  : list of all link entities (top to bottom).
    first  : first (top) link entity.
    last   : last (bottom) link entity.

    Usage::

        chain = ChainRig(length=7, start_x=0, start_y=4, anchor=(0, 4))
        game.scene.add_rig(chain)
    """

    def __init__(
        self,
        length: int = 6,
        link_width: float = 0.35,
        link_height: float = 0.20,
        start_x: float = 0.0,
        start_y: float = 3.0,
        anchor: tuple[float, float] | None = None,
        density: float = 1.0,
        color: tuple = _DEFAULT_COLOR,
        damping: float = 1.0,
    ) -> None:
        super().__init__()
        self.links: list = []

        # Lay links out vertically downward so the chain starts near
        # equilibrium.  start_y is the top edge of the first link.
        half_h = link_height / 2.0
        for i in range(length):
            link = Sprite.rect(
                width=link_width,
                height=link_height,
                x=start_x,
                y=start_y - half_h - i * link_height,
                density=density,
                color=color,
                linear_damping=damping,
                angular_damping=damping,
            )
            self._entities.append(link)
            self.links.append(link)

        # PinJoint between adjacent links at their touching top/bottom edges.
        # Initial distance is 0 (edges touch), so each joint acts as a pivot.
        for i in range(1, length):
            h = JointHandle()
            self._add_spec(
                'pin',
                self.links[i - 1],
                self.links[i],
                h,
                anchor_a=(0.0, -half_h),   # bottom edge of upper link
                anchor_b=(0.0,  half_h),    # top edge  of lower link
            )

        # Optional anchor: PivotJoint from first link's top edge to world.
        if anchor is not None:
            h = JointHandle()
            self._add_spec('pivot', self.links[0], None, h, pivot=anchor)

    @property
    def first(self):
        return self.links[0] if self.links else None

    @property
    def last(self):
        return self.links[-1] if self.links else None
