"""Blender-bundled CPU worker for rigging a self-contained Foundry GLB."""
import json
from math import radians
from pathlib import Path
import sys

import bpy
from mathutils import Quaternion, Vector
from mathutils.kdtree import KDTree
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from geometry import CHAINS
from weights import apply_target, brush_value

POSE_FRAMES = {"rest":1, "elbow":13, "arms":25, "crouch":37, "finger":49, "tail":61, "wing":73,
               "finger_left":85, "finger_right":97, "finger_spread":109, "toe":121}


def select(*objects, active):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def gltf_to_world(point):
    return Vector((point[0], -point[2], point[1]))


def create_armature(joints, height):
    bones = [{"id": start, "head": joints[start], "tail": joints[end], "parent_id": parent}
             for start, end, parent in CHAINS]
    return create_detailed_armature(bones)


def create_detailed_armature(bones):
    data = bpy.data.armatures.new("Foundry skeleton")
    rig = bpy.data.objects.new("Foundry character rig", data)
    bpy.context.collection.objects.link(rig)
    rig.show_in_front = True
    select(rig, active=rig)
    bpy.ops.object.mode_set(mode="EDIT")
    for spec in bones:
        head, tail = gltf_to_world(spec["head"]), gltf_to_world(spec["tail"])
        if (tail-head).length < 1e-7:
            raise ValueError("Separate the two joints of each bone before binding.")
        bone = data.edit_bones.new(spec["id"])
        bone.head, bone.tail = head, tail
        bone.roll = spec.get("roll", 0)
        bone.use_deform = spec.get("deform", True)
    for spec in bones:
        bone = data.edit_bones[spec["id"]]
        parent = spec.get("parent_id")
        if parent:
            bone.parent = data.edit_bones[parent]
            bone.use_connect = spec.get("connected", (bone.head-bone.parent.tail).length < 1e-7)
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def voxel_weights(meshes, rig, height, proxy_resolution):
    copies = []
    for mesh in meshes:
        obj = mesh.copy()
        obj.data = mesh.data.copy()
        bpy.context.collection.objects.link(obj)
        copies.append(obj)
    select(*copies, active=copies[0])
    if len(copies) > 1:
        bpy.ops.object.join()
    helper = bpy.context.object
    modifier = helper.modifiers.new("Bounded anatomical volume", "REMESH")
    modifier.mode = "VOXEL"
    modifier.voxel_size = height / proxy_resolution
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    if not helper.data.polygons:
        bpy.data.objects.remove(helper, do_unlink=True)
        return None
    select(helper, rig, active=rig)
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    return helper


def transfer(mesh, helper, rig):
    deform = [bone for bone in rig.data.bones if bone.use_deform]
    if not deform:
        raise ValueError("Enable at least one deform bone before binding.")
    groups = {bone.name: mesh.vertex_groups.new(name=bone.name) for bone in deform}
    select(mesh, active=mesh)
    if helper is not None and any(v.groups for v in helper.data.vertices):
        modifier = mesh.modifiers.new("Transfer voxel weights", "DATA_TRANSFER")
        modifier.object = helper
        modifier.use_vert_data = True
        modifier.data_types_verts = {"VGROUP_WEIGHTS"}
        modifier.vert_mapping = "POLYINTERP_NEAREST"
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)
    unweighted = [v.index for v in mesh.data.vertices if not any(g.weight > 1e-6 for g in v.groups)]
    counts = {name: [] for name in groups}
    starts = np.array([tuple(b.head_local) for b in deform])
    directions = np.array([tuple(b.tail_local-b.head_local) for b in deform])
    length2 = (directions**2).sum(axis=1)
    names = list(groups)
    # Assign any remaining vertices by nearest segment, in bounded blocks.
    block_size = min(8192, 131072 // len(deform))
    for start in range(0, len(unweighted), block_size):
        block = unweighted[start:start+block_size]
        points = np.array([tuple(mesh.data.vertices[i].co) for i in block])
        offset = points[:,None,:]-starts[None,:,:]
        along = np.clip((offset*directions).sum(axis=2)/length2,0,1)
        nearest = ((offset-along[:,:,None]*directions)**2).sum(axis=2).argmin(axis=1)
        for index, bone in zip(block,nearest):
            counts[names[bone]].append(index)
    for name, indices in counts.items():
        if indices:
            groups[name].add(indices, 1, "REPLACE")
    attach_skin(mesh, rig)
    return len(unweighted)


def attach_skin(mesh, rig):
    world = mesh.matrix_world.copy()
    mesh.parent = rig
    mesh.matrix_world = world
    skin = mesh.modifiers.new("Foundry skin", "ARMATURE")
    skin.object = rig


def transfer_learned_weights(meshes, rig, bones, path, height):
    # The sampled positions share the exact GLB source frame. Interpolation
    # works across split UV/material vertices without relying on import order.
    with np.load(path, allow_pickle=False) as artifact:
        points, weights = artifact["points"], artifact["weights"]
        ids = artifact["bone_ids"].tolist() if "bone_ids" in artifact else None
    if (points.ndim != 2 or points.shape[1] != 3 or not 1 <= len(points) <= 65536 or
            weights.shape != (len(points), len(bones)) or not np.isfinite(points).all() or
            not np.isfinite(weights).all() or np.any(weights < 0)):
        raise ValueError("The learned weights do not match this skeleton.")
    if ids is not None:
        if len(ids) != len(bones) or set(ids) != {bone["id"] for bone in bones}:
            raise ValueError("The learned weight columns do not match these bone identities.")
        index = {bone_id: column for column, bone_id in enumerate(ids)}
        weights = weights[:, [index[bone["id"]] for bone in bones]]
    for index, bone in enumerate(bones):
        if not bone.get("deform", True):
            weights[:, index] = 0
    tree = KDTree(len(points))
    for index, point in enumerate(points):
        tree.insert(gltf_to_world(point), index)
    tree.balance()
    sample_count = min(8, len(points))
    influence_count = min(4, len(bones))
    maximum_distance = 0.0
    for mesh in meshes:
        groups = [mesh.vertex_groups.new(name=bone["id"]) for bone in bones]
        for start in range(0, len(mesh.data.vertices), 512):
            vertices = mesh.data.vertices[start:start+512]
            hits = [tree.find_n(vertex.co, sample_count) for vertex in vertices]
            indices = np.array([[item[1] for item in row] for row in hits])
            distances = np.array([[item[2] for item in row] for row in hits], dtype=np.float32)
            maximum_distance = max(maximum_distance, float(distances[:, 0].max()))
            mix = 1 / (distances + max(height * 1e-8, 1e-10))
            mix /= mix.sum(axis=1, keepdims=True)
            values = np.einsum("nk,nkj->nj", mix, weights[indices])
            best = np.argsort(-values, axis=1, kind="stable")[:, :influence_count]
            top = np.take_along_axis(values, best, axis=1)
            total = top.sum(axis=1, keepdims=True)
            if np.any(total <= 0):
                raise ValueError("Some vertices lack learned influences. Try another prediction or bind with Blender.")
            for vertex, row, influences in zip(vertices, best, top/total):
                for bone_index, weight in zip(row, influences):
                    if weight > 0:
                        groups[bone_index].add([vertex.index], float(weight), "REPLACE")
        attach_skin(mesh, rig)
    if maximum_distance > height * .08:
        raise ValueError("The learned weights do not align with the source mesh.")
    return maximum_distance


def make_poses(scene, rig, orientation, bones=None):
    guide = Quaternion((0,0,1), radians(90*orientation))
    right = guide @ Vector((1,0,0))
    front = guide @ Vector((0,-1,0))
    poses = {
        "rest": {},
        "elbow": {"elbow.R":(right,-80)},
        "arms": {"shoulder.L":(front,45),"shoulder.R":(front,-45)},
        "crouch": {"hip.L":(right,-28),"hip.R":(right,-28),"knee.L":(right,55),"knee.R":(right,55)},
    }
    roles = {}
    for spec in bones or ():
        role,side = spec.get("role"),spec.get("side")
        label = spec.get("landmark_label") or (f"{role}.{side}" if role and side else spec["id"])
        roles[label] = spec["id"]
    poses = {name: {roles.get(key, key): value for key, value in entries.items()
                    if roles.get(key, key) in rig.pose.bones}
             for name, entries in poses.items()}
    finger_roots = {}
    for spec in bones or ():
        if spec.get("role")=="finger" and spec.get("chain_segment",spec.get("segment",1))==1:
            finger_roots.setdefault(spec.get("part_id",spec.get("side","")),[]).append(spec)
    for spec in bones or ():
        role, bone = spec.get("role"), rig.data.bones[spec["id"]]
        group = {"wing_digit":"wing","feather":"wing"}.get(role,role)
        if group in ("finger", "tail", "wing", "toe"):
            axis = bone.matrix_local.to_quaternion() @ Vector((1, 0, 0))
            motion = (axis, {"finger":24,"toe":16}.get(group,14))
            poses.setdefault(group,{})[bone.name] = motion
            side = {"L":"finger_left","R":"finger_right"}.get(spec.get("side"))
            if group=="finger" and side:
                poses.setdefault(side,{})[bone.name] = motion
    for roots in finger_roots.values():
        roots.sort(key=lambda spec:spec["head"][2])
        for index,spec in enumerate(roots):
            bone = rig.data.bones[spec["id"]]
            axis = bone.matrix_local.to_quaternion() @ Vector((0, 0, 1))
            poses.setdefault("finger_spread",{})[bone.name] = (axis, (index-(len(roots)-1)/2)*8)
    frames = {name: frame for name, frame in POSE_FRAMES.items() if name == "rest" or poses.get(name)}
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, max(frames.values())
    for name, frame in frames.items():
        scene.timeline_markers.new(name.title(),frame=frame)
        for bone in rig.pose.bones:
            bone.rotation_mode = "QUATERNION"
            bone.rotation_quaternion = Quaternion()
            if bone.name in poses[name]:
                axis, angle = poses[name][bone.name]
                bone.rotation_quaternion = Quaternion(bone.bone.matrix_local.to_quaternion().inverted() @ axis, radians(angle))
            bone.keyframe_insert("rotation_quaternion", frame=frame, group=bone.name)
    rig.animation_data.action.name = "Foundry deformation checks"
    scene.frame_set(1)
    return {name:(frame-1)/24 for name, frame in frames.items()}


def correct_weights(meshes, edits):
    counts = {"strokes":len(edits), "changed_vertices":0, "rigid_vertices":0, "missed_strokes":0}
    if not edits:
        return counts
    hits = [0]*len(edits)
    budget = 2_000_000
    for mesh in meshes:
        groups = {group.name:group for group in mesh.vertex_groups}
        by_index = {group.index:group.name for group in groups.values()}
        tree = KDTree(len(mesh.data.vertices))
        for vertex in mesh.data.vertices:
            tree.insert(vertex.co, vertex.index)
        tree.balance()

        def weights(index):
            return {by_index[group.group]:group.weight for group in mesh.data.vertices[index].groups}

        for number, edit in enumerate(edits):
            target = edit["bone_id"]
            if target not in groups:
                continue
            radius, mode = edit["radius"], edit["mode"]
            locked = set(edit["locked"])
            affected = {}
            for point in edit["points"]:
                for _, index, distance in tree.find_range(gltf_to_world(point),radius):
                    falloff = 1. if mode == "rigid" else max(0.,1-distance/radius)
                    affected[index] = max(affected.get(index,0.),falloff)
            if len(affected) > budget:
                raise ValueError("These weight corrections cover too many vertices. Decrease the brush radius.")
            budget -= len(affected)
            hits[number] += len(affected)
            pending = {}
            for index, falloff in affected.items():
                old = weights(index)
                neighborhood = 0.
                if mode == "smooth":
                    near = tree.find_n(mesh.data.vertices[index].co,8)
                    neighbors = [weights(j).get(target,0.) for _,j,d in near if d<=radius]
                    neighborhood = sum(neighbors)/len(neighbors) if neighbors else old.get(target,0.)
                value = brush_value(mode,old.get(target,0.),edit["strength"]*falloff,edit["target"],neighborhood)
                changed = apply_target(old,target,value,locked)
                if changed != old:
                    pending[index] = (old,changed)
            for index,(old,changed) in pending.items():
                for name in old.keys()-changed.keys():
                    groups[name].remove([index])
                for name,weight in changed.items():
                    if old.get(name) != weight:
                        groups[name].add([index],weight,"REPLACE")
                if mode == "rigid" and changed.get(target,0.) >= .999999:
                    counts["rigid_vertices"] += 1
            counts["changed_vertices"] += len(pending)
    counts["missed_strokes"] = hits.count(0)
    return counts


def main(target):
    data = json.loads((target/"request.json").read_text(encoding="utf-8"))
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=data["source"])
    scene = bpy.context.scene
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if not meshes or any(obj.type == "ARMATURE" for obj in scene.objects):
        raise ValueError("Choose a static mesh rather than an already rigged asset.")
    bpy.context.view_layer.update()
    for mesh in meshes:
        world = mesh.matrix_world.copy()
        mesh.parent = None
        mesh.matrix_world = world
        select(mesh, active=mesh)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    method = data.get("binding_method", "voxel")
    bones = data.get("bones")
    rig = create_detailed_armature(bones) if bones else create_armature(data["joints"], data["height"])
    maximum_distance = None
    if method in ("learned", "conditioned"):
        maximum_distance = transfer_learned_weights(meshes, rig, bones, data["learned_weights"], data["height"])
        fallback = 0
    else:
        helper = voxel_weights(meshes, rig, data["height"], data.get("binding_settings", {}).get("proxy_resolution",110))
        fallback = sum(transfer(mesh,helper,rig) for mesh in meshes)
        if helper is not None:
            bpy.data.objects.remove(helper, do_unlink=True)
    corrections = correct_weights(meshes,data.get("weight_edits",[]))
    pose_seconds = make_poses(scene, rig, data["orientation"], bones)
    select(*meshes, rig, active=rig)
    for mesh in meshes:
        mesh.data.calc_loop_triangles()
    report = {
        "bones":len(rig.data.bones), "meshes":len(meshes), "triangles":sum(len(o.data.loop_triangles) for o in meshes),
        "vertices":sum(len(o.data.vertices) for o in meshes), "nearest_segment_vertices":fallback,
        "unweighted":sum(not any(g.weight>1e-6 for g in v.groups) for mesh in meshes for v in mesh.data.vertices),
        "pose_seconds":pose_seconds,
        "blender":bpy.app.version_string,
        "binding_method": method,
        "weight_sample_max_distance": maximum_distance,
        "weight_corrections":corrections,
        # Blender Y points down the bone. Convert each column to glTF Y-up world space.
        "rest_axes":{bone.name:[[x,z,-y] for x,y,z,_ in bone.matrix_local.col][:3] for bone in rig.data.bones},
    }
    if report["unweighted"]:
        raise ValueError("Some vertices did not get a skin weight.")
    bpy.ops.export_scene.gltf(filepath=str(target/"rig.glb"), export_format="GLB", use_selection=True, use_active_scene=True,
                             export_animations=True, export_animation_mode="ACTIONS", export_frame_range=True,
                             export_anim_slide_to_zero=True, export_all_influences=False)
    (target/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[sys.argv.index("--")+1]))
