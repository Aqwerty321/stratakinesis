# tests/test_rig_system.py
# Tests for Rig v1: HingeMotorRig and PropertyBinding mirroring.
# (MotorRig component and RigSystem have been replaced by the Rig assembly system.)

import math
import os

import pytest
import pymunk

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from strata.config import FIXED_DT
from strata.ecs.components import PropertyBinding, Physics, Transform
from strata.shapes.factory import Sprite
from strata.rigs import HingeMotorRig


def make_game():
    from strata.core.loop import Game
    return Game(window_size=(800, 600))


class TestHingeMotorRig:
    def test_motor_constraint_added_on_add_rig(self):
        """After add_rig, a SimpleMotor must be present in the pymunk Space."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0)
        game.scene.add_entity(wheel)
        rig = HingeMotorRig(wheel, anchor=(0.0, 0.0), rate=5.0)
        game.scene.add_rig(rig)

        motors = [c for c in game.physics.space.constraints
                  if isinstance(c, pymunk.SimpleMotor)]
        assert len(motors) == 1

    def test_motor_handle_rate_before_registration(self):
        """JointHandle.rate reads back the pending value before add_rig."""
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0)
        rig = HingeMotorRig(wheel, anchor=(0.0, 0.0), rate=7.0)
        assert rig.motor.rate == pytest.approx(7.0)

    def test_motor_handle_rate_after_registration(self):
        """JointHandle.rate reads from the live constraint after add_rig."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0)
        game.scene.add_entity(wheel)
        rig = HingeMotorRig(wheel, anchor=(0.0, 0.0), rate=7.0)
        game.scene.add_rig(rig)

        assert rig.motor.rate == pytest.approx(7.0)

    def test_motor_rate_update_propagates_to_constraint(self):
        """Setting rig.motor.rate must immediately update the pymunk constraint."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0)
        game.scene.add_entity(wheel)
        rig = HingeMotorRig(wheel, anchor=(0.0, 0.0), rate=3.0)
        game.scene.add_rig(rig)

        rig.motor.rate = -6.0
        game.step(FIXED_DT)

        motors = [c for c in game.physics.space.constraints
                  if isinstance(c, pymunk.SimpleMotor)]
        assert motors[0].rate == pytest.approx(-6.0)

    def test_motor_not_duplicated_on_multiple_steps(self):
        """Stepping multiple times must not add duplicate motor constraints."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0)
        game.scene.add_entity(wheel)
        rig = HingeMotorRig(wheel, anchor=(0.0, 0.0), rate=2.0)
        game.scene.add_rig(rig)

        for _ in range(10):
            game.step(FIXED_DT)

        motors = [c for c in game.physics.space.constraints
                  if isinstance(c, pymunk.SimpleMotor)]
        assert len(motors) == 1

    def test_motor_drives_rotation(self):
        """A wheel driven by HingeMotorRig should accumulate angular velocity."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=5.0)
        game.scene.add_entity(wheel)
        rig = HingeMotorRig(wheel, anchor=(0.0, 5.0),
                            rate=10.0, max_force=1e9)
        game.scene.add_rig(rig)

        for _ in range(30):
            game.step(FIXED_DT)

        phys: Physics = wheel.get_component(Physics)
        assert abs(phys.body.angular_velocity) > 0.1

    def test_pivot_and_motor_both_added(self):
        """HingeMotorRig must add both a PivotJoint and a SimpleMotor."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0)
        game.scene.add_entity(wheel)
        rig = HingeMotorRig(wheel, anchor=(0.0, 0.0), rate=1.0)
        game.scene.add_rig(rig)

        pivots = [c for c in game.physics.space.constraints
                  if isinstance(c, pymunk.PivotJoint)]
        motors = [c for c in game.physics.space.constraints
                  if isinstance(c, pymunk.SimpleMotor)]
        assert len(pivots) >= 1
        assert len(motors) >= 1


class TestPropertyBinding:
    def _make_driven_wheel(self, game):
        """Helper: wheel driven by HingeMotorRig."""
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0)
        game.scene.add_entity(wheel)
        rig = HingeMotorRig(wheel, anchor=(0.0, 0.0),
                            rate=5.0, max_force=1e9)
        game.scene.add_rig(rig)
        return wheel

    def test_binding_mirrors_source_angle(self):
        """Follower Transform.angle must match wheel Transform.angle after steps."""
        game = make_game()
        wheel = self._make_driven_wheel(game)

        follower = Sprite.circle(radius=0.3, x=3.0, y=0.0, physics=False)
        follower.add_component(
            PropertyBinding(
                source_entity_id=wheel.id,
                source_attr="angle",
                target_attr="angle",
            )
        )
        game.scene.add_entity(follower)

        for _ in range(30):
            game.step(FIXED_DT)

        wheel_angle = wheel.get_component(Transform).angle
        follower_angle = follower.get_component(Transform).angle
        assert follower_angle == pytest.approx(wheel_angle, abs=1e-6)

    def test_binding_with_scale(self):
        """PropertyBinding.scale must scale the mirrored value."""
        game = make_game()
        source = self._make_driven_wheel(game)

        target = Sprite.circle(radius=0.3, x=3.0, y=0.0, physics=False)
        target.add_component(
            PropertyBinding(
                source_entity_id=source.id,
                source_attr="angle",
                target_attr="angle",
                scale=2.0,
            )
        )
        game.scene.add_entity(target)

        for _ in range(30):
            game.step(FIXED_DT)

        src_angle = source.get_component(Transform).angle
        tgt_angle = target.get_component(Transform).angle
        assert tgt_angle == pytest.approx(src_angle * 2.0, abs=1e-6)

    def test_binding_disabled_does_not_update(self):
        """When enabled=False, the follower angle must not change."""
        game = make_game()
        source = self._make_driven_wheel(game)

        target = Sprite.circle(radius=0.3, x=3.0, y=0.0, physics=False)
        target.add_component(
            PropertyBinding(
                source_entity_id=source.id,
                source_attr="angle",
                target_attr="angle",
                enabled=False,
            )
        )
        game.scene.add_entity(target)
        initial_angle = target.get_component(Transform).angle

        for _ in range(30):
            game.step(FIXED_DT)

        assert target.get_component(Transform).angle == pytest.approx(initial_angle)

    def test_get_entity_by_id(self):
        """World.get_entity_by_id must return the correct entity."""
        game = make_game()
        e1 = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=False)
        e2 = Sprite.rect(width=1.0, height=1.0, x=1.0, y=0.0, physics=False)
        game.scene.add_entities(e1, e2)

        assert game.scene.get_entity_by_id(e1.id) is e1
        assert game.scene.get_entity_by_id(e2.id) is e2
        assert game.scene.get_entity_by_id(-999) is None


