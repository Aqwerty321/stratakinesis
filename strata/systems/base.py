# strata/systems/base.py
# Abstract base class for all systems.

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from strata.ecs.world import World


class System(ABC):
    """All systems inherit from this.  Only update() is mandatory."""

    @abstractmethod
    def update(self, world: "World", dt: float) -> None:
        """Called once per fixed physics step."""
        ...
