# strata/ecs/components.py
# Plain dataclasses — no logic. Systems read and write these.

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any

import pymunk

# Marker base so type hints can use `Component`.
@dataclass
class Component:
    pass


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

@dataclass
class Transform(Component):
    """World-space position and rotation."""
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0  # radians, counter-clockwise positive


# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------

@dataclass
class Physics(Component):
    """Holds the pymunk Body and Shape for a physical entity.

    Not part of the simple public API — created internally by PhysicsSystem.
    Advanced users can access `.body` and `.shape` for customisation.
    """
    body: pymunk.Body = field(default=None, repr=False)
    shape: pymunk.Shape = field(default=None, repr=False)
    density: float = 1.0
    is_static: bool = False


# ---------------------------------------------------------------------------
# Visual
# ---------------------------------------------------------------------------

@dataclass
class Visual(Component):
    """Rendering data for an entity.

    `vertices` is a list of (x, y) tuples in *local* world-unit coordinates
    (relative to the entity's Transform origin).  They are cached at creation
    time and never rebuilt per-frame; RenderSystem applies Transform to them.

    `color`   — fill colour as (R, G, B[, A]) tuple.
    `outline` — outline colour; None means no outline.
    """
    shape_type: str = "polygon"   # "circle" | "polygon"
    radius: float = 0.0           # used only when shape_type == "circle"
    vertices: list[tuple[float, float]] = field(default_factory=list)
    color: tuple[int, ...] = (100, 180, 255, 255)
    outline: tuple[int, ...] | None = (255, 255, 255, 200)


# ---------------------------------------------------------------------------
# Rig (data model — execution deferred post-v0)
# ---------------------------------------------------------------------------

@dataclass
class MotorRig(Component):
    """Declarative motor rig: drives a body's angular velocity toward a target.

    RigSystem creates a ``pymunk.SimpleMotor`` between the entity's body and
    a shared static anchor body, driving angular velocity to ``target_rate``.

    Fields
    ------
    target_rate : target angular velocity in radians/second (+ve = CCW).
    max_force   : pymunk motor maximum force (Nm). Default is effectively unlimited.
    enabled     : set False to zero the rate without removing the constraint.

    Private (managed by RigSystem — do not set manually)
    -------
    _constraint : cached pymunk.SimpleMotor; created on first RigSystem update.
    _anchor_body: static pymunk.Body that anchors the motor constraint.
    """
    target_rate: float = 0.0
    max_force: float = 1e8
    enabled: bool = True
    # --- private cache fields ---
    _constraint: Any = field(default=None, repr=False, init=False, compare=False)
    _anchor_body: Any = field(default=None, repr=False, init=False, compare=False)


@dataclass
class PropertyBinding(Component):
    """Declarative property binding: mirrors a Transform attribute from one entity to another.

    RigSystem each step reads ``source_entity.Transform.{source_attr}`` and writes
    ``entity.Transform.{target_attr} = value * scale + offset``.

    Fields
    ------
    source_entity_id : id of the source Entity (set automatically by Sprite helpers).
    source_attr      : name of the attribute on the source entity's Transform.
    target_attr      : name of the attribute on this entity's Transform.
    scale            : multiply the source value before writing.
    offset           : add to the scaled value before writing.
    enabled          : set False to pause the binding without removing it.
    """
    source_entity_id: int = -1
    source_attr: str = "angle"
    target_attr: str = "angle"
    scale: float = 1.0
    offset: float = 0.0
    enabled: bool = True


# Convenience alias used by type hints elsewhere
RigComponent = MotorRig | PropertyBinding
