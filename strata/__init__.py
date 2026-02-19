# strata — Deterministic, rigging-first 2D engine core.
# Public surface: Game, Sprite, InputBuffer, StampedEvent, CollisionEvent,
#                 SoftBody, and all Rig types.
from strata.core.loop import Game
from strata.shapes.factory import Sprite
from strata.core.input_buffer import InputBuffer, StampedEvent
from strata.systems.physics_system import CollisionEvent
from strata.ecs.components import SoftBody
from strata.rigs import (
    Rig, JointHandle,
    HingeMotorRig, ChainRig, RopeRig,
    GearTrainRig, LeverRig, PendulumRig,
)

__all__ = [
    "Game", "Sprite", "InputBuffer", "StampedEvent", "CollisionEvent",
    "SoftBody",
    "Rig", "JointHandle",
    "HingeMotorRig", "ChainRig", "RopeRig",
    "GearTrainRig", "LeverRig", "PendulumRig",
]
__version__ = "0.4.0"
