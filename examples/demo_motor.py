"""
examples/demo_motor.py
======================
Sprint 3 demo: a motor-driven wheel rolling across a ground platform.

Demonstrates:
  - MotorRig: declarative motor driving a wheel's angular velocity
  - PropertyBinding: mirroring a Transform attribute between entities
  - Live control: LEFT/RIGHT arrows adjust motor speed; SPACE reverses it

Run with:
    python examples/demo_motor.py
"""

import pygame
from strata import Game, Sprite
from strata.ecs.components import MotorRig, PropertyBinding, Physics

MOTOR_RATE = 8.0  # radians/second


if __name__ == "__main__":
    game = Game(window_size=(1024, 768), title="STRATA — demo_motor", vsync=True)

    # Ground
    ground = Sprite.rect(width=20.0, height=0.5, x=0.0, y=-3.5, static=True)

    # Invisible walls at world edges — stop the wheel from rolling off forever
    from strata.config import WORLD_WIDTH, WORLD_HEIGHT
    wall_h = WORLD_HEIGHT
    wall_x = WORLD_WIDTH / 2.0 - 0.1
    wall_left  = Sprite.rect(width=0.2, height=wall_h, x=-wall_x, y=0.0, static=True,
                             color=(0, 0, 0, 0), outline=None)
    wall_right = Sprite.rect(width=0.2, height=wall_h, x= wall_x, y=0.0, static=True,
                             color=(0, 0, 0, 0), outline=None)

    # Wheel: a dynamic circle with a MotorRig attached.
    # High friction so it rolls on the ground instead of sliding.
    wheel = Sprite.circle(radius=0.8, x=-5.0, y=-2.0, density=1.0, physics=True)
    wheel.get_component(Physics).shape.friction = 2.0
    wheel.add_component(MotorRig(target_rate=MOTOR_RATE, max_force=5e5))

    # A secondary disk that mirrors the wheel's angle via PropertyBinding
    # (pure visual — no physics body)
    follower = Sprite.circle(
        radius=0.4,
        x=4.0,
        y=1.5,
        physics=False,
        color=(255, 160, 80, 200),
        outline=(255, 255, 255, 160),
    )
    follower.add_component(
        PropertyBinding(
            source_entity_id=wheel.id,
            source_attr="angle",
            target_attr="angle",
            scale=1.0,
        )
    )

    game.scene.add_entities(ground, wall_left, wall_right, wheel, follower)

    # Override run loop to handle arrow-key input each frame
    # We monkey-patch the event block by subclassing isn't needed — just show
    # users they can step manually with a custom loop instead.

    import sys
    from strata.config import FIXED_DT, MAX_FRAME_TIME

    pygame.init()
    accumulator = 0.0
    font = pygame.font.SysFont("monospace", 18)

    print("STRATA")
    print("Engineered with Stratakinesis")
    print("LEFT/RIGHT: adjust motor speed  |  SPACE: reverse  |  ESC: quit")

    # Cap at 240fps when vsync is unavailable to keep alpha deltas stable
    _FALLBACK_CAP = 240

    clock_obj = game._clock
    running = True
    rig: MotorRig = wheel.get_component(MotorRig)

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    rig.target_rate *= -1.0
            elif event.type == pygame.VIDEORESIZE:
                game._surface = pygame.display.set_mode(
                    (event.w, event.h), pygame.RESIZABLE
                )
                game.camera.resize((event.w, event.h))

        keys = pygame.key.get_pressed()
        if keys[pygame.K_RIGHT]:
            rig.target_rate = min(rig.target_rate + 0.1, 20.0)
        if keys[pygame.K_LEFT]:
            rig.target_rate = max(rig.target_rate - 0.1, -20.0)

        frame_time = min(clock_obj.tick(_FALLBACK_CAP if not game._vsync else 0), MAX_FRAME_TIME)
        accumulator += frame_time
        while accumulator >= FIXED_DT:
            game.scene.update(FIXED_DT)
            accumulator -= FIXED_DT

        alpha = accumulator / FIXED_DT
        game.scene.draw(game._surface, game.camera, alpha)

        # HUD overlay
        hud = font.render(
            f"motor rate: {rig.target_rate:+.1f} rad/s  |  FPS: {clock_obj.fps:.0f}",
            True,
            (220, 220, 220),
        )
        game._surface.blit(hud, (12, 8))
        pygame.display.flip()

    pygame.quit()
    sys.exit(0)
