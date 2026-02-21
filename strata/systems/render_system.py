# strata/systems/render_system.py
# Draws entities using pygame.gfxdraw for anti-aliased polygons.
#
# Visual polygon vertices are cached at entity creation in *local* world-unit
# space; this system transforms them to screen space each frame using the camera.
# For soft bodies (shape_type="soft_polygon"), vertices are rebuilt every step
# by SoftBodySystem and drawn without rotation.

from __future__ import annotations
import math

import pygame
import pygame.gfxdraw

from strata.systems.base import System
from strata.ecs.components import Visual, Transform, SoftBody
from strata.ecs.world import World
from strata.render.camera import Camera
from strata.config import WORLD_WIDTH, WORLD_HEIGHT


# Background fill colour (letterbox bars + scene background).
_BG_COLOUR = (15, 15, 20)
_WORLD_BG_COLOUR = (25, 25, 35)


def _lerp_angle(prev: float, curr: float, alpha: float) -> float:
    """Shortest-path lerp between two angles (radians).

    Handles the ±π wrap-around so a body crossing the boundary doesn't
    produce a single-frame reverse-spin artifact.
    """
    delta = (curr - prev + math.pi) % (2.0 * math.pi) - math.pi
    return prev + alpha * delta


class RenderSystem(System):
    """Clears the screen and draws every entity with Visual + Transform."""

    def __init__(self) -> None:
        # Pre-allocated screen-point buffer reused across all polygon draw calls.
        # Avoids allocating a new list + N tuples every frame per entity.
        self._pts_buffer: list[tuple[int, int]] = []

    def update(self, world: World, dt: float) -> None:
        # RenderSystem has nothing to do during physics steps.
        pass

    def draw(self, world: World, surface: pygame.Surface, camera: Camera, alpha: float = 1.0) -> None:
        """Clear screen then draw all visual entities.

        Parameters
        ----------
        alpha : interpolation factor in [0, 1].  0 = previous physics state,
                1 = current physics state.  Pass ``accumulator / FIXED_DT``
                from the game loop for smooth sub-step rendering.
        """
        # Fill entire window (letterbox colour)
        surface.fill(_BG_COLOUR)

        # Draw world background rectangle
        world_rect = pygame.Rect(
            int(camera.offset_x),
            int(camera.offset_y),
            int(camera.scale * WORLD_WIDTH),
            int(camera.scale * WORLD_HEIGHT),
        )
        pygame.draw.rect(surface, _WORLD_BG_COLOUR, world_rect)

        # Draw each entity
        for entity in world.get_entities_with(Visual, Transform):
            visual: Visual = entity.get_component(Visual)
            if visual.hidden:
                continue
            transform: Transform = entity.get_component(Transform)
            self._draw_entity(surface, camera, visual, transform, alpha, entity)

    # ------------------------------------------------------------------
    # Internal drawing helpers
    # ------------------------------------------------------------------

    def _draw_entity(
        self,
        surface: pygame.Surface,
        camera: Camera,
        visual: Visual,
        transform: Transform,
        alpha: float = 1.0,
        entity=None,
    ) -> None:
        # Build an interpolated transform for rendering — never mutates the real one
        rx = transform.prev_x + alpha * (transform.x - transform.prev_x)
        ry = transform.prev_y + alpha * (transform.y - transform.prev_y)
        # Shortest-path angle lerp to avoid ±π wrap artifacts
        ra = _lerp_angle(transform.prev_angle, transform.angle, alpha)
        if visual.shape_type == "circle":
            self._draw_circle(surface, camera, visual, rx, ry, ra)
        elif visual.shape_type == "soft_polygon":
            soft = entity.get_component(SoftBody) if entity is not None else None
            if soft is not None and soft.debug_render:
                self._draw_soft_debug(surface, camera, soft, rx, ry)
            else:
                self._draw_soft_polygon(surface, camera, visual, rx, ry)
        else:
            self._draw_polygon(surface, camera, visual, rx, ry, ra)

    def _draw_circle(
        self,
        surface: pygame.Surface,
        camera: Camera,
        visual: Visual,
        rx: float,
        ry: float,
        ra: float,
    ) -> None:
        cx, cy = camera.world_to_screen(rx, ry)
        r = camera.scale_length(visual.radius)

        # Cull entities entirely outside the surface (prevents short overflow)
        w, h = surface.get_size()
        if cx + r < 0 or cx - r > w or cy + r < 0 or cy - r > h:
            return

        # Filled circle
        color = visual.color[:3]  # gfxdraw takes RGB or RGBA
        pygame.gfxdraw.filled_circle(surface, cx, cy, r, color)
        # Anti-aliased outline
        if visual.outline is not None:
            pygame.gfxdraw.aacircle(surface, cx, cy, r, visual.outline[:3])

    def _draw_polygon(
        self,
        surface: pygame.Surface,
        camera: Camera,
        visual: Visual,
        rx: float,
        ry: float,
        ra: float,
    ) -> None:
        if not visual.vertices:
            return

        cos_a = math.cos(ra)
        sin_a = math.sin(ra)

        # Reuse the shared buffer — avoids a new list allocation per polygon.
        buf = self._pts_buffer
        buf.clear()
        for lx, ly in visual.vertices:
            rot_x = lx * cos_a - ly * sin_a
            rot_y = lx * sin_a + ly * cos_a
            sx, sy = camera.world_to_screen(rx + rot_x, ry + rot_y)
            buf.append((sx, sy))

        if len(buf) < 3:
            return

        # Cull if all vertices are outside the surface bounds
        w, h = surface.get_size()
        if all(sx < 0 or sx > w or sy < 0 or sy > h for sx, sy in buf):
            return

        # color and outline are guaranteed 4-tuples (normalised in Visual.__post_init__)
        pygame.gfxdraw.filled_polygon(surface, buf, visual.color)
        if visual.outline is not None:
            pygame.gfxdraw.aapolygon(surface, buf, visual.outline)

    def _draw_soft_polygon(
        self,
        surface: pygame.Surface,
        camera: Camera,
        visual: Visual,
        rx: float,
        ry: float,
    ) -> None:
        """Draw soft body mesh — vertices are centroid-relative, no rotation."""
        if not visual.vertices or len(visual.vertices) < 3:
            return

        # Reuse the shared buffer — avoids a new list allocation per polygon.
        buf = self._pts_buffer
        buf.clear()
        for lx, ly in visual.vertices:
            sx, sy = camera.world_to_screen(rx + lx, ry + ly)
            buf.append((sx, sy))

        # Cull if entirely off-screen
        w, h = surface.get_size()
        if all(sx < 0 or sx > w or sy < 0 or sy > h for sx, sy in buf):
            return

        pygame.gfxdraw.filled_polygon(surface, buf, visual.color)
        if visual.outline is not None:
            pygame.gfxdraw.aapolygon(surface, buf, visual.outline)

    def _draw_soft_debug(
        self,
        surface: pygame.Surface,
        camera: Camera,
        soft: SoftBody,
        rx: float,
        ry: float,
    ) -> None:
        """Debug render: draw each node as a small circle and each spring as a line."""
        node_color = (100, 255, 100, 200)
        spring_color = (200, 200, 100, 140)

        # Draw springs first (underneath nodes)
        for spring in soft.springs:
            a_pos = spring.a.position
            b_pos = spring.b.position
            ax, ay = camera.world_to_screen(a_pos.x, a_pos.y)
            bx, by = camera.world_to_screen(b_pos.x, b_pos.y)
            pygame.draw.line(surface, spring_color[:3], (ax, ay), (bx, by), 1)

        # Draw nodes
        r = max(2, camera.scale_length(soft.node_radius))
        for body in soft.nodes:
            cx, cy = camera.world_to_screen(body.position.x, body.position.y)
            pygame.gfxdraw.filled_circle(surface, cx, cy, r, node_color)
            pygame.gfxdraw.aacircle(surface, cx, cy, r, node_color[:3])
