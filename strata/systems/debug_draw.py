# strata/systems/debug_draw.py
# Constraint visualiser — draws every active pymunk constraint as a
# coloured overlay when ``game.show_constraints = True``.
#
# Each constraint type gets a distinct visual:
#   PinJoint         → white line between anchors
#   PivotJoint       → small green circle at pivot point
#   SlideJoint       → dashed orange line between anchor ranges
#   GrooveJoint      → purple line for groove + dot for anchor
#   SimpleMotor      → cyan arc/circle at body A centre
#   GearJoint        → dotted magenta arc between bodies
#   RotaryLimitJoint → yellow arc showing angular range
#   DampedSpring     → zigzag green line
#   DampedRotarySpring → blue arc at body A

from __future__ import annotations
import math

import pygame
import pygame.gfxdraw
import pymunk

from strata.render.camera import Camera


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

_COL_PIN        = (255, 255, 255, 200)
_COL_PIVOT      = (100, 255, 100, 220)
_COL_SLIDE      = (255, 165, 50,  200)
_COL_GROOVE     = (180, 100, 255, 200)
_COL_MOTOR      = (80,  220, 240, 200)
_COL_GEAR       = (240, 80,  240, 180)
_COL_ROT_LIMIT  = (255, 230, 80,  200)
_COL_SPRING     = (100, 230, 100, 180)
_COL_TORSION    = (80,  130, 255, 200)
_COL_UNKNOWN    = (200, 200, 200, 150)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def draw_constraints(
    surface: pygame.Surface,
    camera: Camera,
    space: pymunk.Space,
) -> None:
    """Draw all constraints in *space* as debug overlays on *surface*."""
    for constraint in space.constraints:
        _draw_one(surface, camera, constraint)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _draw_one(
    surface: pygame.Surface,
    camera: Camera,
    c: pymunk.Constraint,
) -> None:
    if isinstance(c, pymunk.PinJoint):
        _draw_pin(surface, camera, c)
    elif isinstance(c, pymunk.PivotJoint):
        _draw_pivot(surface, camera, c)
    elif isinstance(c, pymunk.SlideJoint):
        _draw_slide(surface, camera, c)
    elif isinstance(c, pymunk.GrooveJoint):
        _draw_groove(surface, camera, c)
    elif isinstance(c, pymunk.SimpleMotor):
        _draw_motor(surface, camera, c)
    elif isinstance(c, pymunk.GearJoint):
        _draw_gear(surface, camera, c)
    elif isinstance(c, pymunk.RotaryLimitJoint):
        _draw_rot_limit(surface, camera, c)
    elif isinstance(c, pymunk.DampedSpring):
        _draw_spring(surface, camera, c)
    elif isinstance(c, pymunk.DampedRotarySpring):
        _draw_torsion(surface, camera, c)
    else:
        _draw_unknown(surface, camera, c)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _world_anchor(body: pymunk.Body, local: tuple[float, float]) -> tuple[float, float]:
    """Convert a body-local anchor to world coordinates."""
    wp = body.local_to_world(local)
    return (wp.x, wp.y)


def _to_screen(camera: Camera, wx: float, wy: float) -> tuple[int, int]:
    return camera.world_to_screen(wx, wy)


# ---------------------------------------------------------------------------
# Per-type renderers
# ---------------------------------------------------------------------------

def _draw_pin(surface: pygame.Surface, camera: Camera, c: pymunk.PinJoint) -> None:
    """White line between the two anchor points."""
    wa = _world_anchor(c.a, c.anchor_a)
    wb = _world_anchor(c.b, c.anchor_b)
    sa = _to_screen(camera, *wa)
    sb = _to_screen(camera, *wb)
    pygame.draw.line(surface, _COL_PIN[:3], sa, sb, 2)
    # Small dots at anchor points
    pygame.gfxdraw.filled_circle(surface, sa[0], sa[1], 3, _COL_PIN)
    pygame.gfxdraw.filled_circle(surface, sb[0], sb[1], 3, _COL_PIN)


def _draw_pivot(surface: pygame.Surface, camera: Camera, c: pymunk.PivotJoint) -> None:
    """Green circle at the pivot point."""
    wa = _world_anchor(c.a, c.anchor_a)
    sa = _to_screen(camera, *wa)
    r = max(4, camera.scale_length(0.08))
    pygame.gfxdraw.aacircle(surface, sa[0], sa[1], r, _COL_PIVOT)
    pygame.gfxdraw.filled_circle(surface, sa[0], sa[1], r, _COL_PIVOT)


def _draw_slide(surface: pygame.Surface, camera: Camera, c: pymunk.SlideJoint) -> None:
    """Orange line between anchor points."""
    wa = _world_anchor(c.a, c.anchor_a)
    wb = _world_anchor(c.b, c.anchor_b)
    sa = _to_screen(camera, *wa)
    sb = _to_screen(camera, *wb)
    pygame.draw.line(surface, _COL_SLIDE[:3], sa, sb, 2)
    # Small squares at anchor points
    pygame.draw.rect(surface, _COL_SLIDE[:3], (sa[0] - 3, sa[1] - 3, 6, 6))
    pygame.draw.rect(surface, _COL_SLIDE[:3], (sb[0] - 3, sb[1] - 3, 6, 6))


def _draw_groove(surface: pygame.Surface, camera: Camera, c: pymunk.GrooveJoint) -> None:
    """Purple line for groove + dot for anchor."""
    ga = _world_anchor(c.a, c.groove_a)
    gb = _world_anchor(c.a, c.groove_b)
    sa = _to_screen(camera, *ga)
    sb = _to_screen(camera, *gb)
    pygame.draw.line(surface, _COL_GROOVE[:3], sa, sb, 2)
    # Anchor point on body B
    wa = _world_anchor(c.b, c.anchor_b)
    sp = _to_screen(camera, *wa)
    pygame.gfxdraw.filled_circle(surface, sp[0], sp[1], 4, _COL_GROOVE)


def _draw_motor(surface: pygame.Surface, camera: Camera, c: pymunk.SimpleMotor) -> None:
    """Cyan circle at body A centre indicating motor."""
    pos = c.a.position
    sp = _to_screen(camera, pos.x, pos.y)
    r = max(5, camera.scale_length(0.12))
    pygame.gfxdraw.aacircle(surface, sp[0], sp[1], r, _COL_MOTOR)
    # Direction indicator — short line showing rotation direction
    angle = c.a.angle
    dx = int(r * math.cos(angle))
    dy = int(-r * math.sin(angle))  # screen Y is flipped
    pygame.draw.line(surface, _COL_MOTOR[:3], sp, (sp[0] + dx, sp[1] + dy), 2)


def _draw_gear(surface: pygame.Surface, camera: Camera, c: pymunk.GearJoint) -> None:
    """Magenta dotted line between the two gear bodies."""
    pa = c.a.position
    pb = c.b.position
    sa = _to_screen(camera, pa.x, pa.y)
    sb = _to_screen(camera, pb.x, pb.y)
    # Dotted line effect
    _draw_dotted_line(surface, _COL_GEAR[:3], sa, sb, dot_len=4, gap_len=4)
    # Small circles at centres
    r = max(3, camera.scale_length(0.06))
    pygame.gfxdraw.filled_circle(surface, sa[0], sa[1], r, _COL_GEAR)
    pygame.gfxdraw.filled_circle(surface, sb[0], sb[1], r, _COL_GEAR)


def _draw_rot_limit(surface: pygame.Surface, camera: Camera, c: pymunk.RotaryLimitJoint) -> None:
    """Yellow arc at body A showing the angular range."""
    pos = c.a.position
    sp = _to_screen(camera, pos.x, pos.y)
    r = max(8, camera.scale_length(0.15))
    # Draw an arc from min_angle to max_angle
    min_a = c.min
    max_a = c.max
    # Approximate arc with line segments
    steps = max(8, int(abs(max_a - min_a) / 0.2))
    base_angle = c.a.angle
    points = []
    for i in range(steps + 1):
        a = base_angle + min_a + (max_a - min_a) * i / steps
        px = sp[0] + int(r * math.cos(a))
        py = sp[1] - int(r * math.sin(a))
        points.append((px, py))
    if len(points) >= 2:
        pygame.draw.lines(surface, _COL_ROT_LIMIT[:3], False, points, 2)


def _draw_spring(surface: pygame.Surface, camera: Camera, c: pymunk.DampedSpring) -> None:
    """Green zigzag line between anchor points."""
    wa = _world_anchor(c.a, c.anchor_a)
    wb = _world_anchor(c.b, c.anchor_b)
    sa = _to_screen(camera, *wa)
    sb = _to_screen(camera, *wb)
    _draw_zigzag(surface, _COL_SPRING[:3], sa, sb, teeth=6, amplitude=4)


def _draw_torsion(surface: pygame.Surface, camera: Camera, c: pymunk.DampedRotarySpring) -> None:
    """Blue arc at body A."""
    pos = c.a.position
    sp = _to_screen(camera, pos.x, pos.y)
    r = max(6, camera.scale_length(0.10))
    pygame.gfxdraw.aacircle(surface, sp[0], sp[1], r, _COL_TORSION)


def _draw_unknown(surface: pygame.Surface, camera: Camera, c: pymunk.Constraint) -> None:
    """Grey line between the two bodies' centres."""
    pa = c.a.position
    pb = c.b.position
    sa = _to_screen(camera, pa.x, pa.y)
    sb = _to_screen(camera, pb.x, pb.y)
    pygame.draw.line(surface, _COL_UNKNOWN[:3], sa, sb, 1)


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------

def _draw_zigzag(
    surface: pygame.Surface,
    color: tuple[int, int, int],
    start: tuple[int, int],
    end: tuple[int, int],
    teeth: int = 6,
    amplitude: int = 4,
) -> None:
    """Draw a zigzag (spring) line from *start* to *end*."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return

    # Unit vectors along and perpendicular to the line
    ux, uy = dx / length, dy / length
    px, py = -uy, ux  # perpendicular

    points = [start]
    # Zigzag segment (skip first and last 15% of length for lead-in/out)
    margin = 0.15
    seg_start = margin * length
    seg_end = (1.0 - margin) * length
    seg_len = seg_end - seg_start

    for i in range(teeth * 2 + 1):
        t = seg_start + seg_len * i / (teeth * 2)
        offset = amplitude * (1 if i % 2 == 1 else (-1 if i % 2 == 0 and i > 0 else 0))
        if i == 0 or i == teeth * 2:
            offset = 0
        x = start[0] + ux * t + px * offset
        y = start[1] + uy * t + py * offset
        points.append((int(x), int(y)))

    points.append(end)
    if len(points) >= 2:
        pygame.draw.lines(surface, color, False, points, 1)


def _draw_dotted_line(
    surface: pygame.Surface,
    color: tuple[int, int, int],
    start: tuple[int, int],
    end: tuple[int, int],
    dot_len: int = 4,
    gap_len: int = 4,
) -> None:
    """Draw a dotted line from *start* to *end*."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return

    ux, uy = dx / length, dy / length
    step = dot_len + gap_len
    t = 0.0
    while t < length:
        t_end = min(t + dot_len, length)
        p1 = (int(start[0] + ux * t), int(start[1] + uy * t))
        p2 = (int(start[0] + ux * t_end), int(start[1] + uy * t_end))
        pygame.draw.line(surface, color, p1, p2, 2)
        t += step
