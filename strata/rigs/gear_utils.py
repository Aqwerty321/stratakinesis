# strata/rigs/gear_utils.py
# Parametric trapezoidal gear tooth polygon generator.
#
# Design conventions
# ------------------
# • Gear geometry follows standard module-based spur gear proportions.
# • "module" m = 2 * pitch_radius / num_teeth  (SI: metres/tooth)
# • addendum  = m        (tooth protrudes above pitch circle by 1 module)
# • dedendum  = 1.25 * m (root circle sinks below pitch circle by 1.25 modules)
# • tooth_frac: tooth width at the pitch circle as a fraction of the pitch arc.
#   Typical value: 0.46  (leaves 0.54 fraction for the root gap → slight backlash)
# • tip_frac:   tooth top width as a fraction of the pitch arc.
#   Must be < tooth_frac to produce the trapezoid shape.  Typical: 0.26
#
# Coordinate system
# -----------------
# All geometry is generated in **world space** (Y-up, angles CCW-positive).
# Points are then converted to screen pixels via camera.world_to_screen(), which
# handles the Y-flip.  Pass physics body.angle directly as `angle`.

from __future__ import annotations
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from strata.render.camera import Camera


def gear_polygon(
    cx: float,
    cy: float,
    angle: float,
    pitch_radius: float,
    num_teeth: int,
    camera: "Camera",
    *,
    tooth_frac: float = 0.46,
    tip_frac: float = 0.26,
    addendum: float | None = None,
    dedendum: float | None = None,
    fillet_frac: float = 0.06,
) -> list[tuple[int, int]]:
    """Return a closed list of screen-pixel ``(x, y)`` points for one gear.

    Parameters
    ----------
    cx, cy        : world-space centre of the gear.
    angle         : body rotation (radians, CCW-positive), from physics body.
    pitch_radius  : pitch circle radius (world units).
    num_teeth     : number of teeth.
    camera        : ``Camera`` instance for world→screen conversion.
    tooth_frac    : fraction of angular pitch occupied by the tooth at root
                    width level (0 < tooth_frac < 1).
    tip_frac      : fraction of angular pitch for the tooth tip (trapezoid top);
                    must satisfy ``tip_frac < tooth_frac``.
    addendum      : tooth height above pitch circle.  Default: module.
    dedendum      : root depth below pitch circle.  Default: 1.25 × module.
    fillet_frac   : tiny angular nudge added at root transitions to round the
                    gear-root junction slightly (purely cosmetic).

    Returns
    -------
    List of ``(screen_x, screen_y)`` integer tuples forming a closed polygon
    in screen-pixel space, suitable for ``pygame.gfxdraw.filled_polygon``.
    """
    module = 2.0 * pitch_radius / num_teeth
    if addendum is None:
        addendum = module
    if dedendum is None:
        dedendum = 1.25 * module

    r_tip  = pitch_radius + addendum   # addendum circle radius
    r_root = pitch_radius - dedendum   # dedendum circle radius

    pitch_angle = (2.0 * math.pi) / num_teeth   # angular pitch (radians)
    hw_tooth = tooth_frac * pitch_angle * 0.5   # half-width at tooth root
    hw_tip   = tip_frac   * pitch_angle * 0.5   # half-width at tooth tip
    fillet   = fillet_frac * pitch_angle         # small gap smoothing angle

    # Local (world-relative) polygon in (lx, ly) pairs.
    # Each tooth contributes 4 vertices + 2 root gap vertices = 6 pts/tooth.
    # Going CCW around the gear:
    #   …root gap … | left flank root | left flank tip | tip flat |
    #                 right flank tip | right flank root | root gap … | …
    local_pts: list[tuple[float, float]] = []

    for k in range(num_teeth):
        tc = angle + k * pitch_angle   # angular centre of this tooth (world)

        # ── root gap on left side of tooth ──────────────────────────────────
        a = tc - hw_tooth - fillet
        local_pts.append((r_root * math.cos(a),  r_root * math.sin(a)))

        # ── left flank — bottom (root circle) ───────────────────────────────
        a = tc - hw_tooth
        local_pts.append((r_root * math.cos(a),  r_root * math.sin(a)))

        # ── left flank — top (addendum circle) ──────────────────────────────
        a = tc - hw_tip
        local_pts.append((r_tip  * math.cos(a),  r_tip  * math.sin(a)))

        # ── tooth tip right edge ─────────────────────────────────────────────
        a = tc + hw_tip
        local_pts.append((r_tip  * math.cos(a),  r_tip  * math.sin(a)))

        # ── right flank — bottom (root circle) ──────────────────────────────
        a = tc + hw_tooth
        local_pts.append((r_root * math.cos(a),  r_root * math.sin(a)))

        # ── root gap on right side of tooth ─────────────────────────────────
        a = tc + hw_tooth + fillet
        local_pts.append((r_root * math.cos(a),  r_root * math.sin(a)))

    # Convert to screen-pixel coordinates.  camera.world_to_screen handles Y-flip.
    return [camera.world_to_screen(cx + lx, cy + ly) for (lx, ly) in local_pts]


def select_num_teeth(
    radii: list[float],
    teeth_per_unit: float = 14.0,
    min_teeth: int = 8,
) -> tuple[list[int], float]:
    """Choose integer tooth counts and a shared module for a set of gears.

    Uses a least-squares-ish approach: pick the module that minimises the
    rounding error across all gears while keeping all counts >= ``min_teeth``.

    Returns
    -------
    (num_teeth_list, module)  where module = 2*r[i]/N[i] (averaged).
    """
    # Initial estimate: teeth proportional to radius from smallest gear.
    r_min = min(radii)
    n_ref = max(min_teeth, round(teeth_per_unit * r_min))

    # Each gear's ideal (float) tooth count based on proportional scaling.
    ns_float = [max(min_teeth, n_ref * r / r_min) for r in radii]
    ns       = [max(min_teeth, round(n)) for n in ns_float]

    # Compute module as the weighted average.
    module = sum(2.0 * r / n for r, n in zip(radii, ns)) / len(radii)

    return ns, module


def initial_tooth_phases(
    num_teeth: list[int],
) -> list[float]:
    """Compute per-gear initial angle offsets so adjacent gears visually mesh.

    Gears are placed left-to-right, so adjacent gears touch at:
      gear i  → contact is on its RIGHT side (angle = 0)
      gear i+1 → contact is on its LEFT side  (angle = π)

    For a tooth on gear i to slot into the gap on gear i+1:
      • gear 0 : tooth tip at angle 0  → phase = 0           (tooth k=0 centred at 0)
      • gear 1 : root gap at angle π   → phase = π + pitch/2  (gap between teeth at π)
      • gear 2 : tooth tip at angle 0  → phase = pitch/2      (tooth at 0 again)
      • gear k : alternates based on contact side

    The sign flip from the negative GearJoint ratio means driven gears rotate
    opposite to the driver, so the angular offset between meshes propagates
    correctly at run-time.  The static phases here just set t=0 alignment.

    Returns a list of phase offsets (radians) to *add* to body.angle.
    """
    phases = []
    for i, n in enumerate(num_teeth):
        pitch = (2.0 * math.pi) / n
        if i == 0:
            # First gear: align a tooth tip to angle 0 (right, contact side).
            # tooth k centred at phase + k*pitch; for k=0 centred at phase=0.
            phases.append(0.0)
        else:
            # Driven gear: align a root gap (valley between teeth) to angle π
            # (left side, where the previous gear's tooth presses in).
            # A valley sits halfway between tooth centres → phase = π + pitch/2.
            phases.append(math.pi + pitch * 0.5)
    return phases
