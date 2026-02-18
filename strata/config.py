# strata/config.py
# Boot-time constants. Immutable at runtime.
# All world-space values are in world units (not pixels).

ASPECT_RATIO: tuple[int, int] = (16, 9)

WORLD_WIDTH: float = 16.0
WORLD_HEIGHT: float = WORLD_WIDTH * ASPECT_RATIO[1] / ASPECT_RATIO[0]  # 9.0

FIXED_DT: float = 1.0 / 60.0

MAX_FRAME_TIME: float = 0.25  # clamp per-tick to this to avoid spiral-of-death
