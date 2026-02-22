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
from strata.shapes.mesh import Mesh
from strata.core.collision_groups import CollisionGroups


# Singleton CollisionGroups registry — shared across all Sprite calls.
# Game.groups points to this same instance and can be used to query/allocate.
_collision_groups = CollisionGroups()


def _resolve_collision(group, collides_with):
    """Convert string group/collides_with to bitmask layer/mask.

    Parameters
    ----------
    group : str | None
        Named collision group for this shape's *layer*.
    collides_with : str | list[str] | None
        Named groups this shape should collide with (*mask*).

    Returns
    -------
    (int, int) : (collision_layer, collision_mask)
    """
    if group is not None:
        layer = _collision_groups.get(group)
    else:
        layer = 0xFFFF

    if collides_with is not None:
        if isinstance(collides_with, str):
            collides_with = [collides_with]
        mask = 0
        for name in collides_with:
            mask |= _collision_groups.get(name)
    else:
        mask = 0xFFFF

    return layer, mask


# Number of segments used to approximate a circle's visual polygon.
_CIRCLE_SEGMENTS: int = 32

# Default colours
_DEFAULT_CIRCLE_COLOR = (100, 180, 255, 230)
_DEFAULT_RECT_COLOR = (180, 210, 100, 230)
_DEFAULT_POLYGON_COLOR = (255, 160, 80, 230)
_DEFAULT_OUTLINE = (255, 255, 255, 160)


def _circle_vertices(radius: float, segments: int = _CIRCLE_SEGMENTS) -> list[tuple[float, float]]:
    """Return local-space vertices for a circle polygon approximation.

    Delegates to Mesh.circle() which uses pre-computed unit templates
    and LRU caching — no trig after the first call with these params.
    """
    return Mesh.circle(radius, segments)


def _rect_vertices(width: float, height: float) -> list[tuple[float, float]]:
    """Return local-space vertices for an axis-aligned rectangle (CCW).

    Delegates to Mesh.rect() with LRU caching.
    """
    return Mesh.rect(width, height)


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
        linear_damping: float = 1.0,
        angular_damping: float = 1.0,
        group: str | None = None,
        collides_with: str | list[str] | None = None,
    ) -> Entity:
        """Create a circular sprite.

        Parameters
        ----------
        radius  : circle radius in world units.
        x, y    : initial world-space position.
        density : mass per unit area (kg / world_unit²). Used for physics mass.
        physics : if True, attach a dynamic pymunk body.
        static  : if True, create a static pymunk body (overrides physics=True).
        group   : named collision group (e.g. ``"player"``).
        collides_with : group name(s) this shape collides with.
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

            layer, mask = _resolve_collision(group, collides_with)
            entity.add_component(
                Physics(
                    body=body, shape=shape, density=density, is_static=static,
                    collision_layer=layer, collision_mask=mask,
                    linear_damping=linear_damping, angular_damping=angular_damping,
                )
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
        linear_damping: float = 1.0,
        angular_damping: float = 1.0,
        group: str | None = None,
        collides_with: str | list[str] | None = None,
    ) -> Entity:
        """Create a rectangular sprite.

        Parameters
        ----------
        width, height : dimensions in world units.
        x, y          : initial world-space centre position.
        density       : mass per unit area. Used for physics mass.
        physics       : if True, attach a dynamic pymunk body.
        static        : if True, create a static pymunk body.
        group         : named collision group (e.g. ``"player"``).
        collides_with : group name(s) this shape collides with.
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

            layer, mask = _resolve_collision(group, collides_with)
            entity.add_component(
                Physics(
                    body=body, shape=shape, density=density, is_static=static,
                    collision_layer=layer, collision_mask=mask,
                    linear_damping=linear_damping, angular_damping=angular_damping,
                )
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
        linear_damping: float = 1.0,
        angular_damping: float = 1.0,
        group: str | None = None,
        collides_with: str | list[str] | None = None,
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
        linear_damping  : per-step linear velocity multiplier (0..1). 1.0 = no decay.
        angular_damping : per-step angular velocity multiplier (0..1). 1.0 = no decay.
        group           : named collision group (e.g. ``"player"``).
        collides_with   : group name(s) this shape collides with.
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

            layer, mask = _resolve_collision(group, collides_with)
            entity.add_component(
                Physics(body=body, shape=shape, density=density, is_static=static,
                        collision_layer=layer, collision_mask=mask,
                        linear_damping=linear_damping, angular_damping=angular_damping,)
            )

        return entity

    # ------------------------------------------------------------------
    # Image sprite
    # ------------------------------------------------------------------

    @staticmethod
    def image(
        path: str,
        width: float | None = None,
        height: float | None = None,
        x: float = 0.0,
        y: float = 0.0,
        density: float = 1.0,
        physics: bool = True,
        static: bool = False,
        linear_damping: float = 1.0,
        angular_damping: float = 1.0,
        group: str | None = None,
        collides_with: str | list[str] | None = None,
    ) -> Entity:
        """Create a sprite rendered from an image file.

        The image is loaded once via ``pygame.image.load`` and blitted each
        frame aligned to the body's Transform (position + rotation).

        Parameters
        ----------
        path    : filesystem path to the image (PNG, JPG, BMP, etc.).
        width   : width in world units.  If None, derived from image
                  aspect ratio and *height* (or defaults to 1.0).
        height  : height in world units.  If None, derived from *width*.
        x, y    : initial world-space centre position.
        density : mass per unit area.
        physics : if True, attach a dynamic box-shaped pymunk body matching
                  the image dimensions.
        static  : if True, create a static pymunk body.
        group   : named collision group.
        collides_with : group name(s) this shape collides with.
        """
        import pygame as _pg

        surf = _pg.image.load(path)
        try:
            if surf.get_alpha() is not None or surf.get_colorkey() is not None:
                surf = surf.convert_alpha()
            else:
                surf = surf.convert()
        except _pg.error:
            pass  # headless / no display — keep unconverted surface

        img_w, img_h = surf.get_size()
        aspect = img_w / max(img_h, 1)

        # Resolve world-unit dimensions
        if width is None and height is None:
            width = 1.0
            height = width / aspect
        elif width is None:
            width = height * aspect  # type: ignore[operator]
        elif height is None:
            height = width / aspect

        entity = Entity()
        entity.add_component(Transform(x=x, y=y))
        entity.add_component(Visual(
            shape_type="image",
            image_surface=surf,
            image_width=width,
            image_height=height,
        ))

        if physics or static:
            area = width * height  # type: ignore[operator]
            mass = density * area

            if static:
                body = pymunk.Body(body_type=pymunk.Body.STATIC)
            else:
                moment = pymunk.moment_for_box(mass, (width, height))
                body = pymunk.Body(mass, moment)

            body.position = (x, y)
            shape = pymunk.Poly.create_box(body, (width, height))
            shape.elasticity = 0.3
            shape.friction = 0.8

            layer, mask = _resolve_collision(group, collides_with)
            entity.add_component(
                Physics(body=body, shape=shape, density=density, is_static=static,
                        collision_layer=layer, collision_mask=mask,
                        linear_damping=linear_damping, angular_damping=angular_damping)
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
        node_radius: float = 0.0,
        node_density: float = 0.0,
        color: tuple[int, ...] = _DEFAULT_POLYGON_COLOR,
        outline: tuple[int, ...] | None = _DEFAULT_OUTLINE,
    ) -> Entity:
        """Create a soft rectangular body using a grid spring-mass mesh.

        The mesh has three spring tiers:
          * **structural** — horizontal + vertical (maintain overall shape).
          * **shear** — diagonal (resist shearing).
          * **bending** — 2-away horizontal + vertical (resist folding).

        Parameters
        ----------
        cols, rows : grid subdivisions (minimum 2x2).
                     Overridden by *node_density* when > 0.
        width, height : overall dimensions in world units.
        x, y       : world-space centre of the soft body.
        density    : total mass = density * width * height, distributed evenly.
        stiffness  : DampedSpring stiffness (N per world unit).
        damping    : DampedSpring damping coefficient.
        pressure   : (legacy, forwarded to SoftBody for compat).
        velocity_damping : per-step velocity multiplier (0..1).
        node_radius: collision radius of perimeter node circles.  When 0 (default),
                     auto-calculated from mesh spacing so the perimeter is sealed
                     (no gaps for external objects to poke through).
        node_density : nodes per world unit.  When > 0, computes cols/rows
                       automatically: ``cols = max(2, round(width * node_density))``.
        """
        # node_density override
        if node_density > 0:
            cols = max(2, round(width * node_density))
            rows = max(2, round(height * node_density))

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

        # Auto-calculate node_radius to seal perimeter gaps if not explicit
        if node_radius <= 0:
            # min spacing between adjacent perimeter nodes
            min_gap = min(cell_dx, cell_dy)
            # Half-spacing: adjacent circles just touch along the edge.
            node_radius = min_gap * 0.5

        nodes: list[pymunk.Body] = []
        for r in range(rows):
            for c in range(cols):
                # Infinite moment prevents rotation — keeps collision
                # circle offsets pointing inward permanently.
                body = pymunk.Body(node_mass, float('inf'))
                body.position = (x0 + c * cell_dx, y0 + r * cell_dy)
                nodes.append(body)

        def _idx(r: int, c: int) -> int:
            return r * cols + c

        # Springs: structural, shear, and bending
        springs: list[pymunk.DampedSpring] = []
        _added: set[tuple[int, int]] = set()  # avoid duplicate springs

        def _add_spring(i: int, j: int, stiff: float, damp: float) -> None:
            key = (min(i, j), max(i, j))
            if key in _added:
                return
            _added.add(key)
            a, b = nodes[i], nodes[j]
            rest = a.position.get_distance(b.position)
            spring = pymunk.DampedSpring(
                a, b, (0, 0), (0, 0), rest, stiff, damp
            )
            spring.collide_bodies = False
            springs.append(spring)

        # Bending spring parameters — softer than structural
        bend_stiffness = stiffness * 0.4
        bend_damping = damping * 0.4

        for r in range(rows):
            for c in range(cols):
                # --- Structural: immediate neighbours ---
                # Right
                if c + 1 < cols:
                    _add_spring(_idx(r, c), _idx(r, c + 1), stiffness, damping)
                # Up
                if r + 1 < rows:
                    _add_spring(_idx(r, c), _idx(r + 1, c), stiffness, damping)

                # --- Shear: diagonal neighbours ---
                if r + 1 < rows and c + 1 < cols:
                    _add_spring(_idx(r, c), _idx(r + 1, c + 1), stiffness, damping)
                if r + 1 < rows and c - 1 >= 0:
                    _add_spring(_idx(r, c), _idx(r + 1, c - 1), stiffness, damping)

                # --- Bending: 2-away neighbours ---
                # Horizontal bending
                if c + 2 < cols:
                    _add_spring(_idx(r, c), _idx(r, c + 2), bend_stiffness, bend_damping)
                # Vertical bending
                if r + 2 < rows:
                    _add_spring(_idx(r, c), _idx(r + 2, c), bend_stiffness, bend_damping)
                # Diagonal bending
                if r + 2 < rows and c + 2 < cols:
                    _add_spring(_idx(r, c), _idx(r + 2, c + 2), bend_stiffness, bend_damping)
                if r + 2 < rows and c - 2 >= 0:
                    _add_spring(_idx(r, c), _idx(r + 2, c - 2), bend_stiffness, bend_damping)

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

        # Collision shapes on ALL nodes (not just perimeter).
        # Self-collision is prevented by ShapeFilter.group at registration.
        # Interior shapes must exist to prevent nodes passing through floors.
        #
        # Perimeter nodes get an inward offset so their collision circle's
        # outer edge aligns with the visual polygon edge (the node position).
        # The inward direction is the average of the two adjacent edge
        # inward normals for a CCW polygon.
        n_surf = len(surface_indices)
        perimeter_set = set(surface_indices)
        perimeter_positions = [(nodes[si].position.x, nodes[si].position.y)
                               for si in surface_indices]
        inward_offsets: dict[int, tuple[float, float]] = {}
        for i in range(n_surf):
            px, py = perimeter_positions[(i - 1) % n_surf]
            cx, cy = perimeter_positions[i]
            nx, ny = perimeter_positions[(i + 1) % n_surf]
            # Edge prev->curr inward normal (CCW polygon: inward = (-dy, dx))
            dx1, dy1 = cx - px, cy - py
            inx1, iny1 = -dy1, dx1
            # Edge curr->next inward normal
            dx2, dy2 = nx - cx, ny - cy
            inx2, iny2 = -dy2, dx2
            # Average and normalise
            anx, any_ = inx1 + inx2, iny1 + iny2
            length = math.hypot(anx, any_)
            if length > 1e-9:
                anx /= length
                any_ /= length
            inward_offsets[surface_indices[i]] = (anx * node_radius,
                                                  any_ * node_radius)

        surface_shapes: list[pymunk.Circle] = []
        for idx in range(len(nodes)):
            offset = inward_offsets.get(idx, (0, 0))
            shape = pymunk.Circle(nodes[idx], node_radius, offset=offset)
            shape.elasticity = 0.3
            shape.friction = 0.8
            surface_shapes.append(shape)

        # Perimeter vertices for visual mesh (local coords relative to centre).
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
            node_density=node_density,
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
        node_radius: float = 0.0,
        node_density: float = 0.0,
        color: tuple[int, ...] = _DEFAULT_CIRCLE_COLOR,
        outline: tuple[int, ...] | None = _DEFAULT_OUTLINE,
    ) -> Entity:
        """Create a soft circular body using a radial ring spring-mass mesh.

        The mesh has three spring tiers:
          * **structural** — radial + circumferential (maintain overall shape).
          * **shear** — cross-ring diagonal (resist shearing).
          * **bending** — 2-away circumferential + skip-ring radial (resist
            folding / angular collapse).

        Parameters
        ----------
        rings    : number of concentric rings (minimum 1). ring 0 = centre node.
                   Overridden by *node_density* when > 0.
        segments : nodes per ring (minimum 3).
                   Overridden by *node_density* when > 0.
        radius   : outer radius in world units.
        x, y     : world-space centre of the soft body.
        density  : total mass = density * pi * radius^2.
        stiffness: DampedSpring stiffness.
        damping  : DampedSpring damping coefficient.
        pressure : (legacy, forwarded to SoftBody for compat).
        velocity_damping : per-step velocity multiplier (0..1).
        node_radius: collision radius of outermost ring circles.  When 0 (default),
                     auto-calculated from mesh spacing so the perimeter is sealed.
        node_density : nodes per world unit.  When > 0, computes rings/segments
                       automatically: ``segments = max(6, round(2π * radius * node_density))``,
                       ``rings = max(1, round(radius * node_density))``.
        """
        # node_density override
        if node_density > 0:
            segments = max(6, round(2 * math.pi * radius * node_density))
            rings = max(1, round(radius * node_density))

        if rings < 1:
            raise ValueError(f"soft_circle requires rings>=1, got {rings}")
        if segments < 3:
            raise ValueError(f"soft_circle requires segments>=3, got {segments}")

        total_mass = density * math.pi * radius * radius
        n_nodes = 1 + rings * segments
        node_mass = total_mass / n_nodes

        # Auto-calculate node_radius to seal perimeter gaps if not explicit
        if node_radius <= 0:
            outer_arc = 2.0 * math.pi * radius / segments
            # Half the arc spacing: adjacent circles just touch.
            node_radius = outer_arc * 0.5

        # Centre node — infinite moment prevents rotation.
        centre = pymunk.Body(node_mass, float('inf'))
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
                body = pymunk.Body(node_mass, float('inf'))
                body.position = (bx, by)
                nodes.append(body)

        springs: list[pymunk.DampedSpring] = []
        _added: set[tuple[int, int]] = set()  # avoid duplicate springs

        def _add_spring(i: int, j: int, stiff: float, damp: float) -> None:
            key = (min(i, j), max(i, j))
            if key in _added:
                return
            _added.add(key)
            a, b = nodes[i], nodes[j]
            rest = a.position.get_distance(b.position)
            spring = pymunk.DampedSpring(
                a, b, (0, 0), (0, 0), rest, stiff, damp
            )
            spring.collide_bodies = False
            springs.append(spring)

        # Bending spring parameters — softer than structural
        bend_stiffness = stiffness * 0.4
        bend_damping = damping * 0.4

        # --- Structural: centre -> ring 1 ---
        for seg in range(segments):
            _add_spring(0, ring_start[0] + seg, stiffness, damping)

        # --- Per-ring: circumferential + radial/shear to previous ring ---
        for ring_i in range(len(ring_start)):
            start = ring_start[ring_i]
            # Circumferential (structural)
            for seg in range(segments):
                _add_spring(start + seg, start + (seg + 1) % segments,
                            stiffness, damping)
            # Radial + shear to previous ring
            if ring_i > 0:
                prev_start = ring_start[ring_i - 1]
                for seg in range(segments):
                    # Radial (structural)
                    _add_spring(prev_start + seg, start + seg,
                                stiffness, damping)
                    # Shear diagonal
                    _add_spring(prev_start + (seg + 1) % segments, start + seg,
                                stiffness, damping)

        # --- Bending: 2-away circumferential ---
        for ring_i in range(len(ring_start)):
            start = ring_start[ring_i]
            for seg in range(segments):
                _add_spring(start + seg, start + (seg + 2) % segments,
                            bend_stiffness, bend_damping)

        # --- Bending: skip-ring radial (connect ring i to ring i+2) ---
        for ring_i in range(len(ring_start)):
            start = ring_start[ring_i]
            # Connect to centre if this is ring 1 (ring_i == 0)
            # (already connected via structural radial — skip)
            # Connect to ring two further out
            if ring_i + 2 < len(ring_start):
                far_start = ring_start[ring_i + 2]
                for seg in range(segments):
                    _add_spring(start + seg, far_start + seg,
                                bend_stiffness, bend_damping)

        # Surface = outermost ring
        outer_start = ring_start[-1]
        surface_indices = list(range(outer_start, outer_start + segments))

        # Collision shapes on ALL nodes (not just outermost ring).
        # Self-collision is prevented by ShapeFilter.group at registration.
        # Interior shapes prevent nodes from tunneling through floors.
        #
        # Perimeter (outer ring) nodes get an inward offset so their
        # collision circle's outer edge aligns with the visual polygon
        # edge.  For a circle the inward direction is simply toward the
        # centre of the mesh.
        perimeter_set = set(surface_indices)
        inward_offsets: dict[int, tuple[float, float]] = {}
        for si in surface_indices:
            bx, by = nodes[si].position.x, nodes[si].position.y
            dx, dy = x - bx, y - by  # toward centre
            d = math.hypot(dx, dy)
            if d > 1e-9:
                inward_offsets[si] = (dx / d * node_radius,
                                     dy / d * node_radius)

        surface_shapes: list[pymunk.Circle] = []
        for idx in range(len(nodes)):
            offset = inward_offsets.get(idx, (0, 0))
            shape = pymunk.Circle(nodes[idx], node_radius, offset=offset)
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
            node_density=node_density,
            pressure=pressure,
            velocity_damping=velocity_damping,
            rest_area=rest_area,
            topology="radial",
        ))

        return entity
