"""demo_soft_collisions.py — Multi-soft-body collision demo.

Multiple soft circles and rectangles drop into a V-shaped ramp bowl,
pile up, squish against each other, and generate soft-on-soft contacts.
Mirrors the style of demo_collisions.py but with deformable bodies.

Controls
--------
SPACE   : drop a burst of 3 soft bodies
D       : toggle debug render (nodes + springs) / filled mesh
R       : clear all dynamic soft bodies and respawn defaults
F3      : toggle FPS / physics overlay
ESC     : quit
"""

import itertools
import math
import pygame
from strata import Game, Sprite, SoftBody, CollisionEvent
from strata.ecs.components import Physics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rotated_rect_verts(
    width: float, height: float, angle_deg: float
) -> list[tuple[float, float]]:
    """4 CCW vertices of a (width × height) rect pre-rotated by angle_deg."""
    hw, hh = width / 2.0, height / 2.0
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    return [(x * ca - y * sa, x * sa + y * ca) for x, y in corners]


# ---------------------------------------------------------------------------
# Shape catalogue — cycles through soft body types with distinct colours
# ---------------------------------------------------------------------------

SHAPE_DEFS = itertools.cycle([
    ("circle",  (100, 180, 255, 200)),   # soft blue
    ("rect",    (255, 140,  80, 200)),   # soft orange
    ("circle",  (130, 255, 160, 200)),   # soft green
    ("rect",    (255, 100, 200, 200)),   # soft pink
    ("circle",  (230, 210,  80, 200)),   # soft gold
    ("rect",    (180, 130, 255, 200)),   # soft purple
])

# Size variation cycle
_CIRCLE_RADII = itertools.cycle([0.8, 1.0, 0.65, 1.1, 0.9, 0.75])
_RECT_SIZES   = itertools.cycle([
    (1.4, 1.4), (1.8, 1.2), (1.2, 1.6), (1.6, 1.0), (1.0, 1.8),
])


def make_soft_shape(x: float, y: float):
    """Create a soft body at (x, y) — alternates between circles and rects."""
    kind, color = next(SHAPE_DEFS)
    outline = tuple(min(c + 50, 255) for c in color[:3]) + (180,)

    if kind == "circle":
        r = next(_CIRCLE_RADII)
        return Sprite.soft_circle(
            radius=r, x=x, y=y,
            density=2.0,
            stiffness=600.0,
            damping=25.0,
            velocity_damping=0.993,
            node_density=3.0,
            color=color,
            outline=outline,
        )
    else:
        w, h = next(_RECT_SIZES)
        return Sprite.soft_rect(
            width=w, height=h, x=x, y=y,
            density=2.0,
            stiffness=600.0,
            damping=25.0,
            velocity_damping=0.993,
            node_density=3.0,
            color=color,
            outline=outline,
        )


# ---------------------------------------------------------------------------
# Game setup
# ---------------------------------------------------------------------------

game = Game(
    window_size=(1280, 720),
    title="STRATA — Soft Collisions  (SPACE=burst  D=debug  R=reset  ESC=quit)",
    gravity=(0.0, -9.81),
    show_overlay=True,
    physics_substeps=4,
)


# ---------------------------------------------------------------------------
# Arena: V-shaped ramp bowl + floor + walls + side shelves
# ---------------------------------------------------------------------------

arena_color = (140, 140, 160, 255)
ramp_color  = (180, 155, 100, 255)
shelf_color = (160, 130,  80, 255)

# Floor & walls
floor  = Sprite.rect(width=16.0, height=0.40, x=0.0,  y=-4.0,  static=True, color=arena_color)
wall_l = Sprite.rect(width=0.35, height=10.0, x=-7.9,  y=0.0,  static=True, color=arena_color)
wall_r = Sprite.rect(width=0.35, height=10.0, x= 7.9,  y=0.0,  static=True, color=arena_color)

# V-shaped ramps converging toward centre bottom
lrv = rotated_rect_verts(5.5, 0.35, -25.0)
rrv = rotated_rect_verts(5.5, 0.35,  25.0)
left_ramp  = Sprite.polygon(lrv, x=-3.2, y=-1.2, static=True, color=ramp_color)
right_ramp = Sprite.polygon(rrv, x= 3.2, y=-1.2, static=True, color=ramp_color)

# Small side shelves to catch wide-flung bodies
shelf_l = Sprite.rect(width=2.0, height=0.25, x=-6.2, y=1.5, static=True, color=shelf_color)
shelf_r = Sprite.rect(width=2.0, height=0.25, x= 6.2, y=1.5, static=True, color=shelf_color)

# A narrow central shelf to create layered piling
mid_shelf = Sprite.rect(width=2.5, height=0.22, x=0.0, y=0.5, static=True, color=shelf_color)

for e in [floor, wall_l, wall_r, left_ramp, right_ramp, shelf_l, shelf_r, mid_shelf]:
    game.scene.add_entity(e)

ARENA_IDS = {floor.id, wall_l.id, wall_r.id,
             left_ramp.id, right_ramp.id,
             shelf_l.id, shelf_r.id, mid_shelf.id}


# ---------------------------------------------------------------------------
# Collision tracking
# ---------------------------------------------------------------------------

collision_count = [0]


def on_begin(ev: CollisionEvent) -> None:
    collision_count[0] += 1
    a, b = ev.entity_a_id, ev.entity_b_id
    if a not in ARENA_IDS and b not in ARENA_IDS:
        nx, ny = ev.normal
        print(f"[SOFT↔SOFT] {a:3d} ↔ {b:3d}  "
              f"n=({nx:+.2f},{ny:+.2f})  total={collision_count[0]}")
    elif collision_count[0] % 25 == 0:
        print(f"[arena contact #{collision_count[0]}]")


game.on_collision_begin = on_begin


# ---------------------------------------------------------------------------
# Soft body tracking
# ---------------------------------------------------------------------------

soft_entities: list = []


def spawn_defaults():
    """Spawn the default set of soft bodies spread across the arena."""
    positions = [
        (-4.5, 5.0),
        (-1.8, 6.5),
        ( 1.8, 7.0),
        ( 4.5, 5.5),
        ( 0.0, 8.5),
    ]
    for sx, sy in positions:
        e = make_soft_shape(sx, sy)
        game.scene.add_entity(e)
        soft_entities.append(e)


spawn_defaults()


# ---------------------------------------------------------------------------
# Auto-spawner — drops a new soft body periodically
# ---------------------------------------------------------------------------

spawn_timer = [0.0]
SPAWN_INTERVAL = 2.5   # seconds between auto-spawns
MAX_SOFT_BODIES = 20   # cap to maintain performance
_drop_xs = itertools.cycle([-1.2, 0.6, -0.3, 1.4, -2.0, 0.0, 1.8, -0.8])


def on_update(dt: float) -> None:
    spawn_timer[0] += dt
    if spawn_timer[0] >= SPAWN_INTERVAL and len(soft_entities) < MAX_SOFT_BODIES:
        spawn_timer[0] = 0.0
        sx = next(_drop_xs)
        e = make_soft_shape(sx, 6.5)
        game.scene.add_entity(e)
        soft_entities.append(e)


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

def on_event(event: pygame.event.Event) -> None:
    if event.type != pygame.KEYDOWN:
        return

    if event.key == pygame.K_SPACE:
        # Burst: drop 3 soft bodies
        for dx in (-1.0, 0.0, 1.0):
            e = make_soft_shape(dx, 6.5)
            game.scene.add_entity(e)
            soft_entities.append(e)
        print(f"[BURST] +3 soft bodies  (total={len(soft_entities)})")

    elif event.key == pygame.K_d:
        # Toggle debug rendering on all soft bodies
        for e in soft_entities:
            sb = e.get_component(SoftBody)
            if sb is not None:
                sb.debug_render = not sb.debug_render
        if soft_entities:
            sb = soft_entities[0].get_component(SoftBody)
            mode = "debug" if sb and sb.debug_render else "mesh"
            print(f"[RENDER] {mode}")

    elif event.key == pygame.K_r:
        # Reset: remove all soft bodies
        for e in list(soft_entities):
            sb = e.get_component(SoftBody)
            if sb is not None:
                game.soft_body.unregister(sb, e.id)
            game.scene.remove_entity(e)
        soft_entities.clear()
        collision_count[0] = 0
        spawn_timer[0] = 0.0
        spawn_defaults()
        print("[RESET] cleared — respawned defaults")


game.on_update = on_update
game.on_event  = on_event

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

print("STRATA soft collision demo")
print("Soft circles & rects drop into a V-ramp bowl and pile up.")
print("SPACE=burst  D=debug  R=reset  F3=overlay  ESC=quit")
game.run()
