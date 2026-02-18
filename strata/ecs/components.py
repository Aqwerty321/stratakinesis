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

    RigSystem reads this and applies the motor each fixed step.
    (Execution stubbed for v0.)
    """
    target_rate: float = 0.0    # target angular velocity (rad/s)
    max_force: float = 1e8      # pymunk motor max_force

@dataclass
class PropertyBinding(Component):
    """Declarative property binding: mirrors an attribute from source → target.

    E.g. bind an entity's angle to a slider value.
    (Execution stubbed for v0.)
    """
    source_attr: str = ""
    target_attr: str = ""
    source_entity_id: int = -1
    scale: float = 1.0


# Convenience alias used by type hints elsewhere
RigComponent = MotorRig | PropertyBinding
