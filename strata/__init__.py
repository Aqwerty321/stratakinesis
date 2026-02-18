# strata — Deterministic, rigging-first 2D engine core.
# Public surface: Game, Sprite, InputBuffer, StampedEvent, CollisionEvent
from strata.core.loop import Game
from strata.shapes.factory import Sprite
from strata.core.input_buffer import InputBuffer, StampedEvent
from strata.systems.physics_system import CollisionEvent

__all__ = ["Game", "Sprite", "InputBuffer", "StampedEvent", "CollisionEvent"]
__version__ = "0.2.0"
