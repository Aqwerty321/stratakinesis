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
import math
import time
from typing import Callable
import pygame

from strata.config import FIXED_DT, MAX_FRAME_TIME
from strata.core.clock import Clock
from strata.core.collision_groups import CollisionGroups
from strata.core.input_buffer import InputBuffer, StampedEvent
from strata.ecs.world import World
from strata.ecs.entity import Entity
from strata.ecs.components import Physics as _Physics, SoftBody as _SoftBody
from strata.render.camera import Camera
from strata.systems.physics_system import PhysicsSystem, CollisionEvent
from strata.systems.render_system import RenderSystem
from strata.systems.binding_system import BindingSystem
from strata.systems.soft_body_system import SoftBodySystem
from strata.systems.debug_draw import draw_constraints


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
    """World subclass that auto-registers Physics and SoftBody components on entity add.

    The ``physics_system`` and ``soft_body_system`` references are injected by
    Game after construction.
    """

    def __init__(self) -> None:
        super().__init__()
        self._physics_system: "PhysicsSystem | None" = None
        self._soft_body_system: "SoftBodySystem | None" = None

    def _maybe_register(self, entity: Entity) -> None:
        if self._physics_system is not None:
            phys = entity.get_component(_Physics)
            if phys is not None:
                # P1-4: sync pairs are populated inside register() now.
                from strata.ecs.components import Transform
                transform = entity.get_component(Transform)
                self._physics_system.register(phys, entity.id, transform=transform)
        if self._soft_body_system is not None:
            soft = entity.get_component(_SoftBody)
            if soft is not None:
                self._soft_body_system.register(soft, entity.id)

    def add_entity(self, entity: Entity) -> Entity:
        result = super().add_entity(entity)
        self._maybe_register(entity)
        return result

    def add_entities(self, *entities: Entity) -> None:
        for entity in entities:
            super().add_entity(entity)
            self._maybe_register(entity)

    def add_rig(self, rig: "Rig") -> None:  # type: ignore[name-defined]
        """Register all entities in a Rig, then build its constraints.

        This is the single entry point for adding a constrained assembly to the
        scene.  All owned entities are added first (so their physics bodies
        exist), then ``rig._register()`` builds the pymunk constraints.

        Idempotent — calling ``add_rig(rig)`` again for an already-registered
        rig is a no-op (constraints are not duplicated).

        Parameters
        ----------
        rig : any Rig subclass (ChainRig, GearTrainRig, HingeMotorRig, ...).
        """
        for entity in rig._entities:
            # add_entity is idempotent for already-registered entities.
            self.add_entity(entity)
        if self._physics_system is not None:
            rig._register(self._physics_system.space,
                          self._physics_system.static_body)

    def remove_rig(self, rig: "Rig") -> None:  # type: ignore[name-defined]
        """Remove all constraints and entities belonging to a Rig.

        Tears down pymunk constraints first, then removes each entity
        (which cleans up bodies, shapes, and tracking lists).
        """
        if self._physics_system is not None:
            rig._unregister(self._physics_system.space)
        for entity in rig._entities:
            if entity in self._entities:
                self.remove_entity(entity)

    def remove_entity(self, entity: Entity) -> None:
        """Remove an entity from the scene, cleaning up physics and soft-body state."""
        # Unregister rigid-body physics.
        if self._physics_system is not None:
            phys = entity.get_component(_Physics)
            if phys is not None:
                self._physics_system.unregister(phys, entity.id)
                # Remove from sync pairs that reference the entity's Transform.
                from strata.ecs.components import Transform
                transform = entity.get_component(Transform)
                if transform is not None:
                    self._physics_system._sync_pairs = [
                        (b, t) for b, t in self._physics_system._sync_pairs
                        if t is not transform
                    ]
        # Unregister soft-body physics.
        if self._soft_body_system is not None:
            soft = entity.get_component(_SoftBody)
            if soft is not None:
                self._soft_body_system.unregister(soft, entity.id)
        super().remove_entity(entity)


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
    physics_substeps : base number of sub-steps per physics tick (default 1).
                       Soft bodies with stiff springs need >=4 to stay
                       numerically stable at 60 Hz.  With CCD enabled the
                       actual substep count may be higher to prevent tunneling.
    physics_iterations : pymunk solver iterations per step (default 20).
    physics_slop       : collision slop — allowed overlap before correction
                         (default 0.02 world units).
    physics_ccd        : enable swept CCD + adaptive substeps (default True).
    physics_max_substeps : hard cap on adaptive substeps (default 32).
    show_constraints : draw pymunk constraints as coloured debug overlays.
    """

    def __init__(
        self,
        window_size: tuple[int, int] = (1024, 768),
        title: str = "STRATA",
        gravity: tuple[float, float] = (0.0, -9.81),
        max_fps: int = _DEFAULT_MAX_FPS,
        vsync: bool = _DEFAULT_VSYNC,
        show_overlay: bool = False,
        physics_substeps: int = 1,
        physics_iterations: int = 20,
        physics_slop: float = 0.02,
        physics_ccd: bool = True,
        physics_max_substeps: int = 32,
        show_constraints: bool = False,
    ) -> None:
        pygame.init()

        self._window_size = window_size
        self._title = title
        self._max_fps = max_fps
        self._vsync = vsync
        self._show_overlay = show_overlay
        self.show_constraints: bool = show_constraints

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
        self.physics: PhysicsSystem = PhysicsSystem(
            gravity=gravity,
            substeps=physics_substeps,
            iterations=physics_iterations,
            collision_slop=physics_slop,
            ccd=physics_ccd,
            max_substeps=physics_max_substeps,
        )
        self.soft_body: SoftBodySystem = SoftBodySystem(physics_system=self.physics)
        self._render: RenderSystem = RenderSystem()
        self._binding: BindingSystem = BindingSystem()

        # Wire systems into scene so add_entity/add_entities auto-register
        self.scene._physics_system = self.physics
        self.scene._soft_body_system = self.soft_body

        # System order: Physics first (steps pymunk space), then SoftBody
        # (syncs node positions to Transform/Visual), then Binding, then Render.
        self.scene.add_system(self.physics)
        self.scene.add_system(self.soft_body)
        self.scene.add_system(self._binding)
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
        # on_fixed_update: called once per physics step inside the accumulator
        # loop, with the step dt and the list of StampedEvents whose timestamp
        # falls within that step's time window.  Use this for discrete, timing-
        # sensitive input (jump, fire, reverse) instead of on_event.
        self.on_fixed_update: Callable[[float, list[StampedEvent]], None] | None = None
        # on_collision_begin: called after each physics step for every new
        # contact that began in that step.  Receives a CollisionEvent.
        self.on_collision_begin: Callable[[CollisionEvent], None] | None = None
        # on_collision_end: called after each physics step for every contact
        # that separated in that step.  Receives a CollisionEvent.
        self.on_collision_end: Callable[[CollisionEvent], None] | None = None
        # on_draw: called once per rendered frame *after* scene.draw() but
        # *before* the F3 overlay and display.flip().  Receives
        # (surface, camera) so you can do custom pygame / gfxdraw calls.
        self.on_draw: Callable | None = None

        # Named collision groups — shared registry for string-based layer/mask.
        # Usage: game.groups.get("player") or Sprite.circle(..., group="player")
        # Points to the same singleton used by Sprite factory so allocations
        # made via game.groups are visible to Sprite and vice versa.
        from strata.shapes.factory import _collision_groups
        self.groups: CollisionGroups = _collision_groups

        # Input buffer — replaces pygame.event.get() inside run().
        # Access as game.input for key-polling and event history.
        self.input: InputBuffer = InputBuffer()

    # ------------------------------------------------------------------
    # Public single-step method (useful for testing without a window)
    # ------------------------------------------------------------------

    def step(self, dt: float = FIXED_DT) -> None:
        """Advance the world by exactly one fixed step. Does not render."""
        self.scene.update(dt)
        begin_events = self.physics.drain_begin_events()
        end_events = self.physics.drain_end_events()
        if self.on_collision_begin:
            for ev in begin_events:
                self.on_collision_begin(ev)
        if self.on_collision_end:
            for ev in end_events:
                self.on_collision_end(ev)

    # ------------------------------------------------------------------
    # Scene serialisation
    # ------------------------------------------------------------------

    def save_scene(self, path: str) -> None:
        """Serialise the current scene to a JSON file.

        Captures all entity components and physics state so the scene
        can be restored with ``load_scene()``.
        """
        from strata.core.serialise import save_scene
        save_scene(self.scene, self.physics, path)

    def load_scene(self, path: str) -> None:
        """Load a scene from a JSON file, replacing the current scene.

        Clears all existing entities and rebuilds from the saved data.
        Physics bodies, shapes, and constraints are recreated automatically.
        """
        from strata.core.serialise import load_scene
        load_scene(self, path)

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
        # sim_time tracks the monotonic wall-clock base of each physics step.
        # consume() uses it to assign stamped events to the correct sub-step.
        sim_time: float = time.monotonic()

        running = True
        while running:
            # --- Event drain (stamped) ---
            stamped_events = self.input.drain()
            for se in stamped_events:
                event = se.event
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

            # --- Fixed-step physics with per-step event delivery ---
            accumulator += frame_time
            physics_steps_this_frame = 0
            while accumulator >= FIXED_DT:
                step_events = self.input.consume(sim_time, sim_time + FIXED_DT)
                if self.on_fixed_update:
                    self.on_fixed_update(FIXED_DT, step_events)
                self.scene.update(FIXED_DT)
                # Dispatch collision events from this physics step
                begin_events = self.physics.drain_begin_events()
                end_events = self.physics.drain_end_events()
                if self.on_collision_begin:
                    for ev in begin_events:
                        self.on_collision_begin(ev)
                if self.on_collision_end:
                    for ev in end_events:
                        self.on_collision_end(ev)
                accumulator -= FIXED_DT
                sim_time += FIXED_DT
                physics_steps_this_frame += 1
            # Expire events that fell past the last step boundary;
            # keep events timestamped >= sim_time for the next frame.
            self.input.expire(sim_time)

            # --- Render (pass alpha for sub-step interpolation) ---
            alpha = accumulator / FIXED_DT
            self.scene.draw(self._surface, self.camera, alpha)
            if self.on_draw:
                self.on_draw(self._surface, self.camera)

            # --- Constraint debug overlay ---
            if self.show_constraints:
                draw_constraints(self._surface, self.camera, self.physics.space)

            # --- F3 overlay ---
            if self._show_overlay:
                self._draw_overlay(physics_steps_this_frame)

            pygame.display.flip()

        gc.enable()   # restore GC on clean exit
        pygame.quit()

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
        ccd_str = f"on ({self.physics.substeps} sub)" if self.physics._ccd_enabled else "off"
        platform = "WSLg" if _ON_WSL else "native"
        vsync_str = "on" if self._vsync else f"off (cap {self._max_fps or '∞'})"

        lines = [
            f"FPS        {fps:6.1f}",
            f"entities   {entity_count}",
            f"bodies     {body_count}",
            f"phys steps {physics_steps}/frame",
            f"CCD        {ccd_str}",
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
