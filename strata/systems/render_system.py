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
from strata.backend.array import xp
from strata.config import WORLD_WIDTH, WORLD_HEIGHT

# P-OPT-13: Use numpy directly for render-path arrays to avoid GPU↔CPU sync.
import numpy as np


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
        # P-OPT-7: Cache surface dimensions once per frame.
        surf_w, surf_h = surface.get_size()
        for entity in world.get_entities_with(Visual, Transform):
            visual: Visual = entity.get_component(Visual)
            if visual.hidden:
                continue
            transform: Transform = entity.get_component(Transform)
            self._draw_entity(surface, camera, visual, transform, alpha, entity, surf_w, surf_h)

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
        surf_w: int = 0,
        surf_h: int = 0,
    ) -> None:
        # Build an interpolated transform for rendering — never mutates the real one
        rx = transform.prev_x + alpha * (transform.x - transform.prev_x)
        ry = transform.prev_y + alpha * (transform.y - transform.prev_y)
        # Shortest-path angle lerp to avoid ±π wrap artifacts
        ra = _lerp_angle(transform.prev_angle, transform.angle, alpha)
        if visual.shape_type == "circle":
            self._draw_circle(surface, camera, visual, rx, ry, ra, surf_w, surf_h)
        elif visual.shape_type == "image":
            self._draw_image(surface, camera, visual, rx, ry, ra, surf_w, surf_h)
        elif visual.shape_type == "soft_polygon":
            soft = entity.get_component(SoftBody) if entity is not None else None
            if soft is not None and soft.debug_render:
                self._draw_soft_debug(surface, camera, soft, rx, ry)
            else:
                self._draw_soft_polygon(surface, camera, visual, rx, ry, surf_w, surf_h)
        else:
            self._draw_polygon(surface, camera, visual, rx, ry, ra, surf_w, surf_h)

    def _draw_circle(
        self,
        surface: pygame.Surface,
        camera: Camera,
        visual: Visual,
        rx: float,
        ry: float,
        ra: float,
        surf_w: int = 0,
        surf_h: int = 0,
    ) -> None:
        cx, cy = camera.world_to_screen(rx, ry)
        r = camera.scale_length(visual.radius)

        # P-OPT-7: Use pre-computed surface dimensions for culling.
        w, h = surf_w, surf_h
        if w == 0:
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
        surf_w: int = 0,
        surf_h: int = 0,
    ) -> None:
        if not visual.vertices:
            return

        # P-OPT-8: Screen-space vertex cache — skip rotation + w2s when the
        # entity transform and camera haven't changed (benefits static geometry).
        cache_key = (rx, ry, ra, camera.scale, camera.offset_x, camera.offset_y)
        cached = getattr(visual, '_screen_cache_key', None)
        if cached == cache_key:
            buf = visual._screen_cache_buf
        else:
            cos_a = math.cos(ra)
            sin_a = math.sin(ra)

            # P0-3: Batch rotation + world_to_screen via numpy.
            verts = visual._verts_arr
            if verts is None:
                verts = np.array(visual.vertices, dtype=np.float64)
                visual._verts_arr = verts
            else:
                # P-OPT-13: Ensure numpy (not cupy) for render path.
                verts = np.asarray(verts)

            # P-OPT-6: Direct scalar rotation — avoids allocating a 2×2 rotation
            # matrix per entity per frame.  Uses in-place buffer to eliminate
            # the matrix multiply allocation as well.
            if not hasattr(visual, '_world_buf') or visual._world_buf.shape[0] != verts.shape[0]:
                visual._world_buf = np.empty((verts.shape[0], 2), dtype=np.float64)
            world = visual._world_buf
            vx = verts[:, 0]
            vy = verts[:, 1]
            world[:, 0] = vx * cos_a - vy * sin_a + rx
            world[:, 1] = vx * sin_a + vy * cos_a + ry
            screen = camera.world_to_screen_batch(world)  # (V, 2) int32
            buf = screen.tolist()
            # Store in cache.
            visual._screen_cache_key = cache_key
            visual._screen_cache_buf = buf

        if len(buf) < 3:
            return

        # Cull if all vertices are outside the surface bounds
        # P-OPT-7: Use pre-computed surface dimensions.
        w, h = surf_w, surf_h
        if w == 0:
            w, h = surface.get_size()
        if all(sx < 0 or sx > w or sy < 0 or sy > h for sx, sy in buf):
            return

        # color and outline are guaranteed 4-tuples (normalised in Visual.__post_init__)
        pygame.gfxdraw.filled_polygon(surface, buf, visual.color)
        if visual.outline is not None:
            pygame.gfxdraw.aapolygon(surface, buf, visual.outline)

    def _draw_image(
        self,
        surface: pygame.Surface,
        camera: Camera,
        visual: Visual,
        rx: float,
        ry: float,
        ra: float,
        surf_w: int = 0,
        surf_h: int = 0,
    ) -> None:
        """Blit an image surface aligned to the entity's Transform."""
        if visual.image_surface is None:
            return

        # Scale the original image to the correct world-unit size in pixels.
        pw = max(1, int(visual.image_width * camera.scale))
        ph = max(1, int(visual.image_height * camera.scale))

        # Cache the scaled surface (keyed by pixel dimensions).
        cached = getattr(visual, '_cached_image', None)
        cached_size = getattr(visual, '_cached_image_size', (0, 0))
        if cached is None or cached_size != (pw, ph):
            cached = pygame.transform.smoothscale(visual.image_surface, (pw, ph))
            visual._cached_image = cached
            visual._cached_image_size = (pw, ph)

        # Rotate (pygame rotates CCW, pymunk angles are CCW-positive, so negate).
        # P-OPT-9: Quantize to 1° buckets and cache rotated surfaces.  Most
        # sprites change angle smoothly; 1° granularity is imperceptible but
        # avoids calling pygame.transform.rotate 180×/frame at 180 sprites.
        angle_deg = -math.degrees(ra)
        quantized = round(angle_deg) % 360

        rot_cache = getattr(visual, '_rot_cache', None)
        rot_cache_key = getattr(visual, '_rot_cache_key', None)
        if rot_cache is not None and rot_cache_key == (quantized, pw, ph):
            rotated = rot_cache
        else:
            rotated = pygame.transform.rotate(cached, angle_deg)
            visual._rot_cache = rotated
            visual._rot_cache_key = (quantized, pw, ph)

        # Position: centre of the rotated surface at the screen coordinates.
        cx, cy = camera.world_to_screen(rx, ry)
        rect = rotated.get_rect(center=(cx, cy))

        # Cull
        # P-OPT-7: Use pre-computed surface dimensions.
        w, h = surf_w, surf_h
        if w == 0:
            w, h = surface.get_size()
        if rect.right < 0 or rect.left > w or rect.bottom < 0 or rect.top > h:
            return

        surface.blit(rotated, rect)

    def _draw_soft_polygon(
        self,
        surface: pygame.Surface,
        camera: Camera,
        visual: Visual,
        rx: float,
        ry: float,
        surf_w: int = 0,
        surf_h: int = 0,
    ) -> None:
        """Draw soft body mesh — vertices are centroid-relative, no rotation."""
        if not visual.vertices or len(visual.vertices) < 3:
            return

        # P-OPT-2: _verts_arr is now kept canonical by SoftBodySystem —
        # no need to rebuild from visual.vertices each frame.
        verts = visual._verts_arr
        if verts is None:
            verts = np.array(visual.vertices, dtype=np.float64)
            visual._verts_arr = verts
        else:
            # P-OPT-13: Ensure numpy for render path.
            verts = np.asarray(verts)
        # Offset to world position (centroid) — use pre-allocated buffer
        # to avoid .copy() allocation every frame.
        if not hasattr(visual, '_soft_world_buf') or visual._soft_world_buf.shape[0] != verts.shape[0]:
            visual._soft_world_buf = np.empty((verts.shape[0], 2), dtype=np.float64)
        world = visual._soft_world_buf
        world[:, 0] = verts[:, 0] + rx
        world[:, 1] = verts[:, 1] + ry
        screen = camera.world_to_screen_batch(world)  # (V, 2) int32
        buf = screen.tolist()

        # Cull if entirely off-screen
        # P-OPT-7: Use pre-computed surface dimensions.
        w, h = surf_w, surf_h
        if w == 0:
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
        spring_rgb = spring_color[:3]
        node_rgb = node_color[:3]

        # P1-5: Batch-transform all spring endpoints and nodes in two numpy calls.
        n_springs = len(soft.springs)
        n_nodes = len(soft.nodes)
        if n_nodes == 0:
            return

        # Collect spring endpoints as (N_springs, 4) [ax, ay, bx, by]
        if n_springs > 0:
            endpoints = np.empty((n_springs, 4), dtype=np.float64)
            for i, spring in enumerate(soft.springs):
                ap = spring.a.position
                bp = spring.b.position
                endpoints[i, 0] = ap.x
                endpoints[i, 1] = ap.y
                endpoints[i, 2] = bp.x
                endpoints[i, 3] = bp.y
            a_screen = camera.world_to_screen_batch(endpoints[:, :2]).tolist()
            b_screen = camera.world_to_screen_batch(endpoints[:, 2:]).tolist()
            draw_line = pygame.draw.line
            for i in range(n_springs):
                draw_line(surface, spring_rgb, a_screen[i], b_screen[i], 1)

        # Batch-transform node positions
        node_pos = np.empty((n_nodes, 2), dtype=np.float64)
        for i, body in enumerate(soft.nodes):
            node_pos[i, 0] = body.position.x
            node_pos[i, 1] = body.position.y
        node_screen = camera.world_to_screen_batch(node_pos).tolist()

        r = max(2, camera.scale_length(soft.node_radius))
        filled_circle = pygame.gfxdraw.filled_circle
        aacircle = pygame.gfxdraw.aacircle
        for cx, cy in node_screen:
            filled_circle(surface, cx, cy, r, node_color)
            aacircle(surface, cx, cy, r, node_rgb)
