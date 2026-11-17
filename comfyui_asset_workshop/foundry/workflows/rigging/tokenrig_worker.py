"""Run the pinned TokenRig solver and preserve its hierarchy and sampled skin."""
import hashlib
import json
from collections import defaultdict
import os
from pathlib import Path
import random
import sys
from time import perf_counter, process_time
from uuid import uuid4
from zipfile import BadZipFile


def source_geometry(np, trimesh, run, cache):
    # Cache only deterministic decoding and the axis conversion. The checkpoint's
    # surface sampling stays seed-dependent and runs for every inference.
    size_limit = 96 * 1024**2
    cache.mkdir(parents=True, exist_ok=True)
    key = run["source_sha256"]
    if len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
        raise ValueError("The source mesh is missing a valid content hash.")
    entry = cache / f"z-up-1-{key}.npz"
    if entry.is_file() and entry.stat().st_size <= size_limit:
        try:
            with np.load(entry, allow_pickle=False) as saved:
                geometry = tuple(saved[name] for name in ("vertices", "faces", "bounds"))
            if (geometry[0].ndim != 2 or geometry[0].shape[1] != 3 or geometry[0].dtype != np.float32 or
                    geometry[1].ndim != 2 or geometry[1].shape[1] != 3 or geometry[1].dtype != np.int32 or
                    geometry[2].shape != (2,3) or not np.isfinite(geometry[2]).all()):
                raise ValueError("Invalid geometry cache entry.")
            os.utime(entry, None)
            return (*geometry, True)
        except (OSError, ValueError, KeyError, BadZipFile):
            entry.unlink(missing_ok=True)
    mesh = trimesh.load_scene(run["source"], skip_materials=True).to_geometry()
    mesh.vertices = mesh.vertices[:, (0, 2, 1)] * [1, -1, 1]
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.int32)
    bounds = mesh.bounds.copy()
    if vertices.nbytes + faces.nbytes < size_limit // 2:
        temporary = cache / (uuid4().hex + ".partial")
        try:
            with temporary.open("wb") as stream:
                np.savez(stream, vertices=vertices, faces=faces, bounds=bounds)
            temporary.replace(entry)
        finally:
            temporary.unlink(missing_ok=True)
        total = 0
        for path in sorted(cache.glob("z-up-1-*.npz"), key=lambda item: item.stat().st_mtime, reverse=True):
            total += path.stat().st_size
            if total > size_limit:
                path.unlink()
    return vertices, faces, bounds, False


def conditioning_order(bones):
    children = defaultdict(list)
    for bone in bones:
        children[bone.get("parent_id")].append(bone)
    if len(children[None]) != 1:
        raise ValueError("Learned binding needs one root bone. Blender binding supports multiple roots.")
    ordered, parents, seen = [], [], set()
    pending = [(children[None][0], -1)]
    while pending:
        bone, parent = pending.pop()
        if bone["id"] in seen:
            raise ValueError("The edited skeleton contains duplicate bones or a cycle.")
        seen.add(bone["id"])
        index = len(ordered)
        ordered.append(bone)
        parents.append(parent)
        pending.extend((child, index) for child in reversed(children[bone["id"]]))
    if len(ordered) != len(bones):
        raise ValueError("Learned binding needs a connected hierarchy with one root.")
    return ordered, parents


def main(upstream, request_path):
    os.chdir(upstream)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    sys.path.insert(0, str(upstream))
    import numpy as np
    import torch
    import trimesh
    from src.model.tokenrig import TokenRig
    from src.rig_package.info.asset import Asset
    from src.tokenizer.spec import TokenizeInput

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(including_emulation=False):
        raise ValueError("Local AI fitting requires an NVIDIA GPU with CUDA and native bfloat16 support.")
    if request_path is None:
        return
    run = json.loads(request_path.read_text(encoding="utf-8"))
    settings = run["settings"].copy()
    seed = settings.pop("seed")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    started = perf_counter()
    cpu_started = process_time()
    vertices,faces,bounds,cache_hit = source_geometry(np,trimesh,run,upstream.parent/"geometry-cache")
    asset = Asset(vertices=vertices, faces=faces)
    asset.cls = "articulation"
    center = (bounds[0] + bounds[1]) / 2
    span = max(bounds[1] - bounds[0])
    model = TokenRig.load_from_system_checkpoint(run["checkpoint"]).eval().cuda()
    asset.build_normals()
    model.get_predict_transform().apply(asset)
    # This checkpoint applies centered uniform normalization. Reversing the
    # measured fit keeps points in the exact owned GLB's coordinate system.
    low, high = asset.vertices.min(axis=0), asset.vertices.max(axis=0)
    scale = span / max(high-low)
    offset = center - (low+high)/2 * scale
    tokens = None
    conditioning = None
    if "bones" in run:
        ordered, expected_parents = conditioning_order(run["bones"])
        source_points = np.array([bone["head"] for bone in ordered])
        normalized = (source_points[:, (0, 2, 1)] * [1, -1, 1] - offset) / scale
        quantizer = model.tokenizer
        lower, upper = quantizer.continuous_range
        if np.any(normalized < lower) or np.any(normalized > upper):
            raise ValueError("An edited joint is outside the model's coordinate range. Choose Blender binding.")
        tokens = quantizer.tokenize(TokenizeInput(normalized, expected_parents, cls=asset.cls))
        decoded = quantizer.detokenize(tokens)
        tolerance = float((upper-lower) / (quantizer.num_discrete-1) * np.sqrt(3.0))
        error = float(np.linalg.norm(decoded.joints-normalized, axis=1).max()) if decoded.J == len(ordered) else float("inf")
        if list(decoded.parents) != expected_parents or error > tolerance:
            raise ValueError("Quantizing the edited skeleton changes its hierarchy or joint positions. Choose Blender binding.")
        conditioning = {"bone_ids": [bone["id"] for bone in ordered], "token_count": len(tokens),
                        "source_point_error": error*scale, "source_point_tolerance": tolerance*scale}
    with torch.inference_mode():
        prediction = model.generate(
            vertices=torch.as_tensor(asset.sampled_vertices, device="cuda", dtype=torch.float32),
            normals=torch.as_tensor(asset.sampled_normals, device="cuda", dtype=torch.float32),
            cls=asset.cls, skeleton_tokens=tokens, max_length=2048, num_return_sequences=1, do_sample=True, **settings,
        )
    skeleton = prediction.detokenize_output
    if skeleton is None or prediction.skin_pred is None:
        raise ValueError("TokenRig did not finish the skeleton and learned weights. Try another seed.")
    if conditioning is not None:
        prefix = prediction.output_ids[:len(tokens)].cpu().numpy()
        if not np.array_equal(prefix, tokens) or list(skeleton.parents) != expected_parents:
            raise ValueError("The model did not preserve the supplied skeleton. Choose Blender binding.")
        conditioned_error = float(np.linalg.norm(skeleton.joints-normalized, axis=1).max()) * scale
        if conditioned_error > conditioning["source_point_tolerance"]:
            raise ValueError("The model moved the supplied joints. Choose Blender binding.")
        conditioning.update(verified=True, source_point_error=conditioned_error)

    def to_source(points):
        world = points * scale + offset
        return np.asarray(world[:, (0, 2, 1)] * [1, 1, -1], dtype=np.float32)

    points = to_source(skeleton.joints)
    samples = to_source(asset.sampled_vertices)
    weights = prediction.skin_pred.detach().float().cpu().numpy()
    if (not 1 <= len(points) <= 512 or not 1 <= len(samples) <= 65536 or
            weights.shape != (len(samples), len(points)) or not np.isfinite(weights).all() or
            not np.isfinite(samples).all() or np.any(weights < 0)):
        raise ValueError("TokenRig returned invalid learned weights.")
    artifact = request_path.with_name("weights.npz")
    bone_ids = conditioning["bone_ids"] if conditioning else [f"bone_{i}" for i in range(len(points))]
    np.savez(artifact, points=samples, weights=weights, bone_ids=np.asarray(bone_ids))
    with artifact.open("rb") as stream:
        weights_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    result = {"joints": points.tolist(), "parents": list(map(int,skeleton.parents)),
              "samples":len(samples), "source_sha256":run["source_sha256"], "weights_sha256":weights_hash,
              "model_to_source":{"scale":float(scale), "offset_z_up":offset.tolist(), "target_axis":"Y-up"},
              "geometry_cache_hit":cache_hit, "cpu_seconds":round(process_time()-cpu_started,2),
              "seconds": round(perf_counter()-started, 2), "cuda_allocated_bytes": torch.cuda.max_memory_allocated()}
    if conditioning is not None:
        result["conditioning"] = conditioning
    request_path.with_name("prediction.json").write_text(json.dumps(result,allow_nan=False),encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve() if len(sys.argv)>2 else None)
