"""Fail closed unless the pinned CCORE runtime can use dedicated NVIDIA memory."""
import re
import subprocess

from .contract import IMAGE_MAX_TOKENS, STANDARD_MODEL, TOKEN_LIMITS

RESERVE_MIB = 1024
# The pinned fit tool projects only the language model. Reserve additional
# space for the BF16 projector, CUDA workspace, and reference encoding.
VISION_RESERVE_MIB = 2048
CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FIT = re.compile(r"projected to use (\d+) MiB of device memory vs\. (\d+) MiB of free device memory")
GPU_REQUIRED = ("CCORE needs an NVIDIA CUDA GPU. Start ComfyUI with a CUDA device "
                "and a working NVIDIA driver to generate a prop.")


class BudgetDoesNotFit(ValueError):
    def __init__(self, model_variant, selected, required, free, fallbacks, *, vision=False):
        self.fallbacks = fallbacks
        self.smaller_budget = next((choice["max_tokens"] for choice in fallbacks
                                    if choice["model_variant"] == model_variant), None)
        precision = "Standard (Q4_K_M)" if model_variant == STANDARD_MODEL else "Higher precision (Q8_0)"
        reference = " with this reference" if vision else ""
        message = (f"{precision} at {selected:,} tokens{reference} needs about {required / 1024:.1f} GiB of free GPU "
                   f"memory, including 1 GiB of headroom. Your GPU has {free / 1024:.1f} GiB free.")
        if fallbacks:
            message += " Choose an option that fits or free GPU memory."
        else:
            message += " Free GPU memory or change model precision or budget, then try again."
        super().__init__(message)


def comfy_device():
    import comfy.model_management as memory
    import torch

    device = memory.get_torch_device()
    if device.type != "cuda" or not torch.version.cuda or not torch.cuda.is_available():
        raise ValueError(GPU_REQUIRED)
    index = device.index if device.index is not None else torch.cuda.current_device()
    uuid = getattr(torch.cuda.get_device_properties(index), "uuid", None)
    if uuid is None:
        raise ValueError("CCORE could not identify ComfyUI's NVIDIA GPU. Check the CUDA installation.")
    return f"CUDA{index}", f"GPU-{str(uuid).removeprefix('GPU-')}"


def run_probe(command, cwd):
    try:
        return subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=15,
                              creationflags=CREATE_FLAGS)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("CCORE could not check GPU memory. Verify the NVIDIA driver and local runtime.") from error


def dedicated_free(gpu_id, cwd):
    # On Windows, cudaMemGetInfo can report per-process headroom far above
    # dedicated VRAM free across the desktop. Use the same GPU's driver reading.
    result = run_probe(["nvidia-smi", "-i", gpu_id, "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits"], cwd)
    free = result.stdout.strip()
    if result.returncode or not free.isdecimal():
        raise ValueError("CCORE could not read free NVIDIA GPU memory. Check the NVIDIA driver and try again.")
    return int(free)


def cuda_args(checkpoint, budget, device, *, vision=False):
    context = budget + 4096 + (IMAGE_MAX_TOKENS if vision else 0)
    return ["--model", str(checkpoint), "--parallel", "1", "--ctx-size", str(context),
            "--device", device, "--gpu-layers", "all"]


def measured_fit(result, dedicated, *, vision=False):
    log = result.stderr + result.stdout
    match = FIT.search(log)
    if not match:
        raise ValueError("CCORE could not verify GPU placement. Check that the local runtime supports NVIDIA CUDA.")
    projected, runtime_free = (int(value) for value in match.groups())
    required = projected + RESERVE_MIB + (VISION_RESERVE_MIB if vision else 0)
    free = min(runtime_free, dedicated)
    if projected <= 0 or (required <= free and result.returncode):
        raise ValueError("CCORE could not verify GPU placement. Check the NVIDIA driver and local runtime.")
    return required, free


def check_budgets(selected, measure, check, *, model_variant=STANDARD_MODEL, standard_measure=None, vision=False):
    required, free = measure(selected)
    if required <= free:
        return
    smaller = [budget for budget in reversed(TOKEN_LIMITS) if budget < selected]
    fallbacks = []
    choices = [(model_variant, smaller, measure)]
    if model_variant != STANDARD_MODEL and standard_measure is not None:
        choices.insert(0, (STANDARD_MODEL, [selected, *smaller], standard_measure))
    for variant, budgets, probe in choices:
        for budget in budgets:
            check()
            fit = probe(budget)
            if fit is None:
                break
            needed, available = fit
            if needed <= available:
                fallbacks.append({"model_variant": variant, "max_tokens": budget})
                break
    raise BudgetDoesNotFit(model_variant, selected, required, free, fallbacks, vision=vision)


def preflight(executable, checkpoint, budget, device, gpu_id, check, *,
              model_variant=STANDARD_MODEL, standard_checkpoint=None, vision=False):
    fitter = executable.with_name("llama-fit-params" + executable.suffix)

    def measure(model, candidate):
        check()
        result = run_probe([str(fitter), *cuda_args(model, candidate, device, vision=vision),
                            "--fit", "on", "--fit-target", str(RESERVE_MIB), "--log-verbosity", "4"],
                           executable.parent)
        check()
        return measured_fit(result, dedicated_free(gpu_id, executable.parent), vision=vision)

    standard_measure = None
    if standard_checkpoint is not None:
        standard_measure = lambda candidate: measure(standard_checkpoint, candidate)
    check_budgets(budget, lambda candidate: measure(checkpoint, candidate), check,
                  model_variant=model_variant, standard_measure=standard_measure, vision=vision)
    check()


def verify_placement(log, device, *, vision=False):
    layers = re.search(r"offloaded (\d+)/(\d+) layers to GPU", log)
    buffers = re.findall(r":\s+(\S+) (KV|RS) buffer size\s*=\s*([\d.]+) MiB", log)
    active_buffers = [(owner, kind) for owner, kind, mib in buffers if float(mib) > 0]
    if (not layers or layers[1] != layers[2] or int(layers[1]) == 0
            or set(active_buffers) != {(device, "KV"), (device, "RS")}):
        raise ValueError("CCORE stopped because it could not keep all model layers and generation cache on the GPU. "
                         "Free GPU memory or select a smaller generation budget.")
    if vision and (f"CLIP using {device} backend" not in log or "loaded multimodal model" not in log):
        raise ValueError("CCORE stopped because the vision projector did not load on the selected GPU. "
                         "Free GPU memory or select a smaller generation budget.")
