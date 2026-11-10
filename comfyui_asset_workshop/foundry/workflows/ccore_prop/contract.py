"""Validate CCORE inputs and the self-contained GLB shown in the native viewer."""
import json
import re
import struct

MAX_GLB = 32 * 1024**2
MAX_HTML = 2 * 1024**2
TOKEN_LIMITS = (16384, 32768, 65536)
STANDARD_MODEL = "q4_k_m"
TEXT_MODE = "text"
IMAGE_MODE = "image_text"
PROJECTOR_KEY = "ccore_vision_projector"
IMAGE_MAX_TOKENS = 1024
MODEL_KEYS = {STANDARD_MODEL: "ccore_prop", "q8_0": "ccore_prop_q8"}
SYSTEM = ("Create game assets for the Godot editor, which uses GLB files. Create whatever the user "
          "requests as a good-quality low-poly asset using only Three.js in one complete standalone HTML "
          "file. The HTML must show the asset and include an Export GLB button that downloads a working "
          "GLB. If the requested asset needs animation, add it and include the animation in the "
          "exported GLB; otherwise make it static.")
EXAMPLE = ("A small olive-green sci-fi cargo crate with two orange latches and dark corner guards. "
           "One static low-poly game prop, with solid-color materials.")


def default_model_variant():
    return STANDARD_MODEL


def options(data):
    name = data.get("name", "New prop")
    prompt = data.get("prompt", "")
    seed = data.get("seed", 42)
    budget = data.get("max_tokens", 65536)
    model_variant = data.get("model_variant", default_model_variant())
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
        raise ValueError("Give the prop a name of 1–80 characters.")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 5000:
        raise ValueError("Describe one prop in 1–5,000 characters.")
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError("Use a whole-number seed from 0 to 2,147,483,647.")
    if type(budget) is not int or budget not in TOKEN_LIMITS:
        raise ValueError("Choose an available generation budget.")
    if not isinstance(model_variant, str) or model_variant not in MODEL_KEYS:
        raise ValueError("Choose an available CCORE model precision.")
    config = dict(name=name.strip(), prompt=prompt, seed=seed, max_tokens=budget, model_variant=model_variant)
    mode, image = data.get("mode", TEXT_MODE), data.get("image")
    if mode == IMAGE_MODE:
        upload = r'foundry-references/[^/\\:<>"|?*\x00-\x1f]{1,200}\.(png|jpe?g|webp)'
        created = r'foundry-created/[a-f0-9]{32}/(?:single|front|back)-[a-f0-9]{16}\.png'
        if not isinstance(image, str) or not re.fullmatch(f"(?:{upload}|{created})", image, re.IGNORECASE):
            raise ValueError("Upload one PNG, JPEG or WebP reference before generating.")
        config.update(mode=mode, image=image)
    elif mode != TEXT_MODE or image:
        raise ValueError("Choose the Image + Text workflow to use a reference.")
    return config


def scene_html(text, finish_reason=None):
    if finish_reason == "length":
        raise ValueError("CCORE ran out of room. Use a larger generation budget or simplify the prop.")
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_HTML:
        raise ValueError("The generated scene is too large.")
    start = re.search(r"<!doctype\s+html\s*>|<html(?:\s[^>]*)?>", text, re.IGNORECASE)
    end = text.lower().rfind("</html>")
    if not start or end <= start.start():
        raise ValueError("CCORE did not finish its scene. Try a different seed or a simpler description.")
    return text[start.start():end + len("</html>")]


def _index(items, value, label):
    if type(value) is not int or not 0 <= value < len(items):
        raise ValueError("Invalid GLB " + label + " reference.")
    return items[value]


def _whole(value, maximum, label):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("Invalid GLB " + label + ".")
    return value


def _inspect_document(doc, binary_length):
    pending = [doc]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if "uri" in item:
                raise ValueError("The GLB contains an external or separately encoded resource.")
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    if doc["asset"]["version"] != "2.0" or doc.get("extensionsRequired"):
        raise ValueError("The GLB requires an unsupported format or extension.")
    buffers = doc["buffers"]
    if len(buffers) != 1:
        raise ValueError("The GLB must have one embedded buffer.")
    size = _whole(buffers[0]["byteLength"], binary_length, "buffer size")
    views = doc["bufferViews"]
    for view in views:
        offset = _whole(view.get("byteOffset", 0), size, "buffer offset")
        _whole(view["byteLength"], size - offset, "buffer view size")
        if view["buffer"] != 0:
            raise ValueError("The GLB references an absent buffer.")

    accessors = doc["accessors"]
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
    widths = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
    for accessor in accessors:
        count = _whole(accessor["count"], 2_000_000, "accessor count")
        if "sparse" in accessor:
            raise ValueError("Sparse GLB data is unavailable in this workflow.")
        view = _index(views, accessor["bufferView"], "buffer view")
        width = components[accessor["type"]] * widths[accessor["componentType"]]
        offset = _whole(accessor.get("byteOffset", 0), view["byteLength"], "accessor offset")
        stride = _whole(view.get("byteStride", width), 252, "accessor stride")
        if count < 1 or stride < width or offset + (count - 1) * stride + width > view["byteLength"]:
            raise ValueError("The GLB accessor extends beyond its buffer view.")
    for image in doc.get("images", []):
        _index(views, image["bufferView"], "image buffer")
        if image.get("mimeType") not in ("image/png", "image/jpeg", "image/webp"):
            raise ValueError("The GLB contains an unsupported embedded image.")

    nodes, meshes = doc["nodes"], doc["meshes"]
    if len(nodes) > 10000 or len(meshes) > 5000:
        raise ValueError("The generated scene is too complex.")
    if len(doc["scenes"]) != 1:
        raise ValueError("The GLB must contain one scene for this prop.")
    scene = _index(doc["scenes"], doc.get("scene", 0), "scene")
    visited, mesh_instances, triangles = set(), 0, 0
    pending = [(i, 0) for i in scene.get("nodes", [])]
    while pending:
        node_index, depth = pending.pop()
        node = _index(nodes, node_index, "node")
        if node_index in visited or depth > 128:
            raise ValueError("The GLB contains a scene cycle, shared node, or excessive nesting.")
        visited.add(node_index)
        pending.extend((child, depth + 1) for child in node.get("children", []))
        if "mesh" not in node:
            continue
        mesh_instances += 1
        for primitive in _index(meshes, node["mesh"], "mesh")["primitives"]:
            positions = _index(accessors, primitive["attributes"]["POSITION"], "position")
            if positions["type"] != "VEC3":
                raise ValueError("GLB positions must contain three coordinates.")
            indices = _index(accessors, primitive["indices"], "index") if "indices" in primitive else positions
            count = indices["count"]
            mode = primitive.get("mode", 4)
            if mode == 4:
                triangles += count // 3
            elif mode in (5, 6):
                triangles += max(0, count - 2)
            if triangles > 1_000_000:
                raise ValueError("The generated prop exceeds the triangle limit.")
    if triangles == 0:
        raise ValueError("The exported GLB has no visible triangle geometry.")
    return dict(triangles=triangles, mesh_instances=mesh_instances, animations=len(doc.get("animations", [])))


def inspect_glb(path):
    size = path.stat().st_size
    if not 28 <= size <= MAX_GLB:
        raise ValueError("The exported GLB is empty or exceeds 32 MiB.")
    try:
        with path.open("rb") as stream:
            magic, version, total = struct.unpack("<4sII", stream.read(12))
            length, kind = struct.unpack("<I4s", stream.read(8))
            if magic != b"glTF" or version != 2 or total != size or kind != b"JSON" or not 0 < length <= MAX_HTML:
                raise ValueError("CCORE did not export a valid GLB 2.0 file.")
            doc = json.loads(stream.read(length))
            binary, kind = struct.unpack("<I4s", stream.read(8))
            if kind != b"BIN\0" or binary != size - stream.tell():
                raise ValueError("The GLB has an invalid binary buffer.")
        return {**_inspect_document(doc, binary), "bytes": size}
    except (KeyError, TypeError, AttributeError, RecursionError, UnicodeError, struct.error) as error:
        raise ValueError("CCORE did not export a supported, self-contained GLB.") from error
