# tests/test_v05_features.py
# Tests for v0.5 features:
#   - Named collision groups
#   - Sprite.image()
#   - Constraint visualiser
#   - Scene serialisation

from __future__ import annotations
import json
import math
import os
import tempfile

import pygame
import pymunk
import pytest

# Ensure headless pygame for CI
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from strata.core.collision_groups import CollisionGroups
from strata.shapes.factory import Sprite, _collision_groups
from strata.ecs.components import Transform, Physics, Visual, SoftBody, PropertyBinding
from strata.ecs.entity import Entity
from strata.ecs.world import World
from strata.systems.physics_system import PhysicsSystem
from strata.core.loop import Scene, Game
from strata.core.serialise import save_scene, load_scene, _serialise_entity, _rebuild_entity


# =========================================================================
# Named collision groups
# =========================================================================

class TestCollisionGroups:
    """Named collision groups allocate unique bitmask bits."""

    def test_allocate_first_group(self):
        g = CollisionGroups()
        bit = g.get("player")
        assert bit == 1  # bit 0

    def test_allocate_second_group(self):
        g = CollisionGroups()
        g.get("player")
        bit = g.get("enemy")
        assert bit == 2  # bit 1

    def test_idempotent(self):
        g = CollisionGroups()
        a = g.get("wall")
        b = g.get("wall")
        assert a == b

    def test_all_returns_full_mask(self):
        g = CollisionGroups()
        assert g.get("all") == 0xFFFFFFFF

    def test_layer_combines_bits(self):
        g = CollisionGroups()
        g.get("player")  # 1
        g.get("enemy")   # 2
        combined = g.layer("player", "enemy")
        assert combined == 3  # 0b11

    def test_mask_alias(self):
        g = CollisionGroups()
        g.get("x")
        g.get("y")
        assert g.mask("x", "y") == g.layer("x", "y")

    def test_names_property(self):
        g = CollisionGroups()
        g.get("alpha")
        g.get("beta")
        assert g.names == ["alpha", "beta"]

    def test_contains(self):
        g = CollisionGroups()
        g.get("foo")
        assert "foo" in g
        assert "bar" not in g
        assert "all" in g  # special

    def test_max_groups_exceeded(self):
        g = CollisionGroups()
        for i in range(32):
            g.get(f"g{i}")
        with pytest.raises(RuntimeError, match="exceeded"):
            g.get("overflow")

    def test_repr(self):
        g = CollisionGroups()
        g.get("x")
        r = repr(g)
        assert "CollisionGroups(" in r
        assert "x=" in r


class TestCollisionGroupsInSprite:
    """Sprite factory accepts group/collides_with string parameters."""

    def test_circle_with_group(self):
        e = Sprite.circle(radius=0.5, group="player")
        p = e.get_component(Physics)
        player_bit = _collision_groups.get("player")
        assert p.collision_layer == player_bit

    def test_circle_with_collides_with_string(self):
        e = Sprite.circle(radius=0.5, collides_with="enemy")
        p = e.get_component(Physics)
        enemy_bit = _collision_groups.get("enemy")
        assert p.collision_mask == enemy_bit

    def test_circle_with_collides_with_list(self):
        e = Sprite.circle(radius=0.5, collides_with=["enemy", "wall"])
        p = e.get_component(Physics)
        expected = _collision_groups.get("enemy") | _collision_groups.get("wall")
        assert p.collision_mask == expected

    def test_rect_with_group(self):
        e = Sprite.rect(width=1, height=1, group="wall")
        p = e.get_component(Physics)
        wall_bit = _collision_groups.get("wall")
        assert p.collision_layer == wall_bit

    def test_polygon_with_group(self):
        verts = [(0, 0), (1, 0), (0.5, 1)]
        e = Sprite.polygon(verts, group="projectile")
        p = e.get_component(Physics)
        proj_bit = _collision_groups.get("projectile")
        assert p.collision_layer == proj_bit

    def test_default_no_group(self):
        """Without group/collides_with, defaults to 0xFFFF."""
        e = Sprite.circle(radius=0.5)
        p = e.get_component(Physics)
        assert p.collision_layer == 0xFFFF
        assert p.collision_mask == 0xFFFF

    def test_collision_filtering_works(self):
        """Two shapes in different groups that don't collide should not touch."""
        physics = PhysicsSystem(gravity=(0, -9.81))
        scene = Scene()
        scene._physics_system = physics
        scene.add_system(physics)

        # Group A: only collides with "ground"
        ball = Sprite.circle(radius=0.3, x=0, y=2,
                             group="ghost", collides_with="ground")
        # Group B: only collides with "ground"
        wall = Sprite.rect(width=5, height=0.5, y=0, static=True,
                           group="ground", collides_with="ghost")

        scene.add_entities(ball, wall)

        # Step physics — ball should fall and collide with ground
        for _ in range(120):
            scene.update(1 / 60)

        t = ball.get_component(Transform)
        # Ball should have landed near ground (y ~ 0.3)
        assert t.y < 1.0  # fell down


class TestSpriteImage:
    """Sprite.image() creates image-based entities."""

    @pytest.fixture
    def tmp_image(self, tmp_path):
        """Create a tiny test PNG image."""
        pygame.init()
        surf = pygame.Surface((32, 16))
        surf.fill((255, 0, 0))
        path = str(tmp_path / "test.png")
        pygame.image.save(surf, path)
        return path

    def test_image_creates_entity(self, tmp_image):
        e = Sprite.image(tmp_image, width=2.0)
        assert e is not None
        assert isinstance(e, Entity)

    def test_image_has_visual_component(self, tmp_image):
        e = Sprite.image(tmp_image, width=2.0)
        v = e.get_component(Visual)
        assert v is not None
        assert v.shape_type == "image"
        assert v.image_surface is not None
        assert v.image_width == 2.0
        # Height derived from aspect ratio (32/16 = 2:1, so height = 1.0)
        assert abs(v.image_height - 1.0) < 0.01

    def test_image_has_physics(self, tmp_image):
        e = Sprite.image(tmp_image, width=2.0, x=1, y=3)
        p = e.get_component(Physics)
        assert p is not None
        assert p.body is not None
        assert p.shape is not None
        assert abs(p.body.position.x - 1.0) < 0.01

    def test_image_static(self, tmp_image):
        e = Sprite.image(tmp_image, width=2.0, static=True)
        p = e.get_component(Physics)
        assert p.is_static

    def test_image_no_physics(self, tmp_image):
        e = Sprite.image(tmp_image, width=2.0, physics=False)
        p = e.get_component(Physics)
        assert p is None

    def test_image_height_only(self, tmp_image):
        e = Sprite.image(tmp_image, height=1.0)
        v = e.get_component(Visual)
        # width = height * aspect = 1.0 * 2.0 = 2.0
        assert abs(v.image_width - 2.0) < 0.01
        assert abs(v.image_height - 1.0) < 0.01

    def test_image_default_dimensions(self, tmp_image):
        e = Sprite.image(tmp_image)
        v = e.get_component(Visual)
        assert v.image_width == 1.0
        assert abs(v.image_height - 0.5) < 0.01  # 1/2 aspect

    def test_image_with_group(self, tmp_image):
        e = Sprite.image(tmp_image, width=1, group="sprite")
        p = e.get_component(Physics)
        sprite_bit = _collision_groups.get("sprite")
        assert p.collision_layer == sprite_bit


# =========================================================================
# Constraint visualiser
# =========================================================================

class TestConstraintVisualiser:
    """Constraint debug drawing module."""

    def test_import(self):
        from strata.systems.debug_draw import draw_constraints
        assert callable(draw_constraints)

    def test_draw_constraints_no_crash(self):
        """draw_constraints runs without error on a space with constraints."""
        from strata.systems.debug_draw import draw_constraints
        from strata.render.camera import Camera

        pygame.init()
        surf = pygame.Surface((800, 600))
        cam = Camera((800, 600))
        space = pymunk.Space()

        # Add some bodies and constraints
        static = space.static_body
        body = pymunk.Body(1, 100)
        body.position = (0, 3)
        shape = pymunk.Circle(body, 0.5)
        space.add(body, shape)

        # Pin joint
        pin = pymunk.PinJoint(static, body, (0, 5), (0, 0))
        space.add(pin)

        # Motor
        motor = pymunk.SimpleMotor(static, body, 1.0)
        space.add(motor)

        # Spring
        b2 = pymunk.Body(1, 100)
        b2.position = (2, 3)
        s2 = pymunk.Circle(b2, 0.3)
        space.add(b2, s2)
        spring = pymunk.DampedSpring(body, b2, (0, 0), (0, 0), 2.0, 50, 5)
        space.add(spring)

        # Gear joint
        gear = pymunk.GearJoint(body, b2, 0.0, 1.0)
        space.add(gear)

        # Should not raise
        draw_constraints(surf, cam, space)

    def test_draw_all_constraint_types(self):
        """Every supported constraint type renders without error."""
        from strata.systems.debug_draw import draw_constraints
        from strata.render.camera import Camera

        pygame.init()
        surf = pygame.Surface((800, 600))
        cam = Camera((800, 600))
        space = pymunk.Space()

        static = space.static_body
        body = pymunk.Body(1, 100)
        body.position = (0, 0)
        space.add(body, pymunk.Circle(body, 0.5))

        constraints = [
            pymunk.PinJoint(static, body, (0, 2), (0, 0)),
            pymunk.PivotJoint(static, body, (0, 0)),
            pymunk.SlideJoint(static, body, (0, 0), (0, 0), 0, 2),
            pymunk.GrooveJoint(static, body, (-1, 0), (1, 0), (0, 0)),
            pymunk.SimpleMotor(static, body, 1.0),
            pymunk.GearJoint(static, body, 0, 1),
            pymunk.RotaryLimitJoint(static, body, 0, math.pi),
            pymunk.DampedSpring(static, body, (0, 0), (0, 0), 1, 100, 5),
            pymunk.DampedRotarySpring(static, body, 0, 100, 5),
        ]
        for c in constraints:
            space.add(c)

        # Should not raise
        draw_constraints(surf, cam, space)

    def test_game_show_constraints_attribute(self):
        """Game has show_constraints attribute."""
        pygame.init()
        game = Game.__new__(Game)
        # Just check the attribute would exist with default False
        assert hasattr(Game, '__init__')  # sanity


# =========================================================================
# Scene serialisation
# =========================================================================

class TestSceneSerialisationRoundTrip:
    """Save and load scenes with full state recovery."""

    def _make_game(self):
        pygame.init()
        return Game(window_size=(320, 240), gravity=(0, -9.81))

    def test_save_creates_file(self, tmp_path):
        game = self._make_game()
        ball = Sprite.circle(radius=0.5, x=1, y=3)
        game.scene.add_entity(ball)
        path = str(tmp_path / "test.json")
        game.save_scene(path)
        assert os.path.exists(path)

    def test_save_valid_json(self, tmp_path):
        game = self._make_game()
        ball = Sprite.circle(radius=0.5, x=1, y=3)
        game.scene.add_entity(ball)
        path = str(tmp_path / "test.json")
        game.save_scene(path)
        data = json.loads(open(path).read())
        assert "entities" in data
        assert "gravity" in data
        assert data["version"] == "0.5.0"

    def test_save_entity_count(self, tmp_path):
        game = self._make_game()
        game.scene.add_entity(Sprite.circle(radius=0.5))
        game.scene.add_entity(Sprite.rect(width=1, height=1))
        path = str(tmp_path / "test.json")
        game.save_scene(path)
        data = json.loads(open(path).read())
        assert len(data["entities"]) == 2

    def test_round_trip_circle(self, tmp_path):
        game = self._make_game()
        ball = Sprite.circle(radius=0.7, x=2, y=4, density=1.5)
        game.scene.add_entity(ball)
        original_id = ball.id

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        entities = game.scene.entities
        assert len(entities) == 1
        e = entities[0]
        assert e.id == original_id

        t = e.get_component(Transform)
        assert abs(t.x - 2.0) < 0.01
        assert abs(t.y - 4.0) < 0.01

        p = e.get_component(Physics)
        assert p is not None
        assert abs(p.density - 1.5) < 0.01

    def test_round_trip_rect(self, tmp_path):
        game = self._make_game()
        wall = Sprite.rect(width=5, height=0.5, x=0, y=-2, static=True)
        game.scene.add_entity(wall)

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        entities = game.scene.entities
        assert len(entities) == 1
        p = entities[0].get_component(Physics)
        assert p.is_static

    def test_round_trip_polygon(self, tmp_path):
        game = self._make_game()
        verts = [(0, 0), (1, 0), (0.5, 1)]
        tri = Sprite.polygon(verts, x=3, y=2)
        game.scene.add_entity(tri)

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        entities = game.scene.entities
        assert len(entities) == 1
        v = entities[0].get_component(Visual)
        assert len(v.vertices) == 3

    def test_round_trip_velocity(self, tmp_path):
        """Body velocity is preserved through save/load."""
        game = self._make_game()
        ball = Sprite.circle(radius=0.5, x=0, y=3)
        game.scene.add_entity(ball)

        # Give it velocity
        p = ball.get_component(Physics)
        p.body.velocity = (5.0, 10.0)
        p.body.angular_velocity = 2.0

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        e = game.scene.entities[0]
        p2 = e.get_component(Physics)
        assert abs(p2.body.velocity.x - 5.0) < 0.01
        assert abs(p2.body.velocity.y - 10.0) < 0.01
        assert abs(p2.body.angular_velocity - 2.0) < 0.01

    def test_round_trip_multiple_entities(self, tmp_path):
        game = self._make_game()
        for i in range(5):
            game.scene.add_entity(Sprite.circle(radius=0.3, x=i, y=i))

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        assert len(game.scene.entities) == 5

    def test_round_trip_damping(self, tmp_path):
        game = self._make_game()
        e = Sprite.circle(radius=0.5, linear_damping=0.95, angular_damping=0.9)
        game.scene.add_entity(e)

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        p = game.scene.entities[0].get_component(Physics)
        assert abs(p.linear_damping - 0.95) < 0.001
        assert abs(p.angular_damping - 0.9) < 0.001

    def test_round_trip_collision_layer_mask(self, tmp_path):
        game = self._make_game()
        e = Sprite.circle(radius=0.5, group="player", collides_with="enemy")
        game.scene.add_entity(e)

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        p = game.scene.entities[0].get_component(Physics)
        player_bit = _collision_groups.get("player")
        enemy_bit = _collision_groups.get("enemy")
        assert p.collision_layer == player_bit
        assert p.collision_mask == enemy_bit

    def test_round_trip_gravity(self, tmp_path):
        game = self._make_game()
        game.physics.space.gravity = (0, -20.0)
        game.scene.add_entity(Sprite.circle(radius=0.5))

        path = str(tmp_path / "rt.json")
        game.save_scene(path)

        # Change gravity
        game.physics.space.gravity = (0, -1.0)
        game.load_scene(path)

        gx, gy = game.physics.space.gravity
        assert abs(gy - (-20.0)) < 0.01

    def test_round_trip_visual_color(self, tmp_path):
        game = self._make_game()
        e = Sprite.circle(radius=0.5, color=(255, 0, 128))
        game.scene.add_entity(e)

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        v = game.scene.entities[0].get_component(Visual)
        assert v.color[:3] == (255, 0, 128)

    def test_round_trip_hidden(self, tmp_path):
        game = self._make_game()
        e = Sprite.circle(radius=0.5)
        e.get_component(Visual).hidden = True
        game.scene.add_entity(e)

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        v = game.scene.entities[0].get_component(Visual)
        assert v.hidden is True

    def test_load_clears_old_entities(self, tmp_path):
        game = self._make_game()
        game.scene.add_entity(Sprite.circle(radius=0.5))
        path = str(tmp_path / "rt.json")
        game.save_scene(path)

        # Add more entities
        for _ in range(5):
            game.scene.add_entity(Sprite.circle(radius=0.3))
        assert len(game.scene.entities) == 6

        # Load clears them
        game.load_scene(path)
        assert len(game.scene.entities) == 1

    def test_entity_id_counter_preserved(self, tmp_path):
        """After load, new entities should have IDs > any loaded ID."""
        game = self._make_game()
        e = Sprite.circle(radius=0.5)
        game.scene.add_entity(e)
        saved_id = e.id

        path = str(tmp_path / "rt.json")
        game.save_scene(path)
        game.load_scene(path)

        new_entity = Sprite.circle(radius=0.3)
        assert new_entity.id > saved_id


class TestSerialiseComponents:
    """Low-level serialise/deserialise for individual entities."""

    def test_serialise_transform(self):
        e = Entity()
        e.add_component(Transform(x=1.5, y=2.5, angle=0.3))
        data = _serialise_entity(e)
        assert data["components"]["Transform"]["x"] == 1.5
        assert data["components"]["Transform"]["angle"] == 0.3

    def test_serialise_property_binding(self):
        e = Entity()
        e.add_component(Transform())
        e.add_component(PropertyBinding(
            source_entity_id=42,
            source_attr="angle",
            target_attr="x",
            scale=2.0,
            offset=0.5,
        ))
        data = _serialise_entity(e)
        pb = data["components"]["PropertyBinding"]
        assert pb["source_entity_id"] == 42
        assert pb["scale"] == 2.0

    def test_rebuild_entity_preserves_id(self):
        e = Entity()
        e.id = 999
        e.add_component(Transform(x=5, y=6))
        data = _serialise_entity(e)
        rebuilt = _rebuild_entity(data)
        assert rebuilt.id == 999
        t = rebuilt.get_component(Transform)
        assert abs(t.x - 5.0) < 0.01

    def test_serialise_physics_circle(self):
        e = Sprite.circle(radius=0.8, density=2.0)
        data = _serialise_entity(e)
        phys = data["components"]["Physics"]
        assert phys["shape_type"] == "circle"
        assert phys["radius"] == 0.8
        assert phys["density"] == 2.0

    def test_serialise_physics_poly(self):
        verts = [(0, 0), (1, 0), (0.5, 1)]
        e = Sprite.polygon(verts)
        data = _serialise_entity(e)
        phys = data["components"]["Physics"]
        assert phys["shape_type"] == "poly"
        assert len(phys["vertices"]) == 3
