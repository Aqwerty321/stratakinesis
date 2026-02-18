# tests/test_input_buffer.py
# Tests for InputBuffer: timestamped event drain, windowed consume, clear,
# and integration with Game.on_fixed_update.

import os
import time

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()

from strata.core.input_buffer import InputBuffer, StampedEvent
from strata.config import FIXED_DT


# ---------------------------------------------------------------------------
# StampedEvent
# ---------------------------------------------------------------------------

class TestStampedEvent:
    def test_fields_accessible(self):
        ev = pygame.event.Event(pygame.USEREVENT)
        se = StampedEvent(event=ev, timestamp=1.0)
        assert se.event is ev
        assert se.timestamp == 1.0

    def test_different_timestamps(self):
        ev = pygame.event.Event(pygame.USEREVENT)
        se1 = StampedEvent(event=ev, timestamp=0.1)
        se2 = StampedEvent(event=ev, timestamp=0.2)
        assert se1.timestamp < se2.timestamp


# ---------------------------------------------------------------------------
# InputBuffer.drain()
# ---------------------------------------------------------------------------

class TestDrain:
    def test_drain_empty_when_no_events(self):
        pygame.event.clear()  # flush any pending init/audio events
        buf = InputBuffer()
        result = buf.drain()
        assert result == []
        assert len(buf) == 0

    def test_drain_returns_stamped_events(self, monkeypatch):
        ev = pygame.event.Event(pygame.USEREVENT)
        monkeypatch.setattr(pygame.event, "get", lambda: [ev])
        buf = InputBuffer()
        result = buf.drain()
        assert len(result) == 1
        assert isinstance(result[0], StampedEvent)
        assert result[0].event is ev

    def test_drain_timestamp_is_recent(self, monkeypatch):
        ev = pygame.event.Event(pygame.USEREVENT)
        monkeypatch.setattr(pygame.event, "get", lambda: [ev])
        before = time.monotonic()
        buf = InputBuffer()
        result = buf.drain()
        after = time.monotonic()
        assert before <= result[0].timestamp <= after

    def test_drain_accumulates_in_buffer(self, monkeypatch):
        ev = pygame.event.Event(pygame.USEREVENT)
        monkeypatch.setattr(pygame.event, "get", lambda: [ev])
        buf = InputBuffer()
        buf.drain()
        buf.drain()
        assert len(buf) == 2

    def test_drain_multiple_events(self, monkeypatch):
        evs = [pygame.event.Event(pygame.USEREVENT), pygame.event.Event(pygame.USEREVENT)]
        monkeypatch.setattr(pygame.event, "get", lambda: evs)
        buf = InputBuffer()
        result = buf.drain()
        assert len(result) == 2
        assert len(buf) == 2


# ---------------------------------------------------------------------------
# InputBuffer.consume()
# ---------------------------------------------------------------------------

class TestConsume:
    def _buf_with_events(self, timestamps: list[float]) -> InputBuffer:
        """Build a buffer with synthetic stamped events at given timestamps."""
        buf = InputBuffer()
        for t in timestamps:
            ev = pygame.event.Event(pygame.USEREVENT)
            buf._pending.append(StampedEvent(event=ev, timestamp=t))
        return buf

    def test_consume_returns_events_in_window(self):
        buf = self._buf_with_events([1.0, 1.005, 1.010])
        result = buf.consume(t_start=1.0, t_end=1.006)
        assert len(result) == 2
        assert result[0].timestamp == pytest.approx(1.0)
        assert result[1].timestamp == pytest.approx(1.005)

    def test_consume_leaves_later_events(self):
        buf = self._buf_with_events([1.0, 1.020])
        buf.consume(t_start=1.0, t_end=1.016)  # one FIXED_DT window
        assert len(buf) == 1
        assert buf._pending[0].timestamp == pytest.approx(1.020)

    def test_consume_half_open_interval(self):
        """t_end itself should NOT be included (half-open [t_start, t_end))."""
        buf = self._buf_with_events([1.0, 1.016])
        result = buf.consume(t_start=1.0, t_end=1.016)
        # 1.016 is NOT < 1.016, so it stays
        assert len(result) == 1
        assert len(buf) == 1

    def test_consume_empty_window(self):
        buf = self._buf_with_events([2.0])
        result = buf.consume(t_start=1.0, t_end=1.016)
        assert result == []
        assert len(buf) == 1

    def test_consume_all_in_window(self):
        buf = self._buf_with_events([1.0, 1.005, 1.010])
        result = buf.consume(t_start=0.0, t_end=2.0)
        assert len(result) == 3
        assert len(buf) == 0

    def test_consecutive_windows_no_duplication(self):
        """Two consecutive consume calls each get their own slice."""
        buf = self._buf_with_events([0.0, FIXED_DT * 0.5, FIXED_DT, FIXED_DT * 1.5])
        first  = buf.consume(0.0,       FIXED_DT)
        second = buf.consume(FIXED_DT,  FIXED_DT * 2)
        assert len(first)  == 2
        assert len(second) == 2
        # No overlap
        first_ts  = {se.timestamp for se in first}
        second_ts = {se.timestamp for se in second}
        assert first_ts.isdisjoint(second_ts)


# ---------------------------------------------------------------------------
# InputBuffer.clear()
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_empties_buffer(self, monkeypatch):
        ev = pygame.event.Event(pygame.USEREVENT)
        monkeypatch.setattr(pygame.event, "get", lambda: [ev, ev])
        buf = InputBuffer()
        buf.drain()
        assert len(buf) == 2
        buf.clear()
        assert len(buf) == 0

    def test_clear_idempotent(self):
        buf = InputBuffer()
        buf.clear()
        buf.clear()
        assert len(buf) == 0


# ---------------------------------------------------------------------------
# InputBuffer.poll_keys()
# ---------------------------------------------------------------------------

class TestPollKeys:
    def test_poll_keys_returns_scancode_wrapper(self):
        buf = InputBuffer()
        keys = buf.poll_keys()
        # Should be indexable with pygame key constants
        assert isinstance(keys[pygame.K_SPACE], (bool, int))


# ---------------------------------------------------------------------------
# Integration: Game.on_fixed_update receives correct events per step
# ---------------------------------------------------------------------------

class TestOnFixedUpdateIntegration:
    def make_game(self):
        from strata.core.loop import Game
        return Game(window_size=(640, 480))

    def test_on_fixed_update_default_none(self):
        game = self.make_game()
        assert game.on_fixed_update is None

    def test_on_fixed_update_assignable(self):
        game = self.make_game()
        received = []
        game.on_fixed_update = lambda dt, evs: received.append((dt, evs))
        game.on_fixed_update(FIXED_DT, [])
        assert received == [(pytest.approx(FIXED_DT), [])]

    def test_input_buffer_attached_to_game(self):
        game = self.make_game()
        assert isinstance(game.input, InputBuffer)

    def test_on_fixed_update_called_per_step(self, monkeypatch):
        """Simulate the accumulator: on_fixed_update fires once per step."""
        game = self.make_game()
        call_count = []
        game.on_fixed_update = lambda dt, evs: call_count.append(dt)

        # Manually run the accumulator logic for 3 steps
        accumulator = 0.0
        sim_time = time.monotonic()
        frame_time = FIXED_DT * 3  # enough for exactly 3 steps
        accumulator += frame_time
        while accumulator >= FIXED_DT:
            step_evs = game.input.consume(sim_time, sim_time + FIXED_DT)
            game.on_fixed_update(FIXED_DT, step_evs)
            accumulator -= FIXED_DT
            sim_time += FIXED_DT

        assert len(call_count) == 3
        assert all(dt == pytest.approx(FIXED_DT) for dt in call_count)

    def test_events_delivered_to_correct_step(self, monkeypatch):
        """An event timestamped inside step 2's window should arrive in step 2."""
        game = self.make_game()

        step_events: list[list] = []
        game.on_fixed_update = lambda dt, evs: step_events.append(list(evs))

        t0 = time.monotonic()
        # Inject a synthetic event with a timestamp in step 2's window
        ev = pygame.event.Event(pygame.USEREVENT)
        step2_ts = t0 + FIXED_DT * 1.5  # midpoint of [FIXED_DT, 2*FIXED_DT)
        game.input._pending.append(StampedEvent(event=ev, timestamp=step2_ts))

        # Run accumulator for 3 steps starting at t0
        sim_time = t0
        accumulator = FIXED_DT * 3
        while accumulator >= FIXED_DT:
            step_evs = game.input.consume(sim_time, sim_time + FIXED_DT)
            game.on_fixed_update(FIXED_DT, step_evs)
            accumulator -= FIXED_DT
            sim_time += FIXED_DT
        game.input.clear()

        assert step_events[0] == []          # step 1: no events
        assert len(step_events[1]) == 1      # step 2: our event
        assert step_events[1][0].event.type == pygame.USEREVENT
        assert step_events[2] == []          # step 3: no events
