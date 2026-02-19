# strata/systems/binding_system.py
# BindingSystem — mirrors Transform attributes between entities each frame.
# Extracted from the old RigSystem; motor logic now lives in HingeMotorRig.

from __future__ import annotations
from typing import TYPE_CHECKING

from strata.systems.base import System
from strata.ecs.components import PropertyBinding, Transform
from strata.ecs.world import World


class BindingSystem(System):
    """Applies PropertyBinding components each physics step.

    For each entity with a PropertyBinding, reads
    ``source_entity.Transform.{source_attr}`` and writes::

        entity.Transform.{target_attr} = value * scale + offset

    This is a pure-Python mirror with no pymunk involvement — useful for
    things like a non-physics dial that tracks a wheel's angle.
    """

    def update(self, world: World, dt: float) -> None:
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

            setattr(dst_transform, binding.target_attr,
                    src_value * binding.scale + binding.offset)
