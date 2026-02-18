# strata/ecs/world.py
# Scene / World: entity registry + ordered systems pipeline.

from __future__ import annotations
from typing import TYPE_CHECKING

from strata.ecs.entity import Entity

if TYPE_CHECKING:
    from strata.systems.base import System


class World:
    """Holds all entities and drives the ordered systems pipeline each tick."""

    def __init__(self) -> None:
        self._entities: list[Entity] = []
        self._systems: list["System"] = []       # ordered by priority (ascending)

    # ------------------------------------------------------------------
    # Entity management
    # ------------------------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        """Register an entity and return it (for chaining)."""
        self._entities.append(entity)
        return entity

    def add_entities(self, *entities: Entity) -> None:
        """Register multiple entities at once."""
        for entity in entities:
            self._entities.append(entity)

    def remove_entity(self, entity: Entity) -> None:
        """Deregister an entity (does not clean up physics bodies — caller's responsibility)."""
        self._entities.remove(entity)

    def get_entity_by_id(self, entity_id: int) -> "Entity | None":
        """Return the entity with the given id, or None if not found."""
        for entity in self._entities:
            if entity.id == entity_id:
                return entity
        return None

    def get_entities_with(self, *component_types: type) -> list[Entity]:
        """Return all entities that carry every listed component type."""
        result = []
        for entity in self._entities:
            if all(entity.has_component(ct) for ct in component_types):
                result.append(entity)
        return result

    @property
    def entities(self) -> list[Entity]:
        return list(self._entities)

    # ------------------------------------------------------------------
    # System management
    # ------------------------------------------------------------------

    def add_system(self, system: "System") -> None:
        """Register a system.  Systems are called in insertion order each tick."""
        self._systems.append(system)

    # ------------------------------------------------------------------
    # Update / draw
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        """Call update(dt) on every system in order (physics tick)."""
        for system in self._systems:
            system.update(self, dt)

    def draw(self, surface, camera, alpha: float = 1.0) -> None:  # type: ignore[type-arg]
        """Call draw() on every system that supports it, passing interpolation alpha."""
        for system in self._systems:
            if hasattr(system, "draw"):
                system.draw(self, surface, camera, alpha)
