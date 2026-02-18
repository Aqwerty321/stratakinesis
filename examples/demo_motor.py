"""
examples/demo_motor.py
======================
Sprint 3 demo: a motor-driven wheel rolling across a ground platform.

Demonstrates:
  - MotorRig: declarative motor driving a wheel's angular velocity
  - PropertyBinding: mirroring a Transform attribute between entities
  - Live control: LEFT/RIGHT arrows adjust motor speed; SPACE reverses it
  - game.on_fixed_update: sample-accurate per-physics-step event delivery
  - game.on_update: per-frame continuous key-state polling

Run with:
    python examples/demo_motor.py
"""

import pygame
from strata import Game, Sprite
from strata.ecs.components import MotorRig, Physics, PropertyBinding
from strata.core.input_buffer import StampedEvent
from strata.config import WORLD_WIDTH, WORLD_HEIGHT

MOTOR_RATE = 8.0  # radians/second

if __name__ == "__main__":
    game = Game(window_size=(1024, 768), title="STRATA — demo_motor")

    # Ground
    ground = Sprite.rect(width=20.0, height=0.5, x=0.0, y=-3.5, static=True)

    # Invisible walls at world edges
    wall_h = WORLD_HEIGHT
    wall_x = WORLD_WIDTH / 2.0 - 0.1
    wall_left  = Sprite.rect(width=0.2, height=wall_h, x=-wall_x, y=0.0, static=True,
                             color=(0, 0, 0, 0), outline=None)
    wall_right = Sprite.rect(width=0.2, height=wall_h, x= wall_x, y=0.0, static=True,
                             color=(0, 0, 0, 0), outline=None)

    # Wheel with motor and high friction so it rolls rather than slides
    wheel = Sprite.circle(radius=0.8, x=-5.0, y=-2.0, density=1.0, physics=True)
    wheel.get_component(Physics).shape.friction = 2.0
    wheel.add_component(MotorRig(target_rate=MOTOR_RATE, max_force=5e5))

    # Follower disk that mirrors the wheel's rotation angle (no physics body)
    follower = Sprite.circle(
        radius=0.4, x=4.0, y=1.5, physics=False,
        color=(255, 160, 80, 200), outline=(255, 255, 255, 160),
    )
    follower.add_component(PropertyBinding(
        source_entity_id=wheel.id, source_attr="angle", target_attr="angle", scale=1.0,
    ))

    game.scene.add_entities(ground, wall_left, wall_right, wheel, follower)

    rig: MotorRig = wheel.get_component(MotorRig)

    # on_fixed_update: called once per physics step with the events that
    # occurred within that step's time window.  Ideal for discrete actions
    # (SPACE to reverse) so they land on the exact step they were pressed.
    def on_fixed_update(dt: float, events: list[StampedEvent]) -> None:
        for se in events:
            if se.event.type == pygame.KEYDOWN and se.event.key == pygame.K_SPACE:
                rig.target_rate *= -1.0

    # on_update: called once per rendered frame — right tool for continuous
    # key-state polling (held LEFT/RIGHT).
    def on_update(dt: float) -> None:
        keys = game.input.poll_keys()
        if keys[pygame.K_RIGHT]:
            rig.target_rate = min(rig.target_rate + 0.1, 20.0)
        if keys[pygame.K_LEFT]:
            rig.target_rate = max(rig.target_rate - 0.1, -20.0)

    game.on_fixed_update = on_fixed_update
    game.on_update = on_update

    print("LEFT/RIGHT: adjust motor speed  |  SPACE: reverse  |  ESC: quit  |  F3: overlay")

    game.run()
