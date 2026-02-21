# strata/systems/physics_system.py
# Wraps pymunk.Space.  Never exposes Space or Body through the simple API.
# Steps only at fixed_dt via the accumulator in the game loop.

from __future__ import annotations

from dataclasses import dataclass, field

import pymunk

from strata.systems.base import System
from strata.ecs.components import Physics, Transform
from strata.ecs.world import World


# ---------------------------------------------------------------------------
# CollisionEvent
# ---------------------------------------------------------------------------

@dataclass
class CollisionEvent:
    """A single collision begin or separation event between two entities.

    ``entity_a_id`` and ``entity_b_id`` are the ECS entity IDs of the shapes
    that collided.  Either may be -1 if the shape was not registered (e.g.
    a sensor-only body or a shape added directly to the space).

    ``normal`` is the collision normal unit vector pointing from B toward A.
    For separation events the contact points are gone, so ``normal`` defaults
    to ``(0.0, 0.0)``.
    """
    entity_a_id: int
    entity_b_id: int
    normal: tuple[float, float] = field(default=(0.0, 0.0))


# ---------------------------------------------------------------------------
# PhysicsSystem
# ---------------------------------------------------------------------------

class PhysicsSystem(System):
    """
    Manages the pymunk simulation.

    Responsibilities:
      1. Own the pymunk.Space instance.
      2. Accept new bodies/shapes from the factory via register().
      3. Apply collision layer/mask (ShapeFilter) on registration.
      4. Map pymunk shapes back to ECS entity IDs for collision callbacks.
      5. Buffer CollisionEvent objects during space.step(); Game.run() drains them.
      6. Step the simulation exactly once per call to update().
      7. Sync each entity's Transform from its physics body after the step.
    """

    def __init__(
        self,
        gravity: tuple[float, float] = (0.0, -9.81),
        substeps: int = 1,
    ) -> None:
        self.space: pymunk.Space = pymunk.Space()
        self.space.gravity = gravity
        self.substeps: int = max(1, substeps)

        # shape → entity ID; populated in register()
        self._shape_to_entity: dict[pymunk.Shape, int] = {}

        # Collision event buffers; drained by Game after each physics step.
        self._begin_events: list[CollisionEvent] = []
        self._end_events: list[CollisionEvent] = []

        # Post-substep callbacks — called after every space.step().
        # Used by SoftBodySystem for per-substep COM momentum correction.
        self._post_substep_hooks: list = []

        # Shared static body used as world anchor by all Rigs.
        # Lazily created on first access.
        self._static_body: pymunk.Body | None = None

        # Register a default collision handler to capture all pair events.
        # pymunk 7 API: space.on_collision(None, None, begin=fn, separate=fn)
        # None, None = wildcard (any collision type pair).
        self.space.on_collision(
            None,
            None,
            begin=self._on_collision_begin,
            separate=self._on_collision_separate,
        )

    # ------------------------------------------------------------------
    # Body / shape registration (called by Scene on entity add)
    # ------------------------------------------------------------------

    @property
    def static_body(self) -> pymunk.Body:
        """A shared world-space static body used as the anchor for all Rigs."""
        if self._static_body is None:
            self._static_body = pymunk.Body(body_type=pymunk.Body.STATIC)
        return self._static_body

    def register(self, physics: Physics, entity_id: int = -1) -> None:
        """Add a Physics component's body and shape to the pymunk space.

        Parameters
        ----------
        physics   : the Physics component to register.
        entity_id : the ECS entity ID; stored for collision-event lookup.
                    Defaults to -1 (unregistered) for backward compatibility.
        """
        if physics.body is not None and physics.body not in self.space.bodies:
            self.space.add(physics.body)
        if physics.shape is not None and physics.shape not in self.space.shapes:
            # Apply layer / mask bitmasks as a pymunk ShapeFilter.
            physics.shape.filter = pymunk.ShapeFilter(
                categories=physics.collision_layer,
                mask=physics.collision_mask,
            )
            self.space.add(physics.shape)
            if entity_id >= 0:
                self._shape_to_entity[physics.shape] = entity_id

    # ------------------------------------------------------------------
    # Collision event draining (called by Game.run() / Game.step())
    # ------------------------------------------------------------------

    def drain_begin_events(self) -> list[CollisionEvent]:
        """Return and clear the list of collision-begin events from the last step."""
        events = self._begin_events
        self._begin_events = []
        return events

    def drain_end_events(self) -> list[CollisionEvent]:
        """Return and clear the list of collision-end events from the last step."""
        events = self._end_events
        self._end_events = []
        return events

    # ------------------------------------------------------------------
    # Internal pymunk collision callbacks
    # ------------------------------------------------------------------

    def _on_collision_begin(
        self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: dict
    ) -> bool:
        shape_a, shape_b = arbiter.shapes
        eid_a = self._shape_to_entity.get(shape_a, -1)
        eid_b = self._shape_to_entity.get(shape_b, -1)
        cps = arbiter.contact_point_set
        n = cps.normal
        self._begin_events.append(
            CollisionEvent(eid_a, eid_b, (float(n.x), float(n.y)))
        )
        return True  # True = process the collision normally (generate impulse)

    def _on_collision_separate(
        self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: dict
    ) -> None:
        shape_a, shape_b = arbiter.shapes
        eid_a = self._shape_to_entity.get(shape_a, -1)
        eid_b = self._shape_to_entity.get(shape_b, -1)
        self._end_events.append(CollisionEvent(eid_a, eid_b))

    # ------------------------------------------------------------------
    # System update
    # ------------------------------------------------------------------

    def update(self, world: World, dt: float) -> None:
        """Step physics then sync Transforms.  dt is always FIXED_DT.

        When ``substeps > 1`` the space is stepped ``substeps`` times with
        ``dt / substeps`` each, giving the DampedSpring solver a smaller
        effective timestep.  This is essential for soft-body meshes where
        light nodes + stiff springs would otherwise be numerically unstable.
        """
        n = self.substeps
        sub_dt = dt / n
        for _ in range(n):
            self.space.step(sub_dt)
            # Run post-substep hooks (e.g. soft-body COM correction).
            for hook in self._post_substep_hooks:
                hook(sub_dt)
        self._apply_body_damping(world)
        self._sync_transforms(world)

    def _apply_body_damping(self, world: World) -> None:
        """Apply per-body linear and angular damping once per fixed step."""
        for entity in world.get_entities_with(Physics):
            phys: Physics = entity.get_component(Physics)
            if phys.is_static:
                continue
            if phys.linear_damping < 1.0:
                v = phys.body.velocity
                d = phys.linear_damping
                phys.body.velocity = (v.x * d, v.y * d)
            if phys.angular_damping < 1.0:
                phys.body.angular_velocity *= phys.angular_damping

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
