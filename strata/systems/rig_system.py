# strata/systems/rig_system.py
# RIG SYSTEM — v1
#
# Executes declarative rig components:
#   - MotorRig   → pymunk.SimpleMotor constraint (angular velocity drive)
#   - PropertyBinding → mirrors a Transform attribute between entities

from __future__ import annotations
from typing import TYPE_CHECKING

import pymunk

from strata.systems.base import System
from strata.ecs.components import MotorRig, PropertyBinding, Physics, Transform
from strata.ecs.world import World

if TYPE_CHECKING:
    from strata.systems.physics_system import PhysicsSystem


class RigSystem(System):
    """
    Applies declarative rig components to entities each fixed step.

    Design
    ------
    MotorRig:
        On first update for an entity, creates a ``pymunk.SimpleMotor``
        between the entity's physics body and a shared static anchor body,
        then adds it to the pymunk Space.  Subsequent updates adjust the
        motor's ``rate`` and ``max_force`` without recreating the constraint.

    PropertyBinding:
        Each step, reads ``source_entity.Transform.{source_attr}`` and
        writes the scaled+offset value to ``entity.Transform.{target_attr}``.
        Pure Python — no pymunk involvement.

    Parameters
    ----------
    physics_system : injected by Game so we can add constraints to the Space.
    """

    def __init__(self, physics_system: "PhysicsSystem") -> None:
        self._physics = physics_system
        # One shared static body that anchors all motor constraints.
        # It is never added to the space as a body (static bodies in pymunk
        # can exist without being added), which is intentional.
        self._world_anchor: pymunk.Body = pymunk.Body(body_type=pymunk.Body.STATIC)

    # ------------------------------------------------------------------
    # System update
    # ------------------------------------------------------------------

    def update(self, world: World, dt: float) -> None:
        self._update_motor_rigs(world)
        self._update_property_bindings(world)

    # ------------------------------------------------------------------
    # MotorRig execution
    # ------------------------------------------------------------------

    def _update_motor_rigs(self, world: World) -> None:
        for entity in world.get_entities_with(MotorRig, Physics):
            rig: MotorRig = entity.get_component(MotorRig)
            phys: Physics = entity.get_component(Physics)

            if phys.body is None or phys.is_static:
                continue

            # Create constraint on first encounter
            if rig._constraint is None:
                rig._anchor_body = self._world_anchor
                constraint = pymunk.SimpleMotor(phys.body, self._world_anchor, rig.target_rate)
                constraint.max_force = rig.max_force
                self._physics.space.add(constraint)
                rig._constraint = constraint

            # Update rate and force every step (allows live changes)
            rate = rig.target_rate if rig.enabled else 0.0
            rig._constraint.rate = rate
            rig._constraint.max_force = rig.max_force

    # ------------------------------------------------------------------
    # PropertyBinding execution
    # ------------------------------------------------------------------

    def _update_property_bindings(self, world: World) -> None:
        for entity in world.get_entities_with(PropertyBinding, Transform):
            binding: PropertyBinding = entity.get_component(PropertyBinding)

            if not binding.enabled:
                continue

            source = world.get_entity_by_id(binding.source_entity_id)
            if source is None:
                continue

            src_transform: Transform | None = source.get_component(Transform)
            dst_transform: Transform = entity.get_component(Transform)

            if src_transform is None:
                continue

            src_value = getattr(src_transform, binding.source_attr, None)
            if src_value is None:
                continue

            new_value = src_value * binding.scale + binding.offset
            setattr(dst_transform, binding.target_attr, new_value)

