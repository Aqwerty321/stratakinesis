# Vision — Stratakinesis

**Engineered with Stratakinesis** — move things through structure.

This document is the north star. It defines what Strata is *becoming*, not just what it is today.

---

## Mission

Make deterministic, physics-driven 2D game systems as simple to use as Scratch on the surface and as composable as a proper ECS under the hood — then extend that same determinism to networked multiplayer without rewriting anything.

---

## Core Principles (non-negotiable, ever)

| Principle | What it means |
|---|---|
| **Determinism** | Fixed-timestep accumulator is the only physics mode. Same inputs = same simulation, across machines, across sessions. |
| **World ≠ View ≠ Screen** | World units are truth. Camera maps world to screen. Pixels are an output detail. |
| **Rig-first** | Rigs are assembled constraint graphs — data + joint specs. Systems interpret data. Behavior is composable, inspectable, serialisable. |
| **Minimal surface, deep spine** | 10 lines to get a bouncing ball. 100 lines for a motor-driven mechanism. Full ECS access when you need it. |
| **Visual ≠ Physical** | Visual polygon density is independent from collision geometry. `mass = density × area`, always. |
| **Immutable invariants** | Aspect ratio and timestep are boot-time config. Never mutated at runtime. |

---

## Where We Are (v0.4 — current)

Delivered and tested:

- Deterministic fixed-step loop with accumulator + `MAX_FRAME_TIME` clamp
- Minimal ECS: Entity (int ID + component dict), World, Scene, ordered Systems pipeline
- PhysicsSystem — pymunk space, fixed-step substeps, per-body `linear_damping` + `angular_damping`, Transform sync
- SoftBodySystem — spring-mass meshes (structural/shear/bending tiers), pressure, COM correction per substep
- RenderSystem — pygame-ce gfxdraw, anti-aliased filled polygons, render interpolation, viewport culling
- **Rig assembly system** — six production-ready rigs: `PendulumRig`, `ChainRig`, `RopeRig`, `GearTrainRig`, `LeverRig`, `HingeMotorRig`
- Parametric gear tooth rendering — trapezoidal teeth via `gfxdraw`, meshing-correct phase alignment
- `on_draw` hook — custom gfxdraw overlays after scene render, before F3 overlay
- Camera with uniform scale-to-fit, `world_to_screen` / `screen_to_world`
- Timestamped `InputBuffer` with per-physics-step event delivery (`on_fixed_update`)
- Hook API: `on_event`, `on_update`, `on_fixed_update`, `on_draw` — zero subclassing
- WSL/WSLg auto-detection, manual GC scheduling, F3 debug overlay
- **51 Python files · ~8 500 LOC · 251 tests · 7 demos**

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

Dependency direction: SDK → Editor → Plugins → Core → Backend. Never reversed.

---

## Roadmap

### v0.5 — Scene Serialisation & Skeletal Rigs
- **Scene serialisation** — save/load every entity, rig, and constraint to/from JSON. Deserialise back to a running simulation in one call. Unlocks level editors, hot-reload, and replay files.
- **Constraint visualiser** — `game.debug.show_constraints = True` draws every active pymunk constraint as a coloured overlay: pins as circles, springs as zigzags, gear joints as dotted arcs.
- **Skeletal / articulated character rig** — `SkeletonRig` with a bone hierarchy, FK/IK solver, and pose interpolation. Gives you ragdolls, walkers, and procedural animation. Natural extension of `PendulumRig`.
- **Named collision groups** — replace raw bitmasks with `shape.group = "player"` and filter by name.
- **`Sprite.image(path)`** — blit a pygame surface aligned to body Transform. First step toward real asset pipelines.

### v0.6 — Visual Effects & Camera
- **Trail renderer** — store N previous body positions, draw fading line segments behind fast objects.
- **Particle system** — lightweight non-physics point emitters (sparks, dust, debris). Pool-managed, GPU-backed via cupy when available.
- **Screen shake** — `game.camera.shake(magnitude, duration)` — additive camera offset decaying exponentially.
- **Flash / hit feedback** — per-entity color override for N frames.
- **Camera control** — `game.camera.follow(entity, lerp=0.1)`, zoom with scroll, camera rails/zones, cinematic letterbox.

### v0.7 — Audio & Tilemaps
- **Audio system** — positional SFX (panning by world X), BGM with crossfade, `game.audio.play(path, x=...)`. Backed by pygame mixer.
- **Tiled / LDtk importer** — load `.tmx` or LDtk level files; generate static collision shapes from tile layers, entity spawns from object layers.
- **Asset manager** — lazy loading, caching, hot-swap. `game.assets.load("player.png")`.

### v0.8 — Scripting & Hot-Reload
- **Embedded scripting** — Lua or Wren for game logic. `on_fixed_update` and `on_collision` exposed to scripts. No Python knowledge required for game-specific behaviour.
- **Hot-reload** — watch source files with `watchdog`; on change, reload the module, deserialise the current scene state, re-apply it. Simulation continues running; edit code and see the result in under a second.
- **Console / REPL overlay** — `F1` opens an in-game Python REPL (for dev builds). Inspect and mutate the live ECS.

### v1.0 — Rollback Multiplayer
The architecture is already built for this. The missing pieces are mechanical, not architectural:

1. **Snapshot system** — serialise the full pymunk space state (body positions/velocities/angles + joint positions) into a compact byte buffer per step.
2. **History ring buffer** — keep the last N snapshots (N = rollback window, tunable).
3. **RollbackSystem** — on receiving delayed remote input for step K, restore snapshot K and re-simulate forward, calling `on_fixed_update` with corrected inputs.
4. **Input delay configuration** — add N steps of local input delay to give remote inputs time to arrive before they're needed.

```
Frame N arrives with remote input for step K (K < current step):
  1. Restore snapshot at step K
  2. Re-apply local + remote inputs for steps K ..= current via on_fixed_update
  3. Continue forward from corrected state
  4. Misprediction → interpolate visual correction, never snap
```

This is GGPO-style rollback. The `InputBuffer` is already timestamped and per-step. The physics is deterministic. `on_fixed_update` is already the correct hook. The ECS makes snapshots straightforward.

- **Deterministic replay** — record input stream to disk; replay at any speed; overlay a ghost (semi-transparent replay) over a live run for comparison.
- **Client-server and P2P topologies** — peer-to-peer for 2–4 player; authoritative server for larger.

---

## Speculative / Moonshots

These are the ideas that feel impossible until they aren't.

### GPU Particle Systems
1M+ particles simulated each frame in a `cupy` kernel, rendered into a pygame surface via a fast `ndarray → bytes → Surface` blit. Smoke, fire, fluid splashes that actually look like fluid splashes.

### SPH Fluid Simulation
Smoothed-particle hydrodynamics in numpy/cupy. Particles interact via pressure and viscosity forces; the surface is visualised with marching squares rendered via `gfxdraw`. A 2D fluid that sloshes in a container, flows around physics bodies, and drips.

### Procedural Animation Toolkit
Higher-level tools on top of the skeletal rig:
- **Gait planner** — procedural leg placement for walkers (IK + stride length constraints). A spider that steps correctly on uneven terrain.
- **Spring chains** — hair, tails, tentacles, antennae that follow a leader body with lag.
- **Mechanism designer** — assemble linkages (four-bar, slider-crank, escapements, Geneva drives) from a declarative graph spec. The engine computes the joint geometry.

### WASM / Pyodide Deployment
`strata export --target wasm --out dist/` — package a Strata game as a self-contained `.html` file running in the browser via Pyodide + a pygame-ce WASM build. Every demo becomes a shareable link. No install required.

### Visual Scene Editor (`strata-editor`)
An in-engine scene editor that is itself a Strata game:
- Drag-and-drop entity placement with live physics preview
- Property inspector bound to ECS components (click a body, edit density/damping)
- Rig assembly via a node graph — connect joint specs visually
- Play/pause/scrub the simulation with the timeline
- Output: a JSON scene file loadable by the v0.5 serialiser

### Level Procedural Generation
`ProceduralLevel` API for Spelunky-style room graphs and Wave Function Collapse tile placement, outputting a Strata scene. Rooms are typed by their physics constraints (platformer, pendulum puzzle, gear mechanism) and composed into a traversable graph.

### Physics-Based UI
Buttons, sliders, and menus that are actual rigid bodies with joints. Drag a slider and a gear rotates. Close a panel and it flings off with a spring damper. Gravity affects menus. Most useless feature. Very cool.

---

## Multiplayer Architecture (design notes)

Why the engine is already right for rollback:

1. **Fixed timestep** — both peers advance at identical dt. Same inputs → same state guaranteed.
2. **InputBuffer + StampedEvent** — events are already timestamped. For netcode, replace `time.monotonic()` with a monotonic `sim_tick` counter. `consume(tick_start, tick_end)` delivers inputs to the right step.
3. **`on_fixed_update(dt, events)`** — game logic runs per-step with its event slice. Rollback re-invokes the same hook with corrected inputs. No special rollback path in game code.
4. **ECS architecture** — snapshot = serialise all component dicts. Restore = deserialise and re-attach. No hidden mutable state outside ECS (by design constraint).
5. **Determinism** — no `random.random()` without seeded RNG; no float-order-dependent iteration; entity IDs are ints; systems are ordered.

---

## Non-Goals

- **3D** — Strata is 2D. The camera is orthographic. There is no Z axis.
- **Visual scripting in-engine** — the scripting layer (if built) is text-based.
- **Asset store / marketplace** — no ecosystem tax. MIT license.
- **Replacing Godot/Unity** — Strata is a library. The target user codes their game.

---

## Design Constraints (enforced in review)

- `FIXED_DT` is the canonical timestep. No variable stepping.
- Aspect ratio and world dimensions are immutable after boot.
- Visual vertex arrays are cached at entity creation. Never rebuilt per frame.
- `mass = density × area`. pymunk moment helpers compute inertia.
- Rigs are pure data + constraint specs. No simulation logic lives in rig classes.
- Damping is per-body and multiplicative, applied once per fixed step after `space.step()`.
- Input goes through `InputBuffer`. Raw pygame event polling in userland is discouraged.
- Tests required for any change affecting determinism, physics, rigs, or input delivery.

---

## Audience

| Who | Why Strata |
|---|---|
| Hobbyists | Meaningful physics without architecture debt |
| Educators | Predictable sandbox for teaching physics and systems thinking |
| Indie devs | Deterministic 2D games and prototypes, eventually with rollback multiplayer |
| Jam teams | 10-line demo to full game in a weekend; hooks replace boilerplate |
| Contributors | Clean, opinionated architecture to extend — not a monolith to fight |

---

## Long-Form Vision

Stratakinesis is a small engine that refuses to be trendy. It is not flashy middleware or an AI-generated pile of features. It is an engineered runtime with clear, opinionated constraints: predictable time, separation of world and view, and declarative rigs that make expressive interactions reliable.

The engine is already multiplayer-ready by design — deterministic stepping, timestamped input buffering, and ECS snapshots are the foundation for rollback netcode. The gear tooth renderer, soft-body meshes, and per-body damping are evidence that the architecture supports depth without fighting itself.

Strata should feel approachable at first glance and unbreakably sound when users build anything non-trivial. That tension — *simple surface, powerful spine* — is the product.

---

## Inspirations

- **Scratch** — approachability, good defaults
- **Godot** — scene + node thinking, but much lighter
- **pymunk / Chipmunk** — physics correctness
- **GGPO** — rollback netcode architecture
- **Bevy** — ECS done right (Rust, but the philosophy transfers)
- **Glenn Fiedler** — "Fix Your Timestep" (fixed-step discipline)

---

**Engineered with Stratakinesis**

