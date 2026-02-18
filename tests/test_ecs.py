# tests/test_ecs.py
# Tests for the Entity-Component-System layer.

import pytest
from strata.ecs.entity import Entity
from strata.ecs.components import Transform, Visual, Physics
from strata.ecs.world import World


class TestEntity:
    def test_entity_has_unique_ids(self):
        e1 = Entity()
        e2 = Entity()
        assert e1.id != e2.id

    def test_ids_are_positive_integers(self):
        e = Entity()
        assert isinstance(e.id, int)
        assert e.id > 0

    def test_add_and_get_component(self):
        e = Entity()
        t = Transform(x=1.0, y=2.0)
        e.add_component(t)
        assert e.get_component(Transform) is t

    def test_has_component_returns_true(self):
        e = Entity()
        e.add_component(Transform())
        assert e.has_component(Transform)

    def test_has_component_returns_false_for_absent(self):
        e = Entity()
        assert not e.has_component(Transform)

    def test_remove_component(self):
        e = Entity()
        e.add_component(Transform())
        e.remove_component(Transform)
        assert not e.has_component(Transform)

    def test_remove_absent_component_is_noop(self):
        e = Entity()
        e.remove_component(Transform)  # must not raise

    def test_replace_component(self):
        e = Entity()
        e.add_component(Transform(x=1.0))
        e.add_component(Transform(x=9.0))  # replace
        assert e.get_component(Transform).x == pytest.approx(9.0)

    def test_get_absent_component_returns_none(self):
        e = Entity()
        assert e.get_component(Transform) is None


class TestWorld:
    def test_add_and_get_entity(self):
        world = World()
        e = Entity()
        e.add_component(Transform())
        world.add_entity(e)
        assert e in world.entities

    def test_add_entities_bulk(self):
        world = World()
        e1, e2 = Entity(), Entity()
        world.add_entities(e1, e2)
        assert e1 in world.entities
        assert e2 in world.entities

    def test_get_entities_with_single_component(self):
        world = World()
        e1 = Entity()
        e1.add_component(Transform())
        e2 = Entity()  # no Transform
        world.add_entities(e1, e2)
        result = world.get_entities_with(Transform)
        assert e1 in result
        assert e2 not in result

    def test_get_entities_with_multiple_components(self):
        world = World()
        e1 = Entity()
        e1.add_component(Transform())
        e1.add_component(Visual())
        e2 = Entity()
        e2.add_component(Transform())
        world.add_entities(e1, e2)
        result = world.get_entities_with(Transform, Visual)
        assert e1 in result
        assert e2 not in result

    def test_remove_entity(self):
        world = World()
        e = Entity()
        world.add_entity(e)
        world.remove_entity(e)
        assert e not in world.entities
