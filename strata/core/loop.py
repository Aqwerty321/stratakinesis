# strata/core/loop.py
# Game: main entry point.  Owns the window, scene (World), camera, and systems.
#
# Loop contract:
#   - Accumulator-based fixed-step physics (never variable dt).
#   - Frame time clamped to MAX_FRAME_TIME to prevent spiral-of-death.
#   - VIDEORESIZE / RESIZABLE events update the camera scale.

from __future__ import annotations

import sys
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
    max_fps     : cap real-time frame rate (0 = uncapped).
    """

    def __init__(
        self,
        window_size: tuple[int, int] = (1024, 768),
        title: str = "STRATA",
        gravity: tuple[float, float] = (0.0, -9.81),
        max_fps: int = 0,
    ) -> None:
        pygame.init()

        self._window_size = window_size
        self._title = title
        self._max_fps = max_fps

        # Surface — resizable window
        self._surface = pygame.display.set_mode(
            window_size,
            pygame.RESIZABLE,
        )
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

        accumulator: float = 0.0

        running = True
        while running:
            # --- Event handling ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    # pygame-ce handles this automatically with RESIZABLE;
                    # we just need to recompute the camera.
                    new_size = (event.w, event.h)
                    self._surface = pygame.display.set_mode(new_size, pygame.RESIZABLE)
                    self.camera.resize(new_size)

            # --- Timing ---
            frame_time = self._clock.tick(self._max_fps)
            frame_time = min(frame_time, MAX_FRAME_TIME)  # clamp

            # --- Fixed-step physics ---
            accumulator += frame_time
            while accumulator >= FIXED_DT:
                self.scene.update(FIXED_DT)
                accumulator -= FIXED_DT

            # --- Render (pass alpha for sub-step interpolation) ---
            alpha = accumulator / FIXED_DT
            self.scene.draw(self._surface, self.camera, alpha)
            pygame.display.flip()

        pygame.quit()
        sys.exit(0)
