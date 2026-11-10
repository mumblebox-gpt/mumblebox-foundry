"""Process boundary for the pinned, isolated Garment Particles runtime."""
import json
import os
from pathlib import Path
import subprocess
import time

from .contract import MODES

WORKERS = Path(__file__).with_name("workers")
PHASE = {}
CHECKPOINTS = {"text": ("pgf_text", 32), "image": ("pgf_image", 8), "sketch": ("pgf_sketch", 8)}
CLIP = ("openai/clip-vit-large-patch14", "32bd64288804d66eefd0ccbe215aa642df71cc41")
DINO = ("facebook/dinov2-large", "47b73eefe95e8d44ec3623f8890bd894b6ea2d6c")


def config():
    from ....runtime import configuration

    raw = configuration().get("garment_runtime", {})
    required = ("python", "source", "models", "hf_home")
    if not all(raw.get(key) and Path(raw[key]).is_absolute() for key in required):
        raise ValueError("Install the isolated Garment Particles runtime and its author weights before generating.")
    values = {key: Path(raw[key]) for key in required}
    if not values["python"].is_file() or not (values["source"] / "configs" / "pretrained" / "edge.yaml").is_file():
        raise ValueError("The pinned Garment Particles Python environment or author source is missing.")
    return values


def availability():
    try:
        values = config()
    except ValueError as error:
        return {mode: str(error) for mode in MODES}
    def checkpoint_ready(name, count):
        folder = values["models"] / name
        return (folder / ".metadata").is_file() and all(
            (folder / f"__{index}_0.distcp").is_file() for index in range(count))

    def encoder_ready(repo, revision):
        snapshot = values["hf_home"] / "hub" / ("models--" + repo.replace("/", "--")) / "snapshots" / revision
        return all((snapshot / file).is_file() for file in ("config.json", "model.safetensors"))

    edge_ready = checkpoint_ready("edge", 8)
    clip_ready, dino_ready = encoder_ready(*CLIP), encoder_ready(*DINO)
    missing = {}
    for mode, (name, count) in CHECKPOINTS.items():
        if not edge_ready or not checkpoint_ready(name, count):
            missing[mode] = "The selected author checkpoint or its shared pattern weights are incomplete."
        elif not clip_ready or (mode in ("image", "sketch") and not dino_ready):
            missing[mode] = "The pinned image or text encoder for this garment input is missing."
        else:
            missing[mode] = ""
    return {**missing, "surprise": missing["text"]}


def execute(runtime, program, args, out, job, phase, release_gpu=False, blender=False):
    import comfy.model_management as memory
    from ....pipeline_workers import activity

    if release_gpu:
        memory.unload_all_models()
        memory.soft_empty_cache()
    environment = dict(os.environ, HF_HOME=str(runtime["hf_home"]), HF_HUB_OFFLINE="1",
                       HF_HUB_DISABLE_TELEMETRY="1", WANDB_MODE="disabled")
    if blender:
        from ....finishing.runtime import settings

        exe = settings().get("blender", "")
        if not exe or not Path(exe).is_file():
            raise ValueError("Configure Foundry’s Blender runtime to fit and export garments.")
        command = [exe, "--background", "--factory-startup", "--python-exit-code", "1",
                   "--python", str(WORKERS / program), "--", *map(str, args)]
    else:
        command = [str(runtime["python"]), "-B", "-u", str(WORKERS / program), *map(str, args)]
    log = out / (Path(program).stem + ".log")
    model_key = "garment:" + job if program == "worker.py" else None
    if model_key:
        activity.update(model_key, "Garment Particles")
    PHASE.update(job=job, text=phase)
    try:
        with log.open("w", encoding="utf-8") as stream, subprocess.Popen(
            command, stdout=stream, stderr=subprocess.STDOUT, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        ) as child:
            try:
                offset = 0
                deadline = time.monotonic() + 1800
                while child.poll() is None:
                    memory.throw_exception_if_processing_interrupted()
                    if model_key:
                        activity.read_worker(model_key, "Garment Particles", out / "model-residency.json", child.pid)
                    if time.monotonic() > deadline:
                        raise TimeoutError("Garment Particles took more than 30 minutes. Try fewer points or steps.")
                    with log.open("r", encoding="utf-8", errors="replace") as progress:
                        progress.seek(offset)
                        for line in progress:
                            if line.startswith(("Cloth simulation frame ", "Author guidance:", "Sewing pattern: sampling")):
                                PHASE["text"] = line.strip()
                        offset = progress.tell()
                    time.sleep(.4)
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
        if child.returncode:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
            detail = next((line for line in reversed(lines) if line.startswith(
                ("RuntimeError:", "ValueError:", "FileNotFoundError:", "ImportError:"))), "")
            raise ValueError("Garment Particles could not finish. " + detail.partition(": ")[2][:1000])
    finally:
        if model_key:
            activity.remove(model_key)
        PHASE.clear()

