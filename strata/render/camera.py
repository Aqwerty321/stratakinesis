# strata/render/camera.py
# Uniform scale-to-fit camera.  Converts between world units and screen pixels.
#
# World origin (0, 0) maps to the centre of the viewport.
# Y-axis is flipped: world +Y is screen -Y (up on screen).

from __future__ import annotations
import math

from strata.config import WORLD_WIDTH, WORLD_HEIGHT


class Camera:
    """
    Uniform scale-to-fit camera.

    Keeps the entire world rectangle (WORLD_WIDTH × WORLD_HEIGHT) visible inside
    the window with letter-boxing / pillar-boxing. The world is centred in the window.

    Attributes
    ----------
    scale   : pixels per world unit (float)
    offset_x: left edge of the world rect in screen pixels
    offset_y: top edge of the world rect in screen pixels
    """

    def __init__(self, window_size: tuple[int, int]) -> None:
        self.window_width: int = 0
        self.window_height: int = 0
        self.scale: float = 1.0
        self.offset_x: float = 0.0
        self.offset_y: float = 0.0
        self.resize(window_size)

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def resize(self, window_size: tuple[int, int]) -> None:
        """Recompute scale and centering offsets for a new window size."""
        self.window_width, self.window_height = window_size

        # Uniform scale: largest scale that still fits the whole world
        scale_x = self.window_width / WORLD_WIDTH
        scale_y = self.window_height / WORLD_HEIGHT
        self.scale = min(scale_x, scale_y)

        # Centre the world rect in the window
        world_screen_w = WORLD_WIDTH * self.scale
        world_screen_h = WORLD_HEIGHT * self.scale
        self.offset_x = (self.window_width - world_screen_w) / 2.0
        self.offset_y = (self.window_height - world_screen_h) / 2.0

    # ------------------------------------------------------------------
    # Coordinate conversions
    # ------------------------------------------------------------------

    def world_to_screen(self, wx: float, wy: float) -> tuple[int, int]:
        """Convert a world-space position to integer screen-pixel coordinates."""
        # World centre is at (WORLD_WIDTH/2, WORLD_HEIGHT/2) from tile origin,
        # but we define world origin as the centre of the viewport.
        sx = self.offset_x + (wx + WORLD_WIDTH / 2.0) * self.scale
        # Flip Y: world +Y is up, screen +Y is down
        sy = self.offset_y + (WORLD_HEIGHT / 2.0 - wy) * self.scale
        return int(sx), int(sy)

    def screen_to_world(self, sx: int, sy: int) -> tuple[float, float]:
        """Convert screen-pixel coordinates to world-space position."""
        wx = (sx - self.offset_x) / self.scale - WORLD_WIDTH / 2.0
        wy = WORLD_HEIGHT / 2.0 - (sy - self.offset_y) / self.scale
        return wx, wy

    def scale_length(self, world_length: float) -> int:
        """Convert a world-unit length to screen pixels (for radii, etc.)."""
        return max(1, int(world_length * self.scale))
