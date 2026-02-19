# strata/systems/soft_body_system.py
# Manages spring-mass soft bodies: adds nodes/springs/shapes to the pymunk
# Space, syncs node positions → Visual.vertices + Transform centroid each step,
# and provides clean teardown on entity removal.
#
# Uses numpy arrays for batch processing of all node positions and velocities.
# This ensures consistent (symmetric) treatment of every node and enables a
# center-of-mass momentum correction that eliminates solver-induced drift.
#
# The spring network (structural + shear + bending springs) provides all
# the structural integrity.  This system only:
#   1. NaN guard — reset broken nodes (vectorised).
#   2. COM momentum correction — remove net drift from solver asymmetry.
#   3. Centroid sync + visual vertex rebuild (vectorised).

from __future__ import annotations
import math
from typing import TYPE_CHECKING

import pymunk

from strata.backend.array import xp
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


# Hard speed cap for any soft-body node (world units / second).
# Keep ≤ 10 to prevent spring-network energy amplification in dense meshes.
_MAX_SPEED = 8.0


def _make_velocity_func(
    damp: float, max_speed: float
) -> "Callable":
    """Return a per-substep velocity function for soft-body nodes.

    pymunk calls ``body.velocity_func`` on every ``space.step()``.  By
    applying velocity damping and speed clamping *every substep*, we prevent
    energy from building up between the post-frame damping pass in
    SoftBodySystem.update().
    """
    max_speed_sq = max_speed * max_speed

    def _vel_func(
        body: pymunk.Body,
        gravity: tuple[float, float],
        damping: float,
        dt: float,
    ) -> None:
        # Default pymunk velocity update (gravity + space.damping)
        pymunk.Body.update_velocity(body, gravity, damping, dt)
        vx = body.velocity.x * damp
        vy = body.velocity.y * damp
        speed_sq = vx * vx + vy * vy
        if speed_sq > max_speed_sq:
            s = max_speed / math.sqrt(speed_sq)
            vx *= s
            vy *= s
        body.velocity = (vx, vy)

    return _vel_func


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
        # Track soft bodies for per-substep COM correction.
        self._soft_bodies: list[SoftBody] = []
        # Register a post-substep hook so COM correction runs every
        # space.step(), not just once per frame.
        physics_system._post_substep_hooks.append(self._post_substep_com_correct)

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

        Per-substep velocity function: each node gets a custom
        ``velocity_func`` that applies damping and speed clamping on
        *every* ``space.step()`` call, not just once per frame.
        """
        space = self._physics.space

        # Create per-substep velocity function for this soft body's nodes.
        # Convert the per-frame damping to per-substep: damp^(1/substeps).
        substeps = getattr(self._physics, 'substeps', 1)
        per_step_damp = soft.velocity_damping ** (1.0 / substeps)
        vel_func = _make_velocity_func(per_step_damp, _MAX_SPEED)

        for body in soft.nodes:
            body.velocity_func = vel_func
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
        self._soft_bodies.append(soft)

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
        try:
            self._soft_bodies.remove(soft)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Per-substep COM correction (called by PhysicsSystem after each step)
    # ------------------------------------------------------------------

    def _post_substep_com_correct(self, sub_dt: float) -> None:
        """Remove net horizontal momentum from each soft body.

        pymunk's sequential collision solver creates asymmetric impulses
        across the many independent node-bodies of a soft mesh.  Correcting
        the mass-weighted mean *horizontal* velocity to zero after every
        substep prevents those impulses from accumulating into coherent
        sideways drift.

        Only the X axis is corrected; Y is left alone because gravity gives
        every node the same downward acceleration and zeroing COM-Y would
        make the body float.
        """
        for soft in self._soft_bodies:
            nodes = soft.nodes
            n = len(nodes)
            if n == 0:
                continue

            # Accumulate mass-weighted horizontal velocity
            total_mass = 0.0
            weighted_vx = 0.0
            for body in nodes:
                m = body.mass
                total_mass += m
                weighted_vx += body.velocity.x * m

            if total_mass <= 0:
                continue

            com_vx = weighted_vx / total_mass
            if abs(com_vx) < 1e-12:
                continue

            # Subtract COM horizontal drift from every node
            for body in nodes:
                body.velocity = (body.velocity.x - com_vx, body.velocity.y)

    # ------------------------------------------------------------------
    # System update
    # ------------------------------------------------------------------

    def update(self, world: World, dt: float) -> None:
        """Sync centroid + visual vertices each step, using array ops.

        After pymunk steps the space (with per-substep COM correction),
        this method:
          0. Reads all node positions into numpy arrays.
          1. NaN guard — detects and resets any broken nodes (vectorised).
          2. Computes centroid and rebuilds visual vertices (vectorised).
        """
        for entity in world.get_entities_with(SoftBody, Transform, Visual):
            soft: SoftBody = entity.get_component(SoftBody)
            transform: Transform = entity.get_component(Transform)
            visual: Visual = entity.get_component(Visual)

            n = len(soft.nodes)
            if n == 0:
                continue

            # --- 0. Batch-read positions into array ---
            pos = xp.empty((n, 2), dtype=xp.float64)
            for i, body in enumerate(soft.nodes):
                pos[i, 0] = body.position.x
                pos[i, 1] = body.position.y

            # --- 1. NaN guard (vectorised) ---
            nan_mask = xp.isnan(pos[:, 0]) | xp.isnan(pos[:, 1])
            if xp.any(nan_mask):
                for i in range(n):
                    if nan_mask[i]:
                        soft.nodes[i].position = (transform.x, transform.y)
                    soft.nodes[i].velocity = (0, 0)
                    soft.nodes[i].force = (0, 0)
                continue

            # --- 2. Compute centroid (array op) ---
            centroid = xp.mean(pos, axis=0)
            cx, cy = float(centroid[0]), float(centroid[1])

            # Snapshot previous transform for interpolation
            transform.prev_x = transform.x
            transform.prev_y = transform.y
            transform.prev_angle = transform.angle

            transform.x = cx
            transform.y = cy
            transform.angle = 0.0

            # --- 3. Rebuild visual vertices (array op) ---
            # Push each surface vertex outward by node_radius so the drawn
            # polygon matches the collision boundary (pymunk.Circle radius).
            surf_idx = soft.surface_indices
            surf_pos = pos[surf_idx]  # (S, 2) — surface node positions
            local = surf_pos - centroid[xp.newaxis, :]
            nr = soft.node_radius
            dist = xp.sqrt(local[:, 0] ** 2 + local[:, 1] ** 2)
            # Avoid division by zero for nodes at centroid
            safe_dist = xp.where(dist > 1e-9, dist, 1.0)
            expand = nr / safe_dist
            local[:, 0] += local[:, 0] * expand
            local[:, 1] += local[:, 1] * expand
            visual.vertices = [(float(local[i, 0]), float(local[i, 1]))
                               for i in range(len(surf_idx))]
