# strata/systems/physics_system.py
# Wraps pymunk.Space.  Never exposes Space or Body through the simple API.
# Steps only at fixed_dt via the accumulator in the game loop.

from __future__ import annotations
import math

import pymunk

from strata.systems.base import System
from strata.ecs.components import Physics, Transform
from strata.ecs.world import World


class PhysicsSystem(System):
    """
    Manages the pymunk simulation.

    Responsibilities:
      1. Own the pymunk.Space instance.
      2. Accept new bodies/shapes from the factory (add_body / add_shape).
      3. Step the simulation exactly once per call to update().
      4. Sync each entity's Transform from its physics body after the step.
    """

    def __init__(self, gravity: tuple[float, float] = (0.0, -9.81)) -> None:
        self.space: pymunk.Space = pymunk.Space()
        self.space.gravity = gravity

    # ------------------------------------------------------------------
    # Body / shape registration (called by factory at entity creation)
    # ------------------------------------------------------------------

    def register(self, physics: Physics) -> None:
        """Add a Physics component's body and shape to the pymunk space."""
        if physics.body is not None:
            self.space.add(physics.body)
        if physics.shape is not None:
            self.space.add(physics.shape)

    # ------------------------------------------------------------------
    # System update
    # ------------------------------------------------------------------

    def update(self, world: World, dt: float) -> None:
        """Step physics then sync Transforms.  dt is always FIXED_DT."""
        self.space.step(dt)
        self._sync_transforms(world)

    def _sync_transforms(self, world: World) -> None:
        """Copy body position/angle back into Transform components."""
        for entity in world.get_entities_with(Physics, Transform):
            physics: Physics = entity.get_component(Physics)
            transform: Transform = entity.get_component(Transform)

            if physics.is_static:
                # Static bodies do not move; no sync needed.
                continue

            body: pymunk.Body = physics.body

            # Snapshot current state before overwriting (used for interpolation)
            transform.prev_x = transform.x
            transform.prev_y = transform.y
            transform.prev_angle = transform.angle

            transform.x = body.position.x
            transform.y = body.position.y
            transform.angle = body.angle
