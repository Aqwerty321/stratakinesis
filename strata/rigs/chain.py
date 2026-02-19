# strata/rigs/chain.py
# ChainRig — a series of rectangular links connected by PinJoints.

from __future__ import annotations

from strata.rigs.base import Rig, JointHandle
from strata.shapes.factory import Sprite


_DEFAULT_COLOR: tuple = (180, 150, 100, 230)


class ChainRig(Rig):
    """A chain of rectangular links connected by PinJoints.

    Adjacent links are pinned edge-to-edge so they can swing freely but
    maintain their relative attachment points.  An optional ``anchor``
    pins the first link to a fixed world point via a PivotJoint.

    Parameters
    ----------
    length      : number of links.
    link_width  : width (and horizontal spacing) of each link.
    link_height : height of each link.
    start_x/y   : world position of the first link's centre.
    anchor      : if given, pins the first link to this world point.
    density     : mass density for each link.
    color       : RGBA fill colour.

    Attributes
    ----------
    links  : list of all link entities (left to right).
    first  : first link entity.
    last   : last link entity.

    Usage::

        chain = ChainRig(length=6, start_x=0, start_y=4, anchor=(0, 4))
        game.scene.add_rig(chain)
    """

    def __init__(
        self,
        length: int = 6,
        link_width: float = 0.45,
        link_height: float = 0.15,
        start_x: float = 0.0,
        start_y: float = 3.0,
        anchor: tuple[float, float] | None = None,
        density: float = 1.0,
        color: tuple = _DEFAULT_COLOR,
    ) -> None:
        super().__init__()
        self.links: list = []

        for i in range(length):
            link = Sprite.rect(
                width=link_width,
                height=link_height,
                x=start_x + i * link_width,
                y=start_y,
                density=density,
                color=color,
            )
            self._entities.append(link)
            self.links.append(link)

        # PinJoint between adjacent links at their touching edges.
        half_w = link_width / 2.0
        for i in range(1, length):
            h = JointHandle()
            self._add_spec(
                'pin',
                self.links[i - 1],
                self.links[i],
                h,
                anchor_a=(half_w, 0.0),
                anchor_b=(-half_w, 0.0),
            )

        # Optional anchor: PivotJoint from first link to world.
        if anchor is not None:
            h = JointHandle()
            self._add_spec('pivot', self.links[0], None, h, pivot=anchor)

    @property
    def first(self):
        return self.links[0] if self.links else None

    @property
    def last(self):
        return self.links[-1] if self.links else None
