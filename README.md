# STRATA -- Engineered with Stratakinesis

**Strata** is a deterministic, rigging-first 2D engine library for Python.
It uses pygame-ce for rendering, pymunk for physics, and numpy (or cupy) for batch math.

```
STRATA
Engineered with Stratakinesis
```

---

## What it does

- **Deterministic physics** -- fixed-timestep accumulator, never variable dt. Same inputs = same outputs.
- **Minimal ECS** -- Entity (int ID + component dict), World/Scene, ordered Systems pipeline.
- **Rig-first design** -- MotorRig, PropertyBinding, and more rigs coming. Behavior is data; systems interpret it.
- **Render interpolation** -- sub-step alpha lerp with shortest-path angle interpolation. No jitter at any frame rate.
- **Timestamped input buffer** -- events are stamped with `time.monotonic()` and delivered to the exact physics step they belong to via `on_fixed_update`.
- **Hook API** -- `on_event`, `on_update`, `on_fixed_update`. Zero subclassing. Assign a function and go.
- **F3 debug overlay** -- FPS, entity count, physics steps, gravity, vsync status, platform detection.
- **WSL-aware** -- auto-detects WSLg, disables vsync (which adds compositor latency there), caps at 240fps.

---

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[gpu]"   # or just: pip install -e .

python examples/demo_basic.py
python examples/demo_motor.py
```

---

## 10-line bouncing ball

```python
from strata import Game, Sprite

game = Game(window_size=(1024, 768))
ball = Sprite.circle(radius=1.0, x=0.0, y=5.0, density=1.0, physics=True)
ground = Sprite.rect(width=20.0, height=1.0, x=0.0, y=-1.0, static=True)

game.scene.add_entities(ball, ground)
game.run()
```

All values are in **world units** (16x9 default viewport). The camera handles scale-to-fit. Window is resizable.

---

## Motor-driven wheel with input

```python
import pygame
from strata import Game, Sprite
from strata.ecs.components import MotorRig, Physics
from strata.core.input_buffer import StampedEvent

game = Game(window_size=(1024, 768), title="Motor Demo")

ground = Sprite.rect(width=20.0, height=0.5, y=-3.5, static=True)
wheel  = Sprite.circle(radius=0.8, x=-5.0, y=-2.0, density=1.0, physics=True)
wheel.get_component(Physics).shape.friction = 2.0
wheel.add_component(MotorRig(target_rate=8.0, max_force=5e5))

game.scene.add_entities(ground, wheel)

rig = wheel.get_component(MotorRig)

def on_fixed_update(dt: float, events: list[StampedEvent]) -> None:
    for se in events:
        if se.event.type == pygame.KEYDOWN and se.event.key == pygame.K_SPACE:
            rig.target_rate *= -1.0

def on_update(dt: float) -> None:
    keys = game.input.poll_keys()
    if keys[pygame.K_RIGHT]: rig.target_rate = min(rig.target_rate + 0.1, 20.0)
    if keys[pygame.K_LEFT]:  rig.target_rate = max(rig.target_rate - 0.1, -20.0)

game.on_fixed_update = on_fixed_update
game.on_update = on_update
game.run()
```

`on_fixed_update` fires once per physics step with timestamped events. `on_update` fires once per render frame for continuous key polling. No raw game loop needed.

---

## Hook API

| Hook | When it fires | Use for |
|---|---|---|
| `game.on_event(event)` | Once per pygame event, after built-in handling (QUIT/ESC/F3/VIDEORESIZE already processed) | UI clicks, menu toggles, non-physics events |
| `game.on_update(dt)` | Once per render frame, with raw frame_time before clamp | Continuous key polling, HUD updates, camera control |
| `game.on_fixed_update(dt, events)` | Once per physics step inside the accumulator, with that step's `StampedEvent` slice | Discrete input (jump, fire, reverse), physics-affecting logic |

All hooks are optional. Assign a callable or leave as `None`.

---

## Architecture

```
strata/
  __init__.py          # exports: Game, Sprite, InputBuffer, StampedEvent
  config.py            # ASPECT_RATIO, WORLD_WIDTH/HEIGHT, FIXED_DT, MAX_FRAME_TIME
  backend/
    array.py           # xp = cupy | numpy
  core/
    clock.py           # Clock with tick() and fps
    input_buffer.py    # StampedEvent, InputBuffer (drain/consume/clear/poll_keys)
    loop.py            # Game, Scene, run loop, hooks, F3 overlay
  ecs/
    entity.py          # Entity (int ID + component dict)
    components.py      # Transform, Physics, Visual, MotorRig, PropertyBinding
    world.py           # World (entity registry + systems), update/draw
  systems/
    base.py            # System base class
    physics_system.py  # pymunk.Space wrapper, fixed-step, transform sync
    render_system.py   # pygame-ce gfxdraw, interpolation, viewport culling
    rig_system.py      # MotorRig execution, PropertyBinding mirroring
  render/
    camera.py          # Scale-to-fit, world_to_screen, screen_to_world
  shapes/
    factory.py         # Sprite.circle(), Sprite.rect(), density -> mass
examples/
  demo_basic.py        # Ball + ground
  demo_motor.py        # Motor wheel + arrow keys + PropertyBinding follower
tests/
  test_loop.py         # Accumulator determinism, hooks
  test_ecs.py          # Entity/World/Scene CRUD
  test_camera.py       # Scale-to-fit, conversions, angle lerp
  test_physics.py      # Gravity, sync, density -> mass
  test_rig_system.py   # MotorRig, PropertyBinding, RigSystem
  test_input_buffer.py # Drain, consume, clear, per-step delivery
```

21 Python files. ~2300 LOC. 78 tests.

---

## Systems pipeline

Systems run in this order every fixed step:

1. **PhysicsSystem** -- `space.step(FIXED_DT)`, then syncs pymunk body positions/angles to `Transform` components (snapshots `prev_*` before overwrite for interpolation)
2. **RigSystem** -- creates/updates pymunk constraints for MotorRigs, mirrors Transform attributes via PropertyBindings (reads fresh post-physics transforms)
3. **RenderSystem** -- draws entities using interpolated positions (`alpha = accumulator / FIXED_DT`) with shortest-path angle lerp and viewport culling

---

## Config

| Constant | Default | Meaning |
|---|---|---|
| `ASPECT_RATIO` | `(16, 9)` | Boot-time only. Immutable. |
| `WORLD_WIDTH` | `16.0` | World units across viewport |
| `WORLD_HEIGHT` | `9.0` | Derived from aspect ratio |
| `FIXED_DT` | `1/60` | Physics timestep (seconds) |
| `MAX_FRAME_TIME` | `0.25` | Spiral-of-death clamp |

---

## Controls (built-in)

| Key | Action |
|---|---|
| ESC | Quit |
| F3 | Toggle debug overlay |

---

## Design constraints

- `FIXED_DT` is the only physics timestep. No variable stepping.
- Aspect ratio and world dimensions are immutable after boot.
- Visual vertex arrays are cached at entity creation. Never rebuilt per frame.
- `mass = density * area`. pymunk moment helpers compute inertia.
- Rigs are data-only components. Systems interpret them. No logic in components.
- All hooks are optional callables. No subclassing required.
- Input goes through `InputBuffer` / `screen_to_world`. Raw pygame in userland is discouraged.

---

## Dependencies

| Package | Purpose |
|---|---|
| `pygame-ce` | Rendering, window, events |
| `pymunk` | 2D physics (Chipmunk) |
| `numpy` | Array math (default backend) |
| `cupy` (optional) | GPU-accelerated array math |

---

## Tests

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/pytest tests/ -q
```

78 passing. Covers: accumulator determinism, ECS CRUD, camera math, physics sync, rig execution, input buffer delivery, hook wiring.

---

## What's next

See [VISION.md](VISION.md) for the full roadmap. Near-term:

- **v0.2**: `Sprite.polygon()`, collision callbacks, scene management
- **v0.3**: Audio system, sprite sheets, Tiled map importer
- **v0.4**: SpringRig, HingeRig, SliderRig, rig composition
- **v1.0**: Rollback netcode (InputBuffer is already timestamped and per-step)

---

## License

MIT

---

**Engineered with Stratakinesis**
