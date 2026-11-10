"""Stable quad settings and export attribution, independent of ComfyUI."""
import json
from pathlib import Path

DEFAULT_METHOD = "quadriflow"
METHODS = {
    "quadriflow": ("QuadriFlow", "CPU", "Foundry’s compatible default. Preserves sharp edges and boundaries by default. CPU spikes are normal, and dense meshes can take several minutes."),
    "instant_meshes": ("Instant Meshes", "CPU", "Good first choice for a quick CPU solve. If touching surfaces cause trouble, Foundry can repair the guide and retry."),
    "cyber_cuda": ("CyberRemesher", "NVIDIA CUDA", "Choose this for NVIDIA CUDA acceleration. It needs free GPU memory, and guide preparation, baking and export still take time."),
}


def option(label, default, description, **constraints):
    return {"label": label, "default": default, "description": description, **constraints}


OPTIONS = {
    "shared": {
        "guide_triangles": option("Guide triangle limit", 100000, "Caps the working triangle mesh. Lower values reduce work and can lose thin details.", min=10000, max=200000, step=1000),
        "cage_distance": option("Bake search distance", .01, "Increase this if baked details miss the surface. Too much can pick up neighboring parts.", min=.001, max=.05, step=.001),
        "reuse_geometry": option("Reuse matching geometry", True, "Reuses a saved solve when its input and solver settings match. Turn off to solve again."),
    },
    "quadriflow": {
        "seed": option("Seed", 42, "Change the seed to try a different quad layout with the same mesh.", min=0, max=2147483647, step=1),
        "preserve_sharp": option("Preserve sharp edges", True, "Gives corners and creases more influence on where the quads flow."),
        "preserve_boundary": option("Preserve boundaries", True, "Gives existing open edges more influence when building the quad layout."),
        "adaptive_scale": option("Adaptive quad size", False, "Lets quad size vary across the surface to follow local shape."),
        "aggressive_sat": option("Aggressive SAT solver", False, "Allows a more intensive search for consistent quad connections. Can take longer."),
        "minimum_cost_flow": option("Minimum-cost flow", False, "Tries the solver's alternative connectivity optimization. Layout and runtime can change."),
    },
    "instant_meshes": {
        "crease_angle": option("Crease angle", -1.0, "Use -1 for smooth normals. A positive angle keeps edges sharper above that angle. Zero treats nearly every edge as a crease.", min=-1, max=180, step=1),
        "align_to_boundaries": option("Align to boundaries", True, "Tries to make the quads follow open edges on the guide."),
        "extrinsic": option("Surface alignment", True, "On uses 3D positions and normals to align the field. Off uses intrinsic alignment along the surface."),
        "smooth_iter": option("Smoothing passes", 2, "More passes smooth and reproject the quad layout. Extra passes can soften small details.", min=0, max=10, step=1),
        "deterministic": option("Repeatable layout", True, "Keeps the solve repeatable with identical input and settings."),
        "repair_guide": option("Retry with a contact-repaired guide", True, "If the first guide fails, rebuilds small contacts on a disposable copy before trying again."),
        "repair_resolution": option("Contact repair resolution", 220, "Higher values keep smaller details in the repair guide and use more memory.", min=128, max=384, step=1),
    },
    "cyber_cuda": {
        "layout": option("CUDA layout", "field-aligned", "Field-aligned is the tested default. Quad-cover tries a feature-aware layout and can take substantially longer.",
                         choices={"field-aligned": "Field-aligned", "quad-cover": "Quad-cover"}),
        "adaptivity": option("Adaptivity", 1.0, "Higher values vary quad size more with curvature.", min=0, max=1, step=.05),
        "sharp_edge": option("Sharp-edge angle", 90.0, "Edges sharper than this angle can guide the quad layout.", min=0, max=180, step=1),
        "smooth_normal": option("Smooth projection angle", 0.0, "Higher values smooth projection normals across more edges.", min=0, max=180, step=1),
        "edge_scale": option("Edge scale", 1.0, "Higher values aim for wider spacing. Foundry still checks the resulting face count.", min=.25, max=4, step=.05),
        "hole_fill": option("Solver hole size limit", 64, "Controls which openings CyberRemesher may close during its solve. Foundry checks the finished surface afterward.", min=0, max=64, step=1),
        "symmetry": option("Mirror layout", "none", "Choose a local axis to mirror connectivity across the middle of the guide. Use it for a symmetric object.",
                           choices={"none": "Off", "x": "X", "y": "Y", "z": "Z"}),
    },
}


def validate_options(options):
    if not isinstance(options, dict) or options.keys() - OPTIONS.keys():
        raise ValueError("Choose supported advanced quad settings.")
    result = {}
    for group, values in options.items():
        fields = OPTIONS[group]
        if not isinstance(values, dict) or values.keys() - fields.keys():
            raise ValueError("Choose supported advanced quad settings.")
        overrides = {}
        for name, value in values.items():
            spec = fields[name]
            default = spec["default"]
            valid_type = type(value) is type(default) or type(default) is float and type(value) is int
            if (not valid_type or "min" in spec and not spec["min"] <= value <= spec["max"]
                    or "choices" in spec and value not in spec["choices"]):
                raise ValueError(f"Choose a valid value for {spec['label']}.")
            if value != default:
                overrides[name] = value
        if overrides:
            result[group] = overrides
    return result


def active_options(settings):
    """Only settings for this solver and the shared finishing path affect its stage."""
    options = settings.get("quad_options", {})
    return {key: options[key] for key in ("shared", settings.get("quad_method", DEFAULT_METHOD)) if key in options}

def fingerprint_fields(settings):
    result = {}
    method = settings.get("quad_method", DEFAULT_METHOD)
    if method != DEFAULT_METHOD:
        result["quad_method"] = method
    options = active_options(settings)
    if options:
        result["quad_options"] = options
    return result


def option_values(group, overrides=None):
    fields = OPTIONS[group]
    return {**{name: spec["default"] for name, spec in fields.items()}, **(overrides or {})}

def node_options(settings):
    method = settings.get("quad_method", DEFAULT_METHOD)
    options = active_options(settings)
    return {"method": method, **option_values("shared", options.get("shared")),
            "solver_options_json": json.dumps(options.get(method, {}), sort_keys=True)}


def resource_ids(geometry):
    labels = {"QuadriFlow 0.2.0": "quadriflow", "instant_meshes": "instant_meshes",
              "CyberRemesher CUDA": "cyber_cuda", "meshlib": "meshlib"}
    return list(dict.fromkeys(labels[item["method"]] for item in geometry.get("methods", [])
                              if item.get("method") in labels))


def manifest_resources(manifest):
    report = json.loads(Path(manifest).read_text(encoding="utf-8"))
    return resource_ids(report.get("geometry", {}))

