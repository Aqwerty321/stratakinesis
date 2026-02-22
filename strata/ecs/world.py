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
        # Fast id → entity lookup (O(1) instead of O(N) linear scan).
        self._entity_by_id: dict[int, Entity] = {}
        # Inverted index: component_type → set of entity ids that carry it.
        # Kept in sync by _index_entity / _unindex_entity.
        self._component_index: dict[type, set[int]] = {}
        self._systems: list["System"] = []       # ordered by priority (ascending)
        # P-OPT-15: Pre-filtered list of systems with draw methods.
        self._draw_systems: list["System"] = []
        # P-OPT-14: Query result cache with per-component-type versioning.
        # Only invalidate queries that involve the component types of the
        # added/removed entity, not the entire cache.
        self._query_cache: dict[tuple[type, ...], list[Entity]] = {}
        # Version counter per component type — incremented on add/remove.
        self._comp_version: dict[type, int] = {}
        # Snapshot of versions when each cache entry was created.
        self._query_versions: dict[tuple[type, ...], tuple[int, ...]] = {}

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------

    def _index_entity(self, entity: Entity) -> None:
        """Insert entity into the id map and component index."""
        self._entity_by_id[entity.id] = entity
        for ct in entity.components:
            try:
                self._component_index[ct].add(entity.id)
            except KeyError:
                self._component_index[ct] = {entity.id}
            # P-OPT-14: Bump version for affected component types only.
            self._comp_version[ct] = self._comp_version.get(ct, 0) + 1

    def _unindex_entity(self, entity: Entity) -> None:
        """Remove entity from the id map and component index."""
        self._entity_by_id.pop(entity.id, None)
        for ct in entity.components:
            s = self._component_index.get(ct)
            if s:
                s.discard(entity.id)
            # P-OPT-14: Bump version for affected component types only.
            self._comp_version[ct] = self._comp_version.get(ct, 0) + 1

    # ------------------------------------------------------------------
    # Entity management
    # ------------------------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        """Register an entity and return it (for chaining).

        Idempotent: if the entity is already registered, this is a no-op.
        """
        if entity.id in self._entity_by_id:
            return entity
        self._entities.append(entity)
        self._index_entity(entity)
        return entity

    def add_entities(self, *entities: Entity) -> None:
        """Register multiple entities at once (idempotent per entity)."""
        for entity in entities:
            if entity.id in self._entity_by_id:
                continue
            self._entities.append(entity)
            self._index_entity(entity)

    def remove_entity(self, entity: Entity) -> None:
        """Deregister an entity.  Subclasses (Scene) handle physics cleanup."""
        try:
            self._entities.remove(entity)
        except ValueError:
            return
        self._unindex_entity(entity)

    def get_entity_by_id(self, entity_id: int) -> "Entity | None":
        """Return the entity with the given id, or None if not found.  O(1)."""
        return self._entity_by_id.get(entity_id)

    def get_entities_with(self, *component_types: type) -> list[Entity]:
        """Return all entities that carry every listed component type.

        Uses the inverted component index — O(|result|) rather than O(N)
        when the requested component types are not carried by every entity.
        Results are cached per component-type tuple and invalidated on
        entity add/remove (P1-7).
        """
        if not component_types:
            return list(self._entities)
        # P-OPT-14: Check version freshness instead of clearing entire cache.
        cached = self._query_cache.get(component_types)
        if cached is not None:
            saved_versions = self._query_versions.get(component_types)
            if saved_versions is not None:
                current_versions = tuple(
                    self._comp_version.get(ct, 0) for ct in component_types
                )
                if saved_versions == current_versions:
                    return cached
        # Collect the id-sets for each requested type, fall back to empty set
        # for unknown types.  Sort by size so the intersection starts small.
        sets = sorted(
            [self._component_index.get(ct, set()) for ct in component_types],
            key=len,
        )
        # Fast-path: if any set is empty, no entity qualifies.
        if not sets[0]:
            result: list[Entity] = []
        else:
            common: set[int] = sets[0].copy()
            for s in sets[1:]:
                common &= s
                if not common:
                    result = []
                    break
            else:
                byid = self._entity_by_id
                result = sorted(
                    [byid[eid] for eid in common if eid in byid],
                    key=lambda e: e.id,
                )
        self._query_cache[component_types] = result
        # P-OPT-14: Store current versions for freshness check.
        self._query_versions[component_types] = tuple(
            self._comp_version.get(ct, 0) for ct in component_types
        )
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
        # P-OPT-15: Rebuild draw_systems list to avoid hasattr() per frame.
        self._draw_systems = [s for s in self._systems if hasattr(s, "draw")]

    # ------------------------------------------------------------------
    # Update / draw
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        """Call update(dt) on every system in order (physics tick)."""
        for system in self._systems:
            system.update(self, dt)

    def draw(self, surface, camera, alpha: float = 1.0) -> None:  # type: ignore[type-arg]
        """Call draw() on every system that supports it, passing interpolation alpha.

        P-OPT-15: Iterates pre-built _draw_systems list — no hasattr() per frame.
        """
        for system in self._draw_systems:
            system.draw(self, surface, camera, alpha)
