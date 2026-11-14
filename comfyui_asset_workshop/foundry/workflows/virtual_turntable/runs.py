"""Durable Virtual Turntable sessions on Foundry's queue and export machinery."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import re
import time
import uuid

from ...artifacts import digest, owned_path
from ...quad_policy import manifest_resources
from ..image_creation.definition import filename
from ..image_creation.lineage import resolve_handoff
from ..image_to_3d.definition import DEFAULT_SELECTION, resolve_settings
from ..image_to_3d.runs import WizardRuns, output_entry, signature, view_url
from .definition import ENGINES, METHOD, defaults, validated_settings
from .graph import FINISHING, OFFSET, compile_stage
from .runtime import missing
from .model_preflight import check_models

ACTIVE = None
ORBIT_ACTIVE = None
ORBIT_SPLAT_ACTIVE = None
STEPS = {
    "turnaround": "Generating the four-view turnaround sheet",
    "orbit": "Generating the 360° orbit",
    "frames": "Preparing masked orbit frames",
    "geometry": "Reconstructing the mesh from orbit frames",
    "texture": "Finishing the mesh and projecting orbit colors",
}
OPERATIONS = {
    "turnaround": ("turnaround",),
    "orbit": ("orbit",),
    "frames": ("frames",),
    "reconstruct": ("frames", "geometry"),
    "finish": ("texture",),
    "rocket": tuple(STEPS),
}
OUTPUTS = {
    "turnaround": ("sheet",), "orbit": ("orbit",),
    "frames": ("frame_set", "frames"),
    "geometry": ("project", "raw"), "texture": ("clean", "refined", "texture", "front"),
}
DERIVATIVES = (("game_balanced", "balanced"), ("game_compact", "compact"), ("quad_light", "quads"), ("print", "print"))


def busy():
    from ..orbit_with_splats.hybrid import ENCODERS
    return bool(ENCODERS) or any(service and service.tasks for service in (ACTIVE, ORBIT_ACTIVE, ORBIT_SPLAT_ACTIVE))


class VirtualTurntableRuns(WizardRuns):
    method = METHOD
    title = "Virtual Turntable"
    offset = OFFSET
    steps = STEPS
    operations = OPERATIONS
    outputs = OUTPUTS
    compile = staticmethod(compile_stage)
    controls = staticmethod(validated_settings)
    engines = ENGINES
    finishing_settings = staticmethod(lambda controls, overrides: resolve_settings("default", overrides))
    engine_message = "Choose Meshroom / AliceVision or COLMAP + OpenMVS."
    extra_config_keys = set()

    def required_tools(self, run):
        return missing(run["engine"])

    async def prepare_stage(self, run, stage):
        if stage == "texture" and run["controls"]["refinement"]["refine"]:
            from ..image_to_3d.readiness import ensure
            await asyncio.to_thread(ensure, "refinement", self.root, lambda: run["cancel"], run["id"])

    def check_stage(self, stage, graph):
        if stage in ("turnaround", "orbit", "geometry"):
            check_models(graph)

    def config(self, data):
        allowed = {"name", "image", "engine", "controls", "selection", "overrides", "image_creation"}
        if not isinstance(data, dict) or set(data) - (allowed | self.extra_config_keys):
            raise ValueError("Supply a Virtual Turntable configuration.")
        name = data.get("name", "")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or any(ord(c) < 32 for c in name):
            raise ValueError("Enter an asset name of 1–100 characters.")
        engine = data.get("engine")
        if engine not in self.engines:
            raise ValueError(self.engine_message)
        image = filename(data.get("image", ""))
        path = owned_path(self.input_root, self.input_root / image)
        if not path.is_file():
            raise ValueError("Choose an imported reference image.")
        overrides = data.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("Supply finishing overrides as an object.")
        controls = self.controls(data.get("controls", {}))
        settings = self.finishing_settings(controls, overrides)
        return {
            "name": name.strip(), "engine": engine, "controls": controls,
            "references": [{"filename": image, "role": "primary"}],
            "selection": self.selection(data.get("selection", DEFAULT_SELECTION)), "settings": settings,
            "overrides": overrides, "image_creation": resolve_handoff(self.root.parent / "image-creation",
                data.get("image_creation"), [{"filename": image, "sha256": digest(path)}]),
        }

    def create(self, data):
        config = self.config(data)
        ident = uuid.uuid4().hex
        run = dict(config, id=ident, slug=self.method, method=self.method, version=self.method+"/1",
                   created=time.time(), status="idle", stage="", error="", cancel=False,
                   stages={}, checkpoints={}, previews={}, outputs={}, events=[], category="props", profile="default")
        self.save(run)
        self.runs[ident] = run
        return self.public(run)

    def update(self, ident, data):
        run = self.get(ident)
        if ident in self.tasks:
            raise ValueError("Wait for this " + self.title + " run to finish before editing its settings.")
        config = self.config(data)
        if self.method == METHOD:
            # Browser JSON represents whole numbers as integers. Preserve the
            # recorded representation of unchanged values in older sessions.
            for group, fields in run["controls"].items():
                for key, value in fields.items():
                    if key in config["controls"][group] and config["controls"][group][key] == value:
                        config["controls"][group][key] = value
        run.update(config)
        self.invalidate(run)
        self.save(run)
        return self.public(run)

    def invalidate(self, run):
        stale = [stage for stage in run["stages"] if not self.fresh(run, stage)
                 and not (stage == "orbit" and self.retained_orbit_lineage(run))]
        stale = self.stale_descendants(run, stale)
        for stage in stale:
            run["stages"].pop(stage)
            for key in self.outputs.get(stage, (stage, "quad_manifest") if stage == "quads" else (stage,)):
                run["checkpoints"].pop(key, None)
                run["previews"].pop(key, None)
            if stage == "frames":
                run.pop("frame_review", None)
            if stage == "quads":
                run.pop("quad_report", None)
            if stage == "refinement":
                run.pop("geometry_audit", None)
        if stale:
            run["outputs"] = {}
            run.pop("package", None)
            run.pop("measurements", None)
            run.pop("metadata", None)
        if "geometry" in stale or "views" in stale:
            run.pop("reconstruction", None)
            if self.method == METHOD and "frames" not in run["stages"]:
                run["checkpoints"].pop("frames", None)
                run["previews"].pop("frames", None)
        return stale

    def retained_orbit_lineage(self, run):
        """Deleting an orbit can leave a valid downstream reconstruction."""
        orbit = run["checkpoints"].get("orbit")
        if not orbit or Path(orbit).exists():
            return False
        stages = run["stages"]
        derived_stage = "cameras" if "cameras" in self.steps else "geometry"
        return (stages["orbit"]["fingerprint"] == self.fingerprint(run, "orbit")
                and self.fresh(run, derived_stage))

    def stale_descendants(self, run, stale):
        if "frames" not in stale:
            return stale
        after_frames = set(STEPS) - {"turnaround", "orbit"}
        return [stage for stage in run["stages"]
                if stage in stale or stage in after_frames or stage in FINISHING or stage == "refinement"]

    def public(self, run):
        result = super().public(run)
        result.pop("turnaround", None)
        orbit = run["checkpoints"].get("orbit")
        if orbit and not Path(orbit).is_file():
            result["previews"].pop("orbit", None)
            result["completed"] = [stage for stage in result["completed"] if stage != "orbit"]
        result.update(engine=run["engine"], controls=self.controls(run["controls"]),
                      reconstruction=deepcopy(run.get("reconstruction")),
                      frame_review=deepcopy(run.get("frame_review")),
                      stage_label=self.steps.get(run["stage"], run["stage"].replace("_", " ").capitalize()))
        if result.get("package"):
            result["package"]["download"] = f"/mumblebox-foundry/v1/{self.method}/runs/{run['id']}/package"
        return result

    def fingerprint(self, run, stage):
        controls = run["controls"]
        def old_compatible(group, added_fields):
            base = defaults()[group]
            return {key: value for key, value in controls[group].items()
                    if key not in added_fields or value != base[key]}

        if stage == "turnaround":
            source = owned_path(self.input_root, self.input_root / run["references"][0]["filename"])
            return signature([run["version"], stage, digest(source),
                              old_compatible("turnaround", {"sampler", "sigmas", "video_shift", "decode_tile"})
                              if self.method == METHOD else controls["turnaround"]])
        if stage == "orbit":
            return signature([self.fingerprint(run, "turnaround"), stage, old_compatible("orbit",
                {"denoise", "chunk_threshold", "decode_overlap", "temporal_overlap"})])
        if stage == "frames":
            return signature([self.fingerprint(run, "orbit"), stage, controls["frames"]])
        if stage == "geometry":
            # Keep the established fingerprint for sessions created before frame review existed.
            return signature([self.fingerprint(run, "orbit"), stage, run["engine"], controls["frames"], controls[run["engine"]]])
        if stage in ("texture", "refinement"):
            group = "meshroom_finish" if run["engine"] == "meshroom" else "openmvs_finish"
            appearance = {**defaults()[group], **controls.get(group, {})}
            return signature([self.fingerprint(run, "geometry"), stage, controls["refinement"], appearance])
        return super().fingerprint(run, stage)

    def start(self, ident, operation, client_id, request_id=None):
        run = self.get(ident)
        if operation not in self.operations:
            raise ValueError("Choose a " + self.title + " stage.")
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", request_id):
            raise ValueError("Supply a valid start request identifier.")
        if request_id == run.get("request_id"):
            if operation != run["operation"]:
                raise ValueError("This request identifier belongs to another stage.")
            return self.public(run)
        if self.tasks or self.native.active_ids() or self.legacy_busy():
            raise ValueError("Another Comfy or Foundry job is active. Wait for it to finish.")
        self.invalidate(run)
        first = self.operations[operation][0]
        order = tuple(self.steps)
        if order.index(first) and not self.fresh(run, order[order.index(first)-1]):
            # A new camera/mesh stage needs its actual orbit file.
            if order[order.index(first)-1] == "orbit" and run["checkpoints"].get("orbit"):
                raise ValueError("The saved orbit is missing. Generate the orbit again to use it.")
            raise ValueError("Complete and review the preceding stage first.")
        required = self.required_tools(run)
        if required:
            raise ValueError("The selected engine needs these local tools: " + ", ".join(required))
        run.update(status="running", stage="preparing", error="", cancel=False, operation=operation,
                   client_id=client_id, request_id=request_id, started_at=time.time())
        self.save(run)
        self.tasks[ident] = asyncio.create_task(self.execute(run, operation))
        return self.public(run)

    async def execute(self, run, operation):
        try:
            for stage in self.operations[operation]:
                if self.needs_stage(run, stage):
                    await self.stage(run, stage)
            if operation in ("finish", "rocket"):
                for variant, stage in DERIVATIVES:
                    if variant in run["selection"]["variants"]:
                        await self.stage(run, stage)
                run["metadata"] = await asyncio.to_thread(self.metadata, run)
                await self.stage(run, "package", reuse=False)
                from ...receipts import sync
                await asyncio.to_thread(sync, self.library)
            run.update(status="complete", error="")
        except (asyncio.CancelledError, InterruptedError):
            run.update(status="cancelled", error="Stopped. Completed stages are still available.")
        except Exception as error:
            run.update(status="failed", error=str(error))
        finally:
            run.pop("pending", None)
            try:
                if not self.native.active_ids():
                    run["cleanup"] = await self.lifecycle().release(self.title + " stage complete")
            except Exception as error:
                run["cleanup"] = {"status": "failed", "error": str(error)}
            finally:
                self.tasks.pop(run["id"], None)
                self.save(run)

    def needs_stage(self, run, stage):
        return True

    async def stage(self, run, stage, reuse=True):
        self.require_not_cancelled(run)
        if reuse and await asyncio.to_thread(self.fresh, run, stage):
            self.event(run, f"Reused saved {stage}.")
            return
        run["stage"] = stage
        self.event(run, self.steps.get(stage, f"Preparing {stage}."))
        await self.lifecycle().barrier()
        await self.lifecycle().release("before " + self.title + " " + stage)
        self.require_not_cancelled(run)
        await self.prepare_stage(run, stage)
        self.require_not_cancelled(run)
        graph = self.compile(stage, run, self.output_root)
        self.check_stage(stage, graph)
        ident = str(uuid.uuid4())
        run["pending"] = dict(stage=stage, prompt_id=ident, fingerprint=self.fingerprint(run, stage),
                              nodes=list(graph), started=time.time())
        self.save(run)
        if stage == "orbit":
            await self.native.submit(graph, ident, run["client_id"], preview_method="latent2rgb")
        else:
            await self.native.submit(graph, ident, run["client_id"])
        await self.accept_pending(run)
        self.require_not_cancelled(run)

    async def accept_pending(self, run):
        pending = run["pending"]
        history = await self.native.wait(pending["prompt_id"], 7200, lambda: run["cancel"])
        self.require_not_cancelled(run)
        status = history.get("status", {})
        if status.get("status_str") != "success":
            errors = [message[1].get("exception_message", "") for message in status.get("messages", [])
                      if message[0] == "execution_error"]
            raise ValueError(self.title + " could not finish the stage. " + (" ".join(errors) or "Comfy interrupted the run.")[:3000])
        outputs = {str(int(key)-self.offset): value for key, value in history.get("outputs", {}).items()}
        run["outputs"].update(history.get("outputs", {}))
        files = {}

        def record(path):
            path = owned_path(self.output_root, path)
            if not path.is_file():
                raise ValueError("The stage did not return its expected saved output.")
            files[str(path)] = digest(path)
            return path

        def artifact(key, path, preview=True):
            path = record(path)
            run["checkpoints"][key] = str(path)
            if preview:
                relative = path.relative_to(self.output_root)
                run["previews"][key] = view_url(dict(filename=path.name, subfolder=relative.parent.as_posix(), type="output"))
            return path

        def native(key, node, kind):
            entry = output_entry(outputs, node, kind)
            return artifact(key, self.file_entry(entry))

        stage = pending["stage"]
        if stage == "turnaround":
            sheet = native("sheet", "18", "images")
            run["checkpoints"]["sheet"] = sheet.relative_to(self.output_root).as_posix() + " [output]"
        elif stage == "orbit":
            entries = [item for values in outputs.get("44", {}).values() if isinstance(values, list)
                       for item in values if isinstance(item, dict) and item.get("type") == "output"
                       and str(item.get("filename", "")).lower().endswith((".mp4", ".webm", ".mov"))]
            if not entries:
                raise ValueError("Comfy did not return a saved orbit video.")
            artifact("orbit", self.file_entry(entries[0]))
        elif stage == "frames":
            root = owned_path(self.output_root, outputs["49"]["text"][0])
            manifest = record(root / "frames.json")
            frames = json.loads(manifest.read_text(encoding="utf-8"))
            for index in range(frames["count"]):
                for folder in ("frames", "masks"):
                    record(root / folder / f"frame_{index:05d}.png")
            run["checkpoints"]["frame_set"] = str(root)
            run["frame_review"] = {key: frames[key] for key in ("count", "width", "height", "source_indices", "source_video")
                                   if key in frames}
            native("frames", "49", "images")
        elif self.capture_stage(run, stage, outputs, native, artifact, record):
            pass
        elif stage == "geometry":
            report = json.loads(outputs["55"]["text"][0])
            project = owned_path(self.output_root, report["project"])
            record(project / "result.json")
            run["checkpoints"]["project"] = str(project)
            artifact("raw", report["preview"])
            if "49" in outputs:
                native("frames", "49", "images")
            cameras = report.get("camera_validation", {})
            run["reconstruction"] = {key: report[key] for key in ("faces", "registered_cameras", "frames", "watertight") if key in report}
            if cameras:
                run["reconstruction"]["camera_validation"] = cameras
            if report.get("orbit_coverage"):
                run["reconstruction"]["orbit_coverage"] = report["orbit_coverage"]
        elif stage == "texture":
            native("clean", "2017", "3d")
            native("texture", "2024", "3d")
            front = native("front", "2019", "images")
            run["checkpoints"]["front"] = front.relative_to(self.output_root).as_posix() + " [output]"
            if run["controls"]["refinement"]["refine"]:
                native("refined", "2005", "3d")
            # Standard print/bake stages refer to the native refinement checkpoint.
            run["stages"]["refinement"] = dict(fingerprint=self.fingerprint(run, "refinement"), files=files)
        elif stage in ("balanced", "compact"):
            native(stage, {"balanced": "2034", "compact": "2044"}[stage], "3d")
        elif stage == "quads":
            report = json.loads(outputs["3001"]["text"][0])
            manifest = Path(report["export_dir"]) / "manifest.json"
            artifact("quad_manifest", manifest, preview=False)
            artifact("quads", manifest.with_name("runtime.glb"))
            run["quad_report"] = report
        elif stage == "print":
            run["print_report"] = json.loads(outputs["2050"]["text"][0])
            artifact("print", run["print_report"]["output"])
        elif stage == "package":
            report = json.loads(outputs["3010"]["text"][1])
            record(report["archive_path"])
            run["package"] = report
            for key, path in report.get("grounded_previews", {}).items():
                relative = record(path).relative_to(self.output_root)
                run["previews"][key] = view_url(dict(filename=relative.name, subfolder=relative.parent.as_posix(), type="output"))
        run["stages"][stage] = dict(fingerprint=pending["fingerprint"], files=files, prompt_id=pending["prompt_id"],
                                   seconds=time.time()-pending["started"])
        run.pop("pending", None)
        self.event(run, f"Completed {stage}. Saved files verified.")

    def capture_stage(self, run, stage, outputs, native, artifact, record):
        return False

    def metadata(self, run):
        base = ["virtual_ph3", "virtual_h3", "virtual_orbit_lora", "virtual_kjnodes", "birefnet"]
        base += ["virtual_meshroom", "virtual_alicevision"] if run["engine"] == "meshroom" else [
            "virtual_colmap", "virtual_openmvs", "virtual_openmvs_texture"]
        if run["controls"]["orbit"]["turbo"]:
            base.append("virtual_larry_turbo")
        if run["controls"]["refinement"]["refine"]:
            base.append("hi3d")
        receipts = []
        checkpoints = {"detailed": "texture", "game_balanced": "balanced", "game_compact": "compact", "print": "print"}
        for variant in run["selection"]["variants"]:
            resources = list(base)
            if variant in ("game_balanced", "game_compact", "quad_light"):
                resources.append("pymeshlab")
            if variant in ("game_balanced", "game_compact"):
                resources.append("virtual_cumesh")
            if variant == "quad_light":
                manifest = run["checkpoints"]["quad_manifest"]
                resources += manifest_resources(manifest)
                path = Path(manifest).with_name("editable-quads.blend")
            else:
                path = Path(run["checkpoints"][checkpoints[variant]])
            if variant == "print" and run.get("print_report", {}).get("contact_repair"):
                resources.append("meshlib")
            receipts.append({"variant_id": variant, "sha256": digest(path), "resources": resources,
                             "validation": [{"name": "Virtual Turntable production", "status": "matched",
                                             "note": "File digest bound to the completed run."}]})
        result = {"workflow_version": run["version"], "receipts": receipts, "production": {
            "method": METHOD, "workflow_title": "Virtual Turntable", "engine": run["engine"], "run_id": run["id"],
            "stages": {key: {name: value[name] for name in ("prompt_id", "seconds") if name in value}
                       for key, value in run["stages"].items() if key != "package"},
            "source_artifacts": {**{key: digest(run["checkpoints"][key]) for key in ("raw", "clean", "texture")},
                                 "orbit": run["stages"]["orbit"]["files"][run["checkpoints"]["orbit"]]},
            "orbit_settings": run["controls"]["orbit"],
            "frame_review": run.get("frame_review"),
            "reconstruction": run.get("reconstruction"),
        }}
        if run.get("image_creation"):
            result["production"]["image_creation"] = run["image_creation"]
        return result
