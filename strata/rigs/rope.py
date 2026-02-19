# strata/rigs/rope.py
# RopeRig — small circle beads connected by SlideJoints (allows slack/sag).

from __future__ import annotations

from strata.rigs.base import Rig, JointHandle
from strata.shapes.factory import Sprite


_DEFAULT_COLOR: tuple = (200, 180, 140, 230)


class RopeRig(Rig):
    """A rope of small circle beads connected by SlideJoints.

    Unlike ChainRig, SlideJoints allow the gap between beads to range from
    0 to ``spacing``, giving a natural drooping/slack appearance under gravity.

    Parameters
    ----------
    length      : number of beads.
    bead_radius : visual and collision radius of each bead.
    spacing     : maximum distance between adjacent bead centres.
    start_x/y   : world position of the first bead's centre.
    anchor      : if given, pins the first bead to this world point.
    density     : mass density of each bead.
    color       : RGBA fill colour.

    Attributes
    ----------
    beads  : list of all bead entities (first to last).
    first  : first bead entity.
    last   : last bead entity.

    Usage::

        rope = RopeRig(length=10, start_x=2, start_y=4, anchor=(2, 4))
        game.scene.add_rig(rope)
    """

    def __init__(
        self,
        length: int = 8,
        bead_radius: float = 0.08,
        spacing: float = 0.22,
        start_x: float = 0.0,
        start_y: float = 3.0,
        anchor: tuple[float, float] | None = None,
        density: float = 1.0,
        color: tuple = _DEFAULT_COLOR,
    ) -> None:
        super().__init__()
        self.beads: list = []

        for i in range(length):
            bead = Sprite.circle(
                radius=bead_radius,
                x=start_x + i * spacing,
                y=start_y,
                density=density,
                color=color,
            )
            self._entities.append(bead)
            self.beads.append(bead)

        # SlideJoint between each adjacent pair — min=0 allows beads to crowd,
        # max=spacing is their maximum separation.
        for i in range(1, length):
            h = JointHandle()
            self._add_spec(
                'slide',
                self.beads[i - 1],
                self.beads[i],
                h,
                anchor_a=(0.0, 0.0),
                anchor_b=(0.0, 0.0),
                min=0.0,
                max=float(spacing),
            )

        if anchor is not None:
            h = JointHandle()
            self._add_spec('pivot', self.beads[0], None, h, pivot=anchor)

    @property
    def first(self):
        return self.beads[0] if self.beads else None

    @property
    def last(self):
        return self.beads[-1] if self.beads else None
