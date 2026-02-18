"""demo_collisions.py — Sprite.polygon + collision callbacks demo.

A V-shaped ramp bowl funnels all shapes into the centre so they pile up,
roll over each other, and generate plenty of shape-on-shape contacts.

Controls
--------
SPACE   : drop a burst of 3 shapes immediately
R       : clear all dynamic bodies
F3      : toggle debug overlay
ESC     : quit

Collision layers
----------------
SOLID (0b01) : floor, walls, ramps, shelves  — all normal shapes use this.
GHOST (0b10) : ghost_ledge + ghost_ball only.
The ghost ball (translucent blue) falls right through the ramps because
the ramps have mask=0b01 and the ghost has layer=0b10; the bitmasks never
agree, so pymunk skips those pairs entirely.
"""

import math
import itertools
import pygame
from strata import Game, Sprite, CollisionEvent
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


def equilateral_triangle(r: float) -> list[tuple[float, float]]:
    return [
        (r * math.cos(math.radians(90 + 120 * i)),
         r * math.sin(math.radians(90 + 120 * i)))
        for i in range(3)
    ]


def hexagon(r: float) -> list[tuple[float, float]]:
    return [
        (r * math.cos(math.radians(60 * i)),
         r * math.sin(math.radians(60 * i)))
        for i in range(6)
    ]


# Shape catalogue — cycles on each auto-spawn / burst
SHAPE_DEFS = itertools.cycle([
    ("circle",   (100, 180, 255, 220)),
    ("triangle", (255, 110,  80, 220)),
    ("diamond",  ( 80, 220, 130, 220)),
    ("hexagon",  (230, 190,  50, 220)),
    ("circle",   (255, 130, 220, 220)),
    ("triangle", (130, 210, 255, 220)),
])


def make_shape(x: float, y: float):
    kind, color = next(SHAPE_DEFS)
    if kind == "circle":
        return Sprite.circle(radius=0.38, x=x, y=y, density=1.2, color=color)
    if kind == "triangle":
        return Sprite.polygon(equilateral_triangle(0.45), x=x, y=y,
                              density=1.5, color=color)
    if kind == "diamond":
        verts = [(0.0, 0.6), (-0.45, 0.0), (0.0, -0.6), (0.45, 0.0)]
        return Sprite.polygon(verts, x=x, y=y, density=1.0, color=color)
    # hexagon
    return Sprite.polygon(hexagon(0.38), x=x, y=y, density=1.0, color=color)


# ---------------------------------------------------------------------------
# Game setup
# ---------------------------------------------------------------------------

game = Game(
    window_size=(1280, 720),
    title="STRATA — Collisions  (SPACE=burst  R=reset  F3=overlay  ESC=quit)",
    gravity=(0.0, -9.81),
    show_overlay=True,
)

SOLID_LAYER = 0b01
GHOST_LAYER = 0b10

arena_color = (140, 140, 160, 255)
ramp_color  = (180, 155, 100, 255)
shelf_color = (160, 130,  80, 255)


def add_solid(entity):
    """Tag with SOLID layer/mask and add to scene."""
    p = entity.get_component(Physics)
    if p:
        p.collision_layer = SOLID_LAYER
        p.collision_mask  = SOLID_LAYER
    game.scene.add_entity(entity)
    return entity


# --- Floor & walls ---
floor  = add_solid(Sprite.rect(width=16.0, height=0.40, x=0.0,  y=-4.0, static=True, color=arena_color))
wall_l = add_solid(Sprite.rect(width=0.35, height=10.0, x=-7.9, y=0.0,  static=True, color=arena_color))
wall_r = add_solid(Sprite.rect(width=0.35, height=10.0, x= 7.9, y=0.0,  static=True, color=arena_color))

# --- V-shaped ramps converging toward centre bottom ---
# Left ramp: tilts ~28° downward toward x=0
lrv = rotated_rect_verts(6.0, 0.35, -28.0)
rrv = rotated_rect_verts(6.0, 0.35,  28.0)
left_ramp  = add_solid(Sprite.polygon(lrv, x=-3.5, y=-1.0, static=True, color=ramp_color))
right_ramp = add_solid(Sprite.polygon(rrv, x= 3.5, y=-1.0, static=True, color=ramp_color))

# --- Side shelves (catch shapes that fly wide) ---
shelf_l = add_solid(Sprite.rect(width=2.2, height=0.25, x=-6.5, y=1.8, static=True, color=shelf_color))
shelf_r = add_solid(Sprite.rect(width=2.2, height=0.25, x= 6.5, y=1.8, static=True, color=shelf_color))

# --- Ghost ledge — only ghost-layer objects land here ---
ghost_ledge_verts = rotated_rect_verts(3.2, 0.28, 0.0)
ghost_ledge = Sprite.polygon(ghost_ledge_verts, x=0.0, y=0.6, static=True,
                              color=(160, 160, 255, 90))
ghost_ledge.get_component(Physics).collision_layer = GHOST_LAYER
ghost_ledge.get_component(Physics).collision_mask  = GHOST_LAYER
game.scene.add_entity(ghost_ledge)

# ---------------------------------------------------------------------------
# Initial dynamic shapes
# ---------------------------------------------------------------------------

# Five shapes staggered above the ramps in a tight cluster
for sx, sy in [(-0.9, 3.8), (0.3, 4.5), (-0.2, 5.2), (0.8, 4.0), (-1.5, 5.0)]:
    game.scene.add_entity(make_shape(sx, sy))

# Ghost ball — passes through ramps, lands only on ghost_ledge
ghost_ball = Sprite.circle(radius=0.44, x=0.1, y=6.2, density=0.6,
                            color=(180, 180, 255, 110))
ghost_ball.get_component(Physics).collision_layer = GHOST_LAYER
ghost_ball.get_component(Physics).collision_mask  = GHOST_LAYER
game.scene.add_entity(ghost_ball)

# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------

dynamic_entities: list = []
collision_count  = [0]

ARENA_IDS = {floor.id, wall_l.id, wall_r.id,
             left_ramp.id, right_ramp.id, shelf_l.id, shelf_r.id}


def on_begin(ev: CollisionEvent) -> None:
    collision_count[0] += 1
    a, b = ev.entity_a_id, ev.entity_b_id
    if a not in ARENA_IDS and b not in ARENA_IDS:
        nx, ny = ev.normal
        print(f"[SHAPE↔SHAPE] {a:3d} ↔ {b:3d}  "
              f"n=({nx:+.2f},{ny:+.2f})  total_contacts={collision_count[0]}")
    elif collision_count[0] % 20 == 0:
        print(f"[arena contact #{collision_count[0]}]")


game.on_collision_begin = on_begin

# ---------------------------------------------------------------------------
# Auto-spawner
# ---------------------------------------------------------------------------

spawn_timer = [0.0]
SPAWN_INTERVAL = 1.5   # seconds
_drop_xs = itertools.cycle([-0.7, 0.4, -0.1, 0.9, -1.3, 0.2])


def on_update(dt: float) -> None:
    spawn_timer[0] += dt
    if spawn_timer[0] >= SPAWN_INTERVAL:
        spawn_timer[0] = 0.0
        e = make_shape(next(_drop_xs), 5.9)
        game.scene.add_entity(e)
        dynamic_entities.append(e)


def on_event(event: pygame.event.Event) -> None:
    if event.type != pygame.KEYDOWN:
        return
    if event.key == pygame.K_SPACE:
        for dx in (-0.5, 0.0, 0.5):
            e = make_shape(dx, 5.6)
            game.scene.add_entity(e)
            dynamic_entities.append(e)
        print("[BURST] +3 shapes")
    elif event.key == pygame.K_r:
        for e in list(dynamic_entities):
            p = e.get_component(Physics)
            if p and p.body in game.physics.space.bodies:
                game.physics.space.remove(p.body, p.shape)
            game.scene.entities.pop(e.id, None)
        dynamic_entities.clear()
        collision_count[0] = 0
        spawn_timer[0] = 0.0
        print("[RESET] cleared")


game.on_update = on_update
game.on_event  = on_event

print("STRATA collision demo")
print("Ghost ball (blue, translucent) falls through ramps — lands on ghost ledge only.")
print("SPACE=burst  R=reset  F3=overlay  ESC=quit")
game.run()
