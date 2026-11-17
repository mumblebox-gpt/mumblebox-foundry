"""Own the CPU bind process and attach its exact output to a saved skeleton."""
import json
import math
import subprocess
import time
from pathlib import Path

from ...artifacts import digest, owned_path
from .geometry import IDENTITY, document, product, transform
from .methods import bind_settings
from .sessions import RevisionConflict, current_output, fit_receipt, identifier, pose_key, skeleton_key
from .weights import weight_key

FILES = {"rig.glb", "report.json"}


def binding_path(service, run_id, binding):
    return service.library.output_root / "foundry-rigging" / identifier(run_id) / identifier(binding)


def checked_binding_file(service, run, output):
    path = binding_path(service, run["id"], output["binding"]) / "rig.glb"
    if (not path.is_file() or output.get("glb_sha256") and
            digest(owned_path(service.library.output_root, path)) != output["glb_sha256"]):
        raise ValueError("The saved rig GLB is missing or changed. Bind the current skeleton again.")
    return owned_path(service.library.output_root, path)


def prediction_path(service, run_id, prediction):
    return service.library.output_root / "foundry-rigging" / identifier(run_id) / "predictions" / identifier(prediction)


def binding_method(run):
    fit = fit_receipt(run)
    if fit.get("prediction_id") and fit.get("prediction_geometry") == skeleton_key(run):
        return "learned"
    return "voxel"


def verify_exported_skeleton(gltf, bones, rest_axes=None):
    nodes = gltf.get("nodes", [])
    joints = {index for skin in gltf.get("skins", []) for index in skin["joints"]}
    parents = {child: index for index, node in enumerate(nodes) for child in node.get("children", [])}
    actual = {nodes[index].get("name"): nodes[parents[index]].get("name") if parents.get(index) in joints else None
              for index in joints}
    expected = {bone["id"]: bone.get("parent_id") for bone in bones}
    if len(joints) != len(expected) or actual != expected:
        raise ValueError("The exported GLB changed the rig hierarchy or dropped bones.")
    by_name = {nodes[index]["name"]: index for index in joints}
    worlds = {}
    for index in joints:
        pending = []
        visited = set()
        current = index
        while current is not None and current not in worlds:
            if current in visited:
                raise ValueError("The exported GLB has a circular hierarchy.")
            pending.append(current)
            visited.add(current)
            current = parents.get(current)
        world = worlds[current] if current is not None else IDENTITY
        for current in reversed(pending):
            world = worlds[current] = product(world, transform(nodes[current]))
    for bone in bones:
        world = worlds[by_name[bone["id"]]]
        distance = math.dist(world[12:15], bone["head"])
        if distance > 1e-5 * max(1., math.hypot(*bone["head"])):
            raise ValueError(f"The exported GLB changed the rest position of {bone['id']}.")
        direction = [end-start for start,end in zip(bone["head"],bone["tail"])]
        length = math.hypot(*direction)
        if abs(math.hypot(*world[4:7])-1.) > 1e-4 or math.dist(world[4:7], [value/length for value in direction]) > 1e-4:
            raise ValueError(f"The exported GLB changed the rest direction of {bone['id']}.")
        if rest_axes and any(math.dist(world[column*4:column*4+3], axis) > 1e-4
                             for column, axis in enumerate(rest_axes[bone["id"]])):
            raise ValueError(f"The exported GLB changed the rest orientation of {bone['id']}.")


def learned_weights(service, run):
    fit = fit_receipt(run)
    path = prediction_path(service, run["id"], fit["prediction_id"]) / "weights.npz"
    if not path.is_file() or digest(owned_path(service.library.output_root, path)) != fit["weights_sha256"]:
        raise ValueError("The learned weights are missing or changed. Run Local AI again.")
    return path


def attach_output(service, initial, result, binding, *, context=None, cancelled=lambda: False):
    with service.lock:
        run = service.get(initial["id"])
        service.check_context(context, run)
        if cancelled():
            raise InterruptedError("Binding cancelled. Your joints are preserved.")
        key = skeleton_key(initial)
        if (key != skeleton_key(run) or fit_receipt(initial) != fit_receipt(run) or weight_key(initial) != weight_key(run) or
                pose_key(initial) != pose_key(run) or
                initial["orientation"] != run["orientation"] or initial["source"] != run["source"]):
            raise RevisionConflict("The joints changed while the mesh was binding. Bind the current skeleton again.")
        run["output"] = {**result, "binding": binding, "skeleton": key, "fit":fit_receipt(initial),
                         "source_sha256": run["source"]["sha256"], "weight_key":weight_key(run), "pose_key":pose_key(run)}
        run["pose"] = "rest"
        run["joint_pose"] = None
        run["step"] = "review"
        run["revision"] += 1
        return service.save(run)


def wait_for_binding(worker, cancelled=lambda:False, timeout=240):
    """Poll only this owned process so cancellation never touches Blender's UI."""
    deadline = time.monotonic() + timeout
    while True:
        if cancelled():
            worker.stop()
            raise InterruptedError("Binding cancelled. Your joints and any earlier completed rig are preserved.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            worker.stop()
            raise ValueError("The mesh took too long to bind. Try a lighter mesh variant.")
        try:
            return worker.process.wait(timeout=min(.25, remaining))
        except subprocess.TimeoutExpired:
            pass


def bind(service, run_id, revision, binding, preset="standard", custom=None, cancelled=lambda:False,
         requested_method=None, progress=lambda phase:None, *, context=None):
    from ....blender_handoff import find_blender
    from ....finishing.runtime import settings
    from ....pipeline_workers.worker_process import OwnedWorker

    identifier(binding)
    selected = bind_settings(preset, {} if custom is None else custom)
    with service.lock:
        run = service.get(run_id)
        service.check_context(context, run)
        method = requested_method if requested_method is not None else binding_method(run)
        if method not in ("learned", "conditioned", "voxel"):
            raise ValueError("Choose a supported binding method.")
        if method == "learned" and binding_method(run) != "learned":
            raise ValueError("Original learned weights require the original fitted skeleton. Choose another binding method.")
        previous = current_output(run)
        if previous and previous["binding"] == binding and previous.get("request_revision") == revision:
            if (previous.get("binding_settings", {"proxy_resolution":110}) != selected or
                    previous.get("binding_method", "voxel") != method):
                raise ValueError("Use a new request ID when changing bind settings.")
            checked_binding_file(service,run,previous)
            return run
        run = service.checked(run_id, revision)
        source = service.source_path(run)
    target = binding_path(service, run_id, binding)
    target.mkdir(parents=True, exist_ok=True)
    if (target/"report.json").exists():
        saved = json.loads((target/"request.json").read_text(encoding="utf-8"))
        if (saved["skeleton"] != skeleton_key(run) or saved.get("binding_settings", {"proxy_resolution":110}) != selected
                or saved.get("source_sha256") != run["source"]["sha256"] or saved.get("binding_method") != method
                or saved.get("weight_key") != weight_key(run)
                or saved.get("pose_key", pose_key(run)) != pose_key(run)
                or saved.get("fit", {"method":"guided_template"}) != fit_receipt(run)):
            raise ValueError("Use a new request ID for this skeleton.")
    else:
        exe = settings().get("blender") or str(find_blender())
        if not Path(exe).is_file():
            raise ValueError("Configure Foundry’s Blender executable to bind this mesh.")
        payload = {"source":str(source), "bones":run["skeleton"]["bones"],
                   "source_sha256":run["source"]["sha256"], "binding_method":method,
                   "height":run["bounds"][1][1]-run["bounds"][0][1],
                   "orientation":run["orientation"], "skeleton":skeleton_key(run),
                   "binding_settings":selected,"fit":fit_receipt(run),
                   "weight_edits":run.get("weight_edits",[]),"weight_key":weight_key(run),"pose_key":pose_key(run)}
        if method == "learned":
            payload["learned_weights"] = str(learned_weights(service, run))
        if method == "conditioned":
            from .methods import fit_settings
            from .tokenrig_runtime import fit

            def check():
                if cancelled():
                    raise InterruptedError("Binding cancelled. Your edited skeleton is preserved.")

            neural_stage = target / "conditioning"
            neural_settings = fit_receipt(run).get("settings") or fit_settings("standard", {})
            _, receipt = fit(source, run["source"]["sha256"], neural_settings, neural_stage,
                             check, progress, bones=run["skeleton"]["bones"])
            payload.update(learned_weights=str(neural_stage/"weights.npz"),
                           conditioning={**receipt["conditioning"], "model_revision": receipt["revision"]})
        progress("binding")
        (target/"request.json").write_text(json.dumps(payload), encoding="utf-8")
        with (target/"blender.log").open("w", encoding="utf-8") as output:
            worker = OwnedWorker([exe,"--background","--factory-startup","--disable-autoexec",
                                  "--threads","4","--python-exit-code","1","--python",
                                  str(Path(__file__).with_name("blender_worker.py")),"--",str(target)], output)
            try:
                if wait_for_binding(worker, cancelled):
                    output.flush()
                    tail = (target/"blender.log").read_text(encoding="utf-8", errors="replace")[-3000:]
                    detail = next((line[12:] for line in reversed(tail.splitlines()) if line.startswith("ValueError: ")), "")
                    raise ValueError("Blender could not bind this mesh. " + (detail or "Check the joint placement and try again."))
            finally:
                worker.close()
    if cancelled():
        raise InterruptedError("Binding cancelled. Your joints and any earlier completed rig are preserved.")
    service.source_path(run)
    report = json.loads((target/"report.json").read_text(encoding="utf-8"))
    if method == "conditioned":
        recorded = json.loads((target/"request.json").read_bytes()).get("conditioning", {})
        if not recorded.get("verified"):
            raise ValueError("Learned binding is missing its verified skeleton receipt.")
        report["conditioning"] = recorded
    if report["unweighted"] or report["bones"] != len(run["skeleton"]["bones"]):
        raise ValueError("The bound mesh did not pass the skinning check.")
    glb = target/"rig.glb"
    verify_exported_skeleton(document(glb), run["skeleton"]["bones"], report.pop("rest_axes", None))
    return attach_output(service,run,{"file":"rig.glb", "glb_sha256":digest(glb), "report":report,"request_revision":revision,
                                      "binding_settings":selected,"binding_preset":preset,
                                      "binding_method":method},binding,context=context,cancelled=cancelled)
