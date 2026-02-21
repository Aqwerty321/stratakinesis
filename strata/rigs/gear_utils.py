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


def build_local_tooth_polygon(
    pitch_radius: float,
    num_teeth: int,
    tooth_frac: float = 0.46,
    tip_frac: float = 0.26,
    module: float | None = None,
    fillet_frac: float = 0.06,
) -> list[tuple[float, float]]:
    """Return the gear tooth polygon in **local space at angle 0**.

    All trigonometry is done here, once at rig construction.  At draw time
    the cached points are rotated by a single ``cos``/``sin`` pair per gear.

    Parameters
    ----------
    pitch_radius : pitch circle radius (world units).
    num_teeth    : integer tooth count.
    tooth_frac   : fraction of angular pitch for tooth width at root.
    tip_frac     : fraction of angular pitch for tooth tip width.
    module       : gear module; defaults to ``2 * pitch_radius / num_teeth``.
    fillet_frac  : angular smoothing at root transitions.

    Returns
    -------
    List of ``(lx, ly)`` world-unit float pairs in local gear space
    (gear centre at origin, no rotation applied).
    """
    if module is None:
        module = 2.0 * pitch_radius / num_teeth

    addendum = module
    dedendum = 1.25 * module
    r_tip  = pitch_radius + addendum
    r_root = pitch_radius - dedendum

    pitch_angle = (2.0 * math.pi) / num_teeth
    hw_tooth = tooth_frac * pitch_angle * 0.5
    hw_tip   = tip_frac   * pitch_angle * 0.5
    fillet   = fillet_frac * pitch_angle

    local_pts: list[tuple[float, float]] = []
    for k in range(num_teeth):
        tc = k * pitch_angle   # tooth centre angle at identity rotation

        a = tc - hw_tooth - fillet
        local_pts.append((r_root * math.cos(a), r_root * math.sin(a)))

        a = tc - hw_tooth
        local_pts.append((r_root * math.cos(a), r_root * math.sin(a)))

        a = tc - hw_tip
        local_pts.append((r_tip  * math.cos(a), r_tip  * math.sin(a)))

        a = tc + hw_tip
        local_pts.append((r_tip  * math.cos(a), r_tip  * math.sin(a)))

        a = tc + hw_tooth
        local_pts.append((r_root * math.cos(a), r_root * math.sin(a)))

        a = tc + hw_tooth + fillet
        local_pts.append((r_root * math.cos(a), r_root * math.sin(a)))

    return local_pts


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
