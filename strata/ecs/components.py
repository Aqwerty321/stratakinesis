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
    # Per-fixed-step velocity multipliers (applied once per FIXED_DT tick).
    # 1.0 = no decay; 0.99 ≈ 45 % retained per second at 60 Hz.
    linear_damping:  float = 1.0
    angular_damping: float = 1.0


# ---------------------------------------------------------------------------
# Visual
# ---------------------------------------------------------------------------

@dataclass
class Visual(Component):
    """Rendering data for an entity.

    `vertices` is a list of (x, y) tuples in *local* world-unit coordinates
    (relative to the entity's Transform origin).  They are cached at creation
    time and never rebuilt per-frame; RenderSystem applies Transform to them.

    `color`   — fill colour as (R, G, B) or (R, G, B, A) tuple.
                Always stored internally as a 4-tuple after construction.
    `outline` — outline colour; None means no outline.
                Always stored internally as a 4-tuple (or None) after construction.
    `hidden`  — when True, RenderSystem skips this entity.  Use for entities
                whose visuals are fully managed by a rig's own draw() call.
    `image_surface` — optional pygame.Surface for image-based rendering.
                Loaded by Sprite.image() and blitted aligned to body Transform.
    `image_width`   — width of the image in world units (used for scaling).
    `image_height`  — height of the image in world units.
    """
    shape_type: str = "polygon"   # "circle" | "polygon" | "image"
    radius: float = 0.0           # used only when shape_type == "circle"
    vertices: list[tuple[float, float]] = field(default_factory=list)
    color: tuple[int, ...] = (100, 180, 255, 255)
    outline: tuple[int, ...] | None = (255, 255, 255, 200)
    hidden: bool = False
    image_surface: Any = field(default=None, repr=False)
    image_width: float = 0.0
    image_height: float = 0.0

    def __post_init__(self) -> None:
        # Normalise to 4-tuple RGBA so RenderSystem never needs a len() check.
        if len(self.color) == 3:
            self.color = (self.color[0], self.color[1], self.color[2], 255)
        # Cache vertices as a numpy array for batch-transform in RenderSystem.
        self._verts_arr = None
        if self.vertices:
            from strata.backend.array import xp
            self._verts_arr = xp.array(self.vertices, dtype=xp.float64)
        if self.outline is not None and len(self.outline) == 3:
            self.outline = (self.outline[0], self.outline[1], self.outline[2], 255)


@dataclass
class PropertyBinding(Component):
    """Declarative property binding: mirrors a Transform attribute from one entity to another.

    BindingSystem each step reads ``source_entity.Transform.{source_attr}`` and writes
    ``entity.Transform.{target_attr} = value * scale + offset``.

    Fields
    ------
    source_entity_id : id of the source Entity.
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

    The spring network has three tiers:
      * **structural** — horizontal + vertical (grid) or radial + circumferential
        (radial).  Maintain overall shape.
      * **shear** — diagonal springs that resist shearing deformation.
      * **bending** — 2-away connections that resist folding / angular collapse.

    Fields
    ------
    nodes          : all pymunk Bodies that make up the mesh.
    springs        : all DampedSpring constraints between nodes.
    surface_shapes : pymunk.Circle shapes on the perimeter nodes.
    surface_indices: indices into ``nodes`` defining the CCW perimeter.
    stiffness      : spring rest stiffness (N/world-unit).
    damping        : spring damping coefficient.
    node_radius    : collision radius of each perimeter node circle.
    node_density   : mesh resolution — nodes per world unit. When > 0, overrides
                     explicit cols/rows (rect) or rings/segments (circle).
    velocity_damping: per-step velocity multiplier (0..1). Prevents runaway.
    pressure       : (legacy, unused) internal pressure coefficient.
    rest_area      : (legacy, unused) initial surface polygon area.
    rest_angles    : (legacy, unused) initial interior angles.
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
    node_density: float = 0.0
    velocity_damping: float = 0.995
    pressure: float = 80.0
    rest_area: float = 0.0
    rest_angles: list[float] = field(default_factory=list, repr=False)
    debug_render: bool = False
    topology: str = "grid"


# Convenience alias used by type hints elsewhere
# (MotorRig was replaced by HingeMotorRig Rig assembly in strata.rigs)
RigComponent = PropertyBinding
