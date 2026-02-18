# strata/systems/soft_body_system.py
# Manages spring-mass soft bodies: adds nodes/springs/shapes to the pymunk
# Space, syncs node positions → Visual.vertices + Transform centroid each step,
# and provides clean teardown on entity removal.
#
# Stability measures (position-based, not force-based):
#   1. Spring length enforcement — if any spring stretches beyond
#      max_stretch × rest_length, directly correct endpoint positions.
#   2. Angular strain resistance — for each surface vertex, if the angle
#      between its two adjacent edges deviates too far from the rest angle,
#      push the neighbours back.  Prevents folding/inversion.
#   3. Hard velocity cap + velocity damping.

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


def _angle_at(ax: float, ay: float, bx: float, by: float,
              cx: float, cy: float) -> float:
    """Signed angle at B in the triangle A-B-C (positive = CCW turn).

    Uses atan2 of the cross/dot products of BA and BC vectors.
    """
    bax, bay = ax - bx, ay - by
    bcx, bcy = cx - bx, cy - by
    cross = bax * bcy - bay * bcx
    dot = bax * bcx + bay * bcy
    return math.atan2(cross, dot)


# Maximum a spring may stretch relative to rest_length before position correction
_MAX_STRETCH = 1.4
# Minimum a spring may compress relative to rest_length
_MIN_STRETCH = 0.3
# Hard speed cap for any node (world units / second)
_MAX_SPEED = 12.0
# Angular correction strength (0..1): how much of the angle error to correct per pass
_ANGLE_STIFFNESS = 0.5


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

        # Compute rest angles for angular strain resistance
        if len(soft.surface_indices) >= 3 and not soft.rest_angles:
            angles: list[float] = []
            si = soft.surface_indices
            n = len(si)
            # Compute surface centroid for rest distances
            scx, scy = 0.0, 0.0
            for idx in si:
                scx += soft.nodes[idx].position.x
                scy += soft.nodes[idx].position.y
            scx /= n
            scy /= n

            rest_dists: list[float] = []
            for i in range(n):
                prev_idx = si[(i - 1) % n]
                curr_idx = si[i]
                next_idx = si[(i + 1) % n]
                ax, ay = soft.nodes[prev_idx].position
                bx, by = soft.nodes[curr_idx].position
                cx, cy = soft.nodes[next_idx].position
                angles.append(_angle_at(ax, ay, bx, by, cx, cy))
                # Rest distance of this surface node from surface centroid
                dx, dy = bx - scx, by - scy
                rest_dists.append(math.sqrt(dx * dx + dy * dy))
            soft.rest_angles = angles
            soft._rest_dists = rest_dists

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
        """Enforce spring + angle constraints, clamp velocities, sync visuals."""
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
            for _pass in range(3):
                for spring in soft.springs:
                    a = spring.a
                    b = spring.b
                    ax, ay = a.position
                    bx, by = b.position
                    dx = bx - ax
                    dy = by - ay
                    dist_sq = dx * dx + dy * dy
                    rest_len = spring.rest_length
                    max_len = rest_len * _MAX_STRETCH
                    min_len = rest_len * _MIN_STRETCH
                    if dist_sq < 1e-16:
                        continue
                    dist = math.sqrt(dist_sq)
                    if dist > max_len:
                        target = max_len
                    elif dist < min_len:
                        target = min_len
                    else:
                        continue
                    correction = dist - target
                    nx = dx / dist
                    ny = dy / dist
                    total_mass = a.mass + b.mass
                    rb = b.mass / total_mass
                    ra = a.mass / total_mass
                    a.position = (ax + nx * correction * rb,
                                  ay + ny * correction * rb)
                    b.position = (bx - nx * correction * ra,
                                  by - ny * correction * ra)
                    # Damp velocity along stretch axis
                    va_dot = a.velocity.x * nx + a.velocity.y * ny
                    if va_dot > 0:
                        a.velocity = (a.velocity.x - nx * va_dot * 0.5,
                                      a.velocity.y - ny * va_dot * 0.5)
                    vb_dot = b.velocity.x * nx + b.velocity.y * ny
                    if vb_dot < 0:
                        b.velocity = (b.velocity.x - nx * vb_dot * 0.5,
                                      b.velocity.y - ny * vb_dot * 0.5)

            # --- 2. Angular strain resistance on surface polygon ---
            if soft.rest_angles and len(soft.surface_indices) >= 3:
                self._enforce_angles(soft)

            # --- 2b. Angular order enforcement (anti-inversion) ---
            # The true cause of mesh inversion: during violent collision,
            # surface nodes swap their angular positions around the centroid.
            # Detect out-of-order pairs and average their positions to uncross.
            if hasattr(soft, '_rest_dists') and len(soft.surface_indices) >= 3:
                si = soft.surface_indices
                ns = len(si)

                for _apass in range(2):
                    # Surface centroid (recompute each pass)
                    scx, scy = 0.0, 0.0
                    for idx in si:
                        scx += soft.nodes[idx].position.x
                        scy += soft.nodes[idx].position.y
                    scx /= ns
                    scy /= ns

                    # Compute angle of each surface node relative to centroid
                    angles_current = []
                    for idx in si:
                        dx = soft.nodes[idx].position.x - scx
                        dy = soft.nodes[idx].position.y - scy
                        angles_current.append(math.atan2(dy, dx))

                    # Check each consecutive pair
                    for i in range(ns):
                        j = (i + 1) % ns
                        diff = angles_current[j] - angles_current[i]
                        if diff > math.pi:
                            diff -= 2 * math.pi
                        elif diff < -math.pi:
                            diff += 2 * math.pi

                        # If diff is negative at all, nodes are out of CCW order
                        if diff < -0.05:
                            bi = soft.nodes[si[i]]
                            bj = soft.nodes[si[j]]
                            mx = (bi.position.x + bj.position.x) * 0.5
                            my = (bi.position.y + bj.position.y) * 0.5
                            dx = bj.position.x - bi.position.x
                            dy = bj.position.y - bi.position.y
                            d = math.sqrt(dx * dx + dy * dy)
                            if d > 1e-8:
                                tx, ty = -dy / d, dx / d
                                sep = max(0.08, d * 0.3)
                                bi.position = (mx - tx * sep, my - ty * sep)
                                bj.position = (mx + tx * sep, my + ty * sep)
                            else:
                                bi.position = (mx - 0.05, my)
                                bj.position = (mx + 0.05, my)
                            bi.velocity = (bi.velocity.x * 0.2, bi.velocity.y * 0.2)
                            bj.velocity = (bj.velocity.x * 0.2, bj.velocity.y * 0.2)

            # --- 3. Velocity damping + hard speed clamp ---
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

            # --- 4. Compute centroid of all nodes ---
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

            # --- 5. Rebuild visual vertices ---
            new_verts = []
            for idx in soft.surface_indices:
                bx = soft.nodes[idx].position.x
                by = soft.nodes[idx].position.y
                new_verts.append((bx - cx, by - cy))
            visual.vertices = new_verts

    # ------------------------------------------------------------------
    # Angular strain constraint
    # ------------------------------------------------------------------

    @staticmethod
    def _enforce_angles(soft: SoftBody) -> None:
        """Position-based angular constraint on the surface polygon.

        For each consecutive triple (A, B, C) of surface nodes, compute the
        signed angle at B.  If it differs from the rest angle, push A and C
        along arcs around B to reduce the error.  This resists folding and
        prevents the mesh from inverting even under heavy deformation.
        """
        si = soft.surface_indices
        n = len(si)
        nodes = soft.nodes
        rest = soft.rest_angles
        stiffness = _ANGLE_STIFFNESS

        for i in range(n):
            prev_idx = si[(i - 1) % n]
            curr_idx = si[i]
            next_idx = si[(i + 1) % n]

            a = nodes[prev_idx]
            b = nodes[curr_idx]
            c = nodes[next_idx]

            bx, by = b.position
            ax, ay = a.position
            cx, cy = c.position

            current_angle = _angle_at(ax, ay, bx, by, cx, cy)
            rest_angle = rest[i]
            error = current_angle - rest_angle

            # Normalise error to [-pi, pi]
            if error > math.pi:
                error -= 2.0 * math.pi
            elif error < -math.pi:
                error += 2.0 * math.pi

            # Skip small errors
            if abs(error) < 0.02:
                continue

            correction = -error * stiffness * 0.5

            # Rotate A around B by +correction, C around B by -correction
            # A relative to B
            rax, ray = ax - bx, ay - by
            cos_c = math.cos(correction)
            sin_c = math.sin(correction)
            new_ax = bx + rax * cos_c - ray * sin_c
            new_ay = by + rax * sin_c + ray * cos_c

            # C relative to B
            rcx, rcy = cx - bx, cy - by
            cos_mc = math.cos(-correction)
            sin_mc = math.sin(-correction)
            new_cx = bx + rcx * cos_mc - rcy * sin_mc
            new_cy = by + rcx * sin_mc + rcy * cos_mc

            a.position = (new_ax, new_ay)
            c.position = (new_cx, new_cy)
