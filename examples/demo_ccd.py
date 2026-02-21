"""demo_ccd.py — Continuous Collision Detection showcase.

Demonstrates the multi-layer CCD system preventing high-speed tunneling.

The arena has a series of thin vertical walls.  Projectiles are fired at
extreme speeds — fast enough to tunnel through multiple walls per frame
without CCD.  With CCD enabled (default) they slam into the first wall
they hit.  Press C to toggle CCD on/off and see the difference live.

Controls
--------
SPACE   : fire a fast projectile from the left cannon
B       : fire a burst of 5 projectiles at staggered angles
C       : toggle CCD on / off (watch the difference!)
1-3     : set projectile speed (1=fast, 2=faster, 3=ludicrous)
R       : reset — clear all projectiles
F3      : toggle debug overlay
ESC     : quit
"""

import math
import itertools
import pygame
from strata import Game, Sprite, CollisionEvent
from strata.ecs.components import Physics, Transform


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

WALL_COLOR    = (160, 170, 190, 255)
FLOOR_COLOR   = (120, 125, 135, 255)
CANNON_COLOR  = (200, 100,  60, 255)
TRAIL_COLOR   = (255, 200, 100,  60)

BULLET_COLORS = itertools.cycle([
    (255, 100,  80, 240),   # red
    (100, 200, 255, 240),   # cyan
    (255, 220,  60, 240),   # yellow
    (120, 255, 120, 240),   # green
    (220, 140, 255, 240),   # purple
    (255, 180, 100, 240),   # orange
])


# ---------------------------------------------------------------------------
# Game setup
# ---------------------------------------------------------------------------

game = Game(
    window_size=(1280, 720),
    title="STRATA — CCD Demo  (SPACE=fire  C=toggle CCD  B=burst  R=reset  F3=overlay)",
    gravity=(0.0, -4.0),
    show_overlay=True,
    physics_ccd=True,
    physics_max_substeps=32,
)

# Zero-gravity horizontal arena so projectiles fly straight
game.physics.space.gravity = (0.0, -2.0)


# ---------------------------------------------------------------------------
# Arena: floor, ceiling, side walls, and a series of thin vertical walls
# ---------------------------------------------------------------------------

def add_wall(x, y, w, h, color=WALL_COLOR):
    wall = Sprite.rect(width=w, height=h, x=x, y=y, static=True, color=color)
    game.scene.add_entity(wall)
    return wall


# Floor and ceiling
add_wall(0.0, -4.2, 18.0, 0.4, FLOOR_COLOR)
add_wall(0.0,  4.2, 18.0, 0.4, FLOOR_COLOR)

# Side walls
add_wall(-8.2, 0.0, 0.4, 9.0, FLOOR_COLOR)
add_wall( 8.2, 0.0, 0.4, 9.0, FLOOR_COLOR)

# Thin vertical barrier walls — spaced across the arena
# These are intentionally thin (0.08 world units ≈ 6 pixels) to make
# tunneling trivially easy without CCD.
WALL_THICKNESS = 0.08
wall_positions = [-3.0, -1.0, 1.0, 3.0, 5.0]
thin_walls = []
for wx in wall_positions:
    tw = add_wall(wx, 0.0, WALL_THICKNESS, 7.5, (180, 190, 210, 200))
    thin_walls.append(tw)

# Cannon visual (static decorative rect on left side)
cannon = add_wall(-7.0, 0.0, 1.2, 0.5, CANNON_COLOR)

# Label positions (screen space, drawn in on_draw)
LABEL_WALL_Y = 3.5


# ---------------------------------------------------------------------------
# Projectile management
# ---------------------------------------------------------------------------

projectiles: list = []
impact_count = [0]
speed_level = [1]       # 1=fast, 2=faster, 3=ludicrous
SPEED_MAP = {1: 80, 2: 200, 3: 500}
SPEED_NAMES = {1: "FAST (80)", 2: "FASTER (200)", 3: "LUDICROUS (500)"}

# Trail tracking: list of (x, y, age) tuples for fading trail dots
trails: list[list[tuple[float, float, float]]] = []


def fire_projectile(angle_deg: float = 0.0):
    """Fire a projectile from the left cannon at the current speed level."""
    speed = SPEED_MAP[speed_level[0]]
    color = next(BULLET_COLORS)
    rad = math.radians(angle_deg)
    vx = speed * math.cos(rad)
    vy = speed * math.sin(rad)

    bullet = Sprite.circle(radius=0.15, x=-6.2, y=0.0 + 0.5 * math.sin(rad),
                           density=2.0, color=color)
    game.scene.add_entity(bullet)
    bullet.get_component(Physics).body.velocity = (vx, vy)
    # Low restitution so they stick near the wall
    bullet.get_component(Physics).shape.elasticity = 0.3
    bullet.get_component(Physics).shape.friction = 0.5
    projectiles.append(bullet)
    trails.append([])


def clear_projectiles():
    """Remove all projectiles from the scene."""
    for e in list(projectiles):
        p = e.get_component(Physics)
        if p:
            to_remove = []
            if p.shape is not None and p.shape in game.physics.space.shapes:
                to_remove.append(p.shape)
            if p.body is not None and p.body in game.physics.space.bodies:
                to_remove.append(p.body)
            if to_remove:
                game.physics.space.remove(*to_remove)
        game.scene.remove_entity(e)
    projectiles.clear()
    trails.clear()
    impact_count[0] = 0


# ---------------------------------------------------------------------------
# Collision callback
# ---------------------------------------------------------------------------

WALL_IDS = {tw.id for tw in thin_walls}


def on_begin(ev: CollisionEvent) -> None:
    a, b = ev.entity_a_id, ev.entity_b_id
    # Only count projectile-vs-wall impacts
    if a in WALL_IDS or b in WALL_IDS:
        impact_count[0] += 1


game.on_collision_begin = on_begin


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------

def on_event(event: pygame.event.Event) -> None:
    if event.type != pygame.KEYDOWN:
        return
    if event.key == pygame.K_SPACE:
        fire_projectile(0.0)
        print(f"[FIRE] speed={SPEED_MAP[speed_level[0]]}  CCD={'ON' if game.physics._ccd_enabled else 'OFF'}")
    elif event.key == pygame.K_b:
        for angle in [-8, -4, 0, 4, 8]:
            fire_projectile(angle)
        print(f"[BURST] ×5  speed={SPEED_MAP[speed_level[0]]}")
    elif event.key == pygame.K_c:
        game.physics._ccd_enabled = not game.physics._ccd_enabled
        state = "ON" if game.physics._ccd_enabled else "OFF"
        print(f"[CCD] {state}")
    elif event.key == pygame.K_r:
        clear_projectiles()
        print("[RESET] cleared")
    elif event.key == pygame.K_1:
        speed_level[0] = 1
        print(f"[SPEED] {SPEED_NAMES[1]}")
    elif event.key == pygame.K_2:
        speed_level[0] = 2
        print(f"[SPEED] {SPEED_NAMES[2]}")
    elif event.key == pygame.K_3:
        speed_level[0] = 3
        print(f"[SPEED] {SPEED_NAMES[3]}")


game.on_event = on_event


# ---------------------------------------------------------------------------
# Update: record trails and auto-despawn off-screen projectiles
# ---------------------------------------------------------------------------

def on_update(dt: float) -> None:
    to_remove = []
    for i, bullet in enumerate(projectiles):
        t = bullet.get_component(Transform)
        if t is None:
            continue
        # Record trail position
        if i < len(trails):
            trails[i].append((t.x, t.y, 0.0))
            # Cap trail length
            if len(trails[i]) > 30:
                trails[i] = trails[i][-30:]
        # Despawn if off-screen
        if abs(t.x) > 10 or abs(t.y) > 6:
            to_remove.append(i)

    # Remove off-screen projectiles (reverse order to keep indices valid)
    for idx in reversed(to_remove):
        e = projectiles[idx]
        p = e.get_component(Physics)
        if p:
            rm = []
            if p.shape is not None and p.shape in game.physics.space.shapes:
                rm.append(p.shape)
            if p.body is not None and p.body in game.physics.space.bodies:
                rm.append(p.body)
            if rm:
                game.physics.space.remove(*rm)
        game.scene.remove_entity(e)
        projectiles.pop(idx)
        if idx < len(trails):
            trails.pop(idx)


game.on_update = on_update


# ---------------------------------------------------------------------------
# Custom draw: HUD with CCD status, speed, impact count, and trails
# ---------------------------------------------------------------------------

_hud_font = None


def _get_hud_font():
    global _hud_font
    if _hud_font is None:
        _hud_font = pygame.font.SysFont("monospace", 18)
    return _hud_font


def on_draw(surf, cam) -> None:
    font = _get_hud_font()
    w, h = surf.get_size()

    # Draw fading bullet trails
    for trail in trails:
        n = len(trail)
        for j, (tx, ty, _) in enumerate(trail):
            alpha = int(40 * (j + 1) / n) if n > 0 else 0
            sx, sy = cam.world_to_screen(tx, ty)
            r = max(1, int(2 * (j + 1) / n))
            trail_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(trail_surf, (255, 200, 100, alpha), (r, r), r)
            surf.blit(trail_surf, (sx - r, sy - r))

    # Draw wall labels
    for i, wx in enumerate(wall_positions):
        sx, sy = cam.world_to_screen(wx, LABEL_WALL_Y)
        label = font.render(f"W{i+1}", True, (200, 210, 230))
        surf.blit(label, (sx - label.get_width() // 2, sy))

    # Bottom-right HUD
    ccd_on = game.physics._ccd_enabled
    ccd_color = (100, 255, 100) if ccd_on else (255, 100, 100)
    ccd_text = "CCD: ON" if ccd_on else "CCD: OFF (tunneling likely!)"
    substep_text = f"substeps: {game.physics.substeps}"

    lines = [
        (ccd_text, ccd_color),
        (substep_text, (200, 220, 240)),
        (f"speed: {SPEED_NAMES[speed_level[0]]}", (240, 220, 180)),
        (f"impacts: {impact_count[0]}", (220, 220, 220)),
        ("", (0, 0, 0)),
        ("SPACE=fire  B=burst  C=toggle CCD", (170, 170, 180)),
        ("1/2/3=speed  R=reset  F3=overlay", (170, 170, 180)),
    ]

    pad = 10
    line_h = font.get_linesize()
    box_w = 320
    box_h = len(lines) * line_h + pad * 2
    bx = w - box_w - pad
    by = h - box_h - pad

    overlay = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 140))
    surf.blit(overlay, (bx, by))

    for i, (text, color) in enumerate(lines):
        if text:
            rendered = font.render(text, True, color)
            surf.blit(rendered, (bx + pad, by + pad + i * line_h))

    # Cannon label
    cx, cy = cam.world_to_screen(-7.0, 1.0)
    cannon_label = font.render("CANNON", True, (220, 140, 80))
    surf.blit(cannon_label, (cx - cannon_label.get_width() // 2, cy))


game.on_draw = on_draw


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

print("STRATA CCD demo")
print("Fire projectiles at thin walls.  Toggle CCD with C to see tunneling.")
print("SPACE=fire  B=burst  C=toggle CCD  1/2/3=speed  R=reset  F3=overlay  ESC=quit")
game.run()
