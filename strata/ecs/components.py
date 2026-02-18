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
    """World-space position and rotation.

    ``prev_*`` fields hold the state at the start of the last physics step.
    RenderSystem lerps between prev and current using the accumulator alpha
    to produce smooth visuals at any frame rate.
    """
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0  # radians, counter-clockwise positive
    # --- interpolation snapshots (written by PhysicsSystem before each sync) ---
    prev_x: float = field(default=0.0, repr=False)
    prev_y: float = field(default=0.0, repr=False)
    prev_angle: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        # Initialise prev to the same values so first frame has no lerp jump
        self.prev_x = self.x
        self.prev_y = self.y
        self.prev_angle = self.angle


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
    # Collision layer bitmask: categories this shape belongs to.
    # Applied as pymunk.ShapeFilter on registration.
    collision_layer: int = 0xFFFF
    # Collision mask bitmask: categories this shape will collide with.
    # Two shapes collide only when (A.layer & B.mask) and (B.layer & A.mask) are both non-zero.
    collision_mask: int = 0xFFFF


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


# ---------------------------------------------------------------------------
# Soft body
# ---------------------------------------------------------------------------

@dataclass
class SoftBody(Component):
    """Holds the multi-body spring-mass mesh that forms a soft body.

    A soft body is N point-mass ``pymunk.Body`` objects connected by
    ``pymunk.DampedSpring`` constraints.  Only the *perimeter* nodes carry
    ``pymunk.Circle`` collision shapes; interior nodes are invisible to
    physics collisions (mass only).

    Fields
    ------
    nodes          : all pymunk Bodies that make up the mesh.
    springs        : all DampedSpring constraints between nodes.
    surface_shapes : pymunk.Circle shapes on the perimeter nodes.
    surface_indices: indices into ``nodes`` defining the CCW perimeter.
    stiffness      : spring rest stiffness (N/world-unit).
    damping        : spring damping coefficient.
    node_radius    : collision radius of each perimeter node circle.
    pressure       : internal pressure coefficient — resists volume loss.
                     Higher values make the body resist compression more.
    velocity_damping: per-step velocity multiplier (0..1). Prevents runaway.
    rest_area      : initial surface polygon area (computed at creation).
    debug_render   : when True, render individual nodes+springs instead of mesh.
    topology       : ``"grid"`` or ``"radial"`` — informational tag.
    """
    nodes: list = field(default_factory=list, repr=False)
    springs: list = field(default_factory=list, repr=False)
    surface_shapes: list = field(default_factory=list, repr=False)
    surface_indices: list[int] = field(default_factory=list)
    stiffness: float = 300.0
    damping: float = 10.0
    node_radius: float = 0.12
    pressure: float = 80.0
    velocity_damping: float = 0.995
    rest_area: float = 0.0
    debug_render: bool = False
    topology: str = "grid"


# Convenience alias used by type hints elsewhere
RigComponent = MotorRig | PropertyBinding
