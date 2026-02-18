# STRATA — Engineered with Stratakinesis

**Strata** is a small, opinionated, deterministic 2D engine library (v0) built as a clean core so AI-assisted tools can generate the boilerplate.
It uses pygame-ce for rendering and pymunk for physics. CuPy is an optional acceleration backend for batch math: CuPy.

This README is intentionally prescriptive — copy it into the repo so your assistant (Claude / Copilot) can produce *exactly* the scaffolding and baseline integrations you need.

---

## Quick pitch / tagline

**Engineered with Stratakinesis**
Deterministic, rigging-first 2D engine core — simple surface, rigorous internals.

---

## Design principles (must-follow)

* **Deterministic fixed-step simulation** (default `fixed_dt = 1/60`). Physics only steps at fixed dt via an accumulator.
* **World units ≠ Screen pixels.** Camera performs uniform scale-to-fit. Aspect ratio is a boot-time config (immutable at runtime).
* **Rigging as first-class data.** Rigs are declarative (data) and executed by RigSystems (logic).
* **Visual detail ≠ Physics detail.** Visual polygons (density) are independent from physics shapes. Density (mass/area) applies to physics only.
* **Tiny, approachable surface API** (Scratch-like defaults). Deep features are opt-in via systems/components.
* **Minimal dependencies.** `pygame-ce`, `pymunk`, `numpy` (or `cupy` if available) only.

---

## v0 scope (what to implement first)

Strict, minimal feature list for V0:

1. Package skeleton + `pyproject.toml`.
2. Simple deterministic main loop with accumulator and clamp.
3. World + Entity + Component minimal ECS (entities = id + component dict).
4. Systems pipeline (ordered by priority).
5. PhysicsSystem: thin wrapper around `pymunk.Space` with `step(fixed_dt)` and entity sync.
6. RenderSystem: uses `pygame-ce` surfaces and `pygame.gfxdraw` for anti-aliased polygons.
7. Camera with uniform scale-to-fit (Option 2 behavior) and conversions `world_to_screen`, `screen_to_world`.
8. Basic shapes: `Sprite.circle()` and `Sprite.rect()` producing VisualShape and PhysicsShape; physics mass computed from `density * area`.
9. Rig data model + RigSystem applying motor and property-binding rigs.
10. One demo `examples/demo_basic.py` that spawns a ball (density visible), a ground, runs the sim with resizable window and scale-to-fit behavior.
11. Optional backend abstraction `backend/array.py` that prefers CuPy (`xp`) then falls back to NumPy.

---

## Non-goals for v0 (do not implement)

* Editor, CLI scaffolding, SDK templates (SKSDK).
* Runtime-changing aspect ratio or timestep.
* Complex UI framework — the live tuner is optional and minimal (single toggle button).
* Networked simulation / replay system.
* Replacing `pymunk` physics with GPU physics.

---

## Project layout (expected by boilerplate generator)

```
strata/
├── pyproject.toml
├── README.md
├── strata/
│   ├── __init__.py
│   ├── config.py            # ASPECT_RATIO, WORLD_WIDTH, FIXED_DT
│   ├── core/
│   │   ├── loop.py          # Game, run(), accumulator
│   │   └── clock.py
│   ├── ecs/
│   │   ├── world.py
│   │   ├── entity.py
│   │   └── components.py
│   ├── systems/
│   │   ├── base.py
│   │   ├── physics_system.py
│   │   ├── render_system.py
│   │   └── rig_system.py
│   ├── backend/
│   │   └── array.py         # xp = cupy|numpy
│   ├── render/
│   │   └── camera.py
│   └── shapes/
│       └── factory.py       # Sprite helpers (circle/rect/polygon)
├── examples/
│   └── demo_basic.py
└── tests/
    └── test_loop.py
```

---

## Minimal public API sketch (what the CLI/AI should generate)

```python
# user code example (v0)
from strata import Game, Sprite

game = Game(window_size=(1024, 768))
ball = Sprite.circle(radius=1.0, x=0.0, y=6.0, density=1.0, physics=True)
ground = Sprite.rect(width=20.0, height=1.0, x=0.0, y=-1.0, static=True)

game.scene.add_entities(ball, ground)
game.run()
```

Notes for generator:

* `radius`, `width`, `height` are in **world units**.
* `density` is mass per unit area; internal code computes `mass = density * area` and calls `pymunk.moment_for_circle`/`moment_for_poly`.
* `physics=True` means create a dynamic `pymunk.Body`; `static=True` creates a static body.

---

## Implementation instructions for Claude / Copilot (actionable tasks)

1. **Create package & deps**

   * `pyproject.toml` with dependencies: `pygame-ce`, `pymunk`, `numpy`.
   * Optional extras: `cupy` in `[project.optional-dependencies]` as `gpu`.

2. **Config**

   * `config.py` defines `ASPECT_RATIO = (16, 9)` (project offers to change at boot) and `WORLD_WIDTH = 16.0`. Compute `WORLD_HEIGHT = WORLD_WIDTH * aspect_h/ aspect_w`. `FIXED_DT = 1/60`.

3. **Backend array**

   * `backend/array.py` tries import `cupy as xp` else `numpy as xp`. Expose `xp` and helpers `to_cpu(x)`.

4. **Core loop**

   * `core/loop.py` implements `Game.run()`:

     * initialize `pygame` and window resizable.
     * main loop: `frame_time = clock.tick(max_fps)/1000.0` clamp to `0.25` → accumulator += frame_time; loop: while accumulator >= FIXED_DT: `scene.update(FIXED_DT)`; accumulator -= FIXED_DT; then `scene.draw()`; handle `VIDEORESIZE` to update viewport; clean polite exit.

5. **ECS**

   * `ecs/entity.py` simple `Entity(id)` with `components` dict and helper `add component`.
   * `ecs/world.py` holds `entities`, `systems`, `rigs`, `add_entity`, `add_system`, `update(dt)`.

6. **Systems**

   * `physics_system.py`: wraps `pymunk.Space`, `space.step(fixed_dt)`, and sync transform component from physics body after step.
   * `render_system.py`: draws `Transform` + `Visual` components using camera conversions; use `pygame.gfxdraw.filled_polygon` and `aapolygon` for outlines.
   * `rig_system.py`: iterate declarative rigs and apply motor creation, property bindings, and simple event bindings.

7. **Camera**

   * `render/camera.py` implements `compute_scale(window_size)`, `world_to_screen`, `screen_to_world`, using uniform `scale = min(window_w / WORLD_WIDTH, window_h / WORLD_HEIGHT)` and center offset.

8. **Shapes / Sprite factory**

   * `shapes/factory.py` create `VisualShape` (dense polygon cache) and `PhysicsShape` (simple convex polygon / circle). Visual density param only affects visual vertices. Physics shape is basic (no user-facing complex poly building for v0).

9. **Example**

   * `examples/demo_basic.py` that spawns a ball and ground, prints boot banner:

     ```
     STRATA
     Engineered with Stratakinesis
     ```
   * Demonstrates window resizing, scale-to-fit, stable physics.

10. **Tests**

    * `tests/test_loop.py` checks that `Game.run_step(dt)` updates world and does not mutate `WORLD_WIDTH/HEIGHT`.

---

## How to run (for README)

```bash
# recommended (for dev)
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pygame-ce pymunk numpy

# run example
python examples/demo_basic.py
```

---

## Developer notes / constraints to enforce in codegen

* **Aspect ratio immutable** after config read.
* **Physics stepping must use accumulator**. No direct `space.step(frame_time)` with variable dt.
* **Do not** expose `pymunk.Space` or `Body` by default in the simple API; advanced users can access `.body` on the sprite to tweak.
* `density` default = `1.0`. Use `math.pi * r * r` for circle area and polygon area via polygon area formula.
* **Cache visual polygon vertices** and transform them for rendering; do not rebuild vertex arrays every frame.
* Keep the first iteration minimal and well-tested; more features come later.

---