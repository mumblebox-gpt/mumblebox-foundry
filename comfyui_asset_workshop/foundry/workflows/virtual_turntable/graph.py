"""Compile one tested orbit and one selected reconstruction branch."""
from copy import deepcopy
import json
from pathlib import Path

from ..image_to_3d.graph import ancestor_prompt, compile_stage as finishing_stage
from .definition import ENGINES, TEMPLATE, defaults
from .runtime import runtime_settings
from ..image_to_3d.runs import signature

OFFSET = 780000
FINISHING = ("balanced", "compact", "quads", "print", "package")


def node(kind, **inputs):
    return {"class_type": kind, "inputs": inputs}


def link(key, slot=0):
    return [str(key), slot]


def remap(prompt, stage, offset=OFFSET):
    graph = deepcopy(prompt)
    for item in graph.values():
        for key, value in item["inputs"].items():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) in graph:
                item["inputs"][key] = [str(offset + int(value[0])), value[1]]
        item["_meta"] = {"title": item["class_type"], "turntable_stage": stage}
    return {str(offset + int(key)): value for key, value in graph.items()}


def raw_graph(run, *, photogrammetry=True):
    config = run["controls"]
    saved = run["checkpoints"]
    prefix = f"foundry/{run['method'] if 'method' in run else 'virtual-turntable'}/{run['id']}"
    graph = deepcopy(TEMPLATE)
    del graph["27"]["inputs"]["subject_prompt"]
    base = defaults()
    sheet, orbit, frames = ({**base[key], **config[key]} for key in ("turnaround", "orbit", "frames"))

    def update(key, **options):
        graph[str(key)]["inputs"].update(options)

    update(1, profile="Custom", sheet_panel_size=sheet["panel_size"],
           **{key: orbit[key] for key in ("width", "height", "length", "feedforward_chunks",
                                         "attention_chunks", "decode_tile", "decode_frames")})
    update(2, image=run["references"][0]["filename"] if run["references"] else "none")
    update(11, prompt=sheet["prompt"])
    update(8, shift_video=sheet["video_shift"])
    update(13, noise_seed=sheet["seed"])
    update(14, sampler_name=sheet["sampler"])
    update(15, sigmas=sheet["sigmas"])
    update(17, tile_size=sheet["decode_tile"])
    update(18, filename_prefix=prefix + "/sheet")
    update(19, crop_rectangles=sheet["crops"])
    update(21, **{key: orbit[key] for key in ("margin", "background", "release_previous_models")})
    update(23, **{key: orbit[key] for key in ("side_fraction", "three_quarter_fraction", "back_fraction")})
    update(27, orbit_prompt=orbit["prompt"], subject_direction=orbit["subject_direction"])
    update(33, strength_model=orbit["lora_strength"])
    update(34, seq_threshold=orbit["chunk_threshold"])
    update(37, noise_seed=orbit["seed"])
    if orbit["turbo"]:
        graph["57"] = node("LoraLoaderModelOnly", model=link(33),
                           lora_name="minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors",
                           strength_model=orbit["turbo_strength"])
        update(34, model=link(57))
    update(38, sampler_name=orbit["sampler"])
    update(39, steps=orbit["steps"], scheduler=orbit["scheduler"], denoise=orbit["denoise"])
    update(41, overlap=orbit["decode_overlap"], temporal_overlap=orbit["temporal_overlap"])
    update(43, fps=orbit["fps"])
    update(44, filename_prefix=prefix + "/orbit")
    update(45, **{key: frames[key] for key in ("max_frames", "max_edge", "drop_loop_endpoint", "exclude_indices")})
    update(47, **{key: frames[key] for key in ("batch_size", "release_previous_models")})
    update(48, asset_name="vt-" + run["id"][:16], **{key: frames[key] for key in
                                                      ("mask_threshold", "erode_pixels", "release_gpu")})
    update(48, source_timing=link(45, 2))
    if photogrammetry:
        graph["49"] = node("FoundryV360FrameReview", images=link(48, 1),
                           frame_set=link(48), filename_prefix=prefix + "/frame-review")
        update(52, **config["meshroom"])
        update(54, **config["colmap-openmvs"])
        engine = run.get("engine")
        selected = "54" if engine == "colmap-openmvs" else "52"
        graph["55"] = node("FoundryV360ReconstructionResult", project=link(selected, 2))
        update(53, model_3d=link(selected))
    if saved.get("sheet"):
        graph["56"] = node("LoadImage", image=saved["sheet"])
        update(19, sheet=link(56))
    if saved.get("orbit"):
        update(45, source="Saved video", saved_video=saved["orbit"])
        graph["45"]["inputs"].pop("generated_images", None)
    return graph


def saved_clean_root(run, output_root, run_name):
    if output_root is None:
        return None
    base = Path(output_root).resolve()
    folder = (base / "foundry" / "vt" / run_name).resolve()
    if not folder.is_relative_to(base):
        return None
    names = ["source.json", "reference.png", "clean.npz", "clean.glb", "clean.obj"]
    if run["controls"]["refinement"]["refine"]:
        names += ["inference.json", "alignment.json", "refined.npz", "refined.glb"]
    if any(not (folder / name).is_file() or not (folder / name).stat().st_size for name in names):
        return None
    try:
        context = json.loads((folder / "source.json").read_text(encoding="utf-8"))
        if Path(context["root"]).resolve() == folder and Path(context["project_folder"]).resolve() == Path(run["checkpoints"]["project"]).resolve():
            return folder
    except (ValueError, OSError, KeyError, TypeError):
        pass
    return None


def prepared_graph(run, output_root=None):
    config = run["controls"]
    refine = config["refinement"]
    prefix = f"foundry/virtual-turntable/{run['id']}"
    meshroom = run["engine"] == "meshroom"
    engine = config[run["engine"]]
    prep = "FoundryV360PrepareRefinement" if meshroom else "FoundryV360PrepareOpenMVSRefinement"
    run_name = "f-" + run["id"][:16] + "-" + signature([run["checkpoints"]["project"], refine])[:12]
    graph = {"60": node(prep, project_folder=run["checkpoints"]["project"],
                        reference_frame=refine["reference_frame"], run_name=run_name)}
    source = link(60)
    ends = ["2017", "2019", "2024"]
    graph["2019"] = node("SaveImage", images=link(60, 1), filename_prefix=prefix + "/matched-reference")
    if refine["refine"]:
        graph.update({
            "61": node("Hi3DBackend", url="http://127.0.0.1:8378"),
            "62": node("Hi3DRefine", backend=link(61), mesh=source, image=link(60, 1), mask=link(60, 2),
                       **{key: refine[key] for key in ("resolution", "steps", "seed", "cpu_offload", "attention")}),
            "63": node("Hi3DAlignToSource", mesh=link(62), source_mesh=source),
            "64": node("FoundryV360RestoreRefinement", mesh=link(63), context=link(60, 3),
                       alignment_report=link(63, 1), inference_report=link(62, 1)),
            "2005": node("Save3DAdvanced", model_3d=link(64, 1), filename_prefix=prefix + "/refined",
                         viewport_state=deepcopy(TEMPLATE["53"]["inputs"]["viewport_state"]), width=1024, height=1024),
        })
        source = link(64)
        ends.append("2005")
    else:
        # The prepare adapter uses the matching camera coordinate frame. Restore
        # that exact frame before the surface is rebuilt and colors are projected.
        graph["64"] = node("FoundryV360RestoreSourceFrame", mesh=source, context=link(60, 3))
        source = link(64)
    graph.update({
        "65": node("Hi3DRemoveZeroEdges", mesh=source),
        "66": node("Hi3DNormalizeMesh", mesh=link(65), span=.96),
        "67": node("RemeshMesh", mesh=link(66), resolution=refine["cleanup_resolution"], sign_mode="solid",
                   **{"sign_mode.fill": 20., "sign_mode.qef": False}, band=refine["band"], project_back=0.,
                   fix_poles=True, smooth_iters=refine["smoothing"], drop_small_components=0., precluster_max_verts=20000000),
        "68": node("Hi3DRestoreMeshFrame", mesh=link(67), original_frame=link(66, 1)),
        "69": node("FoundryV360RefinementCheckpoint", mesh=link(68), context=link(60, 3), name="clean"),
    })
    clean_mesh, clean_file, clean_obj, context = link(68), link(69), link(69, 1), link(69, 2)
    resume = saved_clean_root(run, output_root, run_name)
    if resume:
        graph["60"] = node("FoundryV360ResumeRefinement", source="Completed clean checkpoint",
                           run_folder=str(resume), checkpoint="clean")
        reference = (resume / "reference.png").relative_to(Path(output_root).resolve()).as_posix()
        graph["59"] = node("LoadImage", image=reference + " [output]")
        graph["2019"]["inputs"]["images"] = link(59)
        clean_mesh, clean_file, clean_obj, context = link(60), link(60, 2), link(60, 3), link(60, 1)
        if refine["refine"]:
            graph["64"] = node("FoundryV360ResumeRefinement", source="Completed clean checkpoint",
                               run_folder=str(resume), checkpoint="refined")
            graph["2005"]["inputs"]["model_3d"] = link(64, 2)
    finish_group = "meshroom_finish" if meshroom else "openmvs_finish"
    appearance = {**defaults()[finish_group], **config.get(finish_group, {})}
    if meshroom:
        graph["70"] = node("UnwrapMesh", mesh=clean_mesh, segmenter=appearance["segmenter"],
                           resolution=appearance["uv_resolution"], padding=appearance["uv_padding"],
                           weld_distance=appearance["uv_weld_distance"])
        graph["71"] = node("FoundryV360RefinementCheckpoint", mesh=link(70), context=context, name="clean-uv")
        graph["72"] = node("FoundryV360RetextureRefinement", mesh_obj=link(71, 1), context=link(71, 2),
                           texture_size=engine["texture_size"], cpu_threads=engine["cpu_threads"],
                           timeout_minutes=min(engine["timeout_minutes"], 240),
                           **{key: appearance[key] for key in ("unwrap_method", "fill_texture_holes", "weight_by_projected_area",
                                                              "memory_gib", "metallic", "roughness")})
    else:
        target = appearance["texture_triangle_target"]
        if target:
            graph["75"] = node("DecimateMesh", mesh=clean_mesh, target_face_count=target, placement_mode="midpoint")
            graph["76"] = node("FoundryV360RefinementCheckpoint", mesh=link(75), context=context,
                               name=f"projection-{target}")
            clean_obj = link(76, 1)
        graph["73"] = node("FoundryV360OpenMVSExportSettings", context=context,
                           **{key: appearance[key] for key in ("orientation", "ground", "material", "custom_metallic", "custom_roughness")})
        graph["72"] = node("FoundryV360TextureOpenMVSRefinement", mesh_obj=clean_obj, context=link(73),
                           texture_size=engine["texture_size"], cpu_threads=engine["cpu_threads"], gpu_index=engine["gpu_index"],
                           timeout_minutes=min(engine["timeout_minutes"], 240),
                           **{key: appearance[key] for key in ("outlier_threshold", "seam_leveling", "advanced_texture")})
    clean = clean_file
    if not meshroom:
        graph["74"] = node("FoundryV360PresentOpenMVSGeometry", model=clean, context=link(73))
        clean = link(74)
    for key, source, filename in (("2017", clean, "clean"), ("2024", link(72), "textured")):
        graph[key] = node("Save3DAdvanced", model_3d=source, filename_prefix=prefix + "/" + filename,
                          viewport_state=deepcopy(TEMPLATE["53"]["inputs"]["viewport_state"]), width=1024, height=1024)
    return ancestor_prompt(graph, ends)


def compile_stage(stage, run, output_root=None):
    if stage in FINISHING:
        return remap(finishing_stage(stage, run), stage)
    if stage == "texture":
        return remap(prepared_graph(run, output_root), stage)
    graph = raw_graph(run)
    ends = {"turnaround": ["18"], "orbit": ["44"], "frames": ["49"], "geometry": ["53", "55"]}
    if stage == "geometry" and run["checkpoints"].get("frame_set"):
        graph["58"] = node("FoundryV360ResumeFrames", saved_folder=run["checkpoints"]["frame_set"])
        for key in ("52", "54"):
            graph[key]["inputs"]["frame_set"] = link(58)
    elif stage == "geometry":
        ends["geometry"].append("49")
    return remap(ancestor_prompt(graph, ends[stage]), stage)


def template(run=None):
    if run is None:
        run = {"id": "preview", "controls": defaults(), "references": [], "checkpoints": {}}
    graph = raw_graph(run)
    for key in ("22",):
        graph.pop(key, None)
    return remap(graph, "setup")


def dependency_status(engine):
    from .runtime import missing
    return {"missing": missing(engine), "runtime": runtime_settings()}
