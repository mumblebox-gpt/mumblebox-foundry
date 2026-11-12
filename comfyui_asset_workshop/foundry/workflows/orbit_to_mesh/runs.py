"""Orbit to Mesh checkpoints, stage lineage and portable production receipts."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

from ...artifacts import digest, owned_path
from ...quad_policy import fingerprint_fields, manifest_resources
from ..image_to_3d.definition import texture_sampling_settings
from ..image_to_3d.graph import STAGE_KEYS
from ..image_to_3d.readiness import ensure
from ..image_to_3d.runs import signature, view_url
from ..virtual_turntable.runs import VirtualTurntableRuns
from .definition import METHOD, OFFSET, SCHEMA, SELECTION, TITLE, missing_tools, settings, validate
from .graph import compile_stage

STEPS = {
    "turnaround": "Generating the four-view turnaround sheet",
    "orbit": "Generating the 360° orbit",
    "cameras": "Aligning cameras from the masked orbit",
    "views": "Choosing sharp views for Pixal3D",
    "geometry": "Building a mesh with Pixal3D",
    "refinement": "Refining and cleaning the mesh with Hi3D",
    "texture": "Texturing the clean mesh with TRELLIS.2",
}
OPERATIONS = {
    "turnaround": ("turnaround",), "orbit": ("orbit",),
    "cameras": ("cameras", "views"), "views": ("views",),
    "reconstruct": ("geometry",), "finish": ("refinement", "texture"), "rocket": tuple(STEPS),
}
OUTPUTS = {
    "turnaround": ("sheet",), "orbit": ("orbit",), "cameras": ("cameras",),
    "views": ("views_manifest", "frames"), "geometry": ("raw", "decoded", "front"),
    "refinement": ("clean", "refined"), "texture": ("texture",),
}
PREVIOUS = {
    "orbit": "turnaround", "cameras": "orbit", "views": "cameras",
    "geometry": "views", "refinement": "geometry", "texture": "refinement",
    "balanced": "texture", "compact": "texture", "quads": "texture", "print": "refinement",
}


def omit_defaults(controls, group, optional):
    return {key: value for key, value in controls.items()
            if key not in optional or value != SCHEMA[group][key]["default"]}


class OrbitRuns(VirtualTurntableRuns):
    method, title, offset = METHOD, TITLE, OFFSET
    steps, operations, outputs = STEPS, OPERATIONS, OUTPUTS
    compile = staticmethod(compile_stage)
    controls = staticmethod(validate)
    finishing_settings = staticmethod(settings)
    engines = {"pixal3d"}
    extra_config_keys = {"exclude_views"}

    def config(self, data):
        if not isinstance(data, dict):
            raise ValueError("Supply an Orbit to Mesh configuration.")
        exclusions = data.get("exclude_views", [])
        if not isinstance(exclusions, list) or len(exclusions) > 6 or any(type(i) is not int or not 0 <= i <= 17999 for i in exclusions):
            raise ValueError("Choose valid source frame numbers to exclude.")
        return {**super().config({"selection": SELECTION, **data, "engine": "pixal3d"}),
                "exclude_views": sorted(set(exclusions))}

    def update(self, ident, data):
        run = self.get(ident)
        prior = deepcopy(run["selection"])
        result = super().update(ident, data)
        if prior != run["selection"] and run.get("package"):
            run["stages"].pop("package", None)
            run.pop("package", None)
            self.save(run)
            return self.public(run)
        return result

    def stale_descendants(self, run, stale):
        invalid = set(stale)
        for stage, previous in PREVIOUS.items():
            if previous in invalid:
                invalid.add(stage)
        if invalid:
            invalid.add("package")
        return [stage for stage in run["stages"] if stage in invalid]

    def required_tools(self, run):
        return missing_tools()

    def needs_stage(self, run, stage):
        return stage != "texture" or any(variant != "print" for variant in run["selection"]["variants"])

    async def prepare_stage(self, run, stage):
        if stage in ("geometry", "refinement", "texture"):
            loop = asyncio.get_running_loop()

            def progress(value):
                loop.call_soon_threadsafe(run.update, {"dependency": value})

            try:
                await asyncio.to_thread(ensure, stage, self.root.parent / "wizard-runs",
                                        lambda: run["cancel"], run["id"], progress,
                                        texture_mode=run["settings"]["texture_mode"])
            finally:
                run.pop("dependency", None)

    def check_stage(self, stage, graph):
        from ..virtual_turntable.model_preflight import check_models
        check_models(graph)

    def public(self, run):
        payload = super().public(run)
        payload["exclude_views"] = run["exclude_views"]
        payload["views"] = deepcopy(run.get("views", [])) if "views" in run["stages"] else []
        return payload

    def fingerprint(self, run, stage):
        if stage == "turnaround":
            return super().fingerprint(run, stage)
        if stage == "package":
            return signature([run["selection"], self.controls(run["controls"])["bake"]["grounding"], run.get("metadata")])
        group = "pixal" if stage == "geometry" else "camera" if stage == "cameras" else stage
        controls = self.controls(run["controls"])
        control = controls.get(group)
        if stage == "cameras":
            control = [control, run["controls"]["frames"]]
        if stage == "geometry":
            # Preserve saved meshes when additional controls are at the tested recipe values.
            optional = {name + suffix for name in ("structure", "shape", "detail")
                        for suffix in ("_sampler", "_scheduler", "_denoise")}
            control = [omit_defaults(control, "pixal", optional), run["exclude_views"]]
        if stage == "refinement":
            control = omit_defaults(control, "refinement", {"cleanup_band", "cleanup_smoothing", "cleanup_project_back"})
        if stage not in STEPS:
            control = {key: run["settings"][key] for key in STAGE_KEYS[stage] if key != "quad_method"}
            if stage == "quads":
                control.update(fingerprint_fields(run["settings"]))
        if stage in ("balanced", "compact"):
            control.update({key: controls["bake"][key] for key in ("cage_distance", "ignore_backfaces")})
        if stage == "texture":
            control = texture_sampling_settings(run["settings"], control)
        return signature([run["version"], stage, control, self.fingerprint(run, PREVIOUS[stage])])

    def capture_stage(self, run, stage, outputs, native, artifact, record):
        if stage == "cameras":
            manifest = artifact("cameras", outputs["60"]["text"][0], preview=False)
            camera = json.loads(manifest.read_text(encoding="utf-8"))
            for name in ("cameras.txt", "images.txt"):
                record(Path(camera["camera_text"]) / name)
        elif stage == "views":
            manifest = artifact("views_manifest", outputs["62"]["text"][0], preview=False)
            native("frames", "63", "images")
            review = json.loads(manifest.read_text(encoding="utf-8"))
            run["views"] = []
            for frame in review["frames"]:
                path = record(manifest.parent / frame["file_path"])
                relative = path.relative_to(self.output_root)
                run["views"].append({**frame, "image": view_url(
                    dict(filename=path.name, subfolder=relative.parent.as_posix(), type="output"))})
            run["reconstruction"] = {"registered_cameras": review["registered_views"]}
        elif stage == "geometry":
            path = native("raw", "382", "3d")
            run["checkpoints"]["decoded"] = str(path)
            front = native("front", "340", "images")
            run["checkpoints"]["front"] = front.relative_to(self.output_root).as_posix() + " [output]"
        elif stage == "refinement":
            native("refined", "2005", "3d")
            native("clean", "2017", "3d")
            if outputs.get("2015", {}).get("text"):
                run["geometry_audit"] = json.loads(outputs["2015"]["text"][0])
        elif stage == "texture":
            native("texture", "2024", "3d")
        else:
            return False
        return True

    def metadata(self, run):
        from ..image_to_3d.worker_models import texture_dependencies

        base = ["virtual_ph3", "virtual_h3", "virtual_orbit_lora", "virtual_kjnodes",
                "virtual_colmap", "birefnet", "dinov3", "pixal3d", "hi3d", "pymeshlab"]
        if run["controls"]["orbit"]["turbo"]:
            base.append("virtual_larry_turbo")
        mode = run["settings"]["texture_mode"]
        keys = {"detailed": "texture", "game_balanced": "balanced", "game_compact": "compact",
                "print": "print", "quad_light": "quad_manifest"}
        receipts = []
        for variant in run["selection"]["variants"]:
            path = Path(run["checkpoints"][keys[variant]])
            resources = list(base)
            if variant != "print":
                resources += ["trellis2", "trellis_wrapper"]
                if mode == "smd":
                    resources.append("trellis_smd_texture")
            if variant == "quad_light":
                resources += manifest_resources(path)
                path = path.with_name("editable-quads.blend")
            if variant == "print" and run.get("print_report", {}).get("contact_repair"):
                resources.append("meshlib")
            receipts.append({"variant_id": variant, "sha256": digest(path), "resources": list(dict.fromkeys(resources)),
                             "validation": [{"name": TITLE + " production", "status": "matched",
                                             "note": "File digest bound to the completed run."}]})
        lock = json.loads(Path(__file__).resolve().parents[3].joinpath("models.lock.json").read_text(encoding="utf-8"))
        production = {"method": METHOD, "workflow_title": TITLE, "run_id": run["id"],
                      "controls": run["controls"], "settings": run["settings"], "selection": run["selection"],
                      "source_sha256": digest(self.input_root / run["references"][0]["filename"]),
                      "views": [{k: v for k, v in frame.items() if k not in ("image", "file_path")}
                                for frame in run["views"] if frame["source_frame"] not in run["exclude_views"]],
                      "models": {key: {k: v for k, v in lock["models"][key].items()
                                        if k in ("repo", "file", "revision", "sha256", "license", "license_url")}
                                 for key in ("pixal_multiview", "shape_vae", "dino", "birefnet")}}
        if self.needs_stage(run, "texture"):
            production["texture_models"] = texture_dependencies(lock, mode)
        if run.get("image_creation"):
            production["image_creation"] = run["image_creation"]
        if run.get("quad_report"):
            production["quad_retopology"] = run["quad_report"]
        return {"workflow_version": run["version"], "production": production, "receipts": receipts,
                "warnings": run.get("quad_report", {}).get("warnings", [])}
