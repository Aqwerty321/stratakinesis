# strata/rigs/gear_train.py
# GearTrainRig — a row of circle gears linked by GearJoints, with a motor.
# Gears are drawn with parametric trapezoidal teeth via GearTrainRig.draw().

from __future__ import annotations
import math

from strata.rigs.base import Rig, JointHandle
from strata.rigs.gear_utils import gear_polygon, select_num_teeth, initial_tooth_phases, build_local_tooth_polygon
from strata.shapes.factory import Sprite


_PALETTE: list[tuple] = [
    (100, 180, 255, 230),
    (255, 120,  80, 230),
    ( 80, 220, 130, 230),
    (230, 190,  50, 230),
    (255, 130, 220, 230),
    (130, 210, 255, 230),
]


class GearTrainRig(Rig):
    """A row of circular gears connected by GearJoints, driven by a motor.

    Gears are placed tangentially (each pair just touching).  The GearJoint
    ratio is derived from the integer tooth counts so that the visual tooth
    meshing matches the physics constraint exactly.

    All gears are pinned to the world via PivotJoints at their centres.
    A SimpleMotor drives the first gear; all others follow via gear ratios.

    Visual rendering
    ----------------
    The normal Sprite.circle is kept for collision, but you should call
    ``rig.draw(surface, camera)`` from a ``game.on_draw`` hook to draw
    the proper tooth profiles using ``pygame.gfxdraw``.

    Tooth geometry parameters
    -------------------------
    tooth_frac : float
        Width of each tooth at pitch-circle level as a fraction of the
        tooth pitch arc.  Range (0, 1); default 0.46.
    tip_frac : float
        Width of the flat tooth tip as a fraction of the pitch arc.
        Must be < tooth_frac.  Default 0.26.
    teeth_per_unit : float
        Controls how many teeth are generated per world-unit of radius.
        Higher → smaller / more teeth; lower → fewer / chunkier teeth.
        Default 14.0.

    Parameters
    ----------
    radii       : list of gear radii, one per gear (left to right).
    x, y        : world position of the *first* gear's centre.
    motor_rate  : initial motor angular velocity (rad/s).
    motor_force : motor max torque (N·m).
    density     : mass density for each gear.
    colors      : optional per-gear RGBA colours (cycles through palette).
    tooth_frac  : see above.
    tip_frac    : see above.
    teeth_per_unit : see above.

    Attributes
    ----------
    gears        : list of gear entities (left to right).
    motor        : JointHandle for the SimpleMotor — set ``.rate`` to change speed.
    num_teeth    : list of integer tooth counts per gear.
    module       : shared gear module (world units per tooth).
    centres      : list of (x, y) world-space gear centres.

    Usage::

        gears = GearTrainRig(radii=[0.4, 0.8, 0.4], x=-2, y=1, motor_rate=3.0)
        game.scene.add_rig(gears)
        # In your on_draw callback:
        game.on_draw = lambda surf, cam: gears.draw(surf, cam)
    """

    def __init__(
        self,
        radii: list[float],
        x: float = 0.0,
        y: float = 0.0,
        motor_rate: float = 0.0,
        motor_force: float = 1e7,
        density: float = 1.0,
        colors: list[tuple] | None = None,
        tooth_frac: float = 0.46,
        tip_frac: float = 0.26,
        teeth_per_unit: float = 14.0,
        lock_frac: float = 0.15,
    ) -> None:
        super().__init__()

        if not radii:
            raise ValueError("GearTrainRig requires at least one radius")

        palette = colors or _PALETTE
        self.gears: list = []

        # ── tooth geometry ───────────────────────────────────────────────────
        self.tooth_frac     = tooth_frac
        self.tip_frac       = tip_frac
        self.lock_frac      = lock_frac
        self.num_teeth, self.module = select_num_teeth(radii, teeth_per_unit)
        self._tooth_phases  = initial_tooth_phases(self.num_teeth, lock_frac)
        self._colors        = [palette[i % len(palette)] for i in range(len(radii))]

        # ── pre-build local-space tooth polygons (P1 trig cache) ─────────────
        # All sin/cos computed once here; draw() applies a single rotation per gear.
        self._local_tooth_pts: list[list[tuple[float, float]]] = [
            build_local_tooth_polygon(
                radii[i], self.num_teeth[i],
                tooth_frac, tip_frac, self.module,
            )
            for i in range(len(radii))
        ]

        # ── gear centres: place left-to-right tangentially ───────────────────
        self.centres: list[tuple[float, float]] = [(x, y)]
        for i in range(1, len(radii)):
            self.centres.append((self.centres[-1][0] + radii[i - 1] + radii[i], y))

        self._radii = list(radii)

        # ── create Sprite.circle entities (used for collision) ───────────────
        for i, r in enumerate(radii):
            cx, cy_ = self.centres[i]
            gear = Sprite.circle(
                radius=r,
                x=cx,
                y=cy_,
                density=density,
                color=self._colors[i],  # same color as teeth: body fill shows between teeth
            )
            self._entities.append(gear)
            self.gears.append(gear)

        # ── pin each gear to the world at its centre ─────────────────────────
        for i, gear in enumerate(self.gears):
            h = JointHandle()
            cx, cy_ = self.centres[i]
            self._add_spec('pivot', gear, None, h, pivot=(cx, cy_))

        # ── GearJoint between each adjacent pair ─────────────────────────────
        # Meshing gears counter-rotate, so ratio must be negative:
        #   pymunk constraint: a.angle - b.angle * ratio = phase
        #   with ratio = -N_a/N_b, spinning a CCW spins b CW ✓
        for i in range(len(radii) - 1):
            ratio = -(self.num_teeth[i] / self.num_teeth[i + 1])
            h = JointHandle()
            self._add_spec(
                'gear',
                self.gears[i],
                self.gears[i + 1],
                h,
                phase=0.0,
                ratio=ratio,
            )

        # ── motor on the first gear ──────────────────────────────────────────
        motor_handle = JointHandle()
        motor_handle._pending['rate'] = motor_rate
        motor_handle._pending['max_force'] = motor_force
        self._add_spec(
            'motor', self.gears[0], None, motor_handle,
            rate=motor_rate, max_force=motor_force,
        )
        self.motor: JointHandle = motor_handle

    # ------------------------------------------------------------------
    # Visual drawing (call from game.on_draw)
    # ------------------------------------------------------------------

    def draw(self, surface: "pygame.Surface", camera: "Camera") -> None:  # type: ignore[name-defined]
        """Draw all gears with parametric trapezoidal teeth.

        Call this from a ``game.on_draw`` callback *after* the scene has been
        drawn so that the gear shapes render on top of any background.

        Example::

            game.on_draw = lambda surf, cam: gear_train.draw(surf, cam)
        """
        import pygame.gfxdraw
        from strata.ecs.components import Physics

        for i, gear in enumerate(self.gears):
            phys: Physics | None = gear.get_component(Physics)
            if phys is None:
                continue

            body_angle = phys.body.angle         # rotation from physics
            cx, cy     = self.centres[i]
            r          = self._radii[i]
            n          = self.num_teeth[i]
            phase      = self._tooth_phases[i]
            base_color = self._colors[i]

            # Tooth polygon in screen space — one cos/sin per gear (P1 cache)
            raw_angle = body_angle + phase
            cos_a = math.cos(raw_angle)
            sin_a = math.sin(raw_angle)
            pts = [
                camera.world_to_screen(
                    cx + lx * cos_a - ly * sin_a,
                    cy + lx * sin_a + ly * cos_a,
                )
                for lx, ly in self._local_tooth_pts[i]
            ]

            if len(pts) < 3:
                continue

            # Body fill
            pygame.gfxdraw.filled_polygon(surface, pts, base_color)

            # Subtly darker anti-aliased outline
            r_out, g_out, b_out = base_color[0], base_color[1], base_color[2]
            outline = (
                max(0, r_out - 40),
                max(0, g_out - 40),
                max(0, b_out - 40),
                255,
            )
            pygame.gfxdraw.aapolygon(surface, pts, outline)

            # Hub circle (small filled circle at gear centre)
            sx, sy   = camera.world_to_screen(cx, cy)
            hub_px   = max(2, camera.scale_length(self.module * 0.8))
            pygame.gfxdraw.filled_circle(surface, sx, sy, hub_px, outline)
            pygame.gfxdraw.aacircle(surface, sx, sy, hub_px, outline)



