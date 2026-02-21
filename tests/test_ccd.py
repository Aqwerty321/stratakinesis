# tests/test_ccd.py
# Tests for Continuous Collision Detection:
#   - Tunneling prevention (fast body vs thin wall)
#   - Determinism (identical scenes produce identical results)
#   - Adaptive substep correctness
#   - Zero-overhead for slow bodies
#   - Edge cases (overlap at spawn, head-on collision)

import math
import os

import pytest
import pymunk

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from strata.shapes.factory import Sprite
from strata.ecs.components import Physics, Transform
from strata.ecs.world import World
from strata.systems.physics_system import PhysicsSystem
from strata.config import FIXED_DT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game(**kwargs):
    from strata.core.loop import Game
    return Game(window_size=(800, 600), **kwargs)


def _make_physics(**kwargs) -> PhysicsSystem:
    """Create a standalone PhysicsSystem (no Game/window needed)."""
    return PhysicsSystem(**kwargs)


def _step_physics(physics: PhysicsSystem, world: World, n: int = 1, dt: float = FIXED_DT):
    for _ in range(n):
        physics.update(world, dt)


# ---------------------------------------------------------------------------
# Space solver tuning
# ---------------------------------------------------------------------------

class TestSolverTuning:
    def test_default_iterations(self):
        p = _make_physics()
        assert p.space.iterations == 20

    def test_default_collision_slop(self):
        p = _make_physics()
        assert p.space.collision_slop == pytest.approx(0.02)

    def test_custom_iterations(self):
        p = _make_physics(iterations=30)
        assert p.space.iterations == 30

    def test_custom_slop(self):
        p = _make_physics(collision_slop=0.05)
        assert p.space.collision_slop == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# Shape extent registry
# ---------------------------------------------------------------------------

class TestShapeExtent:
    def test_circle_extent(self):
        p = _make_physics()
        radius = 0.5
        body = pymunk.Body(1, 1)
        shape = pymunk.Circle(body, radius)
        extent = p._shape_extent(shape)
        assert extent == pytest.approx(2.0 * radius)

    def test_poly_extent(self):
        """Poly extent = min(bb width, bb height)."""
        p = _make_physics()
        body = pymunk.Body(1, 1)
        body.position = (0, 0)
        # 2 × 1 rectangle — min extent should be the shorter axis
        shape = pymunk.Poly.create_box(body, (2.0, 1.0))
        extent = p._shape_extent(shape)
        assert extent == pytest.approx(1.0, abs=0.1)

    def test_segment_extent(self):
        p = _make_physics()
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        shape = pymunk.Segment(body, (-5, 0), (5, 0), 0.1)
        extent = p._shape_extent(shape)
        assert extent == pytest.approx(0.2)

    def test_dynamic_body_registered_for_ccd(self):
        """Dynamic bodies with shapes are added to _ccd_bodies."""
        p = _make_physics()
        ball = Sprite.circle(radius=0.5, x=0, y=0)
        phys = ball.get_component(Physics)
        p.register(phys, entity_id=1)
        assert len(p._ccd_bodies) == 1
        assert len(p._ccd_extents_list) == 1
        assert p._ccd_extents_list[0] == pytest.approx(1.0)

    def test_static_body_excluded_from_ccd(self):
        """Static bodies must not be tracked for CCD."""
        p = _make_physics()
        wall = Sprite.rect(width=10, height=0.5, static=True)
        phys = wall.get_component(Physics)
        p.register(phys, entity_id=2)
        assert len(p._ccd_bodies) == 0

    def test_ccd_disabled_skips_registration(self):
        """When ccd=False, no CCD bodies are tracked."""
        p = _make_physics(ccd=False)
        ball = Sprite.circle(radius=0.5)
        phys = ball.get_component(Physics)
        p.register(phys, entity_id=3)
        assert len(p._ccd_bodies) == 0


# ---------------------------------------------------------------------------
# Adaptive substep calculation
# ---------------------------------------------------------------------------

class TestAdaptiveSubsteps:
    def test_slow_body_uses_base_substeps(self):
        """A body at rest should yield base_substeps (no extra substeps)."""
        p = _make_physics(substeps=1, ccd=True, gravity=(0, 0))
        ball = Sprite.circle(radius=0.5)
        phys = ball.get_component(Physics)
        p.register(phys, entity_id=1)
        # body velocity is (0, 0) at registration
        n = p._compute_substeps(FIXED_DT)
        assert n == 1

    def test_fast_body_increases_substeps(self):
        """A very fast body should force more substeps."""
        p = _make_physics(substeps=1, ccd=True, gravity=(0, 0))
        ball = Sprite.circle(radius=0.5)
        phys = ball.get_component(Physics)
        p.register(phys, entity_id=1)
        # Set high velocity: travel = 100 * (1/60) ≈ 1.667, extent = 1.0
        # ratio = 1.667, needed = ceil(1.667 / 0.5) = 4
        phys.body.velocity = (100, 0)
        n = p._compute_substeps(FIXED_DT)
        assert n >= 4

    def test_max_substeps_cap(self):
        """Should never exceed max_substeps even at extreme velocities."""
        p = _make_physics(substeps=1, ccd=True, max_substeps=8, gravity=(0, 0))
        ball = Sprite.circle(radius=0.1)  # small body, extent=0.2
        phys = ball.get_component(Physics)
        p.register(phys, entity_id=1)
        phys.body.velocity = (10000, 0)  # absurdly fast
        n = p._compute_substeps(FIXED_DT)
        assert n == 8

    def test_no_ccd_bodies_uses_base(self):
        """With no dynamic CCD bodies, use base substeps."""
        p = _make_physics(substeps=4, ccd=True)
        n = p._compute_substeps(FIXED_DT)
        assert n == 4


# ---------------------------------------------------------------------------
# Tunneling prevention (integration)
# ---------------------------------------------------------------------------

class TestTunnelingPrevention:
    def test_fast_circle_vs_thin_wall(self):
        """A very fast small circle must not tunnel through a thin wall.

        Scenario: circle at x=-5 with velocity (300, 0), thin wall at x=0.
        After several steps the circle must be on the left side (x < 0.5)
        or resting against the wall — never on the far side.
        """
        game = _make_game(physics_ccd=True, physics_max_substeps=32)
        game.physics.space.gravity = (0, 0)

        # Fast projectile
        bullet = Sprite.circle(radius=0.2, x=-5.0, y=0.0)
        game.scene.add_entity(bullet)
        bullet.get_component(Physics).body.velocity = (300, 0)

        # Thin static wall at x=0
        wall = Sprite.rect(width=0.1, height=10.0, x=0.0, y=0.0, static=True)
        game.scene.add_entity(wall)

        # Step for 60 frames (1 second at 60Hz)
        for _ in range(60):
            game.step(FIXED_DT)

        bx = bullet.get_component(Transform).x
        # The bullet must NOT have tunneled past the wall.
        # It should be on the left side or embedded/resting at the wall.
        assert bx < 0.5, f"bullet tunneled to x={bx}, expected < 0.5"

    def test_fast_rect_vs_thin_floor(self):
        """A fast rectangle falling onto a thin floor must not tunnel through."""
        game = _make_game(physics_ccd=True)
        game.physics.space.gravity = (0, -50)

        box = Sprite.rect(width=1.0, height=1.0, x=0.0, y=10.0)
        game.scene.add_entity(box)
        box.get_component(Physics).body.velocity = (0, -200)

        floor = Sprite.rect(width=20.0, height=0.1, x=0.0, y=-5.0, static=True)
        game.scene.add_entity(floor)

        for _ in range(120):
            game.step(FIXED_DT)

        by = box.get_component(Transform).y
        floor_top = -5.0 + 0.05
        assert by > floor_top - 1.0, f"box tunneled to y={by}"

    def test_head_on_collision(self):
        """Two fast circles approaching each other must collide, not pass through."""
        game = _make_game(physics_ccd=True)
        game.physics.space.gravity = (0, 0)

        left = Sprite.circle(radius=0.3, x=-8.0, y=0.0)
        right = Sprite.circle(radius=0.3, x=8.0, y=0.0)
        game.scene.add_entity(left)
        game.scene.add_entity(right)
        left.get_component(Physics).body.velocity = (200, 0)
        right.get_component(Physics).body.velocity = (-200, 0)

        for _ in range(60):
            game.step(FIXED_DT)

        lx = left.get_component(Transform).x
        rx = right.get_component(Transform).x
        # After collision they should have bounced back — left should be
        # to the left of right.
        assert lx < rx, f"bodies passed through each other: left.x={lx}, right.x={rx}"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_identical_runs_produce_same_positions(self):
        """Running the exact same scene twice must yield identical positions."""
        def _run_scene():
            game = _make_game(physics_ccd=True, physics_max_substeps=16)
            game.physics.space.gravity = (0, -9.81)

            ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
            game.scene.add_entity(ball)
            ball.get_component(Physics).body.velocity = (50, 0)

            ground = Sprite.rect(width=20, height=0.5, x=0, y=-4, static=True)
            game.scene.add_entity(ground)

            positions = []
            for _ in range(120):
                game.step(FIXED_DT)
                t = ball.get_component(Transform)
                positions.append((t.x, t.y))
            return positions

        run1 = _run_scene()
        run2 = _run_scene()
        for i, (p1, p2) in enumerate(zip(run1, run2)):
            assert p1[0] == pytest.approx(p2[0], abs=1e-12), f"x differs at frame {i}"
            assert p1[1] == pytest.approx(p2[1], abs=1e-12), f"y differs at frame {i}"


# ---------------------------------------------------------------------------
# CCD disabled: zero overhead
# ---------------------------------------------------------------------------

class TestCCDDisabled:
    def test_ccd_off_uses_fixed_substeps(self):
        """With ccd=False, substep count should stay at the base value."""
        game = _make_game(physics_ccd=False, physics_substeps=2)
        ball = Sprite.circle(radius=0.5, x=0, y=5)
        game.scene.add_entity(ball)
        ball.get_component(Physics).body.velocity = (500, 0)

        # Step once — substeps should remain at base
        game.step(FIXED_DT)
        assert game.physics.substeps == 2


# ---------------------------------------------------------------------------
# Soft body CCD exclusion
# ---------------------------------------------------------------------------

class TestSoftBodyExclusion:
    def test_soft_body_nodes_excluded_from_ccd(self):
        """Soft body node bodies should be marked in _soft_body_bodies set."""
        game = _make_game(physics_substeps=4, physics_ccd=True)
        soft = Sprite.soft_rect(cols=3, rows=3, width=2.0, height=2.0, x=0, y=3)
        game.scene.add_entity(soft)

        from strata.ecs.components import SoftBody
        sb = soft.get_component(SoftBody)
        # All node body ids should be in the exclusion set
        for body in sb.nodes:
            assert id(body) in game.physics._soft_body_bodies
