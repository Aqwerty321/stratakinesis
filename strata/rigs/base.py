# strata/rigs/base.py
# Base Rig class and JointHandle — the core of the constraint assembly system.

from __future__ import annotations
import math
from typing import Any, TYPE_CHECKING

import pymunk

if TYPE_CHECKING:
    from strata.ecs.entity import Entity


# ---------------------------------------------------------------------------
# JointHandle — live handle for runtime motor control
# ---------------------------------------------------------------------------

class JointHandle:
    """Runtime handle to a single pymunk constraint.

    Returned by Rig subclasses for constraints that need per-frame mutation
    (motor rate, spring stiffness, etc.).  Can be written *before* the Rig is
    registered — values are applied the moment the constraint is built.
    """

    def __init__(self) -> None:
        self._constraint: pymunk.Constraint | None = None
        self._pending: dict[str, Any] = {}

    def _attach(self, constraint: pymunk.Constraint) -> None:
        """Called by Rig._register() once the pymunk constraint is built."""
        self._constraint = constraint
        for attr, val in self._pending.items():
            if attr == 'enabled':
                continue  # handled below
            try:
                setattr(self._constraint, attr, val)
            except AttributeError:
                pass  # not all constraint types have every attr
        # Apply enabled state last — overrides max_force if disabled.
        if not self._pending.get('enabled', True):
            self._constraint.max_force = 0.0

    # --- rate (SimpleMotor) ---

    @property
    def rate(self) -> float:
        if self._constraint is not None:
            return getattr(self._constraint, 'rate', 0.0)
        return self._pending.get('rate', 0.0)

    @rate.setter
    def rate(self, value: float) -> None:
        self._pending['rate'] = value
        if self._constraint is not None:
            try:
                self._constraint.rate = value
            except AttributeError:
                pass

    # --- max_force ---

    @property
    def max_force(self) -> float:
        if self._constraint is not None:
            return self._constraint.max_force
        return self._pending.get('max_force', 1e7)

    @max_force.setter
    def max_force(self, value: float) -> None:
        self._pending['max_force'] = value
        if self._constraint is not None:
            # Respect enabled state: if disabled, keep max_force at 0.
            if self._pending.get('enabled', True):
                self._constraint.max_force = value
            # else: don't write to constraint; value is staged in _pending
            # and will be applied when re-enabled.

    # --- enabled toggle (zeros max_force) ---

    @property
    def enabled(self) -> bool:
        return self._pending.get('enabled', True)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._pending['enabled'] = value
        if self._constraint is not None:
            self._constraint.max_force = (
                self._pending.get('max_force', 1e7) if value else 0.0
            )

    def __repr__(self) -> str:
        built = self._constraint is not None
        return f"JointHandle(built={built}, pending={self._pending})"


# ---------------------------------------------------------------------------
# Rig base class
# ---------------------------------------------------------------------------

class Rig:
    """Container for a multi-entity constrained assembly.

    Subclasses create Sprite entities, add them to ``self._entities``, and
    register joint specs via ``self._add_spec()``.

    ``scene.add_rig(rig)`` then:
      1. Calls ``scene.add_entity()`` for every entity in ``_entities``.
      2. Calls ``rig._register(space, static_body)`` to build and add the
         pymunk constraints.

    Parameters
    ----------
    (none — subclasses handle construction)
    """

    def __init__(self) -> None:
        self._entities: list[Entity] = []
        # Each spec is a plain dict:
        #   type      : str  — joint type key (see _build_constraint)
        #   entity_a  : Entity | None  — None = first entity in _entities
        #   entity_b  : Entity | None  — None = world static body
        #   _handle   : JointHandle
        #   **kwargs  : joint-specific parameters
        self._specs: list[dict] = []
        # Live pymunk constraints built by _register(), used by _unregister()
        # for clean teardown.
        self._constraints: list[pymunk.Constraint] = []
        # Whether _register() has been called (guards against double-add).
        self._registered: bool = False

    @property
    def entities(self) -> list:
        """Read-only list of all owned entities."""
        return list(self._entities)

    # ------------------------------------------------------------------
    # Spec helpers (called by subclasses during __init__)
    # ------------------------------------------------------------------

    def _add_spec(
        self,
        joint_type: str,
        entity_a: Any,
        entity_b: Any,
        handle: JointHandle,
        **kwargs: Any,
    ) -> None:
        self._specs.append({
            'type': joint_type,
            'entity_a': entity_a,
            'entity_b': entity_b,
            '_handle': handle,
            **kwargs,
        })

    # ------------------------------------------------------------------
    # Registration (called by Scene.add_rig after entities are added)
    # ------------------------------------------------------------------

    def _register(self, space: pymunk.Space, static_body: pymunk.Body) -> None:
        """Build all pymunk constraints and add them to the space.

        Idempotent — calling _register() a second time is a no-op.
        """
        if self._registered:
            return
        from strata.ecs.components import Physics

        _batch_add: list = []  # P-OPT-12: collect for single space.add()
        for spec in self._specs:
            ea = spec.get('entity_a')
            eb = spec.get('entity_b')

            # Resolve body_a
            if ea is not None:
                phys_a = ea.get_component(Physics)
                body_a = phys_a.body if phys_a else static_body
            elif self._entities:
                phys_a = self._entities[0].get_component(Physics)
                body_a = phys_a.body if phys_a else static_body
            else:
                body_a = static_body

            # Resolve body_b  (None = world static body)
            if eb is not None:
                phys_b = eb.get_component(Physics)
                body_b = phys_b.body if phys_b else static_body
            else:
                body_b = static_body

            constraint = self._build_constraint(spec, body_a, body_b)
            if constraint is not None:
                _batch_add.append(constraint)
                self._constraints.append(constraint)
                handle: JointHandle = spec['_handle']
                handle._attach(constraint)

        # P-OPT-12: Single space.add() call for all constraints.
        if _batch_add:
            space.add(*_batch_add)

        self._registered = True

    def _unregister(self, space: pymunk.Space) -> None:
        """Remove all constraints built by _register() from the space."""
        # P-OPT-12: Batch removal in single space.remove() call.
        to_remove = [c for c in self._constraints if c in space.constraints]
        if to_remove:
            space.remove(*to_remove)
        self._constraints.clear()
        # Reset handles to unbuilt state.
        for spec in self._specs:
            handle: JointHandle = spec['_handle']
            handle._constraint = None
        self._registered = False

    # ------------------------------------------------------------------
    # Constraint factory
    # ------------------------------------------------------------------

    def _build_constraint(
        self,
        spec: dict,
        body_a: pymunk.Body,
        body_b: pymunk.Body,
    ) -> pymunk.Constraint | None:
        t = spec['type']

        if t == 'pin':
            return pymunk.PinJoint(
                body_a, body_b,
                spec.get('anchor_a', (0.0, 0.0)),
                spec.get('anchor_b', (0.0, 0.0)),
            )

        if t == 'pivot':
            # pivot: one world-space point (easiest form)
            return pymunk.PivotJoint(body_a, body_b, spec['pivot'])

        if t == 'pivot_anchors':
            # pivot via two body-local anchors
            return pymunk.PivotJoint(
                body_a, body_b,
                spec.get('anchor_a', (0.0, 0.0)),
                spec.get('anchor_b', (0.0, 0.0)),
            )

        if t == 'slide':
            return pymunk.SlideJoint(
                body_a, body_b,
                spec.get('anchor_a', (0.0, 0.0)),
                spec.get('anchor_b', (0.0, 0.0)),
                float(spec.get('min', 0.0)),
                float(spec.get('max', 1.0)),
            )

        if t == 'groove':
            return pymunk.GrooveJoint(
                body_a, body_b,
                spec.get('groove_a', (0.0, 0.0)),
                spec.get('groove_b', (1.0, 0.0)),
                spec.get('anchor_b', (0.0, 0.0)),
            )

        if t == 'motor':
            c = pymunk.SimpleMotor(body_a, body_b, float(spec.get('rate', 0.0)))
            c.max_force = float(spec.get('max_force', 1e7))
            return c

        if t == 'gear':
            return pymunk.GearJoint(
                body_a, body_b,
                float(spec.get('phase', 0.0)),
                float(spec.get('ratio', 1.0)),
            )

        if t == 'rot_limit':
            return pymunk.RotaryLimitJoint(
                body_a, body_b,
                float(spec.get('min_angle', 0.0)),
                float(spec.get('max_angle', math.pi)),
            )

        if t == 'ratchet':
            return pymunk.RatchetJoint(
                body_a, body_b,
                float(spec.get('phase', 0.0)),
                float(spec.get('ratchet_step', math.pi / 4)),
            )

        if t == 'spring':
            return pymunk.DampedSpring(
                body_a, body_b,
                spec.get('anchor_a', (0.0, 0.0)),
                spec.get('anchor_b', (0.0, 0.0)),
                float(spec.get('rest_length', 1.0)),
                float(spec.get('stiffness', 100.0)),
                float(spec.get('damping', 5.0)),
            )

        if t == 'torsion':
            return pymunk.DampedRotarySpring(
                body_a, body_b,
                float(spec.get('rest_angle', 0.0)),
                float(spec.get('stiffness', 100.0)),
                float(spec.get('damping', 5.0)),
            )

        raise ValueError(f"Rig: unknown joint type {t!r}")
