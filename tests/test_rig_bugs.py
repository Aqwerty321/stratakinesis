# tests/test_rig_bugs.py
# Regression tests for rig/constraint lifecycle bugs.
#
# Fix 1:  Constraint leak on rig/entity removal
# Fix 2:  Duplicate add_rig() stacks duplicate constraints
# Fix 3:  Invalid chain dimensions → Chipmunk C assert
# Fix 4:  Zero-length rigs → IndexError
# Fix 5:  HingeMotorRig with non-physics entity → opaque AssertionError
# Fix 6:  JointHandle.enabled semantics broken with max_force
# Fix 7:  GearTrainRig radius validation
# Fix 8a: Soft-body registration not idempotent (crash on re-add)
# Fix 8b: _soft_body_bodies leaks IDs on removal

from __future__ import annotations
import os
import math

import pygame
import pymunk
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from strata.core.loop import Scene, Game
from strata.ecs.entity import Entity
from strata.ecs.components import Physics, Transform
from strata.shapes.factory import Sprite
from strata.systems.physics_system import PhysicsSystem
from strata.systems.soft_body_system import SoftBodySystem
from strata.rigs.base import Rig, JointHandle
from strata.rigs.chain import ChainRig
from strata.rigs.pendulum import PendulumRig
from strata.rigs.rope import RopeRig
from strata.rigs.gear_train import GearTrainRig
from strata.rigs.hinge_motor import HingeMotorRig


# =========================================================================
# Fix 1: Constraint leak on removal
# =========================================================================

class TestConstraintLeakOnRemoval:
    """Removing a rig's entities must also remove their constraints."""

    def _make_scene(self):
        physics = PhysicsSystem(gravity=(0, -9.81))
        scene = Scene()
        scene._physics_system = physics
        scene.add_system(physics)
        return scene, physics

    def test_remove_rig_clears_constraints(self):
        scene, physics = self._make_scene()
        chain = ChainRig(length=5, anchor=(0, 4))
        scene.add_rig(chain)
        assert len(physics.space.constraints) > 0

        scene.remove_rig(chain)
        assert len(physics.space.constraints) == 0
        assert len(physics.space.bodies) == 0

    def test_remove_rig_clears_bodies(self):
        scene, physics = self._make_scene()
        chain = ChainRig(length=3)
        scene.add_rig(chain)
        before = len(physics.space.bodies)
        assert before == 3

        scene.remove_rig(chain)
        assert len(physics.space.bodies) == 0

    def test_add_remove_cycles_no_leak(self):
        """50 add/remove cycles should leave 0 bodies and 0 constraints."""
        scene, physics = self._make_scene()

        for _ in range(50):
            chain = ChainRig(length=5, anchor=(0, 4))
            scene.add_rig(chain)
            scene.remove_rig(chain)

        assert len(physics.space.bodies) == 0
        assert len(physics.space.constraints) == 0

    def test_entity_removal_cleans_constraints(self):
        """Removing an entity directly also cleans constraints on its body."""
        scene, physics = self._make_scene()
        chain = ChainRig(length=3)
        scene.add_rig(chain)
        constraints_before = len(physics.space.constraints)
        assert constraints_before > 0

        # Remove first link — its constraints should be removed too.
        scene.remove_entity(chain.links[0])
        remaining = len(physics.space.constraints)
        assert remaining < constraints_before


# =========================================================================
# Fix 2: Duplicate add_rig() idempotency
# =========================================================================

class TestDuplicateAddRig:
    """Calling add_rig() twice must not stack duplicate constraints."""

    def _make_scene(self):
        physics = PhysicsSystem(gravity=(0, -9.81))
        scene = Scene()
        scene._physics_system = physics
        scene.add_system(physics)
        return scene, physics

    def test_double_add_rig_no_duplicate_constraints(self):
        scene, physics = self._make_scene()
        chain = ChainRig(length=4)
        scene.add_rig(chain)
        count_after_first = len(physics.space.constraints)

        scene.add_rig(chain)  # second call — should be idempotent
        count_after_second = len(physics.space.constraints)
        assert count_after_first == count_after_second

    def test_double_add_motor_rig_single_rate(self):
        scene, physics = self._make_scene()
        wheel = Sprite.circle(radius=0.5, x=0, y=0)
        rig = HingeMotorRig(wheel, anchor=(0, 0), rate=3.0)

        scene.add_rig(rig)
        scene.add_rig(rig)  # idempotent

        # Only one motor constraint should exist.
        motors = [c for c in physics.space.constraints
                  if isinstance(c, pymunk.SimpleMotor)]
        assert len(motors) == 1
        assert abs(motors[0].rate - 3.0) < 0.01

    def test_rig_registered_flag(self):
        chain = ChainRig(length=2)
        assert chain._registered is False
        physics = PhysicsSystem()
        chain._register(physics.space, physics.static_body)
        assert chain._registered is True

    def test_unregister_resets_flag(self):
        chain = ChainRig(length=2)
        physics = PhysicsSystem()
        chain._register(physics.space, physics.static_body)
        chain._unregister(physics.space)
        assert chain._registered is False
        assert len(chain._constraints) == 0


# =========================================================================
# Fix 3: Invalid chain dimensions
# =========================================================================

class TestChainDimensionValidation:
    """Negative/zero link dimensions must raise ValueError, not segfault."""

    def test_negative_link_height(self):
        with pytest.raises(ValueError, match="link_height"):
            ChainRig(link_height=-0.2)

    def test_zero_link_height(self):
        with pytest.raises(ValueError, match="link_height"):
            ChainRig(link_height=0)

    def test_negative_link_width(self):
        with pytest.raises(ValueError, match="link_width"):
            ChainRig(link_width=-0.35)

    def test_zero_link_width(self):
        with pytest.raises(ValueError, match="link_width"):
            ChainRig(link_width=0)

    def test_negative_density(self):
        with pytest.raises(ValueError, match="density"):
            ChainRig(density=-1.0)

    def test_valid_chain_ok(self):
        chain = ChainRig(length=3, link_width=0.3, link_height=0.2)
        assert len(chain.links) == 3


# =========================================================================
# Fix 4: Zero-length rigs
# =========================================================================

class TestZeroLengthRigs:
    """Rigs with length=0 must raise ValueError, not IndexError."""

    def test_pendulum_zero_length(self):
        with pytest.raises(ValueError, match="length >= 1"):
            PendulumRig(length=0)

    def test_chain_zero_length(self):
        with pytest.raises(ValueError, match="length >= 1"):
            ChainRig(length=0)

    def test_rope_zero_length(self):
        with pytest.raises(ValueError, match="length >= 1"):
            RopeRig(length=0)

    def test_pendulum_negative_length(self):
        with pytest.raises(ValueError, match="length >= 1"):
            PendulumRig(length=-1)

    def test_pendulum_negative_radius(self):
        with pytest.raises(ValueError, match="bob_radius"):
            PendulumRig(bob_radius=-0.1)

    def test_rope_negative_radius(self):
        with pytest.raises(ValueError, match="bead_radius"):
            RopeRig(bead_radius=-0.05)


# =========================================================================
# Fix 5: HingeMotorRig with non-physics entity
# =========================================================================

class TestHingeMotorNonPhysics:
    """HingeMotorRig must reject entities without physics."""

    def test_no_physics_raises(self):
        entity = Sprite.circle(radius=0.5, physics=False)
        with pytest.raises(ValueError, match="Physics component"):
            HingeMotorRig(entity, anchor=(0, 0))

    def test_bare_entity_raises(self):
        entity = Entity()
        with pytest.raises(ValueError, match="Physics component"):
            HingeMotorRig(entity)

    def test_valid_entity_ok(self):
        entity = Sprite.circle(radius=0.5)
        rig = HingeMotorRig(entity, anchor=(0, 0), rate=2.0)
        assert rig.motor.rate == 2.0


# =========================================================================
# Fix 6: JointHandle.enabled + max_force semantics
# =========================================================================

class TestJointHandleEnabled:
    """Disabling a JointHandle then setting max_force must NOT re-enable torque."""

    def test_disable_then_set_max_force_stays_disabled(self):
        h = JointHandle()
        # Simulate an attached constraint
        motor = pymunk.SimpleMotor(pymunk.Body(1, 100), pymunk.Body(1, 100), 3.0)
        h._attach(motor)

        h.enabled = False
        assert motor.max_force == 0.0

        h.max_force = 5e6
        # max_force setter must NOT write to the live constraint when disabled
        assert motor.max_force == 0.0
        # But the pending value is stored
        assert h._pending['max_force'] == 5e6

    def test_disable_then_reenable_applies_pending(self):
        h = JointHandle()
        motor = pymunk.SimpleMotor(pymunk.Body(1, 100), pymunk.Body(1, 100), 3.0)
        h._attach(motor)

        h.enabled = False
        h.max_force = 2e6
        h.enabled = True
        assert abs(motor.max_force - 2e6) < 1.0

    def test_enabled_by_default(self):
        h = JointHandle()
        assert h.enabled is True

    def test_disable_before_attach(self):
        h = JointHandle()
        h.enabled = False
        h.max_force = 1e5
        motor = pymunk.SimpleMotor(pymunk.Body(1, 100), pymunk.Body(1, 100), 1.0)
        h._attach(motor)
        # On attach, enabled=False → max_force should be 0
        assert motor.max_force == 0.0


# =========================================================================
# Fix 7: GearTrainRig radius validation
# =========================================================================

class TestGearTrainRadiusValidation:
    """Zero or negative radii must be rejected."""

    def test_zero_radius(self):
        with pytest.raises(ValueError, match="positive"):
            GearTrainRig(radii=[0.0, 0.5])

    def test_negative_radius(self):
        with pytest.raises(ValueError, match="positive"):
            GearTrainRig(radii=[0.5, -0.3])

    def test_empty_radii(self):
        with pytest.raises(ValueError, match="at least one"):
            GearTrainRig(radii=[])

    def test_valid_radii_ok(self):
        rig = GearTrainRig(radii=[0.5, 0.8])
        assert len(rig.gears) == 2


# =========================================================================
# Fix 8: Soft-body idempotency + _soft_body_bodies cleanup
# =========================================================================

class TestSoftBodyIdempotency:
    """Soft-body registration must be idempotent and unregister must clean up."""

    def _make_scene(self):
        physics = PhysicsSystem(gravity=(0, -9.81))
        soft_sys = SoftBodySystem(physics_system=physics)
        scene = Scene()
        scene._physics_system = physics
        scene._soft_body_system = soft_sys
        scene.add_system(physics)
        scene.add_system(soft_sys)
        return scene, physics, soft_sys

    def test_double_add_soft_body_idempotent(self):
        """Re-adding the same soft body must not crash or duplicate nodes."""
        scene, physics, soft_sys = self._make_scene()
        blob = Sprite.soft_circle(radius=0.5, rings=2, segments=6)
        scene.add_entity(blob)
        bodies_after_first = len(physics.space.bodies)

        # Manually try to re-register — should be no-op
        from strata.ecs.components import SoftBody as SB
        soft = blob.get_component(SB)
        soft_sys.register(soft, blob.id)
        assert len(physics.space.bodies) == bodies_after_first

    def test_remove_soft_body_clears_soft_body_bodies(self):
        """Unregistering a soft body must clean up _soft_body_bodies set."""
        scene, physics, soft_sys = self._make_scene()
        blob = Sprite.soft_circle(radius=0.5, rings=2, segments=6)
        scene.add_entity(blob)
        assert len(physics._soft_body_bodies) > 0

        scene.remove_entity(blob)
        assert len(physics._soft_body_bodies) == 0

    def test_add_remove_cycle_no_leak(self):
        """Multiple add/remove cycles should not grow _soft_body_bodies."""
        scene, physics, soft_sys = self._make_scene()

        for _ in range(10):
            blob = Sprite.soft_circle(radius=0.5, rings=2, segments=6)
            scene.add_entity(blob)
            scene.remove_entity(blob)

        assert len(physics._soft_body_bodies) == 0
        assert len(physics.space.bodies) == 0
        assert len(physics.space.constraints) == 0
