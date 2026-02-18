# tests/test_camera.py
# Tests for world_to_screen / screen_to_world round-trip and scale-to-fit.

import pytest
from strata.render.camera import Camera
from strata.config import WORLD_WIDTH, WORLD_HEIGHT
from strata.systems.render_system import _lerp_angle
import math


class TestCameraScale:
    def test_scale_fits_width(self):
        """With a 16:9 window matching world aspect, scale should be window_w / WORLD_WIDTH."""
        cam = Camera((1600, 900))
        expected = 1600 / WORLD_WIDTH
        assert cam.scale == pytest.approx(expected)

    def test_scale_fits_height_when_window_is_tall(self):
        """If the window is taller than wide (relative to world aspect), height constrains."""
        cam = Camera((800, 1000))
        scale_from_w = 800 / WORLD_WIDTH
        scale_from_h = 1000 / WORLD_HEIGHT
        assert cam.scale == pytest.approx(min(scale_from_w, scale_from_h))

    def test_letterbox_offset_centred_horizontally(self):
        """When window is wider than world aspect, offset_x should be positive (pillar-box)."""
        cam = Camera((2000, 900))  # very wide
        # scale driven by height: 900 / 9 = 100; world_w in pixels = 16*100 = 1600
        # offset_x = (2000 - 1600) / 2 = 200
        assert cam.offset_x == pytest.approx(200.0)
        assert cam.offset_y == pytest.approx(0.0)


class TestCoordinateConversions:
    def test_origin_maps_to_viewport_centre(self):
        """World (0, 0) must map to the centre of the world rect in screen pixels."""
        cam = Camera((1600, 900))
        sx, sy = cam.world_to_screen(0.0, 0.0)
        # World rect centre = offset_x + WORLD_WIDTH/2 * scale, offset_y + WORLD_HEIGHT/2 * scale
        expected_sx = int(cam.offset_x + (WORLD_WIDTH / 2.0) * cam.scale)
        expected_sy = int(cam.offset_y + (WORLD_HEIGHT / 2.0) * cam.scale)
        assert sx == expected_sx
        assert sy == expected_sy

    def test_round_trip_world_to_screen_to_world(self):
        """Converting to screen and back should recover the original world coordinates."""
        cam = Camera((1024, 768))
        for wx, wy in [(0.0, 0.0), (3.5, -2.0), (-7.0, 4.0), (7.9, 4.4)]:
            sx, sy = cam.world_to_screen(wx, wy)
            rx, ry = cam.screen_to_world(sx, sy)
            # Integer pixel round-trip: tolerance of 1 pixel / scale
            tolerance = 1.0 / cam.scale + 1e-6
            assert abs(rx - wx) < tolerance, f"x mismatch for ({wx}, {wy})"
            assert abs(ry - wy) < tolerance, f"y mismatch for ({wx}, {wy})"

    def test_y_axis_flip(self):
        """World +Y (up) should map to a smaller screen-Y (higher on screen)."""
        cam = Camera((1024, 768))
        _, sy_up = cam.world_to_screen(0.0, 2.0)
        _, sy_down = cam.world_to_screen(0.0, -2.0)
        assert sy_up < sy_down

    def test_resize_updates_scale(self):
        cam = Camera((1600, 900))
        scale_before = cam.scale
        cam.resize((800, 450))
        assert cam.scale != pytest.approx(scale_before)
        assert cam.scale == pytest.approx(scale_before / 2.0)


class TestAngleLerp:
    def test_normal_lerp(self):
        assert _lerp_angle(0.0, 1.0, 0.5) == pytest.approx(0.5)

    def test_alpha_zero_returns_prev(self):
        assert _lerp_angle(0.3, 2.0, 0.0) == pytest.approx(0.3)

    def test_alpha_one_returns_curr(self):
        assert _lerp_angle(0.3, 2.0, 1.0) == pytest.approx(2.0)

    def test_wrap_positive_to_negative(self):
        """Crossing +π→−π should take the short path, not spin 350°."""
        prev = math.pi - 0.1
        curr = -(math.pi - 0.1)
        result = _lerp_angle(prev, curr, 0.5)
        # Short path: mid-point is near ±π, not near 0
        assert abs(result) > math.pi / 2.0

    def test_wrap_negative_to_positive(self):
        prev = -(math.pi - 0.1)
        curr = math.pi - 0.1
        result = _lerp_angle(prev, curr, 0.5)
        assert abs(result) > math.pi / 2.0

    def test_no_overshoot_small_delta(self):
        """Small delta should stay between prev and curr."""
        prev, curr = 0.1, 0.4
        result = _lerp_angle(prev, curr, 0.5)
        assert prev <= result <= curr
