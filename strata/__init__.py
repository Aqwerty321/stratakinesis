# strata — Deterministic, rigging-first 2D engine core.
# Public surface: Game, Sprite, InputBuffer, StampedEvent, CollisionEvent
from strata.core.loop import Game
from strata.shapes.factory import Sprite
from strata.core.input_buffer import InputBuffer, StampedEvent
from strata.systems.physics_system import CollisionEvent
from strata.ecs.components import SoftBody

__all__ = ["Game", "Sprite", "InputBuffer", "StampedEvent", "CollisionEvent", "SoftBody"]
__version__ = "0.3.0"
