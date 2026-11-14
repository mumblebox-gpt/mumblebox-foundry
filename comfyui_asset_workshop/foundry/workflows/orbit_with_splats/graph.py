"""Extend the Orbit to Mesh graph with an independently owned Brush stage."""
from ..image_to_3d.graph import ancestor_prompt
from ..orbit_to_mesh import graph as orbit
from ..virtual_turntable.graph import link, node, remap
from .definition import METHOD, OFFSET, TITLE, validate

FINISHING = orbit.FINISHING
TRAIN = "6102"

def orbit_controls(run):
    return {**run, "controls": {key: val for key, val in run["controls"].items() if key != "splat"}}

def add_pair(graph, camera, mesh, texture, grounding, controls):
    graph[TRAIN] = node("FoundryOrbitTrainSplatPair", cameras=link(camera), mesh=link(mesh),
                        textured_mesh=texture, grounding_json=link(grounding),
                        front_frame=controls["views"]["front_frame"], **controls["splat"])

def compile_stage(stage, run, output_root=None):
    run = {**run, "controls": validate(run["controls"])}
    if stage != "splat":
        return orbit.compile_stage(stage, orbit_controls(run), output_root, offset=OFFSET)
    saved = run["checkpoints"]
    graph = {
        "61": node("FoundryOrbitLoadCameras", manifest=saved["cameras"]),
        "6101": node("Hi3DFinishingSource", use_saved_checkpoint=True,
                     saved_clean_mesh=saved["clean"], saved_texture_mesh=saved["texture"]),
        "3011": node("Hi3DGroundingFrame", mesh=link(6101), mode=run["controls"]["bake"]["grounding"]),
    }
    add_pair(graph, 61, 6101, link(6101, 1), 3011, run["controls"])
    return remap(ancestor_prompt(graph, [TRAIN]), stage, OFFSET)

def template(run=None):
    controls = validate(run["controls"] if run else {})
    base = orbit.template(orbit_controls({**run, "controls": controls}) if run else None,
                          offset=OFFSET, method=METHOD, title=TITLE)
    extra = {}
    add_pair(extra, 60, 2015, link(2023), 3011, controls)
    # The Brush node consumes existing compiled canvas IDs.
    entry = extra[TRAIN]
    entry["_meta"] = {"title": "Train aligned Gaussian splat · Brush", "turntable_stage": "setup"}
    for key, value in entry["inputs"].items():
        if isinstance(value, list):
            entry["inputs"][key] = [str(OFFSET + int(value[0])), value[1]]
    return {**base, str(OFFSET + int(TRAIN)): entry}
