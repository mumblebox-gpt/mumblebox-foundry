"""Capabilities and resource checks for the optional Foundry quad solvers."""
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

MIB = 1024 ** 2
CUDA_RESERVE_MIB = 512
CPU_RESERVE_MIB = 512
CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RUNTIME_DIR = Path(__file__).parent / "vendor" / "cyber-cuda"


def verify_bundle(runtime_dir=RUNTIME_DIR):
    manifest = json.loads((runtime_dir / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    if set(files) != {"cyberremesh.exe", "cudart64_12.dll"}:
        raise ValueError("Unexpected files in the CyberRemesher CUDA runtime manifest.")
    for name, expected in files.items():
        if sha256((runtime_dir / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"The CyberRemesher CUDA runtime checksum failed for {name}.")
    path = runtime_dir / "cyberremesh.exe"
    result = subprocess.run([str(path), "--version"], capture_output=True, check=True, text=True,
                            timeout=8, creationflags=CREATE_FLAGS)
    if not result.stdout.startswith("cyberremesh " + manifest["version"]):
        raise ValueError("Unexpected CyberRemesher CUDA runtime version.")
    return manifest["version"]


def executable():
    path = RUNTIME_DIR / "cyberremesh.exe"
    if os.name != "nt" or not path.is_file() or not path.with_name("cudart64_12.dll").is_file():
        raise ValueError("CyberRemesher CUDA needs the Foundry Windows CUDA runtime. Repair Foundry software to restore it.")
    return path


def driver_memory(gpu):
    args = ["nvidia-smi", "-i", gpu, "--query-gpu=memory.free,memory.total", "--format=csv,noheader,nounits"]
    try:
        result = subprocess.run(args, capture_output=True, check=True, text=True, timeout=4, creationflags=CREATE_FLAGS)
        free, total = map(int, result.stdout.strip().split(","))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError("Foundry could not read available NVIDIA GPU memory. Check the NVIDIA driver and try again.") from exc
    return free, total


def cuda_device():
    import comfy.model_management as mm
    import torch

    device = mm.get_torch_device()
    if device.type != "cuda" or not torch.version.cuda or not torch.cuda.is_available():
        raise ValueError("CyberRemesher needs ComfyUI running on a compatible NVIDIA CUDA GPU.")
    props = torch.cuda.get_device_properties(device)
    uuid = getattr(props, "uuid", None)
    if (props.major, props.minor) < (7, 5) or not uuid:
        raise ValueError("CyberRemesher needs an identifiable NVIDIA GPU with compute capability 7.5 or later.")
    return "GPU-" + str(uuid).removeprefix("GPU-")


@lru_cache(maxsize=4)
def installed_bindings(python, modified):
    code = ("import importlib.util,json;"
            "print(json.dumps({n: importlib.util.find_spec(n) is not None "
            "for n in ('pyquadriflow','pynanoinstantmeshes')}))")
    result = subprocess.run([python, "-c", code], capture_output=True, check=True, text=True,
                            timeout=5, creationflags=CREATE_FLAGS)
    return json.loads(result.stdout)


def public_methods():
    from .runtime import worker_python
    from ..foundry.quad_policy import DEFAULT_METHOD, METHODS

    try:
        python = Path(worker_python())
        bindings = installed_bindings(str(python), python.stat().st_mtime_ns)
    except (OSError, subprocess.SubprocessError, ValueError):
        bindings = {}
    cuda_error = ""
    try:
        executable()
        cuda_device()
    except (RuntimeError, ValueError) as exc:
        cuda_error = str(exc)
    errors = {
        "quadriflow": "" if bindings.get("pyquadriflow") else "The QuadriFlow worker is missing. Repair Foundry software.",
        "instant_meshes": "" if bindings.get("pynanoinstantmeshes") else "The Instant Meshes worker is missing. Repair Foundry software.",
        "cyber_cuda": cuda_error,
    }
    return [{"id": key, "label": label, "device": device, "description": description,
             "available": not errors[key], "reason": errors[key], "recommended": key == DEFAULT_METHOD}
            for key, (label, device, description) in METHODS.items()]


def require_cpu_memory(guide_faces):
    import psutil

    free = psutil.virtual_memory().available
    # Shared headroom for mesh arrays, an independent solver, and repair.
    # This is an admission guard, not a solver-specific memory estimate.
    reserve = CPU_RESERVE_MIB * MIB + 4096 * guide_faces
    if free < reserve:
        raise ValueError(f"Quad finishing has {free / MIB:.0f} MiB free system memory. "
                         "Close other work or lower the guide limit, then retry.")


def preflight(method, guide_triangles):
    require_cpu_memory(guide_triangles)
    if method != "cyber_cuda":
        return {}
    path = executable()
    gpu = cuda_device()
    free, total = driver_memory(gpu)
    if free < CUDA_RESERVE_MIB:
        raise ValueError(f"CyberRemesher has {free} MiB of free GPU memory. "
                         f"Free at least {CUDA_RESERVE_MIB} MiB or choose a CPU method.")
    return {"cyber_cuda_executable": str(path), "quad_gpu_uuid": gpu, "quad_gpu_free_mib": free,
            "quad_gpu_total_mib": total}




