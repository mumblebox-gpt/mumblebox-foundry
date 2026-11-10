"""Compile selected stage ancestors without mutating the reviewable source graph."""
from copy import deepcopy
from ...quad_policy import node_options

def ancestor_prompt(prompt, endpoints):
    result, visiting = {}, set()
    def visit(node_id):
        node_id = str(node_id)
        if node_id in result:
            return
        if node_id in visiting:
            raise ValueError("Cycle in workflow at node " + node_id)
        if node_id not in prompt:
            raise ValueError("Missing workflow node " + node_id)
        visiting.add(node_id)
        node = prompt[node_id]
        for value in node.get("inputs", {}).values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[1], int):
                visit(value[0])
        visiting.remove(node_id)
        result[node_id] = deepcopy(node)
    for endpoint in endpoints:
        visit(endpoint)
    return result

import json
from pathlib import Path
from .definition import VERSION
from .prompts import bind_references
from .turnaround import compile_turnaround

STAGE_OUTPUTS = {"turnaround":["901","412","340","344","343","346","2051"],
                 "geometry":["382"], "refinement":["2005","2017"],
                 "texture":["2024","2025","2026"], "balanced":["2034","2035"],
                 "compact":["2044","2045"], "print":["2050"], "quads":["3001"], "package":["3010"]}
STAGE_KEYS = {
 "turnaround":["turnaround_seed"], "geometry":["shape_resolution"],
 "refinement":["refine_resolution","refine_steps","refine_seed","cpu_offload","attention"],
 "texture":["texture_seed","texture_steps","texture_size","texture_guidance"],
 "balanced":["balanced_triangles","texture_size"], "compact":["compact_triangles","texture_size"],
 "quads":["quad_count","texture_size","quad_method"], "print":["print_height_mm"], "package":[]}
DEPENDENCIES = {"turnaround":[], "geometry":["turnaround"], "refinement":["geometry"],
                "texture":["refinement"], "balanced":["texture"], "compact":["texture"],
                "quads":["texture"], "print":["refinement"]}

def template():
    return json.loads(Path(__file__).with_name("template.json").read_text(encoding="utf-8"))

def compile_stage(stage, run):
    if run.get('method')=='single-image':
        from ..single_image.graph import compile_stage as single_stage,remap
        from ..single_image.definition import OFFSET
        return remap(single_stage(stage,run),OFFSET)
    if stage not in STAGE_OUTPUTS:
        raise ValueError("Unknown workflow stage.")
    graph = template()
    settings, saved = run["settings"], run.get("checkpoints", {})
    prefix = "foundry/" + run["slug"] + "/" + run["id"] + "/" + stage
    def inputs(node, **values):
        graph[str(node)]["inputs"].update(values)
    for node_id, node in graph.items():
        data = node["inputs"]
        if "filename_prefix" in data:
            data["filename_prefix"] = prefix + "/" + node_id
        if "run_name" in data:
            data["run_name"] = run["slug"] + "-" + run["id"][:8] + "-" + node_id
    inputs(1558, seed=settings["turnaround_seed"])
    inputs(94, target_resolution=settings["shape_resolution"])
    inputs(2003, resolution=settings["refine_resolution"], steps=settings["refine_steps"],
           seed=settings["refine_seed"], cpu_offload=settings["cpu_offload"], attention=settings["attention"])
    inputs(2023, seed=settings["texture_seed"], steps=settings["texture_steps"],
           texture_size=settings["texture_size"], guidance=settings["texture_guidance"],
           texture_mode=settings.get("texture_mode", "standard"))
    for node, budget in [(2030,"balanced_triangles"),(2040,"compact_triangles")]:
        inputs(node,target_triangles=settings[budget],texture_size=settings["texture_size"])
    for node in (2031,2041):
        inputs(node,resolution=settings["texture_size"])
    inputs(3001,target_quads=settings["quad_count"],texture_size=settings["texture_size"],**node_options(settings))
    inputs(2050,height_mm=settings["print_height_mm"])
    if stage == "turnaround":
        graph.update(compile_turnaround(run))
    elif stage == "geometry":
        for index, view in enumerate(("front","left","back","right"),9101):
            node = str(index)
            graph[node] = {"class_type":"LoadImage","inputs":{"image":saved[view]}}
            inputs(324, **{view:[node,0]})
    elif stage != "package":
        clean = saved["decoded" if stage=="refinement" else "clean"]
        textured = saved.get("texture",clean)
        graph["9100"]={"class_type":"Hi3DFinishingSource","inputs":{
            "use_saved_checkpoint":True,"saved_clean_mesh":clean,"saved_texture_mesh":textured}}
        # File checkpoints are deliberately outside the inference ancestry.
        for node in graph.values():
            for key,value in list(node["inputs"].items()):
                if (stage=="refinement" and value==["92",0]) or (stage!="refinement" and value==["2015",0]):
                    node["inputs"][key]=["9100",0]
                elif stage not in ("refinement","texture") and value==["2023",0]:
                    node["inputs"][key]=["9100",1]
        graph["9101"]={"class_type":"LoadImage","inputs":{"image":saved["front"]}}
        inputs(2020,image=["9101",0])
        inputs(2022,image=["9101",0])
        inputs(3000,use_saved_checkpoint=True,saved_clean_mesh=clean,saved_texture_mesh=textured)
        graph["3000"]["inputs"].pop("mesh",None)
        graph["3000"]["inputs"].pop("textured_source",None)
    if stage == "package":
        node = graph["3010"]["inputs"]
        for key in ("detailed","balanced","compact","print_stl","quad_light","quad_detail"):
            node.pop(key,None)
        node.update(use_saved_variants=True, saved_balanced=saved.get("balanced",""),
            saved_compact=saved.get("compact",""),saved_print=saved.get("print",""),
            asset_name=run["name"], selection_json=json.dumps(run["selection"]),
            metadata_json=json.dumps(run.get("metadata",{"workflow_version":VERSION})))
        if "detailed" in run["selection"]["variants"]:
            graph["9100"]={"class_type":"Hi3DFinishingSource","inputs":{"use_saved_checkpoint":True,
                "saved_clean_mesh":saved["clean"],"saved_texture_mesh":saved["texture"]}}
            node["detailed"]=["9100",1]
        if "quad_light" in run["selection"]["variants"]:
            node["quad_light"]=saved["quad_manifest"]
    return ancestor_prompt(graph,STAGE_OUTPUTS[stage])
