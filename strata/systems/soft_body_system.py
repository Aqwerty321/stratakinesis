# strata/systems/soft_body_system.py
# Manages spring-mass soft bodies: adds nodes/springs/shapes to the pymunk
# Space, syncs node positions → Visual.vertices + Transform centroid each step,
# and provides clean teardown on entity removal.
#
# Anti-inversion measures:
#   1. Internal pressure forces — compute signed surface area via shoelace,
#      push surface nodes outward along edge normals when area shrinks below
#      rest_area.  This prevents mesh collapse/inversion on impact.
#   2. Per-node velocity damping — multiplies velocity by a factor < 1 each
#      step to prevent runaway energy buildup.

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
        """Apply pressure forces, velocity damping, then sync visuals."""
        for entity in world.get_entities_with(SoftBody, Transform, Visual):
            soft: SoftBody = entity.get_component(SoftBody)
            transform: Transform = entity.get_component(Transform)
            visual: Visual = entity.get_component(Visual)

            if not soft.nodes:
                continue

            # --- 1. Internal pressure forces (anti-inversion) ---
            if soft.pressure > 0.0 and soft.rest_area > 0.0 and len(soft.surface_indices) >= 3:
                self._apply_pressure(soft, dt)

            # --- 2. Velocity damping ---
            if soft.velocity_damping < 1.0:
                for body in soft.nodes:
                    body.velocity = (
                        body.velocity.x * soft.velocity_damping,
                        body.velocity.y * soft.velocity_damping,
                    )

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

    # ------------------------------------------------------------------
    # Pressure force (volume preservation)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_pressure(soft: SoftBody, dt: float) -> None:
        """Push surface nodes outward when the mesh area drops below rest_area.

        For each edge of the surface polygon, compute its outward normal and
        apply a force proportional to ``pressure * (1 - current_area / rest_area)``
        distributed along the edge's two endpoint nodes.

        This acts like internal gas pressure: when the body compresses, it
        pushes back.  When at or above rest area, no force is applied.
        """
        indices = soft.surface_indices
        n = len(indices)
        nodes = soft.nodes

        # Current surface node positions
        positions = [(nodes[idx].position.x, nodes[idx].position.y) for idx in indices]

        current_area = _signed_area(positions)

        # If area is inverted (CW winding), use a stronger correction
        if current_area < 0:
            # Area is inverted — very strong correction
            ratio = 2.0
        else:
            ratio = 1.0 - current_area / soft.rest_area
            if ratio <= 0.0:
                return  # at or above rest area, no pressure needed

        # Clamp ratio to prevent explosive forces
        ratio = min(ratio, 3.0)
        force_magnitude = soft.pressure * ratio

        # Apply force along each edge's outward normal, split between endpoints
        for i in range(n):
            j = (i + 1) % n
            ax, ay = positions[i]
            bx, by = positions[j]

            # Edge vector
            ex, ey = bx - ax, by - ay
            edge_len = math.sqrt(ex * ex + ey * ey)
            if edge_len < 1e-8:
                continue

            # Outward normal (for CCW polygon: perpendicular pointing outward)
            nx, ny = -ey / edge_len, ex / edge_len

            # Force proportional to edge length (pressure * area-deficit * edge)
            fx = nx * force_magnitude * edge_len * 0.5
            fy = ny * force_magnitude * edge_len * 0.5

            # Apply to both endpoints of this edge
            body_i = nodes[indices[i]]
            body_j = nodes[indices[j]]
            body_i.apply_force_at_local_point((fx, fy), (0, 0))
            body_j.apply_force_at_local_point((fx, fy), (0, 0))
