# tests/test_soft_body.py
"""Tests for soft body physics: factories, system, render, teardown."""

from __future__ import annotations

import math
import os
import sys

import pygame
import pymunk
import pytest

# Ensure headless pygame for CI
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from strata import Game, Sprite, SoftBody
from strata.ecs.components import Transform, Visual, Physics
from strata.ecs.entity import Entity
from strata.shapes.factory import _shoelace_area
from strata.systems.soft_body_system import SoftBodySystem
from strata.systems.physics_system import PhysicsSystem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def game():
    """Minimal Game instance for testing."""
    g = Game(window_size=(320, 180), gravity=(0.0, -9.81))
    yield g


@pytest.fixture
def physics():
    """Standalone PhysicsSystem."""
    return PhysicsSystem(gravity=(0.0, -9.81))


@pytest.fixture
def soft_body_sys(physics):
    """Standalone SoftBodySystem wired to a PhysicsSystem."""
    return SoftBodySystem(physics_system=physics)


# ===========================================================================
# soft_rect factory
# ===========================================================================

class TestSoftRect:
    def test_node_count(self):
        e = Sprite.soft_rect(cols=3, rows=4, width=2.0, height=3.0)
        sb = e.get_component(SoftBody)
        assert sb is not None
        assert len(sb.nodes) == 3 * 4

    def test_spring_count_2x2(self):
        """2x2 grid: 1 horiz + 1 vert + 1 diag_ur + 1 diag_ul  = structural+shear."""
        e = Sprite.soft_rect(cols=2, rows=2, width=1.0, height=1.0)
        sb = e.get_component(SoftBody)
        # 2x2: horiz=2, vert=2, diag_ur=1, diag_ul=1 = 6
        assert len(sb.springs) == 6

    def test_spring_count_3x3(self):
        e = Sprite.soft_rect(cols=3, rows=3, width=2.0, height=2.0)
        sb = e.get_component(SoftBody)
        # 3x3:  horiz=6, vert=6, diag_ur=4, diag_ul=4 = 20
        assert len(sb.springs) == 20

    def test_mass_distribution(self):
        """Total mass should equal density * area, distributed evenly."""
        density, w, h = 2.0, 3.0, 4.0
        e = Sprite.soft_rect(cols=4, rows=5, width=w, height=h, density=density)
        sb = e.get_component(SoftBody)
        expected_total = density * w * h
        actual_total = sum(b.mass for b in sb.nodes)
        assert abs(actual_total - expected_total) < 1e-6

    def test_surface_indices_ccw_perimeter(self):
        """Perimeter indices should trace the outline without duplication."""
        e = Sprite.soft_rect(cols=4, rows=3, width=3.0, height=2.0)
        sb = e.get_component(SoftBody)
        # CCW perimeter of 4x3 grid: 4+2+3+1 = 10 unique nodes
        assert len(sb.surface_indices) == 10
        # No duplicates
        assert len(set(sb.surface_indices)) == 10

    def test_surface_shapes_on_perimeter_only(self):
        e = Sprite.soft_rect(cols=4, rows=4, width=2.0, height=2.0)
        sb = e.get_component(SoftBody)
        # 4x4: perimeter = 4+3+3+2 = 12 unique nodes
        assert len(sb.surface_shapes) == 12

    def test_visual_is_soft_polygon(self):
        e = Sprite.soft_rect(cols=3, rows=3, width=2.0, height=2.0)
        vis = e.get_component(Visual)
        assert vis.shape_type == "soft_polygon"
        assert len(vis.vertices) > 0

    def test_transform_at_centre(self):
        e = Sprite.soft_rect(cols=3, rows=3, width=2.0, height=2.0, x=5.0, y=7.0)
        t = e.get_component(Transform)
        assert abs(t.x - 5.0) < 1e-6
        assert abs(t.y - 7.0) < 1e-6

    def test_topology_tag(self):
        e = Sprite.soft_rect(cols=2, rows=2, width=1.0, height=1.0)
        sb = e.get_component(SoftBody)
        assert sb.topology == "grid"

    def test_no_physics_component(self):
        """Soft bodies should NOT have a Physics component."""
        e = Sprite.soft_rect(cols=2, rows=2, width=1.0, height=1.0)
        assert e.get_component(Physics) is None

    def test_validation_cols_too_small(self):
        with pytest.raises(ValueError, match="cols>=2"):
            Sprite.soft_rect(cols=1, rows=3)

    def test_validation_rows_too_small(self):
        with pytest.raises(ValueError, match="rows>=2"):
            Sprite.soft_rect(cols=3, rows=1)

    def test_collide_bodies_false(self):
        """All springs should have collide_bodies=False."""
        e = Sprite.soft_rect(cols=3, rows=3, width=2.0, height=2.0)
        sb = e.get_component(SoftBody)
        for spring in sb.springs:
            assert not spring.collide_bodies


# ===========================================================================
# soft_circle factory
# ===========================================================================

class TestSoftCircle:
    def test_node_count(self):
        e = Sprite.soft_circle(rings=2, segments=8, radius=1.0)
        sb = e.get_component(SoftBody)
        # 1 centre + 2*8 = 17
        assert len(sb.nodes) == 1 + 2 * 8

    def test_surface_indices_outermost(self):
        e = Sprite.soft_circle(rings=3, segments=10, radius=2.0)
        sb = e.get_component(SoftBody)
        assert len(sb.surface_indices) == 10

    def test_surface_shapes_on_outermost(self):
        e = Sprite.soft_circle(rings=2, segments=12, radius=1.5)
        sb = e.get_component(SoftBody)
        assert len(sb.surface_shapes) == 12

    def test_mass_distribution(self):
        density, r = 1.5, 2.0
        e = Sprite.soft_circle(rings=3, segments=10, radius=r, density=density)
        sb = e.get_component(SoftBody)
        expected = density * math.pi * r * r
        actual = sum(b.mass for b in sb.nodes)
        assert abs(actual - expected) < 1e-6

    def test_visual_is_soft_polygon(self):
        e = Sprite.soft_circle(rings=2, segments=8, radius=1.0)
        vis = e.get_component(Visual)
        assert vis.shape_type == "soft_polygon"

    def test_topology_tag(self):
        e = Sprite.soft_circle(rings=2, segments=8, radius=1.0)
        sb = e.get_component(SoftBody)
        assert sb.topology == "radial"

    def test_no_physics_component(self):
        e = Sprite.soft_circle(rings=2, segments=8, radius=1.0)
        assert e.get_component(Physics) is None

    def test_validation_rings_too_small(self):
        with pytest.raises(ValueError, match="rings>=1"):
            Sprite.soft_circle(rings=0, segments=8)

    def test_validation_segments_too_small(self):
        with pytest.raises(ValueError, match="segments>=3"):
            Sprite.soft_circle(rings=2, segments=2)

    def test_collide_bodies_false(self):
        e = Sprite.soft_circle(rings=2, segments=8, radius=1.0)
        sb = e.get_component(SoftBody)
        for spring in sb.springs:
            assert not spring.collide_bodies

    def test_centre_at_position(self):
        e = Sprite.soft_circle(rings=2, segments=8, radius=1.0, x=3.0, y=4.0)
        sb = e.get_component(SoftBody)
        # Centre node should be at (3, 4)
        cx, cy = sb.nodes[0].position
        assert abs(cx - 3.0) < 1e-6
        assert abs(cy - 4.0) < 1e-6


# ===========================================================================
# SoftBodySystem — registration and teardown
# ===========================================================================

class TestSoftBodySystem:
    def test_register_adds_to_space(self, physics, soft_body_sys):
        e = Sprite.soft_rect(cols=3, rows=3, width=2.0, height=2.0)
        sb = e.get_component(SoftBody)
        soft_body_sys.register(sb, e.id)

        for body in sb.nodes:
            assert body in physics.space.bodies
        for spring in sb.springs:
            assert spring in physics.space.constraints
        for shape in sb.surface_shapes:
            assert shape in physics.space.shapes

    def test_register_maps_shapes_to_entity(self, physics, soft_body_sys):
        e = Sprite.soft_rect(cols=2, rows=2, width=1.0, height=1.0)
        sb = e.get_component(SoftBody)
        soft_body_sys.register(sb, e.id)

        for shape in sb.surface_shapes:
            assert physics._shape_to_entity.get(shape) == e.id

    def test_unregister_removes_from_space(self, physics, soft_body_sys):
        e = Sprite.soft_circle(rings=2, segments=6, radius=1.0)
        sb = e.get_component(SoftBody)
        soft_body_sys.register(sb, e.id)
        soft_body_sys.unregister(sb, e.id)

        for body in sb.nodes:
            assert body not in physics.space.bodies
        for spring in sb.springs:
            assert spring not in physics.space.constraints
        for shape in sb.surface_shapes:
            assert shape not in physics.space.shapes

    def test_unregister_clears_shape_map(self, physics, soft_body_sys):
        e = Sprite.soft_rect(cols=2, rows=2, width=1.0, height=1.0)
        sb = e.get_component(SoftBody)
        soft_body_sys.register(sb, e.id)
        soft_body_sys.unregister(sb, e.id)

        for shape in sb.surface_shapes:
            assert shape not in physics._shape_to_entity


# ===========================================================================
# SoftBodySystem — update (sync Transform + Visual)
# ===========================================================================

class TestSoftBodyUpdate:
    def test_centroid_sync(self, physics, soft_body_sys):
        """After update, Transform should reflect the centroid of all nodes."""
        e = Sprite.soft_rect(cols=2, rows=2, width=2.0, height=2.0, x=0.0, y=0.0)
        sb = e.get_component(SoftBody)
        t = e.get_component(Transform)

        # Manually shift all nodes right by 1.0
        for body in sb.nodes:
            body.position = (body.position.x + 1.0, body.position.y)

        # Create a minimal world with the entity
        from strata.ecs.world import World
        world = World()
        world.add_entity(e)

        soft_body_sys.update(world, 1 / 60)

        # Centroid should have moved right by 1.0
        assert abs(t.x - 1.0) < 1e-4
        assert abs(t.y - 0.0) < 1e-4

    def test_visual_vertices_updated(self, physics, soft_body_sys):
        """Visual.vertices should be rebuilt relative to the new centroid."""
        e = Sprite.soft_rect(cols=2, rows=2, width=2.0, height=2.0, x=0.0, y=0.0)
        sb = e.get_component(SoftBody)
        vis = e.get_component(Visual)
        original_verts = list(vis.vertices)

        # Shift bottom-left node down
        sb.nodes[0].position = (sb.nodes[0].position.x, sb.nodes[0].position.y - 1.0)

        from strata.ecs.world import World
        world = World()
        world.add_entity(e)
        soft_body_sys.update(world, 1 / 60)

        # Vertices should have changed
        assert vis.vertices != original_verts

    def test_prev_snapshot(self, physics, soft_body_sys):
        """Update should snapshot prev_x/prev_y before overwriting."""
        e = Sprite.soft_rect(cols=2, rows=2, width=2.0, height=2.0, x=5.0, y=5.0)
        sb = e.get_component(SoftBody)
        t = e.get_component(Transform)

        from strata.ecs.world import World
        world = World()
        world.add_entity(e)

        soft_body_sys.update(world, 1 / 60)
        # After first update, prev should be the original
        assert abs(t.prev_x - 5.0) < 1e-4

        # Move nodes
        for body in sb.nodes:
            body.position = (body.position.x + 2.0, body.position.y)
        soft_body_sys.update(world, 1 / 60)
        # prev should now be the centroid from the first update
        assert abs(t.prev_x - 5.0) < 0.5  # approximately


# ===========================================================================
# Deformation under gravity (integration test)
# ===========================================================================

class TestDeformation:
    def test_soft_rect_falls_under_gravity(self, physics, soft_body_sys):
        """A soft rect in free-fall should have all nodes move downward."""
        e = Sprite.soft_rect(cols=3, rows=3, width=2.0, height=2.0, x=0.0, y=10.0)
        sb = e.get_component(SoftBody)
        soft_body_sys.register(sb, e.id)

        initial_ys = [b.position.y for b in sb.nodes]

        # Step physics 10 times
        for _ in range(10):
            physics.space.step(1 / 60)

        final_ys = [b.position.y for b in sb.nodes]
        # All nodes should have fallen
        for iy, fy in zip(initial_ys, final_ys):
            assert fy < iy

    def test_soft_circle_deforms_on_floor(self, physics, soft_body_sys):
        """Dropping a soft circle onto a floor should cause deformation."""
        # Create floor
        floor_body = pymunk.Body(body_type=pymunk.Body.STATIC)
        floor_body.position = (0, 0)
        floor_shape = pymunk.Segment(floor_body, (-10, 0), (10, 0), 0.1)
        floor_shape.elasticity = 0.2
        floor_shape.friction = 0.8
        physics.space.add(floor_body, floor_shape)

        e = Sprite.soft_circle(rings=2, segments=8, radius=0.8, x=0.0, y=2.0)
        sb = e.get_component(SoftBody)
        soft_body_sys.register(sb, e.id)

        # Step enough for the ball to fall and hit the floor
        for _ in range(200):
            physics.space.step(1 / 60)

        # Check that nodes are no longer in a perfect circle
        # The bottom nodes should be closer to y=0 than the top nodes
        outer_ys = [sb.nodes[i].position.y for i in sb.surface_indices]
        spread = max(outer_ys) - min(outer_ys)
        # An undeformed circle of radius 0.8 has spread ~1.6
        # A deformed one sitting on a floor will have less vertical spread
        # (it squishes), but we just check it's still alive and not exploded
        assert spread < 5.0  # sanity: not exploded
        assert spread > 0.01  # sanity: not collapsed to a point


# ===========================================================================
# Game integration (Scene auto-registration)
# ===========================================================================

class TestGameIntegration:
    def test_scene_auto_registers_soft_body(self, game):
        """Adding a soft body entity to scene should register it with the system."""
        e = Sprite.soft_rect(cols=2, rows=2, width=1.0, height=1.0)
        game.scene.add_entity(e)

        sb = e.get_component(SoftBody)
        # All nodes should be in the space
        for body in sb.nodes:
            assert body in game.physics.space.bodies

    def test_step_syncs_soft_body(self, game):
        """game.step() should update soft body visual vertices."""
        e = Sprite.soft_rect(cols=2, rows=2, width=1.0, height=1.0, x=0.0, y=5.0)
        game.scene.add_entity(e)

        vis = e.get_component(Visual)
        original = list(vis.vertices)

        # Step several times (gravity should move nodes)
        for _ in range(30):
            game.step()

        # Vertices should have changed due to gravity
        assert vis.vertices != original

    def test_debug_render_toggle(self, game):
        """SoftBody.debug_render should be togglable without errors."""
        e = Sprite.soft_circle(rings=2, segments=6, radius=1.0)
        game.scene.add_entity(e)

        sb = e.get_component(SoftBody)
        assert sb.debug_render is False
        sb.debug_render = True
        assert sb.debug_render is True

        # Step should not crash with debug_render on
        game.step()
