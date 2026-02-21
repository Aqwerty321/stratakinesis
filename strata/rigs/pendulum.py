# strata/rigs/pendulum.py
# PendulumRig — one or more bob masses hanging from a world anchor.

from __future__ import annotations

from strata.rigs.base import Rig, JointHandle
from strata.shapes.factory import Sprite


_DEFAULT_COLOR: tuple = (100, 180, 255, 230)


class PendulumRig(Rig):
    """One or more pendulum bobs hanging from a world anchor point.

    ``length=1`` creates a simple single pendulum.
    ``length>1`` chains bobs so each one hangs from the previous
    (double / N-tuple pendulum).

    Connections use ``PinJoint`` which maintains the arm distance while
    allowing free rotation — equivalent to a massless rigid rod.

    Parameters
    ----------
    length      : number of bobs.
    bob_radius  : collision + visual radius of each bob.
    arm_length  : initial distance from anchor to first bob, and between
                  subsequent bobs.
    anchor      : world-space pivot point at the top.
    density     : mass density of each bob.
    color       : RGBA fill colour.

    Attributes
    ----------
    bobs : list of bob circle entities (top to bottom).

    Usage::

        # Simple pendulum
        pend = PendulumRig(anchor=(0, 4))
        game.scene.add_rig(pend)

        # Double pendulum
        pend = PendulumRig(length=2, anchor=(-2, 4))
        game.scene.add_rig(pend)
    """

    def __init__(
        self,
        length: int = 1,
        bob_radius: float = 0.25,
        arm_length: float = 1.5,
        anchor: tuple[float, float] = (0.0, 3.0),
        density: float = 1.0,
        color: tuple = _DEFAULT_COLOR,
        damping: float = 1.0,
    ) -> None:
        super().__init__()
        self.bobs: list = []
        self.anchor: tuple[float, float] = anchor
        self._bob_radius = bob_radius
        self._rod_color: tuple = (60, 110, 170, 255)

        ax, ay = anchor
        for i in range(length):
            bob = Sprite.circle(
                radius=bob_radius,
                x=ax,
                y=ay - arm_length * (i + 1),
                density=density,
                color=color,
                linear_damping=damping,
                angular_damping=damping,
            )
            self._entities.append(bob)
            self.bobs.append(bob)

        # First bob: PinJoint to world anchor.
        # PinJoint(body_a, body_b, anchor_a, anchor_b) maintains the initial
        # distance between the two anchor points.  body_b is the world static
        # body (at origin); anchor_b in world coords = the anchor point itself.
        h = JointHandle()
        self._add_spec(
            'pin',
            self.bobs[0],
            None,  # world static body
            h,
            anchor_a=(0.0, 0.0),       # bob centre in local coords
            anchor_b=(ax, ay),          # anchor in static body local = world
        )

        # Subsequent bobs: PinJoint between adjacent bobs at their centres.
        for i in range(1, length):
            h = JointHandle()
            self._add_spec(
                'pin',
                self.bobs[i],
                self.bobs[i - 1],
                h,
                anchor_a=(0.0, 0.0),
                anchor_b=(0.0, 0.0),
            )

    # ------------------------------------------------------------------
    def draw(self, surface, camera) -> None:  # type: ignore[override]
        """Draw rods connecting anchor → bob[0] → bob[1] → …

        Call this inside ``game.on_draw`` so that rods are rendered on
        top of the physics debug layer but below the F3 overlay.
        """
        import pygame
        import pygame.gfxdraw
        from strata.ecs.components import Physics

        rod_w = max(3, int(0.07 * camera.scale))
        cap_r = rod_w // 2           # circle cap radius = half rod width
        col   = self._rod_color

        prev_sx, prev_sy = camera.world_to_screen(*self.anchor)

        for bob in self.bobs:
            phys = bob.get_component(Physics)
            if phys is None:
                continue
            bx, by = phys.body.position
            sx, sy = camera.world_to_screen(bx, by)

            # Filled thick line segment (body of the rod)
            pygame.draw.line(surface, col, (prev_sx, prev_sy), (sx, sy), rod_w)
            # Round caps so the rod looks smooth at the joints
            pygame.gfxdraw.filled_circle(surface, prev_sx, prev_sy, cap_r, col)
            pygame.gfxdraw.aacircle(surface,     prev_sx, prev_sy, cap_r, col)
            pygame.gfxdraw.filled_circle(surface, sx, sy, cap_r, col)
            pygame.gfxdraw.aacircle(surface,     sx, sy, cap_r, col)

            prev_sx, prev_sy = sx, sy
