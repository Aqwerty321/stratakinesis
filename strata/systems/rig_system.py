# strata/systems/rig_system.py
# RIG SYSTEM — v0 STUB
#
# Rig data model is defined in components.py (MotorRig, PropertyBinding).
# Execution is deferred post-v0.  This system iterates rigs so the pipeline
# runs without errors; the actual motor / binding logic is a no-op here.

from __future__ import annotations

from strata.systems.base import System
from strata.ecs.world import World


class RigSystem(System):
    """
    Applies declarative rig components to entities.

    v0 status: stub — update() is a no-op.
    v1 will implement MotorRig execution (pymunk SimpleMotor) and
    PropertyBinding mirroring.
    """

    def update(self, world: World, dt: float) -> None:
        # TODO(v1): iterate world.get_entities_with(MotorRig) and apply motors.
        # TODO(v1): iterate world.get_entities_with(PropertyBinding) and sync attrs.
        pass
