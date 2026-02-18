# strata/systems/soft_body_system.py
# Manages spring-mass soft bodies: adds nodes/springs/shapes to the pymunk
# Space, syncs node positions → Visual.vertices + Transform centroid each step,
# and provides clean teardown on entity removal.
#
# Stability measures (position-based, not force-based):
#   1. Spring length enforcement — after each physics step, if any spring
#      has stretched beyond max_stretch × rest_length, directly correct both
#      endpoint positions back within range (XPBD-style).
#   2. Hard velocity cap — per-node speed is clamped every update.
#   3. Velocity damping — gentle multiplier each step to bleed energy.

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


# Maximum a spring may stretch relative to rest_length before position correction
_MAX_STRETCH = 1.8
# Hard speed cap for any node (world units / second)
_MAX_SPEED = 12.0


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
        """Enforce spring constraints, clamp velocities, then sync visuals."""
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

            # --- 1. Position-based spring length enforcement ---
            # If any spring is over-stretched, pull endpoints back.
            # Two passes for convergence.
            for _pass in range(2):
                for spring in soft.springs:
                    a = spring.a
                    b = spring.b
                    ax, ay = a.position
                    bx, by = b.position
                    dx = bx - ax
                    dy = by - ay
                    dist = math.sqrt(dx * dx + dy * dy)
                    max_len = spring.rest_length * _MAX_STRETCH
                    if dist > max_len and dist > 1e-8:
                        # How much to correct
                        overshoot = dist - max_len
                        nx = dx / dist
                        ny = dy / dist
                        # Split correction based on inverse mass
                        total_mass = a.mass + b.mass
                        ra = a.mass / total_mass  # heavier moves less
                        rb = b.mass / total_mass
                        half = overshoot * 0.5
                        a.position = (ax + nx * half * rb * 2, ay + ny * half * rb * 2)
                        b.position = (bx - nx * half * ra * 2, by - ny * half * ra * 2)
                        # Kill the stretch velocity component
                        va_dot = a.velocity.x * nx + a.velocity.y * ny
                        vb_dot = b.velocity.x * nx + b.velocity.y * ny
                        if va_dot < 0:  # moving away from b
                            pass
                        else:
                            a.velocity = (
                                a.velocity.x - nx * va_dot * 0.5,
                                a.velocity.y - ny * va_dot * 0.5,
                            )
                        if vb_dot > 0:  # moving away from a
                            pass
                        else:
                            b.velocity = (
                                b.velocity.x - nx * vb_dot * 0.5,
                                b.velocity.y - ny * vb_dot * 0.5,
                            )

            # --- 2. Velocity damping + hard speed clamp ---
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

            # --- 3. Compute centroid of all nodes ---
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

            # --- 4. Rebuild visual vertices ---
            new_verts = []
            for idx in soft.surface_indices:
                bx = soft.nodes[idx].position.x
                by = soft.nodes[idx].position.y
                new_verts.append((bx - cx, by - cy))
            visual.vertices = new_verts
