# Vision -- Stratakinesis

**Engineered with Stratakinesis** -- move things through structure.

This document is the north star. It defines what Strata is *becoming*, not just what it is today. The engine is past its v0 scaffold; everything below is the destination.

---

## Mission

Make deterministic, physics-driven 2D game systems as simple to use as Scratch on the surface and as composable as a proper ECS under the hood -- then extend that same determinism to networked multiplayer without rewriting the game.

---

## Core Principles (non-negotiable, ever)

| Principle | What it means |
|---|---|
| **Determinism** | Fixed-timestep accumulator is the only physics mode. Same inputs = same outputs, across machines, across sessions. |
| **World != View != Screen** | World units are truth. Camera maps world to screen. Pixels are an output detail. |
| **Rig-first** | Rigs are data. Systems interpret data. Behavior is composable, inspectable, serialisable. |
| **Minimal surface, deep spine** | 10 lines to get a bouncing ball. 100 lines for a motor-driven wheel with input. Full ECS access when you need it. |
| **Visual != Physical** | Visual polygon density is independent from collision geometry. Mass = density x area, always. |
| **Immutable invariants** | Aspect ratio and timestep are boot-time config. Never mutated at runtime. |

---

## Where We Are (v0.1 -- current)

Delivered and tested:

- Deterministic fixed-step loop with accumulator + `MAX_FRAME_TIME` clamp
- Minimal ECS: Entity (int ID + component dict), World, Scene, ordered Systems pipeline
- PhysicsSystem (pymunk space, sync transforms, prev/curr for interpolation)
- RenderSystem (pygame-ce gfxdraw, anti-aliased filled polygons, viewport culling)
- RigSystem v1 (MotorRig with pymunk.SimpleMotor, PropertyBinding for Transform mirroring)
- Camera with uniform scale-to-fit and `world_to_screen` / `screen_to_world`
- Sprite factory (`circle`, `rect`) with density to mass, cached visual vertices
- Render interpolation (sub-step alpha lerp with shortest-path angle)
- Timestamped InputBuffer with per-physics-step event delivery (`on_fixed_update`)
- Hook API: `on_event`, `on_update`, `on_fixed_update` -- zero subclassing needed
- WSL auto-detection, manual GC scheduling, F3 debug overlay
- 78 tests, 2 demos, ~2300 LOC

---

## End-Goal Architecture

```
+----------------------------------------------+
|                    SKSDK                     |  CLI scaffolding, templates,
|              strata new my-game              |  asset pipeline, hot-reload
+----------------------------------------------+
|                  Strata Editor               |  Visual scene editor, rig
|           (optional, depends on SDK)         |  inspector, timeline, live tuner
+----------------------------------------------+
|                 Plugin System                |  Community systems, renderer
|         register_system, register_rig        |  backends, input adapters
+------------+-------------+-------------------+
|  Netcode   |  Scripting  |  Asset Manager    |
|  rollback  |  (Lua/Wren) |  sprite sheets,   |
|  input     |  hot-reload |  tiled maps, audio|
|  predict   |             |                   |
+------------+-------------+-------------------+
|              Strata Core Engine              |
|  ECS . Systems Pipeline . Fixed-Step Loop    |
|  PhysicsSystem . RigSystem . RenderSystem    |
|  InputBuffer . Camera . Sprite Factory       |
|  Config (immutable invariants)               |
+----------------------------------------------+
|           Backend Abstraction                |
|  numpy / cupy (xp) . pymunk . pygame-ce     |
|  (future: wgpu renderer, box2d alt physics)  |
+----------------------------------------------+
```

Dependency direction: SDK -> Editor -> Plugins -> Core -> Backend. Never reversed.

---

## Roadmap

### v0.2 -- Shapes & Collisions
- `Sprite.polygon()` for arbitrary convex shapes
- Collision callbacks / event hooks (on_collision_begin, on_collision_end)
- Collision layers and masks
- Scene management (multiple scenes, scene transitions)
- `Sprite.polygon()` stress-test demo

### v0.3 -- Audio & Assets
- Audio system (positional audio in world-space, SFX + BGM)
- Sprite sheet / texture atlas loading
- Tiled map importer (TMX)
- Basic asset manager with lazy loading and caching

### v0.4 -- Advanced Rigs & Constraints
- SpringRig, HingeRig, SliderRig, PivotRig
- Rig composition (chain multiple rigs on one entity)
- Constraint visualiser in debug overlay
- Rig serialisation (JSON export/import)

### v0.5 -- Scripting & Hot-Reload
- Embedded Lua or Wren scripting for game logic
- Hot-reload: script changes apply without restarting
- Script <-> ECS bridge (spawn, query, mutate from scripts)
- Console / REPL overlay (F1)

### v1.0 -- Multiplayer & Netcode
- Deterministic replay: record + playback input streams
- Rollback netcode (GGPO-style):
  - InputBuffer already timestamps events with monotonic clock
  - Swap `time.monotonic()` for deterministic sim-tick counter
  - Snapshot/restore world state for rollback
  - Input prediction + re-simulation on correction
- Client-server and peer-to-peer topologies
- Network lobby, matchmaking primitives
- Lag compensation and input delay configuration

### v1.x -- Plugin System & Ecosystem
- `register_system()` / `register_rig()` plugin API
- Community system marketplace
- Alternative renderer backends (wgpu, headless for server-side sim)
- Alternative physics backends (Box2D, custom)
- CI templates, GitHub Actions, automated benchmarking

### v2.0 -- SKSDK & Editor
- `strata new my-game` CLI scaffolding
- Visual scene editor (entity placement, rig inspector, timeline)
- Live tuner (drag sliders for gravity, motor speed, damping -- already prototyped as F3 overlay)
- Asset pipeline (import, compress, pack)
- Export to web (pyodide / wasm target)

---

## Multiplayer Architecture (design notes)

The engine is already built for this. Key decisions that pay off:

1. **Fixed timestep** -- both peers step at identical dt; same inputs = same state.
2. **InputBuffer + StampedEvent** -- events are already timestamped. For netcode, replace `time.monotonic()` with a `sim_tick` counter. `consume(tick_start, tick_end)` delivers inputs to the correct step.
3. **on_fixed_update(dt, events)** -- game logic already runs per-step with its event slice. Rollback re-invokes the same hook with corrected inputs.
4. **ECS architecture** -- snapshot = serialize all component dicts. Restore = deserialize and re-attach. No hidden mutable state outside ECS.
5. **Determinism** -- no `random.random()` without seeded RNG; no float-order-dependent iteration (entity IDs are ints, systems are ordered).

Rollback flow:
```
Frame N arrives with remote input for step K (K < current step):
  1. Restore snapshot at step K
  2. Re-apply local + remote inputs for steps K..current via on_fixed_update
  3. Continue forward from corrected state
  4. Misprediction -> visual correction (interpolate, don't snap)
```

---

## Audience

| Who | Why Strata |
|---|---|
| Hobbyists | Meaningful physics without architecture debt |
| Educators | Predictable sandbox for teaching physics, ECS, and systems thinking |
| Indie devs | Deterministic 2D games & prototypes, eventually with rollback multiplayer |
| Jam teams | 10-line demo to full game in a weekend; hooks replace boilerplate |
| Contributors | Clean architecture to extend, not a monolith to fight |

---

## API Philosophy

**Surface (what beginners see):**
```python
from strata import Game, Sprite

game = Game()
ball = Sprite.circle(radius=1.0, y=5.0, density=1.0, physics=True)
ground = Sprite.rect(width=20.0, height=1.0, y=-1.0, static=True)
game.scene.add_entities(ball, ground)
game.run()
```

**Depth (what power users access):**
```python
# Per-step input delivery
game.on_fixed_update = lambda dt, events: handle_inputs(events)

# Direct pymunk access
ball_body = ball.get_component(Physics).body
ball_body.apply_impulse_at_local_point((0, 500))

# Custom systems
class GravityFlipSystem(System):
    def update(self, world, dt):
        if flip_requested:
            world.physics.space.gravity = (0, 9.81)
```

Advanced access is explicit and opt-in. The primary API never requires it.

---

## Design Constraints (enforced in codegen and review)

- `FIXED_DT` is the canonical timestep. No variable stepping. Period.
- Aspect ratio immutable after boot.
- Visual vertex arrays are cached at creation. Never rebuilt per frame.
- `mass = density * area`. Use pymunk moment helpers for inertia.
- Rigs are data-only. Systems interpret them. No logic in components.
- No implicit pymunk exposure in beginner examples.
- Input mapping goes through `InputBuffer` / `screen_to_world`. Raw pygame calls are discouraged in userland.
- All hook callbacks are optional and assignable -- no subclassing required.
- Tests required for any change affecting determinism, physics, rigs, or input delivery.

---

## Contribution & Community Norms

- **Small PRs**: focused changes with tests.
- **Tests required** for determinism, physics, rigs, input delivery.
- **Design-first PR descriptions**: explain how changes respect core principles.
- **No vibecoding**: explicit assumptions, human-reviewed design notes.
- MIT license. Simple, enforceable code of conduct.

---

## Branding

| | |
|---|---|
| Engine name | **Strata** |
| Project name | **Stratakinesis** |
| Boot banner | `STRATA` / `Engineered with Stratakinesis` |
| Tone | Confident, precise, a little nerdy. Playful in examples, strict in design. |

---

## Inspirations

- **Scratch** -- approachability, good defaults
- **Godot** -- scene + node thinking, but much lighter
- **pymunk / Chipmunk** -- physics correctness
- **GGPO** -- rollback netcode architecture
- **Bevy** -- ECS done right (Rust, but the philosophy transfers)
- **Glenn Fiedler** -- "Fix Your Timestep" (fixed-step discipline)

---

## Long-Form Vision

Stratakinesis is a small engine that refuses to be trendy. It is not flashy middleware or an AI-generated pile of features. It is an engineered runtime with clear, opinionated constraints: predictable time, separation of world and view, and declarative rigs that make expressive interactions reliable. The engine is already multiplayer-ready by design -- deterministic stepping, timestamped input buffering, and ECS snapshots are the foundation for rollback netcode. Strata should feel approachable at first glance and unbreakably sound when users build anything non-trivial. That tension -- simple surface, powerful spine -- is the product.

---
