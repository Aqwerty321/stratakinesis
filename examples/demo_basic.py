"""
examples/demo_basic.py
======================
Minimal demo: a ball falling onto a static ground platform.

Demonstrates:
  - Deterministic fixed-step physics at 1/60 s
  - Uniform scale-to-fit camera (resize the window to see letterboxing)
  - Only the public Strata API is used

Run with:
    python examples/demo_basic.py
"""

from strata import Game, Sprite

if __name__ == "__main__":
    game = Game(window_size=(1024, 768), title="STRATA — demo_basic")

    # A dynamic ball, starting 6 world-units above the origin
    ball = Sprite.circle(radius=0.6, x=0.0, y=6.0, density=1.0, physics=True)

    # A wide static ground platform slightly below the origin
    ground = Sprite.rect(width=18.0, height=0.5, x=0.0, y=-4.0, static=True)

    game.scene.add_entities(ball, ground)
    game.run()
