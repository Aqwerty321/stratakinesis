# strata/core/clock.py
# Thin wrapper around pygame.time.Clock that returns delta time in seconds.

from __future__ import annotations
import pygame


class Clock:
    """Thin wrapper around pygame.time.Clock.

    tick(max_fps) → delta-time in seconds (capped externally by the loop).
    """

    def __init__(self) -> None:
        self._clock = pygame.time.Clock()

    def tick(self, max_fps: int = 0) -> float:
        """Advance the clock and return delta time in **seconds**.

        Pass max_fps > 0 to cap frame rate.
        """
        millis = self._clock.tick(max_fps)
        return millis / 1000.0

    @property
    def fps(self) -> float:
        """Current measured frames per second."""
        return self._clock.get_fps()
