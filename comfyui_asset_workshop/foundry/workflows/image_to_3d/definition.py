"""Pure settings and public capabilities for the first guided workflow."""
from copy import deepcopy
from ...quad_policy import DEFAULT_METHOD, METHODS, validate_options

WORKFLOW_ID = "image-to-3d/v1"
VERSION = "2026-11-01.1"
DEFAULTS = {
    "turnaround_seed": 939810832464276, "shape_resolution": 1024,
    "refine_resolution": 1536, "refine_steps": 25, "refine_seed": 42,
    "cpu_offload": True, "attention": "sdpa", "texture_seed": 42,
    "texture_mode": "standard", "texture_steps": 20, "texture_size": 4096, "texture_guidance": 3.0,
    "balanced_triangles": 250000, "compact_triangles": 100000,
    "quad_count": 25000, "quad_method": DEFAULT_METHOD, "quad_options": {}, "print_height_mm": 100.0,
}
CHOICES = {"shape_resolution": (1024, 1536, 2048),
           "refine_resolution": (512, 1024, 1536),
           "texture_size": (1024, 2048, 4096), "attention": ("sdpa",),
           "texture_mode": ("standard", "smd"), "quad_method": tuple(METHODS)}
RANGES = {"turnaround_seed": (0, 2**53-1), "refine_seed": (0, 2**53-1),
          "texture_seed": (0, 2**53-1), "refine_steps": (1, 100),
          "texture_steps": (1, 100), "texture_guidance": (0, 20),
          "balanced_triangles": (1000, 1000000), "compact_triangles": (1000, 1000000),
          "quad_count": (1000, 100000), "print_height_mm": (1, 10000)}
DEFAULT_SELECTION = {"schema": "mumblebox.export-selection/1", "variants": {
    "detailed": {"formats": ["glb"]}, "game_compact": {"formats": ["glb"]}}}
CATEGORIES = [
    {"id": "characters", "name": "Character", "description": "A humanoid character with its whole body visible.", "qualified": True},
    {"id": "creatures", "name": "Creature", "description": "An animal, monster or non-humanoid character. Keeps its own anatomy and stance.", "qualified": True},
    {"id": "vehicles", "name": "Vehicle", "description": "One car, spacecraft or other vehicle, with fixed wheels, wings and attachments.", "qualified": True},
    {"id": "props", "name": "Prop", "description": "One object, tool, accessory or piece of equipment, including attached parts.", "qualified": True},
    {"id": "environment", "name": "Environment piece", "description": "One building, rock formation or coherent set piece. Supply an isolated piece, not an entire scene or level.", "qualified": True},
]

def texture_sampling_settings(settings, selected):
    """Keep historical Standard cache signatures and record effective SMD controls."""
    if settings.get("texture_mode") == "smd":
        return {**selected, "texture_mode": "smd", "texture_steps": 4, "texture_guidance": 1.0}
    return selected


def resolve_settings(profile, overrides):
    if profile != "default":
        raise ValueError("Only the Default memory profile is configured.")
    if not isinstance(overrides, dict) or overrides.keys() - DEFAULTS.keys():
        raise ValueError("An unsupported workflow setting was supplied.")
    result = deepcopy(DEFAULTS)
    for name, value in overrides.items():
        if name == "quad_options":
            result[name] = validate_options(value)
            continue
        default = DEFAULTS[name]
        if isinstance(default, bool):
            valid = isinstance(value, bool)
        elif isinstance(default, int):
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif isinstance(default, float):
            valid = isinstance(value, (float, int)) and not isinstance(value, bool)
        else:
            valid = isinstance(value, str)
        if not valid:
            raise ValueError("Invalid value for " + name.replace("_", " ") + ".")
        if name in CHOICES and value not in CHOICES[name]:
            raise ValueError("Unsupported " + name.replace("_", " ") + ".")
        if name in RANGES and not RANGES[name][0] <= value <= RANGES[name][1]:
            raise ValueError("Out-of-range " + name.replace("_", " ") + ".")
        result[name] = value
    return result
