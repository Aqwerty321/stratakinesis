# tests/test_physics.py
# Tests for PhysicsSystem: body creation, mass, and simulation correctness.

import math
import os

import pytest
import pymunk

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from strata.shapes.factory import Sprite
from strata.ecs.components import Physics, Transform
from strata.config import FIXED_DT


class TestSpriteMass:
    def test_circle_mass_equals_density_times_area(self):
        """Circle mass = density * pi * r^2."""
        radius = 1.5
        density = 2.0
        ball = Sprite.circle(radius=radius, density=density)
        phys: Physics = ball.get_component(Physics)
        expected_mass = density * math.pi * radius ** 2
        assert phys.body.mass == pytest.approx(expected_mass, rel=1e-4)

    def test_rect_mass_equals_density_times_area(self):
        """Rect mass = density * width * height."""
        width, height, density = 3.0, 2.0, 1.5
        box = Sprite.rect(width=width, height=height, density=density)
        phys: Physics = box.get_component(Physics)
        expected_mass = density * width * height
        assert phys.body.mass == pytest.approx(expected_mass, rel=1e-4)

    def test_static_body_type_is_static(self):
        """static=True must produce a STATIC pymunk body."""
        ground = Sprite.rect(width=10.0, height=1.0, static=True)
        phys: Physics = ground.get_component(Physics)
        assert phys.body.body_type == pymunk.Body.STATIC

    def test_dynamic_body_type_is_dynamic(self):
        """physics=True must produce a DYNAMIC pymunk body."""
        ball = Sprite.circle(radius=0.5, physics=True)
        phys: Physics = ball.get_component(Physics)
        assert phys.body.body_type == pymunk.Body.DYNAMIC


class TestPhysicsSystemSimulation:
    def _make_game(self):
        from strata.core.loop import Game
        return Game(window_size=(800, 600))

    def test_ball_falls_under_gravity(self):
        """A free-falling ball should move downward after N steps."""
        game = self._make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0, physics=True)
        game.scene.add_entities(ball)

        initial_y = ball.get_component(Transform).y
        for _ in range(30):
            game.step(FIXED_DT)
        assert ball.get_component(Transform).y < initial_y

    def test_static_ground_does_not_move(self):
        """A static body must not change position after stepping."""
        game = self._make_game()
        ground = Sprite.rect(width=10.0, height=1.0, x=0.0, y=-4.0, static=True)
        game.scene.add_entities(ground)

        initial_y = ground.get_component(Transform).y
        for _ in range(60):
            game.step(FIXED_DT)
        assert ground.get_component(Transform).y == pytest.approx(initial_y)

    def test_ball_rests_on_ground(self):
        """Ball dropped onto ground should eventually settle above it."""
        game = self._make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=2.0, physics=True)
        ground = Sprite.rect(width=10.0, height=0.5, x=0.0, y=-3.0, static=True)
        game.scene.add_entities(ball, ground)

        # Run for 5 simulated seconds
        for _ in range(int(5.0 / FIXED_DT)):
            game.step(FIXED_DT)

        ball_y = ball.get_component(Transform).y
        ground_top = -3.0 + 0.25  # ground centre + half-height
        # Ball centre should be above ground surface
        assert ball_y > ground_top - 0.1
