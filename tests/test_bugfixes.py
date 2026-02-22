# tests/test_bugfixes.py
# Regression tests for P0/P1 bugfixes.
#
# Covers:
#   - Entity/rig idempotency (P0)
#   - Input-event loss prevention (P0)
#   - Rigid-body unregister/removal lifecycle (P0)
#   - No sys.exit from Game.run() (P1)
#   - Stable query/render iteration order (P1)
#   - Soft-body damping under adaptive CCD substeps (P1)
#   - Polygon damping API consistency (P1)

import math
import os
import time

import pytest
import pymunk

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()

from strata.config import FIXED_DT
from strata.core.input_buffer import InputBuffer, StampedEvent
from strata.ecs.entity import Entity
from strata.ecs.components import Transform, Physics, Visual, SoftBody
from strata.ecs.world import World
from strata.shapes.factory import Sprite


def make_game(**kwargs):
    from strata.core.loop import Game
    return Game(window_size=(800, 600), **kwargs)


# =========================================================================
# P0: Entity / rig idempotency
# =========================================================================

class TestEntityIdempotency:
    def test_add_entity_twice_no_duplicate(self):
        """Adding the same entity twice should not duplicate it in the entity list."""
        world = World()
        e = Entity()
        e.add_component(Transform())
        world.add_entity(e)
        world.add_entity(e)
        assert world.entities.count(e) == 1

    def test_add_entity_idempotent_returns_entity(self):
        """add_entity on an existing entity should return the same entity."""
        world = World()
        e = Entity()
        result1 = world.add_entity(e)
        result2 = world.add_entity(e)
        assert result1 is e
        assert result2 is e

    def test_add_entities_idempotent(self):
        """add_entities with repeated entities should not duplicate."""
        world = World()
        e = Entity()
        e.add_component(Transform())
        world.add_entities(e, e, e)
        assert world.entities.count(e) == 1

    def test_scene_add_entity_no_physics_duplicate(self):
        """Re-adding an entity to a Scene must not duplicate physics registration."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        game.scene.add_entity(ball)
        initial_body_count = len(game.physics.space.bodies)
        initial_shape_count = len(game.physics.space.shapes)

        # Re-add the same entity
        game.scene.add_entity(ball)
        assert len(game.physics.space.bodies) == initial_body_count
        assert len(game.physics.space.shapes) == initial_shape_count

    def test_scene_add_entity_no_tracking_list_duplicate(self):
        """Re-adding should not create duplicate entries in _sync_pairs."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0, linear_damping=0.99)
        game.scene.add_entity(ball)
        sync_count = len(game.physics._sync_pairs)
        damped_count = len(game.physics._damped_bodies)

        game.scene.add_entity(ball)
        assert len(game.physics._sync_pairs) == sync_count
        assert len(game.physics._damped_bodies) == damped_count

    def test_add_rig_idempotent_entities(self):
        """add_rig should not duplicate entities already in the scene."""
        from strata.rigs import HingeMotorRig
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0)
        game.scene.add_entity(wheel)
        entity_count = len(game.scene.entities)
        body_count = len(game.physics.space.bodies)

        rig = HingeMotorRig(wheel, anchor=(0.0, 0.0), rate=5.0)
        game.scene.add_rig(rig)

        # Entities should not be duplicated
        assert game.scene.entities.count(wheel) == 1
        # Original body stays, but no extra bodies from re-registration
        assert len(game.scene.entities) == entity_count

    def test_component_index_consistent_after_re_add(self):
        """Component index must not have duplicates after re-adding an entity."""
        world = World()
        e = Entity()
        e.add_component(Transform())
        world.add_entity(e)
        world.add_entity(e)  # idempotent

        result = world.get_entities_with(Transform)
        assert result.count(e) == 1


# =========================================================================
# P0: Input-event loss prevention
# =========================================================================

class TestInputEventLoss:
    def _buf_with_events(self, timestamps):
        buf = InputBuffer()
        for t in timestamps:
            ev = pygame.event.Event(pygame.USEREVENT)
            buf._pending.append(StampedEvent(event=ev, timestamp=t))
        return buf

    def test_expire_keeps_future_events(self):
        """expire() must keep events timestamped >= the given time."""
        buf = self._buf_with_events([1.0, 2.0, 3.0])
        buf.expire(2.0)
        assert len(buf) == 2  # 2.0 and 3.0 remain

    def test_expire_removes_old_events(self):
        """expire() must remove events strictly before the given time."""
        buf = self._buf_with_events([1.0, 1.5, 2.0])
        buf.expire(1.5)
        assert len(buf) == 2  # 1.5 and 2.0 remain

    def test_expire_empty_buffer(self):
        """expire() on an empty buffer is a no-op."""
        buf = InputBuffer()
        buf.expire(5.0)
        assert len(buf) == 0

    def test_events_survive_no_physics_step_frame(self):
        """Events must not be lost when a frame has 0 physics steps."""
        buf = self._buf_with_events([10.0, 10.01])
        # Simulate: sim_time=10.0, no physics step happened
        buf.expire(10.0)
        # Both events are >= 10.0, so both survive
        assert len(buf) == 2

    def test_events_available_for_next_frame(self):
        """Events kept by expire() must be consumable in the next frame."""
        buf = self._buf_with_events([1.0, 2.0, 3.0])
        # First frame consumed [0, 1.5)
        consumed = buf.consume(0.0, 1.5)
        assert len(consumed) == 1
        # Expire anything before sim_time=1.5
        buf.expire(1.5)
        # Now consume [1.5, 3.0)
        consumed2 = buf.consume(1.5, 3.0)
        assert len(consumed2) == 1  # 2.0
        # 3.0 remains
        assert len(buf) == 1

    def test_clear_still_works(self):
        """clear() must still drop everything (backward compat)."""
        buf = self._buf_with_events([1.0, 2.0])
        buf.clear()
        assert len(buf) == 0


# =========================================================================
# P0: Rigid-body unregister / removal lifecycle
# =========================================================================

class TestRigidBodyRemoval:
    def test_remove_entity_removes_body_from_space(self):
        """Removing a dynamic entity must remove its body from pymunk.Space."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        game.scene.add_entity(ball)
        assert len(game.physics.space.bodies) >= 1

        game.scene.remove_entity(ball)
        phys = ball.get_component(Physics)
        assert phys.body not in game.physics.space.bodies

    def test_remove_entity_removes_shape_from_space(self):
        """Removing an entity must remove its shape from pymunk.Space."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        game.scene.add_entity(ball)
        phys = ball.get_component(Physics)
        assert phys.shape in game.physics.space.shapes

        game.scene.remove_entity(ball)
        assert phys.shape not in game.physics.space.shapes

    def test_remove_entity_cleans_shape_to_entity_map(self):
        """Shape-to-entity mapping must be removed on entity removal."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        game.scene.add_entity(ball)
        phys = ball.get_component(Physics)
        assert phys.shape in game.physics._shape_to_entity

        game.scene.remove_entity(ball)
        assert phys.shape not in game.physics._shape_to_entity

    def test_remove_entity_cleans_sync_pairs(self):
        """_sync_pairs must not reference removed entity's body."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        game.scene.add_entity(ball)
        phys = ball.get_component(Physics)
        bodies_in_sync = [b for b, t in game.physics._sync_pairs]
        assert phys.body in bodies_in_sync

        game.scene.remove_entity(ball)
        bodies_in_sync = [b for b, t in game.physics._sync_pairs]
        assert phys.body not in bodies_in_sync

    def test_remove_entity_cleans_damped_bodies(self):
        """_damped_bodies must not reference removed entity."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0, linear_damping=0.99)
        game.scene.add_entity(ball)
        phys = ball.get_component(Physics)
        damped = [b for b, _, _ in game.physics._damped_bodies]
        assert phys.body in damped

        game.scene.remove_entity(ball)
        damped = [b for b, _, _ in game.physics._damped_bodies]
        assert phys.body not in damped

    def test_remove_entity_cleans_ccd_tracking(self):
        """CCD tracking lists must not reference removed entity."""
        game = make_game(physics_ccd=True)
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        game.scene.add_entity(ball)
        phys = ball.get_component(Physics)
        assert phys.body in game.physics._ccd_bodies

        game.scene.remove_entity(ball)
        assert phys.body not in game.physics._ccd_bodies

    def test_remove_entity_removes_from_registered_set(self):
        """_registered_entities set must not contain removed entity's ID."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        game.scene.add_entity(ball)
        assert ball.id in game.physics._registered_entities

        game.scene.remove_entity(ball)
        assert ball.id not in game.physics._registered_entities

    def test_remove_static_entity(self):
        """Removing a static entity must remove its shape."""
        game = make_game()
        ground = Sprite.rect(width=10.0, height=0.5, y=-4.0, static=True)
        game.scene.add_entity(ground)
        phys = ground.get_component(Physics)
        assert phys.shape in game.physics.space.shapes

        game.scene.remove_entity(ground)
        assert phys.shape not in game.physics.space.shapes

    def test_remove_entity_not_in_scene_is_noop(self):
        """Removing an entity not in the scene must not raise."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        # Never added — should be safe
        game.scene.remove_entity(ball)  # must not raise

    def test_simulation_continues_after_removal(self):
        """Physics must continue to work correctly after removing entities."""
        game = make_game()
        ball1 = Sprite.circle(radius=0.5, x=-2.0, y=5.0)
        ball2 = Sprite.circle(radius=0.5, x=2.0, y=5.0)
        ground = Sprite.rect(width=20.0, height=0.5, y=-4.0, static=True)
        game.scene.add_entities(ball1, ball2, ground)

        # Remove ball1
        game.scene.remove_entity(ball1)

        # Simulation should still work — ball2 falls
        initial_y = ball2.get_component(Transform).y
        for _ in range(30):
            game.step(FIXED_DT)
        assert ball2.get_component(Transform).y < initial_y

    def test_re_add_after_remove(self):
        """An entity can be removed and re-added cleanly."""
        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        game.scene.add_entity(ball)
        game.scene.remove_entity(ball)
        # Re-add
        game.scene.add_entity(ball)
        assert ball in game.scene.entities
        phys = ball.get_component(Physics)
        assert phys.body in game.physics.space.bodies


# =========================================================================
# P1: No sys.exit from Game.run()
# =========================================================================

class TestNoSysExit:
    def test_game_does_not_import_sys(self):
        """loop.py should not import sys (no hard exit)."""
        import strata.core.loop as loop_mod
        source = open(loop_mod.__file__).read()
        # Should not have 'import sys' as a standalone import
        import re
        assert not re.search(r'^import sys\b', source, re.MULTILINE)


# =========================================================================
# P1: Stable query / render iteration order
# =========================================================================

class TestStableQueryOrder:
    def test_get_entities_with_returns_sorted_by_id(self):
        """Query results must be sorted by entity ID for determinism."""
        world = World()
        entities = []
        for _ in range(20):
            e = Entity()
            e.add_component(Transform())
            e.add_component(Visual())
            world.add_entity(e)
            entities.append(e)

        result = world.get_entities_with(Transform, Visual)
        ids = [e.id for e in result]
        assert ids == sorted(ids)

    def test_query_order_stable_across_calls(self):
        """Multiple calls to the same query must return the same order."""
        world = World()
        for _ in range(10):
            e = Entity()
            e.add_component(Transform())
            world.add_entity(e)

        r1 = world.get_entities_with(Transform)
        r2 = world.get_entities_with(Transform)
        assert [e.id for e in r1] == [e.id for e in r2]

    def test_query_order_after_remove(self):
        """Removing an entity in the middle still produces sorted order."""
        world = World()
        entities = []
        for _ in range(5):
            e = Entity()
            e.add_component(Transform())
            world.add_entity(e)
            entities.append(e)

        # Remove the middle entity
        world.remove_entity(entities[2])
        result = world.get_entities_with(Transform)
        ids = [e.id for e in result]
        assert ids == sorted(ids)
        assert entities[2] not in result


# =========================================================================
# P1: Soft-body damping under adaptive CCD substeps
# =========================================================================

class TestSoftBodyDampingCCD:
    def test_vel_damp_recomputed_on_substep_change(self):
        """_vel_damp must update when physics substep count changes."""
        game = make_game(physics_ccd=True)
        blob = Sprite.soft_rect(cols=3, rows=3, width=1.0, height=1.0,
                                x=0.0, y=3.0, velocity_damping=0.99)
        game.scene.add_entity(blob)

        soft = blob.get_component(SoftBody)
        initial_damp = soft._vel_damp

        # Manually change substeps to simulate CCD adaptation
        old_substeps = game.physics.substeps
        game.physics.substeps = old_substeps * 4
        game.soft_body._last_substeps = old_substeps  # force recompute

        # Trigger post-substep hook
        game.soft_body._post_substep_com_correct(FIXED_DT / (old_substeps * 4))

        new_damp = soft._vel_damp
        assert new_damp != pytest.approx(initial_damp, abs=1e-10)
        expected = 0.99 ** (1.0 / (old_substeps * 4))
        assert new_damp == pytest.approx(expected, rel=1e-6)

    def test_vel_damp_not_recomputed_when_unchanged(self):
        """_vel_damp should stay the same when substep count doesn't change."""
        game = make_game(physics_ccd=True)
        blob = Sprite.soft_rect(cols=3, rows=3, width=1.0, height=1.0,
                                x=0.0, y=3.0, velocity_damping=0.99)
        game.scene.add_entity(blob)

        soft = blob.get_component(SoftBody)
        initial_damp = soft._vel_damp

        # Run a step — substep count should remain the same (no fast bodies)
        game.step(FIXED_DT)
        assert soft._vel_damp == pytest.approx(initial_damp, rel=1e-10)


# =========================================================================
# P1: Polygon damping API consistency
# =========================================================================

class TestPolygonDamping:
    def test_polygon_accepts_linear_damping(self):
        """Sprite.polygon must accept linear_damping parameter."""
        verts = [(0, 0), (1, 0), (0.5, 1)]
        entity = Sprite.polygon(verts, linear_damping=0.95)
        phys = entity.get_component(Physics)
        assert phys.linear_damping == pytest.approx(0.95)

    def test_polygon_accepts_angular_damping(self):
        """Sprite.polygon must accept angular_damping parameter."""
        verts = [(0, 0), (1, 0), (0.5, 1)]
        entity = Sprite.polygon(verts, angular_damping=0.90)
        phys = entity.get_component(Physics)
        assert phys.angular_damping == pytest.approx(0.90)

    def test_polygon_damping_defaults_to_one(self):
        """Sprite.polygon with no damping args should default to 1.0."""
        verts = [(0, 0), (1, 0), (0.5, 1)]
        entity = Sprite.polygon(verts)
        phys = entity.get_component(Physics)
        assert phys.linear_damping == pytest.approx(1.0)
        assert phys.angular_damping == pytest.approx(1.0)

    def test_polygon_damping_applied_in_simulation(self):
        """A polygon with damping should decelerate faster than one without."""
        game = make_game()
        verts = [(0, 0), (1, 0), (0.5, 0.8)]

        # Damped polygon
        damped = Sprite.polygon(verts, x=-2.0, y=5.0, linear_damping=0.9)
        # Undamped polygon
        undamped = Sprite.polygon(verts, x=2.0, y=5.0, linear_damping=1.0)
        game.scene.add_entities(damped, undamped)

        # Give both a horizontal kick
        damped.get_component(Physics).body.velocity = (10, 0)
        undamped.get_component(Physics).body.velocity = (10, 0)

        for _ in range(60):
            game.step(FIXED_DT)

        # Damped should be slower
        damped_vx = abs(damped.get_component(Physics).body.velocity.x)
        undamped_vx = abs(undamped.get_component(Physics).body.velocity.x)
        assert damped_vx < undamped_vx

    def test_polygon_api_matches_circle_and_rect(self):
        """polygon, circle, and rect should all accept the same damping params."""
        import inspect
        circle_sig = inspect.signature(Sprite.circle)
        rect_sig = inspect.signature(Sprite.rect)
        poly_sig = inspect.signature(Sprite.polygon)

        for param_name in ('linear_damping', 'angular_damping'):
            assert param_name in circle_sig.parameters
            assert param_name in rect_sig.parameters
            assert param_name in poly_sig.parameters


# =========================================================================
# P0: World.remove_entity safety
# =========================================================================

class TestWorldRemoveEntitySafety:
    def test_remove_nonexistent_entity_does_not_raise(self):
        """Removing an entity not in the world must not raise."""
        world = World()
        e = Entity()
        world.remove_entity(e)  # no-op, no exception

    def test_remove_twice_does_not_raise(self):
        """Removing the same entity twice must not raise."""
        world = World()
        e = Entity()
        world.add_entity(e)
        world.remove_entity(e)
        world.remove_entity(e)  # second removal is safe
