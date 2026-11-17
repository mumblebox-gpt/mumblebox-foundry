"""Describe measurable rig problems and the evidence behind each one."""
import math

from .geometry import numbers
from .sessions import current_output


MAX_ANGLE = math.pi / 2
MAX_SAMPLES = 16384


def selection_for(run, selection):
    if not isinstance(selection, dict):
        raise ValueError("Choose one deforming bone and optional comparison bones.")
    bones = {bone["id"]: bone for bone in run["skeleton"]["bones"]}
    target = selection.get("bone_id")
    neighbors = selection.get("neighbor_ids", [])
    if not isinstance(target, str) or target not in bones:
        raise ValueError("Choose a current bone for the movement check.")
    if not isinstance(neighbors, list) or len(neighbors) > 32 or any(
            not isinstance(item,str) or item not in bones or item == target for item in neighbors):
        raise ValueError("Choose up to 32 different comparison bones in the current rig.")
    return {"bone_id":target, "neighbor_ids":list(dict.fromkeys(neighbors))}


def joint_pose(run, pose):
    if pose is None:
        return None
    bone_id = selection_for(run,pose)["bone_id"]
    axis = pose.get("axis")
    angle = numbers([pose.get("angle")],1)[0]
    if axis not in ("x","y","z") or abs(angle) > MAX_ANGLE:
        raise ValueError("Use a local axis and an angle between −90 and 90 degrees.")
    return {"bone_id":bone_id, "axis":axis, "angle":angle}


def checked_metrics(data):
    if not isinstance(data, dict):
        raise ValueError("The wizard did not supply movement measurements.")
    integers = ("total","sampled","unweighted","invalid_weights","not_normalized","max_influences")
    if any(type(data.get(key)) is not int or data[key]<0 for key in integers):
        raise ValueError("The movement counts are invalid.")
    total, sampled = data["total"], data["sampled"]
    invalid = data["unweighted"] + data["invalid_weights"] + data["not_normalized"]
    if not 0 < sampled <= min(MAX_SAMPLES,total) or invalid>sampled or data["max_influences"]>8:
        raise ValueError("The movement sample is outside the expected bounds.")
    result = {key:data[key] for key in integers}
    for key in ("target","neighbors"):
        region = data.get(key)
        if not isinstance(region,dict) or any(type(region.get(item)) is not int for item in ("samples","moved")):
            raise ValueError("The comparison region is invalid.")
        maximum = numbers([region.get("max")],1)[0]
        if not 0 <= region["moved"] <= region["samples"] <= sampled-invalid or maximum<0:
            raise ValueError("The comparison measurement is invalid.")
        result[key] = {"samples":region["samples"],"moved":region["moved"],"max":maximum}
    if result["target"]["samples"] + result["neighbors"]["samples"] > sampled-invalid:
        raise ValueError("The measured regions exceed the usable vertex sample.")
    return result


def findings(run, selection, pose, evidence):
    target = selection["bone_id"]
    neighbors = selection["neighbor_ids"]
    output = current_output(run)
    identity = {"run_id":run["id"],"source_sha256":run["source"]["sha256"],"rig_revision":run["rig_revision"],
                "binding_key":output["binding"] if output else None,"pose":pose}
    result = []

    def add(code, severity, bones, measure=None, method=None):
        result.append({"code":code,"severity":severity,"bone_ids":bones,"measure":measure,
                       "method":method,"identity":identity,"inspection":"frame"})

    bones = {bone["id"]:bone for bone in run["skeleton"]["bones"]}
    bone = bones[target]
    if not bone.get("deform",True):
        add("non_deforming_bone","info",[target])
    diag = math.dist(*run["bounds"])
    epsilon = max(diag*1e-5,1e-8)
    overlap = [key for key,item in bones.items() if key!=target and
               math.dist(item["head"],bone["head"]) <= epsilon and math.dist(item["tail"],bone["tail"]) <= epsilon]
    if overlap:
        add("overlapping_bones","warning",[target,*overlap],{"distance_threshold":epsilon},"matching_endpoints")
    if not output:
        add("binding_required","unknown",[target])
        return result
    report = output["report"]
    if report.get("unweighted",0):
        add("unweighted","error",[target],{"count":report["unweighted"],"total":report.get("vertices")},"bound_vertices")
    if evidence is None:
        add("movement_not_measured","unknown",[target])
        return result
    evidence = checked_metrics(evidence)
    health = {key:value for key,value in evidence.items() if key not in ("target","neighbors")}
    bad_weights = health["unweighted"] + health["invalid_weights"] + health["not_normalized"]
    add("weight_sample","warning" if bad_weights else "info",[target],health,"sampled_mounted_skin_weights")
    threshold = max(diag*1e-4,1e-8)
    common = {"total":evidence["total"],"sampled":evidence["sampled"],"threshold":threshold}
    add("target_motion","info" if evidence["target"]["moved"] else "warning",[target],
        {**evidence["target"],**common},"sampled_skinning_by_dominant_bone")
    if neighbors:
        add("neighbor_motion","warning" if evidence["neighbors"]["moved"] else "info",neighbors,
            {**evidence["neighbors"],**common},"sampled_skinning_by_dominant_bone")
    return result
