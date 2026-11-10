"""Own uploaded character GLBs and fit parameters for one saved garment."""
import json
import math
from pathlib import Path
import struct

from .contract import identifier

MAX_CHARACTER = 150 * 1024 ** 2
FABRICS = ("light", "medium", "heavy")
DEFAULT_FIT = {"scale": (1, .05, 10), "x": (0, -5, 5), "y": (0, -5, 5), "z": (0, -5, 5),
               "clearance": (4, 0, 30)}


def options(data):
    fit = {}
    for key, (default, low, high) in DEFAULT_FIT.items():
        value = data.get(key, default)
        if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key.capitalize()} must be between {low} and {high}.")
        fit[key] = value
    return {"character": identifier(data.get("character")), **fit}


def drape_options(data):
    settings = options(data)
    fabric = data.get("fabric", "medium")
    frames = data.get("frames", 48)
    if fabric not in FABRICS:
        raise ValueError("Choose Light, Medium or Heavy fabric.")
    if type(frames) is not int or not 16 <= frames <= 120:
        raise ValueError("Choose from 16 to 120 settling frames.")
    return {**settings, "fabric": fabric, "frames": frames}


def validate(path):
    size = path.stat().st_size
    if not 20 <= size <= MAX_CHARACTER:
        raise ValueError("Choose one rigged GLB smaller than 150 MB.")
    with path.open("rb") as stream:
        magic, version, length, chunk, kind = struct.unpack("<4sIII4s", stream.read(20))
        if magic != b"glTF" or version != 2 or length != size or not 2 <= chunk <= min(12 * 1024 ** 2, size - 20) or kind != b"JSON":
            raise ValueError("Choose a valid glTF 2.0 binary character file.")
        data = json.loads(stream.read(chunk))
    if not data.get("skins"):
        raise ValueError("The character GLB needs a body with skin weights and an armature.")
    if any(item.get("uri") for item in [*data.get("buffers", []), *data.get("images", [])]):
        raise ValueError("Use a self-contained GLB with embedded buffers and textures.")


def path(root, ident):
    return Path(root) / "Characters" / (identifier(ident) + ".glb")

