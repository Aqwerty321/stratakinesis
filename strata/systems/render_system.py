# strata/systems/render_system.py
# Draws entities using pygame.gfxdraw for anti-aliased polygons.
#
# Visual polygon vertices are cached at entity creation in *local* world-unit
# space; this system transforms them to screen space each frame using the camera.
# The vertex list is NEVER rebuilt per frame.

from __future__ import annotations
import math

import pygame
import pygame.gfxdraw

from strata.systems.base import System
from strata.ecs.components import Visual, Transform
from strata.ecs.world import World
from strata.render.camera import Camera
from strata.config import WORLD_WIDTH, WORLD_HEIGHT


# Background fill colour (letterbox bars + scene background).
_BG_COLOUR = (15, 15, 20)
_WORLD_BG_COLOUR = (25, 25, 35)


class RenderSystem(System):
    """Clears the screen and draws every entity with Visual + Transform."""

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
            transform: Transform = entity.get_component(Transform)
            self._draw_entity(surface, camera, visual, transform, alpha)

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
    ) -> None:
        # Build an interpolated transform for rendering — never mutates the real one
        rx = transform.prev_x + alpha * (transform.x - transform.prev_x)
        ry = transform.prev_y + alpha * (transform.y - transform.prev_y)
        # Angle lerp (simple linear; fine for small-step sizes)
        ra = transform.prev_angle + alpha * (transform.angle - transform.prev_angle)
        if visual.shape_type == "circle":
            self._draw_circle(surface, camera, visual, rx, ry, ra)
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

        # Transform cached local vertices → screen pixels
        screen_pts: list[tuple[int, int]] = []
        for lx, ly in visual.vertices:
            # Rotate around local origin
            rot_x = lx * cos_a - ly * sin_a
            rot_y = lx * sin_a + ly * cos_a
            # Translate to world position then convert to screen
            sx, sy = camera.world_to_screen(rx + rot_x, ry + rot_y)
            screen_pts.append((sx, sy))

        if len(screen_pts) < 3:
            return

        # Cull if all vertices are outside the surface bounds
        w, h = surface.get_size()
        if all(sx < 0 or sx > w or sy < 0 or sy > h for sx, sy in screen_pts):
            return

        color = visual.color[:4] if len(visual.color) == 4 else (*visual.color, 255)
        pygame.gfxdraw.filled_polygon(surface, screen_pts, color)
        if visual.outline is not None:
            outline = visual.outline[:4] if len(visual.outline) == 4 else (*visual.outline, 255)
            pygame.gfxdraw.aapolygon(surface, screen_pts, outline)
