# tests/test_mesh.py
# Tests for Mesh: pre-computed geometry templates with LRU caching.

import math
import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from strata.shapes.mesh import Mesh


class TestMeshCircle:
    def test_default_32_segments(self):
        verts = Mesh.circle(1.0)
        assert len(verts) == 32

    def test_custom_segments(self):
        verts = Mesh.circle(1.0, segments=16)
        assert len(verts) == 16

    def test_radius_scaling(self):
        verts = Mesh.circle(2.0, segments=4)
        # 4-segment "circle" = unit square scaled by 2
        for x, y in verts:
            assert math.hypot(x, y) == pytest.approx(2.0, abs=1e-10)

    def test_cached_returns_same_list(self):
        """Identical params should return from cache (same object)."""
        a = Mesh.circle(0.5, 32)
        b = Mesh.circle(0.5, 32)
        assert a is b


class TestMeshNgon:
    def test_triangle(self):
        verts = Mesh.ngon(3, 1.0)
        assert len(verts) == 3

    def test_hexagon(self):
        verts = Mesh.ngon(6, 1.0)
        assert len(verts) == 6

    def test_unit_radius(self):
        verts = Mesh.ngon(6, 1.0)
        for x, y in verts:
            assert math.hypot(x, y) == pytest.approx(1.0, abs=1e-10)

    def test_scaled_radius(self):
        r = 3.5
        verts = Mesh.ngon(8, r)
        for x, y in verts:
            assert math.hypot(x, y) == pytest.approx(r, abs=1e-10)

    def test_min_sides(self):
        with pytest.raises(ValueError, match="sides >= 3"):
            Mesh.ngon(2)

    def test_cached(self):
        a = Mesh.ngon(6, 1.0)
        b = Mesh.ngon(6, 1.0)
        assert a is b


class TestMeshTriangle:
    def test_vertex_count(self):
        verts = Mesh.triangle(1.0)
        assert len(verts) == 3

    def test_apex_at_top(self):
        """First vertex should be at (0, radius)."""
        verts = Mesh.triangle(1.0)
        assert verts[0][0] == pytest.approx(0.0, abs=1e-10)
        assert verts[0][1] == pytest.approx(1.0, abs=1e-10)

    def test_circumradius(self):
        r = 0.45
        verts = Mesh.triangle(r)
        for x, y in verts:
            assert math.hypot(x, y) == pytest.approx(r, abs=1e-10)


class TestMeshRect:
    def test_vertex_count(self):
        verts = Mesh.rect(2.0, 1.0)
        assert len(verts) == 4

    def test_dimensions(self):
        w, h = 3.0, 2.0
        verts = Mesh.rect(w, h)
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        assert max(xs) - min(xs) == pytest.approx(w)
        assert max(ys) - min(ys) == pytest.approx(h)

    def test_ccw_winding(self):
        """Area should be positive for CCW winding."""
        verts = Mesh.rect(1.0, 1.0)
        area = Mesh.area(verts)
        assert area == pytest.approx(1.0)


class TestMeshRotatedRect:
    def test_zero_rotation_matches_rect(self):
        """A 0° rotation should produce the same dimensions as rect."""
        w, h = 2.0, 1.0
        normal = Mesh.rect(w, h)
        rotated = Mesh.rotated_rect(w, h, 0.0)
        for (nx, ny), (rx, ry) in zip(normal, rotated):
            assert nx == pytest.approx(rx, abs=1e-10)
            assert ny == pytest.approx(ry, abs=1e-10)

    def test_90_rotation(self):
        """90° rotation swaps width and height axes."""
        w, h = 4.0, 1.0
        verts = Mesh.rotated_rect(w, h, 90.0)
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        # After 90° rotation, the 4-unit width should span the Y axis
        assert max(ys) - min(ys) == pytest.approx(w, abs=1e-10)
        assert max(xs) - min(xs) == pytest.approx(h, abs=1e-10)

    def test_area_preserved(self):
        w, h = 3.0, 2.0
        area = Mesh.area(Mesh.rotated_rect(w, h, 45.0))
        assert area == pytest.approx(w * h, abs=1e-8)


class TestMeshDiamond:
    def test_vertex_count(self):
        verts = Mesh.diamond(1.0, 2.0)
        assert len(verts) == 4

    def test_span(self):
        w, h = 1.0, 2.0
        verts = Mesh.diamond(w, h)
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        assert max(xs) - min(xs) == pytest.approx(w)
        assert max(ys) - min(ys) == pytest.approx(h)


class TestMeshStar:
    def test_vertex_count(self):
        verts = Mesh.star(5, 1.0, 0.4)
        assert len(verts) == 10  # 5 tips + 5 valleys

    def test_tip_at_top(self):
        """First vertex (tip) should be at (0, outer_radius)."""
        verts = Mesh.star(5, 1.0, 0.4)
        assert verts[0][0] == pytest.approx(0.0, abs=1e-10)
        assert verts[0][1] == pytest.approx(1.0, abs=1e-10)

    def test_min_points(self):
        with pytest.raises(ValueError, match="points >= 3"):
            Mesh.star(2)


class TestMeshArea:
    def test_unit_square(self):
        assert Mesh.area(Mesh.rect(1.0, 1.0)) == pytest.approx(1.0)

    def test_circle_area(self):
        r = 1.0
        area = Mesh.area(Mesh.circle(r, 1000))
        assert area == pytest.approx(math.pi * r * r, abs=0.01)


class TestMeshCache:
    def test_cache_info_returns_dict(self):
        Mesh.clear_cache()
        Mesh.circle(1.0)
        info = Mesh.cache_info()
        assert "circle" in info
        assert "ngon" in info

    def test_cache_hit(self):
        Mesh.clear_cache()
        Mesh.ngon(6, 1.0)
        Mesh.ngon(6, 1.0)
        info = Mesh.cache_info()
        assert info["ngon"].hits >= 1  # type: ignore[union-attr]

    def test_clear_cache(self):
        Mesh.circle(1.0)
        Mesh.clear_cache()
        info = Mesh.cache_info()
        assert info["circle"].currsize == 0  # type: ignore[union-attr]


class TestMeshFactoryIntegration:
    """Verify factory.py delegates to Mesh correctly."""

    def test_circle_factory_uses_mesh(self):
        from strata.shapes.factory import _circle_vertices
        verts = _circle_vertices(0.5, 32)
        mesh_verts = Mesh.circle(0.5, 32)
        assert verts is mesh_verts  # same cached object

    def test_rect_factory_uses_mesh(self):
        from strata.shapes.factory import _rect_vertices
        verts = _rect_vertices(2.0, 1.0)
        mesh_verts = Mesh.rect(2.0, 1.0)
        assert verts is mesh_verts
