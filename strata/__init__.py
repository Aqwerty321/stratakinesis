# strata — Deterministic, rigging-first 2D engine core.
# Public surface: Game, Sprite, InputBuffer, StampedEvent
from strata.core.loop import Game
from strata.shapes.factory import Sprite
from strata.core.input_buffer import InputBuffer, StampedEvent

__all__ = ["Game", "Sprite", "InputBuffer", "StampedEvent"]
__version__ = "0.1.0"
