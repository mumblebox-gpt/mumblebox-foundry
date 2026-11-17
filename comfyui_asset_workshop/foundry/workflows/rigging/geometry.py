"""Read bounded glTF metadata and place a humanoid template in its world coordinates."""
import json
import math
import struct

MAX_FILE = 250 * 1024**2
MAX_VERTICES = 2_000_000
IDENTITY = (1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1)
CENTER = {"hips": (0,.49,0), "spine": (0,.61,0), "chest": (0,.75,0),
          "neck": (0,.86,0), "head": (0,.93,0), "crown": (0,.99,0)}
SIDE = {"shoulder": (.43,.79,0), "elbow": (.68,.66,0),
        "wrist": (.89,.53,0), "fingers": (.99,.47,0),
        "hip": (.22,.48,0), "knee": (.26,.27,.05),
        "ankle": (.30,.06,0), "toe": (.31,.025,.36)}
CHAINS = [("hips","spine",None), ("spine","chest","hips"),
          ("chest","neck","spine"), ("neck","head","chest"), ("head","crown","neck")]
for side in (".L", ".R"):
    CHAINS.extend((start+side, end+side, parent+side if parent in SIDE else parent) for start,end,parent in (
        ("shoulder","elbow","chest"), ("elbow","wrist","shoulder"), ("wrist","fingers","elbow"),
        ("hip","knee","hips"), ("knee","ankle","hip"), ("ankle","toe","knee")))
POSES = ("rest", "elbow", "arms", "crouch", "finger", "finger_left", "finger_right", "finger_spread", "toe", "tail", "wing")


def numbers(values, count):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError("Enter a valid 3D coordinate.")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("Enter a valid 3D coordinate.")
    return list(map(float, values))


def bone_frame(bone, origin=None):
    """Match the Blender rest frame, then return its axes in glTF source space."""
    dx, dy, dz = (b-a for a,b in zip(bone["head"], bone["tail"]))
    length = math.hypot(dx, dy, dz)
    x, y, z = dx/length, -dz/length, dy/length
    theta = 1+y
    if theta < 1e-10:
        square = x*x+z*z
        if square < 1e-20:
            basis_x, basis_z = (-1,0,0), (0,0,1)
        else:
            basis_x = (1-2*x*x/square, -x, -2*x*z/square)
            basis_z = (-2*x*z/square, -z, 1-2*z*z/square)
    else:
        basis_x = (1-x*x/theta, -x, -x*z/theta)
        basis_z = (-x*z/theta, -z, 1-z*z/theta)
    cosine, sine = math.cos(bone.get("roll",0)), math.sin(bone.get("roll",0))
    rolled_x = [cosine*a-sine*b for a,b in zip(basis_x,basis_z)]
    rolled_z = [sine*a+cosine*b for a,b in zip(basis_x,basis_z)]
    return {"origin": origin if origin is not None else bone["head"],
            "axes": [[rolled_x[0], rolled_x[2], -rolled_x[1]], [x,z,-y], [rolled_z[0],rolled_z[2],-rolled_z[1]]]}


def product(a, b):
    return tuple(sum(a[k*4+r] * b[c*4+k] for k in range(4)) for c in range(4) for r in range(4))


def transform(node):
    if "matrix" in node:
        return numbers(node["matrix"], 16)
    x,y,z,w = numbers(node.get("rotation", [0,0,0,1]), 4)
    sx,sy,sz = numbers(node.get("scale", [1,1,1]), 3)
    tx,ty,tz = numbers(node.get("translation", [0,0,0]), 3)
    return (
        (1-2*y*y-2*z*z)*sx, (2*x*y+2*z*w)*sx, (2*x*z-2*y*w)*sx, 0,
        (2*x*y-2*z*w)*sy, (1-2*x*x-2*z*z)*sy, (2*y*z+2*x*w)*sy, 0,
        (2*x*z+2*y*w)*sz, (2*y*z-2*x*w)*sz, (1-2*x*x-2*y*y)*sz, 0,
        tx,ty,tz,1)


def document(path):
    size = path.stat().st_size
    if not 20 <= size <= MAX_FILE:
        raise ValueError("Choose a GLB smaller than 250 MB.")
    with path.open("rb") as source:
        magic, version, size_header, length, chunk = struct.unpack("<4sIII4s", source.read(20))
        if (magic, version, size_header, chunk) != (b"glTF", 2, size, b"JSON") or not 2 <= length <= min(size-20, 8*1024**2):
            raise ValueError("Choose a valid binary glTF 2.0 mesh.")
        data = json.loads(source.read(length))
    if not isinstance(data, dict) or not isinstance(data.get("meshes"), list):
        raise ValueError("Choose a GLB containing a surface mesh.")
    return data


def mesh_bounds(path):
    data = document(path)
    if data.get("skins") or data.get("animations"):
        raise ValueError("Choose a mesh that has not been rigged or animated.")
    if any("uri" in entry for section in ("images","buffers") for entry in data.get(section, [])):
        raise ValueError("Choose a self-contained Foundry GLB.")
    nodes = data.get("nodes", [])
    scenes = data.get("scenes", [])
    if not scenes or len(nodes) > 512 or len(data["meshes"]) > 64:
        raise ValueError("Choose a bounded GLB scene with surface geometry.")
    low, high, count, visited = [math.inf]*3, [-math.inf]*3, 0, set()
    pending = [(idx, IDENTITY) for idx in scenes[data.get("scene", 0)]["nodes"]]
    while pending:
        index, parent = pending.pop()
        if index in visited or not 0 <= index < len(nodes):
            raise ValueError("The mesh has an invalid node hierarchy.")
        visited.add(index)
        node = nodes[index]
        world = product(parent, transform(node))
        pending.extend((child,world) for child in node.get("children", []))
        if "mesh" not in node:
            continue
        for primitive in data["meshes"][node["mesh"]]["primitives"]:
            if primitive.get("mode",4) not in (4,5,6):
                raise ValueError("Rigging requires a triangle surface mesh.")
            positions = data["accessors"][primitive["attributes"]["POSITION"]]
            if positions.get("type") != "VEC3" or type(positions.get("count")) is not int or positions["count"] < 3:
                raise ValueError("The mesh has invalid vertices.")
            count += positions["count"]
            if count > MAX_VERTICES:
                raise ValueError("Choose a mesh variant under two million vertices.")
            a,b = numbers(positions["min"],3), numbers(positions["max"],3)
            for row in range(3):
                terms = [(world[col*4+row]*a[col],world[col*4+row]*b[col]) for col in range(3)]
                low[row] = min(low[row],world[12+row] + sum(min(pair) for pair in terms))
                high[row] = max(high[row],world[12+row] + sum(max(pair) for pair in terms))
    if not count or min(high[i]-low[i] for i in (0,1)) < 1e-6 or max(map(abs,low+high))>1e6:
        raise ValueError("Choose an upright GLB with valid dimensions and visible limbs.")
    return [low,high], count


def template(bounds, quarter_turns=0):
    low,high = bounds
    cx,cz = ((low[i]+high[i])/2 for i in (0,2))
    x_span,z_span = ((high[i]-low[i])/2 for i in (0,2))
    if quarter_turns % 2:
        x_span,z_span = z_span,x_span
    height = high[1]-low[1]
    placements = dict(CENTER)
    for side, sign in ((".L",1),(".R",-1)):
        placements.update({key+side:(sign*x,y,z) for key,(x,y,z) in SIDE.items()})
    result = {}
    for key,(x,y,z) in placements.items():
        x,z = x*x_span,z*z_span
        for _ in range(quarter_turns%4):
            x,z = z,-x
        result[key] = [round(cx+x,8),round(low[1]+height*y,8),round(cz+z,8)]
    return result
