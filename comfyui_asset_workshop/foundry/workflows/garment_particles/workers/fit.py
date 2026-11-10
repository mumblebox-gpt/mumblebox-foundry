"""Blender worker for garment alignment, skin transfer and sampled pose checks."""
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def load_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return set(bpy.data.objects) - before


def surface(obj, evaluated=False):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    target = obj.evaluated_get(depsgraph) if evaluated else obj
    data = target.to_mesh() if evaluated else target.data
    try:
        points = [target.matrix_world @ vertex.co for vertex in data.vertices]
        faces = [tuple(face.vertices) for face in data.polygons]
        return BVHTree.FromPolygons(points, faces)
    finally:
        if evaluated:
            target.to_mesh_clear()


def closed_body(body):
    # glTF can split a vertex at UV seams. Weld a check copy only.
    bm = bmesh.new()
    try:
        bm.from_mesh(body.data)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.00001)
        if not bm.faces or any(not edge.is_manifold for edge in bm.edges):
            raise ValueError("Use a character with one closed skin-weighted body mesh.")
        if bm.calc_volume(signed=True) <= 0:
            raise ValueError("The character body needs consistent outward normals.")
    finally:
        bm.free()


def find_target(objects):
    rigs = [obj for obj in objects if obj.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError("Use a GLB with exactly one character armature.")
    rig = rigs[0]
    rig.data.pose_position = "REST"
    bodies = [obj for obj in objects if obj.type == "MESH" and
              any(mod.type == "ARMATURE" and mod.object == rig for mod in obj.modifiers)]
    if not bodies:
        raise ValueError("The character GLB must have a skin-weighted body mesh.")
    body = max(bodies, key=lambda obj: len(obj.data.polygons))
    if len(body.data.polygons) > 250000:
        raise ValueError("Choose a character body with no more than 250,000 polygons for fitting.")
    closed_body(body)
    bpy.context.view_layer.update()
    return rig, body


def align(cloth, bvh, options):
    world = cloth.matrix_world.copy()
    offset = Vector([options["x"], options["y"], options["z"]])
    cloth.data.transform(Matrix.Translation(offset) @ Matrix.Scale(options["scale"], 4) @ world)
    cloth.matrix_world = Matrix.Identity(4)
    distances = []
    moved = 0
    clearance = options["clearance"] / 1000
    for vertex in cloth.data.vertices:
        point, normal, _, distance = bvh.find_nearest(vertex.co)
        distances.append(distance)
        signed = (vertex.co - point).dot(normal)
        if -0.025 <= signed < clearance and distance < 0.035:
            vertex.co += (clearance - signed) * normal
            moved += 1
    distances.sort()
    if distances[len(distances) // 2] > .15:
        raise ValueError("The garment is too far from the body. Adjust its scale and position and try again.")
    cloth.data.update()
    return moved


def skin(cloth, body, rig):
    bpy.context.view_layer.objects.active = cloth
    cloth.select_set(True)
    bones = {bone.name for bone in rig.data.bones if bone.use_deform}
    for group in body.vertex_groups:
        if group.name in bones:
            cloth.vertex_groups.new(name=group.name)
    if not cloth.vertex_groups:
        raise ValueError("The character body has no deformation weights to transfer.")
    mod = cloth.modifiers.new("Body skin weight transfer", "DATA_TRANSFER")
    mod.object = body
    mod.use_vert_data = True
    mod.data_types_verts = {"VGROUP_WEIGHTS"}
    mod.vert_mapping = "POLYINTERP_NEAREST"
    mod.layers_vgroup_select_src = "ALL"
    mod.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.modifier_apply(modifier=mod.name)

    totals = {}
    for vert in cloth.data.vertices:
        values = sorted(((entry.group, entry.weight) for entry in vert.groups
                         if cloth.vertex_groups[entry.group].name in bones and entry.weight > 0.0001),
                        key=lambda entry: entry[1], reverse=True)[:4]
        if not values:
            raise ValueError("Some garment vertices could not receive body skin weights. Adjust the fit.")
        for group in [entry.group for entry in vert.groups]:
            cloth.vertex_groups[group].remove([vert.index])
        weight_sum = sum(weight for _, weight in values)
        for group, weight in values:
            weight /= weight_sum
            vertex_group = cloth.vertex_groups[group]
            vertex_group.add([vert.index], weight, "REPLACE")
            totals[vertex_group.name] = totals.get(vertex_group.name, 0) + weight
    armature = cloth.modifiers.new("Character armature", "ARMATURE")
    armature.object = rig
    world = cloth.matrix_world.copy()
    cloth.parent = rig
    cloth.matrix_world = world
    return sorted(totals, key=totals.get, reverse=True)


def collision_report(name, cloth, body):
    bpy.context.view_layer.update()
    bvh = surface(body, evaluated=True)
    target = cloth.evaluated_get(bpy.context.evaluated_depsgraph_get())
    penetrations = []
    for vertex in target.data.vertices:
        pos = target.matrix_world @ vertex.co
        point, normal, _, _ = bvh.find_nearest(pos)
        depth = -(pos - point).dot(normal)
        if depth > .001:
            penetrations.append(depth)
    return {"name": name, "penetrating": len(penetrations),
            "max_depth_mm": round(max(penetrations, default=0) * 1000, 2)}


def pose_checks(cloth, body, rig, weighted_bones):
    rig.animation_data_clear()
    rig.data.pose_position = "POSE"
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    results = [collision_report("Rest", cloth, body)]
    # These are diagnostic stress poses. Preserve the original armature rest transforms.
    movable = [name for name in weighted_bones if rig.pose.bones[name].parent][:2]
    for name in movable:
        bone = rig.pose.bones[name]
        for degrees in (-18, 18):
            bone.matrix_basis = Matrix.Rotation(math.radians(degrees), 4, "X")
            results.append(collision_report(f"{name} {degrees:+d} degrees", cloth, body))
        bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    return results


def reimport(path, expected_faces):
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    if path.suffix == ".glb":
        load_glb(path)
    else:
        bpy.ops.import_scene.fbx(filepath=str(path))
    # Blender adds its own non-exported mesh for glTF bone display.
    bone_shapes = {bone.custom_shape for obj in bpy.context.scene.objects if obj.type == "ARMATURE"
                   for bone in obj.pose.bones if bone.custom_shape is not None}
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj not in bone_shapes]
    if len(meshes) != 1:
        raise ValueError(f"{path.suffix[1:].upper()} round-trip imported {len(meshes)} garment meshes. Expected one.")
    mesh = meshes[0]
    if (len(mesh.data.polygons) != expected_faces or not mesh.data.uv_layers or
        not mesh.data.materials or not any(mod.type == "ARMATURE" for mod in mesh.modifiers)
        or any(not vertex.groups for vertex in mesh.data.vertices)):
        raise ValueError("The exported wearable lost geometry, UVs, material or skin weights on re-import.")


def main(request):
    output = Path(request["output"])
    clear_scene()
    rig, body = find_target(load_glb(request["character"]))
    pieces = [obj for obj in load_glb(request["mesh"]) if obj.type == "MESH"]
    if not pieces:
        raise ValueError("The sewn garment did not contain polygon panels.")
    bpy.ops.object.select_all(action="DESELECT")
    for piece in pieces:
        piece.select_set(True)
    bpy.context.view_layer.objects.active = pieces[0]
    if len(pieces) > 1:
        bpy.ops.object.join()
    cloth = pieces[0]
    cloth.name = "Wearable garment"
    if not cloth.data.uv_layers:
        raise ValueError("The garment is missing the pattern UVs.")
    moved = 0 if request.get("approved_drape") else align(cloth, surface(body), request)
    weighted = skin(cloth, body, rig)
    poses = pose_checks(cloth, body, rig, weighted)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    cloth.select_set(True)
    bpy.context.view_layer.objects.active = cloth
    faces = len(cloth.data.polygons)
    vertices = len(cloth.data.vertices)
    glb, fbx = output / "wearable.glb", output / "wearable.fbx"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True,
                              export_animations=False, export_yup=True)
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, add_leaf_bones=False, bake_anim=False,
                             axis_forward="-Z", axis_up="Y", path_mode="COPY", embed_textures=True)
    for path in (glb, fbx):
        reimport(path, faces)
    report = {"triangles": faces, "vertices": vertices, "skin_bones": len(weighted), "max_weights": 4,
              "clearance_adjusted_vertices": moved, "pose_checks": poses,
              "round_trip": ["GLB", "FBX"], "needs_review": len(poses) == 1 or any(pose["penetrating"] for pose in poses)}
    (output / "fit-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        request = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
        main(request)
    except Exception as error:
        print("ValueError:", error, flush=True)
        raise

