"""Independent Orbit with Splats run state on the shared orbit runner."""
import asyncio
import json
from pathlib import Path

from ..image_to_3d.runs import signature
from ..orbit_to_mesh import runs as orbit
from .definition import METHOD, OFFSET, TITLE, missing_tools, validate
from .graph import TRAIN, compile_stage
from .package import build_pair

STEPS = {**orbit.STEPS, "splat": "Training the aligned Gaussian splat with Brush"}
OPERATIONS = {**orbit.OPERATIONS, "finish": (*orbit.OPERATIONS["finish"], "splat"), "rocket": tuple(STEPS)}
OUTPUTS = {**orbit.OUTPUTS, "splat": ("pair", "paired_mesh", "gaussian", "pair_zip", "training_views", "hybrid")}

class OrbitSplatRuns(orbit.OrbitRuns):
    method, title, offset = METHOD, TITLE, OFFSET
    steps, operations, outputs = STEPS, OPERATIONS, OUTPUTS
    compile = staticmethod(compile_stage)
    controls = staticmethod(validate)

    def required_tools(self, run):
        return missing_tools()

    def needs_stage(self, run, stage):
        return True

    def stale_descendants(self, run, stale):
        changed = super().stale_descendants(run, stale)
        if "splat" in run["stages"] and set(changed).intersection(("cameras", "views", "geometry", "refinement", "texture")):
            changed.append("splat")
        return changed

    def fingerprint(self, run, stage):
        if stage == "splat":
            controls = self.controls(run["controls"])
            return signature([run["version"], stage, controls["splat"], controls["bake"]["grounding"],
                              self.fingerprint(run, "texture"), self.fingerprint(run, "cameras")])
        return super().fingerprint(run, stage)

    def capture_stage(self, run, stage, outputs, native, artifact, record):
        if stage != "splat":
            captured = super().capture_stage(run, stage, outputs, native, artifact, record)
            if stage == "cameras":
                manifest = Path(run["checkpoints"]["cameras"])
                camera = json.loads(manifest.read_text(encoding="utf-8"))
                record(Path(camera["camera_text"]) / "points3D.txt")
            return captured
        manifest = artifact("pair", outputs[TRAIN]["text"][0], preview=False)
        pair = json.loads(manifest.read_text(encoding="utf-8"))
        artifact("paired_mesh", manifest.parent / pair["mesh"])
        artifact("gaussian", manifest.parent / pair["splat"])
        artifact("training_views", manifest.parent / "training-views.jpg")
        record(manifest.parent / "alignment.json")
        return True

    async def stage(self, run, stage, reuse=True):
        await super().stage(run, stage, reuse)
        if stage != "splat":
            return
        self.require_not_cancelled(run)
        archive = await asyncio.to_thread(build_pair, self.output_root, run["checkpoints"])
        self.require_not_cancelled(run)
        run["checkpoints"]["pair_zip"] = str(archive)
        self.save(run)

    def public(self, run):
        result = super().public(run)
        pair = run["checkpoints"].get("pair")
        if pair and Path(pair).is_file():
            result["pair"] = json.loads(Path(pair).read_text(encoding="utf-8"))
        hybrid = run["checkpoints"].get("hybrid")
        if hybrid and Path(hybrid).is_file():
            result["hybrid"] = f"/mumblebox-foundry/v1/{METHOD}/runs/{run['id']}/artifacts/hybrid"
        return result

    def metadata(self, run):
        info = super().metadata(run)
        info["production"].update(method=METHOD, workflow_title=TITLE)
        return info
