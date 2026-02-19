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
    lock_frac: float = 0.15,
) -> list[float]:
    """Compute per-gear initial angle offsets so adjacent gears visually mesh.

    Gears are placed left-to-right, touching at:
      gear i   right side  → world angle = 0
      gear i+1 left  side  → world angle = π

    Adjacent gears counter-rotate (negative GearJoint ratio), so face states
    alternate: even-indexed gears have a TOOTH at contact; odd-indexed gears
    have a GAP at contact (holds for even tooth counts).

    Phase formula
    -------------
    • Even gear i:  phase = lock_frac × pitch_i
      Tooth centre at lock_frac×pitch past angle 0 — tip sits slightly inside
      the neighbouring gap for a visual "locked" look at t = 0.
    • Odd  gear i:  phase = π − pitch_i / 2
      Tooth centres at π ± pitch/2; gap midpoint exactly at π (left contact)
      and at 0 (right contact) for even tooth counts.

    lock_frac : fraction of a pitch to offset even-gear teeth from the contact
    angle.  Range (0, 0.4); default 0.15.

    Returns a list of phase offsets (radians) added to ``body.angle`` in draw().
    """
    phases = []
    for i, n in enumerate(num_teeth):
        pitch = (2.0 * math.pi) / n
        if i % 2 == 0:
            phases.append(lock_frac * pitch)
        else:
            # Gap centre exactly at π: teeth at π ± pitch/2.
            phases.append(math.pi - pitch * 0.5)
    return phases
