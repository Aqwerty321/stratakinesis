"""demo_soft_body.py — Soft body physics demonstration.

Spawns a soft rectangle (grid topology) and a soft circle (radial topology)
that fall onto platforms and deform on impact.

Controls
--------
D       : toggle debug render (circles + springs) / mesh render
SPACE   : drop a new soft circle
R       : reset — remove all soft bodies and respawn defaults
F3      : toggle FPS overlay
ESC     : quit
"""

import pygame
from strata import Game, Sprite, SoftBody
from strata.ecs.components import Physics


# ---------------------------------------------------------------------------
# Game setup
# ---------------------------------------------------------------------------

game = Game(
    window_size=(1280, 720),
    title="STRATA — Soft Body  (D=debug  SPACE=spawn  R=reset  ESC=quit)",
    gravity=(0.0, -9.81),
    show_overlay=True,
)

# ---------------------------------------------------------------------------
# Arena: floor + two platforms
# ---------------------------------------------------------------------------

arena_color = (140, 140, 160, 255)
platform_color = (180, 155, 100, 255)

floor = Sprite.rect(width=16.0, height=0.40, x=0.0, y=-4.0, static=True, color=arena_color)
wall_l = Sprite.rect(width=0.35, height=10.0, x=-7.9, y=0.0, static=True, color=arena_color)
wall_r = Sprite.rect(width=0.35, height=10.0, x=7.9, y=0.0, static=True, color=arena_color)

# Angled platforms to bounce soft bodies
plat_l = Sprite.rect(width=3.5, height=0.28, x=-3.5, y=-1.5, static=True, color=platform_color)
plat_r = Sprite.rect(width=3.5, height=0.28, x=3.5, y=-1.5, static=True, color=platform_color)

for e in [floor, wall_l, wall_r, plat_l, plat_r]:
    game.scene.add_entity(e)

# ---------------------------------------------------------------------------
# Soft bodies
# ---------------------------------------------------------------------------

soft_entities: list = []


def make_soft_rect(x: float = -2.5, y: float = 3.0):
    """Create a soft rectangle (grid topology)."""
    e = Sprite.soft_rect(
        cols=5, rows=5,
        width=2.0, height=2.0,
        x=x, y=y,
        density=0.8,
        stiffness=350.0,
        damping=12.0,
        node_radius=0.10,
        color=(255, 140, 80, 200),
        outline=(255, 200, 140, 180),
    )
    return e


def make_soft_circle(x: float = 2.5, y: float = 3.5):
    """Create a soft circle (radial topology)."""
    e = Sprite.soft_circle(
        rings=3, segments=14,
        radius=1.2,
        x=x, y=y,
        density=0.6,
        stiffness=280.0,
        damping=10.0,
        node_radius=0.09,
        color=(100, 180, 255, 200),
        outline=(180, 220, 255, 180),
    )
    return e


def spawn_defaults():
    """Spawn the default pair of soft bodies."""
    for factory in [make_soft_rect, make_soft_circle]:
        e = factory()
        game.scene.add_entity(e)
        soft_entities.append(e)


spawn_defaults()

# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

_spawn_x_cycle = iter([0.0, -1.5, 1.5, -3.0, 3.0, 0.5, -0.5])


def on_event(event: pygame.event.Event) -> None:
    if event.type != pygame.KEYDOWN:
        return

    if event.key == pygame.K_d:
        # Toggle debug rendering on all soft bodies
        for e in soft_entities:
            sb = e.get_component(SoftBody)
            if sb is not None:
                sb.debug_render = not sb.debug_render
        mode = "debug" if soft_entities and soft_entities[0].get_component(SoftBody).debug_render else "mesh"
        print(f"[RENDER] {mode}")

    elif event.key == pygame.K_SPACE:
        try:
            sx = next(_spawn_x_cycle)
        except StopIteration:
            sx = 0.0
        e = make_soft_circle(x=sx, y=5.5)
        game.scene.add_entity(e)
        soft_entities.append(e)
        print(f"[SPAWN] soft circle at x={sx:.1f}")

    elif event.key == pygame.K_r:
        # Reset: remove all soft bodies
        for e in list(soft_entities):
            sb = e.get_component(SoftBody)
            if sb is not None:
                game.soft_body.unregister(sb, e.id)
            game.scene.remove_entity(e)
        soft_entities.clear()
        spawn_defaults()
        print("[RESET]")


game.on_event = on_event

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

print("STRATA soft body demo")
print("D=toggle debug/mesh  SPACE=spawn circle  R=reset  F3=overlay  ESC=quit")
game.run()
