"""ComfyUI execution node for CCORE; the wizard submits this same node."""
from pathlib import Path
import tempfile
import uuid

from .contract import EXAMPLE, IMAGE_MODE, MODEL_KEYS, TEXT_MODE, TOKEN_LIMITS, default_model_variant, options
from . import generation, vision
from .gpu import BudgetDoesNotFit

NODE_ID = "FoundryCCOREProp"
PROMPT_NODE = "510100"


def graph(config, job=""):
    return {PROMPT_NODE: {"class_type": NODE_ID, "inputs": {**config, "job": job},
                          "_meta": {"title": "CCORE · Generate and export prop"}}}


class FoundryCCOREProp:
    CATEGORY = "Mumblebox Foundry/CCORE"
    RETURN_TYPES = ()
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "name": ("STRING", {"default": "Sci-fi cargo crate"}),
            "prompt": ("STRING", {"default": EXAMPLE, "multiline": True}),
            "seed": ("INT", {"default": 42, "min": 0, "max": 2**31 - 1}),
            "max_tokens": (list(TOKEN_LIMITS), {"default": 65536}),
        }, "optional": {
            "job": ("STRING", {"default": ""}),
            "model_variant": (list(MODEL_KEYS), {"default": default_model_variant()}),
            "mode": ([TEXT_MODE, IMAGE_MODE], {"default": TEXT_MODE}),
            "image": ("STRING", {"default": ""}),
        }}

    @classmethod
    def IS_CHANGED(cls, **_):
        return float("nan")

    def generate(self, name, prompt, seed, max_tokens, job="", model_variant=None, mode=TEXT_MODE, image=""):
        import comfy.model_management as memory
        import folder_paths
        from .... import models

        data = dict(name=name, prompt=prompt, seed=seed, max_tokens=max_tokens, mode=mode, image=image)
        if model_variant is not None:
            data["model_variant"] = model_variant
        settings = options(data)
        ident = uuid.uuid4().hex
        temp_root = Path(folder_paths.get_temp_directory())
        temp_root.mkdir(parents=True, exist_ok=True)
        generation.STATE.update(job=job, phase="Preparing CCORE")

        def check():
            try:
                memory.throw_exception_if_processing_interrupted()
            except memory.InterruptProcessingException:
                if models.DOWNLOAD.get("owner") == job and models.DOWNLOAD.get("status") == "running":
                    models.DOWNLOAD["cancel"] = True
                raise

        try:
            reference = {}
            image_bytes = None
            if settings.get("mode") == IMAGE_MODE:
                image_bytes, reference_hash = vision.prepare_reference(folder_paths.get_input_directory(), settings["image"])
                reference["prepared_reference_sha256"] = reference_hash
            with tempfile.TemporaryDirectory(prefix="foundry-ccore-", dir=temp_root) as directory:
                try:
                    glb, measurements = generation.generate(settings, Path(directory), check, image=image_bytes)
                except BudgetDoesNotFit as error:
                    if not job:
                        raise
                    return {"ui": {"ccore": [{"error": str(error), "smaller_budget": error.smaller_budget,
                                               "fallbacks": error.fallbacks}]}}
                check()
                subfolder = "foundry-ccore/" + ident + "/Prop"
                destination = Path(folder_paths.get_output_directory()) / subfolder
                destination.mkdir(parents=True)
                # Temp and output can be on different drives.
                import shutil
                partial = destination / "prop.glb.part"
                shutil.copyfile(glb, partial)
                partial.replace(destination / "prop.glb")
            return {"ui": {"ccore": [{"filename": "prop.glb", "subfolder": subfolder,
                                    "type": "output", "measurements": measurements, **reference}]}}
        finally:
            generation.STATE.clear()


NODE_CLASS_MAPPINGS = {NODE_ID: FoundryCCOREProp}
