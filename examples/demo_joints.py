"""
examples/demo_joints.py
=======================
All six rig types in one scene.

World is 16 × 9 units (-8..+8 x, -4.5..+4.5 y), Y-up.

    TOP ROW   (hanging from ceiling):
      left  — double pendulum
      centre — chain (7 links, catenary from ceiling anchor)
      right  — rope  (12 beads, droops from ceiling anchor)

    BOTTOM ROW (on/near floor):
      left-centre — lever  (ball tips it)
      centre      — gear train (3 meshing gears, motor driven)
      right       — spinning disk (HingeMotorRig)

Controls:
  LEFT / RIGHT  speed up / slow down the disk motor
  SPACE         reverse disk direction
  G             toggle gear-train motor on / off
  ESC           quit    F3  debug overlay

Run with:
    python examples/demo_joints.py
"""

import pygame
from strata import Game, Sprite
from strata.ecs.components import Physics
from strata.rigs import HingeMotorRig, ChainRig, RopeRig, GearTrainRig, LeverRig, PendulumRig
from strata.core.input_buffer import StampedEvent

# ── world geometry ─────────────────────────────────────────────────────────────
FLOOR_Y  = -4.0
CEIL_Y   =  4.0

# ── colours ────────────────────────────────────────────────────────────────────
COL_WALL    = (55,  60,  75)
COL_PEND    = (100, 180, 255, 240)
COL_CHAIN   = (180, 150, 100, 230)
COL_ROPE    = (220, 160,  80, 230)
COL_LEVER   = (160, 130,  80, 240)
COL_BALL    = (240,  90,  90, 240)
COL_DISK    = (100, 240, 140, 240)
COL_GEARS   = [(255, 200, 80, 230), (80, 200, 255, 230), (200, 120, 255, 230)]


if __name__ == "__main__":
    game = Game(window_size=(1280, 720), title="STRATA — rig system demo")

    # ── floor & ceiling ──────────────────────────────────────────────────────
    floor   = Sprite.rect(width=18.0, height=0.3, x=0.0, y=FLOOR_Y,
                          static=True, color=COL_WALL)
    ceiling = Sprite.rect(width=18.0, height=0.2, x=0.0, y=CEIL_Y,
                          static=True, color=COL_WALL)
    wall_l  = Sprite.rect(width=0.3, height=10.0, x=-8.0, y=0.0,
                          static=True, color=COL_WALL)
    wall_r  = Sprite.rect(width=0.3, height=10.0, x= 8.0, y=0.0,
                          static=True, color=COL_WALL)
    game.scene.add_entities(floor, ceiling, wall_l, wall_r)

    # ── 1. double pendulum (top-left) ────────────────────────────────────────
    # Two bobs pinned to the ceiling anchor via PinJoints.
    # arm_length=1.6 → first bob at y=4.0-1.6=2.4, second at y=0.8
    pend = PendulumRig(
        length     = 2,
        bob_radius = 0.28,
        arm_length = 1.6,
        anchor     = (-5.5, CEIL_Y),
        density    = 2.0,
        color      = COL_PEND,
    )
    game.scene.add_rig(pend)
    # knock the first bob sideways so it swings immediately
    phys0: Physics = pend.bobs[0].get_component(Physics)
    phys0.body.apply_impulse_at_world_point((3.5, 0.0), phys0.body.position)

    # ── 2. chain (top-centre-left) ───────────────────────────────────────────
    # 7 links laid out horizontally starting at the anchor x.
    # Under gravity the chain forms a catenary curve hanging from the left end.
    chain = ChainRig(
        length      = 7,
        link_width  = 0.5,
        link_height = 0.18,
        start_x     = -2.0,
        start_y     = CEIL_Y - 0.3,      # just below ceiling
        anchor      = (-2.0, CEIL_Y),
        density     = 0.8,
        color       = COL_CHAIN,
    )
    game.scene.add_rig(chain)

    # ── 3. rope (top-centre-right) ───────────────────────────────────────────
    # 12 beads laid out horizontally; SlideJoint lets them sag under gravity.
    rope = RopeRig(
        length      = 12,
        bead_radius = 0.10,
        spacing     = 0.28,
        start_x     = 1.5,
        start_y     = CEIL_Y - 0.15,
        anchor      = (1.5, CEIL_Y),
        density     = 0.5,
        color       = COL_ROPE,
    )
    game.scene.add_rig(rope)

    # ── 4. lever (bottom-left) ───────────────────────────────────────────────
    # Long plank pivoted off-centre; a heavy ball dropped on the short end tips it.
    LEVER_X, LEVER_Y = -5.0, FLOOR_Y + 1.4
    lever = LeverRig(
        width        = 4.5,
        height       = 0.2,
        x            = LEVER_X,
        y            = LEVER_Y,
        pivot_offset = 1.0,          # pivot 1 m right of centre → short arm on right
        density      = 0.6,
        color        = COL_LEVER,
        min_angle    = -0.8,
        max_angle    =  0.8,
    )
    game.scene.add_rig(lever)
    # heavy ball dropped onto the short (right) end
    ball = Sprite.circle(
        radius=0.3, density=4.0,
        x=LEVER_X + 1.0 + 0.9,      # short arm right end
        y=LEVER_Y + 2.5,
        color=COL_BALL,
    )
    game.scene.add_entity(ball)

    # ── 5. gear train (bottom-centre) ────────────────────────────────────────
    # Three gears: large driver → small idler → medium follower.
    # Placed so all gear centres sit well above the floor.
    GEAR_X, GEAR_Y = -0.3, FLOOR_Y + 0.85
    gears = GearTrainRig(
        radii       = [0.65, 0.38, 0.52],
        x           = GEAR_X,
        y           = GEAR_Y,
        motor_rate  = 3.0,
        motor_force = 1e6,
        density     = 1.0,
        colors      = COL_GEARS,
    )
    game.scene.add_rig(gears)

    # ── 6. spinning disk / HingeMotorRig (bottom-right) ──────────────────────
    # Circle pinned to the world at its centre and motor-driven.
    DISK_X, DISK_Y = 5.5, FLOOR_Y + 1.1
    disk = Sprite.circle(
        radius=0.9, x=DISK_X, y=DISK_Y,
        density=0.4, color=COL_DISK,
    )
    game.scene.add_entity(disk)
    disk_rig = HingeMotorRig(disk, anchor=(DISK_X, DISK_Y),
                             rate=6.0, max_force=2e6)
    game.scene.add_rig(disk_rig)

    # ── input ─────────────────────────────────────────────────────────────────
    def on_fixed_update(dt: float, events: list[StampedEvent]) -> None:
        for se in events:
            if se.event.type == pygame.KEYDOWN:
                if se.event.key == pygame.K_SPACE:
                    disk_rig.motor.rate *= -1.0
                elif se.event.key == pygame.K_g:
                    gears.motor.enabled = not gears.motor.enabled

    def on_update(dt: float) -> None:
        keys = game.input.poll_keys()
        if keys[pygame.K_RIGHT]:
            disk_rig.motor.rate = min(disk_rig.motor.rate + 0.2, 30.0)
        if keys[pygame.K_LEFT]:
            disk_rig.motor.rate = max(disk_rig.motor.rate - 0.2, -30.0)

    game.on_fixed_update = on_fixed_update
    game.on_update = on_update

    print(
        "STRATA rig demo\n"
        "  LEFT/RIGHT : disk speed    SPACE: reverse disk\n"
        "  G          : gear on/off   ESC  : quit   F3: overlay"
    )

    game.run()
