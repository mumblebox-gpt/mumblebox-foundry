"""The wizard and MCP use one schema for defaults, help and validation."""
from copy import deepcopy
import json
import math
from pathlib import Path

METHOD = "virtual-turntable"
ENGINES = {
    "meshroom": {
        "name": "Meshroom / AliceVision", "recommended": True,
        "description": "In the jade guardian test, Meshroom gave us clear carving and a usable textured starting mesh. The result had open edges and a spike above the mane.",
    },
    "colmap-openmvs": {
        "name": "COLMAP + OpenMVS", "recommended": False,
        "description": "The tuned COLMAP and OpenMVS test recovered more of the pedestal opening and avoided the mane spike. Fine carving was softer in the geometry, and some texture areas were missed.",
    },
}
LICENSE_MESSAGE = (
    "Pruna P-H3 Image, MiniMax H3 and the orbit LoRA use territory-restricted terms. "
    "See the terms and MiniMax's separate license application for use in an excluded territory. "
    "These terms can apply to outputs, including when the video is an intermediate."
)
LICENSE_LINKS = {
    "P-H3 Image terms": "https://huggingface.co/PrunaAI/P-H3-Image-Comfy/blob/main/LICENSE",
    "MiniMax H3 terms": "https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE",
    "Pablo Dawson orbit LoRA": "https://huggingface.co/pablodawson/MiniMax-H3-360-Orbit-LoRA",
    "MiniMax license application": "https://platform.minimax.io/console/license",
}
DESCRIPTION = (
    "Virtual Turntable uses AI-assisted photogrammetry to turn one reference image into a 3D mesh. "
    "In a traditional scan, you take photos from different angles around a real object. "
    "Here, AI generates a 360° orbit video, and photogrammetry matches details across the frames."
)
TIP = "The mesh comes out best when the object keeps the same shape and details throughout the orbit."


def field(default, help_text, *, limits=None, choices=None, step=None):
    return {"default": default, "help": help_text, "limits": limits, "choices": choices, "step": step}


TEMPLATE = json.loads(Path(__file__).with_name("template.json").read_text(encoding="utf-8"))
SCHEMA = {
    "turnaround": {
        "prompt": field(TEMPLATE["11"]["inputs"]["prompt"], "Describe how H3 should preserve the subject across all four views."),
        "panel_size": field(1024, "Pixels per square panel. More pixels cost VRAM.", limits=(512, 1536), step=64),
        "seed": field(42, "Change the seed to generate a different sheet.", limits=(0, 2**53-1)),
        "crops": field(TEMPLATE["19"]["inputs"]["crop_rectangles"], "Four normalized crop rectangles in front, side, three-quarter and back order."),
    },
    "orbit": {
        "prompt": field(TEMPLATE["27"]["inputs"]["orbit_prompt"], "Motion instruction for H3. Ask for one smooth turn around a stationary subject."),
        "subject_direction": field("Keep the subject rigid and its dimensions, details and materials consistent. Use even light and make one smooth full orbit.",
                                   "Add subject-specific direction such as keeping a carving or asymmetric part in place."),
        "width": field(768, "Video width in pixels. Higher resolution uses more memory.", limits=(384, 1536), step=32),
        "height": field(768, "Video height in pixels. Higher resolution uses more memory.", limits=(384, 1536), step=32),
        "length": field(73, "Number of generated frames. At 24 fps, 73 frames give about three seconds. Longer clips cost memory and time.", limits=(22, 362), step=17),
        "fps": field(24, "Playback frames per second. This controls how fast the finished clip plays.", limits=(1, 60)),
        "seed": field(42, "Change the seed to try a different orbit.", limits=(0, 2**53-1)),
        "steps": field(28, "Denoising iterations. More steps take longer.", limits=(1, 100)),
        "turbo": field(False, "Enable the tested Larry Turbo v4 adapter for the eight-step orbit recipe."),
        "turbo_strength": field(1., "Strength of the Larry Turbo v4 speed adapter when enabled.", limits=(0, 2), step=.05),
        "sampler": field("res_multistep", "Sampling method used for the orbit denoising steps.", choices=("res_multistep", "euler")),
        "scheduler": field("simple", "How noise levels are distributed across the orbit denoising steps.", choices=("simple", "beta")),
        "lora_strength": field(1.0, "How strongly Pablo Dawson’s LoRA guides the orbit motion.", limits=(0, 2), step=.05),
        "side_fraction": field(.25, "Position of the side guide as a fraction of the orbit.", limits=(.01, .99), step=.01),
        "three_quarter_fraction": field(.125, "Position of the three-quarter guide as a fraction of the orbit.", limits=(.01, .99), step=.005),
        "back_fraction": field(.5, "Position of the rear guide as a fraction of the orbit.", limits=(.01, .99), step=.01),
        "margin": field(.04, "Empty border around each normalized view. More margin leaves fewer pixels for details.", limits=(0, .35), step=.01),
        "background": field(.5, "Gray level behind the subject guides, from black (0) to white (1).", limits=(0, 1), step=.05),
        "feedforward_chunks": field(16, "Splits transformer work into more pieces to reduce peak memory.", limits=(1, 64)),
        "attention_chunks": field(28, "Splits attention to reduce peak memory. More chunks may run slower.", limits=(1, 56)),
        "decode_tile": field(256, "Spatial video decoder tile size. Smaller tiles use less VRAM.", limits=(128, 1024), step=32),
        "decode_frames": field(16, "Temporal decoder tile length. Smaller groups use less VRAM.", limits=(16, 128), step=4),
        "release_previous_models": field(True, "Release the preceding image stage’s model allocations before guide masking."),
    },
    "frames": {
        "max_frames": field(72, "Maximum number of evenly spaced usable frames. More frames cost reconstruction time.", limits=(6, 256)),
        "max_edge": field(768, "Maximum frame side in pixels. Lower it to reduce reconstruction cost.", limits=(256, 2048), step=32),
        "drop_loop_endpoint": field(True, "Discard the final frame when it repeats the opening view."),
        "exclude_indices": field("", "Comma-separated frame indices or ranges to skip, starting at zero. Remove pauses, warped views or duplicates."),
        "batch_size": field(1, "Frames masked at once. Larger batches need more VRAM.", limits=(1, 8)),
        "mask_threshold": field(.5, "Confidence required to retain a foreground pixel. Higher values can remove fine edges.", limits=(.01, .99), step=.01),
        "erode_pixels": field(0, "Shrink the foreground mask by this many pixels. This may remove thin details.", limits=(0, 16)),
        "release_previous_models": field(True, "Free orbit models before frame masking."),
        "release_gpu": field(True, "Free the masking model before running the reconstruction engine."),
    },
    "meshroom": {
        "depth_downscale": field(1, "Downsample depth inputs by this factor to trade detail for speed and memory.", choices=(1, 2, 4, 8)),
        "depth_tile": field(768, "Depth work tile in pixels. Smaller tiles reduce peak GPU use.", limits=(256, 2048), step=64),
        "neighbor_cameras": field(10, "Number of nearby views considered for depth. Larger values increase work.", limits=(2, 20)),
        "feature_density": field("high", "Search for more matching points, which can help registration and cost time.", choices=("low", "medium", "normal", "high", "ultra")),
        "min_2d_motion": field(3., "Minimum matching motion in pixels. A higher value rejects nearly identical views.", limits=(0, 20), step=.5),
        "initial_fov": field(10., "Assumed horizontal field of view in degrees. Use Auto to let Meshroom estimate it.", limits=(10, 120), step=.5),
        "camera_calibration": field("Keep chosen lens", "Fix the selected lens or estimate it from the images.", choices=("Estimate lens automatically", "Keep chosen lens")),
        "minimum_checked_fov": field(2., "Reject solved cameras below this horizontal field of view.", limits=(.1, 119), step=.1),
        "maximum_checked_fov": field(120., "Reject solved cameras above this horizontal field of view.", limits=(1, 179), step=.1),
        "texture_size": field(4096, "Atlas edge in pixels. Larger atlases preserve detail and use more memory.", choices=(2048, 4096, 8192)),
        "max_input_points": field(10000000, "Maximum input samples accepted by the mesher.", limits=(1000000, 50000000), step=1000000),
        "max_mesh_points": field(1000000, "Maximum points in the dense mesh. Raise to retain detail at higher cost.", limits=(100000, 5000000), step=100000),
        "cpu_threads": field(8, "CPU concurrency for the native engine.", limits=(1, 64)),
        "timeout_minutes": field(180, "Stop the native job when this time limit is reached.", limits=(5, 1440)),
        "advanced_overrides": field(TEMPLATE["52"]["inputs"]["advanced_overrides"], "JSON keyed by AliceVision graph node. Supply named native controls such as DepthMapFilter_1 consistency and MeshFiltering_1 smoothing."),
    },
    "colmap-openmvs": {
        "camera_model": field("PINHOLE", "Camera model used for feature alignment. Distortion models give the solver more freedom.", choices=("PINHOLE", "OPENCV", "SIMPLE_RADIAL")),
        "shared_camera": field(True, "Use a shared lens for all frames, appropriate when the orbit holds one focal length."),
        "initial_focal_factor": field(1.2, "Initial focal length divided by image size when automatically fitting the lens.", limits=(.3, 5), step=.05),
        "camera_calibration": field("Keep chosen lens", "Hold a chosen horizontal field of view or estimate the lens.", choices=("Auto fit lens", "Keep chosen lens")),
        "initial_fov": field(10., "Assumed horizontal field of view in degrees for fixed pinhole calibration.", limits=(2, 120), step=.5),
        "gpu_features": field(True, "Use the GPU for COLMAP feature matching and extraction."),
        "gpu_index": field(0, "CUDA device index for the native reconstruction.", limits=(0, 7)),
        "max_features": field(8192, "Maximum matched features per image. Higher limits cost RAM and time.", limits=(1024, 32768), step=1024),
        "depth_downscale": field(0, "0 uses full depth resolution, 1 halves it and 2 quarters it.", choices=(0, 1, 2)),
        "max_resolution": field(768, "Limit the depth image size in pixels to manage GPU memory.", limits=(256, 2048), step=32),
        "neighbor_views": field(8, "Number of nearby images used to estimate depth. More views cost time.", limits=(2, 20)),
        "refine_mesh": field(True, "Run OpenMVS photo-consistency refinement on the initial mesh."),
        "refine_on_gpu": field(True, "Use CUDA for OpenMVS refinement. Turning this off uses the CPU."),
        "refine_decimation": field(1., "Input reduction for OpenMVS refinement. 1 preserves density and 0 uses automatic reduction.", limits=(0, 1), step=.01),
        "texture_size": field(4096, "Maximum texture atlas edge in pixels.", choices=(2048, 4096, 8192)),
        "cpu_threads": field(8, "CPU concurrency for the native tools and texture projection.", limits=(1, 64)),
        "timeout_minutes": field(180, "Stop the native job when this time limit is reached.", limits=(5, 1440)),
        "advanced_overrides": field("{}", "JSON keyed by feature, match, mapper, dense, mesh, refine or texture. Use options from the pinned native tool help."),
    },
    "meshroom_finish": {
        "segmenter": field("pec", "Use parallel GPU UV charting or slower adaptive CPU charting.", choices=("pec", "adaptive")),
        "uv_resolution": field(4096, "Atlas size used to plan UV charts.", choices=(1024, 2048, 4096, 8192)),
        "uv_padding": field(1, "Pixels between UV charts to help avoid bleeding.", limits=(0, 16)),
        "uv_weld_distance": field(0., "Fraction of the mesh extent used to join nearby vertices for UV charting. Zero selects automatic.", limits=(0., .01), step=.0001),
        "unwrap_method": field("Basic", "AliceVision chart method if the input needs UVs.", choices=("Basic", "LSCM", "ABF")),
        "fill_texture_holes": field(True, "Fill gaps in the texture atlas. Geometry stays the same."),
        "weight_by_projected_area": field(False, "Favor larger projected faces. Keep this off if dense meshes produce a dark texture."),
        "memory_gib": field(12, "AliceVision texture working memory in GiB. The process can allocate additional memory.", limits=(4, 48)),
        "metallic": field(0., "Uniform metalness of the photo texture. Use zero for stone, plastic and other non-metals.", limits=(0., 1.), step=.05),
        "roughness": field(.65, "Uniform roughness of the photo texture. Lower values make reflections sharper.", limits=(0., 1.), step=.05),
    },
    "openmvs_finish": {
        "texture_triangle_target": field(200000, "Reduce the mesh before projecting photos. More triangles keep finer geometry and take longer to texture. Full density can be much slower.",
                                         choices=(100000, 200000, 350000, 500000, 0)),
        "orientation": field("Reference camera up", "Use the reference camera to orient the result, or keep the native reconstruction axes.",
                             choices=("Reference camera up", "Native reconstruction axes")),
        "ground": field(True, "Center the asset and place its lowest point on the floor."),
        "material": field("Satin", "Choose the finish for the projected texture. Custom uses the next two controls.",
                          choices=("Matte", "Satin", "Glossy", "Metal", "Custom")),
        "custom_metallic": field(0., "Metalness used with the Custom material.", limits=(0., 1.), step=.05),
        "custom_roughness": field(.45, "Roughness used with the Custom material.", limits=(0., 1.), step=.05),
        "outlier_threshold": field(.06, "Reject inconsistent projected samples using this threshold.", limits=(0., 1.), step=.01),
        "seam_leveling": field(True, "Blend colors across texture seams."),
        "advanced_texture": field('{"virtual-face-images": 3}', "JSON for additional native TextureMesh options, such as texture quality or seam leveling."),
    },
    "refinement": {
        "refine": field(False, "Use Hi3D to refine geometry from a matching orbit image. It can introduce plausible new details."),
        "reference_frame": field(-1, "Use the first registered camera automatically, or choose a matched frame index starting at 0.", limits=(-1, 255)),
        "resolution": field(1024, "Hi3D mesh detail resolution. Higher settings cost GPU memory.", choices=(512, 1024, 1536)),
        "steps": field(25, "Hi3D iterations. More iterations take longer.", limits=(1, 100)),
        "seed": field(42, "Change the seed for a different Hi3D result.", limits=(0, 2**53-1)),
        "cpu_offload": field(True, "Move inactive Hi3D modules to system RAM when supported to save VRAM."),
        "attention": field("sdpa", "Attention backend used by the existing Hi3D runtime.", choices=("sdpa",)),
        "cleanup_resolution": field(512, "Resolution of the solid remesh. Higher values can retain thinner detail at higher cost.", limits=(64, 768), step=32),
        "smoothing": field(1, "Number of cleanup smoothing passes. More passes soften bumps and fine details.", limits=(0, 10)),
        "band": field(.5, "Thickness of the remesh surface band, in voxel units.", limits=(.1, 4), step=.1),
    },
}


def defaults(schema=SCHEMA):
    return {group: {name: spec["default"] for name, spec in options.items()} for group, options in schema.items()}


def validated_settings(overrides, schema=SCHEMA):
    if not isinstance(overrides, dict) or set(overrides) - set(schema):
        raise ValueError("Choose a supported Virtual Turntable settings section.")
    values = defaults(schema)
    for group, fields in overrides.items():
        if not isinstance(fields, dict) or set(fields) - set(schema[group]):
            raise ValueError(f"Choose a supported setting in {group}.")
        for name, value in fields.items():
            spec = schema[group][name]
            default = spec["default"]
            kind = type(default)
            valid_type = (type(value) in (int, float)) if kind is float else type(value) is kind
            if not valid_type or (kind in (float, int) and not math.isfinite(value)):
                raise ValueError(f"Choose a valid {name.replace('_', ' ')}.")
            limits, choices = spec["limits"], spec["choices"]
            if choices is not None and value not in choices:
                raise ValueError(f"Choose a supported {name.replace('_', ' ')}.")
            if limits is not None and not limits[0] <= value <= limits[1]:
                raise ValueError(f"{name.replace('_', ' ').capitalize()} must be between {limits[0]} and {limits[1]}.")
            if kind is str and len(value) > 24000:
                raise ValueError(f"{name.replace('_', ' ').capitalize()} is too long.")
            if name in ("advanced_overrides", "advanced_texture"):
                if not isinstance(json.loads(value), dict):
                    raise ValueError("Native overrides must be a JSON object.")
            values[group][name] = value
    orbit = values["orbit"]
    if (orbit["length"] - 5) % 17 or orbit["width"] % 32 or orbit["height"] % 32:
        raise ValueError("Choose an H3 frame count of 5 + 17n (for example 73 or 243), and video dimensions divisible by 32.")
    if not orbit["three_quarter_fraction"] < orbit["side_fraction"] < orbit["back_fraction"]:
        raise ValueError("Place the three-quarter, side and back guides in that order.")
    camera = values.get("meshroom")
    if camera and camera["minimum_checked_fov"] >= camera["maximum_checked_fov"]:
        raise ValueError("Set the minimum field of view below the maximum.")
    return values


def capabilities():
    from .runtime import missing, SOURCES
    from ..image_to_3d.definition import DEFAULT_SELECTION, DEFAULTS
    from ..image_to_3d.readiness import viewer_module
    from ....finishing.package_catalog import VARIANTS

    return {
        "id": METHOD, "description": DESCRIPTION, "tip": TIP,
        "engines": {key: dict(info, missing=missing(key), source=SOURCES[key]) for key, info in ENGINES.items()},
        "controls": deepcopy(SCHEMA), "defaults": defaults(), "selection": DEFAULT_SELECTION,
        "finishing_defaults": DEFAULTS, "viewer": viewer_module(),
        "exports": [{"id": key, "directory": value[0], "formats": value[1], "description": value[2]}
                    for key, value in VARIANTS.items() if key != "quad_detail"],
        "license_note": LICENSE_MESSAGE, "license_links": LICENSE_LINKS,
    }
