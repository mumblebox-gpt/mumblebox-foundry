"""Publish a separate cataloged rig with its provenance and editable joint data."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from ... import VERSION
from ....finishing.package_archive import publish_archive
from ....finishing.package_catalog import FileRecord, VariantRecord, build_catalog
from .runtime import binding_path, checked_binding_file
from .sessions import current_output, fit_receipt, skeleton_key


def publish(service, run, *, context=None):
    def check():
        service.control.check(context)

    @contextmanager
    def commit_scope():
        with service.lock:
            service.check_context(context, service.get(run["id"]))
            yield

    check()
    output = current_output(run)
    if not output:
        raise ValueError("Bind the current joints before exporting.")
    stage = binding_path(service, run["id"], output["binding"])
    # Labels and other authoring metadata can change without a new skin bind.
    export_id = hashlib.sha256(f"{run['id']}:{output['binding']}:{run['rig_revision']}".encode()).hexdigest()[:32]
    target = stage / ("rig-package-" + export_id)
    archive = target.with_suffix(".zip")
    if archive.is_file():
        return service.library.import_package(archive, commit_scope=commit_scope)
    glb = checked_binding_file(service,run,output)
    service.source_path(run)
    (target/"Rigged").mkdir(parents=True, exist_ok=True)
    (target/"Metadata").mkdir(exist_ok=True)
    shutil.copyfile(glb, target/"Rigged/character.glb")
    source = {key:value for key,value in run["source"].items() if key != "fingerprint"}
    fit = fit_receipt(run)
    binding = output.get("binding_settings",{"proxy_resolution":110})
    method = output.get("binding_method", "voxel")
    binder = {
        "learned":"TokenRig learned weights with Blender transfer and GLB export",
        "conditioned":"TokenRig learned weights conditioned on the edited skeleton, transferred in Blender",
        "voxel":"Blender voxel heat with nearest segment fallback",
    }[method]
    poses = output["report"].get("pose_seconds", {})
    report = output["report"]
    data = {**{key:value for key,value in report.items() if key != "bones"},
            "schema":"mumblebox.rigging/3", "source":source, "axis":"glTF Y-up", "bone_count":report["bones"],
            "rig_revision":run["rig_revision"], "bones":run["skeleton"]["bones"],
            "weight_edits":run.get("weight_edits", []), "weight_locks":run.get("weight_locks", []),
            "surface_landmarks":run.get("surface_landmarks", []),
            "orientation":run["orientation"], "skeleton":skeleton_key(run), "fit":fit,
            "binding_method":method, "binding_settings":binding if method == "voxel" else {}}
    (target/"Metadata/rig.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    catalog = service.library.record(source["record_id"])["catalog"]
    provenance = {key:catalog[key] for key in ("schema","export_id","asset_name","workflow_version","resources") if key in catalog}
    (target/"Metadata/source-catalog.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    files = [
        FileRecord("Rigged/character.glb","asset","rigged","Skinned GLB with the complete edited armature, materials and the recorded preview poses.","glb","mesh"),
        FileRecord("Metadata/rig.json","metadata",None,"Stable bone IDs, hierarchy, rest endpoints, roll, source-surface landmarks, source hash, binding method, pose times and skinning validation.","json","provenance"),
        FileRecord("Metadata/source-catalog.json","metadata",None,"Original asset provenance and licensing information.","json","provenance"),
        FileRecord("Metadata/manifest.json","metadata",None,"Package inventory and checksums.","json","catalog"),
    ]
    pack = Path(__file__).resolve().parents[3]
    registry = json.loads((pack/"finishing/package_resources.json").read_text(encoding="utf-8"))
    resources = [{**registry["blender"],"stage":binder,"version":output["report"]["blender"]}]
    if fit["method"] == "local_ai" or method == "conditioned":
        model_revision = output["report"].get("conditioning", {}).get("model_revision") or fit.get("revision")
        resources.append({**registry["rig_tokenrig"],"version":model_revision})
    (target/"Licenses").mkdir(exist_ok=True)
    for resource in resources:
        for notice in resource["notices"]:
            relative = "Licenses/" + notice
            shutil.copyfile(pack/"licenses/pipeline"/notice,target/relative)
            files.append(FileRecord(relative,"license",None,resource["name"]+" license.","txt","notice"))
    measures = {key:output["report"][key] for key in ("bones","triangles","vertices","unweighted","nearest_segment_vertices")}
    description = f"Character armature with {measures['bones']} bones and {len(poses)} preview poses, including rest."
    variant = VariantRecord("rigged","Rigged/",description,
        intended_use="Open in Blender to inspect or refine weights, pose the character and author animation.",
        measurements={"geometry":measures}, file_paths=["Rigged/character.glb"],
        validations=[{"name":"Deforming joint weights","status":"pass",
                      "note":"Every vertex had a positive skin weight before export."}],
        limitations=["The GLB includes the recorded deform skeleton. Blender-specific controls, facial animation and retargeting require separate setup.",
                     "Pose and inspect the whole character. Generated surface defects and misaligned joints can require weight cleanup.",
                     "Inspect the original asset catalog for model and source terms. Rigging does not change them."])
    identity = {"name":"Mumblebox 3D Asset Foundry", "description":"Local asset workflows.",
                "github_url":"https://github.com/mumblebox-gpt/mumblebox-foundry"}
    metadata = {"asset_name":source["asset_name"]+" — Rigged", "export_id":export_id,
                "created_utc":datetime.now(timezone.utc).isoformat(), "workflow_version":VERSION,
                "production":{"method":"rigging/v3","workflow_title":"Rig a Character","source":source,
                              "settings":{"binder":binder,"blender":output["report"]["blender"],
                                          "fit_method":fit["method"], **(binding if method == "voxel" else {})}}}
    build = build_catalog(files,[variant],resources,identity,metadata)
    publish_archive(build,target,archive,check)
    return service.library.import_package(archive, commit_scope=commit_scope)
