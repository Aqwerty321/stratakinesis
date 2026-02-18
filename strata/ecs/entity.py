# strata/ecs/entity.py
# Entity is just an integer ID plus a flat dict of components.
# No class hierarchy — explicit and simple.

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from strata.ecs.components import Component


class Entity:
    """A game object: an integer ID and a mapping of component type → component instance."""

    _id_counter: int = 0

    def __init__(self) -> None:
        Entity._id_counter += 1
        self.id: int = Entity._id_counter
        self.components: dict[type, "Component"] = {}

    # ------------------------------------------------------------------
    # Component helpers
    # ------------------------------------------------------------------

    def add_component(self, component: "Component") -> None:
        """Attach a component. Replaces any existing component of the same type."""
        self.components[type(component)] = component

    def get_component(self, component_type: type) -> "Component | None":
        """Return the component of the given type, or None if absent."""
        return self.components.get(component_type)

    def has_component(self, component_type: type) -> bool:
        """Return True if this entity carries a component of the given type."""
        return component_type in self.components

    def remove_component(self, component_type: type) -> None:
        """Remove the component of the given type (no-op if absent)."""
        self.components.pop(component_type, None)

    def __repr__(self) -> str:
        comp_names = [t.__name__ for t in self.components]
        return f"Entity(id={self.id}, components={comp_names})"
