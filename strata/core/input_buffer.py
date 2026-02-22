# strata/core/input_buffer.py
# Timestamped input buffer for sample-accurate event delivery to physics steps.
#
# Problem this solves:
#   In the fixed-step accumulator loop, pygame events are drained once per
#   rendered frame, but multiple physics steps may run per frame.  Without
#   timestamping, a KEYDOWN at the start of the frame and one at the end look
#   identical — both arrive before any physics step runs.  This causes up to
#   1 render-frame of input latency and makes per-step logic impossible.
#
# How it works:
#   1. InputBuffer.drain() replaces pygame.event.get().  Each event is wrapped
#      in a StampedEvent with time.monotonic() at the moment of drain.
#   2. During the accumulator loop, consume(t_start, t_end) pops only the
#      events whose timestamp falls within that physics step's time window.
#   3. on_fixed_update(dt, events) is called once per step with the relevant
#      slice of events.  Users put discrete input logic (jump, fire, reverse)
#      here instead of on_event.
#   4. clear() is called after the loop to drop events that fell past the last
#      step boundary (they'd be stale in the next frame's buffer).
#
# Multiplayer / rollback note:
#   StampedEvent carries a monotonic wall-clock timestamp.  For rollback netcode
#   this can be replaced with a deterministic sim-tick counter — swap
#   time.monotonic() for self._sim_tick in drain() and the rest of the logic is
#   unchanged.

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    pass


@dataclass
class StampedEvent:
    """A pygame event tagged with a monotonic wall-clock timestamp.

    Attributes
    ----------
    event     : the original pygame.event.Event
    timestamp : time.monotonic() value at the moment the event was drained
    """
    event: pygame.event.Event
    timestamp: float


class InputBuffer:
    """Collects, timestamps, and serves pygame events to fixed physics steps.

    Typical usage
    -------------
    Call ``drain()`` once per render frame (replaces ``pygame.event.get()``).
    Inside the accumulator loop call ``consume(step_start, step_end)`` to get
    the events that belong to that physics step.
    After the accumulator loop call ``clear()`` to drop any leftovers.

    Key-state polling
    -----------------
    ``poll_keys()`` wraps ``pygame.key.get_pressed()`` and is the preferred way
    to query continuous key state — it centralises all input access through one
    object, which will matter when adding input remapping or netcode playback.
    """

    def __init__(self) -> None:
        self._pending: deque[StampedEvent] = deque()

    # ------------------------------------------------------------------
    # Frame-level API (called by Game.run)
    # ------------------------------------------------------------------

    def drain(self) -> list[StampedEvent]:
        """Replace ``pygame.event.get()``.

        Stamps each pending pygame event with the current monotonic time and
        appends it to the internal buffer.  Returns the same events as a list
        so the engine can do its own QUIT/F3/VIDEORESIZE handling pass.
        """
        now = time.monotonic()
        stamped: list[StampedEvent] = []
        for ev in pygame.event.get():
            se = StampedEvent(event=ev, timestamp=now)
            self._pending.append(se)
            stamped.append(se)
        return stamped

    def consume(self, t_start: float, t_end: float) -> list[StampedEvent]:
        """Return all buffered events whose timestamp falls in ``[t_start, t_end)``.

        Events are consumed (removed from the buffer) and returned in
        chronological order.  Remaining events stay buffered for later steps.
        """
        result: list[StampedEvent] = []
        # Peek from the front; pop while still within window.
        while self._pending and self._pending[0].timestamp < t_end:
            se = self._pending.popleft()
            if se.timestamp >= t_start:
                result.append(se)
            # Events older than t_start have drifted past — drop them silently.
        return result

    def clear(self) -> None:
        """Discard all remaining buffered events.

        Call this after the accumulator loop to prevent stale events from
        bleeding into the next frame's physics steps.
        """
        self._pending.clear()

    def expire(self, before: float) -> None:
        """Discard events with timestamps strictly before *before*.

        Events timestamped >= *before* are kept for future physics steps.
        This prevents unconsumed events (e.g. when the frame had no physics
        steps) from being lost.
        """
        while self._pending and self._pending[0].timestamp < before:
            self._pending.popleft()

    # ------------------------------------------------------------------
    # Key-state API
    # ------------------------------------------------------------------

    def poll_keys(self) -> pygame.key.ScancodeWrapper:
        """Return the current key-pressed state (wraps ``pygame.key.get_pressed()``)."""
        return pygame.key.get_pressed()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._pending)

    def __repr__(self) -> str:  # pragma: no cover
        return f"InputBuffer(pending={len(self._pending)})"
