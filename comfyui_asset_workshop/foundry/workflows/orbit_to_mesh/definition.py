"""One source of presets, controls and validation for the wizard and MCP."""
from copy import deepcopy
from pathlib import Path

from ..image_to_3d.definition import CHOICES, DEFAULTS, RANGES, resolve_settings
from ..virtual_turntable.definition import LICENSE_LINKS, LICENSE_MESSAGE, SCHEMA as ORBIT_SOURCE
from ..virtual_turntable.definition import defaults as schema_defaults, field, validated_settings
from ..virtual_turntable.runtime import runtime_settings

METHOD = "orbit-to-mesh"
TITLE = "Orbit to Mesh"
OFFSET = 790000
DESCRIPTION = "Turn one image into an AI-generated orbit. Review matched views before Pixal3D builds a mesh. Hi3D and TRELLIS.2 finish the asset."
TIP = "Use a clear reference of one subject. Check the orbit for changes in shape and details before building the mesh."

ORBIT_PRESETS = {
    "full_steps": {"width": 768, "height": 768, "length": 73, "steps": 28, "turbo": False, "sampler": "res_multistep", "scheduler": "simple"},
    "standard": {"width": 768, "height": 768, "length": 243, "steps": 8, "turbo": True, "sampler": "euler", "scheduler": "beta"},
    "low_vram": {"width": 512, "height": 512, "length": 73, "steps": 8, "turbo": True, "sampler": "euler", "scheduler": "beta"},
}
VIEW_PRESETS = {"2": 2, "4": 4, "6": 6, "8 (experimental)": 8}
SELECTION = {"schema": "mumblebox.export-selection/1", "variants": {
    "detailed": {"formats": ["glb"]}, "game_balanced": {"formats": ["glb"]}}}

SCHEMA = {key: deepcopy(ORBIT_SOURCE[key]) for key in ("turnaround", "orbit", "frames")}
for key, value in ORBIT_PRESETS["full_steps"].items():
    SCHEMA["orbit"][key]["default"] = value
SCHEMA["camera"] = {
    "camera_calibration": field("Auto fit lens", "Fit one shared focal length, or hold it at the chosen field of view.",
                                choices=("Auto fit lens", "Keep chosen lens")),
    "initial_fov": field(20., "Starting horizontal field of view in degrees. Fixed mode uses it as the exact lens.", limits=(2., 120.)),
    "max_features": field(10000, "Maximum features per frame. More features can help alignment and increase processing time.", limits=(1024, 40000)),
    "gpu_features": field(True, "Use the GPU to find and match image features."),
    "cpu_threads": field(8, "CPU threads available to COLMAP.", limits=(1, 64)),
    "timeout_minutes": field(20, "Maximum minutes allowed for camera alignment.", limits=(1, 180)),
}
SCHEMA["views"] = {
    "preset": field("4", "Choose how many evenly spaced views to propose. Eight is experimental and can use more memory.", choices=tuple(VIEW_PRESETS)),
    "front_frame": field(-1, "Source frame for the front of the mesh. Use -1 for the earliest registered frame.", limits=(-1, 17999)),
    "max_angle_error": field(35., "Reject proposed views farther than this many degrees from their target.", limits=(5., 60.)),
    "sharpness_window": field(8., "Prefer sharper frames within this many degrees of the closest candidate. Use zero to choose by angle only.", limits=(0., 20.)),
}
SCHEMA["pixal"] = {
    "shape_resolution": field(1024, "Geometry detail resolution. Higher settings take more GPU memory.", choices=CHOICES["shape_resolution"]),
    "seed": field(42, "Change the seed to generate a different mesh from the same views.", limits=(0, 2**53-15)),
    "structure_shift": field(5., "Shift the structure sampling schedule. Higher values favor earlier structure decisions.", limits=(1., 20.)),
}
for name, steps in (("structure", 12), ("shape", 20), ("detail", 12)):
    SCHEMA["pixal"].update({
        f"{name}_steps": field(steps, "Denoising iterations for this pass. More iterations take longer.", limits=(1, 100)),
        f"{name}_cfg": field(7.5, "How strongly this pass follows the selected image views.", limits=(0., 20.)),
        f"{name}_sampler": field("euler", "Sampling algorithm for this Pixal3D pass.", choices=("euler", "euler_ancestral", "res_multistep", "dpmpp_2m")),
        f"{name}_scheduler": field("simple" if name == "detail" else "normal", "Noise schedule for this Pixal3D pass.",
                                   choices=("normal", "simple", "beta", "karras")),
        f"{name}_denoise": field(1., "Fraction of the noise schedule used for this pass.", limits=(.1, 1.), step=.05),
    })
SCHEMA["refinement"] = {
    "refine_resolution": field(1024, "Hi3D mesh detail resolution. Higher settings cost GPU memory.", choices=CHOICES["refine_resolution"]),
    "refine_steps": field(25, "Hi3D iterations. More iterations take longer.", limits=RANGES["refine_steps"]),
    "refine_seed": field(42, "Change the seed to try a different refinement.", limits=RANGES["refine_seed"]),
    "cpu_offload": field(True, "Move inactive Hi3D modules to system RAM when supported to save VRAM."),
    "attention": field("sdpa", "Attention backend used by the existing Hi3D runtime.", choices=CHOICES["attention"]),
    "intake_triangles": field(1000000, "Reduce a copy of the rough mesh to this triangle limit before Hi3D. The saved rough mesh stays available.",
                              limits=(10000, 4500000), step=1000),
    "cleanup_resolution": field(512, "Voxel resolution used when open geometry needs repair.", limits=(64, 768), step=32),
    "cleanup_band": field(1., "Thickness of the remeshing surface band in voxels.", limits=(.1, 4.), step=.1),
    "cleanup_smoothing": field(0, "Extra smoothing passes when remeshing open geometry. More can soften detail.", limits=(0, 10)),
    "cleanup_project_back": field(0., "Pull the remeshed surface toward the input surface. Zero leaves the voxel surface unchanged.", limits=(0., 1.), step=.05),
}
SCHEMA["texture"] = {
    "texture_triangles": field(500000, "Limit triangles sent to texturing and UV unwrapping. The clean master is preserved. Zero uses the full mesh.",
                               choices=(250000, 500000, 1000000, 2000000, 0)),
    "texture_size": field(2048, "Texture and bake size in pixels. Larger maps use more memory.", choices=CHOICES["texture_size"]),
    "texture_mode": field("standard", "Use standard TRELLIS.2 sampling or the shorter SMD recipe.", choices=CHOICES["texture_mode"]),
    "texture_steps": field(20, "Standard TRELLIS.2 sampling iterations. SMD uses its own fixed settings.", limits=RANGES["texture_steps"]),
    "texture_guidance": field(3., "How strongly standard texturing follows the reference image.", limits=RANGES["texture_guidance"]),
    "texture_seed": field(42, "Change the seed for a different texture.", limits=(0, 2147483647)),
    "texture_sampler": field("euler", "Sampler used by standard TRELLIS.2 texturing. SMD uses its own recipe.", choices=("euler", "heun")),
    "guidance_rescale": field(.2, "Rescale texture guidance to moderate strong color shifts.", limits=(0., 1.), step=.01),
    "reference_lock": field(0., "Increase to keep the painted texture closer to the reference image.", limits=(0., 1.), step=.01),
    "reference_substeps": field(2, "Number of substeps when locking the texture to the reference.", limits=(1, 8)),
}
SCHEMA["bake"] = {
    "cage_distance": field(.01, "Ray distance around the reduced mesh when baking normals.", limits=(.0001, .1), step=.0001),
    "ignore_backfaces": field(True, "Skip faces pointing away from a baking ray to avoid sampling the opposite side."),
    "grounding": field("level", "Level the support surface, place the asset on the floor, or keep its original orientation.",
                       choices=("level", "place", "original")),
}



def defaults():
    return schema_defaults(SCHEMA)


def validate(controls):
    values = validated_settings(controls, SCHEMA)
    for group, fields in SCHEMA.items():
        for key, spec in fields.items():
            if type(spec["default"]) is float:
                values[group][key] = float(values[group][key])
    return values


def settings(controls, overrides):
    fixed = {"shape_resolution": controls["pixal"]["shape_resolution"], **{key: value for key, value in controls["texture"].items() if key in DEFAULTS},
             **{key: value for key, value in controls["refinement"].items() if key in DEFAULTS}}
    if set(overrides) - {"balanced_triangles", "compact_triangles", "quad_count", "quad_method", "quad_options", "print_height_mm"}:
        raise ValueError("Choose advanced stage controls or a supported export override.")
    return resolve_settings("default", {**fixed, **overrides})


def missing_tools():
    path = Path(runtime_settings()["colmap"])
    return [] if path.is_file() else [path.name]


def capabilities():
    from ..image_to_3d.readiness import viewer_module
    from ....finishing.package_catalog import VARIANTS

    return {
        "id": METHOD, "description": DESCRIPTION, "tip": TIP, "controls": deepcopy(SCHEMA),
        "defaults": defaults(), "orbit_presets": ORBIT_PRESETS, "view_presets": VIEW_PRESETS,
        "selection": SELECTION, "finishing_defaults": settings(defaults(), {}), "finishing_ranges": RANGES, "viewer": viewer_module(),
        "exports": [{"id": key, "directory": value[0], "formats": value[1], "description": value[2]}
                    for key, value in VARIANTS.items() if key != "quad_detail"],
        "license_note": LICENSE_MESSAGE, "license_links": {
            **LICENSE_LINKS, "Pixal3D — Tencent ARC Lab, Tsinghua University and Victoria University of Wellington":
            "https://github.com/TencentARC/Pixal3D", "COLMAP": "https://colmap.github.io/",
        },
        "missing": missing_tools(), "setup_source": "https://github.com/colmap/colmap/releases/tag/4.2.1",
    }
