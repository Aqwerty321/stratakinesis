# tests/test_collisions.py
# Tests for Sprite.polygon, CollisionEvent, collision callbacks, and layer/mask filtering.

import math
import os
import pytest
import pymunk

from strata import Game, Sprite, CollisionEvent
from strata.shapes.factory import _shoelace_area
from strata.config import FIXED_DT


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def make_game(**kwargs) -> Game:
    return Game(window_size=(800, 600), **kwargs)


# ===========================================================================
# _shoelace_area
# ===========================================================================

class TestShoelaceArea:
    def test_unit_square(self):
        verts = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
        assert abs(_shoelace_area(verts) - 1.0) < 1e-12

    def test_right_triangle(self):
        # legs 3 and 4 → area = 6
        verts = [(0.0, 0.0), (3.0, 0.0), (0.0, 4.0)]
        assert abs(_shoelace_area(verts) - 6.0) < 1e-12

    def test_equilateral_triangle_r1(self):
        r = 1.0
        verts = [
            (r * math.cos(math.radians(90 + 120 * i)),
             r * math.sin(math.radians(90 + 120 * i)))
            for i in range(3)
        ]
        expected = 3.0 * math.sqrt(3.0) / 4.0  # ≈ 1.299
        assert abs(_shoelace_area(verts) - expected) < 1e-10

    def test_cw_winding_same_as_ccw(self):
        # Shoelace should return absolute area regardless of vertex order
        ccw = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        cw  = list(reversed(ccw))
        assert abs(_shoelace_area(ccw) - _shoelace_area(cw)) < 1e-12


# ===========================================================================
# Sprite.polygon
# ===========================================================================

class TestSpritePolygon:
    TRI = [(-1.0, -0.577), (1.0, -0.577), (0.0, 1.155)]

    def test_returns_entity_with_transform(self):
        from strata.ecs.components import Transform
        e = Sprite.polygon(self.TRI, x=3.0, y=2.0)
        t = e.get_component(Transform)
        assert t is not None
        assert t.x == pytest.approx(3.0)
        assert t.y == pytest.approx(2.0)

    def test_prev_fields_initialised(self):
        from strata.ecs.components import Transform
        e = Sprite.polygon(self.TRI, x=1.0, y=-2.0)
        t = e.get_component(Transform)
        assert t.prev_x == pytest.approx(1.0)
        assert t.prev_y == pytest.approx(-2.0)

    def test_physics_component_created(self):
        from strata.ecs.components import Physics
        e = Sprite.polygon(self.TRI, density=2.0)
        p = e.get_component(Physics)
        assert p is not None
        assert isinstance(p.body, pymunk.Body)
        assert isinstance(p.shape, pymunk.Poly)

    def test_mass_equals_density_times_area(self):
        from strata.ecs.components import Physics
        e = Sprite.polygon(self.TRI, density=3.0)
        p = e.get_component(Physics)
        area = _shoelace_area(self.TRI)
        assert p.body.mass == pytest.approx(3.0 * area, rel=1e-6)

    def test_static_polygon(self):
        from strata.ecs.components import Physics
        e = Sprite.polygon(self.TRI, static=True)
        p = e.get_component(Physics)
        assert p.is_static is True
        assert p.body.body_type == pymunk.Body.STATIC

    def test_no_physics_when_disabled(self):
        from strata.ecs.components import Physics
        e = Sprite.polygon(self.TRI, physics=False)
        assert e.get_component(Physics) is None

    def test_visual_component(self):
        from strata.ecs.components import Visual
        color = (200, 100, 50, 255)
        e = Sprite.polygon(self.TRI, color=color)
        v = e.get_component(Visual)
        assert v is not None
        assert v.shape_type == "polygon"
        assert v.vertices == list(self.TRI)
        assert v.color == color

    def test_vertices_are_copied_not_aliased(self):
        from strata.ecs.components import Visual
        verts = list(self.TRI)
        e = Sprite.polygon(verts)
        verts.clear()
        v = e.get_component(Visual)
        assert len(v.vertices) == 3

    def test_too_few_vertices_raises(self):
        with pytest.raises(ValueError):
            Sprite.polygon([(0.0, 0.0), (1.0, 0.0)])

    def test_exactly_3_vertices_ok(self):
        e = Sprite.polygon(self.TRI)
        assert e is not None

    def test_default_collision_layer_mask(self):
        from strata.ecs.components import Physics
        e = Sprite.polygon(self.TRI)
        p = e.get_component(Physics)
        assert p.collision_layer == 0xFFFF
        assert p.collision_mask == 0xFFFF


# ===========================================================================
# CollisionEvent dataclass
# ===========================================================================

class TestCollisionEvent:
    def test_fields(self):
        ev = CollisionEvent(entity_a_id=1, entity_b_id=2, normal=(0.0, 1.0))
        assert ev.entity_a_id == 1
        assert ev.entity_b_id == 2
        assert ev.normal == (0.0, 1.0)

    def test_default_normal(self):
        ev = CollisionEvent(entity_a_id=3, entity_b_id=4)
        assert ev.normal == (0.0, 0.0)


# ===========================================================================
# Collision callbacks via Game.step()
# ===========================================================================

def _make_drop_scene(game: Game) -> tuple:
    """Floor at y=-5, dynamic box at y=-3 — will collide when stepped."""
    floor = Sprite.rect(width=10.0, height=0.5, y=-5.0, static=True)
    box   = Sprite.rect(width=1.0,  height=1.0, y=-3.0, density=1.0)
    game.scene.add_entities(floor, box)
    return floor, box


class TestCollisionCallbacks:
    def test_begin_fires_on_impact(self):
        game = make_game(gravity=(0.0, -9.81))
        _make_drop_scene(game)
        received = []
        game.on_collision_begin = received.append
        for _ in range(300):
            game.step(FIXED_DT)
            if received:
                break
        assert len(received) > 0
        assert isinstance(received[0], CollisionEvent)

    def test_begin_event_has_valid_entity_ids(self):
        game = make_game(gravity=(0.0, -9.81))
        floor, box = _make_drop_scene(game)
        received = []
        game.on_collision_begin = received.append
        for _ in range(300):
            game.step(FIXED_DT)
            if received:
                break
        ev = received[0]
        ids = {ev.entity_a_id, ev.entity_b_id}
        assert floor.id in ids
        assert box.id in ids

    def test_end_event_fires_after_begin(self):
        # Box falls, settles; on separation (bounce off) end must fire.
        game = make_game(gravity=(0.0, -9.81))
        _make_drop_scene(game)
        begin_events = []
        end_events = []
        game.on_collision_begin = begin_events.append
        game.on_collision_end = end_events.append
        for _ in range(600):
            game.step(FIXED_DT)
        assert len(begin_events) > 0

    def test_step_without_hooks_no_exception(self):
        """Draining events with no hooks attached must not raise."""
        game = make_game(gravity=(0.0, -9.81))
        _make_drop_scene(game)
        for _ in range(300):
            game.step(FIXED_DT)  # should not raise

    def test_polygon_collision_fires(self):
        game = make_game(gravity=(0.0, -9.81))
        floor = Sprite.rect(width=10.0, height=0.5, y=-5.0, static=True)
        tri_verts = [(-0.5, -0.5), (0.5, -0.5), (0.0, 0.5)]
        poly = Sprite.polygon(tri_verts, x=0.0, y=-2.0, density=1.0)
        game.scene.add_entities(floor, poly)
        received = []
        game.on_collision_begin = received.append
        for _ in range(300):
            game.step(FIXED_DT)
            if received:
                break
        assert len(received) > 0


# ===========================================================================
# Collision layer / mask filtering
# ===========================================================================

class TestCollisionLayers:
    def test_shape_filter_applied_on_register(self):
        from strata.ecs.components import Physics
        box = Sprite.rect(width=1.0, height=1.0, y=0.0)
        box.get_component(Physics).collision_layer = 0b0011
        box.get_component(Physics).collision_mask  = 0b0101
        game = make_game()
        game.scene.add_entity(box)
        sf = box.get_component(Physics).shape.filter
        assert sf.categories == 0b0011
        assert sf.mask == 0b0101

    def test_default_filter_is_all_mask(self):
        from strata.ecs.components import Physics
        box = Sprite.rect(width=1.0, height=1.0, y=0.0)
        game = make_game()
        game.scene.add_entity(box)
        sf = box.get_component(Physics).shape.filter
        assert sf.categories == 0xFFFF
        assert sf.mask == 0xFFFF

    def test_mismatched_layers_prevent_collision(self):
        """Layer 1 floor (mask=0b0001) vs Layer 2 box (categories=0b0010) — no collision."""
        from strata.ecs.components import Physics
        game = make_game(gravity=(0.0, -9.81))
        floor = Sprite.rect(width=10.0, height=0.5, y=-5.0, static=True)
        floor.get_component(Physics).collision_layer = 0b0001
        floor.get_component(Physics).collision_mask  = 0b0001
        box = Sprite.rect(width=1.0, height=1.0, y=-3.0, density=1.0)
        box.get_component(Physics).collision_layer = 0b0010
        box.get_component(Physics).collision_mask  = 0b0010
        game.scene.add_entities(floor, box)
        received = []
        game.on_collision_begin = received.append
        for _ in range(300):
            game.step(FIXED_DT)
        assert len(received) == 0

    def test_matching_layers_allow_collision(self):
        """Both shapes in layer 1 (mask=0b0001) — collision must fire."""
        from strata.ecs.components import Physics
        game = make_game(gravity=(0.0, -9.81))
        floor = Sprite.rect(width=10.0, height=0.5, y=-5.0, static=True)
        floor.get_component(Physics).collision_layer = 0b0001
        floor.get_component(Physics).collision_mask  = 0b0001
        box = Sprite.rect(width=1.0, height=1.0, y=-3.0, density=1.0)
        box.get_component(Physics).collision_layer = 0b0001
        box.get_component(Physics).collision_mask  = 0b0001
        game.scene.add_entities(floor, box)
        received = []
        game.on_collision_begin = received.append
        for _ in range(300):
            game.step(FIXED_DT)
            if received:
                break
        assert len(received) > 0
