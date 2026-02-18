# strata/systems/soft_body_system.py
# Manages spring-mass soft bodies: adds nodes/springs/shapes to the pymunk
# Space, syncs node positions → Visual.vertices + Transform centroid each step,
# and provides clean teardown on entity removal.
#
# The spring network (structural + shear + bending springs) provides all
# the structural integrity.  This system only:
#   1. NaN guard — reset broken nodes.
#   2. Velocity damping + hard speed cap — prevents runaway energy.
#   3. Centroid sync + visual vertex rebuild.

from __future__ import annotations
import math
from typing import TYPE_CHECKING

import pymunk

from strata.systems.base import System
from strata.ecs.components import SoftBody, Visual, Transform
from strata.ecs.world import World

if TYPE_CHECKING:
    from strata.systems.physics_system import PhysicsSystem


def _signed_area(positions: list[tuple[float, float]]) -> float:
    """Signed area of a polygon (positive = CCW, negative = CW/inverted)."""
    n = len(positions)
    total = 0.0
    for i in range(n):
        x1, y1 = positions[i]
        x2, y2 = positions[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


# Hard speed cap for any node (world units / second)
_MAX_SPEED = 20.0


class SoftBodySystem(System):
    """Registers soft-body meshes with pymunk and keeps visuals in sync.

    Pipeline order: PhysicsSystem → **SoftBodySystem** → RigSystem → RenderSystem.

    After PhysicsSystem steps the space, this system:
      1. Computes the centroid of each soft body's node positions.
      2. Writes the centroid to ``Transform.x / .y`` (with prev snapshot).
      3. Rebuilds ``Visual.vertices`` from the surface-node positions relative
         to the new centroid.  The render system draws these directly (no
         rotation transform applied, since soft bodies deform freely).
    """

    def __init__(self, physics_system: "PhysicsSystem") -> None:
        self._physics = physics_system
        # Track which entities have been registered so we don't double-add.
        self._registered: set[int] = set()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, soft: SoftBody, entity_id: int = -1) -> None:
        """Add all bodies, springs, and surface shapes to the pymunk space.

        Also maps surface shapes → entity_id in the physics system's
        shape-to-entity lookup (for collision events).

        Self-clipping protection: all surface shapes of the same soft body
        share a non-zero ``ShapeFilter.group``, so pymunk never generates
        contacts between nodes of the same mesh.
        """
        space = self._physics.space

        for body in soft.nodes:
            space.add(body)

        for spring in soft.springs:
            space.add(spring)

        # Use entity_id as the ShapeFilter group.  Shapes with matching
        # non-zero group never collide, preventing self-clipping.
        group = entity_id if entity_id > 0 else 0
        for shape in soft.surface_shapes:
            shape.filter = pymunk.ShapeFilter(group=group)
            space.add(shape)
            if entity_id >= 0:
                self._physics._shape_to_entity[shape] = entity_id

        self._registered.add(entity_id)

    def unregister(self, soft: SoftBody, entity_id: int = -1) -> None:
        """Remove all bodies, springs, and surface shapes from the pymunk space."""
        space = self._physics.space

        for spring in soft.springs:
            if spring in space.constraints:
                space.remove(spring)

        for shape in soft.surface_shapes:
            if shape in space.shapes:
                self._physics._shape_to_entity.pop(shape, None)
                space.remove(shape)

        for body in soft.nodes:
            if body in space.bodies:
                space.remove(body)

        self._registered.discard(entity_id)

    # ------------------------------------------------------------------
    # System update
    # ------------------------------------------------------------------

    def update(self, world: World, dt: float) -> None:
        """Clamp velocities, sync centroid + visual vertices each step.

        The spring network (structural + shear + bending) does all the
        structural work via pymunk's DampedSpring solver.  This method only
        applies safety clamps and syncs the ECS components.
        """
        for entity in world.get_entities_with(SoftBody, Transform, Visual):
            soft: SoftBody = entity.get_component(SoftBody)
            transform: Transform = entity.get_component(Transform)
            visual: Visual = entity.get_component(Visual)

            if not soft.nodes:
                continue

            # --- 0. NaN guard ---
            _has_nan = False
            for body in soft.nodes:
                px, py = body.position
                if px != px or py != py:
                    _has_nan = True
                    break
            if _has_nan:
                for body in soft.nodes:
                    body.velocity = (0, 0)
                    body.force = (0, 0)
                    px, py = body.position
                    if px != px or py != py:
                        body.position = (transform.x, transform.y)
                continue

            # --- 1. Velocity damping + hard speed clamp ---
            damp = soft.velocity_damping
            max_speed_sq = _MAX_SPEED * _MAX_SPEED
            for body in soft.nodes:
                vx = body.velocity.x * damp
                vy = body.velocity.y * damp
                speed_sq = vx * vx + vy * vy
                if speed_sq > max_speed_sq:
                    s = _MAX_SPEED / math.sqrt(speed_sq)
                    vx *= s
                    vy *= s
                body.velocity = (vx, vy)

            # --- 2. Compute centroid of all nodes ---
            cx, cy = 0.0, 0.0
            for body in soft.nodes:
                cx += body.position.x
                cy += body.position.y
            n = len(soft.nodes)
            cx /= n
            cy /= n

            # Snapshot previous transform for interpolation
            transform.prev_x = transform.x
            transform.prev_y = transform.y
            transform.prev_angle = transform.angle

            transform.x = cx
            transform.y = cy
            transform.angle = 0.0

            # --- 3. Rebuild visual vertices ---
            new_verts = []
            for idx in soft.surface_indices:
                bx = soft.nodes[idx].position.x
                by = soft.nodes[idx].position.y
                new_verts.append((bx - cx, by - cy))
            visual.vertices = new_verts
