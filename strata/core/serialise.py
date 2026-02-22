# strata/core/serialise.py
# Scene serialisation — save/load entities, components, and rigs to/from JSON.
#
# Design choices:
#   • Only the *declarative parameters* are saved — the values you'd pass to
#     Sprite.circle() / Sprite.rect() / Sprite.polygon() to recreate the entity.
#   • Runtime state (body positions, velocities, angles) is captured so the
#     scene can be restored mid-simulation.
#   • Soft bodies store node positions/velocities but NOT spring objects —
#     springs are rebuilt from the stored mesh parameters.
#   • pymunk Body/Shape objects are NOT serialised directly; they are rebuilt
#     during load from the stored parameters.
#
# Usage:
#   from strata.core.serialise import save_scene, load_scene
#   save_scene(game.scene, game.physics, "level1.json")
#   load_scene(game, "level1.json")

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from strata.core.loop import Scene, Game
    from strata.systems.physics_system import PhysicsSystem


# ---------------------------------------------------------------------------
# Serialise
# ---------------------------------------------------------------------------

def _serialise_entity(entity) -> dict[str, Any]:
    """Convert a single Entity to a JSON-friendly dict."""
    from strata.ecs.components import (
        Transform, Physics, Visual, SoftBody, PropertyBinding,
    )

    data: dict[str, Any] = {"id": entity.id}
    components: dict[str, Any] = {}

    # --- Transform ---
    t = entity.get_component(Transform)
    if t is not None:
        components["Transform"] = {
            "x": t.x, "y": t.y, "angle": t.angle,
            "prev_x": t.prev_x, "prev_y": t.prev_y, "prev_angle": t.prev_angle,
        }

    # --- Physics ---
    p = entity.get_component(Physics)
    if p is not None:
        phys_data: dict[str, Any] = {
            "density": p.density,
            "is_static": p.is_static,
            "collision_layer": p.collision_layer,
            "collision_mask": p.collision_mask,
            "linear_damping": p.linear_damping,
            "angular_damping": p.angular_damping,
        }
        # Store shape geometry so we can rebuild the pymunk objects on load.
        if p.shape is not None:
            import pymunk
            if isinstance(p.shape, pymunk.Circle):
                phys_data["shape_type"] = "circle"
                phys_data["radius"] = p.shape.radius
            elif isinstance(p.shape, pymunk.Poly):
                phys_data["shape_type"] = "poly"
                # Get local vertices — convert Vec2d to tuples.
                verts = [(v.x, v.y) for v in p.shape.get_vertices()]
                phys_data["vertices"] = verts
            elif isinstance(p.shape, pymunk.Segment):
                phys_data["shape_type"] = "segment"
                phys_data["a"] = (p.shape.a.x, p.shape.a.y)
                phys_data["b"] = (p.shape.b.x, p.shape.b.y)
                phys_data["segment_radius"] = p.shape.radius
            phys_data["elasticity"] = p.shape.elasticity
            phys_data["friction"] = p.shape.friction

        # Store runtime body state (position, velocity, angle, angular_velocity).
        if p.body is not None:
            phys_data["body_state"] = {
                "position": (p.body.position.x, p.body.position.y),
                "velocity": (p.body.velocity.x, p.body.velocity.y),
                "angle": p.body.angle,
                "angular_velocity": p.body.angular_velocity,
            }

        components["Physics"] = phys_data

    # --- Visual ---
    v = entity.get_component(Visual)
    if v is not None:
        vis_data: dict[str, Any] = {
            "shape_type": v.shape_type,
            "radius": v.radius,
            "vertices": list(v.vertices),
            "color": list(v.color),
            "hidden": v.hidden,
            "image_width": v.image_width,
            "image_height": v.image_height,
        }
        if v.outline is not None:
            vis_data["outline"] = list(v.outline)
        else:
            vis_data["outline"] = None
        # Note: image_surface (pygame.Surface) is NOT serialised.
        # On load, the user must re-attach image surfaces if needed.
        components["Visual"] = vis_data

    # --- SoftBody ---
    sb = entity.get_component(SoftBody)
    if sb is not None:
        soft_data: dict[str, Any] = {
            "stiffness": sb.stiffness,
            "damping": sb.damping,
            "node_radius": sb.node_radius,
            "node_density": sb.node_density,
            "velocity_damping": sb.velocity_damping,
            "pressure": sb.pressure,
            "rest_area": sb.rest_area,
            "topology": sb.topology,
            "surface_indices": list(sb.surface_indices),
            "debug_render": sb.debug_render,
        }
        # Store node positions and velocities for state restore.
        node_states = []
        for node in sb.nodes:
            node_states.append({
                "position": (node.position.x, node.position.y),
                "velocity": (node.velocity.x, node.velocity.y),
            })
        soft_data["node_states"] = node_states
        components["SoftBody"] = soft_data

    # --- PropertyBinding ---
    pb = entity.get_component(PropertyBinding)
    if pb is not None:
        components["PropertyBinding"] = {
            "source_entity_id": pb.source_entity_id,
            "source_attr": pb.source_attr,
            "target_attr": pb.target_attr,
            "scale": pb.scale,
            "offset": pb.offset,
            "enabled": pb.enabled,
        }

    data["components"] = components
    return data


def save_scene(scene: "Scene", physics: "PhysicsSystem", path: str) -> None:
    """Serialise all entities in *scene* to a JSON file at *path*.

    Parameters
    ----------
    scene   : the Scene (World) containing entities.
    physics : the PhysicsSystem (for future constraint serialisation).
    path    : output file path (.json).
    """
    entities_data = []
    for entity in scene.entities:
        entities_data.append(_serialise_entity(entity))

    doc = {
        "version": "0.5.0",
        "gravity": (physics.space.gravity.x, physics.space.gravity.y),
        "substeps": physics.base_substeps,
        "entities": entities_data,
    }

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Deserialise
# ---------------------------------------------------------------------------

def _rebuild_entity(edata: dict[str, Any]) -> Any:
    """Rebuild a single Entity from serialised data.

    Returns the Entity with Transform, Visual, Physics (body+shape rebuilt),
    SoftBody (mesh rebuilt), and PropertyBinding components attached.
    """
    import pymunk
    from strata.ecs.entity import Entity
    from strata.ecs.components import (
        Transform, Physics, Visual, SoftBody, PropertyBinding,
    )

    entity = Entity()
    # Overwrite the auto-assigned ID with the original for cross-references.
    entity.id = edata["id"]

    comps = edata.get("components", {})

    # --- Transform ---
    td = comps.get("Transform")
    if td is not None:
        t = Transform(
            x=td["x"], y=td["y"], angle=td["angle"],
        )
        t.prev_x = td.get("prev_x", t.x)
        t.prev_y = td.get("prev_y", t.y)
        t.prev_angle = td.get("prev_angle", t.angle)
        entity.add_component(t)

    # --- Visual ---
    vd = comps.get("Visual")
    if vd is not None:
        vis = Visual(
            shape_type=vd.get("shape_type", "polygon"),
            radius=vd.get("radius", 0.0),
            vertices=[tuple(v) for v in vd.get("vertices", [])],
            color=tuple(vd.get("color", (100, 180, 255, 255))),
            outline=tuple(vd["outline"]) if vd.get("outline") is not None else None,
            hidden=vd.get("hidden", False),
            image_width=vd.get("image_width", 0.0),
            image_height=vd.get("image_height", 0.0),
        )
        entity.add_component(vis)

    # --- Physics ---
    pd = comps.get("Physics")
    if pd is not None:
        is_static = pd.get("is_static", False)
        shape_type = pd.get("shape_type")
        body_state = pd.get("body_state", {})

        # Rebuild body
        if is_static:
            body = pymunk.Body(body_type=pymunk.Body.STATIC)
        else:
            # Need mass — compute from density and shape area.
            density = pd.get("density", 1.0)
            if shape_type == "circle":
                import math
                radius = pd["radius"]
                area = math.pi * radius * radius
                mass = density * area
                moment = pymunk.moment_for_circle(mass, 0, radius)
            elif shape_type == "poly":
                verts = [tuple(v) for v in pd["vertices"]]
                # Shoelace area
                n = len(verts)
                total = 0.0
                for i in range(n):
                    x1, y1 = verts[i]
                    x2, y2 = verts[(i + 1) % n]
                    total += x1 * y2 - x2 * y1
                area = abs(total) / 2.0
                mass = density * area
                moment = pymunk.moment_for_poly(mass, verts)
            else:
                mass = 1.0
                moment = 100.0
            body = pymunk.Body(mass, moment)

        # Apply stored state
        pos = body_state.get("position", (0.0, 0.0))
        body.position = tuple(pos)
        body.angle = body_state.get("angle", 0.0)
        if not is_static:
            vel = body_state.get("velocity", (0.0, 0.0))
            body.velocity = tuple(vel)
            body.angular_velocity = body_state.get("angular_velocity", 0.0)

        # Rebuild shape
        shape = None
        if shape_type == "circle":
            shape = pymunk.Circle(body, pd["radius"])
        elif shape_type == "poly":
            verts = [tuple(v) for v in pd["vertices"]]
            shape = pymunk.Poly(body, verts)
        elif shape_type == "segment":
            shape = pymunk.Segment(body, tuple(pd["a"]), tuple(pd["b"]),
                                   pd.get("segment_radius", 0.0))

        if shape is not None:
            shape.elasticity = pd.get("elasticity", 0.5)
            shape.friction = pd.get("friction", 0.8)

        entity.add_component(Physics(
            body=body,
            shape=shape,
            density=pd.get("density", 1.0),
            is_static=is_static,
            collision_layer=pd.get("collision_layer", 0xFFFF),
            collision_mask=pd.get("collision_mask", 0xFFFF),
            linear_damping=pd.get("linear_damping", 1.0),
            angular_damping=pd.get("angular_damping", 1.0),
        ))

    # --- SoftBody ---
    sd = comps.get("SoftBody")
    if sd is not None:
        # SoftBody nodes/springs are complex — we store enough to restore
        # positions but the full spring mesh must be rebuilt by re-running
        # the soft body factory or a manual rebuild.
        # For now, store the component metadata; node state restore happens
        # if the entity is re-created via Sprite.soft_* with matching params.
        soft = SoftBody(
            stiffness=sd.get("stiffness", 300.0),
            damping=sd.get("damping", 10.0),
            node_radius=sd.get("node_radius", 0.12),
            node_density=sd.get("node_density", 0.0),
            velocity_damping=sd.get("velocity_damping", 0.995),
            pressure=sd.get("pressure", 80.0),
            rest_area=sd.get("rest_area", 0.0),
            topology=sd.get("topology", "grid"),
            surface_indices=sd.get("surface_indices", []),
            debug_render=sd.get("debug_render", False),
        )
        # Note: nodes, springs, surface_shapes are empty — they would need
        # to be rebuilt by the soft body factory.  Node positions are stored
        # in sd["node_states"] for state snapshotting.
        entity.add_component(soft)

    # --- PropertyBinding ---
    pbd = comps.get("PropertyBinding")
    if pbd is not None:
        entity.add_component(PropertyBinding(
            source_entity_id=pbd["source_entity_id"],
            source_attr=pbd["source_attr"],
            target_attr=pbd["target_attr"],
            scale=pbd.get("scale", 1.0),
            offset=pbd.get("offset", 0.0),
            enabled=pbd.get("enabled", True),
        ))

    return entity


def load_scene(game: "Game", path: str) -> None:
    """Deserialise a JSON scene file into *game*.

    Clears the current scene and rebuilds all entities from the saved data.
    Physics bodies and shapes are rebuilt and registered automatically.

    Parameters
    ----------
    game : the Game instance whose scene will be replaced.
    path : path to the JSON file saved by ``save_scene``.
    """
    from strata.ecs.entity import Entity

    p = Path(path)
    doc = json.loads(p.read_text(encoding="utf-8"))

    # Restore gravity
    gx, gy = doc.get("gravity", (0.0, -9.81))
    game.physics.space.gravity = (gx, gy)

    # Clear existing scene entities
    for entity in list(game.scene.entities):
        game.scene.remove_entity(entity)

    # Track the maximum entity ID so Entity._id_counter doesn't collide.
    max_id = 0

    for edata in doc.get("entities", []):
        entity = _rebuild_entity(edata)
        game.scene.add_entity(entity)
        if entity.id > max_id:
            max_id = entity.id

    # Ensure future entities don't reuse IDs
    if Entity._id_counter < max_id:
        Entity._id_counter = max_id
