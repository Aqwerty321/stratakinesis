# Vision — Stratakinesis / Strata

**Engineered with Stratakinesis** — move things through structure.

This document captures the high-level *why*, the non-negotiable design decisions, and the product/technical vision for the Strata core (v0). Treat it as the project's north star: goals, constraints, and the simplest path that guarantees the engine’s integrity and future growth.

---

## Mission

Make deterministic, physics-driven 2D game systems delightfully simple to use on the surface and deeply composable under the hood.
Strata is for people who want Scratch-like immediacy for prototypes and playgrounds, but who also want real physics, rigging, and predictable systems when they dig deeper.

---

## Why this matters

The ecosystem is saturated with tools that either:

* feel fun but collapse under complex interactions, or
* are powerful but hostile to newcomers.

Strata sits in the sweet spot: a tiny, opinionated core that respects constraints so complexity remains manageable. It’s for creators who want to *engineer* motion, not just fake it.

---

## Core Principles (non-negotiable)

* **Determinism**: Fixed-timestep simulation (`FIXED_DT`) is the only allowed mode for physics. No variable stepping hidden in user examples.
* **Separation of concerns**: World (physics, rigs) ≠ View (camera) ≠ Screen (pixels). World units remain truth.
* **Rig-first**: Rigs are data. Systems operate on rigs. Behavior is composable and inspectable.
* **Minimal surface API**: Defaults should let beginners make something real with 10–30 lines. Advanced control is explicit and opt-in.
* **Visual ≠ Physical**: Visual polygon density is independent from physics shape complexity and collision geometry.
* **Immutable project invariants**: Aspect ratio is a boot-time config. Do not change it during simulation.
* **Small core, big potential**: Start as a library; tooling/SDK (SKSDK) is a later, thin layer on top.

---

## V0 Scope (what success looks like for the first release)

Deliver a clean, well-tested library that demonstrates these points:

* Deterministic main loop (accumulator, clamp)
* World / Entity / Component minimal ECS
* Ordered Systems pipeline
* PhysicsSystem (pymunk-space wrapper, sync transforms)
* RenderSystem (pygame-ce + gfxdraw, camera scale-to-fit)
* Camera with uniform scale-to-fit and world ↔ screen conversions
* Sprite factory (circle, rect) separating VisualShape vs PhysicsShape
* Density-based mass calculation (density × area)
* Rig model + RigSystem (motor + property-binding basics)
* One example: `examples/demo_basic.py` that boots and shows a ball + ground with resizing working (visual only)
* Installable package and clear README

---

## Non-goals for V0

* Editor, full SDK, or heavy CLI tooling
* Runtime-changing world invariants (aspect ratio, fixed timestep)
* Complex UI libraries or heavy-weight debuggers (keep tuner minimal/optional)
* GPU-based physics replacing pymunk
* Networking / deterministic replay across machines (future)

---

## Roadmap (high-level milestones)

* **v0 (core library)** — minimal, deterministic engine described above.
* **v0.x (stability & small features)** — better rig types, simple test suites, basic live tuner (debug overlay), more shape factories.
* **v1 (ecosystem)** — CLI templates, `strata new`, SKSDK thin layer, docs site, tutorials, first community-contributed systems.
* **long-term** — optional renderer backends, plugin system, editor prototypes. Always: keep the core lean.

> Keep the core dependency direction: SDK/tooling depends on Strata, not vice versa.

---

## Audience

* Hobbyists who want meaningful physics without steep architecture debt.
* Educators who want a predictable sandbox for teaching physics and systems.
* Indie devs building 2D games or prototypes that require deterministic behavior.
* Contributors who care about architecture, not just features.

---

## API Philosophy (surface vs depth)

* Surface API must be tiny and friendly:

  * `Game`, `Sprite`, `Scene`, `Camera` as first-class simple types.
  * Defaults do the right thing (e.g., `Sprite.circle(radius=1)` → visible circle + optional physics body).
* Depth is explicit:

  * Advanced users may access `.body` or `.space` but the primary API should not make these necessary.
  * Systems and components are the extensibility surface; encourage adding systems rather than subclassing engine types.

---

## Design constraints & facts to enforce in codegen

* `ASPECT_RATIO` and `WORLD_WIDTH` are read on boot and must not be mutated at runtime.
* `FIXED_DT` is the canonical time-step; `Game.run()` must use accumulator pattern and clamp `frame_time` (e.g., max 0.25s).
* Mouse and input mapping must be handled via `screen_to_world` conversions; clicks outside the viewport are ignored.
* Visual polygon generation (density param) must be cached; do not regenerate vertex arrays every frame.
* Physics mass calculation uses `mass = density * area`. Use pymunk moment helpers for inertia.
* Rigs are declarative objects (data-only). Systems interpret them and create or update physics constraints or property bindings.
* No implicit exposure of pymunk internals in beginner examples; advanced docs show how to access `.body`.

---

## UX: the live tuner (guidelines)

* Optional, hidden by default; toggled via a tiny button or hotkey (e.g., F3).
* Expose only read/write scalars that are safe (gravity, damping, motor speed, camera zoom, timescale optionally).
* Never allow structural changes (no aspect ratio, no reconfiguring timestep).
* Tuner must be implemented as an overlay layer that mutates engine state — it does not become the origin of truth.

---

## Contribution & community norms

* **Small PRs**: prefer focused changes with tests where relevant.
* **Tests required** for any change that affects deterministic behavior, physics stepping, rig behavior.
* **Design-first PR descriptions**: every feature PR must explain how it respects the core principles or why deviation is necessary.
* **No vibecoding**: be explicit about assumptions; don’t accept magic-wrangled AI code without human-reviewed design notes.
* Use MIT license by default. Keep contribution and code-of-conduct simple and enforceable.

---

## Success metrics (qualitative & early quantitative)

* v0 runs: demo boots with stable physics and resizing (visual only).
* README & examples let a new user create a bouncing ball in under 60 seconds (ease).
* Test demonstrating deterministic step consistency (run on two machines, identical logs for same seed).
* Community interest: first 10 stars / first 3 PRs in early weeks is healthy signal (not a target).

---

## Branding & tone

* Public short name: **Strata**
* Full project name: **Stratakinesis**
* Tagline at boot: **Engineered with Stratakinesis**
* Tone: confident, precise, a little nerdy. Be playful in examples but strict in design docs.

---

## Inspirations & design lineage

* Scratch (approachability, good defaults)
* Godot (scene + node thinking, but much lighter)
* Chipmunk / pymunk (physics correctness)
* Minimalist deterministic game runtimes (fixed-step discipline)

---

## Example sprints (what to land first)

1. Core loop + camera + simple spawning API + sample demo.
2. PhysicsSystem + sprite factory with density → mass correctness.
3. RigSystem minimal: motor rig + property-binding for Transform → simple demo of a wheel/motor.
4. RenderSystem polishing: gfxdraw usage, caching, resize handling.
5. Tests and CI (basic unit tests for loop and physics stepping).

---

## Long-form vision (one paragraph)

Stratakinesis is a small engine that refuses to be trendy. It’s not flashy middleware or an AI-generated pile of features. It’s an engineered runtime with clear, opinionated constraints: predictable time, separation of world and view, and declarative rigs that make expressive interactions reliable. Strata should feel approachable at first glance and unbreakably sound when users build anything non-trivial. That tension — simple surface, powerful spine — is the product.

---