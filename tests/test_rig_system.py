# tests/test_rig_system.py
# Tests for RigSystem v1: MotorRig execution and PropertyBinding mirroring.

import math
import os

import pytest
import pymunk

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from strata.config import FIXED_DT
from strata.ecs.components import MotorRig, PropertyBinding, Physics, Transform
from strata.shapes.factory import Sprite


def make_game():
    from strata.core.loop import Game
    return Game(window_size=(800, 600))


class TestMotorRig:
    def test_motor_constraint_created_on_first_step(self):
        """After first step, MotorRig._constraint must be a SimpleMotor."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=True)
        wheel.add_component(MotorRig(target_rate=5.0))
        game.scene.add_entities(wheel)

        game.step(FIXED_DT)

        rig: MotorRig = wheel.get_component(MotorRig)
        assert rig._constraint is not None
        assert isinstance(rig._constraint, pymunk.SimpleMotor)

    def test_motor_constraint_rate_matches_target(self):
        """After step, the pymunk constraint rate must match MotorRig.target_rate."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=True)
        rate = 7.0
        wheel.add_component(MotorRig(target_rate=rate))
        game.scene.add_entities(wheel)
        game.step(FIXED_DT)

        rig: MotorRig = wheel.get_component(MotorRig)
        assert rig._constraint.rate == pytest.approx(rate)

    def test_motor_rate_update_propagates(self):
        """Changing target_rate mid-simulation must update the constraint next step."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=True)
        wheel.add_component(MotorRig(target_rate=3.0))
        game.scene.add_entities(wheel)
        game.step(FIXED_DT)

        rig: MotorRig = wheel.get_component(MotorRig)
        rig.target_rate = -6.0
        game.step(FIXED_DT)

        assert rig._constraint.rate == pytest.approx(-6.0)

    def test_motor_disabled_zeroes_rate(self):
        """When enabled=False, the constraint rate must be forced to 0."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=True)
        wheel.add_component(MotorRig(target_rate=10.0, enabled=False))
        game.scene.add_entities(wheel)
        game.step(FIXED_DT)

        rig: MotorRig = wheel.get_component(MotorRig)
        assert rig._constraint.rate == pytest.approx(0.0)

    def test_motor_constraint_added_to_space(self):
        """The SimpleMotor constraint must be present in the pymunk Space."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=True)
        wheel.add_component(MotorRig(target_rate=4.0))
        game.scene.add_entities(wheel)
        game.step(FIXED_DT)

        rig: MotorRig = wheel.get_component(MotorRig)
        assert rig._constraint in game.physics.space.constraints

    def test_motor_constraint_not_duplicated(self):
        """Stepping multiple times must not add duplicate constraints."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=True)
        wheel.add_component(MotorRig(target_rate=2.0))
        game.scene.add_entities(wheel)

        for _ in range(10):
            game.step(FIXED_DT)

        count = sum(
            1 for c in game.physics.space.constraints
            if isinstance(c, pymunk.SimpleMotor)
        )
        assert count == 1

    def test_motor_drives_rotation(self):
        """A wheel with a positive motor rate should accumulate angular velocity."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=5.0, physics=True)
        wheel.add_component(MotorRig(target_rate=10.0, max_force=1e9))
        game.scene.add_entities(wheel)

        for _ in range(30):
            game.step(FIXED_DT)

        phys: Physics = wheel.get_component(Physics)
        # Angular velocity should be non-zero (motor is driving rotation)
        assert abs(phys.body.angular_velocity) > 0.1


class TestPropertyBinding:
    def test_binding_mirrors_source_angle(self):
        """Follower Transform.angle must match wheel Transform.angle after steps."""
        game = make_game()
        wheel = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=True)
        wheel.add_component(MotorRig(target_rate=5.0, max_force=1e9))

        follower = Sprite.circle(radius=0.3, x=3.0, y=0.0, physics=False)
        follower.add_component(
            PropertyBinding(
                source_entity_id=wheel.id,
                source_attr="angle",
                target_attr="angle",
            )
        )

        game.scene.add_entities(wheel, follower)
        for _ in range(30):
            game.step(FIXED_DT)

        wheel_angle = wheel.get_component(Transform).angle
        follower_angle = follower.get_component(Transform).angle
        assert follower_angle == pytest.approx(wheel_angle, abs=1e-6)

    def test_binding_with_scale(self):
        """PropertyBinding.scale must scale the mirrored value."""
        game = make_game()
        source = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=True)
        source.add_component(MotorRig(target_rate=5.0, max_force=1e9))

        target = Sprite.circle(radius=0.3, x=3.0, y=0.0, physics=False)
        target.add_component(
            PropertyBinding(
                source_entity_id=source.id,
                source_attr="angle",
                target_attr="angle",
                scale=2.0,
            )
        )

        game.scene.add_entities(source, target)
        for _ in range(30):
            game.step(FIXED_DT)

        src_angle = source.get_component(Transform).angle
        tgt_angle = target.get_component(Transform).angle
        assert tgt_angle == pytest.approx(src_angle * 2.0, abs=1e-6)

    def test_binding_disabled_does_not_update(self):
        """When enabled=False, the follower angle must not change."""
        game = make_game()
        source = Sprite.circle(radius=0.5, x=0.0, y=0.0, physics=True)
        source.add_component(MotorRig(target_rate=5.0, max_force=1e9))

        target = Sprite.circle(radius=0.3, x=3.0, y=0.0, physics=False)
        target.add_component(
            PropertyBinding(
                source_entity_id=source.id,
                source_attr="angle",
                target_attr="angle",
                enabled=False,
            )
        )

        game.scene.add_entities(source, target)
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
