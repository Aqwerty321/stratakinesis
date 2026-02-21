# strata/shapes/mesh.py
# Mesh: pre-computed geometry templates with LRU caching.
#
# All vertex generation methods return ``list[tuple[float, float]]``
# in local-space CCW winding.  Templates are computed once (with trig)
# and then scaled by simple multiplication on subsequent calls with the
# same parameters.  An internal LRU cache (1024 entries) ensures that
# repeated calls with identical arguments are free.
#
# Usage:
#   from strata.shapes.mesh import Mesh
#   verts = Mesh.circle(radius=0.5)            # 32 segments, cached
#   verts = Mesh.circle(radius=0.5, segments=16)
#   verts = Mesh.ngon(6, radius=1.0)           # hexagon
#   verts = Mesh.triangle(radius=0.4)          # equilateral
#   verts = Mesh.rect(width=2.0, height=1.0)
#   verts = Mesh.star(5, outer=1.0, inner=0.4)
#   verts = Mesh.rotated_rect(2.0, 0.3, angle_deg=30)

from __future__ import annotations

import math
from functools import lru_cache

# Pre-computed unit templates (computed once at import time).
# Unit circle: radius=1, N segments.  Stored as tuple-of-tuples so they
# are hashable and immutable.
_TWO_PI = 2.0 * math.pi


def _build_unit_ngon(n: int) -> tuple[tuple[float, float], ...]:
    """Build a unit n-gon (radius=1) with *n* vertices, CCW from angle=0."""
    step = _TWO_PI / n
    return tuple(
        (math.cos(i * step), math.sin(i * step))
        for i in range(n)
    )


# Common unit templates — computed once at module load.
_UNIT_CIRCLE_32 = _build_unit_ngon(32)
_UNIT_CIRCLE_16 = _build_unit_ngon(16)
_UNIT_TRIANGLE  = _build_unit_ngon(3)
_UNIT_SQUARE    = _build_unit_ngon(4)
_UNIT_HEXAGON   = _build_unit_ngon(6)
_UNIT_OCTAGON   = _build_unit_ngon(8)

# Quick lookup for common segment counts.
_UNIT_CACHE: dict[int, tuple[tuple[float, float], ...]] = {
    3:  _UNIT_TRIANGLE,
    4:  _UNIT_SQUARE,
    6:  _UNIT_HEXAGON,
    8:  _UNIT_OCTAGON,
    16: _UNIT_CIRCLE_16,
    32: _UNIT_CIRCLE_32,
}


class Mesh:
    """Pre-computed geometry vertex generator with LRU caching.

    All methods are static and return ``list[tuple[float, float]]`` in
    local-space CCW winding order, suitable for passing directly to
    ``Sprite.polygon()`` or ``Visual(vertices=...)``.

    Internally, unit-radius templates are pre-computed at import time
    (trig done once) and scaled by simple multiplication.  An LRU cache
    (1024 entries) ensures repeated calls with identical arguments return
    the same list without any computation.

    Examples
    --------
    >>> Mesh.circle(0.5)           # 32-segment circle, radius 0.5
    >>> Mesh.triangle(0.4)         # equilateral triangle, circumradius 0.4
    >>> Mesh.ngon(6, 1.0)          # hexagon, radius 1.0
    >>> Mesh.rect(2.0, 1.0)        # 2×1 rectangle
    >>> Mesh.star(5, 1.0, 0.4)     # 5-point star
    >>> Mesh.rotated_rect(2.0, 0.3, 30)  # rotated rectangle
    """

    # ------------------------------------------------------------------
    # Core: n-gon with arbitrary radius and segment count
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=1024)
    def ngon(
        sides: int,
        radius: float = 1.0,
    ) -> list[tuple[float, float]]:
        """Return *sides* vertices of a regular polygon with given *radius*.

        Uses pre-computed unit templates for common side counts (3, 4, 6,
        8, 16, 32) and builds on demand for others.
        """
        if sides < 3:
            raise ValueError(f"ngon requires sides >= 3, got {sides}")
        unit = _UNIT_CACHE.get(sides)
        if unit is None:
            unit = _build_unit_ngon(sides)
        if radius == 1.0:
            return [(ux, uy) for ux, uy in unit]
        return [(ux * radius, uy * radius) for ux, uy in unit]

    # ------------------------------------------------------------------
    # Circle (n-gon with 32 segments by default)
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=1024)
    def circle(
        radius: float = 1.0,
        segments: int = 32,
    ) -> list[tuple[float, float]]:
        """Return vertices approximating a circle with *segments* sides.

        Default 32 segments matches the engine's visual circle resolution.
        Pre-computed for segments in {16, 32}; any other count is built on
        demand and cached.
        """
        return Mesh.ngon(segments, radius)

    # ------------------------------------------------------------------
    # Triangle (equilateral, apex at top)
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=1024)
    def triangle(
        radius: float = 1.0,
    ) -> list[tuple[float, float]]:
        """Return 3 vertices of an equilateral triangle (circumradius = *radius*).

        Apex points upward (first vertex at 90°).
        """
        unit = _UNIT_TRIANGLE
        # Rotate so apex is at top: shift by 90° (index offset = n/4).
        # For 3 vertices, just start from the vertex nearest 90°.
        # Pre-compute: (cos(90+120k), sin(90+120k)) for k=0,1,2.
        r = radius
        return [
            (r * math.cos(math.radians(90 + 120 * i)),
             r * math.sin(math.radians(90 + 120 * i)))
            for i in range(3)
        ]

    # ------------------------------------------------------------------
    # Rectangle
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=1024)
    def rect(
        width: float = 1.0,
        height: float = 1.0,
    ) -> list[tuple[float, float]]:
        """Return 4 CCW vertices of a *width* × *height* rectangle."""
        hw = width / 2.0
        hh = height / 2.0
        return [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]

    # ------------------------------------------------------------------
    # Rotated rectangle
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=1024)
    def rotated_rect(
        width: float,
        height: float,
        angle_deg: float,
    ) -> list[tuple[float, float]]:
        """Return 4 CCW vertices of a *width* × *height* rectangle
        pre-rotated by *angle_deg* degrees about the origin.
        """
        hw, hh = width / 2.0, height / 2.0
        a = math.radians(angle_deg)
        ca, sa = math.cos(a), math.sin(a)
        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        return [(x * ca - y * sa, x * sa + y * ca) for x, y in corners]

    # ------------------------------------------------------------------
    # Star
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=1024)
    def star(
        points: int = 5,
        outer: float = 1.0,
        inner: float = 0.4,
    ) -> list[tuple[float, float]]:
        """Return vertices of a *points*-pointed star.

        *outer* is the tip radius, *inner* is the valley radius.
        First tip points upward (90°).

        Note: the resulting polygon is non-convex and cannot be used
        directly for pymunk physics (which requires convex shapes).
        Suitable for visual-only entities or decomposed physics.
        """
        if points < 3:
            raise ValueError(f"star requires points >= 3, got {points}")
        verts: list[tuple[float, float]] = []
        step = math.pi / points  # half-step between tip and valley
        offset = math.pi / 2.0   # start at top
        for i in range(2 * points):
            r = outer if i % 2 == 0 else inner
            angle = offset + i * step
            verts.append((r * math.cos(angle), r * math.sin(angle)))
        return verts

    # ------------------------------------------------------------------
    # Diamond (rhombus)
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=1024)
    def diamond(
        width: float = 1.0,
        height: float = 1.0,
    ) -> list[tuple[float, float]]:
        """Return 4 CCW vertices of a diamond (rhombus).

        *width* is the horizontal span, *height* is the vertical span.
        """
        hw = width / 2.0
        hh = height / 2.0
        return [(0.0, hh), (-hw, 0.0), (0.0, -hh), (hw, 0.0)]

    # ------------------------------------------------------------------
    # Utility: shoelace area
    # ------------------------------------------------------------------

    @staticmethod
    def area(vertices: list[tuple[float, float]]) -> float:
        """Return the unsigned area of a simple polygon (Shoelace formula)."""
        n = len(vertices)
        total = 0.0
        for i in range(n):
            x1, y1 = vertices[i]
            x2, y2 = vertices[(i + 1) % n]
            total += x1 * y2 - x2 * y1
        return abs(total) / 2.0

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    @staticmethod
    def cache_info() -> dict[str, object]:
        """Return LRU cache statistics for all cached methods."""
        return {
            "ngon": Mesh.ngon.cache_info(),
            "circle": Mesh.circle.cache_info(),
            "triangle": Mesh.triangle.cache_info(),
            "rect": Mesh.rect.cache_info(),
            "rotated_rect": Mesh.rotated_rect.cache_info(),
            "star": Mesh.star.cache_info(),
            "diamond": Mesh.diamond.cache_info(),
        }

    @staticmethod
    def clear_cache() -> None:
        """Clear all LRU caches (useful for testing or memory pressure)."""
        Mesh.ngon.cache_clear()
        Mesh.circle.cache_clear()
        Mesh.triangle.cache_clear()
        Mesh.rect.cache_clear()
        Mesh.rotated_rect.cache_clear()
        Mesh.star.cache_clear()
        Mesh.diamond.cache_clear()
