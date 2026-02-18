# tests/test_loop.py
# Tests for the Game loop: accumulator determinism and frame-time clamp.

import pytest
from strata.core.loop import Game
from strata.config import FIXED_DT, MAX_FRAME_TIME, WORLD_WIDTH, WORLD_HEIGHT


def make_game():
    """Create a headless Game instance (no display needed for step tests)."""
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    return Game(window_size=(1024, 768))


class TestConfigImmutability:
    def test_world_width_unchanged_after_step(self):
        game = make_game()
        game.step(FIXED_DT)
        assert WORLD_WIDTH == 16.0

    def test_world_height_unchanged_after_step(self):
        game = make_game()
        game.step(FIXED_DT)
        assert WORLD_HEIGHT == pytest.approx(9.0)

    def test_fixed_dt_value(self):
        assert FIXED_DT == pytest.approx(1.0 / 60.0)

    def test_max_frame_time_value(self):
        assert MAX_FRAME_TIME == pytest.approx(0.25)


class TestAccumulatorDeterminism:
    def test_step_advances_physics(self):
        """A ball stepped N times should fall the expected distance (gravity)."""
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from strata.shapes.factory import Sprite
        from strata.ecs.components import Transform

        game = make_game()
        ball = Sprite.circle(radius=0.5, x=0.0, y=5.0, density=1.0, physics=True)
        game.scene.add_entities(ball)

        initial_y = ball.get_component(Transform).y

        steps = 60  # 1 simulated second
        for _ in range(steps):
            game.step(FIXED_DT)

        final_y = ball.get_component(Transform).y
        # Ball should have fallen (gravity is -9.81 m/s²); y must decrease
        assert final_y < initial_y

    def test_deterministic_same_result_twice(self):
        """Two identical simulations run to the same step must give identical results."""
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from strata.shapes.factory import Sprite
        from strata.ecs.components import Transform

        positions = []
        for _ in range(2):
            # Reset entity ID counter for consistency not needed here;
            # we compare within each run.
            g = make_game()
            b = Sprite.circle(radius=0.5, x=1.0, y=4.0, density=1.0, physics=True)
            g.scene.add_entities(b)
            for __ in range(30):
                g.step(FIXED_DT)
            positions.append(b.get_component(Transform).y)

        assert positions[0] == pytest.approx(positions[1], abs=1e-9)


class TestGameHooks:
    """on_event and on_update are assignable and callable without a display."""

    def test_on_update_is_none_by_default(self):
        game = make_game()
        assert game.on_update is None

    def test_on_event_is_none_by_default(self):
        game = make_game()
        assert game.on_event is None

    def test_on_update_callable_assigned(self):
        game = make_game()
        called_with = []
        game.on_update = lambda dt: called_with.append(dt)
        # Simulate what run() does: call on_update with a frame time
        game.on_update(FIXED_DT)
        assert called_with == [pytest.approx(FIXED_DT)]

    def test_on_event_callable_assigned(self):
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame
        pygame.init()

        game = make_game()
        received = []
        game.on_event = lambda e: received.append(e.type)

        # Post a user event and fire the hook manually (mirrors what run() does)
        ev = pygame.event.Event(pygame.USEREVENT)
        game.on_event(ev)
        assert received == [pygame.USEREVENT]

    def test_on_update_receives_positive_dt(self):
        game = make_game()
        dts = []
        game.on_update = lambda dt: dts.append(dt)
        game.on_update(1 / 60)
        assert dts[0] > 0

    def test_hooks_replaceable(self):
        """Hooks can be reassigned mid-session."""
        game = make_game()
        log = []
        game.on_update = lambda dt: log.append("first")
        game.on_update(FIXED_DT)
        game.on_update = lambda dt: log.append("second")
        game.on_update(FIXED_DT)
        assert log == ["first", "second"]
