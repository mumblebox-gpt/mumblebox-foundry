"""Two independent native stages, also submitted by the Foundry wizard."""
import json
from pathlib import Path
from uuid import uuid4

from ...artifacts import owned_path
from . import character, edits, runtime
from .contract import EXAMPLE, MODES, identifier, mesh_options, options

GENERATE = "FoundryGarmentParticles"
SEW = "FoundryGarmentSewMesh"
DRAPE = "FoundryGarmentDrape"
FIT = "FoundryGarmentFit"
STAGE_NODE = "570100"


def directory(output, ident):
    return owned_path(output, Path(output) / "foundry-garments" / identifier(ident))


class GarmentParticles:
    CATEGORY = "Mumblebox Foundry/Garment Particles"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("garment_run",)
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "name": ("STRING", {"default": "Garment"}),
            "mode": (list(MODES), {"default": "text"}),
            "prompt": ("STRING", {"default": EXAMPLE, "multiline": True}),
            "seed": ("INT", {"default": 42, "min": 0, "max": 2147483647}),
            "points": ("INT", {"default": 4096, "min": 100, "max": 8192}),
            "steps": ("INT", {"default": 100, "min": 2, "max": 250}),
        }, "optional": {"image": ("STRING", {"default": ""}), "back_image": ("STRING", {"default": ""}),
                         "job": ("STRING", {"default": ""}), "edit": ("STRING", {"default": ""})}}

    @classmethod
    def IS_CHANGED(cls, **_):
        return float("nan")

    def generate(self, name, mode, prompt, seed, points, steps, image="", back_image="", job="", edit=""):
        import folder_paths
        from ..ccore_prop.vision import prepare_reference

        data = options(dict(name=name, mode=mode, prompt=prompt, seed=seed, points=points, steps=steps,
                            image=image, back_image=back_image))
        if edit:
            if mode not in ("text", "surprise"):
                raise ValueError("Guided editing uses the Garment Particles text checkpoint.")
            data["edit"] = edits.edit_options(json.loads(edit))
        settings = runtime.config()
        run = job or uuid4().hex
        out = directory(folder_paths.get_output_directory(), run)
        out.mkdir(parents=True, exist_ok=False)
        for key, filename in (("image", "reference.png"), ("back_image", "back-reference.png")):
            if data.get(key):
                payload, digest = prepare_reference(folder_paths.get_input_directory(), data[key])
                ref = out / filename
                ref.write_bytes(payload)
                data[key] = str(ref)
                data[key + "_sha256"] = digest
        request = out / "request.json"
        request.write_text(json.dumps({**data, "output": str(out)}), encoding="utf-8")
        runtime.execute(settings, "worker.py", ["--source", settings["source"], "--models", settings["models"],
                        "--request", request], out, run, "Generating drape and sewing pattern", release_gpu=True)
        receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
        return {"ui": {"garment": [receipt]}, "result": (run,)}


class GarmentSewMesh:
    CATEGORY = GarmentParticles.CATEGORY
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("sewn_mesh",)
    FUNCTION = "sew"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "garment_run": ("STRING", {"forceInput": True}),
            "budget": ("INT", {"default": 20000, "min": 2000, "max": 100000}),
        }}

    @classmethod
    def IS_CHANGED(cls, **_):
        return float("nan")

    def sew(self, garment_run, budget):
        import folder_paths

        budget = mesh_options({"budget": budget})["budget"]
        settings = runtime.config()
        out = directory(folder_paths.get_output_directory(), garment_run)
        if not (out / "receipt.json").is_file():
            raise ValueError("Generate and review a garment first.")
        mesh = out / "Mesh" / uuid4().hex
        mesh.mkdir(parents=True)
        runtime.execute(settings, "panel_mesh.py", ["--pattern", out / "garment_specification.json",
                        "--output", mesh, "--author-root", settings["source"].parent, "--budget", budget],
                        mesh, garment_run, "Sewing and UV-mapping polygon panels")
        receipt = json.loads((mesh / "mesh-report.json").read_text(encoding="utf-8"))
        return {"ui": {"garment": [{**receipt, "mesh_id": mesh.name}]},
                "result": (garment_run + "/" + mesh.name,)}


class GarmentDrape:
    CATEGORY = GarmentParticles.CATEGORY
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("settled_drape",)
    FUNCTION = "drape"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        controls = {key: ("FLOAT", {"default": default, "min": low, "max": high, "step": .01})
                    for key, (default, low, high) in character.DEFAULT_FIT.items()}
        return {"required": {
            "mesh_token": ("STRING", {"forceInput": True}),
            "character": ("STRING", {"default": ""}),
            "fabric": (list(character.FABRICS), {"default": "medium"}),
            "frames": ("INT", {"default": 48, "min": 16, "max": 120}),
            **controls,
        }}

    @classmethod
    def IS_CHANGED(cls, **_):
        return float("nan")

    def drape(self, mesh_token, **controls):
        import folder_paths

        ident, sep, mesh_id = mesh_token.partition("/")
        if not sep:
            raise ValueError("Build a sewn garment mesh before draping.")
        root = directory(folder_paths.get_output_directory(), ident)
        mesh = owned_path(root, root / "Mesh" / identifier(mesh_id) / "sewn-garment.glb")
        if not mesh.is_file():
            raise ValueError("Build a sewn garment mesh before draping.")
        config = character.drape_options(controls)
        body = owned_path(root, character.path(root, config["character"]))
        if not body.is_file():
            raise ValueError("Upload the target character before draping.")
        character.validate(body)
        out = root / "Drape" / uuid4().hex
        out.mkdir(parents=True)
        args = out / "request.json"
        args.write_text(json.dumps({**config, "character": str(body), "mesh": str(mesh),
                                    "output": str(out)}), encoding="utf-8")
        runtime.execute(runtime.config(), "drape.py", [args], out, ident, "Settling sewn fabric on the character", blender=True)
        receipt = json.loads((out / "drape-report.json").read_text(encoding="utf-8"))
        return {"ui": {"garment": [{**receipt, "drape_id": out.name, "mesh_id": mesh_id, "settings": config}]},
                "result": (ident + "/" + out.name,)}


class GarmentFit:
    CATEGORY = GarmentParticles.CATEGORY
    RETURN_TYPES = ()
    FUNCTION = "fit"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"mesh_token": ("STRING", {"forceInput": True})}}

    @classmethod
    def IS_CHANGED(cls, **_):
        return float("nan")

    def fit(self, mesh_token):
        import folder_paths

        ident, sep, drape_id = mesh_token.partition("/")
        if not sep:
            raise ValueError("Choose the approved drape before skinning.")
        root = directory(folder_paths.get_output_directory(), ident)
        drape = owned_path(root, root / "Drape" / identifier(drape_id))
        mesh = drape / "draped-garment.glb"
        if not mesh.is_file() or not (drape / "drape-report.json").is_file():
            raise ValueError("Simulate and review the garment before skinning.")
        settings = json.loads((drape / "request.json").read_text(encoding="utf-8"))
        body = owned_path(root / "Characters", settings["character"])
        character.validate(body)
        settings["approved_drape"] = drape_id
        out = root / "Fit" / uuid4().hex
        out.mkdir(parents=True)
        args = out / "request.json"
        args.write_text(json.dumps({**settings, "character": str(body), "mesh": str(mesh), "output": str(out)}),
                        encoding="utf-8")
        runtime.execute(runtime.config(), "fit.py", [args], out, ident, "Fitting, transferring skin and checking poses", blender=True)
        receipt = json.loads((out / "fit-report.json").read_text(encoding="utf-8"))
        return {"ui": {"garment": [{**receipt, "fit_id": out.name}]}}


NODE_CLASS_MAPPINGS = {GENERATE: GarmentParticles, SEW: GarmentSewMesh, DRAPE: GarmentDrape, FIT: GarmentFit}

