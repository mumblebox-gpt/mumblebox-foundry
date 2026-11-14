"""Native Brush stage for the aligned mesh and Gaussian pair."""
import json
import os
from pathlib import Path
import uuid

from ....finishing.grounding import ground_glb, validate_frame
from ...artifacts import digest, owned_path
from ..orbit_to_mesh import nodes as camera_ops
from ..virtual_turntable.processes import release_models, run_process
from .dataset import prepare_dataset
from .definition import BRUSH_RELEASE, BRUSH_SHA256, BRUSH_VERSION, PRESETS, brush_path

class TrainPair:
    CATEGORY = "Foundry/Orbit with Splats"
    FUNCTION = "train"
    RETURN_TYPES = ("FILE_3D_PLY", "FILE_3D")
    RETURN_NAMES = ("aligned Gaussian splat", "aligned textured mesh")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "cameras": ("V360_PIXAL_CAMERAS",),
            "mesh": ("MESH",),
            "textured_mesh": ("FILE_3D",),
            "grounding_json": ("STRING", {"forceInput": True}),
            "front_frame": ("INT", {"default": -1, "min": -1, "max": 17999}),
            "preset": (list(PRESETS), {"default": "balanced"}),
            "timeout_minutes": ("INT", {"default": 30, "min": 1, "max": 120}),
        }}

    def train(self, cameras, mesh, textured_mesh, grounding_json, front_frame, preset, timeout_minutes):
        from comfy_api.latest import Types
        from comfy import model_management
        import folder_paths

        exe = brush_path()
        if not exe.is_file():
            raise ValueError("Install Brush to train the Gaussian splat.")
        if digest(exe) != BRUSH_SHA256:
            raise ValueError("Install the verified Windows build of Brush 0.3.0.")
        output = Path(folder_paths.get_output_directory()).resolve()
        camera_dir = owned_path(output, cameras["camera_text"])
        for key in ("images", "masks"):
            owned_path(output, cameras[key])
        owned_path(output, camera_dir / "points3D.txt")
        root = output / "foundry" / "orbit-with-splats" / ("pair-" + uuid.uuid4().hex)
        grounding = json.loads(grounding_json)
        frame = validate_frame(grounding)
        budget = PRESETS[preset]
        _, alignment = prepare_dataset(root, cameras, mesh, grounding, front_frame, budget, camera_ops)
        model_management.throw_exception_if_processing_interrupted()
        release_models()
        ply = root / "gaussian-splat.ply"
        command = [str(exe.resolve()), str(root / "dataset"), "--total-steps", str(budget["steps"]),
                   "--max-resolution", str(budget["edge"]), "--max-splats", str(budget["max_splats"]),
                   "--sh-degree", str(budget["sh_degree"]), "--refine-every", str(budget["views"]),
                   "--growth-stop-iter", str(int(budget["steps"] * .8)), "--export-every", str(budget["steps"]),
                   "--export-path", str(root), "--export-name", ply.name, "--seed", "42"]
        run_process(command, root, os.environ.copy(), root / "brush.log", timeout_minutes * 60)
        model_management.throw_exception_if_processing_interrupted()
        with ply.open("rb") as stream:
            header = stream.read(8192).split(b"end_header", 1)[0]
        if not all(field in header for field in (b"element vertex", b"f_dc_0", b"opacity", b"scale_0", b"rot_0")):
            raise ValueError("Brush did not export a supported Gaussian PLY.")
        count = int(next(line.split()[-1] for line in header.splitlines() if line.startswith(b"element vertex ")))
        source = textured_mesh.get_source()
        if not isinstance(source, str):
            source = str(root / "texture-source.glb")
            textured_mesh.save_to(source)
        glb = root / "textured-mesh.glb"
        ground_glb(owned_path(output, source), glb, frame, floor=False)
        manifest = root / "pair.json"
        manifest.write_text(json.dumps({
            "schema": "mumblebox.orbit-splat-pair/1", "world": "shared right-handed Y-up frame",
            "splat": ply.name, "mesh": glb.name, "alignment": "alignment.json",
            "preset": preset, "gaussians": count, "brush_version": BRUSH_VERSION, "brush_source": BRUSH_RELEASE,
            "training_views": len(alignment["source_frames"]),
        }, indent=2), encoding="utf-8")
        return {"ui": {"text": [str(manifest)]}, "result": (Types.File3D(str(ply)), Types.File3D(str(glb)))}

NODE_CLASS_MAPPINGS = {"FoundryOrbitTrainSplatPair": TrainPair}
