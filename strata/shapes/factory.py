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
from strata.ecs.components import Transform, Physics, Visual, SoftBody


# Number of segments used to approximate a circle's visual polygon.
_CIRCLE_SEGMENTS: int = 32

# Default colours
_DEFAULT_CIRCLE_COLOR = (100, 180, 255, 230)
_DEFAULT_RECT_COLOR = (180, 210, 100, 230)
_DEFAULT_POLYGON_COLOR = (255, 160, 80, 230)
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


def _shoelace_area(vertices: list[tuple[float, float]]) -> float:
    """Return the absolute area of a simple polygon via the Shoelace formula."""
    n = len(vertices)
    total = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


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

    @staticmethod
    def polygon(
        vertices: list[tuple[float, float]],
        x: float = 0.0,
        y: float = 0.0,
        density: float = 1.0,
        physics: bool = True,
        static: bool = False,
        color: tuple[int, ...] = _DEFAULT_POLYGON_COLOR,
        outline: tuple[int, ...] | None = _DEFAULT_OUTLINE,
    ) -> Entity:
        """Create a convex polygon sprite.

        Parameters
        ----------
        vertices : convex polygon vertices in local CCW order (world units).
                   Must have at least 3 vertices.  No auto-convex-hull is
                   applied — passing non-convex vertices produces undefined
                   physics behaviour.
        x, y     : initial world-space centre position.
        density  : mass per unit area (kg / world_unit²).
        physics  : if True, attach a dynamic pymunk body.
        static   : if True, create a static pymunk body (overrides physics=True).
        """
        if len(vertices) < 3:
            raise ValueError(
                f"Sprite.polygon requires at least 3 vertices, got {len(vertices)}"
            )

        entity = Entity()

        # --- Transform ---
        entity.add_component(Transform(x=x, y=y))

        # --- Visual (cached vertices) ---
        entity.add_component(
            Visual(
                shape_type="polygon",
                vertices=list(vertices),
                color=color,
                outline=outline,
            )
        )

        # --- Physics ---
        if physics or static:
            area = _shoelace_area(vertices)
            mass = density * area

            if static:
                body = pymunk.Body(body_type=pymunk.Body.STATIC)
            else:
                moment = pymunk.moment_for_poly(mass, vertices)
                body = pymunk.Body(mass, moment)

            body.position = (x, y)
            shape = pymunk.Poly(body, vertices)
            shape.elasticity = 0.3
            shape.friction = 0.8

            entity.add_component(
                Physics(body=body, shape=shape, density=density, is_static=static)
            )

        return entity

    # ------------------------------------------------------------------
    # Soft body factories
    # ------------------------------------------------------------------

    @staticmethod
    def soft_rect(
        cols: int = 4,
        rows: int = 4,
        width: float = 2.0,
        height: float = 2.0,
        x: float = 0.0,
        y: float = 0.0,
        density: float = 1.0,
        stiffness: float = 300.0,
        damping: float = 10.0,
        pressure: float = 80.0,
        velocity_damping: float = 0.995,
        node_radius: float = 0.12,
        color: tuple[int, ...] = _DEFAULT_POLYGON_COLOR,
        outline: tuple[int, ...] | None = _DEFAULT_OUTLINE,
    ) -> Entity:
        """Create a soft rectangular body using a grid spring-mass mesh.

        Parameters
        ----------
        cols, rows : grid subdivisions (minimum 2x2).
        width, height : overall dimensions in world units.
        x, y       : world-space centre of the soft body.
        density    : total mass = density * width * height, distributed evenly.
        stiffness  : DampedSpring stiffness (N per world unit).
        damping    : DampedSpring damping coefficient.
        pressure   : internal pressure coefficient — resists volume loss.
        velocity_damping : per-step velocity multiplier (0..1).
        node_radius: collision radius of perimeter node circles.
        """
        if cols < 2 or rows < 2:
            raise ValueError(f"soft_rect requires cols>=2, rows>=2; got {cols}x{rows}")

        total_mass = density * width * height
        n_nodes = cols * rows
        node_mass = total_mass / n_nodes

        # Build grid of bodies centred at (x, y)
        cell_dx = width / (cols - 1)
        cell_dy = height / (rows - 1)
        x0 = x - width / 2.0
        y0 = y - height / 2.0

        nodes: list[pymunk.Body] = []
        for r in range(rows):
            for c in range(cols):
                moment = pymunk.moment_for_circle(node_mass, 0, node_radius)
                body = pymunk.Body(node_mass, moment)
                body.position = (x0 + c * cell_dx, y0 + r * cell_dy)
                nodes.append(body)

        def _idx(r: int, c: int) -> int:
            return r * cols + c

        # Springs: horizontal, vertical, diagonal (structural + shear)
        springs: list[pymunk.DampedSpring] = []

        def _add_spring(i: int, j: int) -> None:
            a, b = nodes[i], nodes[j]
            rest = a.position.get_distance(b.position)
            spring = pymunk.DampedSpring(
                a, b, (0, 0), (0, 0), rest, stiffness, damping
            )
            spring.collide_bodies = False
            springs.append(spring)

        for r in range(rows):
            for c in range(cols):
                # Right neighbour
                if c + 1 < cols:
                    _add_spring(_idx(r, c), _idx(r, c + 1))
                # Up neighbour
                if r + 1 < rows:
                    _add_spring(_idx(r, c), _idx(r + 1, c))
                # Diagonal up-right
                if r + 1 < rows and c + 1 < cols:
                    _add_spring(_idx(r, c), _idx(r + 1, c + 1))
                # Diagonal up-left
                if r + 1 < rows and c - 1 >= 0:
                    _add_spring(_idx(r, c), _idx(r + 1, c - 1))

        # Perimeter indices (CCW): bottom L->R, right B->T, top R->L, left T->B
        surface_indices: list[int] = []
        for c in range(cols):
            surface_indices.append(_idx(0, c))
        for r in range(1, rows):
            surface_indices.append(_idx(r, cols - 1))
        for c in range(cols - 2, -1, -1):
            surface_indices.append(_idx(rows - 1, c))
        for r in range(rows - 2, 0, -1):
            surface_indices.append(_idx(r, 0))

        # Collision shapes on perimeter nodes only
        surface_shapes: list[pymunk.Circle] = []
        perimeter_set = set(surface_indices)
        for idx in perimeter_set:
            shape = pymunk.Circle(nodes[idx], node_radius)
            shape.elasticity = 0.3
            shape.friction = 0.8
            surface_shapes.append(shape)

        # Perimeter vertices for visual mesh (local coords relative to centre)
        perimeter_verts = []
        for idx in surface_indices:
            bx, by = nodes[idx].position
            perimeter_verts.append((bx - x, by - y))

        # Compute rest area from perimeter polygon (for pressure forces)
        rest_area = _shoelace_area(perimeter_verts)

        entity = Entity()
        entity.add_component(Transform(x=x, y=y))
        entity.add_component(Visual(
            shape_type="soft_polygon",
            vertices=perimeter_verts,
            color=color,
            outline=outline,
        ))
        entity.add_component(SoftBody(
            nodes=nodes,
            springs=springs,
            surface_shapes=surface_shapes,
            surface_indices=surface_indices,
            stiffness=stiffness,
            damping=damping,
            node_radius=node_radius,
            pressure=pressure,
            velocity_damping=velocity_damping,
            rest_area=rest_area,
            topology="grid",
        ))

        return entity

    @staticmethod
    def soft_circle(
        rings: int = 3,
        segments: int = 12,
        radius: float = 1.0,
        x: float = 0.0,
        y: float = 0.0,
        density: float = 1.0,
        stiffness: float = 300.0,
        damping: float = 10.0,
        pressure: float = 80.0,
        velocity_damping: float = 0.995,
        node_radius: float = 0.10,
        color: tuple[int, ...] = _DEFAULT_CIRCLE_COLOR,
        outline: tuple[int, ...] | None = _DEFAULT_OUTLINE,
    ) -> Entity:
        """Create a soft circular body using a radial ring spring-mass mesh.

        Parameters
        ----------
        rings    : number of concentric rings (minimum 1). ring 0 = centre node.
        segments : nodes per ring (minimum 3).
        radius   : outer radius in world units.
        x, y     : world-space centre of the soft body.
        density  : total mass = density * pi * radius^2.
        stiffness: DampedSpring stiffness.
        damping  : DampedSpring damping coefficient.
        pressure : internal pressure coefficient — resists volume loss.
        velocity_damping : per-step velocity multiplier (0..1).
        node_radius: collision radius of outermost ring circles.
        """
        if rings < 1:
            raise ValueError(f"soft_circle requires rings>=1, got {rings}")
        if segments < 3:
            raise ValueError(f"soft_circle requires segments>=3, got {segments}")

        total_mass = density * math.pi * radius * radius
        n_nodes = 1 + rings * segments
        node_mass = total_mass / n_nodes

        # Centre node
        moment_centre = pymunk.moment_for_circle(node_mass, 0, node_radius)
        centre = pymunk.Body(node_mass, moment_centre)
        centre.position = (x, y)

        nodes: list[pymunk.Body] = [centre]  # index 0 = centre
        ring_start: list[int] = []  # start index for each ring

        for ring_i in range(1, rings + 1):
            ring_r = radius * ring_i / rings
            ring_start.append(len(nodes))
            for seg in range(segments):
                angle = 2.0 * math.pi * seg / segments
                bx = x + ring_r * math.cos(angle)
                by = y + ring_r * math.sin(angle)
                moment = pymunk.moment_for_circle(node_mass, 0, node_radius)
                body = pymunk.Body(node_mass, moment)
                body.position = (bx, by)
                nodes.append(body)

        springs: list[pymunk.DampedSpring] = []

        def _add_spring(i: int, j: int) -> None:
            a, b = nodes[i], nodes[j]
            rest = a.position.get_distance(b.position)
            spring = pymunk.DampedSpring(
                a, b, (0, 0), (0, 0), rest, stiffness, damping
            )
            spring.collide_bodies = False
            springs.append(spring)

        # Radial springs: centre -> ring 1
        for seg in range(segments):
            _add_spring(0, ring_start[0] + seg)

        # Per-ring: circumferential + radial to previous ring
        for ring_i in range(len(ring_start)):
            start = ring_start[ring_i]
            # Circumferential: connect each node to next in ring
            for seg in range(segments):
                _add_spring(start + seg, start + (seg + 1) % segments)
            # Radial to previous ring
            if ring_i > 0:
                prev_start = ring_start[ring_i - 1]
                for seg in range(segments):
                    _add_spring(prev_start + seg, start + seg)
                    # Diagonal shear
                    _add_spring(prev_start + (seg + 1) % segments, start + seg)

        # Surface = outermost ring
        outer_start = ring_start[-1]
        surface_indices = list(range(outer_start, outer_start + segments))

        # Collision shapes on outermost ring only
        surface_shapes: list[pymunk.Circle] = []
        for idx in surface_indices:
            shape = pymunk.Circle(nodes[idx], node_radius)
            shape.elasticity = 0.3
            shape.friction = 0.8
            surface_shapes.append(shape)

        # Initial perimeter vertices (local coords relative to centre)
        perimeter_verts = []
        for idx in surface_indices:
            bx, by = nodes[idx].position
            perimeter_verts.append((bx - x, by - y))

        # Compute rest area from perimeter polygon (for pressure forces)
        rest_area = _shoelace_area(perimeter_verts)

        entity = Entity()
        entity.add_component(Transform(x=x, y=y))
        entity.add_component(Visual(
            shape_type="soft_polygon",
            vertices=perimeter_verts,
            color=color,
            outline=outline,
        ))
        entity.add_component(SoftBody(
            nodes=nodes,
            springs=springs,
            surface_shapes=surface_shapes,
            surface_indices=surface_indices,
            stiffness=stiffness,
            damping=damping,
            node_radius=node_radius,
            pressure=pressure,
            velocity_damping=velocity_damping,
            rest_area=rest_area,
            topology="radial",
        ))

        return entity
