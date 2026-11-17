"""Suggest body landmarks for humanoid predictions and explicit template conversion."""
from math import dist, isfinite

INCOMPLETE = "The AI fit did not find a complete humanoid skeleton. Check the facing direction, try another seed, or use Guided Template."


def map_humanoid(points, parents, bounds, orientation):
    if not 15 <= len(points) <= 128 or len(points) != len(parents) or parents[0] != -1:
        raise ValueError(INCOMPLETE)
    height = bounds[1][1] - bounds[0][1]
    if height <= 0 or any(len(point) != 3 or not all(map(isfinite, point)) for point in points):
        raise ValueError(INCOMPLETE)
    if any(not low-height*.16 <= value <= high+height*.16 for point in points
           for low, high, value in zip(*bounds, point)):
        raise ValueError(INCOMPLETE)
    children = [[] for _ in points]
    for index, parent in enumerate(parents[1:], 1):
        if type(parent) is not int or not 0 <= parent < index:
            raise ValueError(INCOMPLETE)
        children[parent].append(index)
    vertical = [(point[1]-bounds[0][1])/height for point in points]
    axis, sign = ((0,1),(2,-1),(0,-1),(2,1))[orientation]
    lateral = [point[axis]*sign/height for point in points]

    def leaf_paths(node):
        if not children[node]:
            yield (node,)
        for child in children[node]:
            for path in leaf_paths(child):
                yield (node, *path)

    def legs(node):
        found = {}
        for child in children[node]:
            for path in leaf_paths(child):
                if len(path) < 4:
                    continue
                hip, knee, ankle, toe = path[:4]
                offset = lateral[knee] - lateral[node]
                if (abs(offset) < .02 or not .13 < vertical[knee] < vertical[hip]-.07
                        or vertical[ankle] > .23 or vertical[ankle] > vertical[knee]-.07
                        or vertical[toe] > .20):
                    continue
                side = "L" if offset > 0 else "R"
                score = abs(vertical[hip]-vertical[node]) + abs(vertical[ankle]-.08)
                if side not in found or score < found[side][0]:
                    found[side] = (score, path[:4])
        return found

    def arms_and_head(node):
        found, head_path = {}, ()
        for child in children[node]:
            side_candidates = {}
            for path in leaf_paths(child):
                offset = lateral[path[-1]] - lateral[node]
                if abs(offset) < .12 and vertical[path[-1]] > max(.74, vertical[node]+.045):
                    if not head_path or vertical[path[-1]] > vertical[head_path[-1]]:
                        head_path = path
                if len(path) < 4 or abs(offset) < .14:
                    continue
                side = "L" if offset > 0 else "R"
                # A near-center first joint is the collarbone, followed by the upper arm.
                start = int(len(path) >= 5 and abs(lateral[path[0]]-lateral[node]) < .095)
                arm = path[start:start+4]
                shoulder, elbow, wrist = arm[:3]
                if (vertical[shoulder] < .55 or abs(lateral[shoulder]-lateral[node]) < .06
                        or (lateral[shoulder]-lateral[node])*offset <= 0
                        or min(dist(points[shoulder],points[elbow]), dist(points[elbow],points[wrist])) < height*.045):
                    continue
                score = abs(offset) + .5*abs(lateral[wrist]-lateral[node])
                if side not in side_candidates or score > side_candidates[side][0]:
                    side_candidates[side] = (score, arm, child)
            for side, candidate in side_candidates.items():
                if side not in found or candidate[0] > found[side][0]:
                    found[side] = candidate
        if len(found) != 2 or not head_path or len({found["L"][2], found["R"][2], head_path[0]}) != 3:
            return None
        return found, head_path

    for hips, position in enumerate(vertical):
        if not .26 <= position <= .64 or len(children[hips]) < 3:
            continue
        legs_found = legs(hips)
        if len(legs_found) != 2:
            continue
        for shoulders in range(hips+1, len(points)):
            if not .61 <= vertical[shoulders] <= .93 or len(children[shoulders]) < 3:
                continue
            trunk = [shoulders]
            while parents[trunk[-1]] >= hips:
                trunk.append(parents[trunk[-1]])
            if trunk[-1] != hips or len(trunk) < 3:
                continue
            top = arms_and_head(shoulders)
            if not top:
                continue
            arms, head_path = top
            chest, neck = (shoulders,head_path[0]) if len(head_path) >= 2 else (trunk[1],shoulders)
            head = head_path[-1]
            spine_candidates = [index for index in trunk if vertical[hips] < vertical[index] < vertical[chest]]
            if not spine_candidates:
                continue
            spine = min(spine_candidates, key=lambda index: abs(vertical[index]-(vertical[hips]+vertical[chest])/2))
            joints = {name: list(points[index]) for name,index in
                      (("hips",hips),("spine",spine),("chest",chest),("neck",neck),("head",head))}
            joints["crown"] = list(points[head])
            joints["crown"][1] = max(points[head][1]+height*.025, bounds[1][1]-height*.01)
            for side in ("L","R"):
                for names, indices in ((["shoulder","elbow","wrist","fingers"],arms[side][1]),
                                       (["hip","knee","ankle","toe"],legs_found[side][1])):
                    joints.update({f"{name}.{side}":list(points[index]) for name,index in zip(names,indices)})
            return joints
    raise ValueError(INCOMPLETE)


def suggest_roles(bones, bounds, orientation):
    """Annotate recognizable parts while leaving unfamiliar branches intact."""
    ids = {bone["id"]: index for index, bone in enumerate(bones)}
    indices = {tuple(bone["head"]): index for index, bone in enumerate(bones)}
    points = [bone["head"] for bone in bones]
    parents = [ids.get(bone.get("parent_id"), -1) for bone in bones]
    try:
        roles = map_humanoid(points, parents, bounds, orientation)
    except ValueError:
        return bones
    children = [[] for _ in bones]
    for index, parent in enumerate(parents):
        if parent >= 0:
            children[parent].append(index)
    assigned = {}
    for label, point in roles.items():
        role, _, side = label.partition(".")
        if role in {"crown", "fingers"}:
            continue
        index = indices.get(tuple(point))
        if index is not None and index not in assigned.values():
            assigned[label] = index
            bones[index].update(role=role, side=side, role_source="suggested", landmark_label=label)
    for label, index in assigned.items():
        role, _, side = label.partition(".")
        if side not in {"L", "R"}:
            continue
        mate = assigned.get(f"{role}.{'R' if side=='L' else 'L'}")
        if mate is not None:
            bones[index]["mirror_id"] = bones[mate]["id"]
        if role == "wrist":
            bones[index].update(part_type="hand", part_id=f"hand.{side}")
            for chain, child in enumerate(children[index], 1):
                pending = [(child, 1)]
                while pending:
                    current, number = pending.pop()
                    if current in assigned.values():
                        continue
                    bones[current].update(part_type="hand", part_id=f"hand.{side}", role="finger",
                                          side=side, role_source="suggested", chain=chain, chain_segment=number)
                    pending.extend((item, number+1) for item in children[current])
    return bones
