# strata/core/loop.py
# Game: main entry point.  Owns the window, scene (World), camera, and systems.
#
# Loop contract:
#   - Accumulator-based fixed-step physics (never variable dt).
#   - Frame time clamped to MAX_FRAME_TIME to prevent spiral-of-death.
#   - VIDEORESIZE / RESIZABLE events update the camera scale.
#   - GC is manually managed to eliminate random pause spikes.
#   - F3 toggles a lightweight FPS/physics overlay.

from __future__ import annotations

import gc
import os
import sys
import math
import time
from typing import Callable
import pygame

from strata.config import FIXED_DT, MAX_FRAME_TIME
from strata.core.clock import Clock
from strata.ecs.world import World
from strata.ecs.entity import Entity
from strata.ecs.components import Physics as _Physics
from strata.render.camera import Camera
from strata.systems.physics_system import PhysicsSystem
from strata.systems.render_system import RenderSystem
from strata.systems.rig_system import RigSystem


# ---------------------------------------------------------------------------
# WSLg / WSL detection
# ---------------------------------------------------------------------------

def _is_wsl() -> bool:
    """Return True if running inside WSL (any version)."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


_ON_WSL: bool = _is_wsl()

# WSLg caps its virtual display at 60Hz; vsync=True there locks us to 60Hz
# while also adding compositor latency — counterproductive.  On WSL we
# default to vsync=False and a 240fps cap so interpolation has room to work.
_DEFAULT_VSYNC: bool = not _ON_WSL
_DEFAULT_MAX_FPS: int = 240 if _ON_WSL else 0   # 0 = vsync-controlled on real displays


# ---------------------------------------------------------------------------
# Overlay font (lazy-initialised)
# ---------------------------------------------------------------------------

_overlay_font: pygame.font.Font | None = None

def _get_overlay_font() -> pygame.font.Font:
    global _overlay_font
    if _overlay_font is None:
        _overlay_font = pygame.font.SysFont("monospace", 16)
    return _overlay_font


class Scene(World):
    """World subclass that auto-registers Physics components on entity add.

    The ``physics_system`` reference is injected by Game after construction.
    """

    def __init__(self) -> None:
        super().__init__()
        self._physics_system: "PhysicsSystem | None" = None

    def _maybe_register(self, entity: Entity) -> None:
        if self._physics_system is None:
            return
        phys = entity.get_component(_Physics)
        if phys is not None:
            self._physics_system.register(phys)

    def add_entity(self, entity: Entity) -> Entity:
        result = super().add_entity(entity)
        self._maybe_register(entity)
        return result

    def add_entities(self, *entities: Entity) -> None:
        for entity in entities:
            super().add_entity(entity)
            self._maybe_register(entity)


class Game:
    """
    Top-level engine object.

    Usage::

        game = Game(window_size=(1024, 768))
        ball = Sprite.circle(...)
        game.scene.add_entity(ball)
        game.run()

    Parameters
    ----------
    window_size : initial window dimensions in pixels.
    title       : window caption.
    gravity     : world gravity vector (world units / s²).
    max_fps     : cap real-time frame rate (0 = vsync-controlled or uncapped).
    vsync       : enable vsync.  Defaults to False on WSLg (where it causes
                  extra compositor latency), True on real displays.
    show_overlay: show FPS/physics HUD at startup. Toggle live with F3.
    """

    def __init__(
        self,
        window_size: tuple[int, int] = (1024, 768),
        title: str = "STRATA",
        gravity: tuple[float, float] = (0.0, -9.81),
        max_fps: int = _DEFAULT_MAX_FPS,
        vsync: bool = _DEFAULT_VSYNC,
        show_overlay: bool = False,
    ) -> None:
        pygame.init()

        self._window_size = window_size
        self._title = title
        self._max_fps = max_fps
        self._vsync = vsync
        self._show_overlay = show_overlay

        # Disable automatic GC — we collect manually once per second to avoid
        # random mid-frame pauses that cause perceived stutter.
        gc.disable()
        self._last_gc_time: float = time.monotonic()

        # Build display flags
        flags = pygame.RESIZABLE

        # Attempt vsync; fall back silently if the driver rejects it
        try:
            self._surface = pygame.display.set_mode(window_size, flags, vsync=1 if vsync else 0)
        except pygame.error:
            self._surface = pygame.display.set_mode(window_size, flags)
            self._vsync = False
        pygame.display.set_caption(title)

        self._clock = Clock()
        self.scene: Scene = Scene()
        self.camera: Camera = Camera(window_size)

        # Core systems wired in priority order
        self.physics: PhysicsSystem = PhysicsSystem(gravity=gravity)
        self._render: RenderSystem = RenderSystem()
        self._rig: RigSystem = RigSystem(physics_system=self.physics)

        # Wire physics system into scene so add_entity/add_entities auto-register
        self.scene._physics_system = self.physics

        # System order: Physics first (establishes ground-truth transforms),
        # then Rig (reads fresh transforms for bindings, updates motor rates for
        # next step), then Render.
        self.scene.add_system(self.physics)
        self.scene.add_system(self._rig)
        self.scene.add_system(self._render)

        # User-supplied hooks — assign callables after construction:
        #   game.on_event  = lambda event: ...   # called per pygame event
        #   game.on_update = lambda dt:    ...   # called once per rendered frame
        # on_event  receives the raw pygame.event.Event after the engine has
        #   already handled QUIT / F3 / VIDEORESIZE, so those are safe to ignore.
        # on_update receives frame_time in seconds (raw, before MAX_FRAME_TIME
        #   clamp) — use it for key-polling and any per-frame game logic.
        self.on_event:  Callable[[pygame.event.Event], None] | None = None
        self.on_update: Callable[[float], None] | None = None

    # ------------------------------------------------------------------
    # Public single-step method (useful for testing without a window)
    # ------------------------------------------------------------------

    def step(self, dt: float = FIXED_DT) -> None:
        """Advance the world by exactly one fixed step. Does not render."""
        self.scene.update(dt)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Enter the blocking game loop.  Returns only when the window is closed."""
        print("STRATA")
        print("Engineered with Stratakinesis")
        if _ON_WSL:
            print("[WSL detected] vsync disabled, frame cap:", self._max_fps or "uncapped")

        accumulator: float = 0.0
        physics_steps_this_frame: int = 0

        running = True
        while running:
            # --- Event handling ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_F3:
                        self._show_overlay = not self._show_overlay
                elif event.type == pygame.VIDEORESIZE:
                    new_size = (event.w, event.h)
                    flags = pygame.RESIZABLE
                    try:
                        self._surface = pygame.display.set_mode(
                            new_size, flags, vsync=1 if self._vsync else 0
                        )
                    except pygame.error:
                        self._surface = pygame.display.set_mode(new_size, flags)
                    self.camera.resize(new_size)
                if self.on_event:
                    self.on_event(event)

            # --- Scheduled GC (once per second, between frames) ---
            now = time.monotonic()
            if now - self._last_gc_time >= 1.0:
                gc.collect()
                self._last_gc_time = now

            # --- Timing ---
            frame_time = self._clock.tick(self._max_fps)
            if self.on_update:
                self.on_update(frame_time)
            frame_time = min(frame_time, MAX_FRAME_TIME)  # clamp

            # --- Fixed-step physics ---
            accumulator += frame_time
            physics_steps_this_frame = 0
            while accumulator >= FIXED_DT:
                self.scene.update(FIXED_DT)
                accumulator -= FIXED_DT
                physics_steps_this_frame += 1

            # --- Render (pass alpha for sub-step interpolation) ---
            alpha = accumulator / FIXED_DT
            self.scene.draw(self._surface, self.camera, alpha)

            # --- F3 overlay ---
            if self._show_overlay:
                self._draw_overlay(physics_steps_this_frame)

            pygame.display.flip()

        gc.enable()   # restore GC on clean exit
        pygame.quit()
        sys.exit(0)

    # ------------------------------------------------------------------
    # F3 debug overlay
    # ------------------------------------------------------------------

    def _draw_overlay(self, physics_steps: int) -> None:
        """Draw a minimal top-left HUD: FPS, frame time, physics steps, gravity."""
        font = _get_overlay_font()
        fps = self._clock.fps
        gravity = self.physics.space.gravity
        entity_count = len(self.scene.entities)
        body_count = len(self.physics.space.bodies)
        platform = "WSLg" if _ON_WSL else "native"
        vsync_str = "on" if self._vsync else f"off (cap {self._max_fps or '∞'})"

        lines = [
            f"FPS        {fps:6.1f}",
            f"entities   {entity_count}",
            f"bodies     {body_count}",
            f"phys steps {physics_steps}/frame",
            f"gravity    ({gravity.x:.2f}, {gravity.y:.2f})",
            f"vsync      {vsync_str}",
            f"platform   {platform}",
            f"[F3] hide",
        ]

        pad = 8
        line_h = font.get_linesize()
        box_w = 210
        box_h = len(lines) * line_h + pad * 2
        overlay = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self._surface.blit(overlay, (pad, pad))

        for i, line in enumerate(lines):
            surf = font.render(line, True, (200, 230, 200))
            self._surface.blit(surf, (pad * 2, pad + i * line_h))
