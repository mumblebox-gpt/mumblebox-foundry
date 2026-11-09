"""ComfyUI execution node for CCORE; the wizard submits this same node."""
from pathlib import Path
import tempfile
import uuid

from .contract import EXAMPLE, TOKEN_LIMITS, options
from . import generation

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
        }, "optional": {"job": ("STRING", {"default": ""})}}

    @classmethod
    def IS_CHANGED(cls, **_):
        return float("nan")

    def generate(self, name, prompt, seed, max_tokens, job=""):
        import comfy.model_management as memory
        import folder_paths
        from .... import models

        settings = options(dict(name=name, prompt=prompt, seed=seed, max_tokens=max_tokens))
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
            with tempfile.TemporaryDirectory(prefix="foundry-ccore-", dir=temp_root) as directory:
                glb, measurements = generation.generate(settings, Path(directory), check)
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
                                    "type": "output", "measurements": measurements}]}}
        finally:
            generation.STATE.clear()


NODE_CLASS_MAPPINGS = {NODE_ID: FoundryCCOREProp}
