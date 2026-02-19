# strata/rigs/gear_train.py
# GearTrainRig — a row of circle gears linked by GearJoints, with a motor.

from __future__ import annotations
import math

from strata.rigs.base import Rig, JointHandle
from strata.shapes.factory import Sprite


_PALETTE: list[tuple] = [
    (100, 180, 255, 230),
    (255, 120,  80, 230),
    ( 80, 220, 130, 230),
    (230, 190,  50, 230),
    (255, 130, 220, 230),
    (130, 210, 255, 230),
]


class GearTrainRig(Rig):
    """A row of circular gears connected by GearJoints, driven by a motor.

    Gears are placed tangentially (each pair just touching).  The GearJoint
    ratio is set so the tangential speed at the contact point matches:
    ``ratio = r[i] / r[i+1]``, meaning the larger gear turns more slowly.

    All gears are pinned to the world via PivotJoints at their centres.
    A SimpleMotor drives the first gear; all others follow via gear ratios.

    Parameters
    ----------
    radii       : list of gear radii, one per gear (left to right).
    x, y        : world position of the *first* gear's centre.
    motor_rate  : initial motor angular velocity (rad/s).
    motor_force : motor max torque (N·m).
    density     : mass density for each gear.
    colors      : optional per-gear RGBA colours (cycles through palette).

    Attributes
    ----------
    gears        : list of gear entities (left to right).
    motor        : JointHandle for the SimpleMotor — set ``.rate`` to change speed.

    Usage::

        gears = GearTrainRig(radii=[0.4, 0.8, 0.4], x=-2, y=1, motor_rate=3.0)
        game.scene.add_rig(gears)
        gears.motor.rate = 6.0   # speed up
    """

    def __init__(
        self,
        radii: list[float],
        x: float = 0.0,
        y: float = 0.0,
        motor_rate: float = 0.0,
        motor_force: float = 1e7,
        density: float = 1.0,
        colors: list[tuple] | None = None,
    ) -> None:
        super().__init__()

        if not radii:
            raise ValueError("GearTrainRig requires at least one radius")

        palette = colors or _PALETTE
        self.gears: list = []

        # Compute each gear centre: place left-to-right with tangential gaps.
        centres: list[float] = [x]
        for i in range(1, len(radii)):
            centres.append(centres[-1] + radii[i - 1] + radii[i])

        for i, r in enumerate(radii):
            gear = Sprite.circle(
                radius=r,
                x=centres[i],
                y=y,
                density=density,
                color=palette[i % len(palette)],
            )
            self._entities.append(gear)
            self.gears.append(gear)

        # Pin each gear to the world at its centre.
        for i, gear in enumerate(self.gears):
            h = JointHandle()
            self._add_spec('pivot', gear, None, h, pivot=(centres[i], y))

        # GearJoint between each adjacent pair.
        # ratio = r[i] / r[i+1]:  larger second gear → ratio < 1 → turns slower.
        for i in range(len(radii) - 1):
            ratio = radii[i] / radii[i + 1]
            h = JointHandle()
            self._add_spec(
                'gear',
                self.gears[i],
                self.gears[i + 1],
                h,
                phase=0.0,
                ratio=ratio,
            )

        # Motor on the first gear.
        motor_handle = JointHandle()
        motor_handle._pending['rate'] = motor_rate
        motor_handle._pending['max_force'] = motor_force
        self._add_spec(
            'motor', self.gears[0], None, motor_handle,
            rate=motor_rate, max_force=motor_force,
        )
        self.motor: JointHandle = motor_handle
