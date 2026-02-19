"""
examples/demo_joints.py
=======================
Rig system showcase — all six rig types in one scene.

Layout (world coords, y-up):
  LEFT  column: PendulumRig, LeverRig
  CENTER column: HingeMotorRig, GearTrainRig
  RIGHT column: ChainRig, RopeRig

Controls:
  1-6         toggle labels overlay for each rig
  LEFT/RIGHT  adjust HingeMotorRig speed
  SPACE       reverse HingeMotorRig
  ESC         quit
  F3          physics debug overlay

Run with:
    python examples/demo_joints.py
"""

import pygame
from strata import Game, Sprite
from strata.ecs.components import Physics
from strata.rigs import (
    HingeMotorRig,
    ChainRig,
    RopeRig,
    GearTrainRig,
    LeverRig,
    PendulumRig,
)
from strata.core.input_buffer import StampedEvent

# ── world layout constants ────────────────────────────────────────────────────
GROUND_Y   = -4.2
CEIL_Y     =  4.5

LEFT_X   = -7.0
CENTER_X =  0.0
RIGHT_X  =  7.0

MOTOR_RATE = 6.0  # rad/s initial wheel speed


if __name__ == "__main__":
    game = Game(window_size=(1280, 720), title="STRATA — demo_joints (all rigs)")

    # ── floor & ceiling ──────────────────────────────────────────────────────
    floor   = Sprite.rect(width=26.0, height=0.4, x=0.0, y=GROUND_Y,  static=True,
                          color=(80, 80, 80))
    ceiling = Sprite.rect(width=26.0, height=0.4, x=0.0, y=CEIL_Y,    static=True,
                          color=(80, 80, 80))
    left_wall  = Sprite.rect(width=0.4, height=10.0, x=-12.8, y=0.0,  static=True,
                             color=(80, 80, 80))
    right_wall = Sprite.rect(width=0.4, height=10.0, x= 12.8, y=0.0,  static=True,
                             color=(80, 80, 80))

    game.scene.add_entities(floor, ceiling, left_wall, right_wall)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. PendulumRig  (left column, top)
    # ─────────────────────────────────────────────────────────────────────────
    pendulum = PendulumRig(
        length     = 2,
        bob_radius = 0.22,
        arm_length = 1.2,
        anchor     = (LEFT_X, CEIL_Y - 0.5),
        density    = 1.5,
        color      = (120, 200, 255),
    )
    game.scene.add_rig(pendulum)

    # give the first bob a small horizontal impulse so it swings on start
    first_bob_phys: Physics = pendulum.bobs[0].get_component(Physics)
    first_bob_phys.body.apply_impulse_at_world_point((1.8, 0.0),
                                                     first_bob_phys.body.position)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. LeverRig  (left column, bottom)
    # ─────────────────────────────────────────────────────────────────────────
    lever = LeverRig(
        width        = 5.0,
        height       = 0.2,
        x            = LEFT_X,
        y            = GROUND_Y + 1.0,
        pivot_offset = 0.8,
        density      = 0.8,
        color        = (200, 160, 80),
        min_angle    = -0.6,
        max_angle    =  0.6,
    )
    game.scene.add_rig(lever)

    # drop a ball onto the short end of the lever
    ball = Sprite.circle(radius=0.3, x=LEFT_X - 1.8, y=GROUND_Y + 3.0,
                         density=2.0, color=(255, 80, 80))
    game.scene.add_entity(ball)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. HingeMotorRig  (centre, left of centre)
    # ─────────────────────────────────────────────────────────────────────────
    WHEEL_X, WHEEL_Y = CENTER_X - 1.5, GROUND_Y + 1.2
    wheel = Sprite.circle(radius=0.75, x=WHEEL_X, y=WHEEL_Y,
                          density=1.2, color=(180, 255, 120))
    wheel.get_component(Physics).shape.friction = 1.5
    game.scene.add_entity(wheel)

    motor_rig = HingeMotorRig(wheel, anchor=(WHEEL_X, WHEEL_Y),
                              rate=MOTOR_RATE, max_force=6e5)
    game.scene.add_rig(motor_rig)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. GearTrainRig  (centre, right of centre)
    # ─────────────────────────────────────────────────────────────────────────
    gear_train = GearTrainRig(
        radii       = [0.55, 0.3, 0.45],
        x           = CENTER_X + 1.2,
        y           = GROUND_Y + 1.8,
        motor_rate  = 3.0,
        motor_force = 8e5,
        density     = 1.0,
        colors      = [(255, 200, 80), (80, 200, 255), (200, 120, 255)],
    )
    game.scene.add_rig(gear_train)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. ChainRig  (right column, top)
    # ─────────────────────────────────────────────────────────────────────────
    chain = ChainRig(
        length      = 8,
        link_width  = 0.42,
        link_height = 0.14,
        start_x     = RIGHT_X,
        start_y     = CEIL_Y - 0.8,
        anchor      = (RIGHT_X, CEIL_Y - 0.5),
        density     = 0.5,
        color       = (180, 180, 180),
    )
    game.scene.add_rig(chain)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. RopeRig  (right column, left of chain)
    # ─────────────────────────────────────────────────────────────────────────
    rope = RopeRig(
        length      = 10,
        bead_radius = 0.08,
        spacing     = 0.24,
        start_x     = RIGHT_X - 1.4,
        start_y     = CEIL_Y - 0.8,
        anchor      = (RIGHT_X - 1.4, CEIL_Y - 0.5),
        density     = 0.3,
        color       = (220, 160, 80),
    )
    game.scene.add_rig(rope)

    # ─────────────────────────────────────────────────────────────────────────
    # Input handlers
    # ─────────────────────────────────────────────────────────────────────────
    def on_fixed_update(dt: float, events: list[StampedEvent]) -> None:
        for se in events:
            if se.event.type == pygame.KEYDOWN:
                if se.event.key == pygame.K_SPACE:
                    motor_rig.motor.rate *= -1.0
                elif se.event.key == pygame.K_g:
                    # toggle gear train motor
                    gear_train.motor.enabled = not gear_train.motor.enabled

    def on_update(dt: float) -> None:
        keys = game.input.poll_keys()
        if keys[pygame.K_RIGHT]:
            motor_rig.motor.rate = min(motor_rig.motor.rate + 0.15, 25.0)
        if keys[pygame.K_LEFT]:
            motor_rig.motor.rate = max(motor_rig.motor.rate - 0.15, -25.0)

    game.on_fixed_update = on_fixed_update
    game.on_update = on_update

    print(
        "demo_joints — all six rig types\n"
        "  LEFT/RIGHT : wheel motor speed   SPACE: reverse wheel\n"
        "  G          : toggle gear motor   ESC  : quit   F3: overlay"
    )

    game.run()
