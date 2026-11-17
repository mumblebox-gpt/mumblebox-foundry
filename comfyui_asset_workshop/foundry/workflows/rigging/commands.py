"""Apply one validated structural edit to the session's private working copy."""
from collections import defaultdict
from copy import deepcopy
import math

from .document import geometry_key, landmarks, surface_anchor, validate_skeleton
from .geometry import bone_frame, numbers
from .parts import DIGITS, PART_TYPES, layout, part_group
from .weights import append_stroke

STRUCTURAL_ACTIONS = ("move", "orient", "lock", "label", "role", "add_chain", "add_part", "remove_chain", "reparent",
                      "mirror_chain","pair",
                      "weight_stroke", "weight_lock", "landmark_put", "landmark_remove", "side", "refit_branch")
ROLES = ("hips", "spine", "chest", "neck", "head", "shoulder", "elbow", "wrist", "finger",
         "hip", "knee", "ankle", "toe", "tail", "wing", "palm","foot","wing_digit","feather","other")


class LockedJoint(ValueError):
    code = "locked_joint"


def nearby_point(bounds, value):
    point = numbers(value, 3)
    low, high = bounds
    margin = max(b - a for a, b in zip(low, high))
    if any(not a-margin <= v <= b+margin for a, b, v in zip(low, high, point)):
        raise ValueError("Keep the joints near the mesh.")
    return point


def tip_id(bone):
    return bone.get("legacy_tip", bone["id"]+"/tip")


def endpoint_groups(skeleton):
    groups, adjacency = defaultdict(list), defaultdict(set)
    for bone in skeleton["bones"]:
        head, tail = bone["id"], tip_id(bone)
        groups[head].append((bone, "head"))
        groups[tail].append((bone, "tail"))
    by_id = {bone["id"]: bone for bone in skeleton["bones"]}
    for bone in by_id.values():
        if bone.get("connected"):
            head, tail = bone["id"], tip_id(by_id[bone["parent_id"]])
            adjacency[head].add(tail)
            adjacency[tail].add(head)
    return groups, adjacency


def move_endpoints(run, joint, point, mirror=False, move_children=False):
    skeleton = run["skeleton"]
    groups, adjacency = endpoint_groups(skeleton)
    if not isinstance(joint, str) or joint not in groups:
        raise ValueError("Choose a joint in the current skeleton.")
    if type(mirror) is not bool or type(move_children) is not bool:
        raise ValueError("Choose whether to mirror or move child bones.")
    position = nearby_point(run["bounds"], point)
    by_id = {bone["id"]: bone for bone in skeleton["bones"]}
    destinations = {joint: position}
    if mirror:
        bone, endpoint = next(((bone, endpoint) for bone, endpoint in groups[joint]
                               if bone.get("mirror_id")), (None, None))
        if bone:
            partner = by_id[bone["mirror_id"]]
            other = partner["id"] if endpoint == "head" else tip_id(partner)
            plane = bone.get("mirror_plane") or mirror_plane(run,{})
            destinations[other] = reflect(position,plane)

    changed = set()
    for endpoint, target in destinations.items():
        old_bone, old_key = groups[endpoint][0]
        origin = old_bone[old_key]
        delta = [end-start for start, end in zip(origin, target)]
        pending, seen = [endpoint], set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            for bone, key in groups[current]:
                if bone.get("locked"):
                    raise LockedJoint("Unlock the affected bones before moving this joint.")
                if move_children and key == "head":
                    pending.append(tip_id(bone))
                    pending.extend(child["id"] for child in by_id.values()
                                   if child.get("parent_id") == bone["id"])
                previous = bone[key]
                bone[key] = target if current == endpoint or previous == origin else nearby_point(
                    run["bounds"], [a+b for a, b in zip(previous, delta)])
                changed.add(bone["id"])
            pending.extend(adjacency[current] - seen)
    run["selected_joint"] = joint
    return changed


def add_chain(run, request_id, args, known):
    part = args.get("part", "custom")
    points = args.get("points")
    parent = args.get("parent_id")
    if part not in PART_TYPES or not isinstance(points, list) or not 2 <= len(points) <= 33:
        raise ValueError("Choose a part and place 2 to 33 chain points.")
    if parent is not None and (not isinstance(parent, str) or parent not in known):
        raise ValueError("Choose an existing attachment bone.")
    points = [nearby_point(run["bounds"], point) for point in points]
    part_id = "part_" + request_id[:20]
    ids = []
    for index, (head, tail) in enumerate(zip(points, points[1:])):
        bone_id = f"{part_id}_{index+1}"
        run["skeleton"]["bones"].append({
            "id": bone_id, "label": f"{part.title()} {index+1}", "parent_id": parent,
            "head": head, "tail": tail, "roll": 0, "deform": True, "connected": index > 0,
            "part_id": part_id, "part_type": part, "role": {"toes": "toe"}.get(part, part) if part != "custom" else "other",
        })
        parent = bone_id
        ids.append(bone_id)
    run["selected_joint"] = ids[0]
    return set(ids)


def part_layout(run, args, known=None):
    known = known if known is not None else {bone["id"]:bone for bone in run["skeleton"]["bones"]}
    parent = args.get("parent_id")
    part = args.get("part")
    if not isinstance(parent,str) or parent not in known or part not in PART_TYPES:
        raise ValueError("Choose a part and an attachment bone.")
    anchor = known[parent]
    existing = [bone for bone in known.values() if bone.get("parent_id")==parent]
    digit = args.get("digit","index")
    if part=="hand" and any(bone.get("part_type")=="hand" for bone in existing):
        raise ValueError("This attachment already has hand or finger bones. Select a finger to edit it.")
    if part=="finger" and any(bone.get("role")=="finger" and
                              bone.get("anatomical_name") in (None,digit) for bone in existing):
        raise ValueError("This finger may already exist. Assign finger identities before adding a duplicate.")
    waypoints = args.get("waypoints",[])
    if not isinstance(waypoints,list) or len(waypoints)>6:
        raise ValueError("Use up to six intermediate path points.")
    parse = lambda point: nearby_point(run["bounds"],point)
    result = layout(part,anchor["tail"],parse(args.get("tip")),args.get("segments"),
                    parse(args["width_point"]) if args.get("width_point") is not None else None,
                    [parse(point) for point in waypoints],digit)
    for bone in result:
        parse(bone["head"])
        parse(bone["tail"])
    return result


def add_part(run, request_id, args, known):
    specs = part_layout(run,args,known)
    part_id = "part_" + request_id[:20]
    parent = args["parent_id"]
    side = known[parent].get("side")
    part = part_group(args["part"])
    ids = [f"{part_id}_{index+1}" for index in range(len(specs))]
    for index,spec in enumerate(specs):
        joint_parent = spec["parent"]
        parent_id = parent if joint_parent is None else ids[joint_parent]
        parent_tip = known[parent]["tail"] if joint_parent is None else specs[joint_parent]["tail"]
        name = spec["name"]
        run["skeleton"]["bones"].append({
            "id":ids[index], "label":f"{name.replace('_',' ').title() if name else part.title()} {spec['segment']}",
            "parent_id":parent_id, "head":spec["head"], "tail":spec["tail"], "roll":0.0,"deform":True,
            "connected":spec["head"]==parent_tip,"part_id":part_id,"part_type":part,
            "role":spec["role"],"anatomical_name":name,"side":side,"chain_segment":spec["segment"],
        })
    run["selected_joint"] = ids[0]
    return set(ids)


def mirror_plane(run,args):
    axis = args.get("axis","z" if run["orientation"]%2 else "x")
    if axis not in ("x","y","z"):
        raise ValueError("Choose a mirror axis.")
    index = "xyz".index(axis)
    low,high = run["bounds"]
    center = numbers([args.get("center",(low[index]+high[index])/2)],1)[0]
    if not low[index] <= center <= high[index]:
        raise ValueError("Place the mirror plane inside the source bounds.")
    return [index,center]


def reflect(point,plane):
    axis,center = plane
    result = list(point)
    result[axis] = 2*center-result[axis]
    return result


def pair_bones(run,args,known,bone):
    other = args.get("other")
    if other is not None and (not isinstance(other,str) or other not in known or other==bone["id"]):
        raise ValueError("Choose a different bone as the mirror partner.")
    changed = {bone["id"]}
    for target in (bone,known.get(other)):
        if target is None:
            continue
        if target.get("locked"):
            raise ValueError("Unlock both bones before changing their pairing.")
        if old := target.pop("mirror_id",None):
            if known[old].get("locked"):
                raise ValueError("Unlock the previous paired bone first.")
            known[old].pop("mirror_id",None)
            known[old].pop("mirror_plane",None)
            changed.add(old)
        target.pop("mirror_plane",None)
    if other:
        plane = mirror_plane(run,args)
        bone.update(mirror_id=other,mirror_plane=plane)
        known[other].update(mirror_id=bone["id"],mirror_plane=plane)
        changed.add(other)
    return changed


def mirror_chain(run,args,known,bone,request_id):
    plane = mirror_plane(run,args)
    parent = args.get("parent_id")
    if parent is None and bone.get("parent_id"):
        parent = known[bone["parent_id"]].get("mirror_id") or bone["parent_id"]
    if parent is not None and (not isinstance(parent,str) or parent not in known):
        raise ValueError("Choose an existing mirror attachment.")
    children = defaultdict(list)
    for item in known.values():
        children[item.get("parent_id")].append(item)
    pending, original = [bone], []
    while pending:
        member = pending.pop()
        if member.get("locked") or member.get("mirror_id"):
            raise ValueError("Mirror only an unlocked chain whose bones are not already paired.")
        original.append(member)
        pending.extend(reversed(children[member["id"]]))
    prefix = "part_"+request_id[:20]
    ids = {item["id"]:f"{prefix}_{index+1}" for index,item in enumerate(original)}
    if parent in ids:
        raise ValueError("Attach the mirrored chain outside the original chain.")
    clones=[]
    for item in original:
        bone_id=ids[item["id"]]
        target_parent=ids.get(item.get("parent_id"),parent)
        side={"L":"R","R":"L"}.get(item.get("side"))
        cloned={key:value for key,value in item.items() if key not in ("legacy_tip","landmark_label")}
        cloned.update(id=bone_id,parent_id=target_parent,part_id=prefix,part_type=item.get("part_type","custom"),
                      head=nearby_point(run["bounds"],reflect(item["head"],plane)),
                      tail=nearby_point(run["bounds"],reflect(item["tail"],plane)),roll=0,
                      side=side,mirror_id=item["id"],mirror_plane=plane)
        # Reflection changes handedness. Reflect the long and bend axes and
        # reverse the remaining axis to keep a valid right-handed frame.
        original_x = bone_frame(item)["axes"][0]
        original_x[plane[0]] *= -1
        target_x = [-value for value in original_x]
        basis_x, _, basis_z = bone_frame(cloned)["axes"]
        cloned["roll"] = math.atan2(-sum(a*b for a,b in zip(target_x,basis_z)),
                                    sum(a*b for a,b in zip(target_x,basis_x)))
        if item is bone:
            cloned["connected"]=bool(parent and cloned["head"]==known[parent]["tail"])
        item.update(mirror_id=bone_id,mirror_plane=plane)
        clones.append(cloned)
    run["skeleton"]["bones"].extend(clones)
    run["selected_joint"]=clones[0]["id"]
    return set(ids)|set(ids.values())


def apply_edit(run, action, args, request_id):
    skeleton = run["skeleton"]
    known = {bone["id"]: bone for bone in skeleton["bones"]}
    if action in ("landmark_put", "landmark_remove"):
        edit_landmark(run, action, args, request_id, known)
        return []
    if action == "refit_branch":
        return refit_branch(run, args, known)
    if action == "weight_stroke":
        changed = append_stroke(run, args, known, nearby_point, geometry_key(skeleton))
    elif action == "add_chain":
        changed = add_chain(run, request_id, args, known)
    elif action == "add_part":
        changed = add_part(run,request_id,args,known)
    elif action == "move":
        changed = move_endpoints(run, args.get("joint"), args.get("point"), args.get("mirror", False),
                                 args.get("move_children", False))
    else:
        bone_id = args.get("bone_id")
        if not isinstance(bone_id, str) or bone_id not in known:
            raise ValueError("Choose a bone in the current skeleton.")
        bone = known[bone_id]
        if bone.get("locked") and action not in ("lock", "weight_lock"):
            raise LockedJoint("Unlock this bone before editing it.")
        changed = {bone_id}
        if action == "weight_lock":
            if type(args.get("locked")) is not bool:
                raise ValueError("Choose whether to lock this weight group.")
            locked = set(run.get("weight_locks", []))
            if args["locked"]:
                locked.add(bone_id)
            else:
                locked.discard(bone_id)
            run["weight_locks"] = sorted(locked)
        elif action == "orient":
            bone["roll"] = numbers([args.get("roll")], 1)[0]
        elif action == "lock":
            locked = args.get("locked")
            if type(locked) is not bool:
                raise ValueError("Choose whether to lock this bone.")
            bone["locked"] = locked
        elif action == "label":
            bone["label"] = args.get("label")
        elif action == "role":
            role = args.get("role")
            if role not in ROLES:
                raise ValueError("Choose a supported anatomical role.")
            if role != bone.get("role"):
                bone.pop("landmark_label", None)
                bone.pop("anatomical_name", None)
            bone["role"] = role
            if "digit" in args:
                digit = args["digit"]
                if role != "finger" or digit not in (None, *DIGITS):
                    raise ValueError("Choose a finger identity.")
                bone["anatomical_name"] = digit
        elif action == "side":
            side = args.get("side")
            branch = args.get("apply_to_branch", False)
            if side not in ("L", "R", None) or type(branch) is not bool:
                raise ValueError("Choose a side and whether to label the whole branch.")
            targets = descendants(known, bone_id) if branch else [bone_id]
            if any(known[item].get("locked") for item in targets):
                raise LockedJoint("Unlock the affected bones before changing their side.")
            for item in targets:
                known[item]["side"] = side
            changed = set(targets)
        elif action == "reparent":
            parent = args.get("parent_id")
            if parent is not None and (not isinstance(parent, str) or parent not in known):
                raise ValueError("Choose an existing parent bone.")
            bone.update(parent_id=parent, connected=False)
        elif action == "pair":
            changed = pair_bones(run,args,known,bone)
        elif action == "mirror_chain":
            changed = mirror_chain(run,args,known,bone,request_id)
        elif action == "remove_chain":
            children = defaultdict(list)
            for child in known.values():
                children[child.get("parent_id")].append(child["id"])
            pending = children[bone_id].copy()
            while pending:
                child = pending.pop()
                changed.add(child)
                pending.extend(children[child])
            if any(known[item].get("locked") for item in changed):
                raise ValueError("Unlock the affected bones before removing this chain.")
            skeleton["bones"] = [item for item in skeleton["bones"] if item["id"] not in changed]
            for item in skeleton["bones"]:
                if item.get("mirror_id") in changed:
                    item.pop("mirror_id")
                    item.pop("mirror_plane",None)
    validate_skeleton(skeleton)
    if run["selected_joint"] not in landmarks(skeleton)[0]:
        run["selected_joint"] = skeleton["bones"][0]["id"]
    return sorted(changed)


def descendants(known, root):
    children = defaultdict(list)
    for bone in known.values():
        children[bone.get("parent_id")].append(bone["id"])
    branch = [root]
    for bone_id in branch:
        branch.extend(children[bone_id])
    return branch


def edit_landmark(run, action, args, request_id, known):
    landmark_id = args.get("id", request_id)
    if not isinstance(landmark_id, str) or not 1 <= len(landmark_id) <= 48 or not all(
            ch.isascii() and (ch.isalnum() or ch in "_-") for ch in landmark_id):
        raise ValueError("Choose a valid surface landmark ID.")
    records = run["surface_landmarks"]
    index = next((index for index, item in enumerate(records) if item["id"] == landmark_id), None)
    if action == "landmark_remove":
        if index is None:
            raise ValueError("Choose an existing surface landmark.")
        del records[index]
        return
    if args.get("source_sha256") != run["source"]["sha256"]:
        raise ValueError("Capture the current source mesh before adding a landmark.")
    label = args.get("label", "")
    joint = args.get("joint_id")
    if not isinstance(label, str) or len(label) > 100 or (joint is not None and joint not in known):
        raise ValueError("Choose a short landmark label and an optional joint in this rig.")
    record = {**surface_anchor(args), "id": landmark_id, "label": label,
              "source_sha256": args["source_sha256"], "position": nearby_point(run["bounds"], args.get("position")),
              "joint_id": joint}
    if index is None:
        if len(records) >= 256:
            raise ValueError("Keep up to 256 landmarks per rig.")
        records.append(record)
    else:
        records[index] = record


def refit_branch(run, args, known):
    root = args.get("root_id")
    fixed_ids = args.get("fixed_ids", [])
    landmark_ids = args.get("landmark_ids", [])
    points = args.get("candidate_points")
    if not isinstance(root, str) or root not in known or args.get("preserve_outside", True) is not True:
        raise ValueError("Choose a branch and keep the surrounding rig fixed.")
    if (not isinstance(fixed_ids, list) or len(fixed_ids) > 512 or any(not isinstance(x,str) or x not in known for x in fixed_ids)
            or not isinstance(landmark_ids, list) or len(landmark_ids) > 64
            or not isinstance(points, dict) or not 1 <= len(points) <= 64):
        raise ValueError("Provide up to 64 reviewed points in the selected branch.")
    branch = set(descendants(known,root))
    allowed = {endpoint for item in branch for endpoint in (item,tip_id(known[item]))} - {root}
    source = run["source"]["sha256"]
    marks = {mark["id"]:mark for mark in run["surface_landmarks"] if mark["source_sha256"] == source}
    if any(not isinstance(mark,str) or mark not in marks for mark in landmark_ids):
        raise ValueError("Use landmarks on the current mesh.")
    if any(endpoint not in allowed for endpoint in points):
        raise ValueError("Keep the branch attachment and outside joints fixed.")
    protected = (known.keys() - branch) | set(fixed_ids)
    before = {key:deepcopy(known[key]) for key in protected}
    attachment = known[root]["head"][:]
    changed = set()
    for joint, point in points.items():
        changed.update(move_endpoints(run,joint,point))
    if attachment != known[root]["head"] or any(known[key] != value for key,value in before.items()):
        raise LockedJoint("This fit would move a fixed attachment or a joint outside the branch.")
    validate_skeleton(run["skeleton"])
    return sorted(changed)
