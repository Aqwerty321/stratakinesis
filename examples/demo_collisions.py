"""demo_collisions.py — Sprite.polygon + collision callbacks demo.

Shapes fall onto a static floor.  Console prints each collision-begin
and collision-end event.  Press SPACE to drop extra shapes.
"""

import math
import pygame
from strata import Game, Sprite, CollisionEvent
from strata.ecs.components import Physics

game = Game(
    window_size=(1024, 576),
    title="STRATA — Collisions",
    gravity=(0.0, -9.81),
    show_overlay=True,
)

# --- Static arena (floor + walls) ---
floor = Sprite.rect(width=14.0, height=0.4, x=0.0, y=-4.0, static=True)
wall_l = Sprite.rect(width=0.3, height=8.0, x=-7.0, y=0.0, static=True)
wall_r = Sprite.rect(width=0.3, height=8.0, x=7.0, y=0.0, static=True)

# --- Polygon shapes ---
# Equilateral triangle (side ≈ 1.73 wu)
r = 1.0
tri_verts = [
    (r * math.cos(math.radians(90 + 120 * i)),
     r * math.sin(math.radians(90 + 120 * i)))
    for i in range(3)
]
triangle = Sprite.polygon(tri_verts, x=-2.5, y=2.0, density=1.5, color=(255, 100, 80, 220))

# Diamond (4-sided convex)
diamond_verts = [(0.0, 0.8), (-0.6, 0.0), (0.0, -0.8), (0.6, 0.0)]
diamond = Sprite.polygon(diamond_verts, x=2.5, y=3.0, density=1.0, color=(80, 220, 160, 220))

# Circle for variety
ball = Sprite.circle(radius=0.45, x=0.0, y=4.5, density=1.0)

# --- Ghost ball: different collision layer (won't collide with floor/walls) ---
ghost = Sprite.circle(radius=0.4, x=1.5, y=4.5, density=0.5, color=(180, 180, 255, 120))
ghost.get_component(Physics).collision_layer = 0b0010
ghost.get_component(Physics).collision_mask = 0b0010  # only sees other 0b0010 shapes

game.scene.add_entities(floor, wall_l, wall_r, triangle, diamond, ball, ghost)

# --- Collision hooks ---
collision_count = [0]

def on_begin(ev: CollisionEvent) -> None:
    collision_count[0] += 1
    a, b = ev.entity_a_id, ev.entity_b_id
    nx, ny = ev.normal
    print(f"[BEGIN ] entity {a:3d} ↔ {b:3d}  n=({nx:+.2f}, {ny:+.2f})  total={collision_count[0]}")

def on_end(ev: CollisionEvent) -> None:
    a, b = ev.entity_a_id, ev.entity_b_id
    print(f"[END   ] entity {a:3d} ↔ {b:3d}")

game.on_collision_begin = on_begin
game.on_collision_end   = on_end

# --- SPACE: drop a fresh polygon ---
drop_x = [0.0]

def on_event(event: pygame.event.Event) -> None:
    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
        drop_x[0] = (drop_x[0] + 1.5) % 6.0 - 3.0
        new_shape = Sprite.polygon(
            tri_verts, x=drop_x[0], y=3.5, density=1.0, color=(200, 200, 60, 220)
        )
        game.scene.add_entity(new_shape)
        print(f"[SPAWN ] entity {new_shape.id} at x={drop_x[0]:.1f}")

game.on_event = on_event
game.run()
