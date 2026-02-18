# strata/shapes/factory.py
# Sprite: user-facing factory for creating game entities.
#
# All size parameters are in world units.
# Physics mass = density * area (area computed from geometry).
# Visual polygon vertices are cached once at creation; never rebuilt per frame.

from __future__ import annotations
import math

import pymunk

from strata.ecs.entity import Entity
from strata.ecs.components import Transform, Physics, Visual


# Number of segments used to approximate a circle's visual polygon.
_CIRCLE_SEGMENTS: int = 32

# Default colours
_DEFAULT_CIRCLE_COLOR = (100, 180, 255, 230)
_DEFAULT_RECT_COLOR = (180, 210, 100, 230)
_DEFAULT_OUTLINE = (255, 255, 255, 160)


def _circle_vertices(radius: float, segments: int = _CIRCLE_SEGMENTS) -> list[tuple[float, float]]:
    """Return local-space vertices for a circle polygon approximation."""
    verts = []
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        verts.append((radius * math.cos(angle), radius * math.sin(angle)))
    return verts


def _rect_vertices(width: float, height: float) -> list[tuple[float, float]]:
    """Return local-space vertices for an axis-aligned rectangle (CCW)."""
    hw = width / 2.0
    hh = height / 2.0
    return [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]


class Sprite:
    """
    Factory class.  All methods are static and return `Entity` instances
    ready to be added to a ``Game.scene``.

    The returned entity is *not* yet registered with a PhysicsSystem — that
    happens when you call ``game.scene.add_entity`` (which calls
    ``game.physics.register`` for any entity carrying a Physics component).
    """

    @staticmethod
    def circle(
        radius: float = 1.0,
        x: float = 0.0,
        y: float = 0.0,
        density: float = 1.0,
        physics: bool = True,
        static: bool = False,
        color: tuple[int, ...] = _DEFAULT_CIRCLE_COLOR,
        outline: tuple[int, ...] | None = _DEFAULT_OUTLINE,
    ) -> Entity:
        """Create a circular sprite.

        Parameters
        ----------
        radius  : circle radius in world units.
        x, y    : initial world-space position.
        density : mass per unit area (kg / world_unit²). Used for physics mass.
        physics : if True, attach a dynamic pymunk body.
        static  : if True, create a static pymunk body (overrides physics=True).
        """
        entity = Entity()

        # --- Transform ---
        entity.add_component(Transform(x=x, y=y))

        # --- Visual (cached vertices) ---
        verts = _circle_vertices(radius)
        entity.add_component(
            Visual(
                shape_type="circle",
                radius=radius,
                vertices=verts,
                color=color,
                outline=outline,
            )
        )

        # --- Physics ---
        if physics or static:
            area = math.pi * radius * radius
            mass = density * area

            if static:
                body = pymunk.Body(body_type=pymunk.Body.STATIC)
            else:
                moment = pymunk.moment_for_circle(mass, 0, radius)
                body = pymunk.Body(mass, moment)

            body.position = (x, y)
            shape = pymunk.Circle(body, radius)
            shape.elasticity = 0.5
            shape.friction = 0.8

            entity.add_component(
                Physics(body=body, shape=shape, density=density, is_static=static)
            )

        return entity

    @staticmethod
    def rect(
        width: float = 1.0,
        height: float = 1.0,
        x: float = 0.0,
        y: float = 0.0,
        density: float = 1.0,
        physics: bool = True,
        static: bool = False,
        color: tuple[int, ...] = _DEFAULT_RECT_COLOR,
        outline: tuple[int, ...] | None = _DEFAULT_OUTLINE,
    ) -> Entity:
        """Create a rectangular sprite.

        Parameters
        ----------
        width, height : dimensions in world units.
        x, y          : initial world-space centre position.
        density       : mass per unit area. Used for physics mass.
        physics       : if True, attach a dynamic pymunk body.
        static        : if True, create a static pymunk body.
        """
        entity = Entity()

        # --- Transform ---
        entity.add_component(Transform(x=x, y=y))

        # --- Visual (cached vertices) ---
        verts = _rect_vertices(width, height)
        entity.add_component(
            Visual(
                shape_type="polygon",
                vertices=verts,
                color=color,
                outline=outline,
            )
        )

        # --- Physics ---
        if physics or static:
            area = width * height
            mass = density * area

            if static:
                body = pymunk.Body(body_type=pymunk.Body.STATIC)
            else:
                moment = pymunk.moment_for_box(mass, (width, height))
                body = pymunk.Body(mass, moment)

            body.position = (x, y)
            # pymunk poly verts must be relative to body origin
            shape = pymunk.Poly.create_box(body, (width, height))
            shape.elasticity = 0.3
            shape.friction = 0.9

            entity.add_component(
                Physics(body=body, shape=shape, density=density, is_static=static)
            )

        return entity
