# strata/rigs/hinge_motor.py
# HingeMotorRig — pins an entity to a world point and drives its rotation.
# Replaces the old MotorRig component + RigSystem motor logic.

from __future__ import annotations
from typing import TYPE_CHECKING

from strata.rigs.base import Rig, JointHandle

if TYPE_CHECKING:
    from strata.ecs.entity import Entity


class HingeMotorRig(Rig):
    """Motor-driven hinge: pins an entity to a world pivot and spins it.

    Combines a ``PivotJoint`` (prevents translation) with a ``SimpleMotor``
    (drives angular velocity) against the world static body.

    Parameters
    ----------
    entity  : existing Sprite entity to motorize (e.g. a wheel).
    anchor  : world-space pivot point — usually the entity's centre.
    rate    : target angular velocity in rad/s (CCW positive).
    max_force: motor maximum torque (N·m).

    Usage::

        wheel = Sprite.circle(radius=0.6, x=0, y=0)
        game.scene.add_entity(wheel)
        rig = HingeMotorRig(wheel, anchor=(0, 0), rate=3.0)
        game.scene.add_rig(rig)

        # Change speed at runtime:
        rig.motor.rate = 6.0
        rig.motor.enabled = False   # zero torque (coast)
    """

    def __init__(
        self,
        entity: "Entity",
        anchor: tuple[float, float] = (0.0, 0.0),
        rate: float = 0.0,
        max_force: float = 1e7,
    ) -> None:
        super().__init__()
        # Validate that the entity has a Physics component with a body.
        from strata.ecs.components import Physics
        phys = entity.get_component(Physics)
        if phys is None or phys.body is None:
            raise ValueError(
                "HingeMotorRig requires an entity with a Physics component "
                "(created with physics=True). Got an entity without physics."
            )
        # HingeMotorRig takes an existing entity — add_rig will call
        # add_entity on it (which is idempotent if already registered).
        self._entities = [entity]

        pivot_handle = JointHandle()
        motor_handle = JointHandle()
        # Pre-stage pending values so they read back correctly before _register.
        motor_handle._pending['rate'] = rate
        motor_handle._pending['max_force'] = max_force

        self._add_spec('pivot', entity, None, pivot_handle, pivot=anchor)
        self._add_spec('motor', entity, None, motor_handle,
                       rate=rate, max_force=max_force)

        self.motor: JointHandle = motor_handle
