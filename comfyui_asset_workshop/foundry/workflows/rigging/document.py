"""Versioned skeleton geometry, validation and legacy viewer projection."""
import hashlib
import json
import math
import re

from .geometry import CHAINS, numbers

SCHEMA_VERSION = 3
MAX_BONES = 512
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,48}")


def surface_anchor(value):
    primitive, triangle = value.get("primitive_id"), value.get("triangle_id")
    if (type(primitive) is not int or not 0 <= primitive < 4096
            or type(triangle) is not int or not 0 <= triangle < 2_000_000):
        raise ValueError("Use a triangle from the captured mesh.")
    coordinates = numbers(value.get("barycentric"), 3)
    if any(not -1e-6 <= value <= 1.000001 for value in coordinates) or abs(sum(coordinates) - 1) > 1e-6:
        raise ValueError("The marker must be on the selected triangle.")
    return {"primitive_id": primitive, "triangle_id": triangle, "barycentric": coordinates}


def validate_skeleton(skeleton):
    bones = skeleton.get("bones")
    if not isinstance(bones, list) or not 1 <= len(bones) <= MAX_BONES:
        raise ValueError(f"Use a skeleton with 1 to {MAX_BONES} bones.")
    lookup = {}
    for bone in bones:
        if not isinstance(bone, dict):
            raise ValueError("Each bone needs a valid structure.")
        bone_id = bone.get("id")
        if not isinstance(bone_id, str) or not _ID.fullmatch(bone_id) or bone_id in lookup:
            raise ValueError("Bone IDs must be valid and unique.")
        lookup[bone_id] = bone
        head, tail = numbers(bone.get("head"), 3), numbers(bone.get("tail"), 3)
        if max(map(abs, head + tail)) > 1e7 or math.dist(head, tail) < 1e-7:
            raise ValueError("Keep bone endpoints finite and separated.")
        roll = numbers([bone.get("roll", 0)], 1)[0]
        if abs(roll) > math.tau:
            raise ValueError("Bone roll must be within one full turn.")
        for field in ("deform", "connected", "locked"):
            if field in bone and type(bone[field]) is not bool:
                raise ValueError("Invalid bone flag.")
        label = bone.get("label", bone_id)
        if not isinstance(label, str) or not 1 <= len(label) <= 100:
            raise ValueError("Choose a bone label of up to 100 characters.")
    for bone in bones:
        parent = bone.get("parent_id")
        if parent is not None and (not isinstance(parent, str) or parent not in lookup):
            raise ValueError("Each bone parent must exist in this skeleton.")
        if bone.get("connected") and (parent is None or math.dist(bone["head"], lookup[parent]["tail"]) > 1e-6):
            raise ValueError("A connected bone must start at its parent's tip.")
        mirror = bone.get("mirror_id")
        if mirror is not None and (not isinstance(mirror, str) or mirror == bone["id"] or
                                   mirror not in lookup or lookup[mirror].get("mirror_id") != bone["id"]):
            raise ValueError("Paired bones must refer to one another.")
    checked = set()
    for bone_id in lookup:
        ancestors = set()
        while bone_id is not None and bone_id not in checked:
            if bone_id in ancestors:
                raise ValueError("A bone cannot be its own ancestor.")
            ancestors.add(bone_id)
            bone_id = lookup[bone_id].get("parent_id")
        checked.update(ancestors)
    return skeleton


def guided_skeleton(joints):
    bones = []
    for start, end, parent in CHAINS:
        bone = {"id": start, "label": start, "parent_id": parent,
                "head": joints[start], "tail": joints[end], "roll": 0,
                "deform": True, "connected": False, "legacy_tip": end}
        if start.endswith((".L", ".R")):
            bone["mirror_id"] = start[:-1] + ("R" if start.endswith("L") else "L")
        if parent:
            anchor = next(prior for prior in bones if prior["id"] == parent)
            bone["connected"] = math.dist(anchor["tail"], bone["head"]) <= 1e-7
        bones.append(bone)
    return validate_skeleton({"bones": bones})


def landmarks(skeleton):
    """Project editable endpoints for viewers and older rig clients."""
    joints, chains = {}, []
    for bone in skeleton["bones"]:
        bone_id = bone["id"]
        tip_id = bone.get("legacy_tip", bone_id + "/tip")
        joints[tip_id] = bone["tail"]
        chains.append((bone_id, tip_id, bone.get("parent_id")))
    joints.update((bone["id"], bone["head"]) for bone in skeleton["bones"])
    return joints, chains


def geometry_key(skeleton):
    geometry = sorted(
        (bone["id"], bone.get("parent_id"), bone["head"], bone["tail"],
         bone.get("roll", 0), bone.get("deform", True), bone.get("connected", False))
        for bone in skeleton["bones"]
    )
    return hashlib.sha256(json.dumps(geometry, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def legacy_key(joints):
    return hashlib.sha256(json.dumps(joints, sort_keys=True).encode()).hexdigest()


def read_prediction(folder, source_sha256):
    manifest = folder / "prediction.json"
    weights = folder / "weights.npz"
    if not manifest.is_file() or manifest.stat().st_size > 256 * 1024:
        raise ValueError("The model did not return a bounded skeleton prediction.")
    result = json.loads(manifest.read_bytes())
    if result.get("source_sha256") != source_sha256:
        raise ValueError("The prediction does not belong to this source mesh.")
    if not weights.is_file() or not 4 < weights.stat().st_size <= 128 * 1024**2:
        raise ValueError("The model did not return a bounded learned weights artifact.")
    samples = result.get("samples")
    if type(samples) is not int or not 1 <= samples <= 65536:
        raise ValueError("The model returned an invalid learned weights sample count.")
    with weights.open("rb") as stream:
        weights_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    if result.get("weights_sha256", weights_sha256) != weights_sha256:
        raise ValueError("The learned weights artifact failed its checksum.")
    bones = predicted_bones(result["joints"], result["parents"])
    return bones, {"weights_sha256": weights_sha256, "weight_samples": samples,
                   "predicted_joints": len(bones), "seconds": result["seconds"],
                   "cuda_allocated_bytes": result["cuda_allocated_bytes"],
                   **{key:result[key] for key in ("geometry_cache_hit","cpu_seconds") if key in result}}


def predicted_bones(points, parents):
    if not isinstance(points, list) or not isinstance(parents, list) or not 1 <= len(points) == len(parents) <= MAX_BONES:
        raise ValueError("The model returned an invalid joint hierarchy.")
    points = [numbers(point, 3) for point in points]
    children = [[] for _ in points]
    edge_lengths = []
    for index, parent in enumerate(parents):
        if type(parent) is not int or not -1 <= parent < len(points) or parent == index:
            raise ValueError("The model returned an invalid bone parent.")
        if parent >= 0:
            children[parent].append(index)
            edge_lengths.append(math.dist(points[index], points[parent]))
    default_length = max(sum(edge_lengths)/len(edge_lengths) * .35 if edge_lengths else .02, 1e-5)
    bones = []
    for index, (head, parent) in enumerate(zip(points, parents)):
        linked = children[index]
        if len(linked) == 1 and math.dist(head, points[linked[0]]) >= 1e-7:
            tail = points[linked[0]]
        else:
            direction = [b-a for a, b in zip(points[parent], head)] if parent >= 0 else [0, 1, 0]
            length = math.hypot(*direction)
            if length < 1e-7:
                direction, length = [0, 1, 0], 1
            tail = [value + axis * default_length / length for value, axis in zip(head, direction)]
        bones.append({"id": f"bone_{index}", "label": f"Bone {index+1}",
                      "parent_id": f"bone_{parent}" if parent >= 0 else None, "head": head, "tail": tail,
                      "roll": 0, "deform": True, "connected": False, "model_index": index})
    return validate_skeleton({"bones": bones})["bones"]


def migrate(state):
    version = state.get("schema_version", 1)
    if version == SCHEMA_VERSION:
        return state
    if version not in (1, 2):
        raise ValueError("This saved rig requires a newer Foundry version.")
    if version == 1:
        legacy_joints = state.pop("joints")
        state["skeleton"] = guided_skeleton(legacy_joints)
        if output := state.get("output"):
            if output.get("skeleton") == legacy_key(legacy_joints):
                output["skeleton"] = geometry_key(state["skeleton"])
        for checkpoint in state.get("undo", []):
            checkpoint["skeleton"] = guided_skeleton(checkpoint.pop("joints"))
        state.update(rig_revision=state["revision"], view_revision=0, redo=[])
    state.update(schema_version=SCHEMA_VERSION, surface_landmarks=[])
    return state
