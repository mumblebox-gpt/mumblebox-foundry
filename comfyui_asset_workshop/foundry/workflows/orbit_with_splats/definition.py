"""Settings shared by the native graph, wizard and agent."""
from copy import deepcopy

from ..orbit_to_mesh import definition as orbit
from ..virtual_turntable.definition import defaults, field
from .brush import BRUSH_RELEASE, BRUSH_VERSION, brush_path, can_install

METHOD = "orbit-with-splats"
TITLE = "Orbit with Splats"
OFFSET = 810000
LICENSE_MESSAGE = orbit.LICENSE_MESSAGE
PRESETS = {
    "quick": dict(views=24, edge=512, steps=1500, max_splats=80000, sh_degree=1),
    "balanced": dict(views=48, edge=768, steps=6000, max_splats=200000, sh_degree=2),
    "high": dict(views=72, edge=1024, steps=15000, max_splats=400000, sh_degree=3),
}
SCHEMA = {"preset": field("balanced", "Choose the time, view count and detail budget for Brush.", choices=tuple(PRESETS)),
          "timeout_minutes": field(30, "Stop Brush training at this time limit and keep earlier stages.", limits=(1, 120))}
CREDITS = {
    **orbit.LICENSE_LINKS,
    "BiRefNet — ZhengPeng7 and collaborators": "https://github.com/ZhengPeng7/BiRefNet",
    "COLMAP — Johannes L. Schönberger and contributors": "https://colmap.github.io/",
    "Pixal3D — Tencent ARC Lab, Tsinghua University and Victoria University of Wellington": "https://github.com/TencentARC/Pixal3D",
    "Hi3D — Hi3DGen authors": "https://github.com/Stable-X/Hi3DGen",
    "TRELLIS.2 — Microsoft Research": "https://github.com/microsoft/TRELLIS.2",
    "Brush — Arthur Brussee and contributors (Apache-2.0)": BRUSH_RELEASE,
    "3D Gaussian Splatting — Kerbl, Kopanas, Leimkühler and Drettakis": "https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/",
    "Reference ComfyUI workflow — Enndee": "https://github.com/Enndee/Enndees_Nodepack",
}

def missing_tools():
    return orbit.missing_tools() + ([] if can_install() or brush_path().is_file() else ["brush_app.exe"])

def validate(controls):
    if not isinstance(controls, dict):
        raise ValueError("Supply Orbit with Splats settings.")
    clean = {key: value for key, value in controls.items() if key != "splat"}
    splat = defaults({"splat": SCHEMA})["splat"]
    overrides = controls.get("splat", {})
    if not isinstance(overrides, dict) or set(overrides) - set(SCHEMA):
        raise ValueError("Choose supported Brush settings.")
    splat.update(overrides)
    if not isinstance(splat["preset"], str) or splat["preset"] not in PRESETS:
        raise ValueError("Choose a splat detail preset.")
    if type(splat["timeout_minutes"]) is not int or not 1 <= splat["timeout_minutes"] <= 120:
        raise ValueError("Brush time limit must be between 1 and 120 minutes.")
    return {**orbit.validate(clean), "splat": splat}

def capabilities():
    cap = orbit.capabilities()
    cap.update(id=METHOD, missing=missing_tools(), brush_release=BRUSH_RELEASE,
               splat_presets=deepcopy(PRESETS), brush_folder=str(brush_path().parent),
               brush={"version": BRUSH_VERSION, "automatic": can_install(), "present": brush_path().is_file()},
               description="Create an aligned textured mesh and Gaussian splat from one orbit.",
               license_links=CREDITS)
    cap["controls"]["splat"] = deepcopy(SCHEMA)
    cap["defaults"] = validate({})
    return cap
