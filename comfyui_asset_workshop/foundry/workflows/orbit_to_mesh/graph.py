"""Compile the isolated Orbit to Mesh canvas and its checkpointed prompts."""
from copy import deepcopy
import json
from pathlib import Path

from ..image_to_3d.graph import ancestor_prompt, STAGE_OUTPUTS, template as finishing_template
from ..single_image.graph import compile_stage as finish_stage, remap as shift
from ..virtual_turntable.graph import link, node, raw_graph, remap
from .definition import METHOD, OFFSET, SELECTION, TITLE, defaults, settings, validate

PIXAL = json.loads(Path(__file__).with_name("pixal.json").read_text(encoding="utf-8"))
FINISHING = ("refinement", "texture", "balanced", "compact", "quads", "print", "package")
ENDS = {"turnaround": ["18"], "orbit": ["44"], "cameras": ["60"], "views": ["62", "63"], "geometry": ["382", "340"]}


def main_graph(run):
    graph = raw_graph(run, photogrammetry=False)
    controls, saved = run["controls"], run["checkpoints"]
    prefix = f"foundry/{run.get('method', METHOD)}/{run['id']}"
    graph["60"] = node("FoundryOrbitSolveCameras", frame_set=link(48), **controls["camera"])
    if saved.get("cameras"):
        graph["61"] = node("FoundryOrbitLoadCameras", manifest=saved["cameras"])
    graph["62"] = node("FoundryOrbitSelectViews", cameras=link(61 if "61" in graph else 60), **controls["views"])
    graph["63"] = node("SaveImage", images=link(62, 1), filename_prefix=prefix + "/views")
    graph.update(shift(PIXAL, 1000))
    shape = controls["pixal"]
    graph["64"] = node("FoundryOrbitPixalConditioning", clip_vision_model=link(1015),
                       manifest=saved.get("views_manifest") or link(62),
                       exclude_source_frames=",".join(map(str, run.get("exclude_views", []))))
    for key in ("1003", "1091"):
        graph[key]["inputs"].update(positive=link(64), negative=link(64, 1))
    for key, name, seed_offset in ((1003, "structure", 14), (1018, "shape", 0), (1023, "detail", 0)):
        graph[str(key)]["inputs"].update(seed=shape["seed"]+seed_offset, steps=shape[name+"_steps"],
            cfg=shape[name+"_cfg"], sampler_name=shape[name+"_sampler"],
            scheduler=shape[name+"_scheduler"], denoise=shape[name+"_denoise"])
    graph["1108"]["inputs"]["shift"] = shape["structure_shift"]
    graph["1094"]["inputs"]["target_resolution"] = shape["shape_resolution"]
    graph["48"]["inputs"]["asset_name"] = "orbit-" + run["id"][:16]
    graph["381"] = node("MeshToFile3D", mesh=link(1092))
    graph["382"] = deepcopy(finishing_template()["382"])
    graph["382"]["inputs"].update(model_3d=link(381), filename_prefix=prefix + "/rough")
    graph["340"] = node("SaveImage", images=link(2), filename_prefix=prefix + "/reference")
    return graph


def tune_finishing(graph, controls):
    if "2002" in graph:
        graph["2002"]["inputs"]["target_face_count"] = controls["refinement"]["intake_triangles"]
    if "2011" in graph:
        refine = controls["refinement"]
        graph["2011"]["inputs"].update(resolution=refine["cleanup_resolution"], band=refine["cleanup_band"],
            smooth_iters=refine["cleanup_smoothing"], project_back=refine["cleanup_project_back"])
    if "2023" in graph:
        texture = controls["texture"]
        inputs = graph["2023"]["inputs"]
        if texture["texture_triangles"]:
            graph["2047"] = node("DecimateMesh", mesh=inputs["mesh"], target_face_count=texture["texture_triangles"],
                                 placement_mode="midpoint")
            inputs["mesh"] = link(2047)
        inputs.update(sampler=texture["texture_sampler"], guidance_rescale=texture["guidance_rescale"],
            reference_lock=texture["reference_lock"], reference_substeps=texture["reference_substeps"])
    for ident in ("2031", "2041"):
        if ident in graph:
            graph[ident]["inputs"].update({key: controls["bake"][key] for key in ("cage_distance", "ignore_backfaces")})
    if "3011" in graph:
        graph["3011"]["inputs"]["mode"] = controls["bake"]["grounding"]


def compile_stage(stage, run, output_root=None, *, offset=OFFSET):
    run = {**run, "controls": validate(run["controls"])}
    if stage in FINISHING:
        graph = finish_stage(stage, run)
        tune_finishing(graph, run["controls"])
    else:
        graph = ancestor_prompt(main_graph(run), ENDS[stage])
    return remap(graph, stage, offset)


def template(run=None, *, offset=OFFSET, method=METHOD, title=TITLE):
    controls = defaults()
    run = run or {"id": "preview", "method": method, "controls": controls, "settings": settings(controls, {}),
                  "references": [], "checkpoints": {}, "selection": SELECTION}
    # The canvas shows the entire independent recipe. The wizard queues only
    # the ancestors needed by the stage, using its verified saved checkpoints.
    run = {**run, "controls": validate(run["controls"])}
    base = main_graph({**run, "checkpoints": {}})
    graph = finishing_template()
    graph.update(ancestor_prompt(base, ["18", "44", "60", "62", "63", "382", "340"]))
    selected = run["settings"]
    graph["2003"]["inputs"].update(resolution=selected["refine_resolution"], steps=selected["refine_steps"],
        seed=selected["refine_seed"], cpu_offload=selected["cpu_offload"], attention=selected["attention"])
    graph["2023"]["inputs"].update(seed=selected["texture_seed"], steps=selected["texture_steps"],
        texture_size=selected["texture_size"], guidance=selected["texture_guidance"], texture_mode=selected["texture_mode"])
    for ident, name in (("2030", "balanced_triangles"), ("2040", "compact_triangles")):
        graph[ident]["inputs"].update(target_triangles=selected[name], texture_size=selected["texture_size"])
    for ident in ("2031", "2041"):
        graph[ident]["inputs"]["resolution"] = selected["texture_size"]
    from ...quad_policy import node_options
    graph["3001"]["inputs"].update(target_quads=selected["quad_count"], texture_size=selected["texture_size"], **node_options(selected))
    graph["2050"]["inputs"]["height_mm"] = selected["print_height_mm"]
    graph["192"]["inputs"].update(image=link(2), bg_removal_model=link(46))
    graph["312"]["inputs"]["images"] = link(2)
    graph["2020"]["inputs"]["bg_removal_model"] = link(46)
    graph["2002"]["inputs"]["mesh"] = link(1092)
    graph["3010"]["inputs"].update(asset_name=run.get("name", title), selection_json=json.dumps(run["selection"]))
    graph["3011"] = node("Hi3DGroundingFrame", mesh=link(2015), mode="level")
    graph["3010"]["inputs"]["grounding_json"] = link(3011)
    tune_finishing(graph, run["controls"])
    ends = ["18", "44", "60", "62", "63", "340", "382"]
    ends += [key for stage in FINISHING for key in STAGE_OUTPUTS[stage]]
    return remap(ancestor_prompt(graph, ends), "setup", offset)
