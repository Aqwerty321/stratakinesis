# strata/systems/physics_system.py
# Wraps pymunk.Space.  Never exposes Space or Body through the simple API.
# Steps only at fixed_dt via the accumulator in the game loop.
#
# CCD (Continuous Collision Detection):
#   Multi-layer defense against high-speed tunneling:
#   1. Tuned solver (higher iterations, tighter collision slop).
#   2. Shape-extent registry — each dynamic body's minimum dimension is
#      cached at registration to compute travel-to-extent ratios.
#   3. Adaptive substeps — substep count is raised dynamically so no body
#      moves more than SAFETY_FACTOR × its extent per substep.
#   4. Swept segment queries — residual fast bodies (travel > CCD_TRIGGER
#      × extent in a single substep) are clamped to the first intersection
#      *before* space.step() so the solver generates proper impulse response.

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pymunk

from strata.backend.array import xp
from strata.systems.base import System
from strata.ecs.components import Physics, Transform
from strata.ecs.world import World


# ---------------------------------------------------------------------------
# CCD constants
# ---------------------------------------------------------------------------

# No body should move more than SAFETY_FACTOR × its extent per substep.
# 0.5 = at most half the body's smallest dimension per substep.
_CCD_SAFETY_FACTOR: float = 0.5

# Per-substep trigger: sweep any body whose travel exceeds this fraction
# of its extent in one substep.  0.25 is conservative (catches bodies before
# they move one quarter of their width).
_CCD_TRIGGER: float = 0.25

# Small offset so swept bodies are placed just outside contact, not exactly
# on the surface (avoids starting-inside-shape edge case).
_CCD_EPSILON: float = 0.005


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
        *,
        iterations: int = 20,
        collision_slop: float = 0.02,
        ccd: bool = True,
        max_substeps: int = 32,
    ) -> None:
        self.space: pymunk.Space = pymunk.Space()
        self.space.gravity = gravity
        # Solver tuning — more iterations resolve overlaps faster;
        # tighter slop prevents resting-penetration "sinking."
        self.space.iterations = iterations
        self.space.collision_slop = collision_slop

        self.base_substeps: int = max(1, substeps)
        # Legacy alias kept for backward compat (SoftBodySystem reads it).
        self.substeps: int = self.base_substeps

        # CCD configuration
        self._ccd_enabled: bool = ccd
        self._max_substeps: int = max(self.base_substeps, max_substeps)

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

        # P1-3: Pre-filtered list of (body, linear_damp, angular_damp) for
        # dynamic bodies with damping < 1.0.  Avoids per-frame ECS query.
        self._damped_bodies: list[tuple[pymunk.Body, float, float]] = []

        # P1-4: Pre-built list of (body, transform) for dynamic entities.
        # Avoids per-frame ECS query + get_component in _sync_transforms.
        self._sync_pairs: list[tuple[pymunk.Body, Transform]] = []

        # --- CCD: shape-extent registry ---
        # Parallel lists of (body, shape, min_extent) for each dynamic body.
        # Populated at register(); used by _compute_substeps / _sweep.
        self._ccd_bodies: list[pymunk.Body] = []
        self._ccd_shapes: list[pymunk.Shape] = []
        self._ccd_extents_list: list[float] = []
        # Numpy array of extents, lazily built on first update().
        self._ccd_extents: xp.ndarray | None = None
        self._ccd_dirty: bool = False  # True when _list was appended to

        # Bodies belonging to soft-body entities — excluded from CCD
        # because they already have _MAX_SPEED cap + per-substep damping.
        self._soft_body_bodies: set[int] = set()  # set of body id()s

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

        # P1-3: index damped dynamic bodies once at registration.
        if not physics.is_static and physics.body is not None:
            if physics.linear_damping < 1.0 or physics.angular_damping < 1.0:
                self._damped_bodies.append(
                    (physics.body, physics.linear_damping, physics.angular_damping)
                )

            # CCD: compute and cache the minimum linear extent of this shape
            # so adaptive substep + sweep have the size reference they need.
            if self._ccd_enabled and physics.shape is not None:
                extent = self._shape_extent(physics.shape)
                if extent > 0.0:
                    self._ccd_bodies.append(physics.body)
                    self._ccd_shapes.append(physics.shape)
                    self._ccd_extents_list.append(extent)
                    self._ccd_dirty = True

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
    # CCD: shape extent computation (registration-time)
    # ------------------------------------------------------------------

    @staticmethod
    def _shape_extent(shape: pymunk.Shape) -> float:
        """Return the minimum linear extent of *shape* — the smallest
        dimension that another body could tunnel through.

        Called once at registration, so cost is irrelevant.
        """
        if isinstance(shape, pymunk.Circle):
            return 2.0 * shape.radius
        if isinstance(shape, pymunk.Poly):
            # cache_bb() returns the world-space AABB; at registration the
            # body is at its initial position with zero rotation, so the BB
            # reflects local-space extents accurately enough.  For convex
            # shapes the minimum axis of the local BB is a safe proxy.
            bb = shape.cache_bb()
            return min(bb.right - bb.left, bb.top - bb.bottom)
        if isinstance(shape, pymunk.Segment):
            return max(2.0 * shape.radius, 0.01)
        return 0.0

    # ------------------------------------------------------------------
    # CCD: soft body exclusion
    # ------------------------------------------------------------------

    def mark_soft_body_nodes(self, nodes: list[pymunk.Body]) -> None:
        """Exclude soft-body node bodies from CCD processing.

        Called by SoftBodySystem.register() so soft bodies (which already
        have _MAX_SPEED cap + per-substep damping) are never double-processed.
        """
        for body in nodes:
            self._soft_body_bodies.add(id(body))

    # ------------------------------------------------------------------
    # CCD: adaptive substep computation
    # ------------------------------------------------------------------

    def _ensure_ccd_extents(self) -> None:
        """Rebuild the numpy extents array if bodies were added since last build."""
        if self._ccd_dirty or self._ccd_extents is None:
            if self._ccd_extents_list:
                self._ccd_extents = xp.array(self._ccd_extents_list, dtype=xp.float64)
            else:
                self._ccd_extents = xp.empty(0, dtype=xp.float64)
            self._ccd_dirty = False

    def _compute_substeps(self, dt: float) -> int:
        """Return the number of substeps needed so that no CCD-tracked body
        moves more than ``_CCD_SAFETY_FACTOR × extent`` per substep.

        Deterministic: same body velocities + same dt always yields the same
        substep count.
        """
        self._ensure_ccd_extents()
        n = len(self._ccd_bodies)
        if n == 0:
            return self.base_substeps

        # Batch-read speeds into numpy — one C-boundary crossing.
        speeds = xp.empty(n, dtype=xp.float64)
        for i, body in enumerate(self._ccd_bodies):
            v = body.velocity
            speeds[i] = math.sqrt(v.x * v.x + v.y * v.y)

        # travel_ratios[i] = how many "body widths" body i would cross in dt
        travel = speeds * dt  # (N,)
        ratios = travel / self._ccd_extents  # (N,)
        max_ratio = float(xp.max(ratios)) if n > 0 else 0.0

        needed = max(self.base_substeps, math.ceil(max_ratio / _CCD_SAFETY_FACTOR))
        return min(needed, self._max_substeps)

    # ------------------------------------------------------------------
    # CCD: per-substep swept segment queries
    # ------------------------------------------------------------------

    def _sweep_fast_bodies(self, sub_dt: float) -> None:
        """For each CCD body whose per-substep travel exceeds the trigger
        threshold, run a swept segment query and clamp its position to the
        first external hit.

        This runs *before* ``space.step(sub_dt)`` so pymunk detects the
        near-contact naturally and generates proper impulse response.
        """
        n = len(self._ccd_bodies)
        if n == 0:
            return

        trigger = _CCD_TRIGGER
        slop = self.space.collision_slop
        _sqrt = math.sqrt
        segment_query = self.space.segment_query
        soft_ids = self._soft_body_bodies

        for i in range(n):
            body = self._ccd_bodies[i]

            # Skip soft-body nodes (belt-and-suspenders; they shouldn't
            # be in _ccd_bodies, but guard just in case).
            if id(body) in soft_ids:
                continue

            v = body.velocity
            speed = _sqrt(v.x * v.x + v.y * v.y)
            extent = self._ccd_extents_list[i]
            travel = speed * sub_dt

            # Distance prune: only sweep bodies that travel a significant
            # fraction of their extent in this substep.
            if travel <= extent * trigger:
                continue

            # Start / end of the swept segment for this substep.
            px, py = body.position.x, body.position.y
            dx = v.x * sub_dt
            dy = v.y * sub_dt
            end_x = px + dx
            end_y = py + dy

            # Query radius: half the shape extent as conservative swept width.
            shape = self._ccd_shapes[i]
            if isinstance(shape, pymunk.Circle):
                q_radius = shape.radius
            else:
                q_radius = extent * 0.5

            # Segment query along the body's trajectory.
            hits = segment_query(
                (px, py), (end_x, end_y), q_radius,
                pymunk.ShapeFilter(),
            )

            # Find earliest external hit (skip self-shape hits).
            best_alpha = 1.0
            for hit in hits:
                if hit.shape.body is body:
                    continue
                if hit.alpha < best_alpha:
                    best_alpha = hit.alpha

            if best_alpha < 1.0:
                # Clamp: place the body just before the contact point.
                safe_alpha = max(0.0, best_alpha - _CCD_EPSILON)
                body.position = (px + dx * safe_alpha, py + dy * safe_alpha)

    # ------------------------------------------------------------------
    # System update
    # ------------------------------------------------------------------

    def update(self, world: World, dt: float) -> None:
        """Step physics then sync Transforms.  dt is always FIXED_DT.

        When CCD is enabled the substep count is raised adaptively so no
        body moves more than ``_CCD_SAFETY_FACTOR × extent`` per substep.
        Any residual fast body is further protected by a swept segment query
        before each ``space.step()`` call.

        When ``substeps > 1`` the space is stepped ``substeps`` times with
        ``dt / substeps`` each, giving the DampedSpring solver a smaller
        effective timestep.  This is essential for soft-body meshes where
        light nodes + stiff springs would otherwise be numerically unstable.
        """
        if self._ccd_enabled:
            n = self._compute_substeps(dt)
        else:
            n = self.base_substeps

        # Keep the legacy .substeps attribute in sync so SoftBodySystem
        # can read it when computing per-substep damping factor.
        self.substeps = n

        sub_dt = dt / n
        for _ in range(n):
            # CCD: sweep fast bodies before stepping — positions are clamped
            # to first contact so the solver sees near-contacts, not tunnels.
            if self._ccd_enabled:
                self._sweep_fast_bodies(sub_dt)
            self.space.step(sub_dt)
            # Run post-substep hooks (e.g. soft-body COM correction).
            for hook in self._post_substep_hooks:
                hook(sub_dt)
        self._apply_body_damping(world)
        self._sync_transforms(world)

    def _apply_body_damping(self, world: World) -> None:
        """Apply per-body linear and angular damping once per fixed step.

        P1-3: Iterates the pre-built _damped_bodies list instead of doing
        a full ECS query + component lookup + is_static filter every frame.
        """
        for body, ld, ad in self._damped_bodies:
            if ld < 1.0:
                v = body.velocity
                body.velocity = (v.x * ld, v.y * ld)
            if ad < 1.0:
                body.angular_velocity *= ad

    def _sync_transforms(self, world: World) -> None:
        """Copy body position/angle back into Transform components.

        P1-4: Uses the pre-built _sync_pairs list when available, falling
        back to the ECS query for entities registered before the optimisation.
        """
        if self._sync_pairs:
            for body, transform in self._sync_pairs:
                transform.prev_x = transform.x
                transform.prev_y = transform.y
                transform.prev_angle = transform.angle
                transform.x = body.position.x
                transform.y = body.position.y
                transform.angle = body.angle
        else:
            for entity in world.get_entities_with(Physics, Transform):
                physics: Physics = entity.get_component(Physics)
                transform: Transform = entity.get_component(Transform)
                if physics.is_static:
                    continue
                body: pymunk.Body = physics.body
                transform.prev_x = transform.x
                transform.prev_y = transform.y
                transform.prev_angle = transform.angle
                transform.x = body.position.x
                transform.y = body.position.y
                transform.angle = body.angle
