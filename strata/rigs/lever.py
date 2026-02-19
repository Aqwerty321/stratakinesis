# strata/rigs/lever.py
# LeverRig — a pivoting plank pinned to the world at a configurable point.

from __future__ import annotations
import math

from strata.rigs.base import Rig, JointHandle
from strata.shapes.factory import Sprite


_DEFAULT_COLOR: tuple = (160, 130, 80, 240)


class LeverRig(Rig):
    """A pivoting plank (lever) pinned to the world at a configurable pivot.

    The pivot can be offset from the plank's centre to create an unbalanced
    lever.  Optional rotation limits clamp the swing angle.

    Parameters
    ----------
    width        : length of the plank.
    height       : thickness of the plank.
    x, y         : world position of the plank's centre.
    pivot_offset : horizontal offset of the pivot from the plank centre
                   (+ve = right).
    density      : mass density.
    color        : RGBA fill colour.
    min_angle    : if set (with max_angle), adds a RotaryLimitJoint.
    max_angle    : upper rotation bound (radians, CCW positive).

    Attributes
    ----------
    plank : the rect entity.

    Usage::

        lever = LeverRig(width=4.0, x=3, y=0, pivot_offset=0.8)
        game.scene.add_rig(lever)

        # With rotation limits (±60°):
        lever = LeverRig(width=3.0, x=0, y=0,
                         min_angle=-math.pi/3, max_angle=math.pi/3)
    """

    def __init__(
        self,
        width: float = 3.0,
        height: float = 0.2,
        x: float = 0.0,
        y: float = 0.0,
        pivot_offset: float = 0.0,
        density: float = 1.0,
        color: tuple = _DEFAULT_COLOR,
        min_angle: float | None = None,
        max_angle: float | None = None,
    ) -> None:
        super().__init__()

        self.plank = Sprite.rect(
            width=width, height=height,
            x=x, y=y,
            density=density, color=color,
        )
        self._entities.append(self.plank)

        h = JointHandle()
        self._add_spec('pivot', self.plank, None, h,
                       pivot=(x + pivot_offset, y))

        if min_angle is not None and max_angle is not None:
            h2 = JointHandle()
            self._add_spec('rot_limit', self.plank, None, h2,
                           min_angle=float(min_angle),
                           max_angle=float(max_angle))
