# strata — Deterministic, rigging-first 2D engine core.
# Public surface: Game, Sprite, Mesh, InputBuffer, StampedEvent,
#                 CollisionEvent, CollisionGroups, SoftBody, and all Rig types.
from strata.core.loop import Game
from strata.shapes.factory import Sprite
from strata.shapes.mesh import Mesh
from strata.core.input_buffer import InputBuffer, StampedEvent
from strata.core.collision_groups import CollisionGroups
from strata.systems.physics_system import CollisionEvent
from strata.ecs.components import SoftBody
from strata.rigs import (
    Rig, JointHandle,
    HingeMotorRig, ChainRig, RopeRig,
    GearTrainRig, LeverRig, PendulumRig,
)

__all__ = [
    "Game", "Sprite", "Mesh",
    "InputBuffer", "StampedEvent", "CollisionEvent",
    "CollisionGroups",
    "SoftBody",
    "Rig", "JointHandle",
    "HingeMotorRig", "ChainRig", "RopeRig",
    "GearTrainRig", "LeverRig", "PendulumRig",
]
__version__ = "0.5.0"
