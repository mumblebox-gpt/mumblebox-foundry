"""Adapter from Foundry's component guide to the pinned CUDA-only invocation."""
import json
import os
from pathlib import Path
import subprocess
import time

from quad_contract import read_obj, subdivide_to_quads

class CyberTargetMiss(ValueError):
    """The CUDA solve returned valid faces but could not reach the component budget."""


def remesh_cuda(req, bounded_process, options):
    job = Path(req["job"])
    executable = Path(req["cyber_cuda_executable"])
    gpu = req["quad_gpu_uuid"]
    budget = req["component_target"]
    index = req["component"]
    target = job / "cyber-results" / f"part-{index}.obj"
    target.parent.mkdir(exist_ok=True)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": gpu, "FOUNDRY_CYBER_STRICT_CUDA": "1"}
    quad_method = options["layout"]
    common = [str(executable), "--backend", "cuda", "--quad-method", quad_method,
              "--patch-policy", "keep-all", "--input", str(job / "guide.obj"),
              "--output", str(target)]
    for key in ("adaptivity", "sharp_edge", "smooth_normal", "edge_scale", "hole_fill", "symmetry"):
        common.extend(("--" + key.replace("_", "-"), str(options[key])))
    started = time.monotonic()
    initial_budget = max(6, round(budget / 4))
    trial_budget = initial_budget
    attempts = []
    for attempt in range(4):
        report = job / f"cyber-{index}-{attempt}.json"
        log = job / f"cyber-{index}-{attempt}.log"
        args = common + ["--target-quads", str(trial_budget), "--report", str(report)]
        try:
            remaining = 240 - (time.monotonic() - started)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(args, 240)
            with log.open("w", encoding="utf-8") as stream:
                bounded_process(args, remaining, env=env, stdout=stream, stderr=subprocess.STDOUT)
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"CyberRemesher CUDA reached its time limit on part {index + 1}. "
                             "Try a smaller quad target or choose a CPU method.") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"CyberRemesher CUDA failed on part {index + 1}. "
                             "Check free GPU memory or choose a CPU method. "
                             + log.read_text(encoding="utf-8", errors="replace")[-1200:]) from exc
        receipt = json.loads(report.read_text(encoding="utf-8"))
        if (receipt.get("status") != "success" or receipt.get("gpuFallbacks") != 0
                or receipt.get("parameters", {}).get("quadMethod") != quad_method):
            raise ValueError(f"CyberRemesher did not complete part {index + 1} on its CUDA route.")
        vertices, faces = read_obj(target)
        # Keep the engine's quad-dominant layout. Its own pure-quad
        # relaxation can collapse edges on contact-heavy generated meshes.
        actual = sum(map(len, faces))
        attempts.append({"requested": trial_budget, "actual": actual})
        if abs(actual - budget) / budget <= .25:
            native_polygons = len(faces)
            native_quads = sum(len(face) == 4 for face in faces)
            vertices, faces = subdivide_to_quads(vertices, faces)
            return vertices, faces, {"method": "CyberRemesher CUDA", "target": budget, "actual": actual,
                                     "component": index, "gpu_fallbacks": 0, "quad_method": quad_method,
                                     "native_quads": native_quads, "native_polygons": native_polygons,
                                     "count_attempts": attempts, "seconds": time.monotonic() - started}
        # The upstream count-matching example adjusts the request by the observed ratio.
        corrected = min(initial_budget * 3, max(6, round(trial_budget * budget / actual)))
        if any(item["requested"] == corrected for item in attempts):
            break
        trial_budget = corrected
    best = min((trial["actual"] for trial in attempts), key=lambda actual: abs(actual - budget))
    raise CyberTargetMiss(f"CyberRemesher's closest result on part {index + 1} was {best:,} quads "
                     f"for a {budget:,}-quad target. Change the target or choose another method.")
